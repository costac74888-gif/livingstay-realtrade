"""Immutable financial facts and review requests; never initiates live transfers."""
from pathlib import Path
from uuid import uuid4
from datetime import date,timedelta
import hashlib,json
from hs2_data.repository import require_fixture
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier
from .policy import ReviewedPolicy,money

MIGRATION=Path(__file__).parent/"migrations/001.sql"


def migrate(conn):
    require_fixture(conn);sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=11")
        old=c.fetchone()
        if old:
            if old[0]!=sha:raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute(MIGRATION.read_text());c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(11,%s)",(sha,))


class FinanceRepository:
    def __init__(self,bookings,*,policy_for,consumer_for,provider=None,live_approved=lambda:False):
        if not all(callable(p) for p in (policy_for,consumer_for,live_approved)):
            raise ValueError("Trusted financial policy,identity and operational-gate ports required")
        if provider is not None and (not callable(getattr(provider,"verify",None)) or type(getattr(provider,"sandbox",None)) is not bool):
            raise ValueError("Trusted provider adapter required")
        self.bookings=bookings;self.registrations=bookings.registrations
        self.policy_for=policy_for;self.consumer_for=consumer_for;self.provider=provider;self.live_approved=live_approved

    def provider_ready(self):
        return self.provider is not None and (self.provider.sandbox or self.live_approved() is True)

    @staticmethod
    def today(c):
        c.execute("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date")
        return c.fetchone()[0]

    @staticmethod
    def row(c,key):
        identifier(key)
        # If a concurrent capture waits here, the first statement's joined
        # booking snapshot can predate that capture. Lock the contract first,
        # then read booking state in a new READ COMMITTED statement snapshot.
        c.execute("SELECT id FROM hs2_dev.financial_contracts WHERE id=%s FOR UPDATE",(key,))
        if not c.fetchone():raise ContractError("FINANCIAL_CONTRACT_NOT_FOUND")
        c.execute("""SELECT f.id,f.booking_id,f.user_id,f.terms,f.sandbox,b.status,b.check_in,b.check_out
            FROM hs2_dev.financial_contracts f JOIN hs2_dev.bookings b ON b.id=f.booking_id
            WHERE f.id=%s""",(key,))
        r=c.fetchone()
        if not r:raise ContractError("FINANCIAL_CONTRACT_NOT_FOUND")
        return dict(zip(("id","booking_id","user_id","terms","sandbox","booking_status","check_in","check_out"),r))

    @staticmethod
    def events(c,key):
        c.execute("SELECT kind,amount_krw,at,payload FROM hs2_dev.financial_events WHERE contract_id=%s ORDER BY at,id",(key,))
        return [dict(kind=r[0],amount_krw=r[1],at=r[2].isoformat(),payload=r[3]) for r in c.fetchall()]

    def public(self,c,row):
        events=self.events(c,str(row["id"]));kinds={e["kind"] for e in events}
        c.execute("SELECT 1 FROM hs2_dev.paid_booking_cancellations WHERE booking_id=%s",(str(row["booking_id"]),))
        cancelled=c.fetchone() is not None
        status="refund_review" if "refund_review" in kinds else "late_payment_review" if "late_capture" in kinds else "captured" if "capture" in kinds else "awaiting_payment"
        return dict(contract_id=str(row["id"]),booking_id=str(row["booking_id"]),terms=row["terms"],
            status=status,sandbox=row["sandbox"],actual_money_executed=False,
            booking_cancelled=cancelled,events=events,provider_available=self.provider_ready(),
            payment_verified="capture" in kinds,booking_confirmed=row["booking_status"]=="confirmed" and not cancelled,
            check_in=row["check_in"].isoformat(),check_out=row["check_out"].isoformat(),
            refund_krw=next((e["amount_krw"] for e in events if e["kind"]=="refund_review"),None),
            deposit_return_on=(row["check_out"]+timedelta(days=row["terms"]["policy"]["deposit_return_days"])).isoformat(),
            payout_review_on=(row["check_out"]+timedelta(days=row["terms"]["policy"]["settlement_days"])).isoformat())

    def authority(self,c,who,row,operator):
        if operator:
            self.registrations.active(c,who)
            booking=self.bookings.row(c,str(row["booking_id"]),who["user_id"],operator=True)
            self.registrations.row(c,str(booking["application_id"]),who)
        elif self.bookings.details.active(c,who)!=row["user_id"]:raise ContractError("FINANCIAL_CONTRACT_NOT_FOUND")

    def create(self,who,raw):
        if not isinstance(raw,dict) or set(raw)!={"booking_id","request_id","acknowledged","expected_terms_sha256"} or raw["acknowledged"] is not True:
            raise ContractError("FINANCIAL_ACK_REQUIRED")
        identifier(raw["booking_id"]);identifier(raw["request_id"])
        with self.registrations.transaction() as c:
            uid=self.bookings.details.active(c,who)
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-finance-create:{uid}",))
            c.execute("SELECT id,booking_id FROM hs2_dev.financial_contracts WHERE user_id=%s AND request_id=%s",(uid,raw["request_id"]))
            prior=c.fetchone()
            if prior:
                if str(prior[1])!=raw["booking_id"]:raise ContractError("FINANCIAL_RETRY_CONFLICT")
                prior_row=self.row(c,str(prior[0]))
                if self.terms_digest(raw["booking_id"],prior_row["terms"])!=raw["expected_terms_sha256"]:
                    raise ContractError("FINANCIAL_RETRY_CONFLICT")
                return self.public(c,prior_row)
            c.execute("SELECT id FROM hs2_dev.financial_contracts WHERE booking_id=%s AND user_id=%s",(raw["booking_id"],uid))
            existing=c.fetchone()
            if existing:
                previous=self.row(c,str(existing[0]))
                if self.terms_digest(raw["booking_id"],previous["terms"])!=raw["expected_terms_sha256"]:
                    raise ContractError("FINANCIAL_TERMS_CHANGED")
                return self.public(c,previous)
            booking=self.bookings.row(c,raw["booking_id"],uid)
            if booking["status"]!="awaiting_payment":raise ContractError("BOOKING_STATE_CHANGED")
            policy=self.policy_for(raw["booking_id"])
            if not isinstance(policy,ReviewedPolicy):raise ContractError("REVIEWED_FINANCIAL_POLICY_REQUIRED")
            terms=policy.terms(booking["total_krw"])
            digest=self.terms_digest(raw["booking_id"],terms)
            if raw["expected_terms_sha256"]!=digest:raise ContractError("FINANCIAL_TERMS_CHANGED")
            c.execute("SELECT deadline>clock_timestamp() FROM hs2_dev.bookings WHERE id=%s",(raw["booking_id"],))
            if c.fetchone()[0] is not True:raise ContractError("BOOKING_DEADLINE_EXPIRED")
            key=str(uuid4());sandbox=self.provider is None or self.provider.sandbox
            c.execute("INSERT INTO hs2_dev.financial_contracts(id,booking_id,user_id,request_id,terms,sandbox) VALUES(%s,%s,%s,%s,%s,%s)",
                (key,raw["booking_id"],uid,raw["request_id"],json.dumps(terms),sandbox))
            return self.public(c,self.row(c,key))

    def read(self,who,key,*,operator=False):
        with self.registrations.transaction() as c:
            row=self.row(c,key);self.authority(c,who,row,operator);return self.public(c,row)

    def list(self,who,*,operator=False):
        with self.registrations.transaction() as c:
            if operator:self.registrations.active(c,who);uid=who["user_id"]
            else:uid=self.bookings.details.active(c,who)
            c.execute("""SELECT f.id FROM hs2_dev.financial_contracts f JOIN hs2_dev.bookings b ON b.id=f.booking_id
                JOIN hs2_dev.registration_applications a ON a.id=b.application_id WHERE """+
                ("a.user_id=%s AND a.context_id=%s" if operator else "f.user_id=%s")+" ORDER BY f.created_at DESC LIMIT 100",
                (uid,who["context_id"]) if operator else (uid,))
            return [self.public(c,self.row(c,str(r[0]))) for r in c.fetchall()]

    def paid_cancelled(self,key):
        with self.registrations.transaction() as c:
            c.execute("SELECT 1 FROM hs2_dev.paid_booking_cancellations WHERE booking_id=%s",(key,))
            return c.fetchone() is not None

    def quote(self,who,key):
        identifier(key)
        with self.registrations.transaction() as c:
            uid=self.bookings.details.active(c,who)
            c.execute("SELECT id FROM hs2_dev.financial_contracts WHERE booking_id=%s AND user_id=%s",(key,uid))
            existing=c.fetchone()
            if existing:
                saved=self.row(c,str(existing[0]))
                return dict(booking_id=key,terms=saved["terms"],terms_sha256=self.terms_digest(key,saved["terms"]),sandbox=saved["sandbox"])
            booking=self.bookings.row(c,key,uid)
            if booking["status"]!="awaiting_payment":raise ContractError("BOOKING_STATE_CHANGED")
            policy=self.policy_for(key)
            if not isinstance(policy,ReviewedPolicy):raise ContractError("REVIEWED_FINANCIAL_POLICY_REQUIRED")
            terms=policy.terms(booking["total_krw"])
            digest=self.terms_digest(key,terms)
            return dict(booking_id=key,terms=terms,terms_sha256=digest,sandbox=self.provider is None or self.provider.sandbox)

    @staticmethod
    def terms_digest(key,terms):
        return hashlib.sha256(json.dumps(dict(booking_id=key,terms=terms),sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def receive(self,raw,signature):
        if not self.provider_ready():raise ContractError("LIVE_PAYMENT_NOT_APPROVED")
        event=self.provider.verify(raw,signature)
        # Delivery timestamps/signatures can change on legitimate retries.
        # Economic identity must remain immutable, not HTTP serialization.
        digest=hashlib.sha256(json.dumps({k:v for k,v in event.items() if k!="issued_at"},
            sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with self.registrations.transaction() as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-provider-event:{event['event_id']}",))
            # Every entry path takes the same contract lock before booking lock.
            row=self.row(c,event["contract_id"])
            if row["sandbox"] is not self.provider.sandbox:raise ContractError("PROVIDER_MODE_MISMATCH")
            c.execute("SELECT contract_id,request_hash FROM hs2_dev.financial_events WHERE id=%s",(event["event_id"],))
            prior=c.fetchone()
            if prior:
                if str(prior[0])!=event["contract_id"] or prior[1]!=digest:raise ContractError("PROVIDER_EVENT_REPLAY")
                return self.public(c,row)
            money(event["amount_krw"],positive=True)
            if event["kind"]!="capture" or event["currency"]!="KRW" or event["amount_krw"]!=row["terms"]["payable_krw"]:
                raise ContractError("PROVIDER_AMOUNT_MISMATCH")
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"hs2-finance-reference:{event['reference']}",))
            c.execute("SELECT 1 FROM hs2_dev.financial_events WHERE reference=%s OR (contract_id=%s AND kind IN('capture','late_capture'))",
                (event["reference"],event["contract_id"]))
            if c.fetchone():raise ContractError("PROVIDER_REFERENCE_REPLAY")
            who=self.consumer_for(row["user_id"])
            c.execute("SAVEPOINT financial_booking_confirm")
            try:
                self.bookings.confirm_verified(c,who,str(row["booking_id"]),dict(verified=True,booking_id=str(row["booking_id"]),
                    paid_krw=row["terms"]["stay_krw"],currency="KRW",reference=event["reference"]))
                kind="capture"
            except ContractError as error:
                c.execute("ROLLBACK TO SAVEPOINT financial_booking_confirm")
                # Preserve verified money evidence even if booking expired or
                # source/ownership changed; never revive inventory or lose money.
                kind="late_capture";reason=str(error)
            c.execute("RELEASE SAVEPOINT financial_booking_confirm")
            c.execute("INSERT INTO hs2_dev.financial_events(id,contract_id,kind,reference,request_hash,amount_krw,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (event["event_id"],event["contract_id"],kind,event["reference"],digest,event["amount_krw"],
                 json.dumps(dict(sandbox=row["sandbox"],reason=reason if kind=="late_capture" else None))))
            return self.public(c,self.row(c,event["contract_id"]))

    def cancel(self,who,key):
        with self.registrations.transaction() as c:
            row=self.row(c,key);self.authority(c,who,row,False)
            c.execute("SELECT kind FROM hs2_dev.financial_events WHERE contract_id=%s AND kind IN('capture','late_capture')",(key,))
            captured=c.fetchone()
            if not captured:raise ContractError("VERIFIED_PAYMENT_REQUIRED")
            c.execute("SELECT amount_krw FROM hs2_dev.financial_events WHERE contract_id=%s AND kind='refund_review'",(key,))
            if c.fetchone():return self.public(c,row)
            today=self.today(c)
            if captured[0]=="capture" and today>=row["check_in"]:raise ContractError("POST_CHECKIN_MANUAL_REVIEW_REQUIRED")
            if captured[0]=="capture":
                self.bookings.row(c,str(row["booking_id"]),row["user_id"])
                c.execute("INSERT INTO hs2_dev.paid_booking_cancellations VALUES(%s,%s,%s,clock_timestamp())",
                    (str(row["booking_id"]),key,row["user_id"]))
                c.execute("DELETE FROM hs2_dev.booking_slots WHERE booking_id=%s",(str(row["booking_id"]),))
                self.bookings.event(c,str(row["booking_id"]),row["user_id"],"paid-cancellation-refund-review")
            self.review_event(c,key,"refund_review",row["terms"]["payable_krw"])
            return self.public(c,row)

    @staticmethod
    def review_event(c,key,kind,amount):
        money(amount,positive=True)
        c.execute("INSERT INTO hs2_dev.financial_events(id,contract_id,kind,request_hash,amount_krw,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (str(uuid4()),key,kind,hashlib.sha256((key+kind).encode()).hexdigest(),amount,
             json.dumps(dict(execution="review_only",actual_money_executed=False))))

    def release_reviews(self,who,key):
        with self.registrations.transaction() as c:
            row=self.row(c,key);self.authority(c,who,row,True);public=self.public(c,row)
            if not public["payment_verified"] or public["booking_cancelled"]:raise ContractError("SETTLEMENT_REVIEW_NOT_ELIGIBLE")
            today=self.today(c)
            policy=row["terms"]["policy"]
            if today>=row["check_out"]+timedelta(days=policy["deposit_return_days"]) and row["terms"]["deposit_krw"]:
                self.review_event(c,key,"deposit_review",row["terms"]["deposit_krw"])
            if today>=row["check_out"]+timedelta(days=policy["settlement_days"]) and row["terms"]["host_payout_krw"]:
                self.review_event(c,key,"payout_review",row["terms"]["host_payout_krw"])
            return self.public(c,row)

    def execute_live(self,*_):
        # No approved transfer adapter exists in this development milestone.
        raise ContractError("LIVE_SETTLEMENT_NOT_APPROVED")
