#!/usr/bin/env python3
"""정기 공공 API 수집을 한 실행에서 순서대로 관리한다.

각 수집기의 기존 체크포인트와 UPSERT 로직은 그대로 재사용하고, 이 파일은
전체 실행 잠금·단계별 상태·하트비트·실패 후 재개만 담당한다.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from db import get_conn
from quota_policy import (
    KOREA_TZ,
    cap_for_source,
    korea_today,
    quotas_for_stage,
    regular_cap,
)


STATUS_META_KEY = "scheduled_sync_status"
SCHEDULED_EVIDENCE_META_KEY = "scheduled_sync_last_scheduled"
LOCK_ID = 918299
HEARTBEAT_SEC = 30
MAX_OUTPUT_LINES = 40
STALE_HOURS = 12
BASE_DIR = Path(__file__).resolve().parent

SECRET_ENV_NAMES = (
    "RTMS_SERVICE_KEY",
    "BLD_SERVICE_KEY",
    "BLD_INSPECTION_SERVICE_KEY",
    "STORE_INFO_SERVICE_KEY",
    "LODGING_SERVICE_KEY",
    "DATA_GO_KR_BROKER_API_KEY",
    "JUSO_API_KEY",
    "KAKAO_REST_API_KEY",
)


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    group: str
    command: tuple[str, ...]
    cadence: str
    weekdays: tuple[int, ...] | None = None
    metric_query: str | None = None
    metric_label: str | None = None
    blocking_status_keys: tuple[str, ...] = ()

    def is_due(self, weekday: int) -> bool:
        return self.weekdays is None or weekday in self.weekdays


# 건축HUB 표제부와 건축인허가는 같은 공공 API 일일 한도를 사용하므로
# 같은 날 실행하지 않는다. 월·수·금은 건축물, 화·목·토는 인허가로 나눈다.
STAGES = (
    Stage(
        "transactions",
        "실거래",
        "거래",
        ("sync_batch.py", "--months", "3", "--master-only", "--sleep", "0.8"),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM transactions",
        metric_label="거래",
        blocking_status_keys=("tx_sync_status", "tx_backfill_status"),
    ),
    Stage(
        "building_registry",
        "건축물대장",
        "건물·허가",
        ("sync_brhub.py", "--daily-cap", str(regular_cap("building_hub")), "--sleep", "1.0"),
        "월·수·금",
        weekdays=(0, 2, 4),
        metric_query="SELECT COUNT(*) AS c FROM master_buildings",
        metric_label="건물",
        blocking_status_keys=("brhub_sync_status", "brhub_rescan_status"),
    ),
    Stage(
        "building_permits",
        "준공 전 건축인허가",
        "건물·허가",
        ("sync_permits.py", "--daily-cap", str(regular_cap("building_hub")), "--sleep", "1.5"),
        "화·목·토",
        weekdays=(1, 3, 5),
        metric_query=(
            "SELECT COUNT(*) AS c FROM master_buildings "
            "WHERE source = 'permit_pipeline'"
        ),
        metric_label="준공 전 건물",
        blocking_status_keys=("permits_sync_status",),
    ),
    Stage(
        "lodging",
        "일반·생활숙박",
        "숙박",
        ("sync_lodgings.py",),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM lodging_registry",
        metric_label="영업신고",
        blocking_status_keys=("lodging_sync_status",),
    ),
    Stage(
        "camping",
        "캠핑",
        "숙박",
        ("sync_lodgings.py", "--camping"),
        "매일",
        metric_query=(
            "SELECT COUNT(*) AS c FROM lodging_registry "
            "WHERE hygiene_type = '야영장업'"
        ),
        metric_label="캠핑장",
        blocking_status_keys=("lodging_sync_status",),
    ),
    Stage(
        "rural",
        "농어촌민박",
        "숙박",
        ("sync_rural_hanok.py", "--source", "rural"),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM lodging_registry",
        metric_label="영업신고",
        blocking_status_keys=("rural_hanok_sync_status",),
    ),
    Stage(
        "hanok",
        "한옥체험업",
        "숙박",
        ("sync_rural_hanok.py", "--source", "hanok"),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM lodging_registry",
        metric_label="영업신고",
        blocking_status_keys=("rural_hanok_sync_status",),
    ),
    Stage(
        "brokers",
        "공인중개사 사무소",
        "중개·상가",
        ("sync_brokers.py",),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM broker_registry",
        metric_label="중개업소",
        blocking_status_keys=("broker_sync_status",),
    ),
    Stage(
        "broker_geocode",
        "중개업소 좌표",
        "중개·상가",
        ("geocode_brokers.py",),
        "매일",
        metric_query=(
            "SELECT COUNT(*) AS c FROM broker_registry "
            "WHERE lat IS NOT NULL AND lng IS NOT NULL"
        ),
        metric_label="좌표 확보",
        blocking_status_keys=("geocode_brokers_status",),
    ),
    Stage(
        "realty",
        "건물 내 부동산",
        "중개·상가",
        ("sync_realty_stores.py", "--daily-cap", str(regular_cap("realty_store")), "--sleep", "1.5"),
        "매일",
        metric_query=(
            "SELECT COUNT(*) AS c FROM master_buildings "
            "WHERE realty_checked_at IS NOT NULL"
        ),
        metric_label="확인 건물",
        blocking_status_keys=("realty_sync_status",),
    ),
    Stage(
        "stores",
        "건물 내 상가",
        "중개·상가",
        ("sync_stores.py", "--daily-cap", str(regular_cap("store_info")), "--sleep", "1.0"),
        "매일",
        metric_query="SELECT COUNT(*) AS c FROM building_stores",
        metric_label="입점상가",
        blocking_status_keys=("stores_sync_status",),
    ),
)

STAGE_MAP = {stage.key: stage for stage in STAGES}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _korea_weekday() -> int:
    """Return the weekday for the same KST day used by quota counters."""
    return datetime.now(KOREA_TZ).weekday()


def _redact(text: str) -> str:
    redacted = str(text)
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if value:
            redacted = redacted.replace(value, "***")
    return redacted


def _read_status(status_key: str = STATUS_META_KEY) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT value, updated_at,
                   EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age
              FROM app_meta
             WHERE key=%s
            """,
            (status_key,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return None
    try:
        status = json.loads(row["value"])
    except (TypeError, ValueError):
        return None
    status["_age_seconds"] = float(row["age"] or 0)
    return status


def _write_initial_status(status_key: str, status: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value=EXCLUDED.value, updated_at=NOW()
            """,
            (status_key, json.dumps(status, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _write_status(status_key: str, status: dict, run_id: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta
               SET value=%s, updated_at=NOW()
             WHERE key=%s
               AND (value::jsonb ->> 'run_id')=%s
            """,
            (json.dumps(status, ensure_ascii=False), status_key, run_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError("통합 배치 실행 소유권을 상실했습니다.")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _write_scheduled_evidence(run_id: str, state: str, **timestamps) -> None:
    """Persist deployment evidence separately from manual-run status."""
    evidence = {
        "run_id": run_id,
        "source": "scheduled",
        "state": state,
        "scheduled_date": korea_today(),
        **timestamps,
    }
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value=EXCLUDED.value, updated_at=NOW()
            WHERE (app_meta.value::jsonb ->> 'run_id')=%s
               OR %s='running'
        """, (
            SCHEDULED_EVIDENCE_META_KEY,
            json.dumps(evidence, ensure_ascii=False),
            run_id,
            state,
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _touch(status_key: str, run_id: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta
               SET updated_at=NOW()
             WHERE key=%s
               AND (value::jsonb ->> 'run_id')=%s
            """,
            (status_key, run_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _metric_value(stage: Stage) -> int | None:
    if not stage.metric_query:
        return None
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(stage.metric_query)
        row = cur.fetchone()
        return int(row["c"] or 0) if row else None
    except Exception:
        return None
    finally:
        cur.close()
        conn.close()


def _source_busy(stage: Stage) -> str | None:
    if not stage.blocking_status_keys:
        return None
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT key, value,
                   EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age
              FROM app_meta
             WHERE key = ANY(%s)
            """,
            (list(stage.blocking_status_keys),),
        )
        for row in cur.fetchall():
            try:
                value = json.loads(row["value"]) if row["value"] else {}
            except (TypeError, ValueError):
                continue
            if (
                value.get("state") == "running"
                and float(row["age"] or 0) < STALE_HOURS * 3600
            ):
                return row["key"]
    finally:
        cur.close()
        conn.close()
    return None


def _blank_stage(stage: Stage) -> dict:
    return {
        "key": stage.key,
        "label": stage.label,
        "group": stage.group,
        "cadence": stage.cadence,
        "state": "pending",
        "started_at": None,
        "finished_at": None,
        "last_success_at": None,
        "last_error": None,
        "metric_label": stage.metric_label,
        "before": None,
        "after": None,
        "changed": None,
        "error": None,
        "output_tail": [],
        "retryable": False,
    }


def prepare_stage_statuses(
    previous: dict | None,
    *,
    weekday: int,
    selected_stage: str | None = None,
    retry_failures_only: bool = False,
) -> dict[str, dict]:
    """새 실행 상태를 만들되 실패/중단 재개 시 완료 단계는 보존한다."""
    previous = previous or {}
    resume = previous.get("state") in {"running", "stale", "failed", "partial"}
    previous_stages = previous.get("stages") or {}
    result: dict[str, dict] = {}
    for stage in STAGES:
        old = previous_stages.get(stage.key) or {}
        old_state = old.get("state")
        if resume and old_state == "done" and selected_stage is None:
            result[stage.key] = dict(old)
            result[stage.key]["resumed"] = True
            continue
        item = _blank_stage(stage)
        # Keep a compact per-stage history when a single-stage manual run
        # replaces the outer status document.
        item["last_success_at"] = old.get("last_success_at") or (
            old.get("finished_at") if old_state == "done" else None
        )
        item["last_error"] = old.get("last_error") or old.get("error")
        if selected_stage and stage.key != selected_stage:
            item.update(
                state="skipped",
                finished_at=_now(),
                error="선택 실행 대상이 아님",
            )
        elif retry_failures_only:
            if old_state not in {"failed", "deferred", "running"}:
                item.update(
                    state="skipped",
                    finished_at=_now(),
                    error="재시도 대상이 아님",
                )
        elif old_state in {"failed", "deferred", "running"}:
            # 이전 실패·중단 단계는 재시도 날짜의 요일과 무관하게 복구한다.
            pass
        elif not selected_stage and not stage.is_due(weekday):
            item.update(
                state="skipped",
                finished_at=_now(),
                error=f"{stage.cadence} 실행 단계",
            )
        result[stage.key] = item
    return result


def stage_command(stage: Stage, source: str = "scheduled", used_by_counter: dict | None = None) -> list[str]:
    """Return collector command with the source's portion of shared quota."""
    command = list(stage.command)
    # Only collectors that already expose a CLI cap are source-aware.  Their
    # existing app_meta counter remains the shared authoritative counter.
    for policy in quotas_for_stage(stage.key):
        option = policy["cli_option"]
        if option == "--unsupported":
            continue
        # Counters are absolute daily totals.  A manual child may use only its
        # reserved increment beyond the usage observed after the global lock,
        # never the whole provider total/realtime reserve.
        cap = cap_for_source(policy, source)
        if source == "manual":
            cap = min(int(policy["total"]), int((used_by_counter or {}).get(
                policy["counter_key"], 0)) + int(policy["manual"]))
        try:
            index = command.index(option)
            command[index + 1] = str(cap)
        except ValueError:
            command.extend((option, str(cap)))
    return command


def _run_stage(stage: Stage, source: str = "scheduled") -> tuple[int, list[str]]:
    used = {}
    if source == "manual":
        conn = get_conn()
        cur = conn.cursor()
        try:
            keys = [p["counter_key"] for p in quotas_for_stage(stage.key)]
            if keys:
                cur.execute("SELECT key, value FROM app_meta WHERE key = ANY(%s)", (keys,))
                today = korea_today()
                for row in cur.fetchall():
                    try:
                        value = json.loads(row["value"] or "{}")
                        used[row["key"]] = int(value.get("count", value.get("calls_today", 0)) or 0) if value.get("date", value.get("calls_date")) == today else 0
                    except (TypeError, ValueError):
                        used[row["key"]] = 0
        finally:
            cur.close()
            conn.close()
    command = stage_command(stage, source, used)
    cmd = [sys.executable, "-u", *command]
    tail: deque[str] = deque(maxlen=MAX_OUTPUT_LINES)
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = _redact(raw_line.rstrip())
        tail.append(line)
        print(f"[{stage.key}] {line}", flush=True)
    return proc.wait(), list(tail)


def _acquire_lock():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (LOCK_ID,))
    acquired = bool(cur.fetchone()["acquired"])
    if not acquired:
        cur.close()
        conn.close()
        return None, None
    return conn, cur


def _release_lock(conn, cur) -> None:
    if conn is None or cur is None:
        return
    try:
        cur.execute("SELECT pg_advisory_unlock(%s) AS released", (LOCK_ID,))
        cur.fetchone()
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        cur.close()
        conn.close()


def _status_stage_list(stages: dict[str, dict]) -> Iterable[dict]:
    for stage in STAGES:
        yield stages[stage.key]


def run(
    *,
    status_key: str = STATUS_META_KEY,
    selected_stage: str | None = None,
    retry_failures_only: bool = False,
    source: str = "scheduled",
    run_id: str | None = None,
) -> int:
    lock_conn, lock_cur = _acquire_lock()
    if lock_conn is None:
        if run_id:
            previous = _read_status(status_key) or {}
            if previous.get("run_id") == run_id:
                previous.update(
                    state="failed", finished_at=_now(), retryable=True,
                    error="통합 배치 잠금을 얻지 못했습니다. 다른 실행이 진행 중입니다.",
                )
                _write_status(status_key, previous, run_id)
        print("[scheduled-sync] 다른 통합 배치가 실행 중입니다.", flush=True)
        return 2

    stop_heartbeat = threading.Event()
    run_id = run_id or secrets.token_hex(8)
    try:
        previous = _read_status(status_key)
        if (
            previous
            and previous.get("state") == "running"
            and previous.get("run_id") != run_id
            and float(previous.get("_age_seconds") or 0) < STALE_HOURS * 3600
        ):
            # A web/manual claim is durable before its child gets the
            # advisory lock.  A scheduled invocation must not steal it.
            print("[scheduled-sync] 이미 승인된 다른 실행이 시작을 기다리고 있습니다.", flush=True)
            return 2
        if source == "manual" and (not previous or previous.get("run_id") != run_id):
            print("[scheduled-sync] 수동 실행 소유권을 잃었습니다.", flush=True)
            return 2
        stages = prepare_stage_statuses(
            previous,
            weekday=_korea_weekday(),
            selected_stage=selected_stage,
            retry_failures_only=retry_failures_only,
        )
        status = {
            "run_id": run_id,
            "state": "running",
            "started_at": _now(),
            "finished_at": None,
            "current_stage": None,
            "schedule": "매일 02:00",
            "source": source,
            "selected_stage": selected_stage,
            "retry_failures_only": retry_failures_only,
            "stages": stages,
            "error": None,
            "retryable": False,
            "last_success_at": (previous or {}).get("last_success_at"),
        }
        if source == "manual":
            # Web endpoint has already atomically written this exact claim.
            # Fencing it here prevents a late child from taking another run's
            # status document.
            _write_status(status_key, status, run_id)
        else:
            _write_initial_status(status_key, status)
            _write_scheduled_evidence(
                run_id, "running", started_at=status["started_at"], finished_at=None
            )

        def _heartbeat():
            while not stop_heartbeat.wait(HEARTBEAT_SEC):
                try:
                    _touch(status_key, run_id)
                except Exception as exc:
                    print(
                        f"[scheduled-sync] 하트비트 저장 실패: "
                        f"{_redact(str(exc))[:200]}",
                        flush=True,
                    )

        threading.Thread(target=_heartbeat, daemon=True).start()

        for stage in STAGES:
            item = stages[stage.key]
            if item["state"] in {"done", "skipped"}:
                continue
            busy_key = _source_busy(stage)
            if busy_key:
                item.update(
                    state="deferred",
                    finished_at=_now(),
                    error=f"개별 작업({busy_key})이 이미 실행 중",
                    retryable=True,
                )
                _write_status(status_key, status, run_id)
                continue

            status["current_stage"] = stage.key
            item.update(
                state="running",
                started_at=_now(),
                before=_metric_value(stage),
                error=None,
                retryable=False,
            )
            _write_status(status_key, status, run_id)
            print(f"\n[scheduled-sync] {stage.label} 시작", flush=True)
            try:
                returncode, output_tail = _run_stage(stage, source)
            except Exception as exc:
                returncode, output_tail = 1, []
                item["error"] = _redact(str(exc))[:500]
            item["after"] = _metric_value(stage)
            if item["before"] is not None and item["after"] is not None:
                item["changed"] = item["after"] - item["before"]
            item["output_tail"] = output_tail
            item["finished_at"] = _now()
            if returncode == 0:
                item["state"] = "done"
                item["last_success_at"] = item["finished_at"]
                item["last_error"] = None
                print(f"[scheduled-sync] {stage.label} 완료", flush=True)
            else:
                item["state"] = "failed"
                item["retryable"] = True
                if not item.get("error"):
                    tail_text = "\n".join(output_tail[-8:])
                    item["error"] = (
                        f"종료 코드 {returncode}"
                        + (f": {tail_text}" if tail_text else "")
                    )[:800]
                item["last_error"] = item["error"]
                print(
                    f"[scheduled-sync] {stage.label} 실패 — 독립 단계는 계속합니다.",
                    flush=True,
                )
            _write_status(status_key, status, run_id)

        failed = [s for s in _status_stage_list(stages) if s["state"] == "failed"]
        deferred = [
            s for s in _status_stage_list(stages) if s["state"] == "deferred"
        ]
        status["current_stage"] = None
        status["finished_at"] = _now()
        if failed:
            status["state"] = "failed"
            status["retryable"] = True
            status["error"] = " · ".join(
                f"{s['label']}: {s.get('error') or '실패'}" for s in failed
            )[:1000]
        elif deferred:
            status["state"] = "partial"
            status["retryable"] = True
            status["error"] = " · ".join(
                f"{s['label']}: {s.get('error')}" for s in deferred
            )[:1000]
        else:
            status["state"] = "done"
            status["retryable"] = False
            status["error"] = None
            status["last_success_at"] = status["finished_at"]
        _write_status(status_key, status, run_id)
        if source == "scheduled":
            _write_scheduled_evidence(
                run_id,
                status["state"],
                started_at=status["started_at"],
                finished_at=status["finished_at"],
            )
        print(
            f"[scheduled-sync] 전체 완료 — state={status['state']}",
            flush=True,
        )
        return 1 if failed else 0
    finally:
        stop_heartbeat.set()
        _release_lock(lock_conn, lock_cur)


def main() -> None:
    parser = argparse.ArgumentParser(description="정기 API 통합 동기화")
    parser.add_argument("--status-key", default=STATUS_META_KEY)
    parser.add_argument("--stage", choices=tuple(STAGE_MAP))
    parser.add_argument("--source", choices=("scheduled", "manual"), default="scheduled")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="이전 실행의 실패·중단 단계만 재시도",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="실행 단계만 출력하고 종료",
    )
    args = parser.parse_args()
    if args.list:
        for stage in STAGES:
            print(
                json.dumps(
                    {
                        "key": stage.key,
                        "label": stage.label,
                        "group": stage.group,
                        "cadence": stage.cadence,
                        "command": list(stage.command),
                    },
                    ensure_ascii=False,
                )
            )
        return
    raise SystemExit(run(
        status_key=args.status_key,
        selected_stage=args.stage,
        retry_failures_only=args.retry_failures,
        source=args.source,
        run_id=args.run_id,
    ))


if __name__ == "__main__":
    main()