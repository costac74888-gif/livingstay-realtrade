"""TLS visitor server for owned regression only; never accepts a real DB."""
import os
from pathlib import Path
from werkzeug.serving import run_simple

socket = os.environ.get("HOMENSTAY_LEGACY_SOCKET", "")
if not socket.startswith("/tmp/homenstay-legacy-pg-") or not Path(socket, ".owned").is_file():
    raise SystemExit("Owned regression server capability missing")
from app import app

run_simple("127.0.0.1", int(os.environ["OWNED_REGRESSION_PORT"]), app,
           threaded=True, ssl_context="adhoc")
