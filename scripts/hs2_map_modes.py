"""Owned QA map views; offline public-field snapshots, never live DB connections."""
import hashlib
import json
import math
from pathlib import Path
from flask import jsonify, request
from scripts.hs2_seongsu_seed import require_owned

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "generated-artifacts/map-modes"


class FacilitySnapshot:
    def __init__(self, directory=SNAPSHOT):
        self.rows = []
        self.error = None
        try:
            manifest = json.loads((directory / "snapshot.json").read_text())
            seen = set()
            for part in manifest["parts"]:
                name = part["name"]
                if Path(name).name != name or not name.startswith("facilities-"):
                    raise ValueError("Invalid snapshot path")
                data = (directory / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != part["sha256"]:
                    raise ValueError("Snapshot fingerprint mismatch")
                for raw in json.loads(data):
                    key, name, kind, region, locality, lat, lng = raw
                    if key in seen or len(key) != 32 or kind in {"", "미분류", "mixed_use_excluded"}:
                        raise ValueError("Invalid facility record")
                    seen.add(key)
                    located = (type(lat) in (int, float) and type(lng) in (int, float)
                               and math.isfinite(lat) and math.isfinite(lng)
                               and 32 <= lat <= 39.5 and 124 <= lng <= 132)
                    self.rows.append(dict(id="facility-" + key, name=str(name)[:200],
                        kind=str(kind)[:80], region=str(region)[:100], locality=str(locality)[:100],
                        point={"lat": lat, "lng": lng} if located else None))
            if len(self.rows) != manifest["total"]:
                raise ValueError("Snapshot count mismatch")
            self.captured_at = manifest["captured_at"]
            self.source = manifest.get("source", "development_public_field_snapshot")
            self.reference_count = manifest.get("reference_count", 85617)
            self.reference_verified = False
            if self.source == "production_readonly_public_field_snapshot":
                fence = manifest["public_source_fence"]
                if (fence["before"] != fence["after"]
                    or any(fence["before"][k] != fence["counts"][k]
                           for k in ("total", "located", "fingerprint"))
                    or int(fence["counts"]["total"]) != len(self.rows)
                    or int(fence["counts"]["master_total"]) != self.reference_count
                    or int(fence["counts"]["located"]) != sum(r["point"] is not None for r in self.rows)
                    or manifest.get("production_writes") is not False
                    or manifest.get("contains_customer_or_owner_fields") is not False):
                    raise ValueError("Unverified public source audit")
                self.reference_verified = True
            elif self.source != "development_public_field_snapshot":
                raise ValueError("Unknown public source")
        except (OSError, ValueError, KeyError, TypeError):
            self.rows = []
            self.captured_at = None
            self.source = None
            self.reference_count = None
            self.reference_verified = False
            self.error = "공개 시설 스냅샷 미연결 또는 검증 실패 · 가상 시설로 대체하지 않습니다"
        self.located = sum(r["point"] is not None for r in self.rows)

    def status(self):
        return dict(connected=self.error is None, total=len(self.rows),
            map_connectable=self.located, without_coordinates=len(self.rows)-self.located,
            reference_count=self.reference_count, reference_count_verified=self.reference_verified,
            source=self.source, captured_at=self.captured_at, live_connection=False,
            message=self.error, synthetic=False)

    def matching(self, query, coordinates="all"):
        q = "".join(query.split()).casefold()
        return [r for r in self.rows
                if (coordinates == "all" or (r["point"] is None) == (coordinates == "missing"))
                and (not q or q in
                "".join((r["name"] + r["kind"] + r["region"] + r["locality"]).split()).casefold())]

    def viewport(self, bounds, zoom, query=""):
        south, west, north, east = bounds
        rows = [r for r in self.matching(query) if r["point"] is not None
                and south <= r["point"]["lat"] <= north and west <= r["point"]["lng"] <= east]
        if zoom < 7 and len(rows) <= 160:
            return [dict(**r, count=1, cluster=False) for r in rows], len(rows)
        buckets = {}
        dy = max((north-south)/10, .0003 * 2**(zoom-1))
        dx = max((east-west)/14, dy)
        for row in rows:
            p = row["point"]
            buckets.setdefault((int((p["lat"]-south)/dy), int((p["lng"]-west)/dx)), []).append(row)
        clusters = []
        for (y, x), group in sorted(buckets.items()):
            clusters.append(dict(id=f"facility-cluster-{y}-{x}", cluster=True, count=len(group),
                name="숙박시설", point=dict(lat=sum(r["point"]["lat"] for r in group)/len(group),
                lng=sum(r["point"]["lng"] for r in group)/len(group))))
        return clusters, len(rows)


def install(app):
    require_owned(app)
    source = FacilitySnapshot()
    app.fixture_facility_snapshot = source
    original_results = app.view_functions["hs2_supermap.results"]

    def listing_results(owner):
        require_owned(app)
        if any(len(request.args.getlist(k)) != 1 for k in request.args):
            return jsonify(ok=False, code="DUPLICATE_FILTER"), 400
        args = request.args.copy()
        # Layout mode is NOT an ownership grant. Keep the existing public repo
        # gates; never call an owner/private listing projection or join facilities.
        args["layers"] = args.get("layers", "stay,sale,business,auction") if owner else "stay"
        with app.test_request_context("/hs2/search/api/results", query_string=args):
            blocked = app.preprocess_request()
            return blocked if blocked is not None else original_results()

    app.add_url_rule("/hs2/search/api/consumer-results", "preview_consumer_results",
                     lambda: listing_results(False))
    app.add_url_rule("/hs2/search/api/owner-results", "preview_owner_results",
                     lambda: listing_results(True))

    @app.get("/__development__/map-modes/facilities")
    def facilities():
        require_owned(app)
        if request.args.get("mode") != "owner":
            return jsonify(ok=False, code="OWNER_VIEW_REQUIRED"), 403
        allowed = {"mode", "view", "q", "page", "zoom", "south", "west", "north", "east", "coordinates"}
        if set(request.args) - allowed or any(len(request.args.getlist(k)) != 1 for k in request.args):
            return jsonify(ok=False, code="INVALID_QUERY"), 400
        q = request.args.get("q", "")
        if len(q) > 100:
            return jsonify(ok=False, code="INVALID_QUERY"), 400
        if source.error:
            return jsonify(ok=False, status=source.status()), 503
        try:
            view = request.args.get("view", "map")
            if view == "directory":
                coordinates = request.args.get("coordinates", "all")
                if coordinates not in {"all", "missing", "located"}:
                    raise ValueError()
                page = int(request.args.get("page", 1))
                if not 1 <= page <= 10000:
                    raise ValueError()
                rows = source.matching(q, coordinates)
                return jsonify(ok=True, status=source.status(), page=page, total=len(rows),
                    page_size=40, items=rows[(page-1)*40:page*40])
            if view != "map" or request.args.get("coordinates", "all") != "all":
                raise ValueError()
            zoom = int(request.args.get("zoom", 13))
            bounds = tuple(float(request.args.get(k, d)) for k, d in
                           (("south", 32), ("west", 124), ("north", 39.5), ("east", 132)))
            south, west, north, east = bounds
            if (not 1 <= zoom <= 14 or not all(math.isfinite(v) for v in bounds)
                or not -90 <= south < north <= 90 or not -180 <= west < east <= 180):
                raise ValueError()
            items, count = source.viewport(bounds, zoom, q)
            return jsonify(ok=True, status=source.status(), items=items, viewport_count=count,
                           marker_count=len(items), zoom=zoom)
        except (ValueError, TypeError, OverflowError):
            return jsonify(ok=False, code="INVALID_QUERY"), 400
