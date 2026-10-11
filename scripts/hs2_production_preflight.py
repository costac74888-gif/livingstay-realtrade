#!/usr/bin/env python3
"""Publish preflight using fresh UNIX-only PostgreSQL and a scrubbed environment."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from run_legacy_owned import fixture
from offline_support.process_runner import run_check


def check_publish_flow(root):
    config = tomllib.loads((root / ".replit").read_text())
    deployment = config["deployment"]
    if deployment["run"] != ["bash", "scripts/start-prod.sh"]:
        raise RuntimeError("UNAPPROVED_PUBLISH_RUN")
    if deployment["build"] != ["npm", "run", "build:frontend"]:
        raise RuntimeError("UNAPPROVED_PUBLISH_BUILD")
    package = json.loads((root / "package.json").read_text())
    if package["scripts"]["build:frontend"] != "python scripts/build_frontend.py":
        raise RuntimeError("UNAPPROVED_PUBLISH_BUILDER")


def run_probe(root=ROOT, *, app_suffix="", start_suffix="", start_replace=None):
    """Mutations live in an owned workspace; never edit the real entrypoints."""
    root = Path(root)
    check_publish_flow(root)
    with fixture() as env, tempfile.TemporaryDirectory(prefix="hs2-production-") as tmp:
        work = Path(tmp)
        for entry in root.iterdir():
            if entry.name not in {".git", ".local", "app.py", "scripts"}:
                (work / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        (work / "app.py").write_text((root / "app.py").read_text() + "\n" + app_suffix)
        scripts = work / "scripts"
        scripts.mkdir()
        source = (root / "scripts/start-prod.sh").read_text()
        if start_replace:
            source = source.replace(*start_replace)
        # Inject before exec; suffix after exec would be unreachable.
        source = source.replace("exec gunicorn", start_suffix + "\nexec gunicorn")
        (scripts / "start-prod.sh").write_text(source)
        shim = work / "bin"
        shim.mkdir()
        executable = shim / "gunicorn"
        executable.write_text(
            "#!" + sys.executable + "\n"
            "import runpy\nrunpy.run_path(" + repr(str(ROOT / "scripts/hs2_production_probe.py"))
            + ", run_name='__main__')\n")
        executable.chmod(0o700)
        # fixture() has made the only permitted DB. No schema or live data is
        # needed to inspect registrations; app boot jobs remain disabled.
        env.update(
            PROD_DATABASE_URL=env["DATABASE_URL"],
            SKIP_STARTUP_SCHEMA_INIT="1",
            HS2_PRODUCTION_SOURCE_ROOT=str(work),
            PATH=str(shim) + ":" + env["PATH"],
            PYTHONPATH=str(work) + ":" + env["PYTHONPATH"],
        )
        # guard capability is outside the app's config; it is not evidence that
        # a production temporary database selection is approved.
        result = run_check(
            ["bash", "scripts/start-prod.sh"], cwd=work, env=env,
            timeout=45, logfile=work / "probe.log",
        )
        return result["exit_code"], (work / "probe.log").read_text()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    code, log = run_probe(args.root)
    if code or "PRODUCTION_BOUNDARY_PASS" not in log:
        # The child never receives production credentials; keep the public
        # error independent of DSNs or noisy application initialization logs.
        reasons = [line for line in log.splitlines() if line.startswith(
            ("PRODUCTION_", "UNAPPROVED_", "OWNED_"))]
        raise SystemExit("Production boundary rejected: " + "; ".join(reasons or ["probe failed"]))
    print("Production boundary PASS (owned DB, external transport blocked; not Phase18 PG proof)")


if __name__ == "__main__":
    main()
