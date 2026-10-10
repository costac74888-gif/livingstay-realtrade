from calendar import monthrange
import hashlib
from datetime import date, timedelta
from hs2_design.domain import ContractError, StayKind
from hs2_design.pricing import PriceLine, Terms, money, price_snapshot

POLICY_VERSION = "hs2-calendar-inclusive-whole-periods-2026-10-11"
TERMS = Terms(POLICY_VERSION, "Asia/Seoul", True, "reviewed_explicit_periods")


def local_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ContractError("ISO_LOCAL_DATE_REQUIRED")
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError()
        return result
    except ValueError:
        raise ContractError("ISO_LOCAL_DATE_REQUIRED") from None


def anniversary(start, months):
    if type(months) is not int or not 0 <= months <= 25:
        raise ContractError("MONTH_RANGE_REQUIRED")
    number = start.year * 12 + start.month - 1 + months
    year, month0 = divmod(number, 12)
    month = month0 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def initial(application):
    p = application["payload"]
    return dict(kind=p["stay_kind"], base=p.get("nightly"), weekly=p.get("weekly"),
                monthly=p.get("monthly"), daily={}, periods={}, blocked=[], inclusive=False)


def dates(start, end):
    return (start + timedelta(days=i) for i in range((end - start).days))


def change(current, command, today):
    from copy import deepcopy
    out = deepcopy(current)
    if not isinstance(command, dict) or set(command) != {"start", "end", "action", "values", "inclusive"}:
        raise ContractError("INVALID_CALENDAR_INPUT")
    start, end = local_date(command["start"]), local_date(command["end"])
    if start < today or not start < end <= today + timedelta(days=731):
        raise ContractError("FUTURE_CALENDAR_RANGE_REQUIRED")
    if command["inclusive"] is not True:
        raise ContractError("INCLUSIVE_PRICE_ACK_REQUIRED")
    value, action = command["values"], command["action"]
    if not isinstance(value, dict):
        raise ContractError("INVALID_CALENDAR_VALUES")
    selected = list(dates(start, end))
    if action == "nightly":
        if out["kind"] != "lodging" or not value or set(value) - set("0123456"):
            raise ContractError("LODGING_WEEKDAYS_REQUIRED")
        rates = {int(k): money(v) for k, v in value.items()}
        if any(v > 1_000_000_000 for v in rates.values()):
            raise ContractError("PRICE_RANGE_REQUIRED")
        for day in selected:
            if day.weekday() in rates:
                out["daily"][day.isoformat()] = rates[day.weekday()]
    elif action == "periods":
        if out["kind"] != "non_lodging" or not value or set(value) - {"weekly", "monthly"}:
            raise ContractError("NON_LODGING_PERIODS_REQUIRED")
        for amount in value.values():
            if amount is not None and money(amount) > 1_000_000_000:
                raise ContractError("PRICE_RANGE_REQUIRED")
        for day in selected:
            out["periods"].setdefault(day.isoformat(), {}).update(value)
    elif action in {"close", "open"}:
        if value:
            raise ContractError("NO_RATE_WITH_AVAILABILITY")
        blocked = set(out["blocked"])
        keys = {d.isoformat() for d in selected}
        blocked = blocked | keys if action == "close" else blocked - keys
        out["blocked"] = sorted(blocked)
    else:
        raise ContractError("INVALID_CALENDAR_ACTION")
    out["inclusive"] = True
    return out


def build_snapshot(classification, check_in, check_out, calendar, *, tariff_version,
                   minimum_stay=1):
    if type(check_in) is not date or type(check_out) is not date:
        raise ContractError("BUSINESS_LOCAL_DATES_REQUIRED")
    if not 1 <= (check_out - check_in).days <= 730:
        raise ContractError("CALENDAR_INTERVAL_REQUIRED")
    if type(minimum_stay) is not int or (check_out - check_in).days < minimum_stay:
        raise ContractError("MINIMUM_STAY_NOT_MET")
    if calendar["kind"] != classification.kind.value:
        raise ContractError("CLASSIFICATION_PRICE_MISMATCH")
    if calendar.get("inclusive") is not True:
        raise ContractError("INCLUSIVE_PRICE_ACK_REQUIRED")
    if set(calendar["blocked"]) & {d.isoformat() for d in dates(check_in, check_out)}:
        raise ContractError("CALENDAR_UNAVAILABLE")
    if classification.kind == StayKind.LODGING:
        rows = [PriceLine(day, day + timedelta(days=1), "night",
                          money(calendar["daily"].get(day.isoformat(), calendar["base"])))
                for day in dates(check_in, check_out)]
    else:
        # Months always use the original check-in anniversary, never 30-day
        # conversion or a drifting Jan31 -> Feb28 -> Mar28 chain.
        candidates = []
        monthly_rows = []
        for months in range(26):
            cursor = anniversary(check_in, months)
            if cursor > check_out:
                break
            if months:
                previous = anniversary(check_in, months - 1)
                rate = calendar["periods"].get(previous.isoformat(), {}).get("monthly", calendar["monthly"])
                try:
                    monthly_rows.append(PriceLine(previous, cursor, "month", money(rate)))
                except ContractError:
                    break
            remainder = (check_out - cursor).days
            if remainder % 7:
                continue
            weekly_rows = []
            try:
                while cursor < check_out:
                    rate = calendar["periods"].get(cursor.isoformat(), {}).get("weekly", calendar["weekly"])
                    weekly_rows.append(PriceLine(cursor, cursor + timedelta(days=7), "week", money(rate)))
                    cursor += timedelta(days=7)
                rows = [*monthly_rows, *weekly_rows]
                if rows:
                    candidates.append((sum(r.amount_krw for r in rows), -months, rows))
            except ContractError:
                continue
        if not candidates:
            raise ContractError("EXACT_PERIOD_QUOTE_UNAVAILABLE")
        rows = min(candidates, key=lambda p: (p[0], p[1]))[2]
    return price_snapshot(classification, check_in, check_out, rows, tariff_version=tariff_version,
                          terms=TERMS, adjustments=())


def safe_quote(public_id, snapshot):
    return dict(public_id=public_id, check_in=snapshot.check_in.isoformat(),
                check_out=snapshot.check_out.isoformat(), total_krw=snapshot.total_krw,
                currency="KRW", terms_version=POLICY_VERSION,
                complete=True, public_price_allowed=True,
                source_version=hashlib.sha256((snapshot.tariff_version + "|" + POLICY_VERSION).encode()).hexdigest(),
                lines=[dict(start=x.start.isoformat(), end=x.end.isoformat(),
                            unit=x.unit, amount_krw=x.amount_krw) for x in snapshot.lines],
                fees_included=True, deposit_included=False, booking_confirmed=False)
