"""Allowlisted adapters to existing admin runners, never new collection logic."""

from contextlib import contextmanager
from datetime import datetime, timezone
import zlib

RUN_HANDLERS = {
    "dsSecOnbid": "auction_admin_run",
    "dsSecBackfillLodging": "admin_backfill_lodging_run",
    "dsSecGeo": "admin_geocode_run",
    "dsSecTitle": "admin_title_info_run",
    "dsSecTx": "admin_sync_run",
    "dsSecTxBackfill": "admin_backfill_run",
    "dsSecBroker": "admin_broker_sync_run",
    "dsSecBrokerGeo": "admin_geocode_brokers_run",
    "dsSecRealty": "admin_realty_sync_run",
    "dsSecCampingImages": "admin_camping_image_backfill_run",
    "dsSecGocampingWeb": "admin_gocamping_web_backfill_run",
    "dsSecPermits": "admin_permits_sync_run",
    "dsSecReclassify": "admin_reclassify_unclassified_run",
    "dsSecStores": "admin_stores_sync_run",
}
NO_RUN_REASONS = {
    "dsSecWeeklyDigest": "대표 테스트 승인·메일 발송은 상세 카드에서 진행",
    "dsSecBrhub": "전국 수집·과거 구간 재수집 중 대상은 상세 카드에서 선택",
    "dsSecPhotos": "목록 사전조회·사진 수집 중 대상은 상세 카드에서 선택",
    "dsSecZip": "자동 처리 전용, 기존 실행 API 없음",
    "dsSecLodgingStaging": "별도 검증·승인 절차",
    "dsSecLodging": "기존 직접 수집 경로 사용 중지",
    "dsSecClassificationProvenance": "점검·복원 절차이며 수집 작업 아님",
    "dsSecPendingCompletion": "건물 목록 관리이며 수집 작업 아님",
    "dsSecBackup": "다운로드 기능이며 수집 작업 아님",
    "dsSecRuralHanokTrades": "기존 예약 단계 경로는 공유 API 실행도 차단하여 보드 재실행 연결 제외",
}
SHARED_APIS = (
    frozenset({"dsSecBrhub", "dsSecTitle", "dsSecPermits",
               "dsSecReclassify", "dsSecBackfillLodging"}),
    frozenset({"dsSecTx", "dsSecTxBackfill", "dsSecRuralHanokTrades"}),
)
RUN_STATES = frozenset({"실패", "오래됨", "일시중단", "대기"})


def controls_for(key):
    supported = key in RUN_HANDLERS
    return {
        "run": supported, "stop": False,
        "reason": "" if supported else NO_RUN_REASONS.get(key, "허용되지 않은 항목"),
        "stop_reason": "기존 중지·취소 API 없음",
    }


def shared_names(rows, key):
    group = next((group for group in SHARED_APIS if key in group), ())
    return [r["name"] for r in rows
            if r["key"] in group and r["key"] != key
            and (r.get("shared_active") is True or r["state"] == "실행 중")]


class ActionRejected(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_action(body):
    if not isinstance(body, dict) or set(body) != {"key", "action"}:
        raise ActionRejected(400, "항목 키와 행동만 지정해 주세요.")
    key, action = body["key"], body["action"]
    if not isinstance(key, str) or key not in RUN_HANDLERS:
        raise ActionRejected(400, "이 항목은 한눈에 보기 실행을 지원하지 않습니다.")
    # No existing collector has a stop API. Do not invent kill/cancel behavior.
    if action != "run":
        raise ActionRejected(400, "기존 중지 경로가 없어 중지를 지원하지 않습니다.")
    return key


@contextmanager
def action_guard(get_conn, key, stage_lock_id=None):
    """Serialize board requests; retain original runners' own atomic guards."""
    from datasync_board import ITEMS, _object, _stage_candidates, build_board, metadata_keys
    item = next(i for i in ITEMS if i.anchor == key)
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        lock_ids = [50_000_000_000 + zlib.crc32(key.encode("ascii"))]
        if stage_lock_id is not None:
            lock_ids.append(stage_lock_id)
        for lock_id in lock_ids:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", (lock_id,))
            if not cur.fetchone()["acquired"]:
                raise ActionRejected(409, "이미 실행 중입니다")
        cur.execute("SELECT key,value,updated_at FROM app_meta WHERE key=ANY(%s)",
                    (metadata_keys(),))
        meta = {r["key"]: r for r in cur.fetchall()}
        direct = [_object(meta[k].get("value")) for k in item.keys if k in meta]
        staged = [d for d, _ in _stage_candidates(meta, item.stage)]
        # Even a stale running claim cannot be revived from an opaque board row.
        if any(d.get("state") == "running" for d in direct + staged):
            raise ActionRejected(409, "이미 실행 중입니다")
        current = next(r for r in build_board(meta)["rows"] if r["key"] == key)
        if current["state"] not in RUN_STATES:
            raise ActionRejected(409, "상태를 확정할 수 없거나 재실행 대상이 아닙니다. 상세 카드에서 확인해 주세요.")
        yield
    finally:
        for cleanup in (conn.rollback if conn is not None else None,
                        cur.close if cur is not None else None,
                        conn.close if conn is not None else None):
            if cleanup is not None:
                try:
                    cleanup()
                except Exception:
                    pass


def dispatch(body, *, get_conn, invoke, stage_lock_id=None):
    """Only select static registered handlers. Do not forward original error text."""
    key = validate_action(body)
    try:
        with action_guard(get_conn, key, stage_lock_id):
            response = invoke(RUN_HANDLERS[key])
            code = response.status_code
            payload = response.get_json(silent=True)
            if code == 409:
                return {"ok": False, "message": "이미 실행 중입니다"}, 409
            if code == 429:
                return {"ok": False, "message": "호출 한도·요청 제한 또는 기존 재실행 대기 시간에 걸렸습니다. 상세 카드에서 확인해 주세요."}, 429
            if 200 <= code < 300 and isinstance(payload, dict) and payload.get("ok") is True:
                return {"ok": True, "message": "기존 실행 경로에서 실행 요청을 접수했습니다."}, code
            return {"ok": False, "message": "기존 실행 경로에서 요청을 처리하지 못했습니다. 상세 카드에서 확인해 주세요."}, code if 400 <= code <= 599 else 502
    except ActionRejected:
        raise
    except Exception:
        # Driver / spawn / decorated handler errors may contain secrets.
        return {"ok": False, "message": "실행 상태 확인 또는 요청 처리에 실패했습니다. 상세 카드에서 확인해 주세요."}, 503


def audit(logger, admin_id, key, action, code):
    """Use the existing application logger, no new tables and no raw payloads."""
    # Flask's existing default threshold is WARNING; INFO would silently lose
    # required audit records. Keep global logging configuration unchanged.
    logger.warning("[datasync-board-audit] admin_id=%s at=%s item=%s action=%s http=%s",
                   admin_id, datetime.now(timezone.utc).isoformat(),
                   key if key in RUN_HANDLERS or key in NO_RUN_REASONS else "unsupported",
                   action if action in ("run", "stop") else "unsupported", code)
