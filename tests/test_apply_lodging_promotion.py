import json
import os
import unittest
from unittest.mock import patch

import psycopg2
import psycopg2.extras

import apply_lodging_promotion
from apply_lodging_promotion import apply_manifest, build_registry_record


class _ApplyTestConnection:
    """close() 이후에도 fixture 세션을 유지하는 연결 래퍼."""

    def __init__(self, connection, *, fail_audit=False):
        self._connection = connection
        self.fail_audit = fail_audit

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def cursor(self, *args, **kwargs):
        cursor = self._connection.cursor(*args, **kwargs)
        return _AuditFailureCursor(cursor, self) if self.fail_audit else cursor

    def close(self):
        # apply_manifest가 소유 연결을 닫는 계약을 실행하되 fixture 세션은 유지한다.
        return None


class _AuditFailureCursor:
    """감사 표식 INSERT가 실제로 실행된 직후 실패를 주입한다."""

    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def execute(self, query, params=None):
        result = self._cursor.execute(query, params)
        normalized = " ".join(str(query).split()).upper()
        audit_key = params[0] if params else None
        if (
            normalized.startswith("INSERT INTO APP_META")
            and isinstance(audit_key, str)
            and audit_key.startswith("lodging_promotion_applied:")
        ):
            raise RuntimeError("fixture audit marker failure")
        return result


