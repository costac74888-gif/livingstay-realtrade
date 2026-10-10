from pathlib import Path
import hashlib
import json
from uuid import uuid4
from hs2_data.repository import require_fixture,save_fixture_snapshot
from hs2_listings.validation import identifier
from hs2_listings.review import public_rows
from hs2_calendar.engine import safe_quote
from hs2_design.domain import ContractError
from hs2_supermap.contracts import parse,point,visible_stay
from .contracts import selection,command,consumer,request_hash

MIGRATION=Path(__file__).parent/"migrations/001.sql"


def migrate(conn):
    require_fixture(conn)
    sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=9")
        old=c.fetchone()
        if old:
            if old[0]!=sha:raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute(MIGRATION.read_text())
        c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(9,%s)",(sha,))


class DetailRepository:
    def __init__(self,supermap,*,member_is_active):
        if not callable(member_is_active):raise ValueError("Trusted consumer account callback required")
        self.supermap=supermap;self.calendar=supermap.calendar;self.registrations=self.calendar.registrations
        self.member_is_active=member_is_active

    def detail(self,public_id):
        identifier(public_id)
        with self.registrations.transaction() as c:
            application=self.application(c,public_id)
            public=next((r for r in public_rows(self.registrations) if r["public_id"]==public_id),None)
            if not public:raise ContractError("PUBLIC_LISTING_NOT_FOUND")
            geometry=point(self.supermap.public_geometry(public_id),limited=True)
            if public_id not in {r["public_id"] for r in public_rows(self.registrations)}:
                raise ContractError("PUBLIC_LISTING_NOT_FOUND")
            item=visible_stay(public,application,None,geometry,parse({}))
        # All stay listings are limited here. No automatic metadata or uploaded
        # private-photo storage URL gets promoted by the detail route.
        return dict(item=item,photos=[],photo_visibility="withheld",booking_confirmed=False,
                    currency="KRW",timezone="Asia/Seoul",deposit_status="not_configured",
                    tax_status="before_payment_review",cancel_status="before_booking_review")

    def application(self,c,public_id):
        c.execute("SELECT id FROM hs2_dev.registration_applications WHERE public_id=%s",(public_id,))
        row=c.fetchone()
        if not row:raise ContractError("PUBLIC_LISTING_NOT_FOUND")
        application=self.registrations.row(c,str(row[0]))
        if public_id not in {r["public_id"] for r in public_rows(self.registrations)}:
            raise ContractError("PUBLIC_LISTING_NOT_FOUND")
        return application

    @staticmethod
    def guests(application,count):
        if application["payload"].get("public_summary") is not True:
            raise ContractError("PUBLIC_CAPACITY_REQUIRED")
        capacity=application["payload"]["guests"]
        # Missing capacity is not an invented guest allowance.
        if type(capacity) is not int or count>capacity:
            raise ContractError("GUEST_CAPACITY_UNAVAILABLE")

    def quote(self,public_id,raw):
        identifier(public_id);values=selection(raw)
        self.detail(public_id)
        with self.registrations.transaction() as c:
            application=self.application(c,public_id);self.guests(application,values["guests"])
            snapshot,_=self.calendar._snapshot(c,application,values["check_in"],values["check_out"])
            return dict(quote=safe_quote(public_id,snapshot),guests=values["guests"],
                        booking_confirmed=False,inventory_held=False)

    def active(self,c,who):
        uid=consumer(who)
        if self.member_is_active(uid) is not True:raise ContractError("ACTIVE_CONSUMER_REQUIRED")
        c.execute("SELECT active FROM hs2_fixture_legacy.users WHERE id=%s FOR SHARE",(uid,))
        row=c.fetchone()
        if not row or row[0] is not True:raise ContractError("ACTIVE_CONSUMER_REQUIRED")
        return uid

    @staticmethod
    def receipt(c,key,uid):
        c.execute("""SELECT id,public_id,source_version,application_revision,guests,public_quote,expires_at,
            expires_at>clock_timestamp(),request_hash FROM hs2_dev.consumer_quote_receipts
            WHERE id=%s AND user_id=%s""",(key,uid))
        row=c.fetchone()
        if not row:raise ContractError("QUOTE_RECEIPT_NOT_FOUND")
        if row[7] is not True:raise ContractError("QUOTE_RECEIPT_EXPIRED")
        return dict(receipt_id=str(row[0]),public_id=str(row[1]),source_version=row[2],
                    source_revision=row[3],guests=row[4],quote=row[5],expires_at=row[6].isoformat(),
                    _request_hash=row[8],booking_confirmed=False,inventory_held=False)

    def confirm_quote(self,who,public_id,raw):
        identifier(public_id);data=command(raw);digest=request_hash(public_id,data)
        with self.registrations.transaction() as c:
            uid=self.active(c,who)
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-quote:{uid}:{data['request_id']}",))
            application=self.application(c,public_id);self.guests(application,data["guests"])
            snapshot,latest=self.calendar._snapshot(c,application,data["check_in"],data["check_out"])
            quote=safe_quote(public_id,snapshot)
            if quote["source_version"]!=data["expected_source_version"]:
                raise ContractError("QUOTE_SOURCE_CHANGED")
            c.execute("SELECT id FROM hs2_dev.consumer_quote_receipts WHERE user_id=%s AND request_id=%s",(uid,data["request_id"]))
            old=c.fetchone()
            if old:
                receipt=self.receipt(c,str(old[0]),uid)
                if receipt.pop("_request_hash")!=digest:raise ContractError("QUOTE_RETRY_CONFLICT")
                return receipt
            c.execute("""INSERT INTO hs2_dev.tariff_versions(id,listing_id,version,payload)
                VALUES(%s,%s,%s,%s) ON CONFLICT(listing_id,version) DO NOTHING""",
                (str(uuid4()),application["listing_id"],snapshot.tariff_version,json.dumps(latest["calendar"])))
            snap,key=str(uuid4()),str(uuid4());save_fixture_snapshot(c.connection,snap,snapshot)
            c.execute("""INSERT INTO hs2_dev.consumer_quote_receipts
                (id,user_id,public_id,snapshot_id,request_id,request_hash,source_version,application_revision,guests,public_quote)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (key,uid,public_id,snap,data["request_id"],digest,quote["source_version"],application["revision"],data["guests"],json.dumps(quote)))
            result=self.receipt(c,key,uid);result.pop("_request_hash");return result

    def read_receipt(self,who,key):
        identifier(key)
        with self.registrations.transaction() as c:
            uid=self.active(c,who);receipt=self.receipt(c,key,uid);receipt.pop("_request_hash")
            application=self.application(c,receipt["public_id"])
            if application["revision"]!=receipt["source_revision"]:raise ContractError("QUOTE_SOURCE_CHANGED")
            self.guests(application,receipt["guests"])
            snapshot,_=self.calendar._snapshot(c,application,receipt["quote"]["check_in"],receipt["quote"]["check_out"])
            if safe_quote(receipt["public_id"],snapshot)["source_version"]!=receipt["source_version"]:
                raise ContractError("QUOTE_SOURCE_CHANGED")
            return receipt
