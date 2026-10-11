"""Build a QA-only public snapshot from saved read-only replica query results.

No database, network, credentials, customer, owner or financial fields.
Generated inputs and outputs must stay outside Git and deployment assets.
"""
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "generated-artifacts/public-facility-audit"
OUTPUT = ROOT / "generated-artifacts/map-modes"


def audit_row(path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError("Exactly one public count audit required")
    return rows[0]


def build(audit=AUDIT, output=OUTPUT):
    before, after, counts = (audit_row(audit / name) for name in
                            ("before.csv", "after.csv", "counts.csv"))
    keys = ("total", "located", "fingerprint")
    if before != after or any(before[key] != counts[key] for key in keys):
        raise ValueError("Public source changed during export; old snapshot retained")
    expected = int(counts["total"])
    pages = sorted(audit.glob("page-*.csv"))
    if len(pages) != math.ceil(expected / 4000):
        raise ValueError("Incomplete public export")
    rows, seen = [], set()
    for index, path in enumerate(pages):
        if path.name != f"page-{index:03d}.csv":
            raise ValueError("Public export page gap")
        csv.field_size_limit(4_000_000)
        with path.open(newline="", encoding="utf-8") as stream:
            records = list(csv.reader(stream))
        if len(records) != 2 or records[0] != ["rows"] or len(records[1]) != 1:
            raise ValueError("Truncated public query result")
        batch = json.loads(records[1][0])
        if len(batch) != min(4000, expected - index * 4000):
            raise ValueError("Public page count mismatch")
        for row in batch:
            if len(row) != 7 or row[0] in seen or len(row[0]) != 32:
                raise ValueError("Invalid or duplicate public record")
            seen.add(row[0])
        rows.extend(batch)
    located = sum(type(r[5]) in (int, float) and type(r[6]) in (int, float)
                  and math.isfinite(r[5]) and math.isfinite(r[6])
                  and 32 <= r[5] <= 39.5 and 124 <= r[6] <= 132 for r in rows)
    if len(rows) != expected or located != int(counts["located"]):
        raise ValueError("Public totals do not match replica audit")
    output.mkdir(parents=True, exist_ok=True)
    previous = output / "snapshot.json"
    if previous.exists():
        (audit / "previous-snapshot.json").write_bytes(previous.read_bytes())
    parts = []
    for index, start in enumerate(range(0, len(rows), 4000)):
        name = f"facilities-prod-public-{index:03d}.json"
        raw = json.dumps(rows[start:start + 4000], ensure_ascii=False,
                         separators=(",", ":")).encode()
        (output / name).write_bytes(raw)
        parts.append(dict(name=name, sha256=hashlib.sha256(raw).hexdigest()))
    manifest = dict(
        captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        total=expected, located=located, parts=parts,
        source="production_readonly_public_field_snapshot",
        reference_count=int(counts["master_total"]), reference_count_verified=True,
        public_source_fence=dict(before=before, after=after, counts=counts),
        production_writes=False, contains_customer_or_owner_fields=False,
        qa_only=True, live_connection=False,
    )
    temp = output / "snapshot.json.tmp"
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    os.replace(temp, previous)
    (audit / "verified-snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2))
    return dict(total=expected, located=located, without_coordinates=expected-located,
                reference_count=manifest["reference_count"], source=manifest["source"])


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
