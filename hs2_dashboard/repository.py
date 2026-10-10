"""Exact scoped ledger summaries; recent records are explicitly bounded."""
from hs2_design.domain import ContractError
from hs2_listings.validation import actor

LEGACY_LINKS=[
    dict(key="sale",label="매매",href="/listings"),
    dict(key="business",label="영업권 양도",href="/listings?target=business"),
    dict(key="auction",label="공매",href="/?layer=auction"),
    dict(key="transactions",label="실거래",href="/transactions"),
    dict(key="value",label="건물가치 · 자산분석",href="/analysis"),
    dict(key="datalab",label="데이터랩 · 지도에서 보기",href="/"),
    dict(key="lodging",label="영업신고 현황",href="/?layer=lodging"),
    dict(key="partners",label="파트너 · 중개사",href="/partner")]
WORK_LINKS=dict(register="/hs2/listings/?new=1",manage="/hs2/listings/",
    calendar="/hs2/calendar/",bookings="/hs2/bookings/?view=operator",
    contracts="/hs2/finance/?view=operator",finance="/hs2/finance/?view=operator",
    chat="/mypage")


class DashboardRepository:
    def __init__(self,finance):
        self.finance=finance;self.registrations=finance.registrations

    def overview(self,who):
        actor(who)
        with self.registrations.transaction() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.registrations.active(c,who)
            params=(who["user_id"],who["context_id"])
            c.execute("""WITH scoped AS (
                SELECT a.id,a.status,EXISTS(SELECT 1 FROM hs2_dev.stay_listings l
                    JOIN hs2_dev.registration_grants g ON g.id=l.grant_id
                    WHERE l.id=a.listing_id AND l.status='published' AND g.approved
                    AND a.status='approved' AND a.reviewed_revision=a.revision
                    AND a.approved_until>clock_timestamp()) AS publicly_active
                FROM hs2_dev.registration_applications a WHERE a.user_id=%s AND a.context_id=%s
            ), booked AS (
                SELECT b.*,pc.booking_id IS NOT NULL AS paid_cancelled FROM hs2_dev.bookings b
                JOIN scoped a ON a.id=b.application_id
                LEFT JOIN hs2_dev.paid_booking_cancellations pc ON pc.booking_id=b.id
            ) SELECT (SELECT count(*) FROM scoped),(SELECT count(*) FROM scoped WHERE publicly_active),
                count(*) FILTER(WHERE status='pending_operator' AND deadline>clock_timestamp()),
                count(*) FILTER(WHERE status='awaiting_payment' AND deadline>clock_timestamp()),
                count(*) FILTER(WHERE status='confirmed' AND NOT paid_cancelled),
                count(*) FILTER(WHERE paid_cancelled) FROM booked""",params)
            counts=dict(zip(("registrations_all","published_rooms","bookings_pending_operator",
                "bookings_awaiting_payment","bookings_confirmed_active","bookings_cancelled_paid"),c.fetchone()))
            c.execute("""WITH funds AS (
                SELECT f.id,f.terms,f.sandbox,pc.booking_id IS NOT NULL AS cancelled,
                    EXISTS(SELECT 1 FROM hs2_dev.financial_events e WHERE e.contract_id=f.id AND e.kind='capture') AS captured
                FROM hs2_dev.financial_contracts f JOIN hs2_dev.bookings b ON b.id=f.booking_id
                JOIN hs2_dev.registration_applications a ON a.id=b.application_id
                LEFT JOIN hs2_dev.paid_booking_cancellations pc ON pc.booking_id=b.id
                WHERE a.user_id=%s AND a.context_id=%s
            ) SELECT
                COALESCE((SELECT sum(e.amount_krw) FROM hs2_dev.financial_events e JOIN funds f ON f.id=e.contract_id WHERE f.sandbox AND e.kind IN('capture','late_capture')),0),
                COALESCE((SELECT sum(e.amount_krw) FROM hs2_dev.financial_events e JOIN funds f ON f.id=e.contract_id WHERE NOT f.sandbox AND e.kind IN('capture','late_capture')),0),
                COALESCE(sum((terms->>'stay_krw')::bigint) FILTER(WHERE captured AND NOT cancelled),0),
                COALESCE(sum((terms->>'deposit_krw')::bigint) FILTER(WHERE captured AND NOT cancelled),0),
                COALESCE(sum((terms->>'host_payout_krw')::bigint) FILTER(WHERE captured AND NOT cancelled),0),
                COALESCE((SELECT sum(e.amount_krw) FROM hs2_dev.financial_events e JOIN funds f ON f.id=e.contract_id WHERE e.kind='refund_review'),0),
                COALESCE((SELECT sum(e.amount_krw) FROM hs2_dev.financial_events e JOIN funds f ON f.id=e.contract_id WHERE e.kind='deposit_review'),0),
                COALESCE((SELECT sum(e.amount_krw) FROM hs2_dev.financial_events e JOIN funds f ON f.id=e.contract_id WHERE e.kind='payout_review'),0)
                FROM funds""",params)
            financial=dict(zip(("sandbox_capture_krw","live_capture_krw","active_stay_krw",
                "deposit_liability_krw","host_payout_review_basis_krw","refund_review_krw","deposit_review_krw","payout_review_krw"),
                (int(v) for v in c.fetchone())))
            financial["actual_money_executed"]=False
            c.execute("""SELECT id,payload,status,revision FROM hs2_dev.registration_applications
                WHERE user_id=%s AND context_id=%s ORDER BY updated_at DESC,id LIMIT 20""",params)
            applications=[dict(application_id=str(r[0]),title=r[1].get("title") or r[1].get("public_title") or "등록 방",
                stay_kind=r[1]["stay_kind"],status=r[2],revision=r[3],
                manage_uri="/hs2/listings/?application_id="+str(r[0]),calendar_uri="/hs2/calendar/?application_id="+str(r[0])) for r in c.fetchall()]
            c.execute("""SELECT b.id,b.application_id,b.status,b.check_in,b.check_out,
                s.total_krw,pc.booking_id IS NOT NULL,b.deadline>clock_timestamp()
                FROM hs2_dev.bookings b JOIN hs2_dev.registration_applications a ON a.id=b.application_id
                JOIN hs2_dev.price_snapshots s ON s.id=b.snapshot_id
                LEFT JOIN hs2_dev.paid_booking_cancellations pc ON pc.booking_id=b.id
                WHERE a.user_id=%s AND a.context_id=%s ORDER BY b.created_at DESC,b.id LIMIT 20""",params)
            bookings=[dict(booking_id=str(r[0]),application_id=str(r[1]),
                status="cancelled_paid" if r[6] else "expired" if r[2] in {"pending_operator","awaiting_payment"} and not r[7] else r[2],
                check_in=r[3].isoformat(),check_out=r[4].isoformat(),total_krw=r[5],
                uri="/hs2/bookings/?view=operator&booking_id="+str(r[0])) for r in c.fetchall()]
            c.execute("""SELECT f.id,f.booking_id FROM hs2_dev.financial_contracts f
                JOIN hs2_dev.bookings b ON b.id=f.booking_id JOIN hs2_dev.registration_applications a ON a.id=b.application_id
                WHERE a.user_id=%s AND a.context_id=%s ORDER BY f.created_at DESC,f.id LIMIT 20""",params)
            contracts=[dict(contract_id=str(r[0]),booking_id=str(r[1]),
                uri="/hs2/finance/?view=operator&contract_id="+str(r[0])) for r in c.fetchall()]
            c.execute("""SELECT count(b.id),count(f.id) FROM hs2_dev.registration_applications a
                LEFT JOIN hs2_dev.bookings b ON b.application_id=a.id
                LEFT JOIN hs2_dev.financial_contracts f ON f.booking_id=b.id
                WHERE a.user_id=%s AND a.context_id=%s""",params)
            total_bookings,total_contracts=c.fetchone()
            return dict(scope=dict(role="operator",context_id=who["context_id"]),counts=counts,finance=financial,
                applications=dict(items=applications,total=counts["registrations_all"],has_more=counts["registrations_all"]>len(applications)),
                bookings=dict(items=bookings,total=total_bookings,has_more=total_bookings>len(bookings)),
                contracts=dict(items=contracts,total=total_contracts,has_more=total_contracts>len(contracts)),
                work_links=WORK_LINKS,legacy_links=LEGACY_LINKS,basis="scoped_ledger_not_executed_cash")
