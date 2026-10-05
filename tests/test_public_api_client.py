"""Final relay specification T1–T10. HTTP, quotas and sleeps are all mocked."""
import os
import json
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import quote, quote_plus

import requests
import public_api_client as relay
import building_registry as registry
import sync_batch
import sync_brhub
import discover_new_buildings
import sync_rural_hanok_trades as rural
from secret_redaction import PUBLIC_API_SECRET_NAMES, redact_env_secrets

BLD = registry.BLD_TITLE_URL
RTMS = sync_batch.RTMS_URL
SAMPLE = "only-test+/= credential"
ENV = {
    "RELAY_ENABLED":"1", "RELAY_USE_BLDG_HUB":"1", "RELAY_USE_RTMS":"1",
    "RELAY_BASE_URL":"https://relay.example.test",
    "RELAY_TOKEN":"only-test-realtime-token", "RELAY_TOKEN_BATCH":"only-test-batch-token",
}
XML = b"<response><header><resultCode>000</resultCode></header><body><totalCount>0</totalCount><items/></body></response>"


def response(status=200, code=None):
    result = requests.Response()
    result.status_code = status
    result.url = "https://relay.example.test/v1/fetch?url=" + quote(BLD + "?serviceKey=" + SAMPLE, safe="")
    result._content = XML
    result.headers["Content-Type"] = "application/xml"
    if code:
        result.headers["X-Relay-Error"] = "1"
        result._content = ('{"relay_error":true,"code":"'+code+'","message":"'+SAMPLE+'"}').encode()
    return result


class PublicApiRelayTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, ENV))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.enterContext(patch.object(relay, "_STATUS_DIR", Path(self.directory.name)))
        self.get = self.enterContext(patch("requests.get", return_value=response()))
        self.keys = [
            patch.object(registry, "BLD_SERVICE_KEY", SAMPLE),
            patch.object(sync_batch, "RTMS_SERVICE_KEY", SAMPLE),
            patch.object(discover_new_buildings, "RTMS_SERVICE_KEY", SAMPLE),
        ]
        for key in self.keys:
            self.enterContext(key)

    def test_t1_off_is_exact_original_request_and_response(self):
        for switches in [
            {"RELAY_ENABLED":"0"}, {"RELAY_ENABLED":""},
            {"RELAY_USE_BLDG_HUB":"0"}, {"RELAY_USE_BLDG_HUB":""},
        ]:
            with self.subTest(switches=switches), patch.dict(os.environ, switches):
                self.get.reset_mock()
                result = relay.public_api_get(BLD, {"serviceKey":SAMPLE}, 15)
                self.assertIs(result, self.get.return_value)
                self.get.assert_called_once_with(BLD, params={"serviceKey":SAMPLE}, timeout=15)
                self.assertFalse((Path(self.directory.name) / "status.json").exists())

    def test_t2_realtime_four_hub_methods(self):
        for method in ("getBrTitleInfo","getBrFlrOulnInfo","getBrExposPubuseAreaInfo","getBrJijiguInfo"):
            with self.subTest(method=method):
                self.get.reset_mock()
                target = BLD.rsplit("/",1)[0] + "/" + method
                params = {"serviceKey":SAMPLE,"pageNo":1}
                self.get.return_value = response()
                result = relay.public_api_get(target, params, 10)
                self.get.assert_called_once()
                args, kwargs = self.get.call_args
                self.assertEqual(args, ("https://relay.example.test/v1/fetch",))
                self.assertEqual(set(kwargs["params"]), {"url"})
                self.assertEqual(kwargs["params"]["url"], requests.Request("GET", target, params=params).prepare().url)
                self.assertNotIn("purpose", kwargs["params"]["url"])
                self.assertEqual(kwargs["headers"], {"X-Relay-Token":ENV["RELAY_TOKEN"],"X-Relay-Purpose":"realtime"})
                self.assertEqual(kwargs["timeout"],20)
                self.assertFalse(kwargs["allow_redirects"])
                self.assertEqual(result.content, XML)
                self.assertEqual(result.headers["Content-Type"], "application/xml")

    def test_t3_batch_nrg_preserves_quota_and_result(self):
        with patch.object(sync_batch, "claim_rtms_request") as claim:
            self.assertEqual(sync_batch.fetch_nrg_trade("11110","202609"),[])
            claim.assert_not_called()  # Nrg's existing collector owns the claim, not this transport.
        self.assertEqual(self.get.call_args.kwargs["headers"]["X-Relay-Purpose"],"batch")
        self.assertEqual(self.get.call_args.kwargs["headers"]["X-Relay-Token"],ENV["RELAY_TOKEN_BATCH"])

    def test_t4_independent_service_switches(self):
        with patch.dict(os.environ, {"RELAY_USE_RTMS":"0"}):
            relay.public_api_get(RTMS,{},15,"batch")
            self.get.assert_called_once_with(RTMS,params={},timeout=15)
            self.get.reset_mock()
            relay.public_api_get(BLD,{},15)
            self.assertTrue(self.get.call_args.args[0].endswith("/v1/fetch"))

    def test_t5_non_allowed_services_stay_direct(self):
        for path in ("MtnChkHubService","ArchPmsHubService","GoCamping","lodgings","storeListInPnu","RTMSDataSvcOffiTrade"):
            with self.subTest(path=path):
                self.get.reset_mock()
                url = "https://apis.data.go.kr/1613000/"+path+"/lookup"
                relay.public_api_get(url,{},8,"batch")
                self.get.assert_called_once_with(url,params={},timeout=8)

    def test_t6_provider_429_retains_rate_limit_error(self):
        self.get.return_value = response(429)
        with patch.object(sync_batch,"claim_rtms_request"), self.assertRaises(sync_batch.RateLimitError):
            sync_batch.fetch_nrg_trade("11110","202609")
        self.get.assert_called_once()

    def test_t7_relay_429_is_not_provider_quota_or_retried(self):
        self.get.return_value = response(429,"RELAY_QUOTA")
        with patch.object(sync_batch,"claim_rtms_request"), self.assertRaises(relay.RelayError) as caught:
            sync_batch.fetch_nrg_trade("11110","202609")
        self.assertNotIsInstance(caught.exception,sync_batch.RateLimitError)
        self.assertFalse(caught.exception.retryable)
        self.get.assert_called_once()

    def test_t8_all_eight_codes_and_existing_realtime_retry_budget(self):
        for code,status in relay.ERROR_STATUS.items():
            with self.subTest(code=code):
                self.get.reset_mock()
                self.get.return_value = response(status,code)
                expected = relay.RelayRetryableError if code in relay.RETRYABLE_CODES else relay.RelayError
                with self.assertRaises(expected) as caught:
                    relay.public_api_get(BLD,{},15)
                self.assertEqual(caught.exception.status_code,status)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(caught.exception.retryable,code in relay.RETRYABLE_CODES)
                self.get.reset_mock()
                with patch.object(registry.time,"sleep") as sleep:
                    with self.assertRaises((registry.BuildingRegistryRequestError,relay.RelayError)):
                        registry._get_with_retry(BLD,{},15)
                retries = code in relay.RETRYABLE_CODES
                self.assertEqual(self.get.call_count,3 if retries else 1)
                self.assertEqual(sleep.call_count,2 if retries else 0)
                if retries:
                    self.assertTrue(all(call.args==(registry._RETRY_SLEEP,) for call in sleep.call_args_list))

    def test_t8_all_eight_codes_existing_batch_retry_policy(self):
        for code,status in relay.ERROR_STATUS.items():
            with self.subTest(code=code):
                self.get.reset_mock()
                self.get.return_value = response(status,code)
                with patch.object(sync_brhub,"claim_building_hub_request"), patch.object(sync_brhub.time,"sleep") as sleep:
                    items,pages,error,saw429 = sync_brhub._fetch_all_dong_pages(SAMPLE,"11110","10100",0)
                self.assertIsNone(items)
                self.assertEqual(pages,0)
                self.assertIn(code,error)
                self.assertFalse(saw429)
                self.assertEqual(self.get.call_count,3 if code in relay.RETRYABLE_CODES else 1)
                self.assertEqual(sleep.call_count,2 if code in relay.RETRYABLE_CODES else 0)

    def test_t9_missing_each_token_never_calls_http(self):
        for purpose,name in (("realtime","RELAY_TOKEN"),("batch","RELAY_TOKEN_BATCH")):
            with self.subTest(purpose=purpose),patch.dict(os.environ,{name:""}):
                self.get.reset_mock()
                with self.assertRaises(relay.RelayError) as caught:
                    relay.public_api_get(BLD,{"serviceKey":SAMPLE},15,purpose)
                self.assertEqual(caught.exception.code,"RELAY_AUTH")
                self.get.assert_not_called()

    def test_t10_errors_tracebacks_and_redaction_hide_credentials(self):
        dummy = {name: SAMPLE+name for name in PUBLIC_API_SECRET_NAMES}
        with patch.dict(os.environ,dummy):
            for value in dummy.values():
                variants = [value,quote(value,safe=""),quote(quote(value,safe=""),safe=""),
                            quote_plus(quote_plus(value,safe=""),safe="")]
                raw = "https://relay.example.test/v1/fetch?url="+quote(BLD+"?serviceKey="+value,safe="")
                cleaned = redact_env_secrets(raw+" "+" ".join(variants),())
                for variant in variants:
                    self.assertNotIn(variant,cleaned)
                self.assertNotIn("/v1/fetch?",cleaned)
            self.get.side_effect = requests.exceptions.ConnectTimeout(
                "https://relay.example.test/v1/fetch?url="+quote(BLD+"?serviceKey="+SAMPLE,safe=""))
            with self.assertRaises(relay.RelayRetryableError) as caught:
                relay.public_api_get(BLD,{"serviceKey":SAMPLE},15)
            rendered = "".join(traceback.format_exception(caught.exception))
            self.assertNotIn(SAMPLE,rendered)
            self.assertNotIn("/v1/fetch?",rendered)

    def test_provider_http_error_cannot_print_encoded_relay_request(self):
        self.get.return_value = response(500)
        result = relay.public_api_get(BLD,{"serviceKey":SAMPLE},15)
        with self.assertRaises(requests.HTTPError) as caught:
            result.raise_for_status()
        self.assertNotIn(SAMPLE,str(caught.exception))
        self.assertNotIn("/v1/fetch?",str(caught.exception))

    def test_provider_result_messages_are_redacted_without_changing_failure_type(self):
        from xml.etree import ElementTree as ET
        secret = SAMPLE + "RTMS_SERVICE_KEY"
        encoded = quote(secret,safe="")
        with patch.dict(os.environ,{"BLD_SERVICE_KEY":secret,"RTMS_SERVICE_KEY":secret}):
            xml = f"<response><header><resultCode>30</resultCode><resultMsg>{secret} {encoded}</resultMsg></header></response>"
            with self.assertRaises(RuntimeError) as caught:
                registry._check_api_result_code(ET.fromstring(xml))
            self.assertNotIn(secret,str(caught.exception))
            self.assertNotIn(encoded,str(caught.exception))
            self.get.return_value = response()
            self.get.return_value._content = xml.encode()
            with patch.object(rural,"_claim_call"),self.assertRaises(RuntimeError) as caught:
                rural.fetch_trade(next(iter(rural.API_ENDPOINTS)),"11110","202609",secret)
            self.assertNotIn(secret,str(caught.exception))
            self.assertNotIn(encoded,str(caught.exception))
            self.get.return_value._content = json.dumps({"response":{"header":{
                "resultCode":"30","resultMsg":secret+" "+encoded}}}).encode()
            with patch.object(sync_brhub,"claim_building_hub_request"),self.assertRaises(RuntimeError) as caught:
                sync_brhub._fetch_page(secret,"11110","10100",1)
            self.assertNotIn(secret,str(caught.exception))
            self.assertNotIn(encoded,str(caught.exception))

    def test_batch_four_rtms_apis_preserve_parsing_and_claim_per_page(self):
        for name in rural.API_ENDPOINTS:
            with self.subTest(name=name):
                self.get.reset_mock()
                self.get.return_value = response()
                with patch.object(rural,"_claim_call") as claim:
                    self.assertEqual(rural.fetch_trade(name,"11110","202609",SAMPLE),[])
                    claim.assert_called_once()
                self.assertEqual(self.get.call_args.kwargs["timeout"],(20,60))
                self.assertEqual(self.get.call_args.kwargs["headers"]["X-Relay-Purpose"],"batch")

    def test_invalid_target_and_purpose_never_leave_client(self):
        urls = [
            BLD.replace("https:","http:"), BLD.replace("apis.data.go.kr","apis.data.go.kr:443"),
            BLD+"/../escape", BLD+"/%2e%2e/escape", BLD+"?x="+"a"*8192,
        ]
        for url in urls:
            with self.subTest(url_length=len(url)):
                self.get.reset_mock()
                with self.assertRaises(relay.RelayError) as caught:
                    relay.public_api_get(url,{},15)
                self.assertEqual(caught.exception.code,"RELAY_FORBIDDEN")
                self.get.assert_not_called()
        with self.assertRaises(relay.RelayError):
            relay.public_api_get(BLD,{},15,"unexpected")

    def test_no_fallback_for_network_failures(self):
        for error in (requests.ConnectTimeout("hidden"),requests.ConnectionError("hidden"),requests.ReadTimeout("hidden")):
            with self.subTest(error_type=type(error).__name__):
                self.get.reset_mock()
                self.get.side_effect=error
                with self.assertRaises(relay.RelayRetryableError):
                    relay.public_api_get(BLD,{},15)
                self.get.assert_called_once()
                self.assertTrue(self.get.call_args.args[0].endswith("/v1/fetch"))

    def test_maintenance_remains_direct_and_realtime_parsers_keep_shapes(self):
        args = ("11110","10100","0","1","0")
        self.assertEqual(registry.fetch_maintenance_history(*args),[])
        self.assertIn("/MtnChkHubService/",self.get.call_args.args[0])
        for fn in (registry.fetch_building_title,registry.fetch_floor_outline,registry.fetch_expos_area_strict,registry.fetch_jijigu_rows):
            with self.subTest(function=fn.__name__):
                self.get.reset_mock()
                result = fn(*args,purpose="batch")
                self.assertIn(result,(None,[]))
                self.assertEqual(self.get.call_args.kwargs["headers"]["X-Relay-Purpose"],"batch")

    def test_status_has_only_allowed_fields_and_local_history(self):
        relay.public_api_get(BLD,{},15)
        self.get.return_value=response(429,"RELAY_QUOTA")
        with self.assertRaises(relay.RelayError):
            relay.public_api_get(BLD,{},15)
        data = relay.relay_status()
        self.assertEqual(set(data),{"bldg_hub","rtms"})
        row = data["bldg_hub"]
        self.assertEqual(set(row),{"enabled","last_success_at","last_error_code"})
        self.assertTrue(row["enabled"])
        self.assertTrue(row["last_success_at"])
        self.assertEqual(row["last_error_code"],"RELAY_QUOTA")
        for value in ENV.values():
            if len(value)>2:
                self.assertNotIn(value,str(data))

    def test_admin_status_requires_existing_admin_session(self):
        import app as app_module
        client = app_module.app.test_client()
        self.assertEqual(client.get("/api/admin/public-api-relay/status").status_code,401)
        with client.session_transaction() as session:
            session["admin"] = True
        result = client.get("/api/admin/public-api-relay/status")
        self.assertEqual(result.status_code,200)
        self.assertEqual(set(result.get_json()),{"ok","services"})
        self.assertEqual(set(result.get_json()["services"]),{"bldg_hub","rtms"})


if __name__ == "__main__":
    unittest.main()
