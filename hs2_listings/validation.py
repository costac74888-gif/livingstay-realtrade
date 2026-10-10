from decimal import Decimal, InvalidOperation
from uuid import UUID
from hs2_design.domain import ContractError

OPTIONS = {"wifi", "kitchen", "parking", "washer"}
FIELDS = {"title", "space_label", "space_scope", "stay_kind", "rooms", "area_m2",
          "guests", "options", "nightly", "weekly", "monthly", "min_stay",
          "instant", "discount", "photos", "responsibility", "public_summary", "disclosure"}


def actor(value):
    if not isinstance(value, dict) or type(value.get("user_id")) is not int or value["user_id"] <= 0:
        raise ContractError("AUTH_REQUIRED")
    if value.get("role") not in {"operator", "lodging_operator", "agent"}:
        raise ContractError("APPROVED_BUSINESS_REQUIRED")
    if not isinstance(value.get("context_id"), str) or not value["context_id"] or len(value["context_id"]) > 160:
        raise ContractError("BUSINESS_CONTEXT_REQUIRED")
    return value


def revision(value):
    if type(value) is not int or value < 1:
        raise ContractError("REVISION_REQUIRED")
    return value


def identifier(value):
    try:
        result = str(UUID(value))
        if result != value:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise ContractError("INVALID_ID") from None


def payload(raw, complete=False):
    if not isinstance(raw, dict) or set(raw) - FIELDS:
        raise ContractError("INVALID_PAYLOAD")
    out = dict(raw)
    for name in ("title", "space_label"):
        text = out.get(name, "")
        if not isinstance(text, str) or len(text) > 100 or any(ord(c) < 32 for c in text):
            raise ContractError("INVALID_TEXT")
        out[name] = text.strip()
    if out.get("space_scope", "unit") not in {"unit", "whole"}:
        raise ContractError("INVALID_SPACE_SCOPE")
    out.setdefault("space_scope", "unit")
    if out.get("stay_kind", "") not in {"", "lodging", "non_lodging"}:
        raise ContractError("EXPLICIT_STAY_KIND_REQUIRED")
    out.setdefault("stay_kind", "")
    for name, low, high in (("rooms", 0, 30), ("guests", 1, 100),
                            ("min_stay", 1, 730), ("nightly", 0, 1_000_000_000),
                            ("weekly", 0, 1_000_000_000), ("monthly", 0, 1_000_000_000)):
        v = out.get(name)
        if v is not None and (type(v) is not int or not low <= v <= high):
            raise ContractError("INVALID_NUMBER")
        out[name] = v
    area = out.get("area_m2")
    if area is not None:
        try:
            if not isinstance(area, str) or len(area) > 10:
                raise ValueError()
            d = Decimal(area)
            if not d.is_finite() or not 0 < d <= 10000 or d.as_tuple().exponent < -2:
                raise ValueError()
            out["area_m2"] = str(d)
        except (ValueError, InvalidOperation):
            raise ContractError("INVALID_AREA") from None
    else:
        out["area_m2"] = None
    options = out.get("options", [])
    if not isinstance(options, list) or any(type(v) is not str for v in options) or len(set(options)) != len(options) or set(options) - OPTIONS:
        raise ContractError("INVALID_OPTIONS")
    out["options"] = sorted(options)
    photos = out.get("photos", [])
    if not isinstance(photos, list) or any(type(v) is not str for v in photos) or len(photos) > 10 or len(photos) != len(set(photos)):
        raise ContractError("INVALID_PHOTOS")
    out["photos"] = [identifier(v) for v in photos]
    for name in ("responsibility", "public_summary", "instant", "discount"):
        if type(out.get(name, False)) is not bool:
            raise ContractError("INVALID_BOOLEAN")
        out.setdefault(name, False)
    if out.get("disclosure", "limited") != "limited":
        raise ContractError("LIMITED_DISCLOSURE_REQUIRED")
    out["disclosure"] = "limited"
    if complete:
        if any(not out[n] for n in ("title", "space_label", "stay_kind")) or any(out[n] is None for n in ("rooms", "guests", "area_m2", "min_stay")):
            raise ContractError("COMPLETE_SPACE_REQUIRED")
        if out["min_stay"] < (1 if out["stay_kind"] == "lodging" else 7):
            raise ContractError("MINIMUM_STAY_REQUIRED")
        if (out["stay_kind"] == "lodging" and out["nightly"] is None) or (
                out["stay_kind"] == "non_lodging" and out["weekly"] is None and out["monthly"] is None):
            raise ContractError("TYPE_PRICE_REQUIRED")
        if not out["photos"]:
            raise ContractError("PHOTO_REQUIRED")
        if not out["responsibility"]:
            raise ContractError("RESPONSIBILITY_REQUIRED")
    return out
