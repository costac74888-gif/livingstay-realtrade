#!/usr/bin/env python3
"""Offline development gate CLI. No command can deploy, migrate or charge."""
import argparse
import json
import signal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hs2_harness import core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("self-check")
    for name in ["start", "verify", "finish"]:
        sub = commands.add_parser(name)
        sub.add_argument("stage", type=int)
        if name == "verify":
            sub.add_argument("--note", required=True, help="Changes and review context; no PII/secrets")
    gate = commands.add_parser("request-approval")
    gate.add_argument("kind", choices=["production_migration", "live_pg_settlement", "production_publish"])
    gate.add_argument("--note", required=True, help="Requested scope only; no approval/execution")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = core.load(core.STATE)
        elif args.command == "self-check":
            result = core.self_check()
        elif args.command == "start":
            core.start_stage(args.stage)
            result = {"status": "IN_PROGRESS"}
        elif args.command == "verify":
            result = core.verify_stage(args.stage, args.note)
        elif args.command == "finish":
            core.finish_stage(args.stage)
            result = {"status": "COMPLETE"}
        else:
            result = core.request_approval(args.kind, args.note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") not in {"FAIL", "BLOCKED"} else 1
    except core.GateError as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise SystemExit("Harness interrupted; not a PASS")
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
