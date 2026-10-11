"""Read-only local evidence capacity monitor; no application, DB, email or SMS."""
import argparse
import json
import math
import os
import subprocess
import sys
import time
import uuid

from cleanup_test_artifacts import ROOT, cleanup
from scheduled_artifact_cleanup import (
    POLICY_PATH, audit_lock, checked_file, policy_digest, validate_policy, write_record,
)

STATE_FILE = "capacity-status.json"


def load_status(audit_fd):
    try:
        with checked_file(audit_fd, STATE_FILE, os.O_RDONLY) as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return None
    if (not isinstance(state, dict) or state.get("version") != 1
            or state.get("condition") not in ("ok", "over-limit", "unmeasured", "check-error")
            or not isinstance(state.get("policy_digest"), str)
            or not isinstance(state.get("summary"), str)
            or type(state.get("next_due_at")) not in (int, float)
            or not math.isfinite(state["next_due_at"])
            or type(state.get("checked_at")) not in (int, float)
            or not math.isfinite(state["checked_at"]) or state["checked_at"] <= 0):
        raise ValueError("Invalid capacity status; inspect it before restarting the monitor")
    if state["policy_digest"] != policy_digest(validate_policy(state.get("policy"))):
        raise ValueError("Capacity status policy mismatch")
    return state


def save_status(audit_fd, state):
    """Atomic, fsynced replacement; interrupted writes leave the last status intact."""
    temporary = ".capacity-" + uuid.uuid4().hex
    try:
        with checked_file(audit_fd, temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR) as handle:
            write_record(handle, state)
        os.rename(temporary, STATE_FILE, src_dir_fd=audit_fd, dst_dir_fd=audit_fd)
        os.fsync(audit_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=audit_fd)
        except FileNotFoundError:
            pass


def inspect_capacity(root, policy):
    """Use actual bytes, not dry-run's projected bytes_after, for the alert."""
    limit = policy["max_mib"] * 1048576
    try:
        report = cleanup(root=root, days=policy["keep_days"], max_bytes=limit, apply=False)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        # Do not echo external command output or arbitrary exception paths.
        return {"condition": "check-error", "error_type": type(exc).__name__,
                "summary": "검사 증거 용량을 점검하지 못했습니다. 정상으로 판단하지 않습니다."}
    actual = report["bytes_before"]
    unknown = report["unmeasured_runs"]
    over = actual > limit
    condition = "unmeasured" if unknown else ("over-limit" if over else "ok")
    summary = (f"검사 증거: 측정 {actual / 1048576:.2f} MiB / 한도 {policy['max_mib']} MiB"
               f" · {'한도 초과' if over else '측정분 한도 이내'}"
               f" · 측정 불가 {len(unknown)}건"
               f" · 정리 후에도 한도 충족 불가: {'예' if report['limit_unmet'] else '아니오'}"
               " · 읽기 전용, 삭제 없음")
    return {"condition": condition, "bytes_measured": actual, "limit_bytes": limit,
            "over_limit": over, "limit_unmet": report["limit_unmet"],
            "projected_bytes_after": report["bytes_after"], "unmeasured_runs": unknown,
            "summary": summary}


def check_once(root, policy, *, respect_interval=False, now=None):
    policy = validate_policy(policy)
    now = time.time() if now is None else now
    if not math.isfinite(now) or now <= 0:
        raise ValueError("Invalid check timestamp")
    digest = policy_digest(policy)
    with audit_lock(root, lock_name=".capacity.lock") as audit_fd:
        previous = load_status(audit_fd)
        if (respect_interval and previous and previous["policy_digest"] == digest
                and now < previous["checked_at"] + policy["interval_hours"] * 3600):
            return {"status": "not-due", "current": previous}
        result = inspect_capacity(root, policy)
        same = (previous and previous["policy_digest"] == digest
                and previous["condition"] == result["condition"])
        if same:
            event = "suppressed" if result["condition"] != "ok" else "none"
        elif result["condition"] != "ok":
            event = "warning"
        elif previous and previous["condition"] != "ok":
            event = "recovered"
        else:
            event = "none"
        record = {"version": 1, "status": "checked", "policy": policy,
                  "policy_digest": digest, "checked_at": now,
                  "next_due_at": now + policy["interval_hours"] * 3600,
                  "event": event, **result}
        record["last_transition"] = (
            {"event": event, "at": now, "condition": result["condition"]}
            if event in ("warning", "recovered")
            else previous.get("last_transition") if previous else None
        )
        save_status(audit_fd, record)
        return record


def display(record):
    if record["status"] == "not-due":
        current = record["current"]
        print(f"[최근 점검 / 다음 점검 {current['next_due_at']}] {current['summary']}", flush=True)
        return
    label = {"warning": "경고", "recovered": "정상 복구", "suppressed": "동일 경고 알림 억제",
             "none": "정상"}[record["event"]]
    print(f"[{label}] {record['summary']}", flush=True)
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Check at the approved interval while awake")
    args = parser.parse_args(argv)
    try:
        policy = validate_policy(json.loads(POLICY_PATH.read_text()))
        first = True
        while True:
            if validate_policy(json.loads(POLICY_PATH.read_text())) != policy:
                raise ValueError("Policy changed; restart after reviewing the new policy")
            record = check_once(ROOT, policy, respect_interval=args.watch)
            if first or record["status"] != "not-due":
                display(record)
            first = False
            if not args.watch:
                # A missing/unmeasurable result must not appear as successful health.
                return 0 if record["condition"] == "ok" else 2
            time.sleep(60)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[점검 오류] Capacity monitor refused: {type(exc).__name__}. "
              "점검 상태 파일·잠금·정책을 확인하세요. 삭제는 수행하지 않습니다.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
