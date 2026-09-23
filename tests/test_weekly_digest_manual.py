import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import app as server
import weekly_digest as digest


class WeeklyDigestManualTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = True

    @staticmethod
    def _status_connection(value):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = {"value": value}
        return conn

    def test_full_send_denied_without_successful_test(self):
        with (patch.object(server, "get_conn", return_value=self._status_connection(None)),
              patch.object(server, "_start_detached_sync") as launch):
            response = self.client.post("/api/admin/weekly-digest-send-all")
        self.assertEqual(response.status_code, 409)
        launch.assert_not_called()

    def test_test_button_starts_only_representative_runner(self):
        with patch.object(server, "_start_detached_sync", return_value=(True, 202, {"ok": True})) as launch:
            response = self.client.post("/api/admin/weekly-digest-send-test")
        self.assertEqual(response.status_code, 202)
        self.assertIn("--test", launch.call_args.args[2])
        self.assertEqual(launch.call_args.kwargs["done_cooldown_min"], 0)

    def test_unauthenticated_request_cannot_start_either_send(self):
        unauthenticated = server.app.test_client()
        with patch.object(server, "_start_detached_sync") as launch:
            for path in ("/api/admin/weekly-digest-send-test", "/api/admin/weekly-digest-send-all"):
                with self.subTest(path=path):
                    response = unauthenticated.post(path)
                    self.assertEqual(response.status_code, 401)
        launch.assert_not_called()

    def test_full_send_consumes_current_week_test_approval(self):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        week = (today - timedelta(days=today.weekday())).isoformat()
        approved = '{"state":"test_ready","week_start":"' + week + '"}'
        with (patch.object(server, "get_conn", return_value=self._status_connection(approved)),
              patch.object(server, "_start_detached_sync", return_value=(True, 202, {"ok": True})) as launch):
            response = self.client.post("/api/admin/weekly-digest-send-all")
        self.assertEqual(response.status_code, 202)
        self.assertIn("weekly_digest_runner.py", launch.call_args.args)
        self.assertEqual(launch.call_args.kwargs["done_cooldown_min"], 0)

    def test_old_week_test_is_rejected(self):
        with (patch.object(server, "get_conn", return_value=self._status_connection(
                  '{"state":"test_ready","week_start":"2020-01-06"}')),
              patch.object(server, "_start_detached_sync") as launch):
            response = self.client.post("/api/admin/weekly-digest-send-all")
        self.assertEqual(response.status_code, 409)
        launch.assert_not_called()

    def test_representative_test_uses_real_personalization_without_delivery_claim(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = [{
            "id": 7, "email": "joisys@nate.com", "name": "대표",
            "unsubscribe_token": "token",
        }]
        personalized = {
            "favs": [("건물", "주소", 11)], "deals_by_fav": {},
            "listing_reqs": [{"id": 4}], "buy_reqs": [{"id": 5}],
            "alert_off_count": 0, "signal_counts": {}, "new_deal_count": 0,
        }
        with (patch.object(digest, "get_conn", return_value=conn),
              patch.object(digest, "_get_30_day_rankings", return_value=([], [], "start", "end")),
              patch.object(digest, "_get_datalab_summary", return_value={}),
              patch.object(digest, "_get_active_feature_tip", return_value={"title": "기능"}),
              patch.object(digest, "_personalize_recipient", return_value=personalized) as personalize,
              patch.object(digest, "_get_recent_news", return_value=[{"title": "뉴스"}]),
              patch.object(digest, "_build_subject", return_value="주간메일"),
              patch.object(digest, "build_html", return_value="<html>개인화</html>") as render,
              patch.object(digest, "send_email", return_value=(True, "accepted")) as send,
              patch.object(digest, "_claim_delivery") as claim):
            self.assertEqual(digest._send_representative_test(), 0)
        personalize.assert_called_once()
        self.assertEqual(render.call_args.args[1], personalized["favs"])
        self.assertEqual(render.call_args.args[3], personalized["listing_reqs"])
        self.assertEqual(render.call_args.args[4], personalized["buy_reqs"])
        self.assertEqual(send.call_args.args[0], "joisys@nate.com")
        claim.assert_not_called()


if __name__ == "__main__":
    unittest.main()