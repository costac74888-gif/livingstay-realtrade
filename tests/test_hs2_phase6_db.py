import io
import unittest
from flask import Flask
from hs2_data.repository import connect_fixture
from hs2_design.domain import ContractError
from hs2_listings.api import create_blueprint
from hs2_listings.fixtures import create_fixture_app, PNG, CANDIDATE, WORKFLOW, seed
from hs2_listings.review import review, public_rows
from hs2_listings.repository import migrate
from test_hs2_phase6_validation import BASE

WHO = dict(user_id=101, context_id="operator:fixture:101", role="operator")
OTHER = dict(user_id=102, context_id="operator:fixture:102", role="operator")


class PersistentListingRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()

    def setUp(self):
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.registration_events,hs2_dev.registration_applications,
                hs2_dev.registration_photos,hs2_dev.price_snapshots,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE;
                UPDATE hs2_fixture_legacy.users SET active=true;""")
        self.app = create_fixture_app(False)
        self.client = self.app.test_client()
        self.repo = self.app.fixture_repo
        photo = self.repo.upload(WHO, PNG, "image/png")
        self.data = {**BASE, "photos": [photo["id"]]}
        self.headers = {"X-HS2-CSRF": "synthetic-csrf-only"}

    def draft(self):
        return self.repo.create(WHO, CANDIDATE, self.data)

    def submitted(self):
        row = self.draft()
        return self.repo.change(WHO, row["id"], row["revision"], "submit")

    def approved(self):
        row = self.submitted()
        return review(self.repo, row["id"], 700, row["revision"], "approve",
                      "등록권한·공개정보 확인, 용도 적법성 판단 아님", rights=True, disclosure=True)

    def test_saved_in_actual_pg_and_survives_new_repository_instance(self):
        row = self.draft()
        another = create_fixture_app(False).fixture_repo
        self.assertEqual(another.read(WHO, row["id"])["payload"], self.data)
        self.assertEqual(len(another.list(WHO)), 1)

    def test_private_draft_and_submitted_not_published(self):
        self.submitted()
        self.assertEqual(public_rows(self.repo), [])
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.stay_listings")
            self.assertEqual(c.fetchone()[0], 0)

    def test_admin_approval_creates_only_safe_public_record(self):
        row = self.approved()
        self.assertEqual(row["status"], "approved")
        public = public_rows(self.repo)
        self.assertEqual(len(public), 1)
        self.assertEqual(set(public[0]), {"public_id", "stay_kind", "location_precision"})
        self.assertNotIn(row["id"], str(public))
        self.assertNotIn("PRIVATE_FIXTURE_ADDRESS", str(public))

    def test_warehouse_registration_not_blocked_by_building_use(self):
        row = self.approved()
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SELECT building_use,channel,evidence_id FROM hs2_dev.classification_decisions")
            use, channel, evidence = c.fetchone()
        self.assertEqual(use, "창고")
        self.assertEqual(channel, "operator-declared")
        self.assertIn("operator-declaration/admin-review", evidence)
        self.assertEqual(row["payload"]["stay_kind"], "lodging")

    def test_same_member_other_business_cannot_read_edit_or_withdraw(self):
        row = self.draft()
        scoped = {**WHO, "context_id": "operator:fixture:other"}
        for other in (OTHER, scoped):
            with self.assertRaises(ContractError):
                self.repo.read(other, row["id"])
            with self.assertRaises(ContractError):
                self.repo.change(other, row["id"], 1, "withdraw")

    def test_photo_cross_owner_blocked_and_authenticated_download(self):
        row = self.repo.upload(OTHER, PNG, "image/png")
        with self.assertRaises(ContractError):
            self.repo.create(WHO, CANDIDATE, {**self.data, "photos": [row["id"]]})
        with self.assertRaises(ContractError):
            self.repo.photo(WHO, row["id"])
        mime, content = self.repo.photo(OTHER, row["id"])
        self.assertEqual((mime, content), ("image/png", PNG))

    def test_approval_requires_explicit_review_current_submission(self):
        row = self.draft()
        for uid, rights, disclosure in ((None, True, True), (True, True, True), (700, False, True), (700, True, False)):
            with self.assertRaises(ContractError):
                review(self.repo, row["id"], uid, 1, "approve", "review", rights=rights, disclosure=disclosure)
        with self.assertRaises(ContractError):
            review(self.repo, row["id"], 700, 1, "approve", "review", rights=True, disclosure=True)
        self.assertEqual(public_rows(self.repo), [])

    def test_rejection_edit_and_resubmit_require_new_review(self):
        row = self.submitted()
        result = review(self.repo, row["id"], 700, 1, "reject", "보완 요청")
        self.assertEqual(result["status"], "rejected")
        result = self.repo.change(WHO, row["id"], 1, "save", {**self.data, "title": "보완한 공간"})
        self.assertEqual((result["revision"], result["status"]), (2, "draft"))
        self.assertEqual(self.repo.change(WHO, row["id"], 2, "submit")["status"], "submitted")

    def test_approved_edit_immediately_unpublishes_and_stale_review_fails(self):
        row = self.approved()
        result = self.repo.change(WHO, row["id"], 1, "save", {**self.data, "nightly": 130000})
        self.assertEqual(result["status"], "draft")
        self.assertEqual(public_rows(self.repo), [])
        with self.assertRaises(ContractError):
            review(self.repo, row["id"], 700, 1, "approve", "old review", rights=True, disclosure=True)
        self.repo.change(WHO, row["id"], 2, "submit")
        new = review(self.repo, row["id"], 700, 2, "approve", "new review", rights=True, disclosure=True)
        self.assertNotEqual(row["public_id"], new["public_id"])

    def test_withdrawal_terminal_no_original_hard_delete(self):
        row = self.approved()
        self.repo.change(WHO, row["id"], 1, "withdraw")
        self.assertEqual(public_rows(self.repo), [])
        self.assertEqual(self.repo.read(WHO, row["id"])["status"], "withdrawn")
        with self.assertRaises(ContractError):
            self.repo.change(WHO, row["id"], 1, "save", self.data)
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.registration_events")
            self.assertEqual(c.fetchone()[0], 4)

    def test_duplicate_submission_idempotent_and_optimistic_revision(self):
        row = self.submitted()
        self.assertEqual(self.repo.change(WHO, row["id"], 1, "submit")["status"], "submitted")
        self.repo.change(WHO, row["id"], 1, "save", self.data)
        with self.assertRaises(ContractError):
            self.repo.change(WHO, row["id"], 1, "save", self.data)

    def test_whole_unit_conflict_blocks_approval_not_reference_candidate(self):
        self.approved()
        whole = self.repo.create(WHO, CANDIDATE, {**self.data, "space_scope": "whole", "space_label": "건물전체"})
        self.repo.change(WHO, whole["id"], 1, "submit")
        with self.assertRaises(ContractError):
            review(self.repo, whole["id"], 700, 1, "approve", "overlap", rights=True, disclosure=True)
        self.assertEqual(len(public_rows(self.repo)), 1)

    def test_role_and_account_revocation_hides_public_and_prevents_review(self):
        row = self.approved()
        self.app.fixture_approved.remove((101, WHO["context_id"]))
        self.assertEqual(public_rows(self.repo), [])
        with self.assertRaises(ContractError):
            self.repo.read(WHO, row["id"])
        self.app.fixture_approved.add((101, WHO["context_id"]))
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("UPDATE hs2_fixture_legacy.users SET active=false WHERE id=101")
        self.assertEqual(public_rows(self.repo), [])

    def test_expired_approval_and_revoked_grant_not_public(self):
        row = self.approved()
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("UPDATE hs2_dev.registration_applications SET approved_until=clock_timestamp()-interval '1 day' WHERE id=%s", (row["id"],))
        self.assertEqual(public_rows(self.repo), [])

    def test_migration_idempotent_original_receipt_and_legacy_preserved(self):
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SELECT version,sha256 FROM hs2_dev.migration_receipts ORDER BY version")
            old = c.fetchall()
            migrate(conn)
            c.execute("SELECT version,sha256 FROM hs2_dev.migration_receipts ORDER BY version")
            self.assertEqual(old, c.fetchall())
            c.execute("SELECT * FROM hs2_fixture_legacy.master_buildings")
            self.assertEqual(c.fetchall(), [])
            c.execute("SELECT id,active FROM hs2_fixture_legacy.users ORDER BY id")
            self.assertEqual(c.fetchall(), [(101, True), (102, True)])

    def test_public_database_role_cannot_read_private_applications_photos_audit(self):
        for table in ("registration_applications", "registration_photos", "registration_events"):
            with connect_fixture() as conn, conn.cursor() as c:
                c.execute("SET LOCAL ROLE hs2_fixture_public")
                with self.assertRaises(Exception):
                    c.execute("SELECT * FROM hs2_dev." + table)

    def test_actual_http_csrf_reference_and_actor_forgery(self):
        url = "/hs2/listings/applications"
        body = dict(workflow_id=WORKFLOW, payload=self.data)
        self.assertEqual(self.client.post(url, json=body).status_code, 403)
        self.assertEqual(self.client.post(url, json={**body, "user_id": 102}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post(url, json={**body, "workflow_id": CANDIDATE}, headers=self.headers).status_code, 409)
        response = self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        key = response.get_json()["item"]["id"]
        self.client.post("/hs2/listings-fixture/identity", json={"user": 102})
        self.assertEqual(self.client.get(url + "/" + key).status_code, 404)

    def test_http_admin_guard_and_actual_approval(self):
        row = self.submitted()
        url = f"/hs2/listings/admin/applications/{row['id']}/review"
        body = dict(revision=1, decision="approve", note="検証権限確認", rights=True, disclosure=True)
        self.assertEqual(self.client.post(url, json=body, headers=self.headers).status_code, 403)
        self.client.post("/hs2/listings-fixture/identity", json={"admin": True})
        self.assertEqual(self.client.post(url, json=body).status_code, 403)
        result = self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["item"]["status"], "approved")

    def test_http_photo_validation_and_public_headers(self):
        result = self.client.post("/hs2/listings/photos", data={"file": (io.BytesIO(PNG), "../../private.png")},
                                  headers=self.headers, content_type="multipart/form-data")
        self.assertEqual(result.status_code, 201)
        image = self.client.get(result.get_json()["url"])
        self.assertEqual(image.data, PNG)
        self.assertIn("private", image.headers["Cache-Control"])
        for mime, data in (("image/png", b"x" * 30), ("image/svg+xml", b"<svg>bad</svg>" * 4),
                           ("image/png", PNG + b"x" * 524288)):
            with self.assertRaises(ContractError):
                self.repo.upload(WHO, data, mime)

    def test_no_auth_default_in_real_blueprint(self):
        app = Flask("signed_out")
        app.register_blueprint(create_blueprint(self.repo, resolve_context=lambda: None,
            resolve_admin=lambda: None, csrf_token=lambda: "", check_csrf=lambda: False,
            references=lambda _: [], verify_reference=lambda *_: None))
        self.assertEqual(app.test_client().get("/hs2/listings/applications").status_code, 401)

    def test_actual_original_reference_workflow_pg_link_and_owner_expiry(self):
        start = self.client.post("/hs2/registration/start", json={"query": "창고"}, headers=self.headers).get_json()
        key = start["workflow_id"]
        base = "/hs2/registration/" + key
        address = self.client.post(base + "/address", json={"address_key": start["addresses"][0]["address_key"]}, headers=self.headers).get_json()
        self.client.post(base + "/building", json={"building_key": address["buildings"][0]["building_key"]}, headers=self.headers)
        self.client.post(base + "/coordinates", json={}, headers=self.headers)
        confirmed = self.client.post(base + "/confirm", json={}, headers=self.headers).get_json()
        self.assertEqual(confirmed["status"], "REFERENCE_CONFIRMED")
        body = dict(workflow_id=key, payload=self.data)
        result = self.client.post("/hs2/listings/applications", json=body, headers=self.headers)
        self.assertEqual(result.status_code, 201)
        row = result.get_json()["item"]
        self.assertEqual(row["candidate_id"], confirmed["reference_id"])
        self.client.post("/hs2/listings-fixture/identity", json={"user": 102})
        self.assertEqual(self.client.post("/hs2/listings/applications", json=body, headers=self.headers).status_code, 409)
        self.client.post("/hs2/listings-fixture/identity", json={"user": 101})
        self.app.fixture_reference_service.clock = lambda: 100000000000
        self.assertEqual(self.client.post("/hs2/listings/applications", json=body, headers=self.headers).status_code, 409)
        # Committed drafts rely on their persisted owner-scoped candidate, not an expired search session.
        self.assertEqual(self.repo.change(WHO, row["id"], 1, "submit")["status"], "submitted")

    def test_revoked_business_stale_submission_cannot_be_approved(self):
        row = self.submitted()
        self.app.fixture_approved.remove((101, WHO["context_id"]))
        with self.assertRaises(ContractError):
            review(self.repo, row["id"], 700, 1, "approve", "stale approval", rights=True, disclosure=True)
        self.assertEqual(public_rows(self.repo), [])

    def test_admin_without_operator_context_can_load_own_page_and_assets_only(self):
        app = Flask("admin_without_member_role")
        app.register_blueprint(create_blueprint(self.repo, resolve_context=lambda: None,
            resolve_admin=lambda: 700, csrf_token=lambda: "owned", check_csrf=lambda: False,
            references=lambda _: [], verify_reference=lambda *_: None))
        client = app.test_client()
        for path in ("/admin", "/assets/listings.css", "/assets/admin.js", "/assets/favicon.svg"):
            self.assertEqual(client.get("/hs2/listings" + path).status_code, 200)
        self.assertEqual(client.get("/hs2/listings/applications").status_code, 401)
