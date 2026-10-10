"""Fail-closed, single-stage development ledger, entirely independent of Flask."""
import ast
import contextlib
import csv
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/home_stay_2"
GENERATED = ROOT / ".local/hs2-harness"
STATE = DOC / "state.json"
PLAN = DOC / "stages.json"
CHECKS = DOC / "checks.json"
BASELINE = DOC / "preservation_baseline.json"
CONTROL = {"docs/home_stay_2/state.json", "docs/home_stay_2/STATUS.md",
           "docs/home_stay_2/SELF_CHECK.md"}


class GateError(RuntimeError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        temp = Path(f.name)
    os.replace(temp, path)


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                            capture_output=True, check=False)
    if result.returncode:
        raise GateError("Git command failed: " + " ".join(args[:2]))
    return result.stdout.strip()


def fingerprint():
    """Bind a pass to actual bytes, deletions, spec, harness and reviewed tests."""
    paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    pairs = []
    for name in sorted(set(paths)):
        if not name or name in CONTROL:
            continue
        path = ROOT / name
        pairs.append((name, digest(path) if path.is_file() else "<deleted>"))
    return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()


def routes():
    records = set()
    for name in ["app.py", "auction_service.py", "survey_service.py",
                 "membership_service.py", "membership_checks.py", "listing_extensions.py"]:
        for n in ast.walk(ast.parse((ROOT / name).read_text())):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in n.decorator_list:
                if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and d.func.attr in {"route", "get", "post", "put", "delete", "patch"}
                        and d.args):
                    continue
                try:
                    path = ast.literal_eval(d.args[0])
                    methods = [d.func.attr.upper()] if d.func.attr != "route" else ["GET"]
                    for k in d.keywords:
                        if k.arg == "methods":
                            methods = ast.literal_eval(k.value)
                except (ValueError, TypeError):
                    raise GateError("Dynamic route requires manual review")
                records.update((name, n.name, str(m).upper(), path) for m in methods)
    return sorted(records)


