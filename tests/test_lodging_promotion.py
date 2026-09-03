import os
import unittest
from datetime import date
from unittest.mock import DEFAULT, patch

import psycopg2
import psycopg2.extras

from lodging_promotion import (
    _apply_review_decision,
    _build_targets,
    _canonical_hash,
    approve_production_manifest,
    create_production_baseline_manifest,
    create_resolved_production_manifest,
    run_production_manifest_dry_run,
    _validate_target_admission,
)
from lodging_data_contract import GOVERNMENT_LODGING_SOURCES


class _SharedTestConnection:
    """함수가 close()해도 fixture의 세션을 유지하는 작은 DB 연결 래퍼."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        # 각 production manifest 함수가 소유 연결을 닫는 계약을 그대로 실행하되,
        # 테스트가 같은 임시 테이블 세션을 계속 사용할 수 있게 한다.
        return None


class LodgingPromotionDatabaseFixture:
    """운영 DB와 지문이 다른 DB 세션에 임시 manifest 원장을 만든다."""

    def __init__(self):
        database_url = os.environ.get("LODGING_PROMOTION_TEST_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        if not database_url or not os.environ.get("PROD_DATABASE_URL"):
            raise unittest.SkipTest(
                "개발·운영 DB URL이 모두 있는 환경에서만 promotion DB fixture를 실행합니다."
            )
        self.connection = psycopg2.connect(
            database_url,
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        if self._fingerprint(self.connection) == self._production_fingerprint():
            self.connection.close()
            raise RuntimeError(
                "promotion 테스트 DB가 운영 DB와 같아 fixture를 시작하지 않았습니다."
            )
        self.connection.rollback()
        self.connection.autocommit = True
        self._create_temp_tables()
        self.connection.autocommit = False
        self.shared_connection = _SharedTestConnection(self.connection)

    @staticmethod
    def _fingerprint(connection):
        cur = connection.cursor()
        try:
            cur.execute(
                """
                SELECT current_database() AS db,
                       inet_server_addr()::text AS host,
                       inet_server_port() AS port
                """
            )
            row = cur.fetchone()
            return row["db"], row["host"], row["port"]
        finally:
            cur.close()

    def _production_fingerprint(self):
        production = psycopg2.connect(
            os.environ["PROD_DATABASE_URL"],
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        try:
            production.set_session(readonly=True)
            return self._fingerprint(production)
        finally:
            production.close()

    def _create_temp_tables(self):
        cur = self.connection.cursor()
        try:
            cur.execute(
                """
                CREATE TEMP TABLE admin_users (
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                );
                CREATE TEMP TABLE lodging_source_batches (
                    id BIGINT PRIMARY KEY,
                    batch_key TEXT NOT NULL UNIQUE,
                    source_key TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_ext TEXT NOT NULL,
                    file_sha256 TEXT NOT NULL,
                    reference_date DATE NOT NULL,
                    status TEXT NOT NULL,
                    total_rows INTEGER NOT NULL,
                    parsed_rows INTEGER NOT NULL,
                    valid_rows INTEGER NOT NULL,
                    review_rows INTEGER NOT NULL,
                    file_data BYTEA NOT NULL,
                    result JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE TEMP TABLE lodging_source_rows (
                    id BIGINT PRIMARY KEY,
                    batch_id BIGINT NOT NULL REFERENCES lodging_source_batches(id),
                    row_number INTEGER NOT NULL,
                    snapshot_key TEXT NOT NULL,
                    authority_code TEXT,
                    source_permit_number TEXT,
                    permit_number TEXT,
                    biz_name TEXT,
                    raw_hygiene_type TEXT,
                    service_category TEXT,
                    legacy_lodging_type TEXT,
                    raw_status TEXT,
                    status_bucket TEXT NOT NULL,
                    road_address TEXT,
                    jibun_address TEXT,
                    raw_record JSONB NOT NULL,
                    row_state TEXT NOT NULL,
                    review_reason TEXT,
                    diff_kind TEXT NOT NULL
                );
                CREATE TEMP TABLE lodging_promotion_manifests (
                    id BIGSERIAL PRIMARY KEY,
                    manifest_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'draft',
                    source_batch_ids JSONB NOT NULL,
                    production_baseline_fingerprint TEXT NOT NULL,
                    target_payload_sha256 TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    result JSONB NOT NULL DEFAULT '{}'::jsonb,
                    error TEXT,
                    run_id TEXT NOT NULL UNIQUE,
                    created_by INTEGER REFERENCES admin_users(id),
                    approved_by INTEGER REFERENCES admin_users(id),
                    parent_manifest_id BIGINT REFERENCES lodging_promotion_manifests(id),
                    version_no INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    approved_at TIMESTAMP,
                    started_at TIMESTAMP,
                    heartbeat_at TIMESTAMP,
                    finished_at TIMESTAMP
                );
                CREATE TEMP TABLE lodging_promotion_rows (
                    promotion_manifest_id BIGINT NOT NULL
                        REFERENCES lodging_promotion_manifests(id) ON DELETE CASCADE,
                    source_row_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    production_match_state TEXT,
                    production_building_id INTEGER,
                    existing_applied_building_id INTEGER,
                    payload JSONB NOT NULL,
                    PRIMARY KEY (promotion_manifest_id, source_row_id)
                );
                CREATE TEMP TABLE lodging_promotion_review_decisions (
                    id BIGSERIAL PRIMARY KEY,
                    source_row_id BIGINT NOT NULL,
                    base_manifest_id BIGINT NOT NULL
                        REFERENCES lodging_promotion_manifests(id),
                    resulting_manifest_id BIGINT NOT NULL
                        REFERENCES lodging_promotion_manifests(id),
                    decision TEXT NOT NULL,
                    decision_note TEXT,
                    decided_by INTEGER NOT NULL REFERENCES admin_users(id),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(base_manifest_id, source_row_id)
                );
                INSERT INTO admin_users (id, email, password_hash)
                VALUES (1, 'fixture@example.invalid', 'fixture');
                """
            )
        finally:
            cur.close()

    def seed(self):
        cur = self.connection.cursor()
        try:
            source_keys = list(GOVERNMENT_LODGING_SOURCES)
            cur.executemany(
                """
                INSERT INTO lodging_source_batches (
                    id, batch_key, source_key, filename, file_ext,
                    file_sha256, reference_date, status, total_rows,
                    parsed_rows, valid_rows, review_rows, file_data
                ) VALUES (
                    %s, %s, %s, %s, 'csv', %s, %s, 'validated',
                    %s, %s, %s, %s, %s
                )
                """,
                [
                    (
                        index,
                        f"fixture:{source_key}",
                        source_key,
                        f"{source_key}.csv",
                        f"sha-{index}",
                        date(2026, 9, 1),
                        1 if source_key in {"tourism_lodging", "tourism_pension", "lodging"} else 0,
                        1 if source_key in {"tourism_lodging", "tourism_pension", "lodging"} else 0,
                        1 if source_key == "tourism_lodging" else 0,
                        1 if source_key in {"tourism_pension", "lodging"} else 0,
                        b"fixture",
                    )
                    for index, source_key in enumerate(source_keys, start=1)
                ],
            )
            rows = [
                (
                    101,
                    1,
                    "TOURISM:AUTH-1:ACTIVE-1",
                    "AUTH-1",
                    "ACTIVE-1",
                    "TOURISM:AUTH-1:ACTIVE-1",
                    "활성 숙소",
                    "관광숙박업",
                    "관광숙박",
                    "관광",
                    "영업/정상",
                    "active",
                    "서울특별시 중구 세종대로 1",
                    None,
                    {"객실수": "10"},
                    "validated",
                    None,
                    "new",
                ),
                (
                    102,
                    2,
                    "PENSION:AUTH-2:EXCLUDE-1",
                    "AUTH-2",
                    "EXCLUDE-1",
                    "PENSION:AUTH-2:EXCLUDE-1",
                    "제외할 검토 숙소",
                    "관광펜션업",
                    "관광숙박",
                    "관광",
                    "영업/정상",
                    "active",
                    "서울특별시 중구 세종대로 2",
                    None,
                    {},
                    "review_required",
                    "fixture 수동검토",
                    "review_required",
                ),
                (
                    103,
                    3,
                    "LODGING:HISTORY-1",
                    "AUTH-3",
                    "HISTORY-1",
                    "LODGING:HISTORY-1",
                    "역사 숙소",
                    None,
                    "미분류",
                    None,
                    "폐업",
                    "closed",
                    "서울특별시 중구 세종대로 3",
                    None,
                    {"업태구분명": "", "객실수": "4"},
                    "review_required",
                    "업태 공백·관리자 확인",
                    "review_required",
                ),
            ]
            cur.executemany(
                """
                INSERT INTO lodging_source_rows (
                    id, batch_id, row_number, snapshot_key, authority_code,
                    source_permit_number, permit_number, biz_name,
                    raw_hygiene_type, service_category, legacy_lodging_type,
                    raw_status, status_bucket, road_address, jibun_address,
                    raw_record, row_state, review_reason, diff_kind
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                [
                    (
                        row_id,
                        batch_id,
                        2,
                        snapshot_key,
                        authority_code,
                        source_permit,
                        permit,
                        biz_name,
                        raw_type,
                        category,
                        legacy_type,
                        raw_status,
                        status_bucket,
                        road,
                        jibun,
                        psycopg2.extras.Json(raw_record),
                        row_state,
                        review_reason,
                        diff_kind,
                    )
                    for (
                        row_id,
                        batch_id,
                        snapshot_key,
                        authority_code,
                        source_permit,
                        permit,
                        biz_name,
                        raw_type,
                        category,
                        legacy_type,
                        raw_status,
                        status_bucket,
                        road,
                        jibun,
                        raw_record,
                        row_state,
                        review_reason,
                        diff_kind,
                    ) in rows
                ],
            )
            self.connection.commit()
        finally:
            cur.close()

    def close(self):
        self.connection.close()


class LodgingPromotionDatabaseFlowTest(unittest.TestCase):
    """실제 manifest SQL을 임시 원장으로 실행하는 회귀 테스트."""

    def setUp(self):
        self.fixture = LodgingPromotionDatabaseFixture()
        self.fixture.seed()
        self.production_snapshot = (
            [],
            [
                {
                    "id": 901,
                    "road_address": "서울특별시 중구 세종대로 1",
                    "jibun_address": None,
                    "sgg_cd": None,
                    "umd_nm": None,
                    "jibun": None,
                    "lat": 37.0,
                    "lng": 127.0,
                    "lodging_type": None,
                }
            ],
            "fixture-production-baseline",
            ("fixture-production-db", "fixture-production-host", 5432),
        )
        self.patches = patch.multiple(
            "lodging_promotion",
            get_conn=DEFAULT,
            assert_development_staging=DEFAULT,
            assert_development_connection=DEFAULT,
            _fetch_production_snapshot=DEFAULT,
        )
        mocks = self.patches.start()
        mocks["get_conn"].return_value = self.fixture.shared_connection
        mocks["assert_development_staging"].return_value = None
        mocks["assert_development_connection"].return_value = None
        mocks["_fetch_production_snapshot"].return_value = self.production_snapshot
        self.production_snapshot_mock = mocks["_fetch_production_snapshot"]

    def tearDown(self):
        self.patches.stop()
        self.fixture.close()

    def _manifest_rows(self, manifest_id):
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                SELECT source_row_id, action, production_match_state,
                       production_building_id, existing_applied_building_id, payload
                  FROM lodging_promotion_rows
                 WHERE promotion_manifest_id=%s
                 ORDER BY source_row_id
                """,
                (manifest_id,),
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()

    def _manifest_snapshot(self, manifest_id):
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                SELECT row_count, target_payload_sha256, status, result
                  FROM lodging_promotion_manifests
                 WHERE id=%s
                """,
                (manifest_id,),
            )
            return dict(cur.fetchone())
        finally:
            cur.close()

    def _create_base_manifest(self):
        return create_production_baseline_manifest(created_by=1)

    def _resolve_and_approve(self):
        base = self._create_base_manifest()
        excluded = create_resolved_production_manifest(
            base["id"],
            102,
            decision="exclude",
            decided_by=1,
        )
        resolved = create_resolved_production_manifest(
            excluded["id"],
            103,
            decision="include_unclassified_history",
            decided_by=1,
        )
        approve_production_manifest(resolved["id"], approved_by=1)
        return base, excluded, resolved

    def test_review_exclude_and_history_include_create_versioned_audit_flow(self):
        base = self._create_base_manifest()
        base_snapshot = self._manifest_snapshot(base["id"])
        base_rows = self._manifest_rows(base["id"])
        self.assertEqual(base["row_count"], 3)
        self.assertEqual(base["result"]["manual_review_targets"], 2)

        excluded = create_resolved_production_manifest(
            base["id"],
            102,
            decision="exclude",
            decided_by=1,
            note="중복 검토 대상 제외",
        )
        child_snapshot = self._manifest_snapshot(excluded["id"])
        self.assertEqual(excluded["parent_manifest_id"], base["id"])
        self.assertEqual(excluded["version_no"], 2)
        self.assertEqual(excluded["row_count"], 2)
        self.assertEqual(excluded["result"]["manual_review_targets"], 1)
        self.assertEqual(child_snapshot["status"], "draft")

        # 부모 manifest의 행과 payload hash는 새 버전 생성 후에도 불변이다.
        self.assertEqual(base_snapshot, self._manifest_snapshot(base["id"]))
        self.assertEqual(base_rows, self._manifest_rows(base["id"]))

        included = create_resolved_production_manifest(
            excluded["id"],
            103,
            decision="include_unclassified_history",
            decided_by=1,
            note="폐업 역사 원장 보존",
        )
        self.assertEqual(included["parent_manifest_id"], excluded["id"])
        self.assertEqual(included["row_count"], 2)
        self.assertEqual(included["result"]["manual_review_targets"], 0)
        included_rows = self._manifest_rows(included["id"])
        self.assertEqual(
            _canonical_hash(included_rows),
            self._manifest_snapshot(included["id"])["target_payload_sha256"],
        )
        self.assertEqual(
            included_rows[-1]["payload"]["row_state"],
            "validated",
        )
        self.assertEqual(
            included_rows[-1]["payload"]["review_resolution"]["decision"],
            "include_unclassified_history",
        )

        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                SELECT source_row_id, base_manifest_id, resulting_manifest_id,
                       decision, decision_note
                  FROM lodging_promotion_review_decisions
                 ORDER BY id
                """
            )
            decisions = [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()
        self.assertEqual(
            [(row["source_row_id"], row["decision"]) for row in decisions],
            [(102, "exclude"), (103, "include_unclassified_history")],
        )
        self.assertEqual(
            [(row["base_manifest_id"], row["resulting_manifest_id"]) for row in decisions],
            [(base["id"], excluded["id"]), (excluded["id"], included["id"])],
        )

    def test_duplicate_and_stale_manifest_submissions_are_rejected(self):
        base = self._create_base_manifest()
        latest = create_resolved_production_manifest(
            base["id"],
            102,
            decision="exclude",
            decided_by=1,
        )
        with self.assertRaisesRegex(ValueError, "이미 해결"):
            create_resolved_production_manifest(
                base["id"],
                102,
                decision="exclude",
                decided_by=1,
            )
        with self.assertRaisesRegex(ValueError, "오래된 manifest"):
            create_resolved_production_manifest(
                base["id"],
                103,
                decision="include_unclassified_history",
                decided_by=1,
            )

        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_promotion_rows
                   SET payload=jsonb_set(payload, '{biz_name}', '"변경된 원장"')
                 WHERE promotion_manifest_id=%s AND source_row_id=103
                """,
                (latest["id"],),
            )
            self.fixture.connection.commit()
        finally:
            cur.close()
        with self.assertRaisesRegex(RuntimeError, "payload"):
            create_resolved_production_manifest(
                latest["id"],
                103,
                decision="include_unclassified_history",
                decided_by=1,
            )

    def test_review_resolution_is_atomic_when_child_write_fails(self):
        base = self._create_base_manifest()
        with patch(
            "lodging_promotion.psycopg2.extras.execute_values",
            side_effect=RuntimeError("fixture child row failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "child row"):
                create_resolved_production_manifest(
                    base["id"],
                    102,
                    decision="exclude",
                    decided_by=1,
                )

        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) AS count FROM lodging_promotion_manifests"
            )
            self.assertEqual(cur.fetchone()["count"], 1)
            cur.execute(
                "SELECT COUNT(*) AS count FROM lodging_promotion_review_decisions"
            )
            self.assertEqual(cur.fetchone()["count"], 0)
        finally:
            cur.close()

    def test_unresolved_approval_is_blocked_then_dry_run_verifies_payload(self):
        base = self._create_base_manifest()
        with self.assertRaisesRegex(ValueError, "미해결"):
            approve_production_manifest(base["id"], approved_by=1)

        excluded = create_resolved_production_manifest(
            base["id"],
            102,
            decision="exclude",
            decided_by=1,
        )
        resolved = create_resolved_production_manifest(
            excluded["id"],
            103,
            decision="include_unclassified_history",
            decided_by=1,
        )
        approved = approve_production_manifest(resolved["id"], approved_by=1)
        self.assertEqual(approved["status"], "approved")
        dry_run = run_production_manifest_dry_run(resolved["id"])
        self.assertEqual(dry_run["status"], "dry_run")
        self.assertTrue(dry_run["result"]["dry_run_verified"])
        self.assertTrue(dry_run["result"]["payload_hash_verified"])
        self.assertTrue(dry_run["result"]["production_baseline_unchanged"])
        self.assertEqual(dry_run["result"]["new_permits"], 2)
        self.assertEqual(dry_run["result"]["production_writes"], 0)
        self.assertFalse(dry_run["result"]["applied"])

        final_snapshot = self._manifest_snapshot(resolved["id"])
        self.assertEqual(final_snapshot["status"], "dry_run")
        self.assertEqual(final_snapshot["row_count"], 2)
        self.assertEqual(
            final_snapshot["target_payload_sha256"],
            _canonical_hash(self._manifest_rows(resolved["id"])),
        )

    def test_dry_run_rejects_wrong_new_permit_expectation(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_promotion_manifests
                   SET result=jsonb_set(result, '{new_permits}', '99')
                 WHERE id=%s
                """,
                (resolved["id"],),
            )
            self.fixture.connection.commit()
        finally:
            cur.close()
        with self.assertRaisesRegex(RuntimeError, "신규 permit 기대 수"):
            run_production_manifest_dry_run(resolved["id"])

    def test_dry_run_rejects_changed_payload(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_promotion_rows
                   SET payload=jsonb_set(payload, '{biz_name}', '"변경된 payload"')
                 WHERE promotion_manifest_id=%s AND source_row_id=101
                """,
                (resolved["id"],),
            )
            self.fixture.connection.commit()
        finally:
            cur.close()
        with self.assertRaisesRegex(RuntimeError, "payload"):
            run_production_manifest_dry_run(resolved["id"])

    def test_dry_run_rejects_changed_production_baseline(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        changed_snapshot = list(self.production_snapshot)
        changed_snapshot[2] = "changed-production-baseline"
        self.production_snapshot_mock.return_value = tuple(changed_snapshot)
        with self.assertRaisesRegex(RuntimeError, "운영 기준선"):
            run_production_manifest_dry_run(resolved["id"])


class LodgingPromotionTest(unittest.TestCase):
    def test_new_row_uses_unique_existing_building_without_auto_create(self):
        staging = [
            {
                "source_row_id": 1,
                "batch_id": 10,
                "permit_number": "P-1",
                "biz_name": "숙소",
                "raw_status": "영업/정상",
                "status_bucket": "active",
                "road_address": "서울특별시 중구 세종대로 1",
                "jibun_address": None,
                "raw_hygiene_type": "숙박업(일반)",
                "raw_record": {},
            }
        ]
        buildings = [
            {
                "id": 7,
                "road_address": "서울특별시 중구 세종대로 1",
                "jibun_address": None,
                "sgg_cd": None,
                "umd_nm": None,
                "jibun": None,
            }
        ]
        targets, summary = _build_targets(staging, [], buildings)
        self.assertEqual(targets[0]["action"], "insert")
        self.assertEqual(targets[0]["production_match_state"], "existing_building")
        self.assertEqual(targets[0]["production_building_id"], 7)
        self.assertEqual(summary["would_auto_create_master_buildings"], 0)

    def test_existing_link_is_preserved(self):
        staging = [
            {
                "source_row_id": 2,
                "batch_id": 10,
                "permit_number": "P-2",
                "biz_name": "새 이름",
                "raw_status": "영업/정상",
                "status_bucket": "active",
                "road_address": "새 주소",
                "jibun_address": None,
                "raw_hygiene_type": "숙박업(일반)",
                "raw_record": {"객실수": ""},
                "diff_kind": "changed",
            }
        ]
        registry = [
            {
                "permit_number": "P-2",
                "biz_name": "옛 이름",
                "biz_status_name": "영업/정상",
                "room_count": 10,
                "hygiene_type": "숙박업(일반)",
                "applied_building_id": 99,
                "road_address": "옛 주소",
                "jibun_address": None,
            }
        ]
        targets, summary = _build_targets(staging, registry, [])
        self.assertEqual(targets[0]["action"], "update")
        self.assertEqual(targets[0]["existing_applied_building_id"], 99)
        self.assertEqual(summary["existing_links_preserved"], 1)

    def test_duplicate_permit_is_rejected(self):
        targets = [
            {"payload": {"permit_number": "P-1", "row_state": "validated"}},
            {"payload": {"permit_number": "P-1", "row_state": "validated"}},
        ]
        with self.assertRaisesRegex(RuntimeError, "중복"):
            _validate_target_admission(targets, allow_manual_review=True)

    def test_unresolved_review_row_blocks_approval_or_apply(self):
        targets = [
            {
                "payload": {
                    "permit_number": "P-2",
                    "row_state": "review_required",
                }
            }
        ]
        with self.assertRaisesRegex(RuntimeError, "수동 검토"):
            _validate_target_admission(targets, allow_manual_review=False)
        self.assertEqual(
            _validate_target_admission(targets, allow_manual_review=True),
            1,
        )

    def test_review_include_creates_resolved_copy_without_mutating_original(self):
        target = {
            "source_row_id": 3,
            "action": "insert",
            "payload": {
                "permit_number": "P-3",
                "row_state": "review_required",
                "review_reason": "업태 공백·관리자 확인",
                "raw_hygiene_type": None,
                "service_category": "미분류",
                "status_bucket": "closed",
                "raw_record": {"업태구분명": ""},
            },
        }
        resolved = _apply_review_decision(
            target,
            "include_unclassified_history",
            note="폐업 역사 원장 보존",
        )
        self.assertEqual(target["payload"]["row_state"], "review_required")
        self.assertEqual(resolved["payload"]["row_state"], "validated")
        self.assertIsNone(resolved["payload"]["review_reason"])
        self.assertEqual(
            resolved["payload"]["original_review_reason"],
            "업태 공백·관리자 확인",
        )
        self.assertEqual(
            resolved["payload"]["review_resolution"]["decision"],
            "include_unclassified_history",
        )

    def test_review_exclude_omits_target_from_new_manifest(self):
        target = {
            "payload": {
                "permit_number": "P-4",
                "row_state": "review_required",
            }
        }
        self.assertIsNone(_apply_review_decision(target, "exclude"))

    def test_review_decision_rejects_non_review_target(self):
        target = {
            "payload": {
                "permit_number": "P-5",
                "row_state": "validated",
            }
        }
        with self.assertRaisesRegex(ValueError, "이미 해결"):
            _apply_review_decision(target, "exclude")

    def test_unclassified_history_include_rejects_other_review_reasons(self):
        target = {
            "payload": {
                "permit_number": "P-6",
                "row_state": "review_required",
                "raw_hygiene_type": None,
                "service_category": "미분류",
                "status_bucket": "active",
            }
        }
        with self.assertRaisesRegex(ValueError, "폐업 원장"):
            _apply_review_decision(target, "include_unclassified_history")


if __name__ == "__main__":
    unittest.main()