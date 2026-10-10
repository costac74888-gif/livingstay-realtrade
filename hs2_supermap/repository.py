from hs2_design.domain import ContractError
from hs2_listings.review import public_rows
from .contracts import LAYERS, point, slots, visible_stay, visible_legacy, within


class SuperMapRepository:
    def __init__(self, calendar, *, public_geometry, public_location_match, legacy_layers):
        if (not callable(public_geometry) or not callable(public_location_match)
                or set(legacy_layers) != set(LAYERS[1:]) or not all(callable(x) for x in legacy_layers.values())):
            raise ValueError("Trusted public geometry/location/native read adapters required")
        self.calendar, self.public_geometry = calendar, public_geometry
        self.public_location_match, self.legacy_layers = public_location_match, legacy_layers

    def search(self, values):
        items, counts, withheld, truncated = [], {}, 0, {}
        for layer in values["layers"]:
            rows = []
            if layer == "stay":
                safe = public_rows(self.calendar.registrations)
                if len(safe) > 500:
                    raise ContractError("CATALOG_LIMIT")
                for public in safe:
                    with self.calendar.registrations.transaction() as c:
                        c.execute("SELECT id FROM hs2_dev.registration_applications WHERE public_id=%s", (public["public_id"],))
                        raw = c.fetchone()
                        if not raw:
                            continue
                        application = self.calendar.registrations.row(c, str(raw[0]))
                    if application["status"] != "approved":
                        continue
                    if values["q"] and self.public_location_match(public["public_id"], values["q"]) is not True:
                        continue
                    geometry = point(self.public_geometry(public["public_id"]), limited=True)
                    quote = None
                    if values["check_in"]:
                        try:
                            quote = self.calendar.quote(public["public_id"], values["check_in"], values["check_out"])
                        except ContractError:
                            continue
                    # A second current-publication read prevents a withdrawal or
                    # edit during source/geometry lookup from leaking old data.
                    if public["public_id"] not in {r["public_id"] for r in public_rows(self.calendar.registrations)}:
                        continue
                    row = visible_stay(public, application, quote, geometry, values)
                    if row:
                        rows.append(row)
            else:
                raw = self.legacy_layers[layer](values)
                if not isinstance(raw, dict) or set(raw) != {"items", "truncated"} or type(raw["truncated"]) is not bool:
                    raise ContractError("NATIVE_LAYER_RESULT_REQUIRED")
                if not isinstance(raw["items"], list) or len(raw["items"]) > 500:
                    raise ContractError("NATIVE_LAYER_LIMIT")
                rows = [visible_legacy(layer, r) for r in raw["items"]]
                rows = [r for r in rows if within(r["point"], values["bounds"])]
                truncated[layer] = raw["truncated"]
            if len({r["public_id"] for r in rows}) != len(rows):
                raise ContractError("DUPLICATE_LAYER_ID")
            if layer == "stay" and values["sort"] == "total_asc":
                rows.sort(key=lambda r: (r["quote"] is None, r["quote"]["total_krw"] if r["quote"] else 0, r["public_id"]))
            else:
                rows.sort(key=lambda r: r["public_id"])
            counts[layer] = len(rows)
            truncated[layer] = truncated.get(layer, False) or len(rows) > 60
            rows = rows[:60]
            withheld += sum(r["point"] is None for r in rows)
            items.extend(rows)
        return dict(items=items, markers=slots(items), counts=counts, truncated=truncated,
                    withheld_count=withheld, native_statistics_changed=False)

    def detail(self, layer, key, values):
        if layer not in LAYERS or layer not in values["layers"]:
            raise ContractError("LAYER_NOT_SELECTED")
        # Reuses fresh privacy/publication/price gates; no direct private lookup.
        result = self.search({**values, "layers": [layer]})
        match = next((r for r in result["items"] if r["public_id"] == key), None)
        if not match:
            raise ContractError("PUBLIC_POINT_NOT_FOUND")
        return dict(item=match, booking_confirmed=False)
