"""Run the real frontend builder in an owned directory, never switch preview."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch


@contextmanager
def frontend_workspace(root):
    with tempfile.TemporaryDirectory(prefix="frontend-distribution-") as temp:
        workspace = Path(temp)
        static = workspace / "static"
        static.mkdir()
        for html in (root / "static").glob("*.html"):
            shutil.copy2(html, static / html.name)
        shutil.copytree(root / "static/js", static / "js")
        shutil.copytree(root / "static/css", static / "css")
        (workspace / "tests").symlink_to(root / "tests", target_is_directory=True)
        spec = importlib.util.spec_from_file_location(
            "isolated_frontend_builder", root / "scripts/build_frontend.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.ROOT = workspace
        builder.STATIC = static
        builder.JS_SOURCE = static / "js"
        builder.DIST = static / "dist"
        builder.GENERATED = static / "generated"
        builder.MARKER = builder.GENERATED / ".frontend-build.json"
        # A child started with cwd=workspace does not inherit sys.path.insert
        # from smoke_test. Keep imports and offline guards explicit even when
        # this helper is used outside run_offline_suite.
        child_path = os.pathsep.join(filter(None, (
            str(root / "tests/offline_support"), str(root),
            os.environ.get("PYTHONPATH", ""),
        )))
        with patch.dict(os.environ, {
            "PYTHONPATH": child_path,
            "HOMENSTAY_OFFLINE_TESTS": "1",
            "DISABLE_EXTERNAL_NOTIFICATIONS": "1",
            "SKIP_STARTUP_SCHEMA_INIT": "1",
            "SKIP_APP_BOOT_TASKS": "1",
        }):
            yield builder


@contextmanager
def serve_frontend_workspace(server, builder):
    """Exercise unmodified Flask routing against the isolated real release."""
    with (
        patch.object(server, "__file__", str(builder.ROOT / "app.py")),
        patch.object(server.app, "_static_folder", str(builder.STATIC)),
        patch.object(server, "_FRONTEND_BUILD_MARKER", str(builder.MARKER)),
        patch.object(server, "_FRONTEND_RELEASE_CACHE", {"mtime_ns": None, "release": None}),
    ):
        yield
