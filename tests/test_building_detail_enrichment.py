"""No DB/network calls: preservation, stage commits and source parsing."""
import copy
import json
import re
import unittest
from unittest.mock import patch

import building_detail_enrichment as detail
import building_registry as registry


class FakeConnection:
    def __init__(self):
        self.building = {
            "id": 24841, "sgg_cd": "51210", "umd_nm": "조양동", "jibun": "1383-18",
            "mgm_bldrgst_pk": "11381100208970", "arch_area": None,
            "ride_use_elvt_cnt": 0, "detail_fetched_at": "old-success",
            "last_inspection_submit_day": "2020-01-01",
        }
        self.record = None
        self.snapshots = []
        self.result = None

    def cursor(self):
        return self

    def execute(self, sql, params):
        sql = " ".join(sql.split())
        if sql.startswith("INSERT INTO app_meta"):
            self.record = {**(self.record or {}), **json.loads(params[1])}
            self.result = {"value": json.dumps(self.record)}
        elif sql.startswith("SELECT *"):
            self.result = self.building.copy()
        elif sql.startswith("SELECT value"):
            self.result = {"value": json.dumps(self.record)} if self.record else None
        elif sql.startswith("UPDATE app_meta"):
            self.record = json.loads(params[0])
        elif sql.startswith("UPDATE master_buildings"):
            fields = re.findall(r"(\w+)=COALESCE\(", sql)
            for field, value in zip(fields, params):
                if self.building.get(field) is None:
                    self.building[field] = value

    def fetchone(self):
        return self.result

    def commit(self):
        self.snapshots.append(copy.deepcopy(self.building))

    def rollback(self):
        pass

    def close(self):
        pass


