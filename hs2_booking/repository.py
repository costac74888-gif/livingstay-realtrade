"""Serialize physical-space holds and preserve the original immutable price."""
from pathlib import Path
from uuid import uuid4
import hashlib,json
from hs2_data.repository import require_fixture
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier
from hs2_calendar.engine import POLICY_VERSION
from .contracts import request_command,revision,proof

MIGRATION=Path(__file__).parent/"migrations/001.sql"
ACTIVE=("pending_operator","awaiting_payment","confirmed")


def migrate(conn):
    require_fixture(conn);sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=10")
        old=c.fetchone()
        if old:
            if old[0]!=sha:raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute(MIGRATION.read_text())
        c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(10,%s)",(sha,))


class BookingRepository:
    def __init__(self,details,*,payment_proof=None,payment_terms_reviewed=None):
        self.details=details;self.registrations=details.registrations;self.calendar=details.calendar
        if payment_proof is not None and not callable(payment_proof):raise ValueError("Trusted payment adapter required")
        self.payment_proof=payment_proof;self.payment_terms_reviewed=payment_terms_reviewed

    @staticmethod
    def event(c,key,actor,kind,payload=None):
        c.execute("INSERT INTO hs2_dev.booking_events(booking_id,actor_user_id,kind,payload) VALUES(%s,%s,%s,%s)",
            (key,actor,kind,json.dumps(payload or {})))

    def expire(self,c):
        c.execute("""UPDATE hs2_dev.bookings SET status='expired',deadline=NULL,revision=revision+1
            WHERE status IN('pending_operator','awaiting_payment') AND deadline<=clock_timestamp()
            RETURNING id""")
        for row in c.fetchall():
            self.event(c,str(row[0]),None,"expired")
            c.execute("DELETE FROM hs2_dev.booking_slots WHERE booking_id=%s",(str(row[0]),))

    @staticmethod
    def pools(c,pool,*,lock=True):
        c.execute("SELECT registered_building_id FROM hs2_dev.inventory_pools WHERE id=%s",(pool,))
        row=c.fetchone()
        if not row:raise ContractError("VERIFIED_INVENTORY_REQUIRED")
        building=str(row[0])
        # Whole-space and its descendant units share slots; siblings do not.
        # A building lock also serializes graph edits made by trusted services.
        c.execute("SELECT id FROM hs2_dev.registered_buildings WHERE id=%s"+(" FOR UPDATE" if lock else ""),(building,))
        if not c.fetchone():raise ContractError("VERIFIED_INVENTORY_REQUIRED")
        c.execute("""WITH RECURSIVE paths AS (
            SELECT id,ARRAY[id] AS path,false AS cycle FROM hs2_dev.inventory_pools WHERE id=%s
            UNION ALL SELECT m.child_id,p.path||m.child_id,m.child_id=ANY(p.path)
            FROM paths p JOIN hs2_dev.inventory_members m ON m.parent_id=p.id
            WHERE NOT p.cycle)
            SELECT id,cycle FROM paths LIMIT 1001""",(pool,))
        rows=c.fetchall()
        if len(rows)>1000 or any(r[1] for r in rows):raise ContractError("INVALID_INVENTORY_GRAPH")
        ids=sorted({str(r[0]) for r in rows})
        if lock:
            c.execute("SELECT id FROM hs2_dev.inventory_pools WHERE id=ANY(%s::uuid[]) ORDER BY id FOR UPDATE",(ids,))
            c.fetchall()
        return ids

    @staticmethod
    def available(c,pools,start,end):
        # Expand held roots against the CURRENT graph as well: a new child of
        # a held whole-space must not become accidentally bookable.
        c.execute("""WITH RECURSIVE held AS (
            SELECT s.pool_id FROM hs2_dev.booking_slots s JOIN hs2_dev.bookings b ON b.id=s.booking_id
            JOIN hs2_dev.inventory_pools p ON p.id=s.pool_id
            WHERE p.registered_building_id=(SELECT registered_building_id FROM hs2_dev.inventory_pools
                WHERE id=ANY(%s::uuid[]) LIMIT 1)
            AND b.status IN('pending_operator','awaiting_payment','confirmed')
            AND (b.deadline IS NULL OR b.deadline>clock_timestamp())
            AND b.check_in<%s AND b.check_out>%s
            UNION SELECT m.child_id FROM held h JOIN hs2_dev.inventory_members m ON m.parent_id=h.pool_id)
            SELECT 1 FROM held WHERE pool_id=ANY(%s::uuid[]) LIMIT 1""",(pools,end,start,pools))
        return c.fetchone() is None

    def inventory_available(self,pool,start,end):
        with self.registrations.transaction() as c:
            return self.available(c,self.pools(c,pool,lock=False),start,end)

    @staticmethod
    def row(c,key,uid,*,operator=False):
        identifier(key)
        c.execute("""SELECT b.id,b.user_id,b.application_id,b.receipt_id,b.status,b.revision,b.check_in,
            b.check_out,b.deadline,b.payment_reference,q.public_id,q.public_quote,q.application_revision,
            q.source_version,q.guests,s.total_krw FROM hs2_dev.bookings b
            JOIN hs2_dev.registration_applications a ON a.id=b.application_id
            JOIN hs2_dev.consumer_quote_receipts q ON q.id=b.receipt_id
            JOIN hs2_dev.price_snapshots s ON s.id=b.snapshot_id
            WHERE b.id=%s AND """+("a.user_id=%s" if operator else "b.user_id=%s")+" FOR UPDATE OF b",
            (key,uid))
        row=c.fetchone()
        if not row:raise ContractError("BOOKING_NOT_FOUND")
        return dict(zip(("id","user_id","application_id","receipt_id","status","revision","check_in","check_out",
                         "deadline","payment_reference","public_id","quote","source_revision","source_version","guests","total_krw"),row))

    @staticmethod
    def public(row):
        return dict(booking_id=str(row["id"]),public_id=str(row["public_id"]),status=row["status"],
            revision=row["revision"],check_in=row["check_in"].isoformat(),check_out=row["check_out"].isoformat(),
            deadline=row["deadline"].isoformat() if row["deadline"] else None,quote=row["quote"],
            guests=row["guests"],booking_confirmed=row["status"]=="confirmed",
            payment_verified=row["payment_reference"] is not None,
            inventory_held=row["status"] in ACTIVE)

    def source(self,c,application,receipt):
        if application["revision"]!=receipt["source_revision"]:raise ContractError("QUOTE_SOURCE_CHANGED")
        latest=self.calendar.latest(c,application)
        if latest["stale"] or not latest["tariff_version"]:raise ContractError("QUOTE_SOURCE_CHANGED")
        current=hashlib.sha256((latest["tariff_version"]+"|"+POLICY_VERSION).encode()).hexdigest()
        if current!=receipt["source_version"]:raise ContractError("QUOTE_SOURCE_CHANGED")
        self.details.guests(application,receipt["guests"])

    def request(self,who,raw):
        digest=request_command(raw)
        with self.registrations.transaction() as c:
            uid=self.details.active(c,who)
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-booking-consumer:{uid}",))
            self.expire(c)
            c.execute("SELECT id,request_hash FROM hs2_dev.bookings WHERE user_id=%s AND request_id=%s",(uid,raw["request_id"]))
            prior=c.fetchone()
            if prior:
                if prior[1]!=digest:raise ContractError("BOOKING_RETRY_CONFLICT")
                return self.public(self.row(c,str(prior[0]),uid))
            receipt=self.details.receipt(c,raw["receipt_id"],uid)
            receipt.pop("_request_hash")
            application=self.details.application(c,receipt["public_id"])
            self.source(c,application,receipt)
            c.execute("SELECT snapshot_id FROM hs2_dev.consumer_quote_receipts WHERE id=%s FOR SHARE",(raw["receipt_id"],))
            snapshot_id=str(c.fetchone()[0])
            c.execute("SELECT pool_id FROM hs2_dev.stay_listings WHERE id=%s",(application["listing_id"],))
            pool=c.fetchone()
            if not pool:raise ContractError("VERIFIED_INVENTORY_REQUIRED")
            ids=self.pools(c,str(pool[0]))
            # Recompute blocked-day/classification/price inside the source lock.
            # The inventory provider sees only committed competing holds.
            current,_=self.calendar._snapshot(c,application,receipt["quote"]["check_in"],receipt["quote"]["check_out"])
            if current.total_krw!=receipt["quote"]["total_krw"]:raise ContractError("QUOTE_SOURCE_CHANGED")
            if not self.available(c,ids,current.check_in,current.check_out):raise ContractError("BOOKING_INVENTORY_CONFLICT")
            c.execute("SELECT count(*) FROM hs2_dev.bookings WHERE user_id=%s AND status IN('pending_operator','awaiting_payment')",(uid,))
            if c.fetchone()[0]>=3:raise ContractError("ACTIVE_BOOKING_LIMIT")
            c.execute("SELECT 1 FROM hs2_dev.bookings WHERE receipt_id=%s",(raw["receipt_id"],))
            if c.fetchone():raise ContractError("QUOTE_RECEIPT_ALREADY_USED")
            key=str(uuid4())
            c.execute("""INSERT INTO hs2_dev.bookings
                (id,user_id,application_id,receipt_id,snapshot_id,request_id,request_hash,status,check_in,check_out,deadline)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'pending_operator',%s,%s,clock_timestamp()+interval '30 minutes')""",
                (key,uid,application["id"],raw["receipt_id"],snapshot_id,raw["request_id"],digest,current.check_in,current.check_out))
            for pool_id in ids:c.execute("INSERT INTO hs2_dev.booking_slots VALUES(%s,%s)",(key,pool_id))
            self.event(c,key,uid,"requested",dict(policy="operator30m-payment2h-active3"))
            return self.public(self.row(c,key,uid))

    def list(self,who,*,operator=False):
        with self.registrations.transaction() as c:
            if operator:self.registrations.active(c,who);uid=who["user_id"]
            else:uid=self.details.active(c,who)
            self.expire(c)
            c.execute("""SELECT b.id FROM hs2_dev.bookings b JOIN hs2_dev.registration_applications a ON a.id=b.application_id
                WHERE """+("a.user_id=%s AND a.context_id=%s" if operator else "b.user_id=%s")+" ORDER BY b.created_at DESC LIMIT 100",
                (uid,who["context_id"]) if operator else (uid,))
            keys=[str(r[0]) for r in c.fetchall()]
            return [self.public(self.row(c,key,uid,operator=operator)) for key in keys]

    def act(self,who,key,expected,action,*,operator=False):
        revision(expected)
        if action not in ({"approve","reject"} if operator else {"cancel","confirm-payment"}):
            raise ContractError("INVALID_BOOKING_ACTION")
        with self.registrations.transaction() as c:
            if operator:self.registrations.active(c,who);uid=who["user_id"]
            else:uid=self.details.active(c,who)
            self.expire(c);row=self.row(c,key,uid,operator=operator)
            application=self.registrations.row(c,str(row["application_id"]),who if operator else None)
            if action=="confirm-payment" and row["status"]=="confirmed":return self.public(row)
            if row["revision"]!=expected:raise ContractError("BOOKING_REVISION_CHANGED")
            if action in {"approve","reject"} and row["status"]!="pending_operator":raise ContractError("BOOKING_STATE_CHANGED")
            if action in {"cancel","confirm-payment"} and row["status"] not in {"pending_operator","awaiting_payment"}:
                raise ContractError("BOOKING_STATE_CHANGED")
            reference=row["payment_reference"]
            if action=="approve":
                self.details.application(c,str(row["public_id"]));self.source(c,application,row)
                status="awaiting_payment";deadline="clock_timestamp()+interval '2 hours'"
            elif action=="confirm-payment":
                if row["status"]!="awaiting_payment":raise ContractError("BOOKING_STATE_CHANGED")
                if not self.payment_proof or not callable(self.payment_terms_reviewed):
                    raise ContractError("PAYMENT_PROVIDER_UNAVAILABLE")
                if self.payment_terms_reviewed(str(row["id"])) is not True:raise ContractError("PAYMENT_TERMS_REVIEW_REQUIRED")
                self.details.application(c,str(row["public_id"]));self.source(c,application,row)
                reference=proof(self.payment_proof(str(row["id"])),str(row["id"]),row["total_krw"])
                c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-payment-reference:{reference}",))
                c.execute("SELECT id FROM hs2_dev.bookings WHERE payment_reference=%s AND id<>%s",(reference,key))
                if c.fetchone():raise ContractError("PAYMENT_REFERENCE_REPLAY")
                status="confirmed";deadline="NULL"
            else:status="rejected" if action=="reject" else "cancelled";deadline="NULL"
            c.execute(f"UPDATE hs2_dev.bookings SET status=%s,deadline={deadline},payment_reference=%s,revision=revision+1 WHERE id=%s",(status,reference,key))
            if status not in ACTIVE:c.execute("DELETE FROM hs2_dev.booking_slots WHERE booking_id=%s",(key,))
            self.event(c,key,uid,action)
            return self.public(self.row(c,key,uid,operator=operator))
