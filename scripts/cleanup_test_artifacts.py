"""Conservative run-level retention. Dry-run unless --apply is explicit."""
import argparse
import fcntl
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from offline_support.artifact_lifecycle import MARKER

TREES = ("offline-suite", "browser-checks", "post-merge")


def owner_alive(owner):
    """Unknown process identity is protected, not treated as a dead writer."""
    try:
        if (not isinstance(owner["pid"], int) or isinstance(owner["pid"], bool)
                or owner["pid"] <= 0
                or not isinstance(owner["boot_id"], str) or not owner["boot_id"]
                or not isinstance(owner["start_ticks"], str)
                or not owner["start_ticks"].isdigit()):
            return True
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if boot != owner["boot_id"]:
            return False
        try:
            fields = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            return False
        return fields[19] == owner["start_ticks"]
    except (KeyError, TypeError, OSError, IndexError):
        return True


def metadata(path):
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("state") not in ("passed", "failed")
            or not isinstance(data.get("producer"), str) or not data["producer"]
            or not isinstance(data.get("failed_checks"), list)
            or any(not isinstance(name, str) for name in data["failed_checks"])
            or (data["state"] == "failed" and not data["failed_checks"]
                and data["producer"] == "python-run")
            or not isinstance(data.get("finished_at"), (float, int))
            or not math.isfinite(data["finished_at"]) or data["finished_at"] <= 0
            or owner_alive(data.get("owner", {}))):
        raise ValueError("active, interrupted or invalid run metadata")
    return data


def inventory(path):
    """No traversal through links; freeze stat inventory for deletion recheck."""
    items, size = {}, 0
    def unreadable(error):
        raise error
    for current, directories, files in os.walk(path, followlinks=False, onerror=unreadable):
        for entry in [Path(current), *(Path(current) / n for n in directories + files)]:
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("symlink")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("special file")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("hard-linked file")
            if "baseline" in entry.name.lower() or "frozen" in entry.name.lower():
                raise ValueError("frozen/baseline evidence")
            relative = str(entry.relative_to(path))
            items[relative] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                               info.st_ctime_ns, info.st_mode)
    size = sum(info[2] for name, info in items.items() if stat.S_ISREG(info[5]))
    return items, size


def plan(root, days, max_bytes, now=None):
    now = time.time() if now is None else now
    generated = root / "generated-artifacts"
    if generated.is_symlink():
        raise ValueError("generated-artifacts must not be a symlink")
    # Even accidentally tracked generated baselines are never disposable.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    records = []
    for tree in TREES:
        parent = generated / tree
        if parent.is_symlink():
            raise ValueError(f"Refusing symlink output root: {parent}")
        if not parent.exists():
            continue
        for path in sorted(parent.iterdir()):
            record = {"path": str(path.relative_to(root)), "bytes": 0,
                      "action": "keep", "reason": "unknown run"}
            records.append(record)
            try:
                if not path.is_dir() or path.is_symlink():
                    raise ValueError("not a real run directory")
                record["_snapshot"], record["bytes"] = inventory(path)
                if any(name == record["path"] or name.startswith(record["path"] + "/")
                       for name in tracked if name):
                    raise ValueError("tracked source/reference")
                data = metadata(path / MARKER)
                # An outer completed run cannot hide a still-running capture.
                evidence = [metadata(marker) for marker in path.rglob(MARKER)]
                record.update(_data=data, _evidence=evidence, _tree=tree,
                              reason="within retention")
            except (ValueError, OSError, KeyError, TypeError) as exc:
                record["reason"] = str(exc)
    latest = {}
    for record in records:
        for data in record.get("_evidence", []):
            if data["state"] == "failed":
                keys = [(record["_tree"], name) for name in
                        (data["failed_checks"] or [data["producer"]])]
                for key in keys:
                    if key not in latest or data["finished_at"] > latest[key][0]:
                        latest[key] = (data["finished_at"], [record])
                    elif data["finished_at"] == latest[key][0]:
                        latest[key][1].append(record)
    protected = {r["path"] for _, group in latest.values() for r in group}
    candidates = []
    for record in records:
        if record["path"] in protected:
            record["reason"] = "latest failure evidence"
        elif "_data" in record:
            candidates.append(record)
    candidates.sort(key=lambda r: (r["_data"]["finished_at"], r["path"]))
    total = sum(r["bytes"] for r in records)
    remaining = total
    for record in candidates:
        expired = days is not None and now - record["_data"]["finished_at"] > days * 86400
        over = max_bytes is not None and remaining > max_bytes
        if expired or over:
            record.update(action="delete", reason="age limit" if expired else "size limit")
            remaining -= record["bytes"]
    return records, total, remaining


def cleanup(root=ROOT, days=30, max_bytes=None, apply=False):
    generated = root / "generated-artifacts"
    if not generated.exists() and not generated.is_symlink():
        return {"mode": "apply" if apply else "dry-run", "runs": [],
                "bytes_before": 0, "bytes_after": 0, "limit_unmet": False,
                "unmeasured_runs": []}
    if generated.is_symlink():
        raise ValueError("generated-artifacts must not be a symlink")
    lock = generated / ".artifact-cleanup.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Unsafe cleanup lock")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records, total, remaining = plan(root, days, max_bytes)
        if apply:
            if not shutil.rmtree.avoids_symlink_attacks:
                raise RuntimeError("Safe fd-based directory removal is unavailable")
            for record in records:
                if record["action"] != "delete":
                    continue
                path = root / record["path"]
                # Never reuse the dry-run as authorization. Recheck immediately.
                fresh, _, _ = plan(root, days, max_bytes)
                current = next((r for r in fresh if r["path"] == record["path"]), None)
                if (current is None or current["action"] != "delete"
                        or inventory(path)[0] != record["_snapshot"]):
                    raise RuntimeError(f"Run changed during cleanup: {path}")
                # Parents are allowlisted and checked above, never screenshots/.
                generated_fd = os.open(generated, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    parent_fd = os.open(path.parent.name, os.O_RDONLY | os.O_DIRECTORY |
                                        os.O_NOFOLLOW, dir_fd=generated_fd)
                    try:
                        shutil.rmtree(path.name, dir_fd=parent_fd)
                    finally:
                        os.close(parent_fd)
                finally:
                    os.close(generated_fd)
                record["action"] = "deleted"
        unmeasured = [r["path"] for r in records if "_snapshot" not in r]
        return {"mode": "apply" if apply else "dry-run", "bytes_before": total,
                "bytes_after": remaining,
                "limit_unmet": max_bytes is not None and (remaining > max_bytes or bool(unmeasured)),
                "unmeasured_runs": unmeasured,
                "runs": [{k: v for k, v in r.items() if not k.startswith("_")}
                         for r in records]}


def nonnegative(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Must be finite and nonnegative")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-days", type=nonnegative,
                        help="Delete completed runs older than this many days (default: 30 unless size-only)")
    parser.add_argument("--max-mib", type=nonnegative, help="Total size budget across the three trees")
    parser.add_argument("--apply", action="store_true", help="Actually delete eligible whole runs")
    parser.add_argument("--dry-run", action="store_true", help="Explicit default: report only")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    days = args.keep_days if args.keep_days is not None else (30 if args.max_mib is None else None)
    try:
        report = cleanup(days=days, max_bytes=None if args.max_mib is None else int(args.max_mib * 1048576),
                         apply=args.apply)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Cleanup refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
