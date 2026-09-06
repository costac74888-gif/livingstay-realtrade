import json
import tempfile
import unittest
from pathlib import Path

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

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self.rowcount = 0

    def fetchone(self):
        return {"total": 9}

    def fetchall(self):
        return []


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
        self.assertTrue(importer.is_lodging_top100_address_file(
            "숙박시설_검색순위_TOP100_상세주소_1788686669991.csv"
        ))
        self.assertEqual(
            importer.detect_type(
                "20260905141202_지역별_관광지_검색순위.csv"
            ),
            "search_ranking",
        )

    def test_generic_ranking_filename_is_promoted_only_when_all_rows_are_lodging(self):
        lodging_rows = [
            {
                "순위": "1",
                "광역시/도": "서울특별시",
                "시/군/구": "중구",
                "관광지ID": "hotel-1",
                "관광지명": "테스트호텔",
                "중분류 카테고리": "숙박",
                "소분류 카테고리": "호텔",
                "검색건수": "100",
            }
        ]
        self.assertEqual(
            importer.detect_type_from_rows(
                "지역별 관광지 검색순위.csv", lodging_rows
            ),
            "lodging_search_rank",
        )
        mixed_rows = lodging_rows + [
            {
                **lodging_rows[0],
                "관광지ID": "airport-1",
                "관광지명": "테스트공항",
                "중분류 카테고리": "교통",
            }
        ]
        self.assertEqual(
            importer.detect_type_from_rows(
                "지역별 관광지 검색순위.csv", mixed_rows
            ),
            "search_ranking",
        )

    def test_duplicate_datalab_ids_with_distinct_aliases_are_preserved(self):
        header = (
            "순위,광역시/도,시/군/구,관광지ID,관광지명,"
            "중분류 카테고리,소분류 카테고리,검색건수\n"
        )
        body = (
            "1,인천광역시,중구,same-id,파라다이스시티호텔,숙박,호텔,200\n"
            "2,인천광역시,영종구,same-id,파라다이스시티호텔,숙박,호텔,100\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "지역별 관광지 검색순위.csv"
            path.write_text(header + body, encoding="utf-8-sig")
            rows, skipped = importer.build_rows([path])
        self.assertEqual(skipped, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row[0] for row in rows}, {"lodging_search_rank"})
        self.assertNotEqual(rows[0][10], rows[1][10])

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

    def test_lodging_rank_preserves_collected_road_address(self):
        row = lodging_row(**{"도로명주소": "서울특별시 중구 세종대로 1"})
        built = importer.build_lodging_rank_row(row, "x.csv::x.csv", None)
        self.assertEqual(
            json.loads(built[9])["road_address"],
            "서울특별시 중구 세종대로 1",
        )

    def test_detailed_top100_contract_is_enforced_in_shared_importer(self):
        rows = [
            {
                "순위": str(rank),
                "광역시/도": "서울특별시",
                "시/군/구": "중구",
                "관광지명": f"호텔{rank}",
                "중분류 카테고리": "숙박",
                "검색건수": str(1000 - rank),
                "도로명주소": f"서울특별시 중구 테스트로 {rank}",
            }
            for rank in range(1, 101)
        ]
        name = "숙박시설_검색순위_TOP100_상세주소.csv"
        metric, kind, skipped = importer.build_member_metric_rows(
            name, name, rows, None
        )
        self.assertEqual((kind, len(metric), skipped), (
            "lodging_search_rank", 100, 0,
        ))
        invalid_sets = [
            rows[:-1],
            [{**row, "순위": "1"} if index == 50 else row
             for index, row in enumerate(rows)],
            [{**row, "도로명주소": ""} if index == 0 else row
             for index, row in enumerate(rows)],
            [{**row, "검색건수": ""} if index == 42 else row
             for index, row in enumerate(rows)],
        ]
        for invalid in invalid_sets:
            with self.subTest(rows=len(invalid)):
                with self.assertRaises(ValueError):
                    importer.build_member_metric_rows(
                        name, name, invalid, None
                    )

    def test_non_dedicated_lodging_csv_may_include_optional_address_column(self):
        rows = [{
            **lodging_row(),
            "도로명주소": "강원특별자치도 강릉시 테스트로 1",
        }]
        metric, kind, skipped = importer.build_member_metric_rows(
            "관광숙박 검색순위.csv",
            "관광숙박 검색순위.csv",
            rows,
            None,
        )
        self.assertEqual((kind, len(metric), skipped), (
            "lodging_search_rank", 1, 0,
        ))

    def test_region_core_sql_normalizes_province_aliases(self):
        expression = importer.region_core_sql("source_sido", "source_sgg")
        self.assertIn("특별자치도|특별자치시|특별시|광역시|도|시", expression)
        self.assertIn("'^전라', '전'", expression)
        self.assertIn("'^충청', '충'", expression)
        self.assertIn("'^경상', '경'", expression)
        self.assertIn("전남광주통합특별시", expression)

    def test_building_matching_requires_verified_address_not_business_name(self):
        cur = FakeCursor()
        sources = ["new.zip::관광숙박 검색순위.csv"]

        result = importer.match_lodging_rank_to_buildings(cur, sources)

        self.assertEqual(result, {
            "total": 9, "address": 0, "unmatched": 9,
        })
        self.assertEqual(len(cur.calls), 3)
        for sql, params in cur.calls[:2]:
            self.assertEqual(params, ("lodging_search_rank", sources))
            self.assertIn("source_file = ANY(%s)", sql)
            self.assertIn("stat_type = %s", sql)
        self.assertIn("kakao_confirmed_address", cur.calls[1][0])
        self.assertNotIn("building_name", cur.calls[1][0])
        self.assertNotIn("LIKE '%%'", cur.calls[1][0])

    def test_collected_road_address_uniquely_links_existing_building(self):
        class AddressCursor(FakeCursor):
            def execute(self, sql, params=None):
                super().execute(sql, params)
                if "SET master_building_id" in sql:
                    self.rowcount = 1

            def fetchall(self):
                if "FROM tourism_stats" in self.calls[-1][0]:
                    return [{
                        "id": 44,
                        "dimensions": {
                            "road_address": "서울특별시 중구 세종대로 1",
                        },
                    }]
                return [{
                    "id": 10,
                    "road_address": "서울특별시 중구 세종대로 1",
                    "jibun_address": None,
                }]

        cur = AddressCursor()
        result = importer.match_lodging_rank_to_buildings(cur, ["rank.csv"])

        self.assertEqual(result, {"total": 9, "address": 1, "unmatched": 8})
        update = next(
            call for call in cur.calls if "SET master_building_id" in call[0]
        )
        self.assertEqual(update[1], (10, 44))

    def test_same_address_multi_building_complex_is_not_arbitrarily_linked(self):
        class ComplexCursor(FakeCursor):
            def fetchall(self):
                if "FROM tourism_stats" in self.calls[-1][0]:
                    return [{
                        "id": 44,
                        "dimensions": {
                            "kakao_confirmed_address": "서울 중구 세종대로 1",
                            "kakao_confirmed_road_address": "서울 중구 세종대로 1",
                            "kakao_confirmed_jibun_address": "",
                        },
                    }]
                return [
                    {"id": 10, "road_address": "서울특별시 중구 세종대로 1", "jibun_address": None},
                    {"id": 11, "road_address": "서울특별시 중구 세종대로 1", "jibun_address": None},
                ]

        cur = ComplexCursor()
        result = importer.match_lodging_rank_to_buildings(cur, ["rank.csv"])

        self.assertEqual(result, {"total": 9, "address": 0, "unmatched": 9})
        self.assertFalse(any(
            "SET master_building_id" in sql for sql, _params in cur.calls
        ))

    def test_latest_top100_address_verification_is_bounded_and_persists_evidence(self):
        source = Path(importer.__file__).read_text(encoding="utf-8")
        start = source.index("def verify_latest_top100_lodging_addresses")
        end = source.index("\n\n_KAKAO_LOCAL_KEYWORD_URL", start)
        function = source[start:end]
        self.assertIn("t.metric_value <= 100", function)
        self.assertIn("LIMIT 100", function)
        self.assertIn("kakao_confirmed_address", function)
        self.assertIn("KakaoAK", function)

    def test_kakao_branch_candidates_require_source_region_and_one_result(self):
        documents = [
            {
                "place_name": "인스파이어 엔터테인먼트 리조트",
                "road_address_name": "인천광역시 중구 공항문화로 127",
            },
            {
                "place_name": "인스파이어 엔터테인먼트 리조트 서울점",
                "road_address_name": "서울특별시 중구 세종대로 1",
            },
        ]
        eligible = importer._verified_kakao_candidates(
            "인스파이어 엔터테인먼트 리조트", "인천광역시", "중구", documents
        )
        self.assertEqual(eligible, [documents[0]])
        # Two in-region branch candidates are intentionally not collapsed by
        # a business name or a shared chain brand.
        self.assertEqual(len(importer._verified_kakao_candidates(
            "인스파이어 엔터테인먼트 리조트", "인천광역시", "중구",
            [documents[0], {**documents[0], "road_address_name": "인천광역시 중구 영종해안남로 1"}],
        )), 2)

    def test_unique_verified_hub_lodging_is_created_then_address_linked(self):
        dimensions = {
            "kakao_confirmed_address": "인천광역시 중구 공항문화로 127",
            "kakao_confirmed_road_address": "인천광역시 중구 공항문화로 127",
            "kakao_confirmed_jibun_address": "인천광역시 중구 운서동 2955-74",
            "kakao_x": "126.45", "kakao_y": "37.46",
        }

        class Cursor:
            def __init__(self):
                self.calls, self.rowcount = [], 0
                self.created = False

            def execute(self, sql, params=None):
                self.calls.append((sql, params))
                self.rowcount = int("INSERT INTO master_buildings" in sql or
                                    "SET master_building_id" in sql)
                if "INSERT INTO master_buildings" in sql:
                    self.created = True

            def fetchone(self):
                return {"total": 1}

            def fetchall(self):
                sql = self.calls[-1][0]
                if "SELECT t.id, t.dimensions" in sql:
                    return [{"id": 44, "dimensions": dimensions}]
                if "WHERE mgm_bldrgst_pk" in sql:
                    return []
                if "SELECT id, dimensions" in sql:
                    return [{"id": 44, "dimensions": dimensions}]
                if "FROM master_buildings" in sql:
                    return ([{
                        "id": 77, "road_address": "인천광역시 중구 공항문화로 127",
                        "jibun_address": "인천광역시 중구 운서동 2955-74",
                    }] if self.created else [])
                return []

        class Bjdong:
            def find_bjdong_cd(self, sgg_cd, umd_nm):
                self.args = (sgg_cd, umd_nm)
                return "10100000"

            def sgg_text(self, sgg_cd):
                return "인천광역시 중구"

        title_rows = [{
            "mgmBldrgstPk": "hub-77", "mainPurpsCdNm": "숙박시설",
            "etcPurps": "관광호텔", "bldNm": "인스파이어 엔터테인먼트 리조트", "dongNm": "",
            "hoCnt": "120", "newPlatPlc": "인천광역시 중구 공항문화로 127",
            "platPlc": "인천광역시 중구 운서동 2955-74",
        }]
        cur = Cursor()
        result = importer.enrich_latest_top100_lodging_buildings(
            cur, Bjdong(),
            road_to_jibun_fn=lambda _road: {
                "admCd": "2811000000", "emdNm": "운서동",
                "lnbrMnnm": "2955", "lnbrSlno": "74", "mtYn": "0",
            },
            fetch_title_rows_fn=lambda *_args: title_rows,
        )
        linked = importer.match_lodging_rank_to_buildings(cur, ["rank.csv"])

        self.assertEqual(result, {"checked": 1, "created": 1, "manual_review": 0})
        self.assertEqual(linked, {"total": 1, "address": 1, "unmatched": 0})
        self.assertTrue(any("INSERT INTO master_buildings" in sql for sql, _ in cur.calls))
        self.assertTrue(any("SET master_building_id" in sql for sql, _ in cur.calls))

    def test_ambiguous_hub_lodging_towers_remain_manual_review(self):
        class Cursor:
            def __init__(self):
                self.calls, self.rowcount = [], 0

            def execute(self, sql, params=None):
                self.calls.append((sql, params))
                self.rowcount = 0

            def fetchall(self):
                return [{
                    "id": 44,
                    "dimensions": {"kakao_confirmed_road_address": "서울 중구 세종대로 1"},
                }]

        class Bjdong:
            def find_bjdong_cd(self, *_args):
                return "10100000"

        rows = [
            {"mgmBldrgstPk": "tower-a", "mainPurpsCdNm": "숙박시설"},
            {"mgmBldrgstPk": "tower-b", "mainPurpsCdNm": "숙박시설"},
        ]
        cur = Cursor()
        result = importer.enrich_latest_top100_lodging_buildings(
            cur, Bjdong(),
            road_to_jibun_fn=lambda _road: {
                "admCd": "1114000000", "emdNm": "태평로1가", "lnbrMnnm": "1",
            },
            fetch_title_rows_fn=lambda *_args: rows,
        )

        self.assertEqual(result, {"checked": 1, "created": 0, "manual_review": 1})
        review = [params for sql, params in cur.calls
                  if "lodging_match_review_reason" in sql]
        self.assertEqual(review[0][0], "building_hub_lodging_identity_ambiguous")
        self.assertFalse(any("INSERT INTO master_buildings" in sql for sql, _ in cur.calls))


if __name__ == "__main__":
    unittest.main()