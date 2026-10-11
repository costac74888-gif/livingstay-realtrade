"""Retention metadata: unknown/interrupted runs must never be auto-deleted."""
import json
import os
import time
from pathlib import Path

MARKER = ".artifact-run.json"


def owner_identity():
    # PID alone is unsafe after a reboot or PID reuse.
    return {
        "pid": os.getpid(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "start_ticks": Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()[19],
    }


def write_marker(directory, data):
    directory = Path(directory)
    temporary = directory / (MARKER + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(directory / MARKER)


def start_run(directory):
    write_marker(directory, {
        "version": 1, "state": "running", "started_at": time.time(),
        "owner": owner_identity(), "producer": "python-run",
    })


def finish_run(directory, exit_code, failed_checks=None):
    data = json.loads((Path(directory) / MARKER).read_text())
    data.update(state="failed" if exit_code else "passed",
                finished_at=time.time(), failed_checks=failed_checks or [])
    write_marker(directory, data)
