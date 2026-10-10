import hashlib,json,copy
from pathlib import Path
from uuid import uuid4
from hs2_data.repository import require_fixture
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier,revision
from hs2_listings.review import review
from hs2_help.content import content
from hs2_finance.policy import ReviewedPolicy
from .validation import admin,payload,text

MIGRATION=Path(__file__).parent/"migrations/001.sql"


def migrate(conn):
    require_fixture(conn);sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=15");old=c.fetchone()
        if old:
            if old[0]!=sha:raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute(MIGRATION.read_text());c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(15,%s)",(sha,))


class AdminRepository:
    def __init__(self,finance,*,resolve_admin,fallback_policy):
        if not callable(resolve_admin) or not callable(fallback_policy):raise ValueError("Trusted admin and baseline policy required")
        self.finance=finance;self.registrations=finance.registrations
        self.resolve_admin=resolve_admin;self.fallback_policy=fallback_policy

    def who(self):return admin(self.resolve_admin())

    def overview(self):
        self.who()
        with self.registrations.transaction() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            c.execute("""SELECT a.id,a.public_id,a.status,a.revision,a.payload->>'title',
                jsonb_build_object('nightly',a.payload->'nightly','weekly',a.payload->'weekly','monthly',a.payload->'monthly',
                    'calendar',(SELECT v.payload FROM hs2_dev.calendar_versions v WHERE v.application_id=a.id AND v.source_revision=a.revision ORDER BY v.version DESC LIMIT 1)),
                a.approved_until FROM hs2_dev.registration_applications a ORDER BY a.updated_at DESC LIMIT 100""")
            registrations=[dict(application_id=str(r[0]),public_id=str(r[1]) if r[1] else None,status=r[2],revision=r[3],title=r[4],rate=r[5],approved_until=r[6].isoformat() if r[6] else None) for r in c.fetchall()]
            c.execute("""SELECT b.id,b.status,s.total_krw,b.check_in,b.check_out,b.revision,
                p.booking_id IS NOT NULL,b.deadline>clock_timestamp() FROM hs2_dev.bookings b
                JOIN hs2_dev.price_snapshots s ON s.id=b.snapshot_id
                LEFT JOIN hs2_dev.paid_booking_cancellations p ON p.booking_id=b.id
                ORDER BY b.created_at DESC LIMIT 100""")
            bookings=[dict(booking_id=str(r[0]),status="cancelled_paid" if r[6] else "expired" if r[1] in {"pending_operator","awaiting_payment"} and not r[7] else r[1],total_krw=r[2],
                check_in=r[3].isoformat(),check_out=r[4].isoformat(),revision=r[5]) for r in c.fetchall()]
            c.execute("""SELECT f.id,f.booking_id,f.terms,f.sandbox,
                COALESCE((SELECT jsonb_agg(jsonb_build_object('kind',e.kind,'amount_krw',e.amount_krw,'at',e.at)) FROM hs2_dev.financial_events e WHERE e.contract_id=f.id),'[]'::jsonb)
                FROM hs2_dev.financial_contracts f ORDER BY f.created_at DESC LIMIT 100""")
            finances=[dict(contract_id=str(r[0]),booking_id=str(r[1]),terms=r[2],sandbox=r[3],events=r[4],actual_execution=False) for r in c.fetchall()]
            counts={}
            for label,table in (("registrations","registration_applications"),("bookings","bookings"),("contracts","financial_contracts"),("records","admin_records")):
                c.execute("SELECT count(*) FROM hs2_dev."+table);counts[label]=c.fetchone()[0]
            c.execute("SELECT row_to_json(a) FROM hs2_dev.admin_records a ORDER BY updated_at DESC,id LIMIT 100")
            records=[r[0] for r in c.fetchall()]
            c.execute("SELECT row_to_json(a) FROM hs2_dev.admin_record_events a ORDER BY id DESC LIMIT 50")
            events=[r[0] for r in c.fetchall()]
        return dict(registrations=registrations,bookings=bookings,finances=finances,records=records,
            audits=events,counts=counts,recent_limit=100,live_operations_approved=False,
            preserved_admin_uri="/admin",initial_platform_bps=0)

    def create(self,kind,raw):
        uid=self.who();data=payload(kind,raw);key=str(uuid4())
        with self.registrations.transaction() as c:
            if "application_id" in data:self.registrations.row(c,data["application_id"])
            c.execute("INSERT INTO hs2_dev.admin_records(id,kind,revision,status,payload,admin_id) VALUES(%s,%s,1,'draft',%s,%s)",
                (key,kind,json.dumps(data),uid))
            self.event(c,key,1,uid,"created","관리자 검토 초안")
            return self.row(c,key)

    @staticmethod
    def row(c,key):
        identifier(key);c.execute("SELECT row_to_json(a) FROM hs2_dev.admin_records a WHERE id=%s FOR UPDATE",(key,))
        r=c.fetchone()
        if not r:raise ContractError("ADMIN_RECORD_NOT_FOUND")
        return r[0]

    @staticmethod
    def event(c,key,rev,uid,action,note):
        c.execute("INSERT INTO hs2_dev.admin_record_events(record_id,revision,admin_id,action,note) VALUES(%s,%s,%s,%s,%s)",(key,rev,uid,action,note))

    def change(self,key,expected,action,note,raw=None):
        uid=self.who();revision(expected);note=text(note)
        with self.registrations.transaction() as c:
            row=self.row(c,key)
            if row["revision"]!=expected:raise ContractError("STALE_ADMIN_REVISION")
            if row["status"]=="archived":raise ContractError("ARCHIVE_TERMINAL")
            data=row["payload"]
            if action=="save":data=payload(row["kind"],raw);state="draft"
            elif action=="approve":
                if row["status"]!="draft" or raw is not None:raise ContractError("DRAFT_APPROVAL_REQUIRED")
                data=payload(row["kind"],data);state="approved"
            elif action=="archive":
                if raw is not None:raise ContractError("INVALID_ADMIN_COMMAND")
                state="archived"
            else:raise ContractError("INVALID_ADMIN_COMMAND")
            if "application_id" in data:self.registrations.row(c,data["application_id"])
            c.execute("UPDATE hs2_dev.admin_records SET revision=revision+1,status=%s,payload=%s,admin_id=%s,updated_at=clock_timestamp() WHERE id=%s",
                (state,json.dumps(data),uid,key))
            self.event(c,key,expected+1,uid,action,note)
            return self.row(c,key)

    def review_application(self,key,raw):
        uid=self.who()
        if type(raw) is not dict or set(raw)!={"revision","decision","note","rights","disclosure"}:raise ContractError("EXPLICIT_LISTING_REVIEW_REQUIRED")
        return review(self.registrations,key,uid,raw["revision"],raw["decision"],raw["note"],rights=raw["rights"],disclosure=raw["disclosure"])

    def help_content(self):
        body=copy.deepcopy(content())
        with self.registrations.transaction() as c:
            c.execute("SELECT payload FROM hs2_dev.admin_records WHERE kind='faq' AND status='approved' ORDER BY updated_at,id")
            for r in c.fetchall():
                data=r[0]
                for faq in body["faqs"]:
                    if faq["id"]==data["faq_id"]:faq.update(question=data["question"],answer=data["answer"])
        body["version"]=hashlib.sha256(json.dumps({k:v for k,v in body.items() if k!="version"},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        return body

    def policy_for(self,key):
        # Original contracts retain their stored terms; only new previews use this.
        with self.registrations.transaction() as c:
            c.execute("SELECT id,revision,payload FROM hs2_dev.admin_records WHERE kind='policy' AND status='approved' ORDER BY updated_at DESC,id DESC LIMIT 1")
            r=c.fetchone()
        if not r:return self.fallback_policy(key)
        data=r[2]
        return ReviewedPolicy(str(r[0])+":"+str(r[1]),**{k:v for k,v in data.items() if k not in {"title","note"}},reviewed=True)
