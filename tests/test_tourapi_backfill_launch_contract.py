import unittest
from pathlib import Path


class TourApiBackfillLaunchContractTest(unittest.TestCase):
    def test_detached_runner_resolves_generated_run_id(self):
        source = Path("app.py").read_text(encoding="utf-8")
        start = source.index("def _start_detached_sync(")
        end = source.index("\n\n", source.index("return True, 202", start))
        runner = source[start:end]

        self.assertIn('arg == "__RUN_ID__"', runner)
        self.assertIn('status["run_id"]', runner)
        self.assertIn("+ resolved_args", runner)

    def test_tourapi_launch_uses_run_id_placeholder(self):
        source = Path("app.py").read_text(encoding="utf-8")
        start = source.index("def admin_tourapi_image_backfill_run(")
        end = source.index("\n\n", source.index("return jsonify(payload), code", start))
        route = source[start:end]

        self.assertIn('"--run-id", "__RUN_ID__"', route)


if __name__ == "__main__":
    unittest.main()