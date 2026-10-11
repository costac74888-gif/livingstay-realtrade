"""Public rate projections/date assistance for the OWNED fictional Preview only.

No price calculation, schema, migration, production wiring or credential changes.
Quotes and candidate verification always call the existing calendar repository.
"""
from datetime import date, timedelta
from hs2_calendar.engine import anniversary
from hs2_consumer.search import MAX_KRW
from hs2_design.domain import ContractError
from hs2_listings.review import public_rows
from hs2_supermap.contracts import point, slots, visible_stay
from scripts.hs2_seongsu_seed import require_owned

NOTICE = "기본 요금이며 날짜에 따라 다를 수 있습니다"
PERIOD_ERROR = "EXACT_PERIOD_QUOTE_UNAVAILABLE"
ERROR_MESSAGES = {
    PERIOD_ERROR: "주·월 요금에 맞는 기간을 선택해 주세요",
    "MINIMUM_STAY_NOT_MET": "최소 이용기간 이상을 선택해 주세요",
    "CALENDAR_UNAVAILABLE": "선택 날짜에 이용할 수 없습니다",
    "INVENTORY_UNAVAILABLE": "선택 날짜의 재고를 확인할 수 없습니다",
    "CURRENT_PRICE_VERSION_REQUIRED": "공개 요금을 확인할 수 없습니다",
    "INCLUSIVE_PRICE_ACK_REQUIRED": "공개 요금을 확인할 수 없습니다",
    "PUBLIC_LISTING_NOT_FOUND": "공개 매물을 확인할 수 없습니다",
    "FUTURE_STAY_REQUIRED": "오늘 이후의 날짜를 선택해 주세요",
}


def base_rates(kind, calendar, *, allowed):
    """Explicit allowlist. No int coercion, no missing -> zero conversion."""
    if allowed is not True or not isinstance(calendar, dict) or calendar.get("kind") != kind:
        return None
    raw = {k: calendar.get(k) for k in ("base", "weekly", "monthly")}
    if any(v is not None and (type(v) is not int or not 0 <= v <= MAX_KRW)
           for v in raw.values()):
        return None
    if kind == "lodging":
        if raw["base"] is None or raw["weekly"] is not None or raw["monthly"] is not None:
            return None
        return {"night": raw["base"]}
    if kind == "non_lodging":
        if raw["base"] is not None or raw["weekly"] is None and raw["monthly"] is None:
            return None
        return {"week": raw["weekly"], "month": raw["monthly"]}
    return None


def candidate_ends(start, end, rates, minimum=7):
    """Only proposals; callers must validate every result through quote()."""
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    candidates = set()
    if rates and rates.get("week") is not None:
        candidates.update(start + timedelta(days=7*n) for n in range(1, 14))
    if rates and rates.get("month") is not None:
        for n in range(1, 7):
            month = anniversary(start, n)
            candidates.add(month)
            if rates.get("week") is not None:
                candidates.update(month + timedelta(days=7*w) for w in range(1, 5))
    return [d.isoformat() for d in sorted(candidates,
             key=lambda d: (abs((d-end).days), d))
            if minimum <= (d-start).days <= 730 and d != end]


