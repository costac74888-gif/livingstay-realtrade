import unittest
from datetime import date

from lodging_stats_dedup import deduplicate_cross_source_lodgings
from app import _capped_active_report_rooms_by_building


class LodgingStatsDedupTest(unittest.TestCase):
    def test_room_cap_uses_only_completed_living_candidates_and_living_reports(self):
        completed = {
            "id": 1,
            "units": 10,
            "road_address": "서울 중구 테스트로 1",
            "jibun_address": None,
        }
        pre_completion = {
            "id": 2,
            "units": 100,
            "road_address": "서울 중구 테스트로 1",
            "jibun_address": None,
        }
        road_key = "서울중구테스트로1"
        living = {
            "permit_number": "L-1",
            "biz_name": "생활숙박",
            "permit_date": "2024-01-01",
            "room_count": 30,
            "biz_status_name": "영업/정상",
            "hygiene_type": "숙박업(생활)",
            "road_norm": road_key,
            "jibun_norm": None,
        }
        unrelated = {
            **living,
            "permit_number": "G-1",
            "biz_name": "일반숙박",
            "room_count": 50,
            "hygiene_type": "숙박업(일반)",
        }
        matches = {road_key: {"L-1": living, "G-1": unrelated}}

        completed_only = _capped_active_report_rooms_by_building(
            [completed], matches, {}, expected_type="생활"
        )
        with_pre_completion = _capped_active_report_rooms_by_building(
            [completed, pre_completion], matches, {}, expected_type="생활"
        )

        self.assertEqual(completed_only, {1: 10})
        self.assertEqual(with_pre_completion, {2: 30})

    def test_same_address_date_and_rooms_merges_cross_source_alias(self):
        rows = [
            {
                "permit_number": "3020000-201-2017-00005",
                "biz_name": "노보텔 앰배서더 서울용산",
                "permit_date": date(2017, 9, 29),
                "room_count": 621,
                "road_norm": "서울용산구청파로20길95",
            },
            {
                "permit_number": "TOURISM:3020000:CDFI2260032017000004",
                "biz_name": "(주)서부티엔디 노보텔 앰배서더 서울 용산",
                "permit_date": "2017-09-29",
                "room_count": 621,
                "road_norm": "서울용산구청파로20길95",
            },
        ]
        result = deduplicate_cross_source_lodgings(rows)
        self.assertEqual([row["permit_number"] for row in result], [
            "3020000-201-2017-00005",
        ])

    def test_different_room_counts_are_preserved_as_separate_active_reports(self):
        rows = [
            {
                "permit_number": "6510000-201-2020-00001",
                "biz_name": "그랜드하얏트제주",
                "permit_date": "2020-01-01",
                "room_count": 750,
                "road_norm": "제주도제주시노연로12",
            },
            {
                "permit_number": "TOURISM:6510000:OTHER",
                "biz_name": "그랜드하얏트제주 R타워",
                "permit_date": "2021-01-01",
                "room_count": 850,
                "road_norm": "제주도제주시노연로12",
            },
        ]
        self.assertEqual(len(deduplicate_cross_source_lodgings(rows)), 2)

    def test_missing_rooms_require_same_normalized_business_name(self):
        same = [
            {
                "permit_number": "P-1",
                "biz_name": "호텔 스테이",
                "permit_date": "2020-01-01",
                "room_count": None,
                "jibun_norm": "서울중구1",
            },
            {
                "permit_number": "TOURISM:A:1",
                "biz_name": "호텔스테이",
                "permit_date": "2020-01-01",
                "room_count": None,
                "jibun_norm": "서울중구1",
            },
        ]
        self.assertEqual(len(deduplicate_cross_source_lodgings(same)), 1)
        same[1]["biz_name"] = "별도 타워"
        self.assertEqual(len(deduplicate_cross_source_lodgings(same)), 2)


if __name__ == "__main__":
    unittest.main()