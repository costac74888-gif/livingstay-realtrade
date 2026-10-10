from wsgiref.simple_server import make_server,WSGIRequestHandler
from hs2_registration.fixture_http import LocalServer
from hs2_finance.fixture_http import seed_paid
from hs2_supermap.contracts import parse
from .fixtures import create_fixture_app
from uuid import uuid4


def server(port=0):
    app=create_fixture_app()
    seed_paid(app)
    public=next(r["public_id"] for r in app.fixture_supermap.search(parse({}))["items"] if r["stay_kind"]=="lodging")
    who=app.fixture_consumer
    app.fixture_workspace.preferences(who,dict(email_enabled=True,sms_enabled=False))
    app.fixture_workspace.favorite(who,public,True)
    thread=app.fixture_workspace.open_thread(who,public_id=public)["thread_id"]
    app.fixture_workspace.send(who,thread,"입실 방법과 이용 조건을 확인하고 싶습니다.",str(uuid4()))
    class FailedOwnedTransport:
        owned_sandbox=True
        def send(self,data):return False
    for note in app.fixture_workspace.notifications(who):
        for delivery in note["deliveries"]:app.fixture_workspace.deliver_owned(delivery["delivery_id"],FailedOwnedTransport())
    return make_server("127.0.0.1",port,app,server_class=LocalServer,handler_class=WSGIRequestHandler)
