"""Legacy HTTP/SQL tests may reach only their temporary UNIX PostgreSQL."""
import os
from pathlib import Path
import socket
import sys

root = os.environ.get("HOMENSTAY_LEGACY_SOCKET", "")
if not root.startswith("/tmp/homenstay-legacy-pg-") or not Path(root, ".owned").is_file():
    # Python suppresses ordinary sitecustomize exceptions and continues.
    # Exit the interpreter instead of failing open into application imports.
    print("Owned legacy PostgreSQL capability required", file=sys.stderr)
    os._exit(78)
try:
    import psycopg2
except Exception:
    print("Owned legacy PostgreSQL driver guard unavailable", file=sys.stderr)
    os._exit(78)
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
native_connect = psycopg2._connect


def owned_connect(dsn=None, *args, **kwargs):
    if args:
        raise RuntimeError("Unreviewed PostgreSQL connection")
    factories = {name: kwargs.pop(name) for name in
                 ("cursor_factory", "connection_factory") if name in kwargs}
    config = psycopg2.extensions.parse_dsn(
        psycopg2.extensions.make_dsn(dsn, **kwargs))
    expected = dict(host=root, port="55438", user="legacy_fixture",
                    dbname="postgres", sslmode="disable")
    if any(config.get(k) != v for k, v in expected.items()) or config.get("password"):
        raise RuntimeError("Only owned UNIX PostgreSQL is permitted")
    cursor_factory = factories.pop("cursor_factory", None)
    connection = native_connect(psycopg2.extensions.make_dsn(**config), **factories)
    if cursor_factory is not None:
        connection.cursor_factory = cursor_factory
    return connection


psycopg2.connect = owned_connect
psycopg2._connect = owned_connect
psycopg2._psycopg.connect = owned_connect
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex


def unix_only(self, target):
    if self.family != socket.AF_UNIX or not str(target).startswith(root + "/"):
        raise OSError("Owned legacy test: all TCP and foreign sockets denied")
    return original_connect(self, target)


def unix_only_ex(self, target):
    if self.family != socket.AF_UNIX or not str(target).startswith(root + "/"):
        raise OSError("Owned legacy test: all TCP and foreign sockets denied")
    return original_connect_ex(self, target)


socket.socket.connect = unix_only
socket.socket.connect_ex = unix_only_ex
