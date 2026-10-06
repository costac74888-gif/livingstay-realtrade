"""Read-only transport opinions from saved evidence, never probes or settings writes."""

from datetime import timedelta
import json

from data_sync_transport import SECTION_ROUTES
from public_api_client import ERROR_STATUS, SERVICE_PATHS, SERVICE_SWITCHES as SWITCHES

CONSECUTIVE_NOTE = "연속 횟수 미확인"
SCOPE_NOTE = (
    "이 웹 서버의 로컬 전송 기록입니다. 정기 실행 서버 설정은 별도 확인 필요. "
    "서비스 공유 관측이며 개별 수집·DB 반영 성공을 보장하지 않습니다. "
    "오류 시각 미기록은 판단불가이며 중계 오류 건수에 포함하지 않습니다."
)


def safe_snapshot(raw, now, enabled):
    """Explicit allowlist: discard addresses, tokens, unknown codes and invalid dates."""
    from datasync_board import _time
    result = {}
    for service in SERVICE_PATHS:
        node = raw.get(service) if isinstance(raw, dict) else None
        node = node if isinstance(node, dict) else {}
        # Settings are known even if the local history read failed. Do not
        # misreport a missing telemetry snapshot as relay OFF.
        safe = {"enabled": enabled.get(service) is True}
        for field in ("last_success_at", "last_error_at"):
            stamp = _time(node.get(field))
            safe[field] = (stamp.isoformat() if stamp
                           and stamp <= now + timedelta(minutes=5) else None)
        code = node.get("last_error_code")
        safe["last_error_code"] = code if isinstance(code, str) and code in ERROR_STATUS else None
        result[service] = safe
    return result


def _guidance(switch, label):
    return [
        "지금 상태: 직접 연결. 저장된 최근 실패 유형을 참고하되, 당시 호출 경로·실패 서비스는 별도 확인하세요. DB 오류는 중계로 해결되지 않습니다.",
        f"전환 전 확인: 관리자 ‘중계 상태’에서 {label}의 웹 서버 관측을 확인하고, 해당 서비스가 중계 서버에 등록되어 있는지 별도로 확인하세요.",
        f"전환 방법(사람이 직접): Replit Secrets에서 {switch} 값을 1로 설정합니다. 공통 RELAY_ENABLED도 1이어야 합니다. 웹 앱 재시작/재게시 → 예약 배포(Scheduled deployment)도 Secrets 확인 후 별도로 재게시 → 보드에서 ‘중계 사용 중’을 확인합니다. 기록이 없으면 ‘판단불가’일 수 있으며 이 화면은 시험 호출하지 않습니다.",
        f"되돌리는 방법: {switch} 값을 비우거나 0으로 되돌린 뒤 웹 앱을 재시작/재게시하고, 예약 배포도 별도로 확인·재게시합니다.",
        "주의: 자동으로 직접 호출로 되돌아가는 기능은 없습니다. 중계 서버가 멈추면 해당 수집은 실패합니다. 이 패널은 안내만 제공하며 설정을 변경하지 않습니다.",
    ]


def _latest_evidence(item, meta, now):
    """Select executed records, not wrapper skips; stale retained errors are not new failures."""
    from datasync_board import _object, _stage_candidates, _time, _error_summary, _last_success
    entries = [(_object(meta[k].get("value")), meta[k].get("updated_at"))
               for k in item.keys if k in meta]
    entries.extend(_stage_candidates(meta, item.stage))
    known_states = {"running", "done", "completed", "success", "failed", "error",
                    "paused", "capped", "cooldown", "partial", "waiting_quota",
                    "pending", "idle", "stopped", "cancelled", "aborted"}
    executed = [(d, at) for d, at in entries
                if d.get("state") not in ("skipped", "not_selected", "deferred")
                and ((isinstance(d.get("state"), str) and d["state"] in known_states)
                     or d.get("error") or d.get("last_error"))]
    if not executed:
        return False, None, None

    def stamp(entry):
        d, at = entry
        return _time(d.get("finished_at")) or _time(d.get("started_at")) or _time(at)

    # An undated error cannot outrank a dated execution.
    latest = max(executed, key=lambda entry: stamp(entry).timestamp() if stamp(entry) else float("-inf"))
    data = latest[0]
    at = stamp(latest)
    if not at or at > now + timedelta(minutes=5):
        return False, None, None
    summary = _error_summary(data.get("error") or data.get("last_error"))
    if data.get("state") in ("done", "completed", "success") and data.get("completed") is not False:
        # Scheduled wrappers can retain last_error from older runs.
        if not data.get("error") and not data.get("capped"):
            summary = None
    success_times = [s for d, _ in executed if (s := _last_success(d)) and s <= now]
    if item.success_key and item.success_key in meta:
        value = meta[item.success_key].get("value")
        node = _object(value)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        success = _time(node.get("last_success_at") or node.get("finished_at")) or _time(value)
        if success and success <= now:
            success_times.append(success)
    if summary and success_times and max(success_times) > at:
        summary = None
    # These statuses store total errors/stop reasons, not a reliable consecutive count.
    return True, summary, at


