"""Explicit Phase 3 authorization, immutable prior receipts and whole-suite gates."""
import json
from . import core,phases

PLAN=core.DOC/"phase3/plan.json"


def configuration():
    # Phase 2's configuration/plan stays byte-identical and remains usable.
    phases.configuration()
    p=core.load(PLAN);registry=core.load(core.CHECKS);state=core.load(core.STATE)
    if p["user_phase"]!=3 or p["stop_after_phase"]!=3:raise core.GateError("Only Phase 3 authorized")
    ids=[x["check"] for x in p["acceptance"]]
    expected={"phase3-registration-contracts","phase3-registration-db","phase3-gate-contracts","phase3-registration-ui"}
    if len(ids)!=4 or set(ids)!=expected or any(registry[k]["role"]!="acceptance" for k in ids):
        raise core.GateError("Missing Phase 3 actual acceptance")
    old=json.loads(core.git("show",p["previous_checkpoint"]+":docs/home_stay_2/state.json"))
    if state["user_phases"]["2"]!=old["user_phases"]["2"]:
        raise core.GateError("Phase 2 completion receipt changed")
    old_registry=json.loads(core.git("show",p["previous_checkpoint"]+":docs/home_stay_2/checks.json"))
    if any(registry.get(k)!=v for k,v in old_registry.items()):
        raise core.GateError("Previous registry criterion/hash changed")
    if any(v["status"]!="NOT_APPROVED" for v in state["approval_gates"].values()):
        raise core.GateError("Operational gate changed")
    return p,registry


def render(state,event,**details):
    core.record(state,event,**details)
    row=state["user_phases"]["3"];path=core.DOC/"STATUS.md"
    text=(f"# 현재 사용자 Phase 3 — {row['status']}\n\n"
          "- 범위: 전체 용도 건물 후보·주소·대장·좌표 확인의 등록 기반. 격리/모의 전용.\n"
          "- 번호 대응: 저장소 3단계 요구를 참고하되 인증 2단계 미시작; 저장소 2~18 PENDING.\n"
          "- Phase 1·2: COMPLETE 영수증 보존.\n"
          f"- 완료 범위: {row.get('completed_scope','구현·검증 중')}\n"
          f"- 검사: {row.get('test_summary','검사 예정')}\n"
          f"- 원격 저장: {row.get('remote',{}).get('status','NOT_PUSHED')}\n"
          f"- 차단 사유: {row.get('reason','없음')}\n"
          f"- 다음 작업: {row['next_action']}\n\n---\n\n")
    path.write_text(text+path.read_text())


def verify():
    with core.lock():
        s=core.load(core.STATE);r=s["user_phases"]["3"]
        if r["status"]=="COMPLETE":raise core.GateError("Completed phase immutable")
        r.update(status="RUNNING",next_action="Run entire registered suite; stop after Phase 3")
        render(s,"USER_PHASE_VERIFY_START",phase=3,status="RUNNING")
        before=core.fingerprint();results=[]
        try:
            _,registry=configuration();preserved=core.preservation()
            for key in sorted(registry):results.append(core.run_check(key,registry[key]))
            if before!=core.fingerprint():raise core.GateError("Source changed during verification")
            r["verification"]=dict(at=core.now(),head=core.git("rev-parse","HEAD"),fingerprint=before,
                                   preservation=preserved,results=results)
            failed=[x["id"] for x in results if x["status"]!="PASS"]
            r["test_summary"]=f"{len(results)} registered groups; {len(failed)} failed"
            if failed:r.update(status="FAIL",reason="Failed checks: "+", ".join(failed),next_action="Repair scoped failures and rerun entire registry")
            else:
                r.pop("reason",None)
                r.update(status="PASS",completed_scope="Private fixture UI/API registration workflow, reused registry mapper, strict provider evidence, actual PostgreSQL reference writes, preserved legacy and prior receipts",
                         next_action="Commit evidence, checkpoint Phase 3, sync development branch only; no Phase 4")
            render(s,"USER_PHASE_VERIFY",phase=3,status=r["status"])
            return r
        except BaseException as e:
            r.update(status="BLOCKED",reason=str(e),next_action="Resolve blocker within Phase 3; no next phase")
            r["verification_attempt"]=dict(at=core.now(),fingerprint=before,results=results)
            render(s,"USER_PHASE_BLOCKED",phase=3,status="BLOCKED")
            raise


def finish():
    with core.lock():
        _,registry=configuration();s=core.load(core.STATE);r=s["user_phases"]["3"]
        phases.valid_receipt(r,core.fingerprint(),list(registry));core.preservation()
        if core.git("status","--porcelain"):raise core.GateError("Commit tested source/evidence first")
        for x in r["verification"]["results"]:
            if core.digest(core.ROOT/x["log"])!=x["log_sha256"]:raise core.GateError("Verification log changed")
        head=core.git("rev-parse","HEAD");tag="hs2/phase-03/complete";core.git("tag",tag,head)
        r.update(status="COMPLETE",end=dict(head=head,tag=tag,at=core.now()),
                 next_action="Sync development branch only; stop at Phase 3; operational gates remain NOT_APPROVED")
        render(s,"USER_PHASE_COMPLETE",phase=3,status="COMPLETE",head=head)
        return r
