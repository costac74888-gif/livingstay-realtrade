"""Exercise the real analysis check with captures and the owned offline guard.

Captures use a pinned Nanum Gothic fixture, not a production typography match.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from offline_support.legacy_runtime import legacy_runtime
from offline_support.process_runner import run_check
from offline_support.source_preservation import new_run_directory, SourcePreservation


def main():
    results = new_run_directory(ROOT / "generated-artifacts/analysis-capture-verification")
    print("ANALYSIS_CAPTURE_RUN_DIR:", results, flush=True)
    with SourcePreservation(results) as preservation:
        with legacy_runtime(results / "fixture.log", browser=True) as env:
            env["SAVE_ANALYSIS_SCREENSHOTS"] = "1"
            env["HOMENSTAY_OFFLINE_ARTIFACT_DIR"] = str(results / "captures")
            result = run_check(
                ["node", str(ROOT / "tests/analysis_mobile_browser_test.js")],
                cwd=ROOT, env=env, timeout=180, logfile=results / "analysis.log")
        print((results / "analysis.log").read_text(), flush=True)
        if result["exit_code"]:
            preservation.exit_code = result["exit_code"]
            return result["exit_code"]
        for mode in ("property", "rental", "operation"):
            for extension, signature in (("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF")):
                files = list((results / "captures").rglob(f"analysis-report-{mode}.{extension}"))
                if len(files) != 1 or not files[0].read_bytes().startswith(signature):
                    raise RuntimeError(f"Missing or invalid {mode} {extension} capture")
                if extension == "pdf":
                    pdf = files[0].read_bytes()
                    if b"NanumGothic" not in pdf or b"/FontFile2" not in pdf:
                        raise RuntimeError(f"Korean fixture font not embedded in {mode} PDF")
        print("PASS three Korean analysis reports saved as PNG and PDF", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
