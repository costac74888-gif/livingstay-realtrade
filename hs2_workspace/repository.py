import hashlib,json
from pathlib import Path
from uuid import uuid4
from hs2_design.domain import ContractError
from hs2_data.repository import require_fixture
from hs2_listings.validation import identifier,actor
from hs2_details.contracts import consumer

MIGRATION=Path(__file__).parent/"migrations/001.sql"


def migrate(conn):
    require_fixture(conn);sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=13");old=c.fetchone()
        if old:
            if old[0]!=sha:raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute(MIGRATION.read_text());c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(13,%s)",(sha,))


class WorkspaceRepository:
    def __init__(self,finance):
        self.finance=finance;self.bookings=finance.bookings;self.details=self.bookings.details
        self.registrations=finance.registrations

    def active(self,c,who,operator=False):
        if operator:self.registrations.active(c,who)
        else:
            consumer(who)
            if self.details.member_is_active(who["user_id"]) is not True:raise ContractError("ACTIVE_MEMBER_REQUIRED")
        c.execute("SELECT id FROM hs2_fixture_legacy.users WHERE id=%s AND active FOR SHARE",(who["user_id"],))
        if not c.fetchone():raise ContractError("ACTIVE_MEMBER_REQUIRED")

    def favorites(self,who):
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("SELECT public_id FROM hs2_dev.stay_favorites WHERE user_id=%s ORDER BY created_at DESC,public_id LIMIT 100",(who["user_id"],))
            keys=[str(r[0]) for r in c.fetchall()]
        items=[]
        for key in keys:
            try:items.append(dict(public_id=key,available=True,item=self.details.detail(key)["item"],uri="/hs2/details/?public_id="+key))
            except ContractError as e:
                if str(e)!="PUBLIC_LISTING_NOT_FOUND":raise
                items.append(dict(public_id=key,available=False,item=None,uri=None))
        return items

    def favorite(self,who,key,enabled):
        identifier(key)
        if type(enabled) is not bool:raise ContractError("INVALID_FAVORITE")
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("SELECT pg_advisory_xact_lock(%s)",(who["user_id"],))
            if enabled:
                self.details.application(c,key)
                c.execute("SELECT count(*) FROM hs2_dev.stay_favorites WHERE user_id=%s",(who["user_id"],))
                if c.fetchone()[0]>=100:
                    c.execute("SELECT 1 FROM hs2_dev.stay_favorites WHERE user_id=%s AND public_id=%s",(who["user_id"],key))
                    if not c.fetchone():raise ContractError("FAVORITE_LIMIT")
                c.execute("INSERT INTO hs2_dev.stay_favorites(user_id,public_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(who["user_id"],key))
            else:c.execute("DELETE FROM hs2_dev.stay_favorites WHERE user_id=%s AND public_id=%s",(who["user_id"],key))
        return dict(public_id=key,enabled=enabled)

    def open_thread(self,who,*,public_id=None,booking_id=None):
        if bool(public_id)==bool(booking_id):raise ContractError("ONE_CHAT_REFERENCE_REQUIRED")
        identifier(public_id or booking_id)
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("SELECT pg_advisory_xact_lock(%s)",(who["user_id"],))
            if booking_id:
                c.execute("""SELECT a.id,a.user_id,a.context_id FROM hs2_dev.bookings b
                    JOIN hs2_dev.registration_applications a ON a.id=b.application_id
                    WHERE b.id=%s AND b.user_id=%s""",(booking_id,who["user_id"]))
                r=c.fetchone()
                if not r:raise ContractError("OWNED_BOOKING_REQUIRED")
                application,owner,context=str(r[0]),r[1],r[2]
            else:
                r=self.details.application(c,public_id)
                application,owner,context=r["id"],r["user_id"],r["context_id"]
            c.execute("""SELECT id FROM hs2_dev.stay_threads WHERE application_id=%s AND consumer_user_id=%s
                AND booking_id IS NOT DISTINCT FROM %s::uuid""",(application,who["user_id"],booking_id))
            old=c.fetchone()
            if old:return dict(thread_id=str(old[0]))
            key=str(uuid4())
            c.execute("""INSERT INTO hs2_dev.stay_threads
                (id,application_id,consumer_user_id,operator_user_id,operator_context_id,booking_id)
                VALUES(%s,%s,%s,%s,%s,%s)""",(key,application,who["user_id"],owner,context,booking_id))
        return dict(thread_id=key)

    def thread(self,c,who,key,operator=False):
        identifier(key);self.active(c,who,operator)
        c.execute("""SELECT id,consumer_user_id,operator_user_id,operator_context_id,booking_id,application_id
            FROM hs2_dev.stay_threads WHERE id=%s""",(key,))
        r=c.fetchone()
        if not r or (operator and (r[2]!=who["user_id"] or r[3]!=who["context_id"])) or (not operator and r[1]!=who["user_id"]):
            raise ContractError("CHAT_NOT_FOUND")
        return r

    def threads(self,who,operator=False):
        with self.registrations.transaction() as c:
            self.active(c,who,operator)
            condition="t.operator_user_id=%s AND t.operator_context_id=%s" if operator else "t.consumer_user_id=%s"
            params=(who["user_id"],who["context_id"]) if operator else (who["user_id"],)
            c.execute("""SELECT t.id,t.booking_id,
                (SELECT count(*) FROM hs2_dev.stay_messages m WHERE m.thread_id=t.id AND m.sender_user_id<>%s
                    AND (m.created_at,m.id)>COALESCE((SELECT ROW(r.through_at,r.through_message_id) FROM hs2_dev.stay_thread_reads r
                        WHERE r.thread_id=t.id AND r.user_id=%s),ROW('-infinity'::timestamptz,'00000000-0000-0000-0000-000000000000'::uuid)))
                FROM hs2_dev.stay_threads t WHERE """+condition+" ORDER BY t.created_at DESC,t.id LIMIT 100",
                (who["user_id"],who["user_id"],*params))
            return [dict(thread_id=str(r[0]),booking_id=str(r[1]) if r[1] else None,unread=r[2]) for r in c.fetchall()]

    def messages(self,who,key,operator=False):
        with self.registrations.transaction() as c:
            self.thread(c,who,key,operator)
            c.execute("""SELECT id,body,sender_user_id,created_at FROM
                (SELECT * FROM hs2_dev.stay_messages WHERE thread_id=%s ORDER BY created_at DESC,id DESC LIMIT 100) m
                ORDER BY created_at,id""",(key,))
            return [dict(message_id=str(r[0]),body=r[1],mine=r[2]==who["user_id"],at=r[3].isoformat()) for r in c.fetchall()]

    def send(self,who,key,body,request_id,operator=False):
        identifier(key);identifier(request_id)
        if type(body) is not str or not 1<=len(body.strip())<=2000 or "\0" in body:raise ContractError("INVALID_CHAT_BODY")
        body=body.strip();sha=hashlib.sha256(json.dumps([key,body],ensure_ascii=False).encode()).hexdigest()
        with self.registrations.transaction() as c:
            t=self.thread(c,who,key,operator)
            c.execute("SELECT pg_advisory_xact_lock(%s)",(who["user_id"],))
            c.execute("SELECT id,request_hash FROM hs2_dev.stay_messages WHERE sender_user_id=%s AND request_id=%s",(who["user_id"],request_id))
            old=c.fetchone()
            if old:
                if old[1]!=sha:raise ContractError("CHAT_IDEMPOTENCY_CONFLICT")
                return dict(message_id=str(old[0]),replayed=True)
            message=str(uuid4())
            c.execute("INSERT INTO hs2_dev.stay_messages(id,thread_id,sender_user_id,request_id,request_hash,body) VALUES(%s,%s,%s,%s,%s,%s)",
                (message,key,who["user_id"],request_id,sha,body))
            recipient=t[1] if operator else t[2]
            self.notify(c,recipient,"message:"+message,"chat","/hs2/workspace/?view="+("consumer" if operator else "operator")+"&thread_id="+key)
        return dict(message_id=message,replayed=False)

    def read_thread(self,who,key,through_message_id,operator=False):
        identifier(through_message_id)
        with self.registrations.transaction() as c:
            self.thread(c,who,key,operator)
            # A message arriving after GET cannot be marked read accidentally.
            c.execute("""INSERT INTO hs2_dev.stay_thread_reads(thread_id,user_id,through_at,through_message_id)
                SELECT %s,%s,created_at,id FROM hs2_dev.stay_messages WHERE thread_id=%s AND id=%s
                ON CONFLICT(thread_id,user_id) DO UPDATE SET through_at=EXCLUDED.through_at,
                    through_message_id=EXCLUDED.through_message_id
                WHERE (stay_thread_reads.through_at,stay_thread_reads.through_message_id)<(EXCLUDED.through_at,EXCLUDED.through_message_id)
                RETURNING thread_id""",(key,who["user_id"],key,through_message_id))
            if not c.fetchone():
                c.execute("SELECT 1 FROM hs2_dev.stay_messages WHERE thread_id=%s AND id=%s",(key,through_message_id))
                if not c.fetchone():raise ContractError("READ_MESSAGE_NOT_FOUND")
        return dict(read=True)

    @staticmethod
    def notify(c,user,source,kind,uri):
        c.execute("""INSERT INTO hs2_dev.stay_notifications(id,user_id,source_key,kind,uri)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(user_id,source_key) DO NOTHING RETURNING id""",(str(uuid4()),user,source,kind,uri))
        r=c.fetchone()
        if not r:return
        c.execute("SELECT email_enabled,sms_enabled FROM hs2_dev.stay_notification_preferences WHERE user_id=%s",(user,))
        pref=c.fetchone() or (False,False)
        for enabled,channel in zip(pref,("email","sms")):
            if enabled:c.execute("INSERT INTO hs2_dev.stay_notification_deliveries(id,notification_id,channel) VALUES(%s,%s,%s)",(str(uuid4()),r[0],channel))

    def booking_event(self,c,key,actor_id,kind,payload):
        c.execute("""SELECT b.user_id,a.user_id,b.revision FROM hs2_dev.bookings b
            JOIN hs2_dev.registration_applications a ON a.id=b.application_id WHERE b.id=%s""",(key,))
        r=c.fetchone()
        if not r:raise ContractError("BOOKING_NOTICE_SOURCE_REQUIRED")
        for user,view in {(r[0],"consumer"),(r[1],"operator")}:
            self.notify(c,user,f"booking:{key}:{r[2]}:{kind}","booking_"+kind,"/hs2/bookings/?view="+view+"&booking_id="+key)

    def preferences(self,who,values=None):
        with self.registrations.transaction() as c:
            self.active(c,who)
            if values is not None:
                if type(values) is not dict or set(values)!={"email_enabled","sms_enabled"} or any(type(v) is not bool for v in values.values()):raise ContractError("EXPLICIT_NOTIFICATION_CONSENT_REQUIRED")
                c.execute("""INSERT INTO hs2_dev.stay_notification_preferences(user_id,email_enabled,sms_enabled)
                    VALUES(%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET email_enabled=EXCLUDED.email_enabled,
                    sms_enabled=EXCLUDED.sms_enabled,updated_at=clock_timestamp()""",(who["user_id"],values["email_enabled"],values["sms_enabled"]))
            c.execute("SELECT email_enabled,sms_enabled FROM hs2_dev.stay_notification_preferences WHERE user_id=%s",(who["user_id"],))
            r=c.fetchone() or (False,False)
            return dict(email_enabled=r[0],sms_enabled=r[1],live_delivery_enabled=False)

    def notifications(self,who):
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("""SELECT n.id,n.kind,n.uri,n.read_at IS NOT NULL,n.created_at,
                COALESCE((SELECT jsonb_agg(jsonb_build_object('delivery_id',d.id,'channel',d.channel,'status',d.status,'attempts',d.attempts))
                    FROM hs2_dev.stay_notification_deliveries d WHERE d.notification_id=n.id),'[]'::jsonb)
                FROM hs2_dev.stay_notifications n WHERE n.user_id=%s ORDER BY n.created_at DESC,n.id LIMIT 100""",(who["user_id"],))
            return [dict(notification_id=str(r[0]),kind=r[1],uri=r[2],read=r[3],at=r[4].isoformat(),deliveries=r[5]) for r in c.fetchall()]

    def read_notification(self,who,key):
        identifier(key)
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("UPDATE hs2_dev.stay_notifications SET read_at=COALESCE(read_at,clock_timestamp()) WHERE id=%s AND user_id=%s RETURNING id",(key,who["user_id"]))
            if not c.fetchone():raise ContractError("NOTIFICATION_NOT_FOUND")
        return dict(read=True)

    def retry_delivery(self,who,key):
        identifier(key)
        with self.registrations.transaction() as c:
            self.active(c,who)
            c.execute("""UPDATE hs2_dev.stay_notification_deliveries d SET status='pending',updated_at=clock_timestamp()
                FROM hs2_dev.stay_notifications n WHERE n.id=d.notification_id AND n.user_id=%s
                AND d.id=%s AND d.status='failed' AND d.attempts<5 RETURNING d.id""",(who["user_id"],key))
            if not c.fetchone():raise ContractError("RETRYABLE_OWNED_DELIVERY_REQUIRED")
        return dict(status="pending")

    def deliver_owned(self,key,adapter):
        """Isolated delivery test only: no live transport, no contact data."""
        identifier(key)
        if getattr(adapter,"owned_sandbox",False) is not True:raise ContractError("LIVE_DELIVERY_NOT_APPROVED")
        with self.registrations.transaction() as c:
            c.execute("""SELECT d.id,d.status,d.attempts,d.channel,n.user_id,n.kind FROM hs2_dev.stay_notification_deliveries d
                JOIN hs2_dev.stay_notifications n ON n.id=d.notification_id WHERE d.id=%s FOR UPDATE OF d""",(key,))
            r=c.fetchone()
            if not r:raise ContractError("DELIVERY_NOT_FOUND")
            if r[1] not in {"pending","failed"} or r[2]>=5:return dict(status=r[1],replayed=True)
            c.execute("""SELECT u.active,COALESCE(p.email_enabled,false),COALESCE(p.sms_enabled,false)
                FROM hs2_fixture_legacy.users u LEFT JOIN hs2_dev.stay_notification_preferences p ON p.user_id=u.id WHERE u.id=%s""",(r[4],))
            pref=c.fetchone()
            if not pref or not pref[0] or not pref[1 if r[3]=="email" else 2]:status="suppressed"
            else:
                try:status="sandbox_sent" if adapter.send(dict(delivery_id=key,channel=r[3],kind=r[5])) is True else "failed"
                except Exception:status="failed"
            c.execute("UPDATE hs2_dev.stay_notification_deliveries SET status=%s,attempts=attempts+1,updated_at=clock_timestamp() WHERE id=%s",(status,key))
        return dict(status=status,actual_message_sent=False)
