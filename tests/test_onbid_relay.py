"""Onbid transport contracts. Every HTTP request, DB write and sleep is mocked."""
import json
import os
import tempfile
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import quote

import requests
import public_api_client as relay
import sync_onbid as onbid
from auction_domain import ENDPOINTS
from tests.test_public_api_client import ENV, SAMPLE, response

TARGET = "https://apis.data.go.kr/B010003/" + ENDPOINTS["list"]


def provider(status=200, code="00"):
    result = response(status)
    result.headers.pop("X-Relay-Error", None)
    result._content = json.dumps({
        "header": {"resultCode": code},
        "body": {"items": [], "totalCount": 0},
    }).encode()
    return result


class OnbidRelayTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            **ENV, "RELAY_USE_ONBID": "1", "DATA_GO_KR_BROKER_API_KEY": SAMPLE,
        }))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(relay, "_STATUS_DIR", Path(directory)))
        self.enterContext(patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("External calls forbidden"),
        ))
        self.http = self.enterContext(patch("requests.get", return_value=provider()))
        self.runner = onbid.Runner.__new__(onbid.Runner)
        self.runner.key = SAMPLE
        self.runner.args = SimpleNamespace(sleep=0, status_key="test:offline", limit=0)
        self.runner.state = {"last_error": None, "errors": 0, "detail_pending": 0}
        self.runner.failures = 0
        self.runner.stopped = Mock()
        self.runner.stopped.is_set.return_value = False
        self.runner.reserve = Mock()
        self.runner.save_state = Mock()
        self.runner.session = Mock()

    def test_off_exact_direct_request_arguments_and_no_session_reuse(self):
        for flag in (None, "", "0", "true", "yes"):
            with self.subTest(flag=flag), patch.dict(os.environ):
                if flag is None:
                    os.environ.pop("RELAY_USE_ONBID", None)
                else:
                    os.environ["RELAY_USE_ONBID"] = flag
                self.http.reset_mock()
                self.assertEqual(self.runner.call("list", pageNo=7), ([], 0))
                self.http.assert_called_once_with(TARGET, params={
                    "serviceKey": SAMPLE, "pageNo": 7, "numOfRows": 1000,
                    "resultType": "json",
                }, timeout=(15, 30))
        self.runner.session.get.assert_not_called()

    def test_switches_are_independent_and_unknown_service_is_disabled(self):
        with patch.dict(os.environ, {"RELAY_USE_ONBID": "0"}):
            self.assertFalse(relay._enabled("onbid"))
            self.assertTrue(relay._enabled("rtms"))
            self.assertTrue(relay._enabled("bldg_hub"))
        with patch.dict(os.environ, {"RELAY_ENABLED": "0"}):
            self.runner.call("list")
            self.http.assert_called_once_with(TARGET, params={
                "serviceKey": SAMPLE, "pageNo": 1, "numOfRows": 1000,
                "resultType": "json",
            }, timeout=(15, 30))
        self.assertFalse(relay._enabled("unknown"))

    def test_on_batch_all_four_endpoints_and_redacted_response_url(self):
        for service, endpoint in ENDPOINTS.items():
            with self.subTest(service=service):
                self.http.reset_mock()
                self.runner.reserve.reset_mock()
                self.assertEqual(self.runner.call(service), ([], 0))
                self.runner.reserve.assert_called_once_with(service)
                args, kwargs = self.http.call_args
                self.assertEqual(args, (ENV["RELAY_BASE_URL"] + "/v1/fetch",))
                self.assertIn("/B010003/" + endpoint, kwargs["params"]["url"])
                self.assertEqual(kwargs["headers"]["X-Relay-Purpose"], "batch")
                self.assertEqual(kwargs["headers"]["X-Relay-Token"], ENV["RELAY_TOKEN_BATCH"])
                self.assertEqual(kwargs["timeout"], (20, 30))
                self.assertFalse(kwargs["allow_redirects"])
                self.assertNotIn(SAMPLE, self.http.return_value.url)
                self.assertNotIn("serviceKey", self.http.return_value.url)
        status = relay.relay_status()
        self.assertEqual(set(status), {"bldg_hub", "rtms", "onbid", "juso"})
        self.assertTrue(status["onbid"]["enabled"])
        self.assertTrue(status["onbid"]["last_success_at"])
        for value in (SAMPLE, ENV["RELAY_TOKEN_BATCH"], ENV["RELAY_BASE_URL"]):
            self.assertNotIn(value, str(status))

    def test_only_allowed_host_and_path_can_be_sent_to_relay(self):
        for target in (
            TARGET.replace("https:", "http:"),
            TARGET.replace("apis.data.go.kr", "evil.example.test"),
            TARGET.replace("/B010003/", "/B010003/../"),
            TARGET + "#fragment",
        ):
            with self.subTest(target=target):
                self.http.reset_mock()
                with self.assertRaises(relay.RelayError) as caught:
                    relay.public_api_get(target, {"serviceKey": SAMPLE}, (15, 30), "batch")
                self.assertEqual(caught.exception.code, "RELAY_FORBIDDEN")
                self.http.assert_not_called()
        self.http.reset_mock()
        unrelated = "https://apis.data.go.kr/not-supported/list"
        relay.public_api_get(unrelated, {}, (15, 30), "batch")
        self.http.assert_called_once_with(unrelated, params={}, timeout=(15, 30))

    def test_nonretryable_errors_map_to_fixed_fatal_messages_without_fallback(self):
        for code, kind, message in (
            ("RELAY_QUOTA", onbid.BudgetExceeded, "중계서버 호출 한도 도달"),
            ("RELAY_AUTH", PermissionError, "중계서버 인증·허용 설정 확인 필요"),
            ("RELAY_FORBIDDEN", PermissionError, "중계서버 인증·허용 설정 확인 필요"),
            ("CIRCUIT_OPEN", onbid.OnbidRelayUnavailable, "중계서버 일시 오류"),
            ("RELAY_INTERNAL", onbid.OnbidRelayUnavailable, "중계서버 일시 오류"),
        ):
            with self.subTest(code=code):
                self.http.reset_mock()
                self.runner.reserve.reset_mock()
                self.runner.stopped.wait.reset_mock()
                self.http.return_value = response(relay.ERROR_STATUS[code], code)
                with self.assertRaises(kind) as caught:
                    self.runner.call("detail")
                self.assertEqual(str(caught.exception), message)
                rendered = "".join(traceback.format_exception(caught.exception))
                for value in (SAMPLE, ENV["RELAY_TOKEN_BATCH"], ENV["RELAY_BASE_URL"], "serviceKey"):
                    self.assertNotIn(value, rendered)
                self.http.assert_called_once()
                self.runner.reserve.assert_called_once_with("detail")
                self.runner.stopped.wait.assert_not_called()
                self.runner.save_state.assert_not_called()
                self.assertEqual(self.runner.failures, 0)

    def test_retryable_errors_use_existing_four_attempts_reserve_and_backoff(self):
        for code in relay.RETRYABLE_CODES:
            with self.subTest(code=code):
                self.http.reset_mock()
                self.runner.reserve.reset_mock()
                self.runner.stopped.wait.reset_mock()
                self.runner.save_state.reset_mock()
                self.runner.failures = 0
                self.http.return_value = response(relay.ERROR_STATUS[code], code)
                with self.assertRaises(RuntimeError):
                    self.runner.call("list")
                self.assertEqual(self.http.call_count, 4)
                self.assertEqual(self.runner.reserve.call_count, 4)
                self.assertEqual(self.runner.save_state.call_count, 4)
                self.assertEqual([c.args for c in self.runner.stopped.wait.call_args_list],
                                 [(15,), (30,), (60,)])
                self.assertEqual(self.runner.failures, 4)
                self.assertNotIn(SAMPLE, self.runner.state["last_error"])
                self.assertNotIn(ENV["RELAY_BASE_URL"], self.runner.state["last_error"])
                self.assertTrue(all(c.args[0].endswith("/v1/fetch")
                                    for c in self.http.call_args_list))

    def test_provider_status_and_result_codes_keep_original_judgment(self):
        for status, code, kind in (
            (401, "00", PermissionError), (403, "00", PermissionError),
            (429, "00", onbid.BudgetExceeded), (200, "22", onbid.BudgetExceeded),
            *((200, code, PermissionError) for code in ("20", "21", "30", "31", "32")),
        ):
            with self.subTest(status=status, code=code):
                self.http.reset_mock()
                self.http.return_value = provider(status, code)
                with self.assertRaises(kind):
                    self.runner.call("list")
                self.http.assert_called_once()

    def test_network_timeout_is_redacted_and_retry_recovery_keeps_budget(self):
        raw = ENV["RELAY_BASE_URL"] + "/v1/fetch?url=" + quote(TARGET + "?serviceKey=" + SAMPLE, safe="")
        self.http.side_effect = [requests.exceptions.Timeout(raw), provider()]
        self.assertEqual(self.runner.call("list"), ([], 0))
        self.assertEqual(self.runner.reserve.call_count, 2)
        self.runner.stopped.wait.assert_called_once_with(15)
        self.assertEqual(self.runner.failures, 0)
        for value in (SAMPLE, ENV["RELAY_BASE_URL"], "serviceKey"):
            self.assertNotIn(value, self.runner.state["last_error"])

    def test_fatal_relay_error_final_state_has_only_fixed_message(self):
        self.runner.claim = Mock(return_value=True)
        self.runner.heartbeat = Mock()
        self.runner.collect_lists = Mock(side_effect=onbid.OnbidRelayUnavailable())
        self.runner.load_master_index = Mock()
        self.runner.lock_conn = None
        self.runner.run_id = "offline-only"
        self.runner.own = Mock(return_value=True)
        with patch("sync_onbid.threading.Thread"), patch("sync_onbid.get_conn") as conn, \
                patch("sync_onbid.record_sync_outcome") as outcome, patch("builtins.print"):
            conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = {
                "owner": "offline-only",
            }
            self.runner.run()
        self.assertEqual(self.runner.state["state"], "failed")
        self.assertEqual(self.runner.state["last_error"], "중계서버 일시 오류")
        self.runner.load_master_index.assert_not_called()
        outcome.assert_called_once()

    def test_fatal_relay_error_escapes_both_detail_loops_and_stops_execution(self):
        for ended in (False, True):
            with self.subTest(ended=ended):
                target = {"source_item_id": "offline-item", "pbct_cdtn_no": "1"}
                source = {"cltrMngNo": "offline-item", "pbctCdtnNo": "1",
                          "cltrBidBgngDt": "20260101", "cltrUsgSclsCtgrNm": "숙박시설"}
                self.runner.claim = Mock(return_value=True)
                self.runner.heartbeat = Mock()
                self.runner.collect_lists = Mock(return_value={
                    ("offline-item", "1"): source,
                })
                self.runner.load_master_index = Mock()
                self.runner.stage_rows = Mock(return_value=([], [] if ended else [target, target]))
                self.runner.detail_target = Mock(side_effect=onbid.OnbidRelayUnavailable())
                self.runner.lock_conn = None
                self.runner.run_id = "offline-only"
                self.runner.own = Mock(return_value=True)
                self.runner.state = {"last_error": None, "errors": 0, "processed": 0,
                                     "detail_pending": 0}
                with patch("sync_onbid.threading.Thread"), patch("sync_onbid.get_conn") as conn, \
                        patch("sync_onbid.record_sync_outcome"), patch("builtins.print"):
                    cursor = conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                    cursor.fetchone.return_value = {"owner": "offline-only"}
                    cursor.fetchall.return_value = [
                        {**target, "source_row": source}, {**target, "source_row": source},
                    ] if ended else []
                    self.runner.run()
                self.runner.detail_target.assert_called_once()
                self.assertEqual(self.runner.state["state"], "failed")
                self.assertEqual(self.runner.state["last_error"], "중계서버 일시 오류")
                self.assertEqual(self.runner.state["errors"], 0)


if __name__ == "__main__":
    unittest.main()
