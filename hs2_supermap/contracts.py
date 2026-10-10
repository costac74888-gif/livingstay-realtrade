import math
from decimal import Decimal
from hs2_design.domain import ContractError
from hs2_consumer.search import query

LAYERS = ("stay", "sale", "business", "auction")
SHAPES = dict(stay="price-bubble", sale="diamond", business="hexagon", auction="square")
SLOTS = dict(stay=(0, 56), sale=(-72, 0), business=(72, 0), auction=(0, -56))


def parse(values):
    filters = {k: v for k, v in values.items() if k not in {"layers", "bounds", "min_total", "max_total"}}
    out = query(filters)
    # Phase7 allows up to KRW 1e9 per unit for <=730 days. Preserve the older
    # Phase5 contract but make the real period-total range searchable here.
    for name in ("min_total", "max_total"):
        raw_total = values.get(name, "")
        if raw_total and (not raw_total.isascii() or not raw_total.isdigit()
                          or len(raw_total) > 12 or int(raw_total) > 730_000_000_000):
            raise ContractError("INVALID_NUMBER")
        out[name] = int(raw_total) if raw_total else None
    if any(out[k] is not None for k in ("min_total", "max_total")) and not out["check_in"]:
        raise ContractError("TOTAL_REQUIRES_DATES")
    if out["min_total"] is not None and out["max_total"] is not None and out["min_total"] > out["max_total"]:
        raise ContractError("INVALID_PRICE_RANGE")
    raw = values.get("layers", "stay")
    layers = raw.split(",") if raw else []
    if len(set(layers)) != len(layers) or set(layers) - set(LAYERS):
        raise ContractError("INVALID_LAYERS")
    out["layers"] = [k for k in LAYERS if k in layers]
    bounds = values.get("bounds", "")
    if bounds:
        try:
            parts = [float(x) for x in bounds.split(",")]
            if (len(parts) != 4 or any(not math.isfinite(x) for x in parts)
                    or not -90 <= parts[0] < parts[2] <= 90
                    or not -180 <= parts[1] < parts[3] <= 180):
                raise ValueError()
            out["bounds"] = parts
        except ValueError:
            raise ContractError("INVALID_BOUNDS") from None
    else:
        out["bounds"] = None
    return out


def point(raw, *, limited):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContractError("PUBLIC_GEOMETRY_REQUIRED")
    lat, lng = raw.get("lat"), raw.get("lng")
    if (type(lat) not in {int, float} or type(lng) not in {int, float}
            or not math.isfinite(lat) or not math.isfinite(lng)
            or not -90 <= lat <= 90 or not -180 <= lng <= 180):
        raise ContractError("INVALID_PUBLIC_POINT")
    if limited:
        scope, count = raw.get("aggregate_scope"), raw.get("aggregate_count")
        digits = 3 if scope == "dong" else 2 if scope == "sgg" else None
        if (digits is None or type(count) is not int or count < (5 if digits == 3 else 10)
                or raw.get("precision") != "approx" or lat != round(lat, digits) or lng != round(lng, digits)):
            return None  # No exact point fallback when privacy aggregate is unsafe.
        return dict(lat=lat, lng=lng, precision="approx", radius_m=500,
                    label="동 중심 근처" if digits == 3 else "시군구 중심 근처")
    if raw.get("precision") != "exact":
        raise ContractError("PUBLIC_GEOMETRY_REQUIRED")
    return dict(lat=lat, lng=lng, precision="exact", radius_m=0, label="공개 위치")


def within(geometry, bounds):
    return geometry is None or bounds is None or (
        bounds[0] <= geometry["lat"] <= bounds[2] and bounds[1] <= geometry["lng"] <= bounds[3])


def visible_stay(public, application, quote, geometry, values):
    """Only explicitly public operator-entered summary; never master metadata."""
    p = application["payload"]
    summary = p.get("public_summary") is True
    kind = public["stay_kind"]
    if values["kind"] not in {"all", kind}:
        return None
    if any(values[k] is not None for k in ("rooms", "min_area", "guests")) or values["options"] or values["instant"] or values["discount"]:
        if not summary:
            return None
        if ((values["rooms"] is not None and p["rooms"] != values["rooms"])
                or (values["min_area"] is not None and (p["area_m2"] is None or Decimal(p["area_m2"]) < values["min_area"]))
                or (values["guests"] is not None and (p["guests"] is None or p["guests"] < values["guests"]))
                or not set(values["options"]).issubset(p.get("options", []))
                or (values["instant"] and p.get("instant") is not True)
                or (values["discount"] and p.get("discount") is not True)):
            return None
    if values["check_in"] and quote is None:
        # Unavailable/unsupported stays must not appear as bookable or 0 price.
        return None
    if any(values[k] is not None for k in ("min_total", "max_total")):
        if not quote:
            return None
        if ((values["min_total"] is not None and quote["total_krw"] < values["min_total"])
                or (values["max_total"] is not None and quote["total_krw"] > values["max_total"])):
            return None
    if not within(geometry, values["bounds"]):
        return None
    # Never expose operator title/space_label/photos/address/candidate/master ids.
    out = dict(public_id=public["public_id"], layer="stay", stay_kind=kind,
               title="숙박형 단기임대" if kind == "lodging" else "주·월 단기임대",
               quote=quote, point=geometry, marker_shape=SHAPES["stay"], location_precision="approx" if geometry else "withheld")
    if summary:
        out["summary"] = {k: p.get(k) for k in ("rooms", "area_m2", "guests", "min_stay", "options", "instant", "discount")}
    return out


def visible_legacy(layer, row):
    if layer not in LAYERS[1:] or not isinstance(row, dict) or row.get("public") is not True:
        raise ContractError("PUBLIC_LEGACY_PROJECTION_REQUIRED")
    key = row.get("public_id")
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in key):
        raise ContractError("PUBLIC_LEGACY_ID_REQUIRED")
    limited = row.get("disclosure_scope") != "public"
    geometry = point(row.get("public_point"), limited=limited)
    title = {"sale": "매매 매물", "business": "영업권 양도", "auction": "공매 물건"}[layer]
    if not limited:
        supplied = row.get("public_title")
        if isinstance(supplied, str) and 0 < len(supplied) <= 100 and not any(ord(c) < 32 for c in supplied):
            title = supplied
    return dict(public_id=key, layer=layer, title=title, point=geometry,
                location_precision=("approx" if limited else "exact") if geometry else "withheld",
                marker_shape=SHAPES[layer], restricted=limited)


def slots(items):
    """Stable screen pixel slots; never perturb public or native lat/lng."""
    groups = {}
    for row in items:
        geo = row.get("point")
        if geo:
            groups.setdefault((geo["lat"], geo["lng"], row["layer"]), []).append(row)
    markers = []
    for rows in groups.values():
        ordered = sorted(rows, key=lambda r: r["public_id"])
        first = ordered[0]
        markers.append(dict(layer=first["layer"], ids=[r["public_id"] for r in ordered],
                            point=first["point"], offset=list(SLOTS[first["layer"]]),
                            marker_shape=SHAPES[first["layer"]], count=len(ordered),
                            total_krw=first.get("quote", {}).get("total_krw") if first.get("quote") else None))
    return sorted(markers, key=lambda r: (r["point"]["lat"], r["point"]["lng"], LAYERS.index(r["layer"])))
