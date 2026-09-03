import unittest
from unittest.mock import Mock, patch

import requests

from addr_norm import normalize_road_prefix
from prewarm_tourapi_metadata import (
    _catalog_matches,
    _tour_catalog_page,
    _upsert_catalog_metadata,
)


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))


class TourApiMetadataTest(unittest.TestCase):
    def test_catalog_match_prefers_exact_road_address(self):
        item = {
            "addr1": "서울특별시 용산구 청파로20길 95",
            "addr2": "(한강로3가)",
        }
        key = normalize_road_prefix("서울특별시 용산구 청파로20길 95")
        self.assertEqual(_catalog_matches(item, {key: [3156]}, {}), [3156])

    def test_upsert_stores_only_content_id_and_photo_flag(self):
        item = {
            "contentid": "12345",
            "addr1": "전라남도 여수시 오동도로 111",
            "firstimage": "https://tong.visitkorea.or.kr/example.jpg",
        }
        key = normalize_road_prefix(item["addr1"])
        cursor = RecordingCursor()

        result = _upsert_catalog_metadata(cursor, [item], {key: [3804]}, {})

        self.assertEqual(result["matched_buildings"], 1)
        self.assertEqual(result["with_image_buildings"], 1)
        self.assertEqual(cursor.calls[0][1], [3804, "catalog_matched", "12345", True])
        self.assertNotIn("example.jpg", str(cursor.calls[0][1]))

    def test_no_representative_image_becomes_streetview_candidate(self):
        item = {
            "contentid": "67890",
            "addr1": "부산광역시 해운대구 구남로 9",
            "firstimage": "",
            "firstimage2": "",
        }
        key = normalize_road_prefix(item["addr1"])
        cursor = RecordingCursor()

        result = _upsert_catalog_metadata(cursor, [item], {key: [4114]}, {})

        self.assertEqual(result["without_image_buildings"], 1)
        self.assertEqual(
            cursor.calls[0][1],
            [4114, "catalog_no_photo", "67890", False],
        )

    @patch("prewarm_tourapi_metadata.time.sleep")
    def test_catalog_connection_timeout_retries_with_backoff(self, sleep):
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"response": {"body": {"items": {"item": []}}}}
        session = Mock()
        session.get.side_effect = [
            requests.ConnectTimeout("temporary outage"),
            requests.ConnectTimeout("temporary outage"),
            success,
        ]

        result = _tour_catalog_page(session, "test-key", 1)

        self.assertEqual(result, success.json.return_value)
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [10, 20])


if __name__ == "__main__":
    unittest.main()