"""Internal Work/Replit user-phase ledger; never rewrites native receipts."""
import json
from . import core, phase3, phases

PLAN = core.DOC / "continuation.json"
TITLES = [
    "로그인/사용자·운영자 Mode 분리", "PC 소비자 Main", "단기임대 매물등록",
    "가격/Calendar Engine", "검색/Filter/Super Map", "매물 Detail + 예약 Panel",
    "Booking Engine", "Payment/Deposit/Settlement 기반", "운영자 Dashboard",
    "관심/Chat/Notification/My Booking", "FAQ/이용 Guide/Policy", "Admin 확장",
    "Mobile", "통합 Regression/Security/Payment Validation", "Cutover/Open",
]


def configuration():
    phase3.configuration()
    p = core.load(PLAN)
    registry = core.load(core.CHECKS)
    if p.get("work_route") != "internal" or p.get("stop_after_phase") != 18:
        raise core.GateError("Explicit internal Work continuation authorization required")
    source = core.ROOT / p["directive"]["file"]
    if core.digest(source) != p["directive"]["sha256"]:
        raise core.GateError("User directive bytes changed")
    if [x["id"] for x in p["phases"]] != list(range(4, 19)):
        raise core.GateError("User phases must preserve exact ordered 4..18 plan")
    if [x["title"] for x in p["phases"]] != TITLES:
        raise core.GateError("Original user phase meanings changed")
    if p.get("manual_gates") != ["production_migration", "live_pg_settlement", "production_publish"]:
        raise core.GateError("Manual operational gates removed")
    old = json.loads(core.git("show", p["previous_checkpoint"] + ":docs/home_stay_2/state.json"))
    state = core.load(core.STATE)
    for key in ("2", "3"):
        if state["user_phases"][key] != old["user_phases"][key]:
            raise core.GateError("Historical completed user receipt changed")
    old_registry = json.loads(core.git("show", p["previous_checkpoint"] + ":docs/home_stay_2/checks.json"))
    if any(registry.get(k) != v for k, v in old_registry.items()):
        raise core.GateError("Historical registered criterion changed")
    return p, registry


def row_for(state, phase):
    if phase not in range(4, 19):
        raise core.GateError("Only authorized user phases 4..18")
    return state.setdefault("user_phases", {}).setdefault(str(phase), {"status": "PENDING"})


def checkpoint(tag, head):
    """Retry safely after partial local tagging; never overwrite another target."""
    if core.git("tag", "--list", tag):
        if core.git("rev-parse", tag + "^{commit}") != head:
            raise core.GateError("Checkpoint collision; never force-update")
    else:
        core.git("tag", tag, head)


def render(state, event, phase, **details):
    core.record(state, event, phase=phase, **details)
    row = state["user_phases"][str(phase)]
    path = core.DOC / "STATUS.md"
    title = next(p["title"] for p in core.load(PLAN)["phases"] if p["id"] == phase)
    text = (f"# 현재 사용자 Phase {phase} — {row['status']}\n\n"
            f"- 범위: {title}. 사용자 총괄지시서 기준; native 번호와 구분.\n"
            "- Work: Replit 내부의 지시·검토 역할. 외부 통신 아님.\n"
            "- 기존 Phase 1~3 영수증·native 계획·검사·보존·운영 Gate 유지.\n"
            f"- 검사: {row.get('test_summary', '미검증')}\n"
            f"- 원격 저장: {row.get('remote', {}).get('status', 'NOT_VERIFIED')}\n"
            f"- 차단 사유: {row.get('reason', '없음')}\n"
            f"- 다음 작업: {row.get('next_action', '현재 Phase 구현·검증')}\n\n---\n\n")
    path.write_text(text + path.read_text())


