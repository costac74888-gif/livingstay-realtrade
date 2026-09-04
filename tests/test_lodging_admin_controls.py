import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import lodging_import_staging
import sync_lodgings
import apply_lodging_import
import sync_rural_hanok


class LodgingAdminControlTests(unittest.TestCase):
    def test_camping_only_sync_bypasses_disabled_legacy_lodging_gate(self):
        @contextmanager
        def disabled_gate():
            raise AssertionError("camping-only sync must not enter legacy gate")
            yield False

        with (
            patch.object(sync_lodgings, "legacy_lodging_writer_gate", disabled_gate),
            patch.object(sync_lodgings, "_main_with_legacy_gate") as run,
            patch.object(sys, "argv", ["sync_lodgings.py", "--camping"]),
        ):
            sync_lodgings.main()

        run.assert_called_once_with()

    def test_regular_sync_still_honors_disabled_legacy_lodging_gate(self):
        @contextmanager
        def disabled_gate():
            yield False

        with (
            patch.object(sync_lodgings, "legacy_lodging_writer_gate", disabled_gate),
            patch.object(sync_lodgings, "_main_with_legacy_gate") as run,
            patch.object(sys, "argv", ["sync_lodgings.py"]),
        ):
            sync_lodgings.main()

        run.assert_not_called()

    def test_upload_extensions_are_source_specific(self):
        self.assertEqual(lodging_import_staging.allowed_extensions("rural"), {"csv"})
        self.assertEqual(
            lodging_import_staging.allowed_extensions("airbnb"), {"csv", "xlsx"}
        )
        self.assertEqual(
            lodging_import_staging.allowed_extensions("hanok"), {"csv", "xlsx"}
        )

    def test_lodging_lock_conflict_returns_nonzero(self):
        @contextmanager
        def denied_lock():
            yield False

        with (
            patch.object(sync_lodgings, "_lodging_sync_lock", denied_lock),
            patch.object(sys, "argv", ["sync_lodgings.py", "--camping"]),
        ):
            with self.assertRaises(SystemExit) as raised:
                sync_lodgings.main()
        self.assertEqual(raised.exception.code, 75)

    def test_admin_has_source_stats_and_approval_routes(self):
        app = Path("app.py").read_text(encoding="utf-8")
        html = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn('@app.route("/api/admin/lodging-source-overview")', app)
        self.assertIn('@app.route("/api/admin/lodging-import/preview"', app)
        self.assertIn('id="lodgingSourceCards"', html)
        self.assertIn('id="lodgingImportPreviewBtn"', html)
        for stage in ("camping", "rural", "hanok", "pension"):
            self.assertIn(f'("{stage}",', app)
        self.assertIn("AND run_id=%s", Path("apply_lodging_import.py").read_text())
        self.assertIn("lodging-import-retry", html)

    def test_admin_has_eight_source_staging_approval_flow_without_apply(self):
        app = Path("app.py").read_text(encoding="utf-8")
        html = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn(
            '@app.route("/api/admin/lodging-staging/overview")',
            app,
        )
        self.assertIn(
            '"/api/admin/lodging-staging/<int:batch_id>/approval"',
            app,
        )
        self.assertIn(
            '"/api/admin/lodging-staging/approval/<int:approval_id>/approve"',
            app,
        )
        self.assertIn(
            '"/api/admin/lodging-staging/approval/<int:approval_id>/dry-run"',
            app,
        )
        self.assertNotIn(
            '"/api/admin/lodging-staging/approval/<int:approval_id>/apply"',
            app,
        )
        self.assertIn('id="lodgingStagingSummary"', html)
        self.assertIn('id="lodgingStagingCards"', html)
        self.assertIn("운영 DB는 아직 변경되지 않습니다.", html)
        self.assertIn("loadLodgingStagingOverview();", html)
        self.assertIn(
            '"/api/admin/lodging-staging/promotion/<int:manifest_id>/approve"',
            app,
        )
        self.assertIn(
            '"/api/admin/lodging-staging/promotion/<int:manifest_id>/dry-run"',
            app,
        )
        self.assertNotIn(
            '"/api/admin/lodging-staging/promotion/<int:manifest_id>/apply"',
            app,
        )
        self.assertIn(
            '"/review/<int:source_row_id>"',
            app,
        )
        self.assertIn('id="lodgingPromotionManifest"', html)
        self.assertIn("원본 전체값 보기", html)
        self.assertIn("include_unclassified_history", html)
        self.assertIn("새 manifest 버전에 기록", html)
        self.assertIn("parallel_comparison", app)
        self.assertIn("8단계 병행 비교", html)

    def test_rural_upload_uses_same_source_lock_as_api_collector(self):
        lock_id = sync_rural_hanok._source_lock_ids(["rural"])[0]
        calls = []

        class Cursor:
            def execute(self, sql, params):
                calls.append((sql, params))

            def fetchone(self):
                return {"acquired": True, "released": True}

            def close(self):
                pass

        class Connection:
            def cursor(self):
                return Cursor()

            def close(self):
                pass

        with patch.object(apply_lodging_import, "get_conn", return_value=Connection()):
            with apply_lodging_import._import_lock("rural") as acquired:
                self.assertTrue(acquired)
        self.assertEqual(calls[0][1], (lock_id,))
        self.assertEqual(calls[-1][1], (lock_id,))

    def test_rural_upload_is_denied_when_api_source_lock_is_held(self):
        class Cursor:
            def execute(self, _sql, _params):
                pass

            def fetchone(self):
                return {"acquired": False}

            def close(self):
                pass

        class Connection:
            def cursor(self):
                return Cursor()

            def close(self):
                pass

        with patch.object(apply_lodging_import, "get_conn", return_value=Connection()):
            with apply_lodging_import._import_lock("rural") as acquired:
                self.assertFalse(acquired)


if __name__ == "__main__":
    unittest.main()