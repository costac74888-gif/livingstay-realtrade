"""Read-only adapters for original public APIs; no default URL/auth/DB."""
from hs2_design.domain import ContractError


class NativePublicAdapters:
    def __init__(self, *, get_public_json, default_bounds):
        if not callable(get_public_json) or not isinstance(default_bounds, (list, tuple)) or len(default_bounds) != 4:
            raise ValueError("Trusted original GET reader and map bounds required")
        self.get_public_json, self.default_bounds = get_public_json, default_bounds

    @staticmethod
    def projection(row, layer):
        if not isinstance(row, dict) or row.get("id") is None:
            raise ContractError("NATIVE_PUBLIC_ID_REQUIRED")
        limited = row.get("is_limited_listing") is True
        geometry = None
        if limited:
            label = row.get("approx_location_label")
            scope = "dong" if label == "동 중심 근처" else "sgg" if label == "시군구 중심 근처" else None
            if scope:
                geometry = dict(lat=row.get("approx_lat"), lng=row.get("approx_lng"), precision="approx",
                                aggregate_scope=scope, aggregate_count=5 if scope == "dong" else 10)
        elif row.get("lat") is not None and row.get("lng") is not None:
            geometry = dict(lat=float(row["lat"]), lng=float(row["lng"]), precision="exact")
        # The original API supplies this label ONLY after its >=5/>=10 SQL
        # privacy aggregation. Never infer approval from raw building GPS.
        return dict(public=True, public_id=str(row["id"]),
                    disclosure_scope="limited" if limited else "public", public_point=geometry,
                    public_title=row.get("building_name") if layer != "auction" else row.get("item_name"))

    def listings(self, layer, values):
        if layer not in {"sale", "business"}:
            raise ContractError("INVALID_NATIVE_LAYER")
        rows, truncated = {}, False
        targets = ("unit", "whole") if layer == "sale" else ("business_rights",)
        for target in targets:
            for scope in ("public", "limited"):
                if target == "unit" and scope == "limited":
                    continue
                params = dict(limit="50", offset="0", channel="direct",
                              transaction_target=target, disclosure_scope=scope)
                if layer == "sale":
                    params["deal_type"] = "매매"
                # The old endpoint searches private building_name even in its
                # limited SQL branch. Never send q there; compare only redacted
                # public region labels afterward to avoid inference leaks.
                if scope == "public" and values["q"]:
                    params["q"] = values["q"]
                result = self.get_public_json("/api/listings", params)
                if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("items"), list):
                    raise ContractError("NATIVE_SOURCE_UNAVAILABLE")
                if len(result["items"]) > 50:
                    raise ContractError("NATIVE_LAYER_LIMIT")
                truncated |= result.get("has_more") is True
                for raw in result["items"]:
                    if scope == "limited":
                        if raw.get("is_limited_listing") is not True:
                            raise ContractError("NATIVE_PRIVACY_PROJECTION_REQUIRED")
                        label = raw.get("building_name", "")
                        if values["q"] and values["q"] not in label:
                            continue
                    row = self.projection(raw, layer)
                    rows[row["public_id"]] = row
        return dict(items=list(rows.values()), truncated=truncated)

    def auctions(self, values):
        south, west, north, east = values["bounds"] or self.default_bounds
        result = self.get_public_json("/api/auctions/map",
            dict(south=str(south), west=str(west), north=str(north), east=str(east)))
        if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("items"), list):
            raise ContractError("NATIVE_SOURCE_UNAVAILABLE")
        if len(result["items"]) > 500:
            raise ContractError("NATIVE_LAYER_LIMIT")
        return dict(items=[self.projection(r,"auction") for r in result["items"]],
                    truncated=result.get("truncated") is True)

    def ports(self):
        return dict(sale=lambda values:self.listings("sale",values),
                    business=lambda values:self.listings("business",values), auction=self.auctions)
