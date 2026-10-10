"""Fixture-only migration/data adapter. No URL/env DSN or live application hooks."""
from dataclasses import asdict
from datetime import date
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from hs2_design.domain import ContractError

MIGRATIONS = Path(__file__).parent / "migrations"


def connect_fixture():
    """The test guard restricts this native driver call to its owned UNIX socket."""
    import psycopg2
    host = os.environ.get("HS2_FIXTURE_SOCKET", "")
    if not host.startswith("/tmp/hs2-pg-") or not Path(host, ".hs2-fixture").is_file():
        raise ContractError("OWNED_FIXTURE_SOCKET_REQUIRED")
    return psycopg2.connect(host=host, port=55439, user="hs2_fixture",
                           dbname="postgres", password="", connect_timeout=5,
                           sslmode="disable")


def require_fixture(conn):
    host = conn.get_dsn_parameters().get("host", "")
    if (host != os.environ.get("HS2_FIXTURE_SOCKET")
            or not host.startswith("/tmp/hs2-pg-")
            or not Path(host, ".hs2-fixture").is_file()):
        raise ContractError("OWNED_FIXTURE_SOCKET_REQUIRED")


def migrate(conn, direction="up"):
    require_fixture(conn)
    if direction not in {"up", "down"}:
        raise ContractError("UNKNOWN_MIGRATION_DIRECTION")
    up = (MIGRATIONS / "001_up.sql").read_bytes()
    sha = hashlib.sha256(up).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SET LOCAL hs2.fixture_cluster='phase2-isolated'")
        cur.execute("SELECT to_regnamespace('hs2_dev')")
        exists = cur.fetchone()[0] is not None
        if exists:
            cur.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=1")
            row = cur.fetchone()
            if row is None or row[0] != sha:
                raise ContractError("MIGRATION_RECEIPT_MISMATCH")
        if (direction == "up" and exists) or (direction == "down" and not exists):
            return "ALREADY_APPLIED" if exists else "ALREADY_REVERTED"
        cur.execute((MIGRATIONS / f"001_{direction}.sql").read_text())
        if direction == "up":
            cur.execute("INSERT INTO hs2_dev.migration_receipts VALUES(1,%s)", (sha,))
    return "APPLIED" if direction == "up" else "REVERTED"


class FixtureRepository:
    def __init__(self, conn, actor_id):
        require_fixture(conn)
        if type(actor_id) is not int or actor_id <= 0:
            raise ContractError("TRUSTED_FIXTURE_ACTOR_REQUIRED")
        self.conn, self.actor_id = conn, actor_id
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('hs2.actor_user',%s,true)", (str(actor_id),))

    def create_draft(self, *, listing_id, public_id, building_id, pool_id, grant_id):
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO hs2_dev.stay_listings
                (id,public_id,registered_building_id,creator_user_id,pool_id,grant_id)
                VALUES(%s,%s,%s,%s,%s,%s)""",
                (listing_id, public_id, building_id, self.actor_id, pool_id, grant_id))

    def change_status(self, listing_id, status, decision_id=None):
        with self.conn.cursor() as cur:
            cur.execute("""UPDATE hs2_dev.stay_listings
                SET status=%s,classification_id=COALESCE(%s,classification_id)
                WHERE id=%s AND creator_user_id=%s RETURNING id""",
                (status, decision_id, listing_id, self.actor_id))
            if cur.fetchone() is None:
                raise ContractError("OWNED_LISTING_REQUIRED")

    def limited_listings(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT public_id,stay_kind,location_precision FROM hs2_dev.limited_stay_listings")
            return [dict(public_id=str(row[0]), stay_kind=row[1], location_precision=row[2])
                    for row in cur.fetchall()]


def save_fixture_snapshot(conn, snapshot_id, snapshot):
    """Persist a resolved design fixture only. This does NOT confirm a booking."""
    require_fixture(conn)
    def encode(value):
        if isinstance(value, (date, UUID)):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        raise TypeError("unsupported snapshot component")
    payload = asdict(snapshot)
    payload["total_krw"] = snapshot.total_krw
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO hs2_dev.price_snapshots
            (id,listing_id,check_in,check_out,kind,currency,tariff_version,terms_version,
             classification_evidence,classification_version,total_krw,payload)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (snapshot_id, snapshot.listing_id, snapshot.check_in, snapshot.check_out,
             snapshot.kind.value, snapshot.currency, snapshot.tariff_version,
             snapshot.terms_version, snapshot.classification_evidence,
             snapshot.classification_version, snapshot.total_krw, json.dumps(payload, default=encode)))
