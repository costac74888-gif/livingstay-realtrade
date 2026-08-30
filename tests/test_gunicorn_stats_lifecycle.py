"""Regression tests for non-blocking Gunicorn master-stat worker startup."""

import importlib.util
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("FLASK_SECRET_KEY", "gunicorn-lifecycle-test-secret")

import db  # noqa: E402

with patch.object(db, "init_db"):
    import app as app_module  # noqa: E402


def _load_gunicorn_config():
    spec = importlib.util.spec_from_file_location(
        "gunicorn_stats_lifecycle_config",
        os.path.join(ROOT, "gunicorn.conf.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GunicornStatsLifecycleTests(unittest.TestCase):
    def test_post_fork_starts_async_stats_worker_without_sync_rebuild(self):
        config = _load_gunicorn_config()
        start_worker = Mock()
        start_badge_worker = Mock()
        fake_app_module = SimpleNamespace(
            start_master_stats_worker=start_worker,
            start_badge_waitlist_worker=start_badge_worker,
        )
        server = SimpleNamespace(log=Mock())
        worker = SimpleNamespace(pid=12345)

        with patch.dict(sys.modules, {"app": fake_app_module}):
            config.post_fork(server, worker)

        start_worker.assert_called_once_with()
        start_badge_worker.assert_called_once_with()
        server.log.exception.assert_not_called()

    def test_worker_service_defers_cold_rebuild_to_background_loop(self):
        with (
            patch.object(app_module, "_rebuild_master_stats") as rebuild,
            patch.object(app_module, "_master_stats_background_loop") as background_loop,
        ):
            app_module._master_stats_warm_then_loop()

        rebuild.assert_not_called()
        background_loop.assert_called_once_with()

    def test_background_loop_does_not_rebuild_empty_cache_until_requested(self):
        class StopLoop(Exception):
            pass

        original_cache = dict(app_module._MASTER_STATS_CACHE)
        refresh_was_set = app_module._MASTER_STATS_NEEDS_REFRESH.is_set()
        app_module._MASTER_STATS_NEEDS_REFRESH.clear()
        try:
            app_module._MASTER_STATS_CACHE.update({
                "ts": 0.0,
                "data": {},
                "sections": {},
                "invalidation_token": None,
            })
            with (
                patch.object(app_module, "_master_stats_schedule_revalidation") as schedule,
                patch.object(app_module.time, "sleep", side_effect=StopLoop),
                self.assertRaises(StopLoop),
            ):
                app_module._master_stats_background_loop()
            schedule.assert_not_called()
        finally:
            app_module._MASTER_STATS_CACHE.clear()
            app_module._MASTER_STATS_CACHE.update(original_cache)
            if refresh_was_set:
                app_module._MASTER_STATS_NEEDS_REFRESH.set()

    def test_worker_service_is_started_as_a_daemon_thread(self):
        worker_thread = Mock()
        with patch.object(app_module.threading, "Thread", return_value=worker_thread) as thread:
            result = app_module.start_master_stats_worker()

        self.assertIs(result, worker_thread)
        thread.assert_called_once_with(
            target=app_module._master_stats_warm_then_loop,
            daemon=True,
            name="master-stats-worker",
        )
        worker_thread.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()