"""User Phase 2 ledger; does not start/reorder/complete the native 18 stages."""
import json
from pathlib import Path

from . import core

PLAN = core.DOC / "phases.json"


def configuration():
    _, registry = core.configuration()
    plan = core.load(PLAN)
    if plan["user_phase"] != 2 or plan["stop_after_phase"] != 2:
        raise core.GateError("Only user Phase 2 is authorized")
    checks = [x["check"] for x in plan["acceptance"]]
    if (len(checks) != 2 or set(checks) != {"phase2-data-contracts", "phase2-gate-contracts"}
            or any(k not in registry or registry[k]["role"] != "acceptance" for k in checks)):
        raise core.GateError("Missing Phase 2 acceptance")
    original = json.loads(core.git("show", plan["phase1_checkpoint"] + ":docs/home_stay_2/state.json"))
    state = core.load(core.STATE)
    if state["stages"]["1"] != original["stages"]["1"]:
        raise core.GateError("Phase 1 completion receipt changed")
    original_plan = json.loads(core.git("show", plan["phase1_checkpoint"] + ":docs/home_stay_2/stages.json"))
    if core.load(core.PLAN) != original_plan:
        raise core.GateError("Native stages/criteria/manual gates changed")
    if any(v["status"] != "PENDING" for k,v in state["stages"].items() if k != "1"):
        raise core.GateError("Unrequested native stage was started")
    return plan, registry


def render(state, event, **details):
    core.record(state, event, **details)
    row = state["user_phases"]["2"]
    old = (core.DOC / "STATUS.md").read_text()
    header = (
        "# 현재 사용자 Phase 2 — " + row["status"] + "\n\n"
        "- 범위: 격리 PostgreSQL 데이터 확장. 기존 18단계의 2단계(인증)와 별도.\n"
        "- Phase 1: COMPLETE 기록 보존. 저장소 2~18단계: PENDING.\n"
        "- 완료 범위: " + row.get("completed_scope", "아직 구현·검증 중") + "\n"
        "- 검사: " + row.get("test_summary", "검사 예정") + "\n"
        "- 원격 저장: " + row.get("remote", {}).get("status", "NOT_PUSHED") + "\n"
        "- 차단 사유: " + row.get("reason", "없음") + "\n"
        "- 다음 작업: " + row["next_action"] + "\n\n---\n\n"
    )
    (core.DOC / "STATUS.md").write_text(header + old)


def valid_receipt(row, fingerprint, expected_ids):
    receipt = row.get("verification", {})
    results = receipt.get("results", [])
    if (row.get("status") != "PASS" or receipt.get("fingerprint") != fingerprint
            or sorted(r.get("id","") for r in results) != sorted(expected_ids)
            or not results or any(r.get("status") != "PASS" or r.get("exit_code") != 0 for r in results)):
        raise core.GateError("Full current-byte registry PASS required")


def verify():
    with core.lock():
        state = core.load(core.STATE)
        row = state["user_phases"]["2"]
        if row["status"] == "COMPLETE":
            raise core.GateError("Completed user phase is immutable")
        row.update(status="RUNNING", next_action="Run all registered acceptance/regression checks")
        render(state, "USER_PHASE_VERIFY_START", phase=2, status="RUNNING")
        before = core.fingerprint()
        results = []
        try:
            _, registry = configuration()
            preserved = core.preservation()
            for key in sorted(registry):
                results.append(core.run_check(key, registry[key]))
            if before != core.fingerprint():
                raise core.GateError("Source changed during verification")
            failed = [r["id"] for r in results if r["status"] != "PASS"]
            row["verification"] = dict(at=core.now(), head=core.git("rev-parse","HEAD"),
                fingerprint=before, preservation=preserved, results=results,
                phase1_revalidation=["phase1-use-contracts","phase1-graph-contracts"])
            row["test_summary"] = f"{len(results)} registered groups; {len(failed)} failed"
            if failed:
                row.update(status="FAIL", reason="Failed checks: " + ", ".join(failed),
                           next_action="Repair scoped failures and rerun full registry; do not complete")
            else:
                row.pop("reason",None)
                row.update(status="PASS", completed_scope="Fixture PostgreSQL data extension, migration/rollback and preserved legacy connections",
                           next_action="Commit verified source/evidence, finish local checkpoint, push development branch only")
            render(state,"USER_PHASE_VERIFY",phase=2,status=row["status"])
            return row
        except BaseException as exc:
            row.update(status="BLOCKED",reason=str(exc),next_action="Resolve recorded blocker; no subsequent phase")
            row["verification_attempt"] = dict(at=core.now(),fingerprint=before,results=results)
            render(state,"USER_PHASE_BLOCKED",phase=2,status="BLOCKED",reason=str(exc))
            raise


def finish():
    with core.lock():
        _, registry = configuration()
        state = core.load(core.STATE)
        row=state["user_phases"]["2"]
        valid_receipt(row,core.fingerprint(),list(registry))
        core.preservation()
        for result in row["verification"]["results"]:
            if core.digest(core.ROOT/result["log"]) != result["log_sha256"]:
                raise core.GateError("Verification log changed")
        if core.git("status","--porcelain"):
            raise core.GateError("Commit verified bytes/evidence before checkpoint")
        head=core.git("rev-parse","HEAD")
        tag="hs2/phase-02/complete"
        core.git("tag",tag,head)
        row.update(status="COMPLETE",end=dict(head=head,tag=tag,at=core.now()),
                   next_action="Push only development branch and verify remote; stop before Phase 3")
        render(state,"USER_PHASE_COMPLETE",phase=2,status="COMPLETE",head=head,tag=tag)
        return row