class PreviewRateSearch:
    def __init__(self, original):
        self.original = original
        self.native_search = original.search
        self.calendar = original.calendar

    def source(self, public):
        """Re-read the same approval/rights/member/context gates under row lock."""
        registrations = self.calendar.registrations
        with registrations.transaction() as c:
            c.execute("SELECT id FROM hs2_dev.registration_applications WHERE public_id=%s",
                      (public["public_id"],))
            match = c.fetchone()
            if not match:
                return None
            application = registrations.row(c, str(match[0]))
            c.execute("""SELECT 1 FROM hs2_dev.registration_applications a
                JOIN hs2_dev.stay_listings l ON l.id=a.listing_id
                JOIN hs2_dev.registration_grants g ON g.id=l.grant_id
                JOIN hs2_fixture_legacy.users u ON u.id=a.user_id
                WHERE a.id=%s AND a.status='approved' AND a.reviewed_revision=a.revision
                  AND a.approved_until>clock_timestamp() AND l.status='published'
                  AND g.approved AND u.active""", (application["id"],))
            if not c.fetchone() or registrations.context_is_active(
                    application["user_id"], application["context_id"]) is not True:
                return None
            latest = self.calendar.latest(c, application)
            allowed = (not latest["stale"] and latest["tariff_version"] is not None
                       and latest["calendar"].get("inclusive") is True)
            rates = base_rates(public["stay_kind"], latest["calendar"], allowed=allowed)
            return application, latest["calendar"], rates

    def search(self, values):
        # Preserve every native layer/geometry/count contract and its adapter.
        result = self.native_search({**values, "layers": [
            layer for layer in values["layers"] if layer != "stay"]})
        result["period_hidden_count"] = 0
        if "stay" not in values["layers"]:
            return result
        safe = public_rows(self.calendar.registrations)
        if len(safe) > 500:
            raise ContractError("CATALOG_LIMIT")
        if len({r["public_id"] for r in safe}) != len(safe):
            raise ContractError("DUPLICATE_LAYER_ID")
        rows = []
        for public in safe:
            key = public["public_id"]
            if values["q"] and self.original.public_location_match(key, values["q"]) is not True:
                continue
            geometry = point(self.original.public_geometry(key), limited=True)
            source = self.source(public)
            if source is None:
                continue
            application, calendar, rates = source
            # Apply the SAME summary/attribute/bounds/price filters before counts.
            matching = visible_stay(public, application, None, geometry,
                                    {**values, "check_in": None, "check_out": None})
            days = ((date.fromisoformat(values["check_out"])
                    - date.fromisoformat(values["check_in"])).days
                    if values["check_in"] else None)
            quote, issue = None, None
            if values["check_in"]:
                try:
                    quote = self.calendar.quote(key, values["check_in"], values["check_out"])
                except ContractError as exc:
                    issue = str(exc)
            # Never count withheld prices, unavailable inventory, blocked dates,
            # private metadata, price-filter exclusions or nonmatching items.
            if public["stay_kind"] == "non_lodging" and days is not None and days < 7:
                blocked = set(calendar.get("blocked", []))
                selected = { (date.fromisoformat(values["check_in"])
                             + timedelta(days=n)).isoformat() for n in range(days) }
                if (values["kind"] == "all" and matching is not None and rates is not None
                        and issue == "MINIMUM_STAY_NOT_MET" and not blocked & selected
                        and key in {r["public_id"] for r in public_rows(self.calendar.registrations)}):
                    result["period_hidden_count"] += 1
                continue
            row = visible_stay(public, application, quote, geometry, values)
            # Only genuine decomposition errors get a public, unquoted card.
            # Other availability/public-price failures retain the original gate.
            zero_without_quote = (issue == "POSITIVE_INTEGER_KRW_REQUIRED"
                                   and rates is not None and 0 in rates.values())
            if row is None and rates is not None and (issue == PERIOD_ERROR or zero_without_quote):
                row = matching
            if row is None:
                continue
            if key not in {r["public_id"] for r in public_rows(self.calendar.registrations)}:
                continue
            candidates = []
            if issue == PERIOD_ERROR and rates is not None:
                for end in candidate_ends(values["check_in"], values["check_out"],
                                          rates, application["payload"]["min_stay"]):
                    try:
                        self.calendar.quote(key, values["check_in"], end)
                    except ContractError:
                        continue
                    candidates.append(end)
                    if len(candidates) == 2:
                        break
            row.update(base_rates=rates, base_rate_notice=NOTICE if rates is not None else None,
                       quote_issue=PERIOD_ERROR if issue == PERIOD_ERROR else None,
                       candidate_check_outs=candidates)
            rows.append(row)
        rows.sort(key=(lambda r: (r["quote"] is None,
                  r["quote"]["total_krw"] if r["quote"] else 0, r["public_id"]))
                  if values["sort"] == "total_asc" else lambda r: r["public_id"])
        result["counts"]["stay"] = len(rows)
        result["truncated"]["stay"] = len(rows) > 60
        result["items"] = rows[:60] + result["items"]
        result["markers"] = slots(result["items"])
        result["withheld_count"] = sum(r["point"] is None for r in result["items"])
        return result


def install(app):
    require_owned(app)
    adapter = PreviewRateSearch(app.fixture_supermap)
    app.fixture_supermap.search = adapter.search

    from flask import jsonify, request
    @app.get("/__development__/seongsu/quote-check")
    def quote_check():
        require_owned(app)
        if set(request.args) != {"public_id", "check_in", "check_out"} or any(
                len(request.args.getlist(k)) != 1 for k in request.args):
            return jsonify(ok=False, code="INVALID_QUERY", message="날짜 조건을 확인하세요"), 400
        try:
            quote = adapter.calendar.quote(request.args["public_id"], request.args["check_in"],
                                           request.args["check_out"])
            return jsonify(ok=True, quote=quote)
        except ContractError as exc:
            code = str(exc)
            # Public reason allowlist, never raw exception/private identifiers.
            return jsonify(ok=False, code=code if code in ERROR_MESSAGES else "QUOTE_UNAVAILABLE",
                message=ERROR_MESSAGES.get(code, "해당 날짜의 공개 견적을 제공할 수 없습니다")), 400
