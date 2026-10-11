"""Synthetic TOML graph mutations; no collector, provider or database executes."""
import copy
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_dev_workflow_boundary import (
    DEV_COMMANDS, WorkflowBoundaryError, check_config, check_file, main,
)


def run(name):
    return {"task": "workflow.run", "args": name}


def shell(command):
    return {"task": "shell.exec", "args": command}


def workflow(name, *tasks, **options):
    return {"name": name, "tasks": list(tasks), **options}


def fixture(*entries, button="Default"):
    return {"workflows": {"runButton": button, "workflow": list(entries)}}


PREVIEW = "python -u scripts/hs2_dev_preview.py"


class DevWorkflowBoundaryTests(unittest.TestCase):
    def reject(self, config, reason):
        with self.assertRaisesRegex(WorkflowBoundaryError, reason):
            check_config(config)

    def test_current_configuration_passes_without_writing_or_executing(self):
        path = ROOT / ".replit"
        before = path.read_bytes()
        with patch("subprocess.Popen", side_effect=AssertionError("must not execute")), \
                patch("os.system", side_effect=AssertionError("must not execute")):
            reached = check_file(path)
        self.assertIn("Start application", reached)
        self.assertEqual(path.read_bytes(), before)

    def test_renamed_safe_services_and_nested_parallel_sequential_groups_pass(self):
        config = fixture(
            workflow("Default", run("Group"), run("Regression"), mode="parallel"),
            workflow("Group", run("Renamed preview"), mode="sequential"),
            workflow("Renamed preview", shell(PREVIEW)),
            workflow("Regression", *[shell(cmd) for cmd in DEV_COMMANDS if cmd != PREVIEW]),
        )
        original = copy.deepcopy(config)
        self.assertEqual(set(check_config(config)),
                         {"Default", "Group", "Renamed preview", "Regression"})
        self.assertEqual(config, original)

    def test_shared_diamond_and_duplicate_edges_are_not_cycles(self):
        config = fixture(
            workflow("Default", run("A"), run("B"), run("A")),
            workflow("A", run("Preview")), workflow("B", run("Preview")),
            workflow("Preview", shell(PREVIEW)),
        )
        self.assertEqual(len(check_config(config)), 4)

    def test_deep_nesting_uses_no_python_recursion(self):
        entries = [workflow(str(i), run(str(i + 1))) for i in range(1500)]
        entries.append(workflow("1500", shell(PREVIEW)))
        self.assertEqual(len(check_config(fixture(*entries, button="0"))), 1501)

    def test_new_production_command_is_rejected_regardless_of_name_or_labels(self):
        for command in (
            'env DATABASE_URL="$PROD_DATABASE_URL" python new_collector.py',
            "python newly_added_writer.py",
            "python new_mail_sender.py --scheduled",
            "python merge_dev_to_prod.py --dry-run",
            "curl https://example.invalid/send",
        ):
            with self.subTest(command=command):
                self.reject(fixture(
                    workflow("Default", run("Wrapper")),
                    workflow("Wrapper", run("Start application")),
                    workflow("Start application", shell(command),
                             metadata={"isValidation": True, "outputType": "webview"}),
                ), "MANUAL_ONLY_COMMAND")

    def test_unreachable_production_definitions_and_cycles_remain_untouched(self):
        config = fixture(
            workflow("Default", shell(PREVIEW)),
            workflow("Production", shell('env DATABASE_URL="$PROD_DATABASE_URL" python writer.py'),
                     schedule="0 2 * * *"),
            workflow("Sender", shell("python sender.py")),
            workflow("Dormant", run("Dormant")),
        )
        original = copy.deepcopy(config)
        self.assertEqual(check_config(config), ("Default",))
        self.assertEqual(config, original)

    def test_every_real_manual_workflow_fails_if_attached_to_default(self):
        config = tomllib.loads((ROOT / ".replit").read_text())
        safe = set(check_config(config))
        count = 0
        for entry in config["workflows"]["workflow"]:
            if entry["name"] in safe:
                continue
            with self.subTest(workflow=entry["name"]):
                mutated = copy.deepcopy(config)
                default = next(w for w in mutated["workflows"]["workflow"]
                               if w["name"] == mutated["workflows"]["runButton"])
                default["tasks"].append(run(entry["name"]))
                self.reject(mutated, "MANUAL_ONLY_COMMAND|UNAPPROVED_WORKFLOW_OPTIONS")
                count += 1
        self.assertGreater(count, 0)

    def test_self_and_indirect_cycles_fail(self):
        self.reject(fixture(workflow("Default", run("Default"))), "WORKFLOW_CYCLE")
        self.reject(fixture(workflow("Default", run("A")),
                            workflow("A", run("B")), workflow("B", run("Default"))),
                    "WORKFLOW_CYCLE")

    def test_missing_button_target_and_nested_reference_fail(self):
        self.reject(fixture(workflow("Other", shell(PREVIEW))), "UNKNOWN_WORKFLOW")
        self.reject(fixture(workflow("Default", run("Absent"))), "UNKNOWN_WORKFLOW")

    def test_unknown_task_types_and_execution_options_fail(self):
        for task in (
            {"task": "new.executor", "args": PREVIEW},
            {"task": "shell.exec", "args": PREVIEW, "env": {"DATABASE_URL": "synthetic"}},
            {"task": "workflow.run", "args": ["Other"]},
            "invalid",
        ):
            with self.subTest(task=task):
                self.reject(fixture(workflow("Default", task)),
                            "UNKNOWN_TASK_TYPE|UNAPPROVED_TASK_OPTIONS|INVALID_")
        self.reject(fixture(workflow("Default", shell(PREVIEW), newExecutor="writer")),
                    "UNAPPROVED_WORKFLOW_OPTIONS")

    def test_shell_additions_cannot_hide_inside_an_approved_command(self):
        for command in (
            PREVIEW + "; python writer.py", PREVIEW + "\npython sender.py",
            PREVIEW + " && python writer.py", PREVIEW + " | python sender.py",
            "env DATABASE_URL=synthetic " + PREVIEW,
            PREVIEW + " $(python writer.py)", PREVIEW + " > output",
            PREVIEW + " &", PREVIEW + " --new-flag",
        ):
            with self.subTest(command=command):
                self.reject(fixture(workflow("Default", shell(command))), "MANUAL_ONLY_COMMAND")

    def test_top_level_run_checked_even_with_safe_button(self):
        config = fixture(workflow("Default", shell(PREVIEW)))
        config["run"] = "python writer.py"
        self.reject(config, "MANUAL_ONLY_COMMAND")
        config["run"] = PREVIEW
        self.assertEqual(check_config(config), ("Default",))
        self.assertEqual(check_config({"run": PREVIEW}), ())
        self.reject({"run": ["python", "writer.py"]}, "MANUAL_ONLY_COMMAND")

    def test_ambiguous_or_malformed_configuration_fails_closed(self):
        for config, reason in (
            ({}, "MISSING_DEFAULT_RUN"),
            ({"workflows": []}, "INVALID_WORKFLOWS"),
            ({"workflows": {"workflow": {}}}, "INVALID_WORKFLOW_LIST"),
            (fixture(workflow("Default", shell(PREVIEW)), button=""), "INVALID_RUN_BUTTON"),
            (fixture(workflow("Default", shell(PREVIEW)), button=42), "INVALID_RUN_BUTTON"),
            (fixture(workflow("Default", shell(PREVIEW)),
                     workflow("Default", shell(PREVIEW))), "DUPLICATE_WORKFLOW"),
            (fixture({"name": "", "tasks": []}), "INVALID_WORKFLOW_NAME"),
            (fixture(workflow("Default")), "EMPTY_OR_INVALID_TASKS"),
            (fixture({"name": "Default", "tasks": {}}), "EMPTY_OR_INVALID_TASKS"),
            (fixture(workflow("Default", shell(PREVIEW), mode="unknown")), "INVALID_WORKFLOW_MODE"),
            (fixture(workflow("Default", shell(PREVIEW), mode=[])), "INVALID_WORKFLOW_MODE"),
        ):
            with self.subTest(reason=reason):
                self.reject(config, reason)

    def test_cli_parses_synthetic_toml_and_fails_without_printing_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text('''[workflows]
runButton = "Default"
[[workflows.workflow]]
name = "Default"
[[workflows.workflow.tasks]]
task = "shell.exec"
args = "python -u scripts/hs2_dev_preview.py"
''')
            with patch.object(sys, "argv", ["checker", str(path)]):
                self.assertEqual(main(), 0)
                path.write_text(path.read_text().replace(PREVIEW, "secret-marker python writer.py"))
                from io import StringIO
                stderr = StringIO()
                with patch("sys.stderr", stderr):
                    self.assertEqual(main(), 1)
                self.assertIn("MANUAL_ONLY_COMMAND", stderr.getvalue())
                self.assertNotIn("secret-marker", stderr.getvalue())
                path.write_text("not valid toml")
                self.assertEqual(main(), 1)
                path.unlink()
                self.assertEqual(main(), 1)

    def test_offline_suite_registers_as_independent_pure_check(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from run_offline_suite import PURE_UNIT_CHECKS, discover_checks
        name = Path(__file__).name
        self.assertIn(name, PURE_UNIT_CHECKS)
        entries = discover_checks()
        self.assertEqual(sum(key == name for key, _ in entries), 1)
        self.assertIn("--ignore=tests/" + name, dict(entries)["Python pytest"])


if __name__ == "__main__":
    unittest.main()
