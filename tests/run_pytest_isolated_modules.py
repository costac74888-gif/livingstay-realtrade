"""Run all pytest modules in fresh interpreters; retain every assertion/result."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    modules = sorted(p for p in (ROOT / "tests").glob("*.py")
                     if p.name.startswith("test_") or p.name.endswith("_test.py"))
    failed = []
    for path in modules:
        print(f"\nPYTEST MODULE {path.name}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "-q", "--tb=short"],
            timeout=180)
        if result.returncode:
            failed.append(path.name)
    print(f"\nPYTEST MODULES {len(modules)}; FAILED {len(failed)}: {failed}",
          flush=True)
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
