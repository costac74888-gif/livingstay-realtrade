"""Selected-stay total query contract; never infer a quote from a unit rate."""
from datetime import date
from uuid import UUID
from hs2_design.domain import ContractError

FIELDS = {"q", "check_in", "check_out", "min_total", "max_total", "rooms", "kind",
          "min_area", "guests", "options", "instant", "discount", "sort"}
OPTIONS = {"wifi", "kitchen", "parking", "washer"}
MAX_KRW = 1_000_000_000


def query(values):
    if set(values) - FIELDS:
        raise ContractError("UNKNOWN_FILTER")
    out = {"q": values.get("q", "").strip(), "kind": values.get("kind", "all"),
           "sort": values.get("sort", "total_asc")}
    if len(out["q"]) > 100 or out["kind"] not in {"all", "lodging", "non_lodging"} or out["sort"] not in {"total_asc", "id"}:
        raise ContractError("INVALID_FILTER")
    for name in ("check_in", "check_out"):
        raw = values.get(name, "")
        try:
            out[name] = date.fromisoformat(raw).isoformat() if raw else None
            if raw and raw != out[name]:
                raise ValueError()
        except ValueError:
            raise ContractError("INVALID_DATE") from None
    if bool(out["check_in"]) != bool(out["check_out"]):
        raise ContractError("BOTH_DATES_REQUIRED")
    if out["check_in"] and out["check_out"] <= out["check_in"]:
        raise ContractError("INVALID_INTERVAL")
    if out["check_in"] and (date.fromisoformat(out["check_out"]) - date.fromisoformat(out["check_in"])).days > 730:
        raise ContractError("INTERVAL_TOO_LONG")
    for name, maximum in (("min_total", MAX_KRW), ("max_total", MAX_KRW),
                          ("rooms", 30), ("guests", 100), ("min_area", 10000)):
        raw = values.get(name, "")
        if raw and (not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) > maximum):
            raise ContractError("INVALID_NUMBER")
        out[name] = int(raw) if raw else None
    if any(out[n] is not None for n in ("min_total", "max_total")) and not out["check_in"]:
        raise ContractError("TOTAL_REQUIRES_DATES")
    if out["min_total"] is not None and out["max_total"] is not None and out["min_total"] > out["max_total"]:
        raise ContractError("INVALID_PRICE_RANGE")
    for name in ("instant", "discount"):
        raw = values.get(name, "0")
        if raw not in {"0", "1"}:
            raise ContractError("INVALID_BOOLEAN")
        out[name] = raw == "1"
    options = values.get("options", "").split(",") if values.get("options") else []
    if len(options) != len(set(options)) or set(options) - OPTIONS:
        raise ContractError("INVALID_OPTIONS")
    out["options"] = sorted(options)
    return out


def search(values, source):
    """source supplies published PUBLIC projections, not private building rows.

    Current Phase 2 limited projection permits only id/kind/withheld location.
    Until Phase 6/8 approved public metadata is available, private building
    amenities, area, occupants, addresses, photos and GPS are NOT promoted.
    Source quotes are supplied separately by a trusted quote callback/adapter.
    """
    rows = list(source(values))
    if len(rows) > 500:
        raise ContractError("CATALOG_LIMIT")
    items, seen, unquoted = [], set(), 0
    for row in rows:
        public_id = str(UUID(row["public_id"]))
        if public_id in seen:
            raise ContractError("DUPLICATE_PUBLIC_ID")
        seen.add(public_id)
        kind = row["stay_kind"]
        if kind not in {"lodging", "non_lodging"} or row.get("location_precision") != "withheld":
            raise ContractError("PUBLIC_PROJECTION_REQUIRED")
        title = "숙박형 단기임대" if kind == "lodging" else "주·월 단기임대"
        if (kind == "non_lodging" and values["check_in"]
                and (date.fromisoformat(values["check_out"]) - date.fromisoformat(values["check_in"])).days < 7):
            continue
        if values["kind"] not in {"all", kind} or (values["q"] and values["q"] not in title):
            continue
        # Unknown protected attributes must not satisfy a filter or leak through it.
        if (any(values[n] is not None for n in ("rooms", "min_area", "guests"))
                or values["options"] or values["instant"] or values["discount"]):
            continue
        quote = None
        supplied = row.get("quote")
        if values["check_in"] and supplied:
            if (supplied.get("check_in") == values["check_in"]
                    and supplied.get("check_out") == values["check_out"]
                    and supplied.get("complete") is True
                    and supplied.get("public_price_allowed") is True
                    and isinstance(supplied.get("source_version"), str)
                    and supplied["source_version"]
                    and type(supplied.get("total_krw")) is int
                    and 0 <= supplied["total_krw"] <= MAX_KRW):
                quote = {k: supplied[k] for k in ("check_in", "check_out", "total_krw")}
        if values["check_in"] and quote is None:
            unquoted += 1
        if values["min_total"] is not None or values["max_total"] is not None:
            if quote is None:
                continue
            total = quote["total_krw"]
            if ((values["min_total"] is not None and total < values["min_total"])
                    or (values["max_total"] is not None and total > values["max_total"])):
                continue
        items.append(dict(public_id=public_id, stay_kind=kind, title=title,
                          region="위치 비공개", rooms=None, area_m2=None, max_guests=None,
                          options=[], instant=False, discount=False,
                          location_precision="withheld", quote=quote))
    if values["sort"] == "total_asc":
        items.sort(key=lambda r: (r["quote"] is None, r["quote"]["total_krw"] if r["quote"] else 0, r["public_id"]))
    else:
        items.sort(key=lambda r: r["public_id"])
    return dict(items=items[:60], count=len(items), unquoted_count=unquoted,
                price_basis="selected_stay_total")
