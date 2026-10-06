"""Read-only aggregation of existing sync evidence. Never start or probe a job."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from data_sync_transport import SECTION_ROUTES
from public_api_client import _enabled
from quota_policy import PROVIDER_QUOTAS
from datasync_controls import controls_for, shared_names

UTC = timezone.utc
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class Item:
    name: str
    anchor: str
    keys: tuple = ()
    stage: str = ""
    counter: str = ""
    limit: int | None = None
    counter_field: str = ""
    success_key: str = ""
    days: int | None = None
    weekdays: tuple = ()
    unknown: str = ""
    heartbeat_seconds: int = 300


ITEMS = (
    Item("온비드", "dsSecOnbid", ("onbid_sync_status",),
         success_key="onbid_last_success_at", days=1),
    Item("주간 이메일", "dsSecWeeklyDigest", ("weekly_digest_manual_status",),
         unknown="수동 발송 상태와 정기 발송 이력이 분리되어 전체 발송 상태를 판정할 수 없습니다."),
    Item("건축물대장", "dsSecBrhub", ("brhub_sync_status", "brhub_rescan_status"),
         "building_registry", "building_hub_daily_calls", 10000,
         days=3, weekdays=(0, 2, 4)),
    Item("숙박신고 기반 건물 보완", "dsSecBackfillLodging",
         ("admin:backfill_lodging_registry:status",),
         counter="building_hub_daily_calls", limit=10000),
    Item("건물 좌표", "dsSecGeo", ("geocode_sync_status",), "building_geocode", days=1),
    Item("건물 사진", "dsSecPhotos",
         ("building_photos_sync_status", "admin:tourapi_image_backfill:status"),
         counter="building_photos_tourapi_calls", limit=3000),
    Item("건축정보 보완", "dsSecTitle", ("title_info_sync_status",), "title_info",
         "building_hub_daily_calls", 10000, days=1),
    Item("우편번호", "dsSecZip", ("zip_code_backfill_status",),
         counter="zip_code_backfill_status", limit=5000,
         counter_field="calls_today", days=1, heartbeat_seconds=600),
    Item("최근 실거래", "dsSecTx", ("tx_sync_status",), "transactions",
         "rtms_provider_daily_calls", 10000, days=1),
    Item("과거 실거래", "dsSecTxBackfill", ("tx_backfill_status",),
         counter="rtms_provider_daily_calls", limit=10000),
    Item("한옥·농어촌민박 실거래", "dsSecRuralHanokTrades",
         ("rural_hanok_trade_sync_status",), "rural_hanok_trades",
         limit=10000, success_key="rural_hanok_trade_last_success", days=1),
    Item("중개사 원장", "dsSecBroker", ("broker_sync_status",), "brokers",
         "broker_daily_calls", PROVIDER_QUOTAS["broker"]["total"],
         success_key="broker_last_sync", days=1),
    Item("중개사 좌표", "dsSecBrokerGeo", ("geocode_brokers_status",),
         "broker_geocode", days=1),
    Item("단지부동산", "dsSecRealty",
         ("realty_stores_sync_status", "realty_sync_status"), "realty",
         "store_api_batch_requests", 7500, "realty", days=1),
    Item("숙박 8종 검증·승인", "dsSecLodgingStaging",
         unknown="승인·검토 카드이며 단일 수집 실행 이력이 없습니다. 운영 승격 상태와는 별개입니다."),
    Item("고캠핑 사진", "dsSecCampingImages",
         ("admin:camping_image_backfill:status",),
         counter="camping_daily_calls", limit=1000),
    Item("고캠핑 웹 보강", "dsSecGocampingWeb",
         ("admin:gocamping_web_backfill:status",), "gocamping_web",
         days=7, weekdays=(6,)),
    Item("기존 숙박 직접 수집", "dsSecLodging",
         unknown="현재 상세 카드에서 사용 중지된 경로입니다. 과거 기록으로 현재 실행 상태를 판정하지 않습니다."),
    Item("건축인허가", "dsSecPermits", ("permits_sync_status",), "building_permits",
         "building_hub_daily_calls", 10000, days=3, weekdays=(1, 3, 5)),
    Item("미분류 재판정", "dsSecReclassify", ("reclassify_unclassified_status",),
         counter="building_hub_daily_calls", limit=10000),
    Item("분류 근거 점검", "dsSecClassificationProvenance",
         unknown="저장 근거 집계 화면이며 마지막 실행·성공·오류 이력이 없습니다."),
    Item("상가정보", "dsSecStores", ("stores_sync_status",), "stores",
         "store_api_batch_requests", 500, "stores", days=1),
    Item("준공 전 건물 관리", "dsSecPendingCompletion",
         unknown="건물 상태를 관리하는 목록이며 수집 작업의 실행 이력이 없습니다."),
    Item("데이터 백업", "dsSecBackup",
         unknown="다운로드 작업이며 별도 실행 상태와 마지막 성공 이력이 없습니다."),
)


def _object(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _time(value):
    """Existing naive runner timestamps use the server's UTC clock."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value, UTC)
        except (ValueError, OverflowError, OSError):
            return None
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _integer(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _error_summary(value):
    """Return only fixed, safe descriptions; never echo raw errors or credentials."""
    if not value:
        return None
    text = str(value).lower()
    if any(word in text for word in ("429", "quota", "daily cap", "한도", "daily_cap")):
        return "API 호출 한도 또는 요청 제한 오류"
    if any(word in text for word in ("403", "forbidden", "401", "auth", "인증", "권한")):
        return "API 인증 또는 접근 권한 오류"
    if any(word in text for word in ("timeout", "timed out", "시간 초과")):
        return "외부 API 응답 시간 초과"
    if any(word in text for word in ("connect", "ssl", "connection", "연결")):
        return "외부 API 또는 DB 연결 오류"
    if any(word in text for word in ("cancel", "signal", "중단", "종료 신호")):
        return "실행 중단 기록"
    return "작업 오류 기록 있음 — 상세 카드 확인"


def _counter(meta, item, now):
    if not item.counter:
        return None, item.limit
    record = meta.get(item.counter)
    if not record:
        return None, item.limit
    data = _object(record.get("value"))
    day = data.get("date") or data.get("calls_date") or data.get("last_run_date")
    # Most counters use KST; the legacy postal worker uses the server UTC date.
    today = now.date().isoformat() if item.anchor == "dsSecZip" else now.astimezone(KST).date().isoformat()
    if not day:
        return None, item.limit
    if not isinstance(day, str) or len(day) != 10:
        return None, item.limit
    try:
        recorded_day = datetime.fromisoformat(day).date()
    except ValueError:
        return None, item.limit
    if recorded_day > datetime.fromisoformat(today).date():
        return None, item.limit
    if day != today:
        return 0, item.limit
    field = item.counter_field
    value = data.get(field) if field else data.get("count", data.get("calls_today"))
    return _integer(value), item.limit


def _route(item, enabled):
    if item.anchor == "dsSecRuralHanokTrades":
        kind = "중계" if enabled.get("rtms") else "직접"
        return kind, (
            f"RHTrade(연립·다세대): {kind} / SHTrade(단독·다가구): {kind} / "
            f"LandTrade(토지): {kind}(예약 수집 제외) / NrgTrade: {kind} / "
            "분리 서비스·스위치 없이 RTMS 설정 공유; 별도 정기 실행 서버 설정 미확인; "
            "전용 상세 카드가 없어 기존 최근 실거래 카드로 이동"
        )
    routes = SECTION_ROUTES[item.anchor]
    api_routes = [route for route in routes if route[2] in ("relay", "direct")]
    if not api_routes:
        labels = {"web": "웹 수집", "file": "파일·승인", "internal": "내부 처리",
                  "disabled": "사용 중지"}
        return None, " / ".join(labels.get(route[2], "해당 없음") for route in routes)
    service, _, mode = api_routes[0]
    route = "중계" if mode == "relay" and enabled.get(service) else "직접"
    notes = []
    if len(api_routes) > 1:
        for service, label, mode in api_routes[1:]:
            kind = "중계" if mode == "relay" and enabled.get(service) else "직접"
            notes.append(f"{label}: {kind}")
    if any(r[2] == "relay" for r in api_routes):
        notes.append("현재 웹 서버 설정이며 별도 정기 실행 서버 설정은 미확인")
    return route, " / ".join(notes)


def _stage_candidates(meta, stage):
    if not stage:
        return []
    candidates = []
    for key in ("scheduled_sync_status", f"scheduled_sync_status:{stage}",
                f"scheduled_sync_status:{stage}:{stage}"):
        record = meta.get(key)
        if not record:
            continue
        root = _object(record.get("value"))
        stages = root.get("stages")
        if isinstance(stages, list):
            node = next((entry for entry in stages
                         if isinstance(entry, dict) and entry.get("key") == stage), {})
        elif isinstance(stages, dict):
            node = stages.get(stage, {})
        else:
            node = root if key.endswith(":" + stage) else {}
        if isinstance(node, dict) and node:
            candidates.append((node, record.get("updated_at")))
    return candidates


def _last_success(data):
    explicit = _time(data.get("last_success_at"))
    if explicit:
        return explicit
    if (data.get("state") in ("done", "completed", "success")
            and data.get("completed") is not False
            and not data.get("capped")
            and data.get("stop_reason") not in (
                "daily_cap", "quota", "quota_exhausted", "consecutive_errors")
            and not data.get("error")
            and not data.get("last_error")):
        # The postal worker records its terminal commit with done=True +
        # heartbeat, not finished_at. Other heartbeats are not success evidence.
        return _time(data.get("finished_at")) or (
            _time(data.get("heartbeat")) if data.get("done") is True else None)
    return None


def _next_run(item, now):
    if item.anchor == "dsSecLodging":
        return "수동(현재 사용 중지 — 일반 실행 불가)"
    if item.anchor == "dsSecOnbid":
        local = now.astimezone(KST)
        planned = local.replace(hour=6, minute=10, second=0, microsecond=0)
        if planned <= local:
            planned += timedelta(days=1)
        return f"자동({planned:%Y-%m-%d %H:%M} KST 이후 예정, 실제 작동 여부 미확인)"
    if item.anchor == "dsSecZip":
        return "자동(30분마다 조건 확인·한도 소진 시 다음 날, 정확한 다음 시각 미기록)"
    if item.anchor == "dsSecWeeklyDigest":
        return "자동(화·목 발송 대상, 다음 시각 확인불가: 예약 시간대 미기록) / 수동 테스트"
    if item.stage:
        cadence = ("월·수·금" if item.weekdays == (0, 2, 4) else
                   "화·목·토" if item.weekdays == (1, 3, 5) else
                   "매주 일" if item.weekdays == (6,) else "매일")
        clock = "02:00" if item.stage == "transactions" else "02:30"
        return f"자동({cadence} 예약 {clock}, 다음 시각 확인불가: 시간대·단계 시작 미확인)"
    return "수동(사람이 눌러야 함)"


def _state(data, updated_at, item, now, success, calls, limit):
    raw = data.get("state")
    error = _error_summary(data.get("error") or data.get("last_error"))
    stamp = (_time(data.get("heartbeat_at")) or _time(data.get("heartbeat"))
             or _time(updated_at))
    if raw == "running":
        if not stamp or (now - stamp).total_seconds() > item.heartbeat_seconds or stamp > now + timedelta(minutes=5):
            return "확인불가", "실행 중 기록의 하트비트가 끊겼습니다. 실제 실행·중단 여부를 확인해야 합니다.", error
        return "실행 중", "", error
    cap_recorded = (
        data.get("capped") is True
        or data.get("stop_reason") in ("daily_cap", "quota", "quota_exhausted", "consecutive_errors")
        or raw in ("paused", "capped", "cooldown", "waiting_quota")
        or (raw == "partial" and item.anchor == "dsSecZip")
        or (data.get("completed") is False and (
            (calls is not None and limit is not None and calls >= limit)
            or (item.stage in ("building_registry", "building_permits")
                and (_integer(data.get("calls_today")) or 0) >= 8000)))
        or (raw in ("failed", "partial") and error == "API 호출 한도 또는 요청 제한 오류")
    )
    if cap_recorded:
        return "일시중단", "한도·요청 제한 또는 연속 오류로 멈춘 기록이 있습니다.", error
    if raw in ("failed", "error"):
        return "실패", "", error or "작업 실패 기록 있음"
    if raw in ("cancelled", "interrupted", "stale", "stopped"):
        return "확인불가", "중단·응답 끊김 기록은 있지만 한도 소진·연속 오류 중단인지 확인할 수 없습니다.", error
    if raw == "partial":
        return "확인불가", "부분 처리로 기록되어 있지만 전체 완료 여부와 중단 사유를 확정할 수 없습니다.", error
    if success and item.days and now - success >= timedelta(days=item.days * 2):
        return "오래됨", "마지막 확인된 성공이 예정 주기의 2배 이상 지났습니다.", error
    if raw in ("done", "completed", "success"):
        if data.get("completed") is False:
            return "확인불가", "작업 종료 기록은 있지만 남은 대상의 중단 이유가 기록되어 있지 않습니다.", error
        if error:
            return "확인불가", "완료 상태와 오류 기록이 함께 있어 성공 여부를 확정할 수 없습니다.", error
        if success:
            return "완료", "", None
        return "확인불가", "완료 기록에 성공 시각이 없습니다.", error
    if raw in ("idle", "pending", "waiting", "deferred"):
        return "대기", "", error
    return "확인불가", "판정 가능한 실행 상태가 저장되어 있지 않습니다.", error


def _action(state, route, error):
    if state == "일시중단":
        return "중단 사유와 한도 초기화 시각 확인 — 상세 카드에서 재개 조건 확인"
    if state == "오래됨":
        return "예약 실행 기록 확인 — 상세 카드에서 갱신 필요 여부 확인"
    if state == "실패":
        if error == "API 호출 한도 또는 요청 제한 오류":
            return "API 한도·요청 제한 확인 후 재실행 검토"
        if route == "직접" and error in ("외부 API 응답 시간 초과", "외부 API 또는 DB 연결 오류"):
            return "직접 요청 실패 원인 확인 — 중계 전환 필요 여부 검토"
        return "상세 카드의 오류 확인 후 재실행 검토"
    return ""


def build_board(meta, *, now=None, enabled=None, unavailable=False):
    """Pure projection for offline tests and the one new endpoint."""
    now = _time(now) or datetime.now(UTC)
    if enabled is None:
        enabled = {service: _enabled(service) for service in ("bldg_hub", "rtms")}
    rows = []
    for item in ITEMS:
        route, route_note = _route(item, enabled)
        calls, limit = _counter(meta, item, now)
        candidates = [(_object(meta[key].get("value")), meta[key].get("updated_at"))
                      for key in item.keys if key in meta]
        candidates.extend(_stage_candidates(meta, item.stage))
        # A cadence skip must not conceal an actual collector failure.
        executed = [entry for entry in candidates
                    if entry[0].get("state") not in ("skipped", "not_selected")]
        history = candidates
        candidates = executed
        successes = [value for data, _ in candidates
                     if (value := _last_success(data)) and value <= now + timedelta(minutes=5)]
        successes.extend(value for data, _ in history if
                         (value := _time(data.get("last_success_at")))
                         and value <= now + timedelta(minutes=5))
        if item.success_key and item.success_key in meta:
            value = meta[item.success_key].get("value")
            data = _object(value)
            stamp = _time(data.get("finished_at") or data.get("last_success_at"))
            if not stamp:
                try:
                    value = json.loads(value) if isinstance(value, str) else value
                except ValueError:
                    pass
                stamp = _time(value)
            if stamp and stamp <= now + timedelta(minutes=5):
                successes.append(stamp)
        success = max(successes, default=None)
        data = {}
        if candidates:
            data, updated = max(candidates, key=lambda entry: (
                _time(entry[0].get("finished_at")) or _time(entry[0].get("started_at"))
                or _time(entry[1]) or datetime.min.replace(tzinfo=UTC)))
            state, reason, error = _state(data, updated, item, now, success, calls, limit)
            # A scheduled wrapper may exit zero after a collector stops at its cap.
            for original, stamp in candidates:
                original_time = _time(original.get("finished_at"))
                latest_time = _time(data.get("finished_at"))
                if original_time and latest_time and abs((latest_time - original_time).total_seconds()) < 60:
                    inner_state, inner_reason, inner_error = _state(
                        original, stamp, item, now, success, calls, limit)
                    if inner_state == "일시중단" and state != "실행 중":
                        state, reason, error = inner_state, inner_reason, inner_error
        else:
            if success and item.days and now - success >= timedelta(days=item.days * 2):
                state, reason, error = "오래됨", "마지막 확인된 성공이 예정 주기의 2배 이상 지났습니다.", None
            elif history:
                state, reason, error = "대기", "이번 예약 실행에서 선택되지 않았거나 실행 조건을 기다리고 있습니다.", None
            else:
                state, reason, error = "확인불가", "실행 상태 기록이 없습니다.", None
        if item.unknown or unavailable:
            state = "확인불가"
            reason = "상태 저장소를 읽지 못했습니다." if unavailable else item.unknown
            if unavailable:
                calls, success, error = None, None, None
        rows.append({
            "key": item.anchor, "name": item.name, "state": state,
            "last_success_at": success.astimezone(KST).isoformat() if success else None,
            "last_error_summary": error, "today_calls": calls, "daily_limit": limit,
            "route": route, "route_note": route_note,
            "next_run": _next_run(item, now),
            "anchor": "dsSecTx" if item.anchor == "dsSecRuralHanokTrades" else item.anchor,
            "reason": reason, "action": _action(state, route, error),
            "controls": controls_for(item.anchor),
            # Composite rows may display a newer failed sub-job while a different
            # sub-job still has a fresh running heartbeat. Warn about either.
            "shared_active": not unavailable and any(
                original.get("state") == "running"
                and _state(original, stamp, item, now, success, calls, limit)[0] == "실행 중"
                for original, stamp in executed),
            "quota_paused": state == "일시중단" and (
                error == "API 호출 한도 또는 요청 제한 오류"
                or data.get("capped") is True
                or data.get("state") == "waiting_quota"
                or data.get("stop_reason") in ("daily_cap", "quota", "quota_exhausted")
                or (data.get("completed") is False and calls is not None
                    and limit is not None and calls >= limit)
                or (item.stage in ("building_registry", "building_permits")
                    and data.get("completed") is False
                    and (_integer(data.get("calls_today")) or 0) >= 8000)),
            "quota_note": ("실거래 API 공유 한도, 이 단계의 별도 오늘 호출 횟수 미기록"
                          if item.anchor == "dsSecRuralHanokTrades" else
                          "건축HUB 서비스 전체 공유 호출" if item.counter == "building_hub_daily_calls"
                           else "실거래 서비스 전체 공유 호출" if item.counter == "rtms_provider_daily_calls"
                           else "수집 배정 한도" if item.counter == "store_api_batch_requests" else ""),
        })
    for row in rows:
        row["shared_running"] = shared_names(rows, row["key"])
    return {"ok": True, "rows": rows, "checked_at": now.astimezone(KST).isoformat(),
            "scope": "current_database_and_runtime"}


def metadata_keys():
    keys = {key for item in ITEMS for key in item.keys}
    keys.update(item.counter for item in ITEMS if item.counter)
    keys.update(item.success_key for item in ITEMS if item.success_key)
    keys.add("scheduled_sync_status")
    keys.update(f"scheduled_sync_status:{item.stage}" for item in ITEMS if item.stage)
    keys.update(f"scheduled_sync_status:{item.stage}:{item.stage}" for item in ITEMS if item.stage)
    return sorted(keys)


def read_board(get_conn, key=None):
    """One bounded SELECT; optional single-row response retains peer warnings."""
    if key is not None and key not in {i.anchor for i in ITEMS}:
        raise ValueError("Unsupported board key")
    conn = cur = None
    result = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        cur.execute("SELECT key, value, updated_at FROM app_meta WHERE key = ANY(%s)", (metadata_keys(),))
        meta = {row["key"]: row for row in cur.fetchall()}
    except Exception:
        # Do not log or send exceptions: DB/API errors may contain credentials.
        result = build_board({}, unavailable=True)
    finally:
        if conn is not None:
            for cleanup in (conn.rollback, cur.close if cur is not None else None, conn.close):
                if cleanup is not None:
                    try:
                        cleanup()
                    except Exception:
                        # A broken connection must not expose driver exceptions.
                        pass
    if result is None:
        result = build_board(meta)
    if key is not None:
        result["rows"] = [r for r in result["rows"] if r["key"] == key]
    return result