def begin(phase):
    with core.lock():
        configuration()
        state = core.load(core.STATE)
        prior = state["user_phases"].get(str(phase - 1), {})
        if prior.get("status") != "COMPLETE" or prior.get("remote", {}).get("status") != "SYNCED":
            raise core.GateError("Prior completed checkpoint and verified development sync required")
        core.git("merge-base", "--is-ancestor", prior["end"]["head"], prior["remote"]["head"])
        if phase > 4 and (
            prior["remote"].get("checkpoint_head") != prior["end"]["head"]
            or prior["remote"].get("source_fingerprint") != prior["verification"]["fingerprint"]
            or prior["remote"].get("main_unchanged") is not True):
            raise core.GateError("Remote receipt does not match completed source/checkpoint")
        row = row_for(state, phase)
        if row["status"] != "PENDING":
            raise core.GateError("User phase already started/completed")
        if any(r.get("status") in {"RUNNING", "PASS", "FAIL", "BLOCKED"}
               for k, r in state["user_phases"].items() if int(k) >= 4):
            raise core.GateError("Resolve current user phase first")
        row.update(status="RUNNING", instruction=f"docs/home_stay_2/phase{phase}/WORK_INSTRUCTION.md",
                   at=core.now(), source_head=core.git("rev-parse", "HEAD"),
                   next_action="Implement actual acceptance, run full registry, review and sync checkpoint")
        state["current_user_phase"] = phase
        render(state, "WORK_INSTRUCTION_ACCEPTED", phase, status="RUNNING")


def verify(phase):
    with core.lock():
        p, registry = configuration()
        state = core.load(core.STATE)
        row = row_for(state, phase)
        if state.get("current_user_phase") != phase or row["status"] == "COMPLETE":
            raise core.GateError("Only current incomplete user phase may verify")
        stage = next(x for x in p["phases"] if x["id"] == phase)
        row.update(status="RUNNING", next_action="Execute and review all registered checks")
        render(state, "REPLIT_FULL_VERIFY_START", phase, status="RUNNING")
        before = core.fingerprint()
        results = []
        try:
            acceptance = stage.get("acceptance", [])
            if not acceptance or any(a.get("check") is None or a["check"] not in registry
                                     or registry[a["check"]]["role"] != "acceptance"
                                     for a in acceptance):
                raise core.GateError("Actual phase acceptance missing")
            preserved = core.preservation()
            for key in sorted(registry):
                results.append(core.run_check(key, registry[key]))
            if before != core.fingerprint():
                raise core.GateError("Source changed during full verification")
            row["verification"] = dict(at=core.now(), head=core.git("rev-parse", "HEAD"),
                                       fingerprint=before, preservation=preserved, results=results)
            failed = [r["id"] for r in results if r["status"] != "PASS"]
            row["test_summary"] = f"{len(results)} registered groups; {len(failed)} failed"
            if failed:
                row.update(status="FAIL", reason="Failed checks: " + ", ".join(failed),
                           next_action="Repair scoped failures and rerun full registry")
            else:
                row.pop("reason", None)
                row.update(status="PASS", next_action="Work review, commit evidence, checkpoint and verify development remote")
            render(state, "REPLIT_FULL_VERIFY_RESULT", phase, status=row["status"])
            return row
        except BaseException as exc:
            row.update(status="BLOCKED", reason=str(exc), next_action="Resolve blocker; no next phase")
            row["verification_attempt"] = dict(at=core.now(), fingerprint=before, results=results)
            render(state, "USER_PHASE_BLOCKED", phase, status="BLOCKED")
            raise


def finish(phase):
    with core.lock():
        _, registry = configuration()
        state = core.load(core.STATE)
        row = row_for(state, phase)
        if state.get("current_user_phase") != phase:
            raise core.GateError("Only current user phase can finish")
        phases.valid_receipt(row, core.fingerprint(), list(registry))
        core.preservation()
        review = row.get("work_review", {})
        if (review.get("passed") is not True
                or review.get("fingerprint") != row["verification"]["fingerprint"]
                or sorted(review.get("reviewed_check_ids", [])) != sorted(registry)):
            raise core.GateError("Recorded Work evidence review required")
        if phase == 18:
            raise core.GateError("Cutover/Open requires explicit operational approvals and actual cutover evidence; readiness is not completion")
        for result in row["verification"]["results"]:
            if core.digest(core.ROOT / result["log"]) != result["log_sha256"]:
                raise core.GateError("Verification log changed")
        if core.git("status", "--porcelain"):
            raise core.GateError("Commit verified source/evidence before completion checkpoint")
        head = core.git("rev-parse", "HEAD")
        start_tag = f"hs2/phase-{phase:02d}/start"
        checkpoint(start_tag, row["source_head"])
        tag = f"hs2/phase-{phase:02d}/complete"
        checkpoint(tag, head)
        row.update(status="COMPLETE", start=dict(head=row["source_head"], tag=start_tag),
                   end=dict(head=head, tag=tag, at=core.now()),
                   next_action="Verify development remote then issue next user phase; operational gates remain closed")
        render(state, "WORK_PHASE_COMPLETE", phase, status="COMPLETE", head=head, tag=tag)
        return row
