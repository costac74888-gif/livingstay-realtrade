import os
import unittest
from datetime import date
from unittest.mock import DEFAULT, patch

import psycopg2
import psycopg2.extras

from addr_norm import normalize_jibun_prefix, normalize_road_prefix
from apply_lodging_promotion import (
    _hold_verified_manifest_source,
    _unresolved_source_review_count,
)
from lodging_promotion import (
    _apply_review_decision,
    _build_targets,
    _canonical_hash,
    _get_development_connection,
    approve_production_manifest,
    create_production_baseline_manifest,
    create_resolved_production_manifest,
    compare_parallel_results,
    run_production_manifest_dry_run,
    _surface_expected_ranges,
    _surface_snapshot,
    _validate_target_admission,
    _decode_legacy_sync_control,
    CUTOVER_MINIMUM_CONSECUTIVE_CLEAN,
    CUTOVER_MINIMUM_OBSERVATIONS,
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

    def test_applied_review_decisions_unblock_the_same_source_batch(self):
        base = self._create_base_manifest()
        cur = self.fixture.connection.cursor()
        try:
            self.assertEqual(
                _unresolved_source_review_count(cur, 3, "rural_homestay"),
                1,
            )
        finally:
            cur.close()

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
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                "UPDATE lodging_promotion_manifests SET status='applied' WHERE id=%s",
                (resolved["id"],),
            )
            self.fixture.connection.commit()
            self.assertEqual(
                _unresolved_source_review_count(cur, 3, "rural_homestay"),
                0,
            )
        finally:
            cur.close()

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
        self.assertEqual(
            dry_run["result"]["screen_expected_ranges"]["stats"]["room_count"],
            {"expected": 10, "min": 10, "max": 10},
        )

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

    def test_dry_run_rejects_source_row_changed_after_approval(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_source_rows
                   SET biz_name='승인 뒤 바뀐 업체명'
                 WHERE id=101
                """
            )
            self.fixture.connection.commit()
        finally:
            cur.close()

        with self.assertRaisesRegex(RuntimeError, "승인 원본 행"):
            run_production_manifest_dry_run(resolved["id"])

    def test_apply_guard_rejects_source_row_changed_after_dry_run(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        dry_run = run_production_manifest_dry_run(resolved["id"])
        self.assertEqual(dry_run["status"], "dry_run")
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_source_rows
                   SET raw_status='폐업', status_bucket='closed'
                 WHERE id=101
                """
            )
            self.fixture.connection.commit()
        finally:
            cur.close()

        with (
            patch(
                "apply_lodging_promotion.get_conn",
                return_value=self.fixture.shared_connection,
            ),
            patch("apply_lodging_promotion.assert_development_connection"),
            self.assertRaisesRegex(RuntimeError, "승인 원본 행"),
        ):
            with _hold_verified_manifest_source(resolved["id"]):
                self.fail("변경된 승인 원본이 apply 경계를 통과했습니다.")

    def test_approval_rejects_newer_source_batch(self):
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
        cur = self.fixture.connection.cursor()
        try:
            cur.execute(
                """
                INSERT INTO lodging_source_batches (
                    id, batch_key, source_key, filename, file_ext,
                    file_sha256, reference_date, status, total_rows,
                    parsed_rows, valid_rows, review_rows, file_data
                ) VALUES (
                    99, 'fixture:new-tourism', 'tourism_lodging',
                    'tourism_lodging_new.csv', 'csv', 'sha-new',
                    '2026-09-02', 'validated', 0, 0, 0, 0, %s
                )
                """,
                (b"new fixture",),
            )
            self.fixture.connection.commit()
        finally:
            cur.close()

        with self.assertRaisesRegex(RuntimeError, "최신 승인 원본 batch"):
            approve_production_manifest(resolved["id"], approved_by=1)

    def test_dry_run_rejects_changed_production_baseline(self):
        _base, _excluded, resolved = self._resolve_and_approve()
        changed_snapshot = list(self.production_snapshot)
        changed_snapshot[2] = "changed-production-baseline"
        self.production_snapshot_mock.return_value = tuple(changed_snapshot)
        with self.assertRaisesRegex(RuntimeError, "운영 기준선"):
            run_production_manifest_dry_run(resolved["id"])


