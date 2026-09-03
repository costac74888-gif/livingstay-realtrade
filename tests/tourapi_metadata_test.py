import unittest

from addr_norm import normalize_road_prefix
from prewarm_tourapi_metadata import (
    _catalog_matches,
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


if __name__ == "__main__":
    unittest.main()