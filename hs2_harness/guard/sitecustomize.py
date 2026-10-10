"""Defense-in-depth for reviewed Python checks, NOT a hostile-code sandbox."""
import importlib.abc
import socket
import sys
import os

os.environ["HS2_HARNESS_GUARD"] = "1"


def denied(*args, **kwargs):
    raise RuntimeError("HS2 harness: network and database access are forbidden")


socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied


class BlockApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"app", "psycopg", "asyncpg", "pg8000"}:
            raise ImportError("HS2 harness: application boot / DB driver forbidden")


sys.meta_path.insert(0, BlockApplication())
try:
    import psycopg2
    psycopg2.connect = denied
    from psycopg2 import _psycopg
    _psycopg.connect = denied
except ImportError:
    pass

# Do not permit children that could circumvent the guard (curl/psql/gunicorn).
import subprocess
subprocess.Popen = denied
os.system = denied
os.execve = denied
