# -*- coding: utf-8 -*-
"""Shared, privacy-minimised data source for the administrator action centre."""
import html
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from email_util import send_email
from urllib.parse import urlparse

KST = ZoneInfo("Asia/Seoul")
_COMPANY_EMAIL_RE = re.compile(r"문의\s+([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.I)
_DELIVERY_LOCK_KEY = 1_184_920_671
_DEEP_LINKS = {
    "application": "/admin#members",
    "user": "/admin#members",
    "ota_request": "/admin#ota-requests",
    "building_request": "/admin#requests",
    "buy_request": "/admin#requests",
    "presale_application": "/admin#presale",
    "listing_request": "/admin#listings",
    "unassigned_broker_listing": "/admin#listings",
    "bug_report": "/admin#bug-reports",
    "sync_failure": "/admin#datasync",
}
_CATEGORY_LABELS = {
    "approval_required": "승인 필요",
    "new_registration": "신규 접수",
    "urgent": "긴급",
    "delayed": "지연",
}


def company_email():
    """Read the visible company contact from index.html; no duplicate setting exists."""
    index = Path(__file__).with_name("static") / "index.html"
    try:
        matches = _COMPANY_EMAIL_RE.findall(index.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"회사 문의 이메일 원본을 읽을 수 없습니다: {exc}") from exc
    unique = list(dict.fromkeys(value.strip() for value in matches))
    if len(unique) != 1:
        raise RuntimeError("static/index.html의 회사 문의 이메일을 하나로 확인할 수 없습니다.")
    return unique[0]


def canonical_origin():
    """Use only a validated configured public origin, never request headers."""
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(configured)
    if (parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and parsed.path in ("", "/")
            and not parsed.query and not parsed.fragment):
        return configured
    return "https://homenstay.com"


def _item(kind, row, label, priority="normal", requires_approval=False):
    return {
        "kind": kind, "id": int(row["id"]), "label": label,
        "title": label, "created_at": row.get("created_at"),
        "priority": priority, "requires_approval": requires_approval,
        "deep_link": _DEEP_LINKS[kind],
    }


def _sort_timestamp(value):
    """Normalise mixed TIMESTAMP/TIMESTAMPTZ source values for deterministic feeds."""
    if not isinstance(value, datetime):
        return float("-inf")
    if value.tzinfo is None:
        return value.replace(tzinfo=KST).timestamp()
    return value.timestamp()


def action_items(cur, limit=500):
    """Read only operational metadata. Never select contact details or report text."""
    groups = {key: [] for key in ("approval_required", "new_registration", "urgent", "delayed")}

    def add(category, value):
        groups[category].append(value)

    cur.execute("""SELECT id, submitted_at AS created_at, applicant_type FROM applications
                   WHERE status = 'submitted' ORDER BY submitted_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        item = _item("application", r, f"파트너 신청 #{r['id']}", "high", True)
        add("approval_required", item); add("new_registration", item)

    cur.execute("""SELECT id, submitted_at AS created_at FROM booking_url_requests WHERE status = 'pending'
                   ORDER BY submitted_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        add("approval_required", _item("ota_request", r, f"OTA 링크 신청 #{r['id']}", "high", True))

    cur.execute("""SELECT id, created_at, status, request_type FROM building_requests
                   WHERE status IN ('pending', 'name_review') ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        review = r["status"] == "name_review"
        item = _item("building_request", r, f"{'건물명 검토' if review else '건물 요청'} #{r['id']}",
                     "high" if review else "normal", True)
        add("approval_required", item)
        if not review:
            add("new_registration", item)

    cur.execute("""SELECT id, created_at, status FROM presale_applications
                   WHERE status IN ('submitted', 'reviewing') ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        add("approval_required", _item("presale_application", r, f"분양 신청 #{r['id']}",
                                        "high" if r["status"] == "submitted" else "normal", True))

    cur.execute("""SELECT id, created_at, deal_mode, routed_agent_id FROM listing_requests
                   WHERE status = 'submitted' ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        mode = r.get("deal_mode") or "broker"
        unassigned = mode == "broker" and r.get("routed_agent_id") is None
        item = _item("listing_request", r, f"{'직거래' if mode == 'direct' else '중개'} 매물 요청 #{r['id']}",
                     "urgent" if unassigned else "normal", False)
        add("new_registration", item)
        if unassigned:
            add("urgent", item)

    cur.execute("""SELECT id, created_at, status FROM buy_requests
                   WHERE status IN ('pending', 'submitted') ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        add("new_registration", _item("buy_request", r, f"매수 요청 #{r['id']}", "normal", False))

    cur.execute("""SELECT id, created_at, severity FROM bug_reports WHERE status <> 'resolved'
                   ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        item = _item("bug_report", r, f"오류 신고 #{r['id']}",
                     "urgent" if r["severity"] == "blocking" else "normal", False)
        add("urgent" if r["severity"] == "blocking" else "new_registration", item)

    cur.execute("""SELECT id, created_at FROM users
                   WHERE created_at >= NOW() - INTERVAL '7 days'
                   AND COALESCE(status, 'active') <> 'withdrawn'
                   ORDER BY created_at DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        add("new_registration", _item("user", r, f"신규 회원 #{r['id']}", "normal", False))

    cur.execute("""SELECT id, COALESCE(finished_at, started_at) AS created_at FROM sync_log
                   WHERE LOWER(COALESCE(status, '')) IN ('failed', 'error')
                   ORDER BY COALESCE(finished_at, started_at) DESC LIMIT %s""", (limit,))
    for r in cur.fetchall():
        add("urgent", _item("sync_failure", r, f"동기화 실패 #{r['id']}", "high", False))

    # Outstanding work older than three days is a separate operational signal.
    # Do this from the live source timestamps instead of keeping a second state.
    seen_delayed = set()
    for values in groups.values():
        for value in values:
            marker = (value["kind"], value["id"])
            created = value.get("created_at")
            if marker in seen_delayed or not isinstance(created, datetime):
                continue
            now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
            if (now - created).total_seconds() >= 3 * 24 * 60 * 60:
                groups["delayed"].append(value)
                seen_delayed.add(marker)

    # An item may belong to multiple views, but each view itself is deterministic.
    for values in groups.values():
        values.sort(
            key=lambda value: (value["priority"] != "urgent", -_sort_timestamp(value["created_at"])),
        )
    return groups


def action_payload(cur):
    groups = action_items(cur)
    # Categories deliberately overlap. The flat feed does not: it is the UI's
    # canonical actionable total and prevents badges/digests from double-counting.
    unique = {}
    for rows in groups.values():
        for item in rows:
            unique.setdefault((item["kind"], item["id"]), item)
    for category, rows in groups.items():
        for item in rows:
            unique[(item["kind"], item["id"])].setdefault("categories", []).append(category)
    priority_rank = {"urgent": 0, "high": 1, "normal": 2}
    items = sorted(
        unique.values(),
        key=lambda value: (
            priority_rank.get(value["priority"], 9),
            -_sort_timestamp(value["created_at"]),
        ),
        reverse=False,
    )
    counts = {name: len(rows) for name, rows in groups.items()}
    counts["total"] = len(items)
    return {
        "ok": True,
        "generated_at": datetime.now(KST).isoformat(),
        "recipient_email": company_email(),
        "items": items,
        "categories": groups,
        "counts": counts,
    }


def enqueue_immediate(cur, kind, item_id, label):
    """Insert durable alert within its source transaction, idempotently."""
    key = f"admin-immediate:{kind}:{item_id}"
    cur.execute("""INSERT INTO admin_notification_deliveries
                     (channel, idempotency_key, status, source_kind, source_id, label, next_attempt_at)
                   VALUES ('immediate', %s, 'pending', %s, %s, %s, NOW())
                   ON CONFLICT (channel, idempotency_key) DO NOTHING RETURNING id""",
                (key, kind, item_id, label[:500]))
    return bool(cur.fetchone())


def dispatch_pending_immediate(conn, cur, limit=20, source_kind=None):
    """Lease due rows, send outside the lease transaction, and retain bounded retries."""
    source_filter = "AND source_kind = %s" if source_kind else ""
    params = [source_kind, limit] if source_kind else [limit]
    cur.execute(f"""WITH due AS (
                     SELECT id FROM admin_notification_deliveries
                     WHERE channel='immediate' AND attempts < 5
                       AND (status='pending' OR (status='attempting'
                            AND attempting_at < NOW() - INTERVAL '15 minutes'))
                       AND next_attempt_at <= NOW()
                       {source_filter}
                     ORDER BY next_attempt_at, id FOR UPDATE SKIP LOCKED LIMIT %s
                   )
                   UPDATE admin_notification_deliveries d SET status='attempting',
                     attempting_at=NOW(), attempts=d.attempts+1, attempted_at=NOW()
                   FROM due WHERE d.id=due.id
                   RETURNING d.id, d.idempotency_key, d.source_kind, d.label""", params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.commit()
    failures = 0
    for row in rows:
        origin, link = canonical_origin(), _DEEP_LINKS.get(row["source_kind"], "/admin")
        body = (f"<p>관리자 즉시 확인이 필요한 항목입니다.</p><p>{html.escape(row.get('label') or '', quote=True)}</p>"
                f"<p><a href=\"{html.escape(origin + link, quote=True)}\">관리자 화면 열기</a></p>")
        ok, message, outcome = send_email(company_email(), "[홈앤스테이] 관리자 즉시 확인", body,
                                          idempotency_key=row["idempotency_key"], detailed=True)
        if not ok:
            failures += 1
        cur.execute("""UPDATE admin_notification_deliveries
                       SET status=%s, outcome=%s, provider_message=%s,
                           sent_at=CASE WHEN %s THEN NOW() ELSE NULL END,
                           next_attempt_at=CASE WHEN %s THEN NOW() ELSE NOW() + (LEAST(attempts, 5) * INTERVAL '5 minutes') END
                       WHERE id=%s""",
                    ("sent" if ok else "pending", outcome, str(message)[:1000], ok, ok, row["id"]))
        conn.commit()
    return len(rows), failures


def send_daily_digest(conn, cur):
    """Called by the cron script. A transaction-level advisory lock prevents overlap."""
    cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS locked", (_DELIVERY_LOCK_KEY,))
    if not cur.fetchone()["locked"]:
        conn.rollback()
        return False, "another digest is running"
    payload = action_payload(cur)
    routine_items = [
        item for item in payload["items"]
        if "urgent" not in item["categories"]
        and (item["kind"] != "user" or _sort_timestamp(item["created_at"]) >=
             datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - 86400)
        and (item["kind"] != "user" or _sort_timestamp(item["created_at"]) <
             datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    ]
    total = len(routine_items)
    if not total:
        conn.commit()
        return False, "no actionable items"
    day = datetime.now(KST).date().isoformat()
    key = f"admin-digest:{day}"
    cur.execute("""INSERT INTO admin_notification_deliveries
                   (channel, idempotency_key, status, source_kind, label)
                   VALUES ('daily_digest', %s, 'pending', 'digest', '일일 요약')
                   ON CONFLICT (channel, idempotency_key) DO NOTHING RETURNING id""", (key,))
    if not cur.fetchone():
        conn.commit()
        return False, "already delivered"
    conn.commit()
    routine_counts = {
        name: sum(1 for item in routine_items if name in item["categories"])
        for name in _CATEGORY_LABELS
    }
    lines = "".join(f"<li>{html.escape(_CATEGORY_LABELS[name])}: {count}건</li>"
                    for name, count in routine_counts.items() if count)
    origin = canonical_origin()
    body = (
        f"<p>관리자 액션 센터 일일 요약 ({day}, KST)</p>"
        f"<p>중복 제외 처리 대상: {total}건</p><ul>{lines}</ul>"
        f"<p><a href=\"{html.escape(origin + '/admin', quote=True)}\">관리자 화면 열기</a></p>"
    )
    ok, message, _ = send_email(company_email(), "[홈앤스테이] 관리자 액션 센터 일일 요약", body,
                                idempotency_key=key, detailed=True)
    cur.execute("""UPDATE admin_notification_deliveries SET status=%s, provider_message=%s,
                   sent_at=CASE WHEN %s THEN NOW() ELSE NULL END, attempted_at=NOW()
                   WHERE channel='daily_digest' AND idempotency_key=%s""",
                ("sent" if ok else "failed", str(message)[:1000], ok, key))
    conn.commit()
    return ok, message