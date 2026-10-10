"""S01-A02: new graph behavior + observed legacy shape, with no DB/app import."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import re
import unittest

from hs2_design.domain import (
    BuildingGrant, Candidate, Classification, ContractError, LegacyMasterLink,
    RegisteredBuilding, StayKind, StayListing, limited_projection, validate_graph,
)

ROOT = Path(__file__).resolve().parents[1]


class GraphContracts(unittest.TestCase):
    def setUp(self):
        self.c = Candidate("candidate:one", "registry-building:fixture-1", True, "아파트", "fixture address")
        self.b = RegisteredBuilding("registration:one", self.c.id)
        self.g = BuildingGrant(self.b.id, 101, "owner", "rights:fixture", True, ("inventory:one",))
        self.l = StayListing(
            "stay:one", "00000000-0000-4000-8000-000000000001", self.b.id, 101, "inventory:one",
            Classification("stay:one", StayKind.NON_LODGING, "review:fixture", "v1"),
        )
        self.legacy = {42: self.c.identity_key}
        self.link = LegacyMasterLink(self.c.id, 42, self.c.identity_key, True)

    def graph(self, **changes):
        args = dict(candidates=[self.c], buildings=[self.b], grants=[self.g],
                    listings=[self.l], links=[self.link], legacy_identity_by_id=self.legacy)
        args.update(changes)
        return validate_graph(**args)

    def test_candidate_search_has_no_registration_or_legacy_requirement(self):
        candidates = [replace(self.c, id=f"candidate:{i}", identity_key=None,
                              identity_confirmed=False, building_use=use)
                      for i, use in enumerate(("원룸", "아파트", "상가", "창고", "캠핑", "기타"))]
        self.assertTrue(validate_graph(candidates, [], [], [], [], {}))

    def test_new_non_lodging_building_needs_no_lodging_master(self):
        self.assertTrue(self.graph(links=[], legacy_identity_by_id={}))

    def test_existing_master_link_is_optional_exact_and_read_only(self):
        before = deepcopy(self.legacy)
        self.assertTrue(self.graph())
        self.assertEqual(self.legacy, before)
        self.assertEqual(self.link.master_id, 42)

    def test_existing_master_id_alone_does_not_prove_identity(self):
        with self.assertRaisesRegex(ContractError, "LEGACY_LINK"):
            self.graph(legacy_identity_by_id={42: "registry-building:different"})

    def test_missing_unverified_or_ambiguous_master_link_rejected(self):
        for link in (replace(self.link, master_id=999), replace(self.link, verified=False),
                     replace(self.link, identity_key="address-only")):
            with self.subTest(link=link), self.assertRaises(ContractError):
                self.graph(links=[link])
        with self.assertRaises(ContractError):
            self.graph(legacy_identity_by_id={42: self.c.identity_key, 43: self.c.identity_key})

    def test_independent_namespaces_and_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ContractError, "NAMESPACE"):
            self.graph(candidates=[replace(self.c, id="42")])
        with self.assertRaisesRegex(ContractError, "DUPLICATE"):
            self.graph(candidates=[self.c, self.c])

    def test_confirmed_identity_not_address_controls_deduplication(self):
        same_address = replace(self.c, id="candidate:two", identity_key="registry-building:fixture-2")
        self.assertTrue(self.graph(candidates=[self.c, same_address]))
        duplicate = replace(same_address, identity_key=self.c.identity_key)
        with self.assertRaisesRegex(ContractError, "IDENTITY"):
            self.graph(candidates=[self.c, duplicate])

    def test_candidate_cannot_have_multiple_physical_registrations(self):
        with self.assertRaisesRegex(ContractError, "ONE_REGISTRATION"):
            self.graph(buildings=[self.b, replace(self.b, id="registration:two")])

    def test_dangling_or_unconfirmed_candidate_cannot_be_registered(self):
        with self.assertRaises(ContractError):
            self.graph(buildings=[replace(self.b, candidate_id="candidate:missing")])
        with self.assertRaises(ContractError):
            self.graph(candidates=[replace(self.c, identity_confirmed=False)])

    def test_multiple_scoped_owners_and_listings_are_not_multiple_buildings(self):
        grant = replace(self.g, user_id=102, role="operator", inventory_keys=("inventory:two",))
        second = replace(self.l, id="stay:two", public_id="00000000-0000-4000-8000-000000000002",
                         creator_user_id=102, inventory_key="inventory:two",
                         classification=replace(self.l.classification, subject_id="stay:two"))
        self.assertTrue(self.graph(grants=[self.g, grant], listings=[self.l, second]))

    def test_same_inventory_reference_is_not_independent_stock(self):
        second = replace(self.l, id="stay:two", public_id="00000000-0000-4000-8000-000000000002",
                         classification=replace(self.l.classification, subject_id="stay:two"))
        self.assertTrue(self.graph(listings=[self.l, second]))
        self.assertEqual(second.inventory_key, self.l.inventory_key)
        # Future inventory locks must key this shared inventory, not listing ID.

    def test_unapproved_other_user_or_other_building_grant_cannot_create(self):
        for grant in (replace(self.g, approved=False), replace(self.g, user_id=102)):
            with self.subTest(grant=grant), self.assertRaisesRegex(ContractError, "RIGHTS_REQUIRED"):
                self.graph(grants=[grant])
        other_c = replace(self.c, id="candidate:two", identity_key="registry-building:fixture-2")
        other_b = RegisteredBuilding("registration:two", other_c.id)
        with self.assertRaisesRegex(ContractError, "RIGHTS_REQUIRED"):
            self.graph(candidates=[self.c, other_c], buildings=[self.b, other_b],
                       grants=[replace(self.g, registered_building_id=other_b.id)])

    def test_duplicate_grants_and_missing_rights_evidence_rejected(self):
        with self.assertRaises(ContractError):
            self.graph(grants=[self.g, self.g])
        with self.assertRaises(ContractError):
            self.graph(grants=[replace(self.g, rights_evidence="")])

    def test_building_grant_does_not_authorize_other_units_automatically(self):
        with self.assertRaisesRegex(ContractError, "RIGHTS_REQUIRED"):
            self.graph(listings=[replace(self.l, inventory_key="inventory:unowned")])

    def test_inventory_pool_cannot_cross_physical_buildings(self):
        c2 = replace(self.c, id="candidate:two", identity_key="registry-building:fixture-2")
        b2 = RegisteredBuilding("registration:two", c2.id)
        grant = replace(self.g, registered_building_id=b2.id)
        listing = replace(self.l, id="stay:two", public_id="00000000-0000-4000-8000-000000000002",
                          registered_building_id=b2.id,
                          classification=replace(self.l.classification, subject_id="stay:two"))
        with self.assertRaisesRegex(ContractError, "INVENTORY_BELONGS"):
            self.graph(candidates=[self.c, c2], buildings=[self.b, b2],
                       grants=[self.g, grant], listings=[self.l, listing])

    def test_listing_subject_parent_and_public_identifier_are_checked(self):
        for listing in (
            replace(self.l, classification=replace(self.l.classification, subject_id="stay:other")),
            replace(self.l, registered_building_id="registration:missing"),
            replace(self.l, public_id=self.l.id), replace(self.l, inventory_key=""),
            replace(self.l, creator_user_id=True),
        ):
            with self.subTest(listing=listing), self.assertRaises(ContractError):
                self.graph(listings=[listing])

    def test_duplicate_master_link_and_public_id_rejected(self):
        with self.assertRaises(ContractError):
            self.graph(links=[self.link, self.link])
        other = replace(self.l, id="stay:two",
                        classification=replace(self.l.classification, subject_id="stay:two"))
        with self.assertRaises(ContractError):
            self.graph(listings=[self.l, other])

    def test_limited_dto_does_not_leak_location_through_nested_join(self):
        payload = dict(master_building_id=42, registered_building_id=self.b.id,
                       lat=37.5, lng=127.0, road_address="fixture address", unit="101",
                       building_name="identifying name", photo_metadata={"gps": [37.5, 127.0]},
                       building_info_overrides={"address": "fixture address"},
                       verified_phone="fixture", nested={"candidate": self.c})
        before = deepcopy(payload)
        result = limited_projection(self.l, payload)
        self.assertEqual(set(result), {"public_id", "stay_kind", "location_precision"})
        self.assertEqual(result["location_precision"], "withheld")
        self.assertEqual(payload, before)

    def test_full_location_publication_is_not_implemented_in_phase_one(self):
        with self.assertRaises(ContractError):
            limited_projection(replace(self.l, disclosure_scope="full"), {})

    def test_public_identifier_cannot_be_a_private_id_or_free_text_address(self):
        for public_id in (self.c.id, str(self.link.master_id), self.c.road_address):
            with self.subTest(public_id=public_id), self.assertRaises(ContractError):
                limited_projection(replace(self.l, public_id=public_id), {})

    def test_observed_legacy_relationships_are_not_booking_inventory(self):
        # Static corroboration, in addition to the behavioral graph tests above.
        # Does not assert production schema/data or import the DB initializer.
        source = (ROOT / "db.py").read_text()
        def table(name):
            return re.search(
                r"CREATE TABLE IF NOT EXISTS " + name + r"\s*\((.*?)\n\s*\)",
                source, re.S,
            ).group(1)
        self.assertIn("REFERENCES master_buildings(id)", table("listing_requests"))
        self.assertIn("REFERENCES users(id)", table("listing_requests"))
        self.assertIn("REFERENCES listing_requests(id)", table("business_room_inventory"))
        self.assertIn("contract_end_date DATE", table("business_room_inventory"))
        self.assertIn("booking_url TEXT NOT NULL", table("booking_url_requests"))
        self.assertIn("queue_position INTEGER", table("slots"))
        self.assertIn("월 회비", table("slots"))
        self.assertIn("만원 단위", table("listing_requests"))

    def test_design_is_not_imported_by_existing_application_or_schema(self):
        for name in ("app.py", "db.py", "listing_extensions.py", "public_api_client.py"):
            with self.subTest(name=name):
                self.assertNotIn("hs2_design", (ROOT / name).read_text())


if __name__ == "__main__":
    unittest.main()
