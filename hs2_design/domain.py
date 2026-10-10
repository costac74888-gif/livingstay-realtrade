"""Executable value contracts, not an application service or storage adapter.

All evidence/permissions supplied here are trusted *fixture inputs*. A future
service must resolve them server-side; a client boolean is never authorization.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping
from uuid import UUID


class ContractError(ValueError):
    pass


class StayKind(str, Enum):
    LODGING = "lodging"
    NON_LODGING = "non_lodging"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Classification:
    subject_id: str
    kind: StayKind
    evidence_id: str
    decision_version: str

    def __post_init__(self):
        if not self.subject_id or not isinstance(self.kind, StayKind):
            raise ContractError("INVALID_CLASSIFICATION")
        if self.kind != StayKind.UNRESOLVED and not (
            self.evidence_id and self.decision_version
        ):
            raise ContractError("CLASSIFICATION_EVIDENCE_REQUIRED")


LODGING_PERMITS = frozenset({
    "hotel", "general_lodging", "urban_guesthouse", "rural_guesthouse",
    "hanok_experience", "camping",
})


def classify_use(subject_id, *, building_use, channel, permit=None,
                 permit_verified=False, non_lodging_reviewed=False,
                 evidence_id="", decision_version=""):
    """Use an evidenced listing-level decision, never its channel/use alone."""
    if type(permit_verified) is not bool or type(non_lodging_reviewed) is not bool:
        raise ContractError("TRUSTED_REVIEW_FLAGS_REQUIRED")
    if permit_verified:
        if permit not in LODGING_PERMITS:
            raise ContractError("UNKNOWN_PERMIT_REQUIRES_REVIEW")
        if non_lodging_reviewed:
            raise ContractError("CONFLICTING_CLASSIFICATION")
        kind = StayKind.LODGING
    elif non_lodging_reviewed:
        if permit is not None:
            raise ContractError("UNRESOLVED_PERMIT_REQUIRES_REVIEW")
        kind = StayKind.NON_LODGING
    else:
        kind = StayKind.UNRESOLVED
    # building_use and channel remain independent descriptive dimensions.
    return Classification(subject_id, kind, evidence_id, decision_version)


@dataclass(frozen=True)
class Candidate:
    id: str
    identity_key: str | None
    identity_confirmed: bool
    building_use: str
    road_address: str


@dataclass(frozen=True)
class RegisteredBuilding:
    id: str
    candidate_id: str


@dataclass(frozen=True)
class BuildingGrant:
    registered_building_id: str
    user_id: int
    role: str
    rights_evidence: str
    approved: bool
    inventory_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class StayListing:
    id: str
    public_id: str
    registered_building_id: str
    creator_user_id: int
    inventory_key: str
    classification: Classification
    disclosure_scope: str = "limited"


@dataclass(frozen=True)
class LegacyMasterLink:
    candidate_id: str
    master_id: int
    identity_key: str
    verified: bool


def _index(rows, prefix):
    result = {}
    for row in rows:
        if not isinstance(row.id, str) or not row.id.startswith(prefix + ":"):
            raise ContractError("SEPARATE_ID_NAMESPACE_REQUIRED")
        if not row.id.split(":", 1)[1] or row.id in result:
            raise ContractError("DUPLICATE_OR_EMPTY_ID")
        result[row.id] = row
    return result


def _public_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except ValueError:
        return False


def validate_graph(candidates, buildings, grants, listings, links,
                   legacy_identity_by_id: Mapping[int, str]):
    """Validate an in-memory proposal without copying/writing legacy records."""
    cs = _index(candidates, "candidate")
    bs = _index(buildings, "registration")
    _index(listings, "stay")
    identities = set()
    for c in cs.values():
        if c.identity_confirmed:
            if not c.identity_key or c.identity_key in identities:
                raise ContractError("CONFIRMED_IDENTITY_MUST_BE_UNIQUE")
            identities.add(c.identity_key)
    registered_candidates = set()
    for b in bs.values():
        c = cs.get(b.candidate_id)
        if c is None or not c.identity_confirmed:
            raise ContractError("MISSING_OR_AMBIGUOUS_CANDIDATE")
        if b.candidate_id in registered_candidates:
            raise ContractError("ONE_REGISTRATION_PER_PHYSICAL_BUILDING")
        registered_candidates.add(b.candidate_id)
    grant_keys = set()
    for g in grants:
        key = (g.registered_building_id, g.user_id, g.role)
        if (g.registered_building_id not in bs or type(g.user_id) is not int
                or g.user_id <= 0 or g.role not in {"owner", "operator", "agent"}
                or key in grant_keys or not g.rights_evidence
                or type(g.inventory_keys) is not tuple or not g.inventory_keys
                or not all(isinstance(k, str) and k for k in g.inventory_keys)):
            raise ContractError("INVALID_SCOPED_GRANT")
        grant_keys.add(key)
    public_ids = set()
    inventory_buildings = {}
    for l in listings:
        if (l.registered_building_id not in bs or not l.inventory_key
                or type(l.creator_user_id) is not int or l.creator_user_id <= 0
                or not _public_uuid(l.public_id) or l.public_id in public_ids
                or l.public_id == l.id
                or l.disclosure_scope not in {"limited", "full"}
                or l.classification.subject_id != l.id):
            raise ContractError("INVALID_LISTING_RELATION")
        if not any(
            g.registered_building_id == l.registered_building_id
            and g.user_id == l.creator_user_id and g.approved is True
            and l.inventory_key in g.inventory_keys
            for g in grants
        ):
            raise ContractError("BUILDING_SCOPED_RIGHTS_REQUIRED")
        if (l.inventory_key in inventory_buildings
                and inventory_buildings[l.inventory_key] != l.registered_building_id):
            raise ContractError("INVENTORY_BELONGS_TO_ONE_BUILDING")
        inventory_buildings[l.inventory_key] = l.registered_building_id
        public_ids.add(l.public_id)
    linked_candidates, linked_masters = set(), set()
    for link in links:
        c = cs.get(link.candidate_id)
        if (c is None or not c.identity_confirmed or link.verified is not True
                or type(link.master_id) is not int or link.master_id <= 0
                or c.identity_key != link.identity_key
                or legacy_identity_by_id.get(link.master_id) != link.identity_key
                or sum(v == link.identity_key for v in legacy_identity_by_id.values()) != 1
                or link.candidate_id in linked_candidates
                or link.master_id in linked_masters):
            raise ContractError("LEGACY_LINK_MUST_BE_UNIQUE_AND_EXACT")
        linked_candidates.add(link.candidate_id)
        linked_masters.add(link.master_id)
    return True


def limited_projection(listing, private_building_payload):
    """A separate allowlist DTO: no joins, labels, free text or photo metadata.

    This prototype only defines the LIMITED DTO. Full-location publication
    needs later disclosure authorization, and is deliberately unavailable here.
    """
    if listing.disclosure_scope != "limited":
        raise ContractError("FULL_DISCLOSURE_NOT_IMPLEMENTED")
    if not _public_uuid(listing.public_id):
        raise ContractError("SERVER_ISSUED_PUBLIC_UUID_REQUIRED")
    return {
        "public_id": listing.public_id,
        "stay_kind": listing.classification.kind.value,
        "location_precision": "withheld",
    }
