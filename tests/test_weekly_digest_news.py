import unittest
from datetime import datetime
from html import escape
from unittest.mock import patch
from zoneinfo import ZoneInfo

import weekly_digest_news as news


SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=SEOUL)


def _rss(items):
    records = []
    for title, url, published in items:
        records.append(
            "<item>"
            f"<title>{escape(title)}</title><link>{escape(url)}</link>"
            f"<pubDate>{published}</pubDate>"
            "</item>"
        )
    return (
        "<rss version='2.0'><channel>"
        + "".join(records)
        + "</channel></rss>"
    ).encode()


def _kto_html(items):
    records = []
    for title, href, published in items:
        records.append(
            "<li><div><a href=\""
            + escape(href, quote=True)
            + "\">"
            + escape(title)
            + "</a></div><div class=\"col-date\"><span>"
            + escape(published)
            + "</span></div></li>"
        )
    return ("<html><body><ul>" + "".join(records) + "</ul></body></html>").encode()


class WeeklyDigestNewsTests(unittest.TestCase):
    def test_filters_recent_relevant_allowlisted_articles_and_caps_results(self):
        payload = _rss([
            (
                "지역 숙박시설 활성화 방안 발표",
                "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=12345&pMenuCD=0302000000",
                "20260922132226",
            ),
            (
                "K-컬처 행사 안내",
                "http://www.mcst.go.kr/web/s_notice/press/pressView.jsp?pSeq=12346",
                "20260922132226",
            ),
            (
                "관광 정책 발표",
                "https://evil.example/web/s_notice/press/pressView.jsp?pSeq=12347",
                "20260922132226",
            ),
            (
                "호텔 관광 지원 사업",
                "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=12348",
                "20260922132226",
            ),
            (
                "국내 여행 지원 계획",
                "http://www.mcst.go.kr/web/s_notice/press/pressView.jsp?pSeq=12349",
                "20260922132226",
            ),
            (
                "관광 숙박 특별 지원",
                "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=12350",
                "20260922132226",
            ),
        ])

        results = news._parse_feed(payload, now=NOW, limit=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(
            results[0],
            {
                "title": "지역 숙박시설 활성화 방안 발표",
                "url": "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=12345&pMenuCD=0302000000",
                "source": "문화체육관광부",
                "published": "2026-09-22",
            },
        )
        self.assertTrue(all(item["url"].startswith("https://www.mcst.go.kr/") for item in results))

    def test_rejects_old_future_malformed_and_non_original_links(self):
        payload = _rss([
            ("오래된 관광 정책 자료", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=20", "20260823110000"),
            ("미래 숙박 정책 발표", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=21", "20260924110000"),
            ("관광 정책 날짜 오류", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=22", "not-a-date"),
            ("호텔 정책 링크 오류", "https://www.mcst.go.kr/redirect?pSeq=23", "20260922110000"),
            ("숙박 정책 링크 누락 ID", "https://www.mcst.go.kr/web/s_notice/press/pressView.jsp?pSeq=nope", "20260922110000"),
        ])
        self.assertEqual(news._parse_feed(payload, now=NOW), [])

    def test_deduplicates_article_ids_and_rejects_malformed_titles(self):
        payload = _rss([
            ("관광 숙박 지원 정책", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=30", "20260922110000"),
            ("호텔 중복 숙박 제목", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=30", "20260922110000"),
            (" ", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=31", "20260922110000"),
            ("호텔", "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=32", "20260922110000"),
        ])
        results = news._parse_feed(payload, now=NOW)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "관광 숙박 지원 정책")

    def test_kto_listing_requires_direct_article_and_lodging_specific_title(self):
        payload = _kto_html([
            (
                "1박의 이유는 숙소 밖에… 데이터로 본 요즘 숙박",
                "/pressRelease/550763?curPage=1&fieldTy=",
                "2026-08-31",
            ),
            (
                "가을 캠핑장 운영 계획",
                "https://knto.or.kr/pressRelease/550764",
                "2026-09-22",
            ),
            (
                "관광 정책과 국내 여행 활성화",
                "/pressRelease/550765",
                "2026-09-22",
            ),
            (
                "호텔 투자 소식",
                "https://evil.example/pressRelease/550766",
                "2026-09-22",
            ),
        ])

        results = news._parse_knto_listing(payload, now=NOW, limit=3)

        self.assertEqual([item["title"] for item in results], [
            "1박의 이유는 숙소 밖에… 데이터로 본 요즘 숙박",
            "가을 캠핑장 운영 계획",
        ])
        self.assertEqual(results[0]["source"], "한국관광공사")
        self.assertEqual(results[0]["url"], "https://knto.or.kr/pressRelease/550763")

    def test_mcst_http_feed_links_are_not_upgraded_to_https(self):
        payload = _rss([
            ("숙박 정책 발표", "http://www.mcst.go.kr/web/s_notice/press/pressView.jsp?pSeq=60", "20260922110000"),
        ])
        self.assertEqual(news._parse_feed(payload, now=NOW), [])

    def test_kto_listing_rejects_stale_or_malformed_dates(self):
        payload = _kto_html([
            ("오래된 호텔 운영 소식", "/pressRelease/550768", "2026-08-23"),
            ("날짜 오류 숙박 소식", "/pressRelease/550769", "2026-99-45"),
        ])
        self.assertEqual(news._parse_knto_listing(payload, now=NOW), [])

    def test_feed_fetch_url_must_be_allowlisted_https(self):
        for url in (
            "http://knto.or.kr/pressRelease",
            "https://evil.example/pressRelease",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                news._fetch_feed(url)

    def test_rejects_dtd_and_invalid_xml(self):
        self.assertEqual(
            news._parse_feed(b"<!DOCTYPE rss [<!ENTITY x 'bad'>]><rss/>", now=NOW),
            [],
        )
        self.assertEqual(news._parse_feed(b"<rss>", now=NOW), [])

    def test_fetch_failures_return_empty_list(self):
        with patch.object(news, "_fetch_feed", side_effect=TimeoutError("slow")):
            self.assertEqual(news.get_recent_news(), [])

    def test_public_fetch_uses_mock_source_and_returns_expected_shape(self):
        payload = _kto_html([
            ("숙박 산업 동향", "/pressRelease/550767", "2026-09-22"),
        ])
        def mock_fetch(url):
            if url == news.KTO_PRESS_RELEASE_URL:
                return payload
            return _rss([])

        with (
            patch.object(news, "_fetch_feed", side_effect=mock_fetch),
            patch.object(news, "_now_seoul", return_value=NOW),
        ):
            result = news.get_recent_news(limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]), {"title", "url", "source", "published"})


if __name__ == "__main__":
    unittest.main()