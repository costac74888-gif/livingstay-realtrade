"""JUSO transport, callers and user submission; HTTP and persistence are mocked."""
import json
import os
import tempfile
import traceback
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import requests
import address_utils as addresses
import public_api_client as relay
import zip_code_backfill as zip_backfill
from data_sync_transport import data_sync_transport_status
from datasync_board import build_board
from tests.test_public_api_client import ENV, SAMPLE, response


PARCEL = {
    "zipNo": "12345", "siNm": "서울특별시", "sggNm": "종로구",
    "emdNm": "테스트동", "liNm": "", "lnbrMnnm": "1", "lnbrSlno": "0",
    "admCd": "1111010100",
}


def provider(items=None):
    result = response()
    result.headers["Content-Type"] = "application/json"
    result._content = json.dumps({"results": {"juso": items or []}}).encode()
    return result


class JusoRelayTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            **ENV, "RELAY_USE_JUSO": "1", "JUSO_API_KEY": SAMPLE,
        }))
        self.enterContext(patch.object(addresses, "JUSO_API_KEY", SAMPLE))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(relay, "_STATUS_DIR", Path(directory)))
        self.enterContext(patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("External calls forbidden"),
        ))
        self.http = self.enterContext(patch("requests.get", return_value=provider([PARCEL])))

    def test_off_exact_arguments_flags_and_host_order(self):
        params = {
            "confmKey": SAMPLE, "currentPage": 1, "countPerPage": 1,
            "keyword": "서울 테스트로 1", "resultType": "json",
        }
        for flag in (None, "", "0", "true", "yes"):
            with self.subTest(flag=flag), patch.dict(os.environ):
                if flag is None:
                    os.environ.pop("RELAY_USE_JUSO", None)
                else:
                    os.environ["RELAY_USE_JUSO"] = flag
                self.http.reset_mock()
                self.http.side_effect = [requests.ConnectTimeout("timed out"), provider([PARCEL])]
                self.assertEqual(addresses.road_to_jibun("서울 테스트로 1, 2층 (테스트동)"), PARCEL)
                self.assertEqual([call.args[0] for call in self.http.call_args_list],
                                 list(addresses.JUSO_URLS))
                for call in self.http.call_args_list:
                    self.assertEqual(call.kwargs, {"params": params, "timeout": (5, 20)})
        self.http.side_effect = None
        self.http.reset_mock()
        with patch.dict(os.environ, {"RELAY_ENABLED": "0"}):
            addresses.road_to_jibun("서울 테스트로 1")
        self.http.assert_called_once_with(addresses.JUSO_URLS[0], params=params, timeout=(5, 20))

    def test_on_realtime_and_batch_tokens_url_masking_and_timeout(self):
        for purpose in ("realtime", "batch"):
            with self.subTest(purpose=purpose):
                self.http.reset_mock()
                self.http.return_value = provider([PARCEL])
                self.assertEqual(addresses.road_to_jibun("서울 테스트로 1", purpose=purpose), PARCEL)
                call = self.http.call_args
                self.assertEqual(call.args, (ENV["RELAY_BASE_URL"] + "/v1/fetch",))
                self.assertEqual(call.kwargs["headers"]["X-Relay-Purpose"], purpose)
                token = ENV["RELAY_TOKEN_BATCH" if purpose == "batch" else "RELAY_TOKEN"]
                self.assertEqual(call.kwargs["headers"]["X-Relay-Token"], token)
                self.assertEqual(call.kwargs["timeout"], (20, 20))
                self.assertFalse(call.kwargs["allow_redirects"])
                target = urlsplit(call.kwargs["params"]["url"])
                self.assertEqual(target.hostname, "business.juso.go.kr")
                self.assertEqual(parse_qs(target.query)["confmKey"], [SAMPLE])
                self.assertEqual(self.http.return_value.url, addresses.JUSO_URLS[0])
                self.assertNotIn(SAMPLE, self.http.return_value.url)
                self.assertNotIn("confmKey", self.http.return_value.url)

    def test_host_path_pairs_are_validated_without_dispatch(self):
        for url in addresses.JUSO_URLS:
            self.assertTrue(relay._valid_target(url))
        forbidden = (
            addresses.JUSO_URLS[0].replace("https:", "http:"),
            addresses.JUSO_URLS[0].replace("business.juso.go.kr", "evil.example.test"),
            addresses.JUSO_URLS[0].replace("business.juso.go.kr", "apis.data.go.kr"),
            addresses.JUSO_URLS[0].replace("/addrlink/", "/addrlink/../"),
            addresses.JUSO_URLS[0].replace("/addrlink/", "/addrlink/%2e/"),
            addresses.JUSO_URLS[0].replace("business.juso.go.kr", "business.juso.go.kr:443"),
            addresses.JUSO_URLS[0].replace("business.juso.go.kr", "user@business.juso.go.kr"),
            addresses.JUSO_URLS[0] + "#fragment",
            "https://business.juso.go.kr/not-allowed/search",
            "https://www.juso.go.kr/B010003/list",
        )
        for url in forbidden:
            with self.subTest(url=url):
                self.http.reset_mock()
                # Turn Onbid on too: its supported path on a JUSO host must be rejected.
                with patch.dict(os.environ, {"RELAY_USE_ONBID": "1"}):
                    with self.assertRaises(relay.RelayError) as caught:
                        relay.public_api_get(url, {"confmKey": SAMPLE}, (5, 20))
                self.assertEqual(caught.exception.code, "RELAY_FORBIDDEN")
                self.assertFalse(relay._valid_target(url))
                self.http.assert_not_called()

    def test_retryable_errors_switch_to_www_through_relay(self):
        for code in relay.RETRYABLE_CODES:
            with self.subTest(code=code):
                self.http.reset_mock()
                self.http.side_effect = [response(relay.ERROR_STATUS[code], code), provider([PARCEL])]
                self.assertEqual(addresses.road_to_jibun("서울 테스트로 1", purpose="batch"), PARCEL)
                self.assertEqual(self.http.call_count, 2)
                self.assertEqual(
                    [urlsplit(call.kwargs["params"]["url"]).hostname for call in self.http.call_args_list],
                    ["business.juso.go.kr", "www.juso.go.kr"],
                )
                self.assertTrue(all(call.args[0] == ENV["RELAY_BASE_URL"] + "/v1/fetch"
                                    for call in self.http.call_args_list))
                self.assertTrue(all(call.kwargs["headers"]["X-Relay-Purpose"] == "batch"
                                    for call in self.http.call_args_list))

    def test_exhausted_retryable_errors_are_transient_and_safe(self):
        for code in relay.RETRYABLE_CODES:
            with self.subTest(code=code):
                self.http.reset_mock()
                self.http.side_effect = None
                self.http.return_value = response(relay.ERROR_STATUS[code], code)
                with self.assertRaises(requests.ConnectionError) as caught:
                    addresses.road_to_jibun("서울 테스트로 1", purpose="batch")
                self.assertEqual(self.http.call_count, 2)
                self.assertTrue(zip_backfill._is_transient_provider_error(caught.exception))
                rendered = "".join(traceback.format_exception(caught.exception))
                for value in (SAMPLE, ENV["RELAY_BASE_URL"], ENV["RELAY_TOKEN_BATCH"], "confmKey"):
                    self.assertNotIn(value, rendered)

    def test_fatal_errors_do_not_switch_hosts_or_fall_back_directly(self):
        for purpose in ("realtime", "batch"):
            for code in ("RELAY_QUOTA", "RELAY_AUTH", "RELAY_FORBIDDEN",
                         "CIRCUIT_OPEN", "RELAY_INTERNAL"):
                with self.subTest(purpose=purpose, code=code):
                    self.http.reset_mock()
                    self.http.return_value = response(relay.ERROR_STATUS[code], code)
                    auth = code in ("RELAY_AUTH", "RELAY_FORBIDDEN")
                    kind = addresses.JusoRelayConfigurationError if auth else requests.ConnectionError
                    with self.assertRaises(kind) as caught:
                        addresses.road_to_jibun("서울 테스트로 1", purpose=purpose)
                    self.http.assert_called_once()
                    self.assertEqual(zip_backfill._is_transient_provider_error(caught.exception), not auth)
                    if auth:
                        self.assertEqual(str(caught.exception), "중계 설정 확인 필요" if purpose == "batch"
                                         else "일시적으로 주소 조회를 할 수 없습니다")
                    rendered = "".join(traceback.format_exception(caught.exception))
                    for value in (SAMPLE, ENV["RELAY_BASE_URL"], ENV["RELAY_TOKEN"], "confmKey"):
                        self.assertNotIn(value, rendered)

    def test_empty_response_and_missing_key_do_not_retry(self):
        self.http.return_value = provider([])
        self.assertIsNone(addresses.road_to_jibun("서울 테스트로 1"))
        self.http.assert_called_once()
        self.http.reset_mock()
        with patch.object(addresses, "JUSO_API_KEY", ""):
            self.assertIsNone(addresses.road_to_jibun("서울 테스트로 1"))
        self.http.assert_not_called()

    def test_direct_error_preserves_class_but_redacts_key_and_traceback(self):
        with patch.dict(os.environ, {"RELAY_USE_JUSO": "0"}):
            self.http.side_effect = requests.ConnectTimeout(
                addresses.JUSO_URLS[0] + "?confmKey=" + SAMPLE
            )
            with self.assertRaises(requests.ConnectTimeout) as caught:
                addresses.road_to_jibun("서울 테스트로 1")
        self.assertEqual(self.http.call_count, 2)
        self.assertTrue(zip_backfill._is_transient_provider_error(caught.exception))
        self.assertNotIn(SAMPLE, "".join(traceback.format_exception(caught.exception)))

    def test_missing_relay_token_fails_before_any_request(self):
        with patch.dict(os.environ, {"RELAY_TOKEN": ""}):
            with self.assertRaises(addresses.JusoRelayConfigurationError):
                addresses.road_to_jibun("서울 테스트로 1")
        self.http.assert_not_called()

    def test_invalid_json_preserves_decode_error_after_host_failover(self):
        bad = provider([])
        bad._content = b"not json"
        self.http.return_value = bad
        with self.assertRaises(requests.exceptions.JSONDecodeError):
            addresses.road_to_jibun("서울 테스트로 1")
        self.assertEqual(self.http.call_count, 2)

    def test_off_on_board_status_and_guidance_are_safe(self):
        for enabled, route in (("0", "직접"), ("1", "중계")):
            with self.subTest(enabled=enabled), patch.dict(os.environ, {"RELAY_USE_JUSO": enabled}):
                status = data_sync_transport_status()
                self.assertEqual(status["sections"]["dsSecZip"]["routes"][0]["mode"], "relay")
                self.assertEqual(status["services"]["juso"]["enabled"], enabled == "1")
                row = next(r for r in build_board({})["rows"] if r["key"] == "dsSecZip")
                self.assertEqual(row["route"], route)
        with patch.dict(os.environ, {"RELAY_USE_JUSO": "0"}):
            now = datetime.now(timezone.utc)
            meta = {"zip_code_backfill_status": {
                "value": {"state": "failed", "last_error": "ConnectionError: timed out",
                          "finished_at": now.isoformat()},
                "updated_at": now.isoformat(),
            }}
            advice = next(r["transport_advice"] for r in build_board(meta, now=now)["rows"]
                          if r["key"] == "dsSecZip")
            self.assertEqual(advice["switch_name"], "RELAY_USE_JUSO")
            self.assertIn("RELAY_USE_JUSO", " ".join(advice["steps"]))
        for value in (SAMPLE, ENV["RELAY_BASE_URL"], ENV["RELAY_TOKEN"]):
            self.assertNotIn(value, str(status) + str(row) + str(advice))
        self.http.assert_not_called()

    def test_zip_batch_wait_preserves_checkpoint_and_reservation_count(self):
        connection = Mock()
        progress = {"last_id": 10, "in_flight_id": 11, "calls_today": 1, "completed": 0}
        provider_fn = Mock(side_effect=addresses.JusoRelayConnectionError("중계서버 일시 오류"))
        outcome, _, changed = zip_backfill._attempt_address(
            connection, Mock(), progress, {"id": 11, "road_address": "서울 테스트로 1"}, provider_fn,
        )
        provider_fn.assert_called_once_with("서울 테스트로 1", purpose="batch")
        self.assertEqual(outcome, "retry")
        self.assertFalse(changed)
        self.assertEqual((progress["last_id"], progress["in_flight_id"], progress["calls_today"]),
                         (10, 11, 1))
        connection.rollback.assert_called_once()
        capped = {"calls_today": 5000}
        self.assertFalse(zip_backfill._reserve_attempt(connection, capped, 11, 5000))
        self.assertEqual(capped["calls_today"], 5000)

    def test_user_submission_uses_realtime_and_fixed_auth_message(self):
        import app as web
        cursor = Mock()
        connection = Mock()
        connection.cursor.return_value = cursor
        codes = Mock()
        codes.find_sgg_cd.return_value = "11110"
        codes.find_bjdong_cd.return_value = "10100"
        codes.sgg_text.return_value = "서울특별시 종로구"
        client = web.app.test_client()
        with patch.object(web, "get_conn", return_value=connection), \
                patch.object(web.limiter, "enabled", False), \
                patch.object(addresses, "BjdongMap", return_value=codes):
            cursor.fetchone.side_effect = [{"id": 1}, {
                "id": 2, "building_name": "테스트 건물", "lodging_type": "생활숙박시설",
                "lodging_type_detail": "", "lodging_subtype": "", "road_address": "서울 테스트로 1",
                "name_pending": False,
            }]
            result = client.post("/api/submit-building", json={"road_address": "서울 테스트로 1"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.get_json()["status"], "verified")
            self.assertEqual(self.http.call_args.kwargs["headers"]["X-Relay-Purpose"], "realtime")
            self.assertEqual(self.http.call_args.kwargs["headers"]["X-Relay-Token"], ENV["RELAY_TOKEN"])
            for code in ("RELAY_AUTH", "RELAY_FORBIDDEN"):
                with self.subTest(code=code):
                    cursor.fetchone.side_effect = [{"id": 1}]
                    self.http.return_value = response(relay.ERROR_STATUS[code], code)
                    result = client.post("/api/submit-building", json={"road_address": "서울 테스트로 1"})
                    self.assertEqual(result.get_json()["status"], "rejected")
                    self.assertEqual(result.get_json()["message"],
                                     "주소 변환 중 오류: 일시적으로 주소 조회를 할 수 없습니다")
                    for value in (SAMPLE, ENV["RELAY_BASE_URL"], ENV["RELAY_TOKEN"], "confmKey"):
                        self.assertNotIn(value, result.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