def preservation():
    baseline = load(BASELINE)
    missing = [name for name, sha in baseline["frozen_files"].items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    if missing:
        raise GateError("Preservation violation: " + ", ".join(missing))
    inventory = ROOT / baseline["route_inventory"]
    if digest(inventory) != baseline["route_inventory_sha256"]:
        raise GateError("Audit route baseline changed")
    with inventory.open(encoding="utf-8-sig") as f:
        expected = {(r["file"], r["function"], r["method"], r["path"])
                    for r in csv.DictReader(f)}
    current = set(tuple(r) for r in routes())
    removed = expected - current
    if removed:
        raise GateError(f"Existing route/function/method removed: {len(removed)}")
    for name in baseline["must_exist"]:
        if not (ROOT / name).is_file():
            raise GateError("Existing feature removed: " + name)
    return {"frozen_files": len(baseline["frozen_files"]),
            "preserved_routes": len(expected),
            "must_exist": len(baseline["must_exist"])}


def configuration():
    plan = load(PLAN)
    registry = load(CHECKS)
    required = {"lodging-status", "lodging-types", "auction-domain", "relay",
                "map-legacy", "admin-scope", "privacy-ui", "harness-unit", "harness-contracts"}
    if not required.issubset(registry):
        raise GateError("Mandatory preservation/regression checks removed")
    ids = [s["id"] for s in plan["stages"]]
    if ids != list(range(1, 19)):
        raise GateError("Exactly 18 ordered stages required")
    if len(set(registry)) != len(registry):
        raise GateError("Duplicate check ID")
    for name, check in registry.items():
        path = ROOT / check["file"]
        reviewed_isolation = {
            ("phase2-data-contracts","tests/test_hs2_phase2_data.py"):("python","temporary-postgres"),
            ("phase3-registration-db","tests/test_hs2_phase3_db.py"):("python","temporary-postgres"),
            ("phase3-registration-ui","tests/hs2_phase3_ui_test.cjs"):("node","private-browser-fixture"),
            ("phase4-auth-db","tests/test_hs2_phase4_auth_db.py"):("python","temporary-postgres"),
            ("phase4-mode-ui","tests/hs2_phase4_ui_test.cjs"):("node","private-browser-fixture"),
            ("phase5-consumer-db","tests/test_hs2_phase5_db.py"):("python","temporary-postgres"),
            ("phase5-consumer-ui","tests/hs2_phase5_ui_test.cjs"):("node","private-browser-fixture"),
            ("phase6-listing-db","tests/test_hs2_phase6_db.py"):("python","temporary-postgres"),
            ("phase6-listing-ui","tests/hs2_phase6_ui_test.cjs"):("node","private-browser-fixture"),
            ("phase7-calendar-db","tests/test_hs2_phase7_db.py"):("python","temporary-postgres"),
            ("phase7-calendar-ui","tests/hs2_phase7_ui_test.cjs"):("node","private-browser-fixture"),
        }
        if check.get("isolation") is not None and reviewed_isolation.get(
                (name,check["file"])) != (check["kind"],check["isolation"]):
            raise GateError("Unreviewed isolated database capability")
        if (check["kind"] not in {"python", "node"}
                or check["role"] not in {"regression", "acceptance", "harness"}
                or not path.is_file()
                or path.is_symlink() or not path.resolve().is_relative_to(ROOT / "tests")
                or path.suffix not in {".py", ".js", ".cjs"}
                or digest(path) != check["reviewed_sha256"]):
            raise GateError("Unreviewed check or invalid test path: " + name)
    acceptance_ids = []
    for stage in plan["stages"]:
        if not stage["acceptance"] or not stage["regression"]:
            raise GateError("Acceptance and regression cannot be empty")
        if any(key not in registry for key in stage["regression"]):
            raise GateError("Unknown regression binding")
        for item in stage["acceptance"]:
            acceptance_ids.append(item["id"])
            if not item["criterion"].strip():
                raise GateError("Empty criterion")
            key = item["check"]
            if key is not None:
                if key not in registry or registry[key]["role"] != "acceptance":
                    raise GateError("Acceptance must bind to a reviewed acceptance check")
    if len(set(acceptance_ids)) != len(acceptance_ids):
        raise GateError("Acceptance IDs must be unique")
    return plan, registry


def test_env(work):
    # Never copy the process environment: no production DSN, tokens or keys.
    env = {key: os.environ[key] for key in ["PATH", "LANG"] if key in os.environ}
    env.update({
        "HOME": str(work), "TMPDIR": str(work), "PYTHONDONTWRITEBYTECODE": "1",
        # Nix-managed dependencies are on the interpreter's sys.path. Preserve
        # library directories, NOT the inherited environment/PYTHONPATH string.
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(
            [str(ROOT / "hs2_harness/guard"), str(ROOT)]
            + [p for p in sys.path if p and Path(p).is_dir()])),
        "NODE_OPTIONS": "--require=" + str(ROOT / "hs2_harness/guard/network.cjs"),
        "HOMENSTAY_OFFLINE_TESTS": "1", "DISABLE_EXTERNAL_NOTIFICATIONS": "1",
        "SKIP_STARTUP_SCHEMA_INIT": "1", "SKIP_APP_BOOT_TASKS": "1",
        "RELAY_ENABLED": "0", "FLASK_SECRET_KEY": "hs2-not-a-production-secret",
        "BLD_SERVICE_KEY": "hs2-fake", "RTMS_SERVICE_KEY": "hs2-fake",
        "LODGING_SERVICE_KEY": "hs2-fake", "TOUR_API_SERVICE_KEY": "hs2-fake",
    })
    return env


