"""Read-only development Run-button policy; never execute workflow commands.

Only reviewed synthetic preview / regression commands may be reachable from
the Run button or legacy top-level run. Everything else is manual-only,
including production collectors, DB writers, mail/SMS senders and dry-runs.
Workflow names and isValidation/outputType labels grant no permission.

Keep commands exact: shell parsing/normalizing could hide assignments, command
substitution, redirection or extra commands. A new service requires an explicit
policy review here, not simply a familiar workflow name.
"""
import argparse
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]

DEV_COMMANDS = {
    "python -u scripts/hs2_dev_preview.py": "synthetic-preview",
    "python tests/smoke_test.py": "isolated-regression",
    "python tests/api_test.py": "isolated-regression",
    "python tests/test_hs2_production_boundary.py -v": "isolated-regression",
}


class WorkflowBoundaryError(ValueError):
    """Invalid or unapproved development execution graph."""


def check_config(config):
    """Inspect parsed TOML without imports, expansion, subprocesses or writes.

    Return reachable workflow names for reporting. Unreachable operational
    workflows are intentionally neither inspected for command permission nor
    altered. Their schedules and manual execution remain outside this policy.
    """
    if not isinstance(config, dict):
        raise WorkflowBoundaryError("INVALID_CONFIG")

    def command_allowed(command, location):
        if not isinstance(command, str) or command not in DEV_COMMANDS:
            # Never include command text: it may contain embedded credentials.
            raise WorkflowBoundaryError(f"MANUAL_ONLY_COMMAND: {location}")

    if "run" in config:
        command_allowed(config["run"], "top-level run")

    workflows = config.get("workflows", {})
    if not isinstance(workflows, dict):
        raise WorkflowBoundaryError("INVALID_WORKFLOWS")
    entries = workflows.get("workflow", [])
    if not isinstance(entries, list):
        raise WorkflowBoundaryError("INVALID_WORKFLOW_LIST")
    by_name = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise WorkflowBoundaryError("INVALID_WORKFLOW")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowBoundaryError("INVALID_WORKFLOW_NAME")
        if name in by_name:
            raise WorkflowBoundaryError(f"DUPLICATE_WORKFLOW: {name}")
        by_name[name] = entry

    button = workflows.get("runButton")
    if button is None:
        if "run" not in config:
            raise WorkflowBoundaryError("MISSING_DEFAULT_RUN")
        return ()
    if not isinstance(button, str) or not button.strip():
        raise WorkflowBoundaryError("INVALID_RUN_BUTTON")

    # Iterative DFS supports deep nesting without Python recursion overflow.
    active, finished, reachable = set(), set(), []
    stack = [(button, False)]
    while stack:
        name, exiting = stack.pop()
        if exiting:
            active.remove(name)
            finished.add(name)
            continue
        if name in active:
            raise WorkflowBoundaryError(f"WORKFLOW_CYCLE: {name}")
        if name in finished:
            continue
        if name not in by_name:
            raise WorkflowBoundaryError(f"UNKNOWN_WORKFLOW: {name}")
        entry = by_name[name]
        # Unknown execution options cannot silently extend the allowed graph.
        if set(entry) - {"name", "mode", "author", "metadata", "tasks"}:
            raise WorkflowBoundaryError(f"UNAPPROVED_WORKFLOW_OPTIONS: {name}")
        if "mode" in entry and (
            not isinstance(entry["mode"], str)
            or entry["mode"] not in {"parallel", "sequential"}
        ):
            raise WorkflowBoundaryError(f"INVALID_WORKFLOW_MODE: {name}")
        tasks = entry.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise WorkflowBoundaryError(f"EMPTY_OR_INVALID_TASKS: {name}")
        active.add(name)
        reachable.append(name)
        stack.append((name, True))
        children = []
        for task in tasks:
            if not isinstance(task, dict):
                raise WorkflowBoundaryError(f"INVALID_TASK: {name}")
            if set(task) - {"task", "args", "waitForPort"}:
                raise WorkflowBoundaryError(f"UNAPPROVED_TASK_OPTIONS: {name}")
            kind, args = task.get("task"), task.get("args")
            if kind == "shell.exec":
                command_allowed(args, name)
            elif kind == "workflow.run":
                if not isinstance(args, str) or not args.strip():
                    raise WorkflowBoundaryError(f"INVALID_WORKFLOW_REFERENCE: {name}")
                children.append((args, False))
            else:
                raise WorkflowBoundaryError(f"UNKNOWN_TASK_TYPE: {name}")
        stack.extend(reversed(children))
    return tuple(reachable)


def check_file(path=ROOT / ".replit"):
    with Path(path).open("rb") as source:
        return check_config(tomllib.load(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, default=ROOT / ".replit")
    args = parser.parse_args()
    try:
        reachable = check_file(args.config)
    except (WorkflowBoundaryError, OSError, tomllib.TOMLDecodeError) as error:
        # Parser errors can contain raw configuration text. Report only our
        # own safe diagnostics or the exception type for file/parse failures.
        detail = str(error) if isinstance(error, WorkflowBoundaryError) else type(error).__name__
        print(f"DEV_WORKFLOW_BOUNDARY_FAIL: {detail}", file=sys.stderr)
        return 1
    print(f"DEV_WORKFLOW_BOUNDARY_PASS: {len(reachable)} reachable workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
