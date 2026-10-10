import copy
import unittest
from hs2_design.domain import ContractError
from hs2_listings.validation import actor, payload, identifier, revision

BASE = dict(title="검증 공간", space_label="101", space_scope="unit",
            stay_kind="lodging", rooms=0, area_m2="21.5", guests=2, options=["wifi"],
            nightly=120000, weekly=None, monthly=None, min_stay=1,
            photos=["00000000-0000-4000-8000-000000006010"],
            responsibility=True, public_summary=False, instant=False, discount=False,
            disclosure="limited")


class RegistrationValidation(unittest.TestCase):
    def test_complete_declared_lodging_and_studio(self):
        result = payload(BASE, complete=True)
        self.assertEqual(result["rooms"], 0)
        self.assertEqual(result["min_stay"], 1)

    def test_incomplete_draft_not_complete_submission(self):
        self.assertEqual(payload({})["stay_kind"], "")
        with self.assertRaises(ContractError):
            payload({}, complete=True)

    def test_non_lodging_seven_days_and_explicit_week_month(self):
        p = {**BASE, "stay_kind": "non_lodging", "min_stay": 7, "weekly": 250000, "nightly": None}
        self.assertEqual(payload(p, True)["min_stay"], 7)
        for changes in ({"min_stay": 6}, {"weekly": None}, {"stay_kind": ""}):
            with self.assertRaises(ContractError):
                payload({**p, **changes}, True)

    def test_missing_photo_and_responsibility(self):
        for change in ({"photos": []}, {"responsibility": False}):
            with self.assertRaises(ContractError):
                payload({**BASE, **change}, True)

    def test_unknown_owner_or_approval_fields_refused(self):
        for key in ("user_id", "candidate_id", "approved", "rights_verified", "reviewer_id", "context_id"):
            with self.assertRaises(ContractError):
                payload({**BASE, key: 1})

    def test_invalid_numeric_bool_nan_negative_overflow(self):
        for field, value in (("rooms", True), ("guests", 0), ("nightly", -1),
                             ("weekly", 1000000001), ("min_stay", 731),
                             ("area_m2", "NaN"), ("area_m2", "Infinity"),
                             ("area_m2", "0"), ("area_m2", 21.5), ("area_m2", "1.234")):
            with self.assertRaises(ContractError):
                payload({**BASE, field: value})

    def test_invalid_options_ids_and_boolean_shapes(self):
        for field, value in (("options", ["wifi", "wifi"]), ("options", ["private"]),
                             ("photos", [{}]), ("photos", ["42"]), ("instant", 1),
                             ("responsibility", "true"), ("disclosure", "full"),
                             ("space_scope", "arbitrary"), ("title", "x" * 101)):
            with self.assertRaises(ContractError):
                payload({**BASE, field: value})

    def test_valid_zero_rate_is_not_missing(self):
        self.assertEqual(payload({**BASE, "nightly": 0}, True)["nightly"], 0)

    def test_control_characters_not_saved(self):
        with self.assertRaises(ContractError):
            payload({**BASE, "title": "hello\x00"})

    def test_actor_context_role_and_revision_not_forged(self):
        good = dict(user_id=101, role="operator", context_id="operator:fixture:101")
        self.assertEqual(actor(good), good)
        for changes in ({"user_id": True}, {"user_id": -1}, {"role": "loan_consultant"}, {"context_id": ""}):
            with self.assertRaises(ContractError):
                actor({**good, **changes})
        for v in (0, True, "1", -1):
            with self.assertRaises(ContractError):
                revision(v)

    def test_identifier_not_private_int_or_noncanonical_uuid(self):
        for v in ("42", None, [], "00000000-0000-4000-8000-00000000600A"):
            with self.assertRaises(ContractError):
                identifier(v)

    def test_validation_does_not_modify_caller(self):
        before = copy.deepcopy(BASE)
        payload(BASE, True)
        self.assertEqual(before, BASE)
