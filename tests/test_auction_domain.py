"""공적 상태·일정·가격을 임의로 추정하지 않는 공매 판정 회귀 검사."""
import unittest
from datetime import datetime
from unittest.mock import patch

from auction_domain import (
    KST, normalize, number, source_date, status, sale_kind, safe_url, response_items,
)


class AuctionDomainTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 4, 12, tzinfo=KST)
        self.row = {
            "cltrMngNo": "2026-00001-001", "pbctCdtnNo": 123,
            "prptDivCd": "0007", "pbctStatCd": "0001",
            "cltrBidBgngDt": "202610061400", "cltrBidEndDt": "202610071700",
            "pbctNsq": "035", "usbdNft": 2, "apslEvlAmt": 100000000,
            "lowstBidPrcIndctCont": "66,640,000", "bldSqms": 23,
            "onbidCltrNm": "경기도 수원시 팔달구 매산로1가 10 제4층 제401호 생활숙박시설",
            "onbidCltrno": 1981, "onbidPbancNo": 892, "pbctNo": 100,
        }

    def test_null_and_nonpublic_prices_are_not_zero(self):
        for value in (None, "", "비공개", "0", 0, "최저가 120000원", float("nan"), float("inf"), "-1"):
            self.assertIsNone(number(value, True))

    def test_date_placeholders_are_not_real_deadlines(self):
        for value in ("299912301600", "202602300000", "x", None):
            self.assertIsNone(source_date(value))

    def test_scheduled_and_bidding_use_real_period(self):
        self.assertEqual(status(self.row, self.now), "scheduled")
        row = dict(self.row, cltrBidBgngDt="202610011400", cltrBidEndDt="202610071700")
        self.assertEqual(status(row, self.now), "bidding")

    def test_expired_period_does_not_infer_failed(self):
        row = dict(self.row, cltrBidBgngDt="202609011400", cltrBidEndDt="202609021700")
        self.assertEqual(status(row, self.now), "closed")

    def test_undated_prepared_is_not_scheduled(self):
        row = dict(self.row, cltrBidBgngDt="299912301000", cltrBidEndDt="299912301600")
        self.assertEqual(status(row, self.now), "closed")

    def test_final_result_codes(self):
        for code, result in (("0010", "sold"), ("0011", "failed"), ("0012", "canceled")):
            self.assertEqual(status(dict(self.row, pbctStatCd=code), self.now), result)

    def test_previous_failed_result_is_not_current_failed(self):
        bid = {"prcnNsqBidRsltNm": "유찰", "prcnBidClgList": [{"pbctNsq": "034", "pbctStatNm": "유찰"}]}
        self.assertEqual(status(self.row, self.now, bid), "scheduled")

    def test_current_round_confirmed_result(self):
        bid = {"prcnBidClgList": [{"pbctCdtnNo": 123, "pbctNsq": "035", "pbctStatNm": "낙찰"}]}
        self.assertEqual(status(self.row, self.now, bid), "sold")

    def test_same_round_number_from_earlier_notice_is_not_current_result(self):
        bid = {"prcnBidClgList": [{"pbctNsq": "035", "cltrOpbdDt": "202608090900", "pbctStatNm": "낙찰"}]}
        self.assertEqual(status(self.row, self.now, bid), "scheduled")

    def test_entrusted_is_not_trust(self):
        self.assertEqual(sale_kind({"prptDivCd": "0008"}, []), "기타")
        self.assertEqual(sale_kind({"orgNm": "코리아신탁", "prptDivCd": "0005"}, []), "기타")

    def test_trust_requires_agency_and_official_evidence(self):
        self.assertEqual(sale_kind({"orgNm": "코리아신탁", "prptDivCd": "0005"},
                                   [{"anncmAlCont": "신탁부동산 매각"}]), "신탁")
        self.assertEqual(sale_kind({"orgNm": "일반기관", "prptDivCd": "0005"},
                                   [{"anncmAlCont": "신탁부동산"}]), "기타")

    def test_normalized_prices_ratio_category_unit(self):
        row = normalize(self.row, now=self.now)
        self.assertEqual(row["min_bid_price"], 66640000)
        self.assertEqual(row["min_bid_ratio"], 66.64)
        self.assertEqual(row["lodging_category"], "생활숙박")
        self.assertIn("401호", row["unit_label"])
        self.assertIn("onbidCltrno=1981", row["detail_url"])

    def test_pnu_address_fallback_is_parcel_not_title_guess(self):
        row = normalize(dict(self.row, ltnoPnu="4122010200004830006",
                             lctnSdnm="경기도", lctnSggnm="평택시", lctnEmdNm="장당동"))
        self.assertEqual(row["address_jibun"], "경기도 평택시 장당동 483-6")

    def test_signed_or_credential_urls_not_accepted_as_provider_photos(self):
        for value in ("javascript:alert(1)", "https://evil.example/a.jpg", "https://www.onbid.co.kr/a?serviceKey=SECRET",
                      "https://user:pass@www.onbid.co.kr/a.jpg", "//www.onbid.co.kr/a.jpg"):
            self.assertIsNone(safe_url(value, onbid_only=True))
        self.assertTrue(safe_url("https://www.onbid.co.kr/a?atchSn=1", onbid_only=True))

    def test_single_item_and_no_data_shapes(self):
        items, total = response_items({"header": {"resultCode": "00"}, "body": {"totalCount": 1, "items": {"item": {"x": 1}}}})
        self.assertEqual((items, total), ([{"x": 1}], 1))
        self.assertEqual(response_items({"result": {"resultCode": "03"}}), ([], 0))
        with self.assertRaises(ValueError):
            response_items({"result": {"resultCode": "30"}})


if __name__ == "__main__":
    unittest.main()