"""Join two disjoint current-source suites; never replace failed historical runs."""
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts/hs2-rebuild"


def read(path):
    return json.loads(path.read_text())


def main():
    directories = []
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        directories = []
        for name in ("regression-current-a", "regression-current-b"):
            runs = list((OUT / name).glob("*/source-preservation.json"))
            if runs:
                directories.append(runs[-1].parent)
        if len(directories) == 2:
            break
        time.sleep(10)
    if len(directories) != 2:
        raise RuntimeError("Current-source suite incomplete; do not deliver partial as complete")
    before = [read(p / "source-before.json") for p in directories]
    if before[0] != before[1]:
        raise RuntimeError("Suite shards measured different sources")
    rows = [row for p in directories for row in read(p / "summary.json")]
    names = [row["name"] for row in rows]
    prior = next((OUT / "regression-final-complete").glob("*/summary.json"))
    expected = [row["name"] for row in read(prior)]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise RuntimeError("Incomplete or duplicate whole-suite coverage")
    rows.sort(key=lambda row: expected.index(row["name"]))
    unchanged = all(read(p / "source-preservation.json")["unchanged"] for p in directories)
    changed_now = [name for name, digest in before[0].items()
                   if not (ROOT / name).is_file()
                   or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    if changed_now:
        raise RuntimeError("Measured source changed before aggregation")
    target = OUT / "regression-current-combined" / "whole-current"
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (target / "source-preservation.json").write_text(json.dumps({
        "unchanged": unchanged, "files_checked": len(before[0]), "changed": [],
        "disjoint_shards": [str(p.relative_to(ROOT)) for p in directories],
        "exact_whole_suite_coverage": len(rows),
    }, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": len(rows), "passed": sum(r["exit_code"] == 0 for r in rows),
                      "failed": [r["name"] for r in rows if r["exit_code"]],
                      "source_preserved": unchanged}))


if __name__ == "__main__":
    main()
