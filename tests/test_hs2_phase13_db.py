import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import test_hs2_phase11_db as finance_tests
from hs2_workspace.fixtures import create_fixture_app
from hs2_workspace.repository import WorkspaceRepository
from hs2_data.repository import connect_fixture
from hs2_details.fixtures import CONSUMER
from hs2_supermap.fixtures import WHO
from hs2_design.domain import ContractError


class Sandbox:
    owned_sandbox=True
    def __init__(self,success=True):self.success=success;self.sent=[]
    def send(self,data):self.sent.append(data);return self.success


class WorkspaceSQL(unittest.TestCase):
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
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.stay_favorites,hs2_dev.stay_notifications,
                hs2_dev.stay_notification_preferences,hs2_dev.stay_threads CASCADE""")
        self.workspace=WorkspaceRepository(self.finance)
        self.repo.event_callback=self.workspace.booking_event
        self.buyer={**CONSUMER,"user_id":102}

    def thread(self):
        return self.workspace.open_thread(self.buyer,public_id=self.id)["thread_id"]

    def test_favorite_duplicate_remove_foreign_and_unpublished_history(self):
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.workspace.favorite(self.buyer,self.id,True),range(2)))
        self.assertEqual(len(self.workspace.favorites(self.buyer)),1)
        self.assertEqual(self.workspace.favorites(CONSUMER),[])
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.registration_applications SET approved_until=clock_timestamp()-interval '1 second' WHERE public_id=%s",(self.id,))
        saved=self.workspace.favorites(self.buyer)[0]
        self.assertFalse(saved["available"]);self.assertIsNone(saved["item"]);self.assertIsNone(saved["uri"])
        self.workspace.favorite(self.buyer,self.id,False);self.assertEqual(self.workspace.favorites(self.buyer),[])
        with self.assertRaises(ContractError):self.workspace.favorite(self.buyer,self.id,True)

    def test_participant_authority_idempotent_thread_message_and_atomic_notice(self):
        t=self.thread();self.assertEqual(self.thread(),t);key=str(uuid4())
        first=self.workspace.send(self.buyer,t,"실제 저장 메시지 <script>alert(1)</script>",key)
        self.assertTrue(self.workspace.send(self.buyer,t,"실제 저장 메시지 <script>alert(1)</script>",key)["replayed"])
        self.assertEqual(len(self.workspace.messages(WHO,t,True)),1)
        self.assertEqual(len(self.workspace.notifications(CONSUMER)),1)
        with self.assertRaisesRegex(ContractError,"CHAT_IDEMPOTENCY_CONFLICT"):self.workspace.send(self.buyer,t,"다른 내용",key)
        with self.assertRaisesRegex(ContractError,"CHAT_NOT_FOUND"):self.workspace.messages(CONSUMER,t)
        with patch.object(self.workspace.registrations,"context_is_active",return_value=True):
            with self.assertRaisesRegex(ContractError,"CHAT_NOT_FOUND"):self.workspace.messages({**WHO,"context_id":"operator:other"},t,True)
        with patch.object(self.workspace,"notify",side_effect=ContractError("NOTICE_FAILURE")):
            with self.assertRaises(ContractError):self.workspace.send(self.buyer,t,"롤백되어야 하는 내용",str(uuid4()))
        self.assertEqual(len(self.workspace.messages(self.buyer,t)),1)
        self.assertEqual(self.workspace.messages(self.buyer,t)[0]["message_id"],first["message_id"])

    def test_explicit_read_cursor_does_not_ack_unseen_or_foreign_message(self):
        t=self.thread();first=self.workspace.send(self.buyer,t,"첫 메시지",str(uuid4()))
        second=self.workspace.send(self.buyer,t,"GET 이후 도착",str(uuid4()))
        self.workspace.read_thread(WHO,t,first["message_id"],True)
        self.assertEqual(self.workspace.threads(WHO,True)[0]["unread"],1)
        self.workspace.read_thread(WHO,t,second["message_id"],True)
        self.workspace.read_thread(WHO,t,first["message_id"],True)
        self.assertEqual(self.workspace.threads(WHO,True)[0]["unread"],0)
        with self.assertRaises(ContractError):self.workspace.read_thread(self.buyer,t,str(uuid4()))
        self.workspace.send(WHO,t,"운영자 답변",str(uuid4()),True)
        self.assertEqual(self.workspace.threads(self.buyer)[0]["unread"],1)

    def test_booking_chat_and_notifications_are_committed_with_original_event(self):
        b=self.request(who=self.buyer)
        t=self.workspace.open_thread(self.buyer,booking_id=b["booking_id"])["thread_id"]
        self.assertEqual(self.workspace.threads(self.buyer)[0]["booking_id"],b["booking_id"])
        with self.assertRaisesRegex(ContractError,"OWNED_BOOKING_REQUIRED"):self.workspace.open_thread(CONSUMER,booking_id=b["booking_id"])
        self.assertTrue(self.workspace.notifications(self.buyer))
        with patch.object(self.workspace,"notify",side_effect=ContractError("NOTICE_FAILURE")):
            with self.assertRaises(ContractError):self.repo.act(WHO,b["booking_id"],1,"approve",operator=True)
        self.assertEqual(self.repo.list(self.buyer)[0]["status"],"pending_operator")
        self.repo.act(WHO,b["booking_id"],1,"approve",operator=True)
        self.assertEqual(len(self.workspace.notifications(self.buyer)),2)
        self.assertEqual(self.workspace.messages(self.buyer,t),[])

    def test_consent_fail_retry_replay_optout_suppression_and_live_closed(self):
        self.assertFalse(self.workspace.preferences(CONSUMER)["email_enabled"])
        with self.assertRaises(ContractError):self.workspace.preferences(CONSUMER,dict(email_enabled=1,sms_enabled=False))
        self.workspace.preferences(CONSUMER,dict(email_enabled=True,sms_enabled=False))
        self.workspace.send(self.buyer,self.thread(),"알림 동의 검사",str(uuid4()))
        note=self.workspace.notifications(CONSUMER)[0];delivery=note["deliveries"][0]["delivery_id"]
        self.assertEqual(self.workspace.deliver_owned(delivery,Sandbox(False))["status"],"failed")
        with self.assertRaises(ContractError):self.workspace.retry_delivery(self.buyer,delivery)
        self.workspace.retry_delivery(CONSUMER,delivery)
        sandbox=Sandbox();self.assertEqual(self.workspace.deliver_owned(delivery,sandbox)["status"],"sandbox_sent")
        self.assertTrue(self.workspace.deliver_owned(delivery,sandbox)["replayed"]);self.assertEqual(len(sandbox.sent),1)
        with self.assertRaisesRegex(ContractError,"LIVE_DELIVERY_NOT_APPROVED"):self.workspace.deliver_owned(delivery,object())
        self.workspace.send(self.buyer,self.thread(),"끄기 후 발송 금지",str(uuid4()))
        pending=self.workspace.notifications(CONSUMER)[0]["deliveries"][0]["delivery_id"]
        self.workspace.preferences(CONSUMER,dict(email_enabled=False,sms_enabled=False))
        self.assertEqual(self.workspace.deliver_owned(pending,sandbox)["status"],"suppressed")
        with self.assertRaises(ContractError):self.workspace.read_notification(self.buyer,note["notification_id"])
        self.workspace.read_notification(CONSUMER,note["notification_id"])

    def test_api_auth_csrf_scope_validation_and_no_store(self):
        from hs2_workspace.api import create_blueprint
        self.app.fixture_consumer=self.buyer
        self.app.register_blueprint(create_blueprint(self.workspace,current_consumer=lambda:self.app.fixture_consumer,
            current_operator=lambda:self.app.fixture_booking_operator,csrf_for=lambda who:"owned-csrf",allow_request=lambda:True))
        client=self.app.test_client()
        r=client.get("/hs2/workspace/api/meta");self.assertEqual(r.status_code,200);self.assertEqual(r.headers["Cache-Control"],"no-store")
        self.assertEqual(client.get("/hs2/workspace/api/threads?user_id=101").status_code,403)
        self.assertEqual(client.post("/hs2/workspace/api/threads",json=dict(public_id=self.id)).status_code,403)
        self.assertEqual(client.post("/hs2/workspace/api/threads",json=dict(public_id=self.id,recipient=101),headers={"X-HS2-CSRF":"owned-csrf"}).status_code,403)
        self.app.fixture_consumer=None
        self.assertEqual(client.get("/hs2/workspace/api/meta").status_code,403)


if __name__=="__main__":unittest.main()
