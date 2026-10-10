"""Phase 3 only; no operational or next-phase command."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hs2_harness import phase3

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("verify","finish"));args=parser.parse_args()
    try:
        row=phase3.verify() if args.command=="verify" else phase3.finish()
        print(json.dumps({k:row.get(k) for k in ("status","test_summary","reason","end")},ensure_ascii=False,indent=2))
        sys.exit(0 if row["status"] in {"PASS","COMPLETE"} else 1)
    except Exception as e:
        print("BLOCKED:",str(e));sys.exit(1)
