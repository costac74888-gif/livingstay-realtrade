"""주간 이메일 자동 opt-in의 상태 보존 계약을 정적으로 회귀 검증한다."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
DB = (ROOT / "db.py").read_text(encoding="utf-8")


class WeeklyEmailOptInTests(unittest.TestCase):
    def test_schema_defaults_and_migration_preserve_explicit_choice(self):
        self.assertIn("weekly_email_enabled BOOLEAN DEFAULT TRUE", DB)
        self.assertIn("updated_weekly_email_at TIMESTAMP", DB)
        self.assertIn("AND updated_weekly_email_at IS NULL", DB)
        self.assertIn('SCHEMA_VERSION = "2026-08-24-04"', DB)
        self.assertIn("WHERE weekly_email_enabled = FALSE", DB)

    def test_manual_toggle_and_unsubscribe_record_explicit_change(self):
        unsubscribe_start = APP.index("def unsubscribe_weekly_email")
        unsubscribe_end = APP.index("\ndef _best_effort_weekly_email_opt_in", unsubscribe_start)
        unsubscribe = APP[unsubscribe_start:unsubscribe_end]
        toggle_start = APP.index("def auth_update_weekly_email")
        toggle_end = APP.index("\n\n@app.route", toggle_start)
        toggle = APP[toggle_start:toggle_end]
        self.assertIn("weekly_email_enabled = FALSE", unsubscribe)
        self.assertIn("updated_weekly_email_at = NOW()", unsubscribe)
        self.assertIn("weekly_email_enabled = %s", toggle)
        self.assertIn("updated_weekly_email_at = NOW()", toggle)

    def test_all_save_flows_use_savepoint_protected_auto_opt_in(self):
        helper_start = APP.index("def _best_effort_weekly_email_opt_in")
        helper_end = APP.index("\ndef current_user", helper_start)
        helper = APP[helper_start:helper_end]
        self.assertIn("SAVEPOINT", helper)
        self.assertIn("ROLLBACK TO SAVEPOINT", helper)
        self.assertIn("updated_weekly_email_at IS NULL", helper)

        for function_name in (
            "favorites_mine_add",
            "alerts_mine_add",
            "create_listing_request",
            "create_buy_request",
        ):
            start = APP.index(f"def {function_name}")
            next_def = APP.find("\ndef ", start + 1)
            section = APP[start:next_def if next_def != -1 else len(APP)]
            self.assertIn("_best_effort_weekly_email_opt_in(", section, function_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)