import json
import unittest

import import_tourism_stats as importer


def lodging_row(**overrides):
    row = {
        "광역시/도": "강원특별자치도",
        "시/군/구": "강릉시",
        "관광숙박ID": "stay-102",
        "관광숙박명": "  오션-호텔  ",
        "소분류": "관광호텔",
        "중분류": "관광숙박",
        "검색건수": "1,234",
        "검색순위": "2",
    }
    row.update(overrides)
    return row


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0
        self._updates = iter((3, 2))

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "SELECT COUNT(*)" in sql:
            self.rowcount = 1
        else:
            self.rowcount = next(self._updates)

    def fetchone(self):
        return (9,)


class TourismStatsImporterTests(unittest.TestCase):
    def test_lodging_rank_filename_is_separate_from_generic_ranking(self):
        self.assertEqual(
            importer.detect_type("지역별 관광지 검색순위_202601-202602.csv"),
            "search_ranking",
        )
        self.assertEqual(
            importer.detect_type("관광숙박 검색순위_202601-202602.csv"),
            "lodging_search_rank",
        )
        self.assertEqual(
            importer.detect_type("관광숙박_검색순위_202601-202602.csv"),
            "lodging_search_rank",
        )

    def test_lodging_rank_shape_is_canonical_and_hash_ignores_row_order(self):
        first = importer.build_lodging_rank_row(
            lodging_row(), "source.zip::관광숙박 검색순위.csv", "202601-202602"
        )
        reordered = importer.build_lodging_rank_row(
            lodging_row(검색순위="7", 검색건수="99"),
            "source.zip::관광숙박 검색순위.csv", "202601-202602"
        )

        self.assertEqual(len(first), 11)
        self.assertEqual(first[:7], (
            "lodging_search_rank", "강원특별자치도", "강릉시", None,
            "검색순위", 2.0, "위",
        ))
        self.assertEqual(
            json.loads(first[9]),
            {
                "datalab_id": "stay-102",
                "place_name": "오션-호텔",
                "sub_category": "관광호텔",
                "mid_category": "관광숙박",
                "search_count": "1,234",
            },
        )
        self.assertEqual(first[10], reordered[10])

    def test_lodging_rank_without_valid_rank_or_name_is_skipped(self):
        self.assertIsNone(importer.build_lodging_rank_row(
            lodging_row(검색순위="not a rank"), "x.csv::x.csv", None
        ))
        self.assertIsNone(importer.build_lodging_rank_row(
            lodging_row(관광숙박명=" "), "x.csv::x.csv", None
        ))

    def test_lodging_rank_without_id_uses_collision_safe_row_fallback(self):
        without_id = lodging_row(관광숙박ID="")
        first = importer.build_lodging_rank_row(
            without_id, "x.csv::x.csv", None, row_index=2
        )
        second = importer.build_lodging_rank_row(
            without_id, "x.csv::x.csv", None, row_index=3
        )
        repeated = importer.build_lodging_rank_row(
            without_id, "x.csv::x.csv", None, row_index=2
        )
        self.assertNotEqual(first[10], second[10])
        self.assertEqual(first[10], repeated[10])

    def test_lodging_rank_accepts_datalab_category_headers(self):
        row = lodging_row(
            소분류="",
            중분류="",
            **{"소분류 카테고리": "호텔", "중분류 카테고리": "숙박"},
        )
        built = importer.build_lodging_rank_row(row, "x.csv::x.csv", None)
        dimensions = json.loads(built[9])
        self.assertEqual(dimensions["sub_category"], "호텔")
        self.assertEqual(dimensions["mid_category"], "숙박")

    def test_region_core_sql_normalizes_province_aliases(self):
        expression = importer.region_core_sql("source_sido", "source_sgg")
        self.assertIn("특별자치도|특별자치시|특별시|광역시|도|시", expression)
        self.assertIn("'^전라', '전'", expression)
        self.assertIn("'^충청', '충'", expression)
        self.assertIn("'^경상', '경'", expression)
        self.assertIn("전남광주통합특별시", expression)

    def test_building_matching_is_limited_to_lodging_rows_and_imported_sources(self):
        cur = FakeCursor()
        sources = ["new.zip::관광숙박 검색순위.csv"]

        result = importer.match_lodging_rank_to_buildings(cur, sources)

        self.assertEqual(result, {
            "total": 9, "exact": 3, "containment": 2, "unmatched": 4,
        })
        self.assertEqual(len(cur.calls), 3)
        for sql, params in cur.calls:
            self.assertEqual(params, ("lodging_search_rank", sources))
            self.assertIn("source_file = ANY(%s)", sql)
            self.assertIn("stat_type = %s", sql)
            self.assertNotIn("LIMIT 1", sql.upper())
        self.assertIn("SET master_building_id = c.building_id", cur.calls[1][0])
        self.assertIn("t.master_building_id IS NULL", cur.calls[2][0])
        self.assertIn("'^경상', '경'", cur.calls[1][0])
        self.assertIn("LIKE '%%'", cur.calls[2][0])
        self.assertIn("HAVING COUNT(DISTINCT b.id) = 1", cur.calls[1][0])
        self.assertIn("length(", cur.calls[2][0])


if __name__ == "__main__":
    unittest.main()