def advice_for(item, row, meta, snapshot, now, unavailable=False):
    routes = (("rtms", "실거래", "relay"),) if item.anchor == "dsSecRuralHanokTrades" else SECTION_ROUTES[item.anchor]
    api_routes = [r for r in routes if r[2] in ("relay", "direct")]
    service, label, mode = api_routes[0] if api_routes else (None, None, None)
    supported = mode == "relay" and service in SERVICE_PATHS
    evidence, failure, _ = _latest_evidence(item, meta, now)
    if evidence and row.get("quota_paused"):
        failure = "API 호출 한도 또는 요청 제한 오류"
    result = {
        "verdict": "판단불가", "reason": "실행·전송 판정 근거 기록이 없습니다.",
        "service": service, "service_label": label,
        "switch_name": SWITCHES.get(service) if supported else None,
        "failure_summary": failure, "consecutive_note": CONSECUTIVE_NOTE, "steps": [],
    }
    if unavailable:
        result["reason"] = "상태 저장소를 읽지 못해 연결 판단 근거를 확인할 수 없습니다."
        return result
    if item.unknown or not api_routes:
        result["reason"] = item.unknown or "외부 API 수집 중계 판정 대상이 아닙니다."
        return result
    if row["route"] == "중계":
        from datasync_board import _time
        status = snapshot.get(service, {})
        success = _time(status.get("last_success_at"))
        error_at = _time(status.get("last_error_at"))
        error = status.get("last_error_code")
        if error and not error_at:
            result["reason"] = "중계 오류 시각 미기록으로 마지막 성공과 선후 비교 불가"
        elif error and (not success or error_at > success):
            result.update(verdict="중계 사용 중 - 오류 있음",
                          reason=(f"마지막 2xx보다 최근 중계 오류: {error}" if success
                                  else f"중계 오류 기록: {error} — 마지막 2xx 기록 없음"))
        elif success:
            result.update(verdict="중계 사용 중", reason="중계 전송 성공 기록이 있고 더 최근의 중계 오류 기록은 없습니다.")
        else:
            result["reason"] = "중계 설정은 사용 중이지만 로컬 전송 성공·오류 기록이 없습니다."
        if error in ("RELAY_QUOTA", "RELAY_AUTH", "RELAY_FORBIDDEN"):
            result["reason"] += " · " + _cause_hint(
                "API 호출 한도 또는 요청 제한 오류" if error == "RELAY_QUOTA"
                else "API 인증 또는 접근 권한 오류")
        return result
    if not evidence:
        return result
    hint = _cause_hint(failure)
    if not supported:
        result.update(verdict="중계 미지원",
                      reason="코드상 중계 미지원: 전환하려면 먼저 중계 서버와 클라이언트 작업이 필요합니다."
                      + (f" · {hint}" if failure else ""))
    elif failure in ("외부 API 응답 시간 초과", "외부 API 또는 DB 연결 오류"):
        result.update(verdict="중계 전환 검토",
                      reason="현재 직접 연결이며 최근 저장된 수집 오류는 " + failure + "입니다. 접속 문제 가능성을 검토하세요.",
                      steps=_guidance(SWITCHES[service], label))
    else:
        result.update(verdict="직접 유지",
                      reason=hint if failure else "최근 실행 기록에 접속 실패 근거가 없습니다.")
    return result


def _cause_hint(failure):
    if failure == "API 호출 한도 또는 요청 제한 오류":
        return "중계로 해결되지 않습니다. 한도는 서비스 전체가 공유합니다. 내일 초기화 또는 호출량 조정"
    if failure == "API 인증 또는 접근 권한 오류":
        return "키 또는 승인 상태 확인. 중계 전환으로 해결되지 않을 수 있습니다"
    if failure == "외부 API 또는 DB 연결 오류":
        return "접속 문제 가능성을 검토하되 DB 연결 오류는 중계로 해결되지 않습니다."
    if failure == "외부 API 응답 시간 초과":
        return "접속 문제 가능성이 있는 시간 초과 기록입니다."
    return "최근 오류는 접속 문제로 확인되지 않았습니다. 상세 카드에서 확인하세요."


def enrich_board(result, items, meta, now, relay_snapshot=None, unavailable=False, enabled=None):
    snapshot = safe_snapshot(relay_snapshot, now, enabled or {})
    by_key = {item.anchor: item for item in items}
    for row in result["rows"]:
        row["transport_advice"] = advice_for(
            by_key[row["key"]], row, meta, snapshot, now, unavailable)
    result["relay_observation"] = {"services": snapshot, "scope_note": SCOPE_NOTE}
    return result
