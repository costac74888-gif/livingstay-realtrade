import unittest,json
from unittest.mock import patch
from uuid import uuid4
import test_hs2_phase11_db as finance_tests
from hs2_data.repository import connect_fixture
from hs2_admin.repository import AdminRepository
from hs2_admin.fixtures import create_fixture_app
from hs2_admin.validation import payload
from hs2_admin.api import create_blueprint
from hs2_details.fixtures import CONSUMER
from hs2_design.domain import ContractError


class AdminSQL(unittest.TestCase):
    receipt=finance_tests.FinanceSQL.receipt
    command=staticmethod(finance_tests.FinanceSQL.command)
    request=finance_tests.FinanceSQL.request
    contract=finance_tests.FinanceSQL.contract
    event=finance_tests.FinanceSQL.event
    paid=finance_tests.FinanceSQL.paid

    @classmethod
    def setUpClass(cls):create_fixture_app()

    def setUp(self):
        finance_tests.FinanceSQL.setUp(self)
        with connect_fixture() as conn,conn.cursor() as c:c.execute("TRUNCATE hs2_dev.admin_records CASCADE")
        self.admin_id=700
        self.admin=AdminRepository(self.finance,resolve_admin=lambda:self.admin_id,fallback_policy=lambda key:self.app.fixture_financial_policy)
        self.finance.policy_for=self.admin.policy_for
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT id FROM hs2_dev.registration_applications WHERE public_id=%s",(self.id,));self.application=str(c.fetchone()[0])

    @staticmethod
    def policy():
        return dict(title="격리 개발 정책",note="실제 PG/환불 실행 아님",deposit_krw=60000,pg_processing_krw=3000,platform_bps=0,deposit_return_days=7,settlement_days=2)

    def faq(self):return self.admin.create("faq",dict(faq_id="consumer-1",question="실제 수정된 질문?",answer="관리자가 직접 검토한 별도의 답변입니다. <script>는 실행되지 않습니다."))

    def test_sql_crud_revision_archive_audit_rollback_and_approved_faq(self):
        first=self.admin.help_content();f=self.faq();self.assertEqual(self.admin.help_content()["version"],first["version"])
        approved=self.admin.change(f["id"],1,"approve","게시 안내 검토")
        self.assertEqual(approved["revision"],2);self.assertNotEqual(self.admin.help_content()["version"],first["version"])
        self.assertIn("실제 수정",self.admin.help_content()["faqs"][0]["question"])
        with self.assertRaisesRegex(ContractError,"STALE_ADMIN_REVISION"):self.admin.change(f["id"],1,"archive","낡은 차수")
        with patch.object(self.admin,"event",side_effect=ContractError("AUDIT_FAILURE")):
            with self.assertRaises(ContractError):self.admin.change(f["id"],2,"archive","원자 롤백")
        self.assertEqual(self.admin.overview()["records"][0]["status"],"approved")
        archived=self.admin.change(f["id"],2,"archive","안내 철회");self.assertEqual(archived["status"],"archived")
        with self.assertRaisesRegex(ContractError,"ARCHIVE_TERMINAL"):self.admin.change(f["id"],3,"approve","복원 금지")
        self.assertEqual(self.admin.help_content()["version"],first["version"])
        with connect_fixture() as conn,conn.cursor() as c:
            with self.assertRaises(Exception):c.execute("DELETE FROM hs2_dev.admin_record_events")

    def test_explicit_zero_platform_unknowns_and_existing_contract_immutable(self):
        old=self.contract();before=self.finance.quote(CONSUMER,old["booking_id"])["terms"]
        p=self.admin.create("policy",self.policy());self.admin.change(p["id"],1,"approve","비용·기간 명시 확인")
        self.assertEqual(self.admin.policy_for("own-booking").pg_processing_krw,3000)
        self.assertEqual(self.finance.quote(CONSUMER,old["booking_id"])["terms"],before)
        self.assertEqual(self.admin.policy_for("own-booking").terms(200000)["platform_fee_krw"],0)
        for bad in ({**self.policy(),"platform_bps":500},{**self.policy(),"pg_processing_krw":None},{**self.policy(),"deposit_krw":True},{**self.policy(),"settlement_days":0}):
            with self.assertRaises(ContractError):self.admin.create("policy",bad)

    def test_promotion_report_review_references_and_actual_ledgers_no_execution(self):
        self.paid()
        for kind in ("promotion","report","review"):
            data=dict(application_id=self.application,title="실제 관리자 기록",note="현재 관리자 확인 메모")
            if kind=="promotion":data.update(start="2027-01-01",end="2027-02-01",amount_krw=10000)
            row=self.admin.create(kind,data);self.admin.change(row["id"],1,"approve","확인 완료·실행 별도")
        overview=self.admin.overview()
        self.assertEqual(overview["counts"]["contracts"],1);self.assertEqual(len(overview["records"]),3)
        self.assertTrue(overview["registrations"]);self.assertTrue(overview["bookings"]);self.assertTrue(overview["finances"][0]["events"])
        self.assertFalse(overview["finances"][0]["actual_execution"]);self.assertFalse(overview["live_operations_approved"])
        self.assertEqual(overview["preserved_admin_uri"],"/admin")
        with self.assertRaises(ContractError):self.admin.create("report",dict(application_id=str(uuid4()),title="없는 대상",note="보류"))

    def test_original_listing_review_engine_and_missing_explicit_checks(self):
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.registration_applications SET status='submitted' WHERE id=%s",(self.application,))
            c.execute("SELECT revision FROM hs2_dev.registration_applications WHERE id=%s",(self.application,));current=c.fetchone()[0]
        with self.assertRaises(ContractError):self.admin.review_application(self.application,dict(revision=current,decision="approve",note="근거",rights=False,disclosure=True))
        r=self.admin.review_application(self.application,dict(revision=current,decision="reject",note="확인 부족",rights=False,disclosure=False))
        self.assertEqual(r["status"],"rejected")
        with self.assertRaises(ContractError):payload("faq",dict(faq_id="invented",question="없는 질문",answer="본문"))

    def test_api_signed_authority_csrf_unknown_id_fields_and_revocation(self):
        self.app.register_blueprint(create_blueprint(self.admin,csrf_for=lambda uid:"owned-admin-csrf",allow_request=lambda:True))
        client=self.app.test_client();r=client.get("/hs2/admin/api/overview")
        self.assertEqual(r.status_code,200);self.assertEqual(r.headers["Cache-Control"],"no-store, private")
        self.assertEqual(client.get("/hs2/admin/api/overview?admin_id=700").status_code,400)
        data=dict(kind="faq",payload=dict(faq_id="consumer-2",question="날짜 확인?",answer="현재 조건 확인 안내"))
        self.assertEqual(client.post("/hs2/admin/api/records",json=data).status_code,403)
        good=client.post("/hs2/admin/api/records",json=data,headers={"X-HS2-CSRF":"owned-admin-csrf"})
        self.assertEqual(good.status_code,200)
        self.admin_id=None
        self.assertEqual(client.get("/hs2/admin/api/overview").status_code,403)
        self.assertEqual(client.post("/hs2/admin/api/records",json=data,headers={"X-HS2-CSRF":"owned-admin-csrf"}).status_code,403)


if __name__=="__main__":unittest.main()
