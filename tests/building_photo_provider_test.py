import unittest
from unittest.mock import Mock, patch

from app import _google_streetview_metadata_status


class BuildingPhotoProviderTest(unittest.TestCase):
    @patch("app.requests.get")
    def test_streetview_metadata_ok(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "OK"}
        get.return_value = response

        self.assertEqual(
            _google_streetview_metadata_status(37.5, 127.0, "test-key"),
            "OK",
        )

    @patch("app.requests.get")
    def test_streetview_metadata_zero_results(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "ZERO_RESULTS"}
        get.return_value = response

        self.assertEqual(
            _google_streetview_metadata_status(37.5, 127.0, "test-key"),
            "ZERO_RESULTS",
        )

    @patch("app.requests.get")
    def test_streetview_metadata_failure_is_closed(self, get):
        get.side_effect = ValueError("invalid response")

        self.assertIsNone(
            _google_streetview_metadata_status(37.5, 127.0, "test-key")
        )


if __name__ == "__main__":
    unittest.main()