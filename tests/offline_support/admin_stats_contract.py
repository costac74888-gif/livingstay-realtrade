"""Separate auction reference rows without exempting any lodging assertion."""

NEUTRAL_REFERENCE_FIELDS = {
    "units": 0, "favorites": 0, "listing_requests": 0, "broker_badge": 0,
    "store_realty": 0, "store_total": 0, "report_rate": None,
    "permit_count": 0, "room_count": 0, "closed_rate": None,
    "lodging_metric": "not_applicable", "report_rate_numerator": 0,
    "report_rate_denominator": 0, "report_rate_basis": "not_applicable",
}


def admin_stats_contract_errors(rows, lodging_required):
    lodging = [row for row in rows if row.get("type") != "공매"]
    reference = [row for row in rows if row.get("type") == "공매"]
    errors = []
    if (not lodging or any(not lodging_required <= set(row) for row in lodging)
            or any(row.get("reference_only") is True for row in lodging)):
        errors.append("관리자 전체 통계 원본 컬럼이 사라짐")
    totals = [row for row in lodging if row.get("type") == "전체"]
    reference_fields = {
        "type", "building_count", "auction_building_count",
        "auction_item_count", "reference_only",
    }
    if len(reference) != 1 or len(totals) != 1:
        errors.append("공매 참고행·숙박 전체행이 각각 한 행이 아님")
        return errors
    row = reference[0]
    # The merged application emits neutral compatibility cells for a uniform
    # administrator table. Accept that complete shape and the original compact
    # shape, never arbitrary extra cells or real lodging metrics.
    compatible_fields = reference_fields | NEUTRAL_REFERENCE_FIELDS.keys()
    if set(row) not in (reference_fields, compatible_fields) or row.get("reference_only") is not True:
        errors.append("공매 참고행 필드·참고용 표식이 잘못됨")
    for key, expected in NEUTRAL_REFERENCE_FIELDS.items():
        if key in row and (type(row[key]) is not type(expected) or row[key] != expected):
            errors.append("공매 참고행에 숙박 수치·신고율이 섞임: " + key)
    counts = [row.get(key) for key in
              ("building_count", "auction_building_count", "auction_item_count")]
    if any(type(value) is not int or value < 0 for value in counts):
        errors.append("공매 참고행 건수는 음수가 아닌 정수여야 함")
    elif (counts[0] != counts[1] or counts[1] > counts[2]
          or totals[0].get("auction_building_count") != counts[1]):
        errors.append("공매 물건수·연결건물수·전체 참고수가 일치하지 않음")
    return errors
