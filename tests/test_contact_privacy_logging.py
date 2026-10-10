import ast
import io
import logging
import tempfile
import unittest
from datetime import datetime
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import quote

from privacy_logging import redact_contact_data, diagnostic_sample, private_contact_report
import privacy_logging
import report_authority_match as report

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "synthetic.recipient+fixture@example.test"
PHONE = "02-1234-5678"


def source_function(filename, name, namespace):
    tree = ast.parse((ROOT / filename).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), namespace)
    return namespace[name]


class ContactPrivacyTests(unittest.TestCase):
    def test_plain_encoded_exception_contacts_are_masked_without_losing_error_details(self):
        message = f"503 temporary {EMAIL} {PHONE} 01012345678 +82-10-1234-5678"
        for value in (message, quote(message, safe=""), quote(quote(message, safe=""), safe=""), Exception(message)):
            safe = redact_contact_data(value)
            for contact in (EMAIL, PHONE, "01012345678", "+82-10-1234-5678"):
                self.assertNotIn(contact, safe)
            self.assertIn("503 temporary", safe)
        self.assertEqual(redact_contact_data("2026-10-11 count=12345678 price=29000"), "2026-10-11 count=12345678 price=29000")
        for phone in ("(02) 1234-5678", "+82 (0)10 1234 5678", "+1 (202) 555-1234", "1588-1234"):
            self.assertNotIn(phone.strip("()"), redact_contact_data(phone))

    def test_sample_contact_fields_even_unknown_format_are_hidden_without_mutating_input(self):
        data = {"TELNO": "extension 42", "email": EMAIL, "status": "영업", "nested": [{"cnpsTelno": PHONE, "count": 3}]}
        safe = diagnostic_sample(data)
        self.assertEqual(safe["status"], "영업")
        self.assertEqual(safe["nested"][0]["count"], 3)
        self.assertNotIn(PHONE, str(safe));self.assertNotIn(EMAIL, str(safe))
        self.assertEqual(data["email"], EMAIL)

    def test_real_application_email_functions_preserve_recipient_body_return_and_hide_failures(self):
        stream = io.StringIO();logger = logging.Logger("owned");logger.addHandler(logging.StreamHandler(stream))
        send = Mock(return_value=(False, f"503 temporary {EMAIL} {PHONE}"))
        ns = {"app": SimpleNamespace(logger=logger), "send_email": send, "datetime": datetime, "_APPLICANT_TYPE_KR": {"agent": "중개사"}}
        received = source_function("app.py", "_send_application_received_email", ns)
        approval = source_function("app.py", "_send_approval_email", ns)
        received("agent", "가상업체", EMAIL)
        result = approval("agent", EMAIL, EMAIL, "synthetic-password", "https://example.test/login")
        self.assertEqual(result, send.return_value)
        for call in send.call_args_list:self.assertEqual(call.args[0], EMAIL)
        self.assertIn(EMAIL, send.call_args_list[-1].args[2])
        self.assertIn("synthetic-password", send.call_args_list[-1].args[2])
        send.side_effect = RuntimeError(f"provider error {EMAIL} {PHONE}")
        received("agent", "가상업체", EMAIL)
        self.assertEqual(approval("agent", EMAIL, EMAIL, None, "https://example.test/login"), (False, str(send.side_effect)))
        text = stream.getvalue()
        self.assertNotIn(EMAIL, text);self.assertNotIn(PHONE, text)
        self.assertNotIn("Traceback", text);self.assertIn("503 temporary", text);self.assertIn("RuntimeError", text)

    def test_default_report_preserves_matches_counts_and_department_without_contact(self):
        contacts = [{"region_name_raw": "서울특별시 강남구", "dept": "가상 담당부서", "phone": PHONE}]
        master = [("서울특별시 강남구", 3), ("미확인 지역", 1)]
        safe, full = io.StringIO(), io.StringIO()
        with redirect_stdout(safe):report.render_report(contacts, master)
        report.render_report(contacts, master, contact_output=full)
        self.assertIn(PHONE, full.getvalue())
        self.assertNotIn(PHONE, safe.getvalue())
        self.assertIn("가상 담당부서", safe.getvalue())
        self.assertEqual(safe.getvalue(), full.getvalue().replace(PHONE, "[연락처 숨김]"))

    def test_explicit_report_export_is_private_no_overwrite_no_escape_and_console_stays_masked(self):
        contacts = [{"region_name_raw": "서울특별시 강남구", "dept": "가상 담당부서", "phone": PHONE}]
        conn = Mock();cur = conn.cursor.return_value
        cur.fetchall.side_effect = [contacts, [{"sgg_text": "서울특별시 강남구", "c": 3}]]
        with tempfile.TemporaryDirectory() as folder, patch.object(privacy_logging, "PRIVATE_REPORT_DIR", Path(folder)/"private"):
            output = io.StringIO()
            with patch.object(report, "get_conn", return_value=conn), redirect_stdout(output):
                report.main("contacts.txt")
            p = Path(folder)/"private"/"contacts.txt"
            self.assertIn(PHONE, p.read_text());self.assertNotIn(PHONE, output.getvalue())
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(p.parent.stat().st_mode & 0o777, 0o700)
            conn.commit.assert_not_called()
            with self.assertRaises(FileExistsError):
                with private_contact_report("contacts.txt"):pass
            for bad in ("../escape.txt", "/tmp/escape.txt"):
                with self.assertRaises(ValueError):
                    with private_contact_report(bad):pass
            (p.parent/"link.txt").symlink_to(p)
            with self.assertRaises(OSError):
                with private_contact_report("link.txt"):pass
            conn.close.assert_called_once()

    def test_real_digest_logging_calls_never_include_synthetic_recipient_or_error_contact(self):
        for filename in ("weekly_digest.py", "deal_alert_digest.py"):
            tree = ast.parse((ROOT/filename).read_text())
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "log" and n.args and isinstance(n.args[0], ast.Constant)
                and ("✓" in str(n.args[0].value) or "✗" in str(n.args[0].value) or "이미 발송됨/다른 작업자" in str(n.args[0].value))]
            self.assertTrue(calls)
            for call in calls:
                stream=io.StringIO();logger=logging.Logger("owned");logger.addHandler(logging.StreamHandler(stream))
                ns=dict(log=logger,uid=42,recipient_type="agent",email=EMAIL,user={"id":42,"email":EMAIL},
                    msg=f"503 {EMAIL} {PHONE}",message=f"503 {EMAIL} {PHONE}",claimed_deals=[{}],redact_contact_data=redact_contact_data)
                eval(compile(ast.Expression(call),filename,"eval"),ns)
                self.assertNotIn(EMAIL,stream.getvalue());self.assertNotIn(PHONE,stream.getvalue())


if __name__ == "__main__":unittest.main()
