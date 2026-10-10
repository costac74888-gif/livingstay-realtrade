import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import test_hs2_phase11_db as finance_tests
import test_hs2_phase13_db as workspace_tests
from hs2_admin.fixtures import create_fixture_app
from hs2_workspace.fixtures import create_fixture_app as workspace_app
from hs2_admin.repository import AdminRepository
from hs2_supermap.fixtures import WHO
from hs2_data.repository import connect_fixture
from hs2_design.domain import ContractError


class IntegratedSQL(unittest.TestCase):
    receipt=finance_tests.FinanceSQL.receipt
    command=staticmethod(finance_tests.FinanceSQL.command)
    request=finance_tests.FinanceSQL.request

    @classmethod
    def setUpClass(cls):create_fixture_app(app_factory=workspace_app)

    def setUp(self):
        workspace_tests.WorkspaceSQL.setUp(self)
        with connect_fixture() as conn,conn.cursor() as c:c.execute("TRUNCATE hs2_dev.admin_records CASCADE")
        self.admin=AdminRepository(self.finance,resolve_admin=lambda:700,fallback_policy=lambda key:self.app.fixture_financial_policy)
        self.finance.policy_for=self.admin.policy_for

    def test_cross_module_booking_chat_policy_replay_cancel_review_preserves_contract(self):
        self.workspace.favorite(self.buyer,self.id,True)
        b=self.request(who=self.buyer)
        thread=self.workspace.open_thread(self.buyer,booking_id=b["booking_id"])["thread_id"]
        self.workspace.send(self.buyer,thread,"현재 조건 확인 요청",str(uuid4()))
        self.workspace.send(WHO,thread,"달력 확인 후 응답",str(uuid4()),True)
        self.repo.act(WHO,b["booking_id"],1,"approve",operator=True)
        preview=self.finance.quote(self.buyer,b["booking_id"])
        p=self.admin.create("policy",dict(title="검토 정책",note="조건 변경을 다시 확인",deposit_krw=60000,pg_processing_krw=3000,platform_bps=0,deposit_return_days=7,settlement_days=2))
        self.admin.change(p["id"],1,"approve","새 조건만")
        raw=dict(booking_id=b["booking_id"],request_id=str(uuid4()),acknowledged=True,expected_terms_sha256=preview["terms_sha256"])
        with self.assertRaises(ContractError):self.finance.create(self.buyer,raw)
        preview=self.finance.quote(self.buyer,b["booking_id"]);raw["expected_terms_sha256"]=preview["terms_sha256"]
        contract=self.finance.create(self.buyer,raw)
        import time
        wire,sig=self.app.fixture_payment_provider.sign(dict(event_id=str(uuid4()),contract_id=contract["contract_id"],reference="owned-"+str(uuid4()),
            kind="capture",amount_krw=contract["terms"]["payable_krw"],currency="KRW",issued_at=int(time.time())))
        with self.assertRaises(ContractError):self.finance.receive(wire,"invalid-proof")
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.finance.receive(wire,sig),range(2)))
        self.assertTrue(all(r["booking_confirmed"] and not r["actual_money_executed"] for r in results))
        self.assertEqual(len(results[0]["events"]),1)
        self.assertTrue(self.workspace.favorites(self.buyer));self.assertTrue(self.workspace.notifications(self.buyer))
        with self.assertRaises(ContractError):self.workspace.messages({**self.buyer,"user_id":999},thread)
        cancelled=self.finance.cancel(self.buyer,contract["contract_id"])
        self.assertTrue(cancelled["booking_cancelled"]);self.assertEqual(cancelled["terms"],contract["terms"])
        self.assertFalse(cancelled["actual_money_executed"])
        ledger=self.admin.overview()
        self.assertTrue(ledger["bookings"]);self.assertTrue(ledger["finances"]);self.assertTrue(ledger["audits"])
        self.assertFalse(ledger["live_operations_approved"])

    def test_real_composite_html_and_api_security_headers(self):
        app=create_fixture_app(False,populate=False,app_factory=workspace_app);client=app.test_client()
        with client.session_transaction() as s:s["fixture_admin"]=True;s["fixture_csrf"]="owned"
        for path in ("/hs2/consumer","/hs2/search/","/hs2/search/mobile/","/hs2/listings/","/hs2/calendar/","/hs2/bookings/","/hs2/finance/","/hs2/dashboard/","/hs2/workspace/","/hs2/help/","/hs2/admin/"):
            r=client.get(path);self.assertEqual(r.status_code,200,path)
            for h in ("Content-Security-Policy","Permissions-Policy","Strict-Transport-Security","X-Frame-Options","X-Permitted-Cross-Domain-Policies","Referrer-Policy","X-Content-Type-Options"):
                self.assertTrue(r.headers.get(h),path+" "+h)
            self.assertIn("no-store",r.headers["Cache-Control"])
        self.assertEqual(client.post("/hs2/admin/api/records",json={}).status_code,403)


if __name__=="__main__":unittest.main()
