import unittest
import io
from unittest.mock import Mock, patch
from PIL import Image

from app import (
    _cache_streetview_image,
    _bearing_degrees,
    _fetch_best_streetview_image,
    _google_streetview_metadata,
    _google_streetview_metadata_status,
    _select_streetview_metadata,
    _streetview_cached_image,
    _streetview_capture_points,
    _streetview_image_score,
    _streetview_quality_rejection,
    _streetview_view_params,
)


class BuildingPhotoProviderTest(unittest.TestCase):
    def tearDown(self):
        import app
        app._STREETVIEW_SELECTION_CACHE.clear()

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
            "date": "2026-01",
            "copyright": "© Google",
        }
        get.return_value = response

        self.assertEqual(
            _google_streetview_metadata(37.5, 127.0, "test-key"),
            {
                "status": "OK",
                "pano_id": "test-pano",
                "lat": 37.4999,
                "lng": 127.0001,
                "date": "2026-01",
                "copyright": "© Google",
            },
        )

    def test_heading_faces_building_from_panorama(self):
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 38.0, 127.0), 0.0)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 37.0, 128.0), 89.7, places=1)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 36.0, 127.0), 180.0)
        self.assertAlmostEqual(_bearing_degrees(37.0, 127.0, 37.0, 126.0), 270.3, places=1)

    def test_high_rise_view_looks_up_and_widens(self):
        pitch, fov = _streetview_view_params(30.7, floor_count=42)
        self.assertEqual(pitch, 35.0)
        self.assertEqual(fov, 102)

    def test_low_rise_view_stays_near_street_level(self):
        pitch, fov = _streetview_view_params(30, floor_count=4)
        self.assertAlmostEqual(pitch, 8.0, places=1)
        self.assertEqual(fov, 87)

    def test_unknown_height_uses_balanced_exterior_view(self):
        self.assertEqual(_streetview_view_params(30), (12.0, 90))

    @patch("app._google_streetview_metadata")
    def test_high_rise_prefers_farther_nearby_official_panorama(self, metadata):
        nearest = {
            "status": "OK", "pano_id": "near", "copyright": "© Google",
            "date": "2024-01", "lat": 37.49973, "lng": 127.0,
        }
        opposite = {
            "status": "OK", "pano_id": "opposite", "copyright": "© Google",
            "date": "2024-01", "lat": 37.49955, "lng": 127.0,
        }
        metadata.side_effect = [nearest, opposite, nearest, nearest, nearest]
        selected = _select_streetview_metadata(
            37.5, 127.0, "key", floor_count=40
        )
        self.assertEqual(selected["pano_id"], "opposite")
        self.assertEqual(metadata.call_count, 5)

    @patch("app._google_streetview_metadata")
    def test_low_rise_does_not_make_extra_panorama_queries(self, metadata):
        nearest = {"status": "OK", "pano_id": "near"}
        metadata.return_value = nearest
        self.assertIs(
            _select_streetview_metadata(37.5, 127.0, "key", floor_count=5),
            nearest,
        )
        metadata.assert_called_once_with(37.5, 127.0, "key")

    @patch("app._google_streetview_metadata")
    def test_three_capture_points_are_selected_without_review_queue(self, metadata):
        candidates = [
            {
                "status": "OK", "pano_id": f"pano-{index}",
                "copyright": "© Google", "date": "2025-01",
                "lat": 37.5 + delta, "lng": 127.0,
            }
            for index, delta in enumerate((-0.00028, -0.00020, 0.00035, 0.00045, 0.00010))
        ]
        metadata.side_effect = candidates
        selected = _streetview_capture_points(
            37.5, 127.0, "key", floor_count=20
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual(metadata.call_count, 5)
        self.assertEqual(len({item["pano_id"] for item in selected}), 3)

    @patch("app._streetview_ocr_text", return_value="테스트호텔 서울 강남")
    def test_image_score_combines_exposure_location_and_ocr(self, _ocr):
        image = Image.new("RGB", (640, 480), "white")
        for x in range(160, 480):
            for y in range(80, 430):
                if (x + y) % 12 < 6:
                    image.putpixel((x, y), (30, 30, 30))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        matched = _streetview_image_score(
            buffer.getvalue(), 32, 0, "테스트호텔", "서울 강남"
        )
        unmatched = _streetview_image_score(
            buffer.getvalue(), 32, 18, "다른건물", "부산 해운대"
        )
        self.assertGreater(matched, unmatched)

    @patch("sync_building_photos._claim_daily_slot", return_value=1)
    @patch("app._streetview_image_score")
    @patch("app.requests.get")
    def test_highest_of_nine_candidates_is_always_returned(
        self, get, score, _claim
    ):
        response = Mock()
        response.status_code = 200
        response.headers = {"Content-Type": "image/jpeg"}
        response.content = b"candidate"
        get.return_value = response
        score.side_effect = [0.1, 0.2, 0.3, 0.4, 0.95, 0.5, 0.6, 0.7, 0.8]
        points = [
            {
                "pano_id": f"pano-{index}", "lat": 37.5 + index * 0.0001,
                "lng": 127.0, "status": "OK",
            }
            for index in range(3)
        ]
        building = {
            "lat": 37.5, "lng": 127.0, "grnd_flr_cnt": 10, "heit": 30,
            "building_name": "테스트호텔", "road_address": "서울 강남",
        }
        best = _fetch_best_streetview_image(building, "key", points)
        self.assertEqual(best[0], 0.95)
        self.assertEqual(get.call_count, 9)

    @patch("app.time.monotonic", side_effect=[100.0, 100.0, 86601.0])
    def test_selected_image_cache_expires_after_one_day(self, _clock):
        _cache_streetview_image(77, b"best", "image/jpeg")
        self.assertEqual(
            _streetview_cached_image(77),
            (b"best", "image/jpeg"),
        )
        self.assertIsNone(_streetview_cached_image(77))

    @patch("sync_building_photos._claim_daily_slot", return_value=1)
    @patch("app._streetview_image_score")
    @patch("app.requests.get")
    def test_one_scoring_failure_does_not_block_best_remaining_candidate(
        self, get, score, _claim
    ):
        response = Mock()
        response.status_code = 200
        response.headers = {"Content-Type": "image/jpeg"}
        response.content = b"candidate"
        get.return_value = response
        score.side_effect = [RuntimeError("broken OCR")] + [0.75] * 8
        points = [
            {
                "pano_id": f"pano-{index}", "lat": 37.5 + index * 0.0001,
                "lng": 127.0, "status": "OK",
            }
            for index in range(3)
        ]
        building = {
            "lat": 37.5, "lng": 127.0, "grnd_flr_cnt": 10, "heit": 30,
            "building_name": "테스트호텔", "road_address": "서울 강남",
        }
        best = _fetch_best_streetview_image(building, "key", points)
        self.assertEqual(best[0], 0.75)

    def test_user_contributed_panorama_is_rejected(self):
        metadata = {
            "copyright": "© tim asdf",
            "date": "2021-07",
            "lat": 33.4934169803494,
            "lng": 126.4911207239808,
        }
        self.assertEqual(
            _streetview_quality_rejection(
                metadata,
                33.4934493811534,
                126.490997010344,
                now=__import__("datetime").datetime(2026, 9, 1),
            ),
            "unofficial panorama",
        )

    def test_eight_year_old_official_panorama_is_allowed(self):
        metadata = {
            "copyright": "© Google",
            "date": "2018-10",
            "lat": 33.49954034515397,
            "lng": 126.4974937801802,
        }
        self.assertIsNone(
            _streetview_quality_rejection(
                metadata,
                33.4994393059707,
                126.497430428476,
                now=__import__("datetime").datetime(2026, 9, 1),
            )
        )

    def test_official_panorama_without_date_is_allowed(self):
        metadata = {
            "copyright": "© Google",
            "date": None,
            "lat": 37.5001,
            "lng": 127.0001,
        }
        self.assertIsNone(
            _streetview_quality_rejection(metadata, 37.5, 127.0)
        )

    def test_very_old_official_panorama_is_rejected(self):
        metadata = {
            "copyright": "© Google",
            "date": "2013-08",
            "lat": 37.5001,
            "lng": 127.0001,
        }
        self.assertEqual(
            _streetview_quality_rejection(
                metadata,
                37.5,
                127.0,
                now=__import__("datetime").datetime(2026, 9, 1),
            ),
            "stale panorama",
        )

    def test_recent_nearby_google_panorama_is_allowed(self):
        metadata = {
            "copyright": "© Google",
            "date": "2024-05",
            "lat": 37.5001,
            "lng": 127.0001,
        }
        self.assertIsNone(
            _streetview_quality_rejection(
                metadata,
                37.5,
                127.0,
                now=__import__("datetime").datetime(2026, 9, 1),
            )
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