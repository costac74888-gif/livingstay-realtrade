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
        self.assertRegex(DB, r'SCHEMA_VERSION = "\d{4}-\d{2}-\d{2}-\d{2}"')
        for table in ("agents", "operators", "loan_consultants"):
            self.assertIn(
                f"weekly_email_enabled BOOLEAN NOT NULL DEFAULT TRUE", DB
            )
            self.assertIn(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                "weekly_email_enabled BOOLEAN NOT NULL DEFAULT TRUE",
                DB,
            )
            self.assertIn(
                f"UPDATE {table} SET weekly_email_enabled = TRUE ", DB
            )
            self.assertIn("WHERE weekly_email_updated_at IS NULL", DB)
            self.assertIn(
                f"UPDATE {table} SET weekly_email_enabled = FALSE ",
                DB,
            )
            self.assertIn(
                "WHERE weekly_email_enabled IS NULL "
                "AND weekly_email_updated_at IS NOT NULL",
                DB,
            )
            self.assertIn(
                f"ALTER TABLE {table} ALTER COLUMN weekly_email_enabled SET DEFAULT TRUE",
                DB,
            )
            self.assertIn(
                f"ALTER TABLE {table} ALTER COLUMN weekly_email_enabled SET NOT NULL",
                DB,
            )
        self.assertIn(
            "SET updated_weekly_email_at = NOW()", DB
        )
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

    def test_partner_dashboard_describes_default_enabled_opt_out(self):
        for dashboard in (
            "agent_dashboard.html",
            "operator_dashboard.html",
            "loan_consultant_dashboard.html",
        ):
            source = (ROOT / "static" / dashboard).read_text(encoding="utf-8")
            self.assertIn("승인된 파트너는 주간 정보를 기본으로 받습니다.", source)
            self.assertIn("아래 토글로 언제든지 끌 수 있으며", source)
            self.assertNotIn("동의 체크를 직접 켜야", source)

    def test_unsubscribe_confirmation_routes_each_account_to_its_settings(self):
        source = (ROOT / "static" / "unsubscribe_done.html").read_text(encoding="utf-8")
        self.assertIn('agent: "/agent/dashboard"', source)
        self.assertIn('operator: "/operator/dashboard"', source)
        self.assertIn('loan_consultant: "/loan-consultant/dashboard"', source)
        self.assertIn("파트너 대시보드에서 설정 변경", source)

    def test_guide_describes_default_delivery_and_opt_out(self):
        source = (ROOT / "static" / "guide.html").read_text(encoding="utf-8")
        self.assertIn("가입 후 다음 발송일부터 받아보실 수 있어요", source)
        self.assertIn("원하지 않으면 마이페이지에서 언제든 수신을 끌 수 있습니다.", source)
        self.assertNotIn("주간이메일 신청하면!", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
