"""Bounded subprocesses with process-group and temporary-workspace ownership."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def group_running(pgid):
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == pgid and fields[0] != "Z":
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def stop_group(process, grace=5):
    """Stop surviving children even when the parent already exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    # Parent wait does not prove its children exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    deadline = time.monotonic() + 2
    while group_running(process.pid):
        if time.monotonic() >= deadline:
            raise RuntimeError("Test process group did not stop after SIGKILL")
        time.sleep(0.01)


def run_check(command, *, cwd, env, timeout, logfile):
    start = time.monotonic()
    process = None
    timed_out = False
    # Child processes inherit the same directory; deletion belongs to us, so a
    # hung/crashed child cannot leave parser/build temporary data behind.
    with tempfile.TemporaryDirectory(prefix="homenstay-check-") as tempdir:
        child_env = dict(env, TMPDIR=tempdir, HOMENSTAY_MANAGED_TEST="1")
        with Path(logfile).open("w") as output:
            try:
                process = subprocess.Popen(
                    command, cwd=cwd, env=child_env, stdout=output,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    output.write(f"\nDEADLINE: {timeout}s; dumping stacks and stopping process group\n")
                    output.flush()
                    if Path(command[0]).name.startswith("python"):
                        try:
                            os.kill(process.pid, signal.SIGUSR1)
                            time.sleep(0.1)
                        except ProcessLookupError:
                            pass
                    stop_group(process)
                    code = 124
            finally:
                if process is not None:
                    stop_group(process)
    return {
        "exit_code": code, "timed_out": timed_out,
        "seconds": round(time.monotonic() - start, 2),
        "process_group_cleaned": True, "temporary_directory_cleaned": True,
    }
