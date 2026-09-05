import unittest

import backfill_gocamping_web as web


class GoCampingWebBackfillTests(unittest.TestCase):
    def test_parses_list_identity_address_and_image(self):
        page = """
        <div class="list-item ">
          <img src="/images/decorative.svg">
          <a href="/bsite/camp/info/read.do?c_no=100093">
            <img alt='비토애글램핑2호점(BITOLUV GLAMPING Season2)'
                 src='/upload/camp/100093/thumb/main.jpg'>
          </a>
          <a class="address fs-16bodyR">경상남도 사천시 서포면 토끼로 217 </a>
        </div>
        """
        rows = web.parse_web_list(page)
        self.assertEqual(rows[0]["content_id"], "100093")
        self.assertEqual(
            web._candidate_key(rows[0]["name"], rows[0]["address"]),
            ("비토애글램핑2호점", "경상남도사천시서포면토끼로217"),
        )
        self.assertTrue(rows[0]["first_image_url"].startswith("https://"))

    def test_known_bitoae_record_matches_verified_web_content(self):
        candidates = [{
            "id": 1388281,
            "biz_name": "비토애글램핑2호점(BITOLUV GLAMPING Season2)",
            "road_address": "경상남도 사천시 서포면 토끼로 217",
        }]
        web_rows = [{
            "content_id": "100093",
            "name": "비토애글램핑2호점(BITOLUV GLAMPING Season2)",
            "address": "경상남도 사천시 서포면 토끼로 217",
        }]
        matches, ambiguous = web.match_web_rows(candidates, web_rows)
        self.assertEqual(ambiguous, 0)
        self.assertEqual(matches[0][0]["id"], 1388281)
        self.assertEqual(matches[0][1]["content_id"], "100093")

    def test_parses_naver_reservation_and_deduplicates_full_images(self):
        page = """
        <dt>예약페이지</dt><dd>
          <a href="https://booking.naver.com/booking/3/bizes/576792">바로가기</a>
        </dd>
        <img src="/upload/camp/100093/a.jpg">
        <img src="/upload/camp/100093/a.jpg">
        <img src="/upload/camp/100093/thumb/thumb.jpg">
        <img src="/upload/camp/100093/b.jpg">
        """
        result = web.parse_web_detail(
            page, "100093", "https://gocamping.or.kr/upload/camp/100093/main.jpg"
        )
        self.assertIn("booking.naver.com", result["reservation_url"])
        self.assertEqual(len(result["image_urls"]), 3)
        self.assertNotIn("/thumb/thumb.jpg", result["image_urls"])

    def test_rejects_non_http_reservation(self):
        page = '<dt>예약페이지</dt><dd><a href="javascript:alert(1)">예약</a></dd>'
        self.assertIsNone(
            web.parse_web_detail(page, "1")["reservation_url"]
        )

    def test_unique_address_does_not_override_changed_name(self):
        candidates = [{
            "id": 1, "biz_name": "예전 상호",
            "road_address": "경상남도 사천시 서포면 토끼로 217",
        }]
        web_rows = [{
            "content_id": "100093", "name": "새로운 상호",
            "address": "경상남도 사천시 서포면 토끼로 217",
        }]
        matches, ambiguous = web.match_web_rows(candidates, web_rows)
        self.assertEqual(ambiguous, 0)
        self.assertEqual(matches, [])

    def test_shared_address_is_not_automatically_matched(self):
        candidates = [
            {"id": 1, "biz_name": "A", "road_address": "서울 성동구 뚝섬로 1"},
            {"id": 2, "biz_name": "B", "road_address": "서울 성동구 뚝섬로 1"},
        ]
        web_rows = [{
            "content_id": "9", "name": "새 상호",
            "address": "서울 성동구 뚝섬로 1",
        }]
        matches, _ = web.match_web_rows(candidates, web_rows)
        self.assertEqual(matches, [])

    def test_duplicate_web_identity_is_not_automatically_matched(self):
        candidates = [{
            "id": 1, "biz_name": "같은 캠핑장",
            "road_address": "경남 사천시 토끼로 217",
        }]
        web_rows = [
            {
                "content_id": "10", "name": "같은 캠핑장",
                "address": "경남 사천시 토끼로 217",
            },
            {
                "content_id": "11", "name": "같은 캠핑장",
                "address": "경남 사천시 토끼로 217",
            },
        ]
        matches, ambiguous = web.match_web_rows(candidates, web_rows)
        self.assertEqual(matches, [])
        self.assertEqual(ambiguous, 1)


if __name__ == "__main__":
    unittest.main()