class LodgingPromotionTest(unittest.TestCase):
    def test_scheduler_production_override_routes_comparison_write_to_pg_dev(self):
        connection = object()
        seen = []

        def fake_get_conn():
            seen.append(os.environ.get("DATABASE_URL"))
            return connection

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://production",
                    "PROD_DATABASE_URL": "postgres://production",
                    "DEV_DATABASE_URL": "postgres://development",
                    "PGUSER": "dev-user",
                    "PGPASSWORD": "dev-password",
                    "PGHOST": "dev-host",
                    "PGPORT": "5432",
                    "PGDATABASE": "dev-db",
                },
                clear=False,
            ),
            patch("lodging_promotion.get_conn", side_effect=fake_get_conn),
            patch("lodging_promotion.assert_development_connection") as gate,
        ):
            self.assertIs(_get_development_connection(), connection)
            self.assertEqual(
                seen,
                ["postgres://development"],
            )
            self.assertEqual(
                os.environ["DATABASE_URL"],
                "postgres://production",
            )
            gate.assert_called_once_with(connection)

    def test_parallel_comparison_records_permit_status_link_and_duplicates(self):
        targets = [{
            "action": "status_change",
            "production_match_state": "existing_building",
            "production_building_id": 7,
            "existing_applied_building_id": None,
            "payload": {
                "source_key": "lodging",
                "permit_number": "P-0",
                "biz_name": "숙소",
                "raw_status": "폐업",
                "status_bucket": "closed",
                "raw_hygiene_type": "숙박업(일반)",
                "service_category": "일반숙박업",
                "raw_record": {},
            },
        }]
        result = compare_parallel_results(
            targets,
            [{"permit_number": "P-0"}, {"permit_number": "P-0"}],
            [{"permit_number": "P-0", "biz_status_name": "영업/정상"}],
            [{
                "permit_number": "P-0",
                "biz_name": "숙소",
                "biz_status_name": "영업/정상",
                "hygiene_type": "숙박업(일반)",
                "applied_building_id": None,
            }],
        )
        self.assertEqual(result["declared_action_counts"]["status_change"], 1)
        self.assertEqual(result["outcome_counts"]["duplicate"], 1)
        self.assertEqual(result["history_status_diffs"][0]["permit_number"], "P-0")
        self.assertEqual(result["building_link_counts"]["matched"], 1)

    def test_surface_comparison_is_clean_only_with_complete_expected_baseline(self):
        road_address = "서울특별시 중구 세종대로 1"
        registry = [{
            "permit_number": "P-1",
            "biz_status_name": "영업/정상",
            "room_count": 12,
            "applied_building_id": 7,
            "road_norm": normalize_road_prefix(road_address),
        }]
        buildings = [{
            "id": 7,
            "lat": 37.0,
            "lng": 127.0,
            "road_address": road_address,
        }]
        snapshot = _surface_snapshot(registry, buildings)
        result = compare_parallel_results(
            [],
            [],
            [],
            registry,
            screen_baseline=snapshot,
            screen_expected_after_apply=snapshot,
            screen_expected_ranges=_surface_expected_ranges(snapshot),
            production_buildings=buildings,
        )
        comparison = result["screen_comparison"]
        self.assertEqual(comparison["status"], "expected_match")
        self.assertEqual(comparison["verification_status"], "clean")
        self.assertFalse(comparison["blocking"])
        self.assertEqual(comparison["out_of_range"], {})

    def test_surface_metric_outside_manifest_range_is_a_blocking_regression(self):
        road_address = "서울특별시 중구 세종대로 1"
        expected_registry = [{
            "permit_number": "P-1",
            "biz_status_name": "영업/정상",
            "room_count": 12,
            "applied_building_id": 7,
            "road_norm": normalize_road_prefix(road_address),
        }]
        actual_registry = [{
            **expected_registry[0],
            "room_count": 3,
        }]
        buildings = [{
            "id": 7,
            "lat": 37.0,
            "lng": 127.0,
            "road_address": road_address,
        }]
        expected = _surface_snapshot(expected_registry, buildings)
        result = compare_parallel_results(
            [],
            [],
            [],
            actual_registry,
            screen_baseline=expected,
            screen_expected_after_apply=expected,
            screen_expected_ranges=_surface_expected_ranges(expected),
            production_buildings=buildings,
        )
        comparison = result["screen_comparison"]
        self.assertEqual(comparison["status"], "regression")
        self.assertTrue(comparison["blocking"])
        self.assertIn("stats.room_count", comparison["out_of_range"])

    def test_address_normalization_regression_breaks_detail_stats_and_admin(self):
        road_address = "서울특별시 중구 세종대로 1"
        expected_registry = [{
            "permit_number": "P-1",
            "biz_status_name": "영업/정상",
            "room_count": 12,
            "road_norm": normalize_road_prefix(road_address),
            "jibun_norm": None,
        }]
        buildings = [{
            "id": 7,
            "road_address": road_address,
            "lat": 37.0,
            "lng": 127.0,
            "units": 20,
        }]
        expected = _surface_snapshot(expected_registry, buildings)
        broken_registry = [{**expected_registry[0], "road_norm": "깨진-도로명-키"}]
        result = compare_parallel_results(
            [],
            [],
            [],
            broken_registry,
            screen_baseline=expected,
            screen_expected_after_apply=expected,
            screen_expected_ranges=_surface_expected_ranges(expected),
            production_buildings=buildings,
        )
        comparison = result["screen_comparison"]
        self.assertEqual(comparison["status"], "regression")
        self.assertIn("detail.link_count", comparison["out_of_range"])
        self.assertIn("stats.active_count", comparison["out_of_range"])
        self.assertIn("admin.registry_count", comparison["out_of_range"])

    def test_detail_active_lookup_falls_back_to_jibun_when_road_has_only_closed(self):
        road_address = "서울특별시 중구 세종대로 1"
        jibun_address = "서울특별시 중구 태평로1가 31"
        registry = [
            {
                "permit_number": "P-CLOSED",
                "biz_status_name": "폐업",
                "room_count": 5,
                "road_norm": normalize_road_prefix(road_address),
                "jibun_norm": None,
            },
            {
                "permit_number": "P-ACTIVE",
                "biz_status_name": "영업/정상",
                "room_count": 9,
                "road_norm": None,
                "jibun_norm": normalize_jibun_prefix(jibun_address),
            },
        ]
        snapshot = _surface_snapshot(
            registry,
            [{
                "id": 7,
                "road_address": road_address,
                "jibun_address": jibun_address,
            }],
        )
        self.assertEqual(snapshot["detail"]["active_count"], 1)
        self.assertEqual(snapshot["detail"]["room_count"], 9)
        self.assertEqual(snapshot["stats"]["active_count"], 0)
        self.assertEqual(snapshot["admin"]["registry_count"], 1)

    def test_search_and_admin_use_visible_building_set(self):
        snapshot = _surface_snapshot(
            [],
            [
                {"id": 1, "lodging_type": "생활", "lat": 37.0, "lng": 127.0},
                {
                    "id": 2,
                    "lodging_type": "mixed_use_excluded",
                    "lat": 37.1,
                    "lng": 127.1,
                },
            ],
        )
        self.assertEqual(snapshot["search"]["building_count"], 1)
        self.assertEqual(snapshot["search"]["mapped_building_count"], 1)
        self.assertEqual(snapshot["admin"]["building_count"], 1)

    def test_missing_surface_baseline_is_pending_and_never_clean(self):
        result = compare_parallel_results([], [], [], [])
        comparison = result["screen_comparison"]
        self.assertEqual(
            comparison["status"],
            "expected_baseline_unavailable",
        )
        self.assertEqual(comparison["verification_status"], "pending")
        self.assertTrue(comparison["blocking"])
        self.assertTrue(comparison["blocking_reasons"])

    def test_missing_surface_ranges_are_pending_even_when_snapshots_match(self):
        legacy_snapshot = {
            "search": {"lodging_registry_rows": 0},
            "detail": {"lodging_registry_rows": 0, "linked_permits": 0},
            "stats": {"status_counts": {}, "active_permits": 0, "active_rooms": 0},
            "admin": {
                "lodging_registry_rows": 0,
                "linked_permits": 0,
                "unlinked_permits": 0,
            },
        }
        result = compare_parallel_results(
            [],
            [],
            [],
            [],
            screen_baseline=legacy_snapshot,
            screen_expected_after_apply=legacy_snapshot,
        )
        comparison = result["screen_comparison"]
        self.assertEqual(comparison["verification_status"], "pending")
        self.assertTrue(comparison["blocking"])
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

    def test_production_status_change_is_not_hidden_by_development_new_diff(self):
        staging = [
            {
                "source_row_id": 3,
                "batch_id": 10,
                "permit_number": "P-3",
                "biz_name": "운 스테이",
                "raw_status": "폐업",
                "status_bucket": "closed",
                "road_address": "서울특별시 중구 세종대로 3",
                "jibun_address": None,
                "raw_hygiene_type": "외국인관광도시민박업",
                "raw_record": {},
                "diff_kind": "new",
            }
        ]
        registry = [
            {
                "permit_number": "P-3",
                "biz_name": "운 스테이",
                "biz_status_name": "영업/정상",
                "room_count": None,
                "hygiene_type": "외국인관광도시민박업",
                "applied_building_id": 101,
                "road_address": "서울특별시 중구 세종대로 3",
                "jibun_address": None,
            }
        ]
        targets, summary = _build_targets(staging, registry, [])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["action"], "status_change")
        self.assertEqual(targets[0]["existing_applied_building_id"], 101)
        self.assertEqual(summary["action_counts"], {"status_change": 1})

    def test_production_non_status_update_still_respects_development_diff(self):
        staging = [
            {
                "source_row_id": 4,
                "batch_id": 10,
                "permit_number": "P-4",
                "biz_name": "새 이름",
                "raw_status": "영업/정상",
                "status_bucket": "active",
                "road_address": "서울특별시 중구 세종대로 4",
                "jibun_address": None,
                "raw_hygiene_type": "외국인관광도시민박업",
                "raw_record": {},
                "diff_kind": "new",
            }
        ]
        registry = [
            {
                "permit_number": "P-4",
                "biz_name": "기존 이름",
                "biz_status_name": "영업/정상",
                "room_count": None,
                "hygiene_type": "외국인관광도시민박업",
                "applied_building_id": 102,
                "road_address": "서울특별시 중구 세종대로 4",
                "jibun_address": None,
            }
        ]
        targets, summary = _build_targets(staging, registry, [])
        self.assertEqual(targets, [])
        self.assertEqual(summary["action_counts"], {})

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

    def test_legacy_sync_control_defaults_to_enabled_without_explicit_approval(self):
        self.assertTrue(_decode_legacy_sync_control(None)["enabled"])
        self.assertTrue(_decode_legacy_sync_control("not-json")["enabled"])
        self.assertTrue(_decode_legacy_sync_control("{}")["enabled"])
        self.assertFalse(
            _decode_legacy_sync_control(
                '{"enabled": false, "state": "disabled", "manifest_id": 7}'
            )["enabled"]
        )

    def test_cutover_policy_requires_observation_and_clean_streak(self):
        self.assertEqual(CUTOVER_MINIMUM_OBSERVATIONS, 3)
        self.assertEqual(CUTOVER_MINIMUM_CONSECUTIVE_CLEAN, 3)


if __name__ == "__main__":
    unittest.main()
