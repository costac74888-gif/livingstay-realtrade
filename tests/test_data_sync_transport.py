"""Offline contracts for administrator synchronization route badges."""

import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import data_sync_transport as transport
import public_api_client as relay


class DataSyncTransportTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.object(relay, "_STATUS_DIR", Path(directory.name)))
        self.enterContext(patch.dict(os.environ, {
            "RELAY_ENABLED": "1", "RELAY_USE_BLDG_HUB": "1", "RELAY_USE_RTMS": "0",
            "RELAY_USE_ONBID": "0", "RELAY_USE_JUSO": "0",
            "RELAY_TOKEN": "test-private-token",
            "RELAY_TOKEN_BATCH": "test-private-batch",
            "RELAY_BASE_URL": "https://test-private.example",
        }))
        self.http = self.enterContext(patch(
            "requests.get", side_effect=AssertionError("Status must never probe a provider"),
        ))

    def test_all_actual_sections_are_mapped_once(self):
        source = Path("static/admin.html").read_text()
        start = source.index("function showDataSync()")
        end = source.index("function stopBrokerSyncPolling()", start)
        ids = re.findall(r'id="(dsSec\w+)"', source[start:end])
        self.assertEqual(len(ids), 23)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(transport.SECTION_ROUTES))
        self.assertTrue(all(len(routes) > 0 for routes in transport.SECTION_ROUTES.values()))

    def test_runtime_switches_and_mixed_routes(self):
        data = transport.data_sync_transport_status()
        hub, rtms = data["sections"]["dsSecTitle"], data["sections"]["dsSecTx"]
        self.assertTrue(hub["routes"][0]["enabled"])
        self.assertFalse(rtms["routes"][0]["enabled"])
        self.assertTrue(rtms["routes"][1]["enabled"])
        with patch.dict(os.environ, {"RELAY_ENABLED": "0"}):
            off = transport.data_sync_transport_status()
        for section in off["sections"].values():
            for row in section["routes"]:
                if row["mode"] == "relay":
                    self.assertFalse(row["enabled"])
        self.http.assert_not_called()

    def test_direct_is_not_relay_off_or_verified_success(self):
        data = transport.data_sync_transport_status()
        onbid = data["sections"]["dsSecOnbid"]["routes"][0]
        self.assertEqual(onbid["mode"], "relay")
        self.assertFalse(onbid["enabled"])
        juso = data["sections"]["dsSecZip"]["routes"][0]
        self.assertEqual(juso["mode"], "relay")
        self.assertFalse(juso["enabled"])
        for section_id in ("dsSecRealty", "dsSecStores"):
            row = data["sections"][section_id]["routes"][0]
            self.assertEqual(row["mode"], "direct")
            self.assertEqual(set(row), {"service", "label", "mode"})
        self.assertEqual(data["sections"]["dsSecLodgingStaging"]["routes"][0]["mode"], "file")
        self.assertEqual(data["sections"]["dsSecLodging"]["routes"][0]["mode"], "disabled")

    def test_no_credentials_urls_or_shared_batch_health(self):
        relay._record_status("bldg_hub")
        relay._record_status("rtms", "RELAY_FORBIDDEN")
        data = transport.data_sync_transport_status()
        self.assertEqual(data["observation_scope"], "current_runtime")
        self.assertEqual(
            data["sections"]["dsSecTitle"]["routes"][0]["last_success_at"],
            data["services"]["bldg_hub"]["last_success_at"],
        )
        self.assertEqual(data["sections"]["dsSecTx"]["routes"][0]["last_error_code"], "RELAY_FORBIDDEN")
        text = json.dumps(data)
        for value in ("test-private-token", "test-private-batch", "https://", "serviceKey"):
            self.assertNotIn(value, text)
        self.http.assert_not_called()

    def test_relay_snapshot_read_once(self):
        with patch.object(transport, "relay_status", wraps=relay.relay_status) as snapshot:
            transport.data_sync_transport_status()
        snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
