"""Building-level lodging report status helpers."""

from lodging_classification import is_active_status, lodging_type_for_hygiene


def summarize_building_report_status(permits, expected_type):
    """Return (has_active_report, has_any_report) for one building and type."""
    relevant = [
        permit for permit in permits
        if (
            expected_type == "복합"
            or lodging_type_for_hygiene(permit.get("hygiene_type")) == expected_type
        )
    ]
    return (
        any(is_active_status(permit.get("biz_status_name")) for permit in relevant),
        bool(relevant),
    )