"""Offline contracts for intervals and immutable prices, not a booking engine."""
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .domain import Classification, ContractError, StayKind


def money(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ContractError("POSITIVE_INTEGER_KRW_REQUIRED")
    return value


@dataclass(frozen=True)
class Terms:
    version: str
    timezone: str
    reviewed: bool
    month_basis: str | None = None

    def require_resolved(self):
        if not self.version or self.reviewed is not True:
            raise ContractError("UNRESOLVED_BUSINESS_POLICY")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ContractError("BUSINESS_TIMEZONE_REQUIRED") from None


@dataclass(frozen=True)
class PriceLine:
    start: date
    end: date
    unit: str
    amount_krw: int

    def __post_init__(self):
        if type(self.start) is not date or type(self.end) is not date:
            raise ContractError("BUSINESS_LOCAL_DATES_REQUIRED")
        if self.end <= self.start or self.unit not in {"night", "week", "month"}:
            raise ContractError("INVALID_PRICE_PERIOD")
        money(self.amount_krw)


@dataclass(frozen=True)
class PriceSnapshot:
    listing_id: str
    check_in: date
    check_out: date
    kind: StayKind
    classification_evidence: str
    classification_version: str
    tariff_version: str
    terms_version: str
    timezone: str
    lines: tuple[PriceLine, ...]
    adjustments: tuple[tuple[str, int], ...]
    currency: str = "KRW"

    def __post_init__(self):
        if (type(self.lines) is not tuple
                or not all(isinstance(x, PriceLine) for x in self.lines)
                or type(self.adjustments) is not tuple
                or not all(type(x) is tuple for x in self.adjustments)):
            raise ContractError("DEEP_IMMUTABLE_COMPONENTS_REQUIRED")
        if self.currency != "KRW":
            raise ContractError("UNSUPPORTED_CURRENCY")

    @property
    def accommodation_krw(self):
        return sum(x.amount_krw for x in self.lines)

    @property
    def total_krw(self):
        return self.accommodation_krw + sum(x[1] for x in self.adjustments)


def validate_interval(classification: Classification, check_in, check_out):
    if type(check_in) is not date or type(check_out) is not date:
        raise ContractError("BUSINESS_LOCAL_DATES_REQUIRED")
    if classification.kind == StayKind.UNRESOLVED:
        raise ContractError("CLASSIFICATION_REQUIRES_REVIEW")
    minimum = 1 if classification.kind == StayKind.LODGING else 7
    if (check_out - check_in).days < minimum:
        raise ContractError("MINIMUM_STAY_NOT_MET")


def price_snapshot(classification, check_in, check_out, lines, *,
                   tariff_version, terms, adjustments):
    """Freeze an already resolved fixture quote; reject gaps or invented prorata.

    Month boundaries are supplied by a separately reviewed period definition,
    not calculated as 30 days here. Explicit adjustments (including an empty
    tuple) are a resolved-terms input, not a default assumption of zero tax.
    This does not reserve inventory, charge, refund or persist a booking.
    """
    validate_interval(classification, check_in, check_out)
    terms.require_resolved()
    if not tariff_version:
        raise ContractError("TARIFF_VERSION_REQUIRED")
    rows = tuple(lines)
    cursor = check_in
    for row in rows:
        if not isinstance(row, PriceLine) or row.start != cursor:
            raise ContractError("PRICE_GAP_OVERLAP_OR_UNSORTED")
        duration = (row.end - row.start).days
        if classification.kind == StayKind.LODGING:
            if row.unit != "night" or duration != 1:
                raise ContractError("LODGING_REQUIRES_DATE_PRICES")
        else:
            if row.unit == "week" and duration == 7:
                pass
            elif row.unit == "month" and duration >= 7:
                if terms.month_basis != "reviewed_explicit_periods":
                    raise ContractError("MONTH_POLICY_UNRESOLVED")
            else:
                raise ContractError("PARTIAL_PERIOD_POLICY_UNRESOLVED")
        cursor = row.end
    if not rows or cursor != check_out:
        raise ContractError("INCOMPLETE_PRICE_COVERAGE")
    components = tuple(tuple(x) for x in adjustments)
    names = set()
    for component in components:
        if (len(component) != 2 or not isinstance(component[0], str)
                or not component[0] or component[0] in names
                or type(component[1]) is not int
                or abs(component[1]) > 2**63 - 1):
            raise ContractError("INVALID_ADJUSTMENT")
        names.add(component[0])
    result = PriceSnapshot(
        classification.subject_id, check_in, check_out, classification.kind,
        classification.evidence_id, classification.decision_version,
        tariff_version, terms.version, terms.timezone, rows, components,
    )
    money(result.total_krw)
    return result


def lodging_date_snapshot(classification, check_in, check_out, rates, **kwargs):
    if classification.kind != StayKind.LODGING:
        raise ContractError("LODGING_CLASSIFICATION_REQUIRED")
    validate_interval(classification, check_in, check_out)
    rows = []
    cursor = check_in
    while cursor < check_out:
        if cursor not in rates:
            raise ContractError("MISSING_DATE_RATE")
        rows.append(PriceLine(cursor, cursor + timedelta(days=1), "night", rates[cursor]))
        cursor += timedelta(days=1)
    return price_snapshot(classification, check_in, check_out, rows, **kwargs)
