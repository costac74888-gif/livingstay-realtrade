"""Opt-in local retention runner. Never imports the application or contacts services."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

from cleanup_test_artifacts import ROOT, cleanup

POLICY_PATH = ROOT / "docs/test-artifact-retention-policy.json"
AUDIT_TREE = "artifact-cleanup-audit"


def validate_policy(policy):
    limits = {"keep_days": 3650, "max_mib": 1048576, "interval_hours": 8760}
    if not isinstance(policy, dict) or set(policy) != {"version", *limits}:
        raise ValueError("Policy requires version, keep_days, max_mib, interval_hours")
    if type(policy["version"]) is not int or policy["version"] != 1:
        raise ValueError("Unsupported policy version")
    for name, maximum in limits.items():
        if type(policy[name]) is not int or not 1 <= policy[name] <= maximum:
            raise ValueError(f"Invalid {name}: expected integer 1..{maximum}")
    return dict(policy)


def policy_digest(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def checked_file(directory_fd, name, flags):
    fd = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise ValueError(f"Unsafe audit file: {name}")
    return os.fdopen(fd, "r+" if flags & os.O_RDWR else "r")


def write_record(handle, record):
    handle.seek(0)
    json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
    handle.write("\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


@contextmanager
def audit_lock(root):
    """Hold a separate scheduler lock; manual cleanup keeps its own deletion lock."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    generated_fd = audit_fd = None
    try:
        try:
            os.mkdir("generated-artifacts", 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        generated_fd = os.open("generated-artifacts", os.O_RDONLY | os.O_DIRECTORY |
                               os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            os.mkdir(AUDIT_TREE, 0o700, dir_fd=generated_fd)
        except FileExistsError:
            pass
        audit_fd = os.open(AUDIT_TREE, os.O_RDONLY | os.O_DIRECTORY |
                           os.O_NOFOLLOW, dir_fd=generated_fd)
        with checked_file(audit_fd, ".scheduler.lock", os.O_CREAT | os.O_RDWR) as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield audit_fd
    finally:
        for fd in (audit_fd, generated_fd, root_fd):
            if fd is not None:
                os.close(fd)


def approval(audit_fd, receipt, policy):
    if not receipt or not re.fullmatch(r"[0-9a-f]{32}", receipt):
        raise ValueError("--apply requires --confirm-dry-run RECEIPT from a successful preview")
    with checked_file(audit_fd, receipt + ".json", os.O_RDONLY) as handle:
        record = json.load(handle)
    if (not isinstance(record, dict)
            or record.get("status") != "finished" or record.get("mode") != "dry-run"
            or record.get("policy") != policy
            or record.get("policy_digest") != policy_digest(policy)
            or not isinstance(record.get("report"), dict)
            or record["report"].get("mode") != "dry-run"):
        raise ValueError("Dry-run receipt is incomplete or belongs to another policy")


def last_attempt(audit_fd, policy, mode):
    """Running/error attempts also count: restarts must not cause a tight retry loop."""
    latest = 0
    for name in os.listdir(audit_fd):
        if not re.fullmatch(r"[0-9a-f]{32}\.json", name):
            continue
        with checked_file(audit_fd, name, os.O_RDONLY) as handle:
            record = json.load(handle)
        if not isinstance(record, dict):
            raise ValueError("Invalid audit record; refusing schedule")
        if record.get("policy_digest") == policy_digest(policy) and record.get("mode") == mode:
            stamp = record.get("started_at")
            if type(stamp) not in (int, float) or not 0 < stamp < float("inf"):
                raise ValueError("Invalid attempt timestamp; refusing schedule")
            latest = max(latest, stamp)
    return latest


def execute(audit_fd, root, policy, *, apply=False, receipt=None,
            respect_interval=True, now=None):
    policy = validate_policy(policy)
    now = time.time() if now is None else now
    mode = "apply" if apply else "dry-run"
    if apply:
        approval(audit_fd, receipt, policy)
    previous = last_attempt(audit_fd, policy, mode)
    due_at = previous + policy["interval_hours"] * 3600
    if respect_interval and previous and now < due_at:
        return {"status": "not-due", "mode": mode, "next_due_at": due_at}
    identifier = uuid.uuid4().hex
    record = {"version": 1, "receipt": identifier, "policy": policy,
              "policy_digest": policy_digest(policy), "started_at": now,
              "mode": mode, "status": "running", "confirmation": receipt}
    # Reserve and fsync a log BEFORE allowing deletion. Logs are outside cleanup's
    # three allowlisted trees and are never automatically removed by this runner.
    with checked_file(audit_fd, identifier + ".json", os.O_CREAT | os.O_EXCL | os.O_RDWR) as log:
        write_record(log, record)
        os.fsync(audit_fd)
        try:
            report = cleanup(root=root, days=policy["keep_days"],
                             max_bytes=policy["max_mib"] * 1048576, apply=apply)
        except Exception as exc:
            record.update(status="error", finished_at=time.time(),
                          error=f"{type(exc).__name__}: {exc}")
            write_record(log, record)
            raise
        record.update(status="finished", finished_at=time.time(), report=report)
        write_record(log, record)
    return record


def run_once(root, policy, *, enabled=False, **kwargs):
    if not enabled:
        return {"status": "disabled", "message": "No cleanup. Explicit --enable is required."}
    policy = validate_policy(policy)
    with audit_lock(root) as audit_fd:
        return execute(audit_fd, root, policy, **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="Explicitly opt into execution")
    parser.add_argument("--watch", action="store_true", help="Run while workspace is awake")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Report only; default mode")
    modes.add_argument("--apply", action="store_true", help="Delete eligible evidence")
    parser.add_argument("--confirm-dry-run", help="Receipt ID of inspected dry-run for this policy")
    args = parser.parse_args(argv)
    if args.confirm_dry_run and not args.apply:
        parser.error("--confirm-dry-run is only valid with --apply")
    if not args.enable:
        print(json.dumps(run_once(ROOT, None)))
        return 0
    try:
        policy = validate_policy(json.loads(POLICY_PATH.read_text()))
        with audit_lock(ROOT) as audit_fd:
            while True:
                # Stop instead of silently adopting unreviewed policy edits.
                if validate_policy(json.loads(POLICY_PATH.read_text())) != policy:
                    raise ValueError("Policy changed; stop and perform a new dry-run")
                record = execute(audit_fd, ROOT, policy, apply=args.apply,
                                 receipt=args.confirm_dry_run,
                                 respect_interval=args.watch or not args.dry_run)
                if record["status"] != "not-due" or not args.watch:
                    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
                if not args.watch:
                    return 0
                time.sleep(60)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Scheduled cleanup refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
