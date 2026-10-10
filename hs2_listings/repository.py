"""Persistent transactional fixture repository; explicit trusted connection port."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from hs2_data.repository import require_fixture
from hs2_design.domain import ContractError
from .validation import actor, identifier, payload, revision

MIGRATION = Path(__file__).parent / "migrations" / "001.sql"


def migrate(conn):
    require_fixture(conn)
    sha = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=6")
        old = c.fetchone()
        if old:
            if old[0] != sha:
                raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute("SET LOCAL hs2.fixture_cluster='phase2-isolated'")
        c.execute(MIGRATION.read_text())
        c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(6,%s)", (sha,))


class Repository:
    def __init__(self, connect, context_is_active):
        if not callable(connect) or not callable(context_is_active):
            raise ValueError("Trusted connection and fresh membership ports required")
        self.connect, self.context_is_active = connect, context_is_active

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            require_fixture(conn)
            with conn, conn.cursor() as c:
                yield c
        finally:
            conn.close()

    def active(self, c, who):
        actor(who)
        if self.context_is_active(who["user_id"], who["context_id"]) is not True:
            raise ContractError("APPROVED_BUSINESS_REQUIRED")
        c.execute("SELECT active FROM hs2_fixture_legacy.users WHERE id=%s FOR SHARE", (who["user_id"],))
        row = c.fetchone()
        if not row or row[0] is not True:
            raise ContractError("ACTIVE_MEMBER_REQUIRED")

    @staticmethod
    def row(c, key, who=None):
        identifier(key)
        c.execute("SELECT row_to_json(a) FROM hs2_dev.registration_applications a WHERE id=%s FOR UPDATE", (key,))
        row = c.fetchone()
        if not row or (who and (row[0]["user_id"], row[0]["context_id"]) != (who["user_id"], who["context_id"])):
            raise ContractError("APPLICATION_NOT_FOUND")
        return row[0]

    @staticmethod
    def event(c, row, uid, kind, event):
        c.execute("INSERT INTO hs2_dev.registration_events(application_id,revision,actor_id,actor_kind,event) VALUES(%s,%s,%s,%s,%s)",
                  (row["id"], row["revision"], uid, kind, event))

    @staticmethod
    def photos(c, who, data):
        for key in data["photos"]:
            c.execute("SELECT 1 FROM hs2_dev.registration_photos WHERE id=%s AND user_id=%s AND context_id=%s",
                      (key, who["user_id"], who["context_id"]))
            if not c.fetchone():
                raise ContractError("OWNED_PHOTO_REQUIRED")

    @staticmethod
    def unpublish(c, row):
        if row["listing_id"]:
            c.execute("SELECT set_config('hs2.actor_user',%s,true)", (str(row["user_id"]),))
            c.execute("UPDATE hs2_dev.stay_listings SET status='withdrawn' WHERE id=%s", (row["listing_id"],))

    def create(self, who, candidate, raw):
        data = payload(raw)
        with self.transaction() as c:
            self.active(c, who)
            c.execute("SELECT 1 FROM hs2_dev.candidates WHERE id=%s AND identity_confirmed FOR SHARE", (identifier(candidate),))
            if not c.fetchone():
                raise ContractError("CONFIRMED_REFERENCE_REQUIRED")
            self.photos(c, who, data)
            key = str(uuid4())
            c.execute("""INSERT INTO hs2_dev.registration_applications
                (id,user_id,context_id,candidate_id,revision,status,payload)
                VALUES(%s,%s,%s,%s,1,'draft',%s)""",
                (key, who["user_id"], who["context_id"], candidate, json.dumps(data)))
            row = self.row(c, key, who)
            self.event(c, row, who["user_id"], "member", "created")
            return row

    def read(self, who, key):
        with self.transaction() as c:
            self.active(c, who)
            return self.row(c, key, who)

    def list(self, who=None):
        with self.transaction() as c:
            if who:
                self.active(c, who)
                c.execute("SELECT row_to_json(a) FROM hs2_dev.registration_applications a WHERE user_id=%s AND context_id=%s ORDER BY updated_at DESC LIMIT 200",
                          (who["user_id"], who["context_id"]))
            else:
                c.execute("SELECT row_to_json(a) FROM hs2_dev.registration_applications a ORDER BY updated_at DESC LIMIT 200")
            return [r[0] for r in c.fetchall()]

    def change(self, who, key, expected, action, raw=None):
        revision(expected)
        with self.transaction() as c:
            self.active(c, who)
            row = self.row(c, key, who)
            if row["revision"] != expected:
                raise ContractError("STALE_REVISION")
            if row["status"] == "withdrawn":
                raise ContractError("WITHDRAWAL_TERMINAL")
            data, state, rev = row["payload"], row["status"], row["revision"]
            if action == "save":
                data = payload(raw)
                self.photos(c, who, data)
                self.unpublish(c, row)
                state, rev = "draft", rev + 1
            elif action == "submit":
                if state == "submitted":
                    return row
                if state not in {"draft", "rejected"}:
                    raise ContractError("SUBMISSION_STATE_REQUIRED")
                data = payload(data, complete=True)
                self.photos(c, who, data)
                state = "submitted"
            elif action == "withdraw":
                self.unpublish(c, row)
                state = "withdrawn"
            else:
                raise ContractError("INVALID_ACTION")
            c.execute("""UPDATE hs2_dev.registration_applications SET payload=%s,status=%s,revision=%s,
                reviewed_revision=NULL,approved_until=NULL,updated_at=clock_timestamp() WHERE id=%s""",
                (json.dumps(data), state, rev, key))
            row = self.row(c, key, who)
            self.event(c, row, who["user_id"], "member", action)
            return row

    def upload(self, who, content, mime):
        valid = ((mime == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or
                 (mime == "image/jpeg" and content.startswith(b"\xff\xd8\xff")) or
                 (mime == "image/webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP"))
        if not valid or not 24 <= len(content) <= 524288:
            raise ContractError("PHOTO_FORMAT_OR_SIZE")
        with self.transaction() as c:
            self.active(c, who)
            c.execute("SELECT count(*) FROM hs2_dev.registration_photos WHERE user_id=%s AND context_id=%s", (who["user_id"], who["context_id"]))
            if c.fetchone()[0] >= 100:
                raise ContractError("PHOTO_LIMIT")
            key = str(uuid4())
            c.execute("INSERT INTO hs2_dev.registration_photos VALUES(%s,%s,%s,%s,%s)",
                      (key, who["user_id"], who["context_id"], mime, content))
            return dict(id=key, url="/hs2/listings/photos/" + key)

    def photo(self, who, key, admin=False):
        with self.transaction() as c:
            if who:
                self.active(c, who)
            c.execute("SELECT user_id,context_id,mime,content FROM hs2_dev.registration_photos WHERE id=%s", (identifier(key),))
            row = c.fetchone()
            if not row or (not admin and (row[0], row[1]) != (who["user_id"], who["context_id"])):
                raise ContractError("PHOTO_NOT_FOUND")
            return row[2], bytes(row[3])