class ApplyLodgingPromotionDatabaseFixture:
    """실제 운영 DB 대신 개발 DB의 별도 세션·임시 테이블을 운영 원장으로 쓴다."""

    BASELINE = "fixture-production-baseline"
    PRODUCTION_FINGERPRINT = ("fixture-production-db", "fixture-production-host", 5432)

    def __init__(self):
        database_url = os.environ.get("LODGING_PROMOTION_TEST_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        production_url = os.environ.get("PROD_DATABASE_URL")
        if not database_url or not production_url:
            raise unittest.SkipTest(
                "개발·운영 DB URL이 모두 있는 환경에서만 apply DB fixture를 실행합니다."
            )

        self.staging_connection = psycopg2.connect(
            database_url,
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        try:
            if self._fingerprint(self.staging_connection) == self._production_fingerprint(
                production_url
            ):
                raise RuntimeError(
                    "apply 테스트 DB가 운영 DB와 같아 fixture를 시작하지 않았습니다."
                )
            self.staging_connection.rollback()
            self.staging_connection.autocommit = True
            self._create_staging_tables()
            self.staging_connection.autocommit = False
            self.production_connection = psycopg2.connect(
                database_url,
                connect_timeout=10,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            self.production_connection.rollback()
            self.production_connection.autocommit = True
            self._create_production_tables()
            self.production_connection.autocommit = False
        except Exception:
            self.staging_connection.close()
            raise

        self.staging = _ApplyTestConnection(self.staging_connection)
        self.production = _ApplyTestConnection(self.production_connection)

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

    @classmethod
    def _production_fingerprint(cls, production_url):
        production = psycopg2.connect(
            production_url,
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        try:
            production.set_session(readonly=True)
            return cls._fingerprint(production)
        finally:
            production.close()

    def _create_staging_tables(self):
        cur = self.staging_connection.cursor()
        try:
            cur.execute(
                """
                CREATE TEMP TABLE lodging_promotion_manifests (
                    id BIGINT PRIMARY KEY,
                    manifest_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result JSONB NOT NULL DEFAULT '{}'::jsonb,
                    error TEXT,
                    run_id TEXT NOT NULL,
                    heartbeat_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                INSERT INTO lodging_promotion_manifests (
                    id, manifest_key, status, result, run_id
                ) VALUES (1, 'fixture:apply', 'dry_run', '{}', 'run-a')
                """
            )
        finally:
            cur.close()

    def _create_production_tables(self):
        cur = self.production_connection.cursor()
        try:
            cur.execute(
                """
                CREATE TEMP TABLE app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TEMP TABLE lodging_registry (
                    id SERIAL PRIMARY KEY,
                    biz_name TEXT NOT NULL,
                    permit_number TEXT NOT NULL UNIQUE,
                    road_address TEXT,
                    jibun_address TEXT,
                    permit_date TEXT,
                    biz_status_name TEXT,
                    biz_status_detail TEXT,
                    room_count INTEGER,
                    camping_site_count INTEGER,
                    hygiene_type TEXT,
                    phone TEXT,
                    road_norm TEXT,
                    jibun_norm TEXT,
                    biz_name_norm TEXT,
                    source_updated_at TEXT,
                    bld_use_nm TEXT,
                    facility_area NUMERIC,
                    region_name TEXT,
                    applied_building_id INTEGER,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
        finally:
            cur.close()

    def close(self):
        self.staging_connection.close()
        self.production_connection.close()


class ApplyLodgingPromotionTest(unittest.TestCase):
    def test_existing_room_and_link_are_preserved_when_csv_is_blank(self):
        payload = {
            "source_key": "rural_homestay",
            "permit_number": "RURAL:1:A",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "road_address": "서울시 중구 세종대로 1",
            "raw_record": {"객실수": ""},
            "production_match_state": "new_building_candidate",
            "production_building_id": None,
        }
        result = build_registry_record(
            payload,
            {
                "room_count": 27,
                "camping_site_count": None,
                "applied_building_id": 101,
            },
        )
        self.assertEqual(result["room_count"], 27)
        self.assertEqual(result["applied_building_id"], 101)

    def test_new_active_unique_match_is_linked(self):
        payload = {
            "source_key": "tourism_lodging",
            "permit_number": "TOUR:1:A",
            "biz_name": "호텔",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"한실수": "2", "양실수": "8"},
            "production_match_state": "existing_building",
            "production_building_id": 55,
        }
        result = build_registry_record(payload)
        self.assertEqual(result["room_count"], 10)
        self.assertEqual(result["applied_building_id"], 55)

    def test_inactive_or_ambiguous_new_row_is_not_linked(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:1",
            "biz_name": "폐업 숙소",
            "status_bucket": "closed",
            "raw_status": "폐업",
            "raw_record": {},
            "production_match_state": "existing_building",
            "production_building_id": 77,
        }
        self.assertIsNone(build_registry_record(payload)["applied_building_id"])
        payload["status_bucket"] = "active"
        payload["production_match_state"] = "ambiguous_existing_building"
        self.assertIsNone(build_registry_record(payload)["applied_building_id"])

    def test_camping_sites_do_not_become_room_count(self):
        payload = {
            "source_key": "general_camping",
            "permit_number": "CAMP:1",
            "biz_name": "캠핑장",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"객실수": "20", "야영사이트수": "45"},
        }
        result = build_registry_record(payload)
        self.assertIsNone(result["room_count"])
        self.assertEqual(result["camping_site_count"], 45)

    def test_phone_is_stored_as_digits_only(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:2",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"전화번호": "02-1234-5678"},
        }
        self.assertEqual(build_registry_record(payload)["phone"], "0212345678")

    def test_facility_area_is_preserved_for_new_record(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:3",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"시설규모": "1,234.50"},
        }
        self.assertEqual(
            str(build_registry_record(payload)["facility_area"]),
            "1234.50",
        )

    @patch("apply_lodging_promotion._load_manifest")
    def test_apply_rejects_manifest_before_completed_dry_run(self, load_manifest):
        load_manifest.return_value = (
            {"status": "approved", "run_id": "run-a"},
            [],
        )
        with self.assertRaisesRegex(ValueError, "dry-run"):
            apply_manifest(1, confirm_run_id="run-a")

    @patch("apply_lodging_promotion._load_manifest")
    def test_apply_rejects_wrong_confirmation_run_id(self, load_manifest):
        load_manifest.return_value = (
            {"status": "dry_run", "run_id": "run-a"},
            [],
        )
        with self.assertRaisesRegex(ValueError, "run_id"):
            apply_manifest(1, confirm_run_id="run-b")


class ApplyLodgingPromotionDatabaseFlowTest(unittest.TestCase):
    """운영 반영 트랜잭션을 테스트 전용 DB fixture에서 실행하는 회귀 테스트."""

    def setUp(self):
        self.fixture = ApplyLodgingPromotionDatabaseFixture()
        self.manifest = {
            "id": 1,
            "manifest_key": "fixture:apply",
            "status": "dry_run",
            "production_baseline_fingerprint": self.fixture.BASELINE,
            "target_payload_sha256": "fixture-payload-hash",
            "row_count": 2,
            "result": {"action_counts": {"insert": 2}},
            "run_id": "run-a",
        }
        self.targets = [
            {
                "source_row_id": 1,
                "action": "insert",
                "production_match_state": "new_building_candidate",
                "production_building_id": None,
                "existing_applied_building_id": None,
                "payload": {
                    "source_key": "lodging",
                    "permit_number": "FIXTURE:1",
                    "biz_name": "첫 번째 숙소",
                    "status_bucket": "active",
                    "raw_status": "영업/정상",
                    "raw_hygiene_type": "숙박업(일반)",
                    "road_address": "서울특별시 중구 세종대로 1",
                    "jibun_address": None,
                    "raw_record": {"객실수": "10"},
                    "production_match_state": "new_building_candidate",
                },
            },
            {
                "source_row_id": 2,
                "action": "insert",
                "production_match_state": "new_building_candidate",
                "production_building_id": None,
                "existing_applied_building_id": None,
                "payload": {
                    "source_key": "lodging",
                    "permit_number": "FIXTURE:2",
                    "biz_name": "두 번째 숙소",
                    "status_bucket": "active",
                    "raw_status": "영업/정상",
                    "raw_hygiene_type": "숙박업(일반)",
                    "road_address": "서울특별시 중구 세종대로 2",
                    "jibun_address": None,
                    "raw_record": {"객실수": "20"},
                    "production_match_state": "new_building_candidate",
                },
            },
        ]
        self.patches = patch.multiple(
            "apply_lodging_promotion",
            get_conn=unittest.mock.DEFAULT,
            _load_manifest=unittest.mock.DEFAULT,
            _fetch_production_snapshot=unittest.mock.DEFAULT,
            _database_fingerprint=unittest.mock.DEFAULT,
            assert_development_connection=unittest.mock.DEFAULT,
        )
        mocks = self.patches.start()
        mocks["get_conn"].return_value = self.fixture.staging
        mocks["_load_manifest"].return_value = (self.manifest, self.targets)
        mocks["_fetch_production_snapshot"].return_value = (
            [],
            [],
            self.fixture.BASELINE,
            self.fixture.PRODUCTION_FINGERPRINT,
        )
        mocks["_database_fingerprint"].return_value = self.fixture.PRODUCTION_FINGERPRINT
        mocks["assert_development_connection"].return_value = None
        self.load_manifest_mock = mocks["_load_manifest"]
        self.connect_patch = patch(
            "apply_lodging_promotion.psycopg2.connect",
            return_value=self.fixture.production,
        )
        self.connect_patch.start()

    def tearDown(self):
        self.connect_patch.stop()
        self.patches.stop()
        self.fixture.close()

    def _production_rows(self):
        cur = self.fixture.production_connection.cursor()
        try:
            cur.execute(
                """
                SELECT permit_number, biz_name, room_count
                  FROM lodging_registry
                 ORDER BY permit_number
                """
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            self.fixture.production_connection.rollback()
            cur.close()

    def _meta(self):
        cur = self.fixture.production_connection.cursor()
        try:
            cur.execute("SELECT key, value FROM app_meta ORDER BY key")
            return {row["key"]: row["value"] for row in cur.fetchall()}
        finally:
            self.fixture.production_connection.rollback()
            cur.close()

    def _staging_manifest(self):
        cur = self.fixture.staging_connection.cursor()
        try:
            cur.execute(
                """
                SELECT status, result, error
                  FROM lodging_promotion_manifests
                 WHERE id=1
                """
            )
            return dict(cur.fetchone())
        finally:
            self.fixture.staging_connection.rollback()
            cur.close()

    def test_success_writes_registry_audit_and_stats_in_one_fixture_transaction(self):
        result = apply_manifest(1, confirm_run_id="run-a")

        self.assertTrue(result["applied"])
        self.assertFalse(result["already_applied"])
        self.assertEqual(self._production_rows(), [
            {"permit_number": "FIXTURE:1", "biz_name": "첫 번째 숙소", "room_count": 10},
            {"permit_number": "FIXTURE:2", "biz_name": "두 번째 숙소", "room_count": 20},
        ])
        meta = self._meta()
        audit = json.loads(meta["lodging_promotion_applied:fixture:apply"])
        self.assertEqual(audit["run_id"], "run-a")
        self.assertEqual(audit["production_writes"], 2)
        stats_signal = json.loads(meta["master_stats_invalidation"])
        self.assertEqual(stats_signal["source"], "lodging_promotion")
        self.assertEqual(self._staging_manifest()["status"], "applied")

    def test_upsert_failure_after_first_row_rolls_back_everything(self):
        real_execute_batch = psycopg2.extras.execute_batch

        def fail_after_first_row(cur, sql, records, page_size=100):
            real_execute_batch(cur, sql, records[:1], page_size=page_size)
            raise RuntimeError("fixture lodging_registry UPSERT failure")

        with patch(
            "apply_lodging_promotion.psycopg2.extras.execute_batch",
            side_effect=fail_after_first_row,
        ):
            with self.assertRaisesRegex(RuntimeError, "UPSERT"):
                apply_manifest(1, confirm_run_id="run-a")

        self.assertEqual(self._production_rows(), [])
        self.assertEqual(self._meta(), {})
        staging = self._staging_manifest()
        self.assertEqual(staging["status"], "dry_run")
        self.assertEqual(staging["result"], {})

    def test_audit_marker_failure_rolls_back_registry_audit_and_stats(self):
        self.fixture.production.fail_audit = True

        with self.assertRaisesRegex(RuntimeError, "audit marker"):
            apply_manifest(1, confirm_run_id="run-a")

        self.assertEqual(self._production_rows(), [])
        self.assertEqual(self._meta(), {})
        self.assertEqual(self._staging_manifest()["status"], "dry_run")

    def test_development_update_is_automatically_retried_after_production_commit(self):
        # 운영 트랜잭션은 커밋됐지만 두 번째(개발 manifest) 갱신만 실패한
        # 상태를 재현한다.
        real_mark_development_applied = (
            apply_lodging_promotion._mark_development_applied
        )
        mark_attempts = 0

        def fail_first_development_update(manifest, result):
            nonlocal mark_attempts
            mark_attempts += 1
            if mark_attempts == 1:
                raise RuntimeError("fixture development manifest update failure")
            return real_mark_development_applied(manifest, result)

        real_execute_batch = psycopg2.extras.execute_batch
        with patch(
            "apply_lodging_promotion._mark_development_applied",
            side_effect=fail_first_development_update,
        ), patch(
            "apply_lodging_promotion.psycopg2.extras.execute_batch",
            wraps=real_execute_batch,
        ) as execute_batch, patch("apply_lodging_promotion.time.sleep") as sleep:
            result = apply_manifest(1, confirm_run_id="run-a")

        self.assertFalse(result["already_applied"])
        self.assertEqual(mark_attempts, 2)
        self.assertEqual(execute_batch.call_count, 1)
        sleep.assert_called_once_with(0.2)
        self.assertEqual(len(self._production_rows()), 2)
        self.assertIn("lodging_promotion_applied:fixture:apply", self._meta())
        self.assertEqual(self._staging_manifest()["status"], "applied")

    def test_same_run_id_retry_is_idempotent_and_different_run_id_is_rejected(self):
        first = apply_manifest(1, confirm_run_id="run-a")
        first_meta = self._meta()
        first_rows = self._production_rows()

        # 실제 재시도에서는 개발 manifest가 이미 applied로 조회된다.
        self.manifest["status"] = "applied"
        retry = apply_manifest(1, confirm_run_id="run-a")
        self.assertTrue(retry["already_applied"])
        self.assertEqual(retry["run_id"], first["run_id"])
        self.assertEqual(self._production_rows(), first_rows)
        self.assertEqual(self._meta(), first_meta)
        self.assertEqual(self.load_manifest_mock.call_count, 2)

        conflicting_manifest = {**self.manifest, "run_id": "run-b"}
        conflicting_manifest["status"] = "failed"
        self.load_manifest_mock.return_value = (conflicting_manifest, self.targets)
        with self.assertRaisesRegex(RuntimeError, "다른 run_id"):
            apply_manifest(1, confirm_run_id="run-b")

        self.assertEqual(self._production_rows(), first_rows)
        self.assertEqual(self._meta(), first_meta)


if __name__ == "__main__":
    unittest.main()