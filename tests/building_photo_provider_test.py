import unittest
from unittest.mock import Mock, patch

from app import (
    _bearing_degrees,
    _google_streetview_metadata,
    _google_streetview_metadata_status,
)


class BuildingPhotoProviderTest(unittest.TestCase):
    @patch("app.requests.get")
    def test_streetview_metadata_ok(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "OK",
            "pano_id": "test-pano",
            "location": {"lat": 37.4999, "lng": 127.0},
        }
        get.return_value = response

        self.assertEqual(
            _google_streetview_metadata_status(37.5, 127.0, "test-key"),
            "OK",
        )
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["source"], "outdoor")
        self.assertEqual(params["radius"], 50)

    @patch("app.requests.get")
    def test_streetview_metadata_returns_camera_location(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "OK",
            "pano_id": "test-pano",
            "location": {"lat": 37.4999, "lng": 127.0001},
        }
        get.return_value = response

        self.assertEqual(
            _google_streetview_metadata(37.5, 127.0, "test-key"),
            {
                "status": "OK",
                "pano_id": "test-pano",
                "lat": 37.4999,
                "lng": 127.0001,
            },
        )

    def test_heading_faces_building_from_panorama(self):
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 38.0, 127.0), 0.0)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 37.0, 128.0), 89.7, places=1)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 36.0, 127.0), 180.0)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 37.0, 126.0), 270.3, places=1)

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