def run_check(name, check, timeout=120):
    """No shell; bounded process group; logs stay outside deployment/Git."""
    if check.get("isolation") == "temporary-postgres":
        from .isolated_postgres import run_check as isolated_check
        return isolated_check(name, check, timeout)
    if check.get("isolation") == "private-browser-fixture":
        from .isolated_browser import run_check as browser_check
        return browser_check(name,check,timeout)
    GENERATED.mkdir(parents=True, exist_ok=True)
    file = check["file"]
    command = ([sys.executable, "-m", "unittest", "discover", "-s",
                str(Path(file).parent), "-p", Path(file).name, "-v"]
               if check["kind"] == "python" else ["node", file])
    logfile = GENERATED / (name + "-" + str(time.time_ns()) + ".log")
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="hs2-test-") as work:
        with logfile.open("w") as output:
            proc = subprocess.Popen(command, cwd=ROOT, env=test_env(Path(work)),
                                    stdout=output, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
            except BaseException as exc:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                if not isinstance(exc, subprocess.TimeoutExpired):
                    raise
                code = 124
    if code == 0:
        text = logfile.read_text(errors="replace")
        # unittest skips/expected failures or an empty suite never count as PASS.
        if check["kind"] == "python" and (
                "Ran 0 tests" in text or "skipped=" in text or "expected failures=" in text):
            code = 125
    return {"id": name, "status": "PASS" if code == 0 else "FAIL",
            "exit_code": code, "seconds": round(time.monotonic() - start, 3),
            "command": command, "test_sha256": digest(ROOT / file),
            "log": str(logfile.relative_to(ROOT)), "log_sha256": digest(logfile)}


@contextlib.contextmanager
def lock():
    GENERATED.mkdir(parents=True, exist_ok=True)
    with (GENERATED / "ledger.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GateError("Another harness operation is running")
        yield


def record(state, event, **details):
    state["events"].append({"at": now(), "event": event, **details})
    atomic(STATE, state)
    lines = ["# HOME & STAY 2.0 Harness 상태", "",
             f"- 하네스 자체검사: **{state['bootstrap']['status']}**",
             f"- 현재 개발 단계: **{state['current_stage']}** (0 = 아직 시작 전)",
             "- 운영 migration / 실제 PG·정산 / 배포: 자동 실행 불가", "",
             "| 단계 | 상태 | 시작 Git | 완료 Git |", "| --- | --- | --- | --- |"]
    for key, row in state["stages"].items():
        lines.append(f"| {key} | {row['status']} | {row.get('start', {}).get('head', '-')} | {row.get('end', {}).get('head', '-')} |")
    (DOC / "STATUS.md").write_text("\n".join(lines) + "\n")
    bootstrap = state["bootstrap"]
    summary = ["# 0.5단계 자체점검 기록", "",
               f"- 결과: **{bootstrap['status']}**",
               f"- 검사 시각: {bootstrap.get('at', 'NOT_RUN')}",
               f"- Git HEAD: `{bootstrap.get('head', '-')}`",
               f"- 검증 파일 지문: `{bootstrap.get('fingerprint', '-')}`",
               "- 제품 1~18단계 구현 PASS를 의미하지 않음. 미구현 acceptance는 BLOCKED.",
               "- 원본 코드/DB/API/Relay를 수정하거나 실제 운영 작업을 수행하지 않음.",
               "- 앱/운영 UI/DB 연결/실제 provider 발송은 검사 범위에서 제외.",
               "- 시작/완료 체크포인트는 clean tree에서 stage start/finish 시 local tag 생성.",
               "- 하네스는 자동 commit/push/배포하지 않음. 현재 commit 상태는 state.json 참조.",
               "", "| 검사 | 결과 | 소요(초) | 로그 SHA-256 |",
               "| --- | --- | --- | --- |"]
    for result in bootstrap.get("results", []):
        summary.append(f"| {result['id']} | {result['status']} | {result['seconds']} | {result['log_sha256']} |")
    summary += ["", "## 보존 검사", json.dumps(bootstrap.get("preservation", {}), ensure_ascii=False),
                "", "## 승인 게이트", "운영 DB migration / 실제 PG·정산 / 운영 배포는 별도 승인 대기. 자동 실행 경로 없음.",
                "", "## 검사 한계",
                "관리자 인증의 실제 HTTP/DB 동작과 전체 browser/통합검사는 미실행. 정적 계약/모의 요청/순수 함수 검사만 수행.",
                "운영 DB 불변 자체를 접속해 증명한 것이 아니라 하네스가 운영 연결을 하지 않았음을 검사.",
                "앞선 실패 및 변경된 검증 범위는 README와 state.events에 기록."]
    (DOC / "SELF_CHECK.md").write_text("\n".join(summary) + "\n")


def self_check():
    with lock():
        state = load(STATE)
        started = fingerprint()
        try:
            configuration()
            preserved = preservation()
            registry = load(CHECKS)
            results = [run_check(name, check) for name, check in registry.items()
                       if check["role"] in {"regression", "harness"}]
            if fingerprint() != started:
                raise GateError("Repository changed during verification")
            status = "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"
            state["bootstrap"] = {"phase": "0.5", "status": status, "at": now(),
                                  "fingerprint": started, "head": git("rev-parse", "HEAD"),
                                  "commit_status": git("status", "--porcelain"),
                                  "preservation": preserved, "results": results}
            record(state, "SELF_CHECK", status=status, fingerprint=started,
                   results=results, preservation=preserved)
            return state["bootstrap"]
        except BaseException as exc:
            state["bootstrap"] = {"phase": "0.5", "status": "FAIL", "reason": str(exc), "at": now()}
            record(state, "SELF_CHECK", status="FAIL", reason=str(exc))
            raise


def start_stage(stage_id):
    with lock():
        state = load(STATE)
        configuration()
        preservation()
        if state["bootstrap"]["status"] != "PASS":
            raise GateError("Harness self-check must PASS first")
        if state["bootstrap"]["fingerprint"] != fingerprint():
            raise GateError("Harness PASS is stale; run self-check again")
        if not 1 <= stage_id <= 18:
            raise GateError("Stage must be 1..18")
        for i in range(1, stage_id):
            if state["stages"][str(i)]["status"] != "COMPLETE":
                raise GateError("Previous stage is not COMPLETE")
        row = state["stages"][str(stage_id)]
        if row["status"] != "PENDING":
            raise GateError("Stage already started/completed")
        if any(r["status"] in {"IN_PROGRESS", "PASS", "FAIL", "BLOCKED"}
               for r in state["stages"].values()):
            raise GateError("Finish current stage first")
        head = git("rev-parse", "HEAD")
        tag = f"hs2/stage-{stage_id:02d}/start"
        # Lightweight local tag is a real Git checkpoint, never commit/push.
        if git("status", "--porcelain"):
            raise GateError("Commit reviewed changes first; harness never auto-commits")
        git("tag", tag, head)
        row.update(status="IN_PROGRESS", start={"head": head, "tag": tag, "at": now()})
        state["current_stage"] = stage_id
        record(state, "STAGE_START", stage=stage_id, head=head, tag=tag)


def verify_stage(stage_id, note):
    with lock():
        state = load(STATE)
        if stage_id != state["current_stage"] or not stage_id:
            raise GateError("Only current stage can be verified")
        row = state["stages"][str(stage_id)]
        if row["status"] == "COMPLETE":
            raise GateError("Completed stage is immutable")
        try:
            plan, registry = configuration()
            preservation()
            stage = plan["stages"][stage_id - 1]
            missing = [a["id"] for a in stage["acceptance"] if a["check"] is None]
            if missing:
                row.update(status="BLOCKED", missing_acceptance=missing)
                record(state, "STAGE_BLOCKED", stage=stage_id, missing=missing)
                raise GateError("Acceptance checks not implemented: " + ", ".join(missing))
            before = fingerprint()
            common = [k for k, v in registry.items()
                      if v.get("role") in {"regression", "harness"}]
            previous = [a["check"] for s in plan["stages"][:stage_id - 1]
                        for a in s["acceptance"]]
            if any(k is None for k in previous):
                raise GateError("Previous completed acceptance binding was removed")
            keys = sorted(set(common + previous + stage["regression"]
                              + [a["check"] for a in stage["acceptance"]]))
            results = [run_check(k, registry[k]) for k in keys]
            status = "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"
            if before != fingerprint():
                status = "FAIL"
            row.update(status=status, verification={"at": now(), "fingerprint": before,
                       "head": git("rev-parse", "HEAD"), "results": results,
                       "change_note": note,
                       "changed_files": git("diff", "--name-only", row["start"]["head"]).splitlines(),
                       "commit_status": git("status", "--porcelain")})
            record(state, "STAGE_VERIFY", stage=stage_id, status=status,
                   verification=row["verification"])
            return row["verification"] | {"status": status}
        except BaseException as exc:
            if row["status"] != "BLOCKED":
                row["status"] = "FAIL"
                record(state, "STAGE_VERIFY", stage=stage_id, status="FAIL",
                       reason=str(exc))
            raise


def finish_stage(stage_id):
    with lock():
        state = load(STATE)
        if not stage_id or state["current_stage"] != stage_id:
            raise GateError("Only current stage can finish")
        row = state["stages"][str(stage_id)]
        if row["status"] != "PASS" or row["verification"]["fingerprint"] != fingerprint():
            raise GateError("Current bytes do not have a PASS; verify again")
        configuration()
        preservation()
        if git("status", "--porcelain"):
            raise GateError("Commit test evidence and reviewed changes first; then finish")
        head = git("rev-parse", "HEAD")
        tag = f"hs2/stage-{stage_id:02d}/complete"
        git("tag", tag, head)
        row.update(status="COMPLETE", end={"head": head, "tag": tag, "at": now()})
        record(state, "STAGE_COMPLETE", stage=stage_id, head=head, tag=tag)


def request_approval(kind, note):
    if kind not in {"production_migration", "live_pg_settlement", "production_publish"}:
        raise GateError("Unknown manual gate")
    with lock():
        state = load(STATE)
        state.setdefault("approval_gates", {})[kind] = {
            "status": "AWAITING_OWNER_APPROVAL", "automatic_execution": False,
            "at": now(), "scope": note}
        record(state, "APPROVAL_REQUEST", kind=kind, status="AWAITING_OWNER_APPROVAL",
               scope=note, automatic_execution=False)
    return {"status": "AWAITING_OWNER_APPROVAL", "automatic_execution": False}
