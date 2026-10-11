"""Reference-row compatibility must not silently relax lodging validation."""
import copy

import pytest
from offline_support.admin_stats_contract import (
    admin_stats_contract_errors, NEUTRAL_REFERENCE_FIELDS,
)

REQUIRED = {
    "type", "building_count", "units", "favorites", "listing_requests",
    "broker_badge", "store_realty", "store_total", "report_rate",
    "permit_count", "room_count", "closed_rate", "lodging_metric",
    "report_rate_numerator", "report_rate_denominator", "report_rate_basis",
}


def payload(count=0, items=0):
    total = dict.fromkeys(REQUIRED, 0)
    total.update(type="전체", building_count=40, units=400,
                 auction_building_count=count)
    lodging = dict(total, type="생활")
    reference = dict(type="공매", building_count=count,
                     auction_building_count=count, auction_item_count=items,
                     reference_only=True)
    return [total, lodging, reference]


@pytest.mark.parametrize("counts", [(0, 0), (4, 7)])
@pytest.mark.parametrize("compatibility", [False, True])
def test_zero_and_nonzero_reference_preserve_lodging_contract(counts, compatibility):
    rows = payload(*counts)
    if compatibility:
        rows[-1].update(NEUTRAL_REFERENCE_FIELDS)
    assert admin_stats_contract_errors(rows, REQUIRED) == []


@pytest.mark.parametrize("corruption", [
    "missing_reference", "duplicate_reference", "missing_lodging_column",
    "false_reference", "unexpected_room_column", "negative_count",
    "boolean_count", "missing_count", "inconsistent_total",
    "more_buildings_than_items", "lodging_marked_reference", "partial_compatibility",
])
def test_each_corrupt_contract_remains_a_failure(corruption):
    rows = payload(4, 7)
    if corruption == "missing_reference":
        rows.pop()
    elif corruption == "duplicate_reference":
        rows.append(copy.deepcopy(rows[-1]))
    elif corruption == "missing_lodging_column":
        rows[1].pop("room_count")
    elif corruption == "false_reference":
        rows[-1]["reference_only"] = False
    elif corruption == "unexpected_room_column":
        rows[-1]["room_count"] = 500
    elif corruption == "negative_count":
        rows[-1]["building_count"] = -1
    elif corruption == "boolean_count":
        rows[-1]["auction_item_count"] = True
    elif corruption == "missing_count":
        rows[-1].pop("auction_item_count")
    elif corruption == "inconsistent_total":
        rows[0]["auction_building_count"] = 5
    elif corruption == "more_buildings_than_items":
        rows[-1]["auction_item_count"] = 3
    elif corruption == "lodging_marked_reference":
        rows[1]["reference_only"] = True
    elif corruption == "partial_compatibility":
        rows[-1]["room_count"] = 0
    assert admin_stats_contract_errors(rows, REQUIRED)


@pytest.mark.parametrize("key", list(NEUTRAL_REFERENCE_FIELDS))
def test_compatibility_cells_cannot_contain_lodging_metrics(key):
    rows = payload(4, 7)
    rows[-1].update(NEUTRAL_REFERENCE_FIELDS)
    expected = NEUTRAL_REFERENCE_FIELDS[key]
    rows[-1][key] = 1 if type(expected) is int else 0
    assert admin_stats_contract_errors(rows, REQUIRED)


def test_actual_authenticated_endpoint_response_and_corruptions():
    # Use a fresh application process: unrelated collection fixtures must not
    # replace the DB or stats implementation under this integration contract.
    import os
    from pathlib import Path
    import subprocess
    import sys
    root = os.environ.get("HOMENSTAY_LEGACY_SOCKET", "")
    assert root.startswith("/tmp/homenstay-legacy-pg-") and Path(root, ".owned").is_file(), (
        "FIXTURE_SETUP: endpoint contract requires the owned offline runner")
    script = """
import copy, json
import app as module
from offline_support.admin_stats_contract import admin_stats_contract_errors,NEUTRAL_REFERENCE_FIELDS
required=REQUIRED
client=module.app.test_client()
headers={'X-Forwarded-For':'198.18.0.42'}
login=client.post('/api/admin/login',json={'email':'ADMIN','password':'ADMIN'},headers=headers)
assert login.status_code==200 and login.get_json()['ok'],login.status_code
module._rebuild_master_stats(force=True)
response=client.get('/api/admin/buildings/full-stats',headers=headers)
assert response.status_code==200,response.status_code
rows=response.get_json()['rows']
assert not admin_stats_contract_errors(rows,required)
reference=next(r for r in rows if r['type']=='공매')
assert NEUTRAL_REFERENCE_FIELDS.keys()<=reference.keys()
for key,expected in NEUTRAL_REFERENCE_FIELDS.items():
    changed=copy.deepcopy(rows)
    target=next(r for r in changed if r['type']=='공매')
    target[key]=1 if type(expected) is int else 0
    assert admin_stats_contract_errors(changed,required),key
"""
    script = script.replace("required=REQUIRED", "required=" + repr(REQUIRED))
    result = subprocess.run([sys.executable, "-c", script],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
