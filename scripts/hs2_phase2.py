"""No app boot, DSN flags, operational migration, deployment or next-phase command."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hs2_harness import phases

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify","finish"))
    args=parser.parse_args()
    try:
        row=phases.verify() if args.command=="verify" else phases.finish()
        print(json.dumps({k:row.get(k) for k in ("status","test_summary","reason","end")},ensure_ascii=False,indent=2))
        sys.exit(0 if row["status"] in {"PASS","COMPLETE"} else 1)
    except Exception as exc:
        print("BLOCKED:",str(exc))
        sys.exit(1)
