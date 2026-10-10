"""Versioned actual PostgreSQL calendar and append-only snapshot foundation."""
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from hs2_design.domain import Classification, ContractError, StayKind
from hs2_data.repository import require_fixture, save_fixture_snapshot
from hs2_listings.validation import identifier
from hs2_listings.review import public_rows
from .engine import build_snapshot, change, initial, local_date, safe_quote

MIGRATION = Path(__file__).parent / "migrations" / "001.sql"


def migrate(conn):
    require_fixture(conn)
    sha = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with conn.cursor() as c:
        c.execute("SELECT sha256 FROM hs2_dev.migration_receipts WHERE version=7")
        old = c.fetchone()
        if old:
            if old[0] != sha:
                raise ContractError("MIGRATION_RECEIPT_MISMATCH")
            return
        c.execute("SET LOCAL hs2.fixture_cluster='phase2-isolated'")
        c.execute(MIGRATION.read_text())
        c.execute("INSERT INTO hs2_dev.migration_receipts VALUES(7,%s)", (sha,))


def seoul_today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


class CalendarRepository:
    def __init__(self, registrations, *, inventory_is_available, today=seoul_today):
        if not callable(inventory_is_available) or not callable(today):
            raise ValueError("Trusted inventory/clock callbacks required")
        self.registrations, self.inventory_is_available, self.today = registrations, inventory_is_available, today

    def business_date(self):
        today = self.today()
        if type(today) is not date:
            raise ContractError("BUSINESS_CLOCK_REQUIRED")
        return today

    @staticmethod
    def latest(c, application):
        c.execute("""SELECT id,version,source_revision,payload FROM hs2_dev.calendar_versions
            WHERE application_id=%s ORDER BY version DESC LIMIT 1""", (application["id"],))
        row = c.fetchone()
        stale = bool(row and row[2] != application["revision"])
        return dict(version=row[1] if row else 0,
                    source_revision=application["revision"],
                    stale=stale,
                    tariff_version="calendar:" + str(row[0]) if row and not stale else None,
                    calendar=row[3] if row and not stale else initial(application))

    def read(self, who, key):
        with self.registrations.transaction() as c:
            self.registrations.active(c, who)
            application = self.registrations.row(c, key, who)
            return dict(application_id=application["id"], status=application["status"],
                        title=application["payload"]["title"], today=self.business_date().isoformat(),
                        **self.latest(c, application))

    def update(self, who, key, expected, source_revision, command):
        if type(expected) is not int or expected < 0 or type(source_revision) is not int:
            raise ContractError("CALENDAR_REVISION_REQUIRED")
        with self.registrations.transaction() as c:
            self.registrations.active(c, who)
            application = self.registrations.row(c, key, who)
            if application["status"] == "withdrawn":
                raise ContractError("WITHDRAWAL_TERMINAL")
            latest = self.latest(c, application)
            if expected != latest["version"] or source_revision != application["revision"]:
                raise ContractError("STALE_CALENDAR_REVISION")
            updated = change(latest["calendar"], command, self.business_date())
            c.execute("""INSERT INTO hs2_dev.calendar_versions
                (id,application_id,version,source_revision,payload) VALUES(%s,%s,%s,%s,%s)""",
                (str(uuid4()), key, expected + 1, source_revision, json.dumps(updated)))
            self.registrations.event(c, application, who["user_id"], "member", "calendar_version_created")
            return dict(application_id=key, source_revision=source_revision, version=expected + 1,
                        calendar=updated, stale=False, today=self.business_date().isoformat())

    def _snapshot(self, c, application, start, end):
        latest = self.latest(c, application)
        if latest["stale"] or latest["tariff_version"] is None:
            raise ContractError("CURRENT_PRICE_VERSION_REQUIRED")
        check_in, check_out = local_date(start), local_date(end)
        if check_in < self.business_date():
            raise ContractError("FUTURE_STAY_REQUIRED")
        if not application["listing_id"] or application["status"] != "approved":
            raise ContractError("CURRENT_PUBLICATION_REQUIRED")
        c.execute("""SELECT l.pool_id,d.kind,d.evidence_id,d.decision_version FROM hs2_dev.stay_listings l
            JOIN hs2_dev.classification_decisions d ON d.id=l.classification_id
            JOIN hs2_dev.registration_applications a ON a.listing_id=l.id
            JOIN hs2_dev.registration_grants g ON g.id=l.grant_id
            JOIN hs2_fixture_legacy.users u ON u.id=a.user_id
            WHERE l.id=%s AND a.status='approved' AND a.reviewed_revision=a.revision
              AND a.approved_until>clock_timestamp() AND l.status='published' AND g.approved AND u.active""",
            (application["listing_id"],))
        row = c.fetchone()
        if not row:
            raise ContractError("CLASSIFICATION_REQUIRES_REVIEW")
        if self.registrations.context_is_active(application["user_id"], application["context_id"]) is not True:
            raise ContractError("CURRENT_PUBLICATION_REQUIRED")
        if self.inventory_is_available(str(row[0]), check_in, check_out) is not True:
            raise ContractError("INVENTORY_UNAVAILABLE")
        classification = Classification(application["listing_id"], StayKind(row[1]), row[2], row[3])
        snapshot = build_snapshot(classification, check_in, check_out, latest["calendar"],
                                  tariff_version=latest["tariff_version"],
                                  minimum_stay=application["payload"]["min_stay"])
        return snapshot, latest

    def quote(self, public_id, start, end):
        identifier(public_id)
        # Use the original limited view with Phase6 expiry/revision/rights/context
        # checks, not a raw listing lookup that bypasses publication.
        if public_id not in {row["public_id"] for row in public_rows(self.registrations)}:
            raise ContractError("PUBLIC_LISTING_NOT_FOUND")
        with self.registrations.transaction() as c:
            c.execute("SELECT id FROM hs2_dev.registration_applications WHERE public_id=%s", (public_id,))
            match = c.fetchone()
            if not match:
                raise ContractError("PUBLIC_LISTING_NOT_FOUND")
            application = self.registrations.row(c, str(match[0]))
            # Revalidate after acquiring the row lock; edits/withdrawal must not
            # race a preliminary public lookup into a stale quote.
            c.execute("""SELECT 1 FROM hs2_dev.registration_applications a
                JOIN hs2_dev.stay_listings l ON l.id=a.listing_id
                JOIN hs2_dev.registration_grants g ON g.id=l.grant_id
                JOIN hs2_fixture_legacy.users u ON u.id=a.user_id
                WHERE a.id=%s AND a.status='approved' AND a.reviewed_revision=a.revision
                  AND a.approved_until>clock_timestamp() AND l.status='published' AND g.approved AND u.active""",
                (application["id"],))
            if not c.fetchone() or self.registrations.context_is_active(application["user_id"], application["context_id"]) is not True:
                raise ContractError("PUBLIC_LISTING_NOT_FOUND")
            snapshot, _ = self._snapshot(c, application, start, end)
            return safe_quote(public_id, snapshot)

    def freeze_fixture(self, who, key, start, end):
        """Internal developer proof only; does NOT confirm or hold a booking."""
        with self.registrations.transaction() as c:
            self.registrations.active(c, who)
            application = self.registrations.row(c, key, who)
            snapshot, latest = self._snapshot(c, application, start, end)
            c.execute("""INSERT INTO hs2_dev.tariff_versions(id,listing_id,version,payload)
                VALUES(%s,%s,%s,%s) ON CONFLICT(listing_id,version) DO NOTHING""",
                (str(uuid4()), application["listing_id"], snapshot.tariff_version, json.dumps(latest["calendar"])))
            key = str(uuid4())
            # The original adapter enforces the immutable FK-bound line/amount/
            # classification/terms contract. It receives the same transaction.
            save_fixture_snapshot(c.connection, key, snapshot)
            return dict(snapshot_id=key, total_krw=snapshot.total_krw, booking_confirmed=False)

    def consumer_rows(self, values):
        result = []
        for row in public_rows(self.registrations):
            projected = dict(row)
            if values.get("check_in"):
                try:
                    projected["quote"] = self.quote(row["public_id"], values["check_in"], values["check_out"])
                except ContractError:
                    projected["quote"] = None
            result.append(projected)
        return result