class BuildingDetailTests(unittest.TestCase):
    def test_actual_zoning_response_field_names(self):
        values = detail.stage_values("zoning", [
            {"jijiguGbCdNm": "용도지역", "jijiguCdNm": "일반상업지역"},
            {"jijiguGbCdNm": "용도지구", "jijiguCdNm": "고도지구"},
        ], {})
        self.assertEqual(values["jiyuk_nm"], "일반상업지역")
        self.assertEqual(values["jigu_nm"], "고도지구")
        self.assertIsNone(values["guyuk_nm"])

    def test_inspection_identity_requires_number_and_official_parcel(self):
        building = FakeConnection().building
        row = {"mgmBldrgstPk": "51210-100208970", "sigunguCd": "51210", "bun": "1383", "ji": "0018"}
        self.assertTrue(detail.inspection_identity_matches(row, building))
        self.assertFalse(detail.inspection_identity_matches({**row, "ji": "0019"}, building))
        self.assertFalse(detail.inspection_identity_matches({**row, "sigunguCd": "41463"}, building))

    def test_same_parcel_with_wrong_title_id_is_not_selected(self):
        with self.assertRaises(ValueError):
            detail.select_title([{"mgmBldrgstPk": "different"}], FakeConnection().building)
        with self.assertRaises(ValueError):
            detail.select_title([{}, {}], {})

    def test_zero_preserved_invalid_numbers_rejected_and_date_placeholders_empty(self):
        self.assertEqual(detail.parse_value("ride_use_elvt_cnt", "0"), 0)
        self.assertIsNone(detail.parse_value("permit_day", "00000000"))
        for value in ("nan", "inf", "-1"):
            with self.assertRaises(ValueError):
                detail.parse_value("arch_area", value)

    def test_parking_total_requires_all_four_original_counts(self):
        raw = {"mgmBldrgstPk": "one", "indrAutoUtcnt": "12", "oudrAutoUtcnt": "0",
               "indrMechUtcnt": "0", "oudrMechUtcnt": "2"}
        self.assertEqual(detail.stage_values("title", [raw], {"mgm_bldrgst_pk": "one"})["tot_pkng_cnt"], 14)
        self.assertIsNone(detail.stage_values("title", [{**raw, "oudrMechUtcnt": ""}],
                                             {"mgm_bldrgst_pk": "one"})["tot_pkng_cnt"])

    def test_observer_counts_every_http_retry(self):
        import requests
        response = type("Response", (), {"raise_for_status": lambda self: None})()
        seen = []
        with patch.object(registry, "public_api_get", side_effect=[
            requests.exceptions.ConnectTimeout("safe"), response
        ]), patch.object(registry.time, "sleep"):
            with registry.observe_requests(seen.append):
                registry._get_with_retry(registry.BLD_TITLE_URL, {}, 1)
        self.assertEqual(seen, [registry.BLD_TITLE_URL, registry.BLD_TITLE_URL])

    def test_budget_reached_sends_no_request(self):
        from quota_policy import QuotaExhausted
        def exhausted(_url):
            raise QuotaExhausted("budget reached")
        with patch.object(registry, "public_api_get") as request:
            with registry.observe_requests(exhausted):
                with self.assertRaises(QuotaExhausted):
                    registry._get_with_retry(registry.BLD_TITLE_URL, {}, 1)
        request.assert_not_called()

    def test_claim_lease_busy_does_not_call_sources(self):
        conn = FakeConnection()
        execute = conn.execute
        def busy(sql, params):
            execute(sql, params)
            if sql.strip().startswith("INSERT INTO app_meta"):
                conn.result = None
                conn.record["owner"] = "someone-else"
        conn.execute = busy
        with patch.object(detail, "get_conn", return_value=conn), \
             patch.object(registry, "_fetch_title_rows") as fetch:
            self.assertEqual(detail.enrich(24841, None), {"busy": True})
        fetch.assert_not_called()
        self.assertEqual(conn.record["owner"], "someone-else")

    def test_successful_title_commits_before_failed_inspection_preserving_old_values(self):
        conn = FakeConnection()
        def failed_inspection(*args, **kwargs):
            self.assertEqual(conn.building["arch_area"], 430.38)
            self.assertTrue(any(s.get("arch_area") == 430.38 for s in conn.snapshots))
            raise RuntimeError("inspection unavailable")
        with (
            patch.object(detail, "get_conn", return_value=conn),
            patch.object(registry, "_fetch_title_rows", return_value=[
                {"mgmBldrgstPk": "11381100208970", "archArea": "430.38", "rideUseElvtCnt": "2"}
            ]),
            patch.object(registry, "fetch_jijigu_rows", return_value=[]),
            patch.object(registry, "fetch_maintenance_history", side_effect=failed_inspection),
        ):
            bjd = type("Map", (), {"find_bjdong_cd": lambda *args: "10800"})()
            result = detail.enrich(24841, bjd)
        self.assertEqual(conn.building["ride_use_elvt_cnt"], 0)
        self.assertEqual(conn.building["last_inspection_submit_day"], "2020-01-01")
        self.assertEqual(conn.building["detail_fetched_at"], "old-success")
        self.assertEqual(result["stages"]["title"]["status"], "ok")
        self.assertEqual(result["stages"]["zoning"]["status"], "empty")
        self.assertEqual(result["stages"]["inspection"]["status"], "failed")
        self.assertFalse(result["running"])
        self.assertNotIn("error", result["stages"]["inspection"])
        self.assertNotIn("owner", conn.record)

    def test_success_and_empty_are_not_retried_failed_waits_for_backoff(self):
        status = {"stages": {"title": {"status": "ok"}, "zoning": {"status": "empty"},
                             "inspection": {"status": "failed", "retry_at": 200}}}
        self.assertEqual(detail.due_stages(status, 100), [])
        self.assertEqual(detail.due_stages(status, 201), ["inspection"])

    def test_http_200_provider_error_does_not_become_empty(self):
        response = type("Response", (), {"content": b"<response><header><resultCode>30</resultCode><resultMsg>denied</resultMsg></header><body><items/></body></response>"})()
        with patch.object(registry, "_get_with_retry", return_value=response):
            with self.assertRaises(RuntimeError):
                registry.fetch_jijigu_rows("51210", "10800", "0", "1383", "18")
            with self.assertRaises(RuntimeError):
                registry.fetch_maintenance_history("51210", "10800", "0", "1383", "18")

    def test_auxiliary_pagination_does_not_drop_later_records(self):
        responses = [
            type("Response", (), {"content": f"<response><body><totalCount>2</totalCount><items><item><jijiguCdNm>zone{i}</jijiguCdNm></item></items></body></response>".encode()})()
            for i in range(2)
        ]
        with patch.object(registry, "_get_with_retry", side_effect=responses) as request:
            rows = registry.fetch_jijigu_rows("51210", "10800", "0", "1383", "18")
        self.assertEqual(len(rows), 2)
        self.assertEqual(request.call_args_list[1].kwargs["params"]["pageNo"], 2)


if __name__ == "__main__":
    unittest.main()
