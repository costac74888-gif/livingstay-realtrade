"""Owned-only substitute for gunicorn: inspect the app selected by start-prod."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hs2_production_boundary import (
    BoundaryError, inspect_app, inspect_environment, reject_fixture_call,
)


def main():
    # Do not rely on sitecustomize exceptions, which Python can ignore.
    import psycopg2
    if (os.environ.get("HOMENSTAY_OFFLINE_TESTS") != "1"
            or psycopg2.connect.__module__ != "sitecustomize"
            or not Path(os.environ.get("HOMENSTAY_LEGACY_SOCKET", ""), ".owned").is_file()):
        raise BoundaryError("OWNED_PROBE_GUARD_REQUIRED")
    if sys.argv[-1:] != ["app:app"]:
        raise BoundaryError("UNAPPROVED_PRODUCTION_ENTRYPOINT")
    expected_database = os.environ["PROD_DATABASE_URL"]
    inspect_environment(os.environ, expected_database)
    sys.setprofile(reject_fixture_call)
    try:
        import app as server
        inspect_app(server.app, Path(os.environ["HS2_PRODUCTION_SOURCE_ROOT"]))
        inspect_environment(os.environ, expected_database)
    finally:
        sys.setprofile(None)
    print("PRODUCTION_BOUNDARY_PASS: registered app only; no real PG verification")


if __name__ == "__main__":
    try:
        main()
    except BoundaryError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(42)
