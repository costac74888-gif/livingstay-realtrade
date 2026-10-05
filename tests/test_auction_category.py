"""생활숙박 분류의 공적 근거·SQL 필터·재수집 보존 검사. DB 변경은 모두 롤백."""
import json
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

from auction_domain import category, EFFECTIVE_CATEGORY_SQL, KST
from auction_building_matching import build_indexes, resolve_building
from db import get_conn


class AuctionCategoryTest(unittest.TestCase):
    building = {"id": 1, "lodging_type": "생활",
                "lodging_type_detail": "숙박시설(생활숙박시설), 제1종근린생활시설"}
    source = {"cltrUsgSclsCtgrNm": "숙박시설", "onbidCltrNm": "더마크속초레지던스 제507호"}

    def test_verified_building_supplements_generic_source(self):
        self.assertEqual(category(self.source, self.building), "생활숙박")
        self.assertEqual(category(self.source), "기타")

    def test_residence_or_brand_name_alone_is_not_evidence(self):
        for title in ("더마크속초레지던스", "어떤 레지던스", "생소한 숙박시설"):
            self.assertEqual(category({**self.source, "onbidCltrNm": title}), "기타")

    def test_missing_ambiguous_or_nonliving_building_evidence_is_not_used(self):
        for building in ({"lodging_type": "생활"}, {"lodging_type": "일반"},
                         {**self.building, "lodging_type": "생활·일반"}):
            self.assertEqual(category(self.source, building), "기타")

    def test_explicit_source_classification_is_preserved(self):
        for usage, result in (("오피스텔", "오피스텔"), ("모텔", "모텔"), ("펜션", "펜션")):
            self.assertEqual(category({**self.source, "cltrUsgSclsCtgrNm": usage}, self.building), result)

    def test_read_resolution_uses_same_category_without_writing(self):
        building = {**self.building, "jibun_address": "강원특별자치도 속초시 조양동 1383-18"}
        item = {"title": self.source["onbidCltrNm"], "usage_name": "숙박시설",
                "lodging_category": "기타", "address_jibun": building["jibun_address"]}
        with patch("auction_building_matching.get_indexes", return_value=build_indexes([building])):
            self.assertEqual(resolve_building(None, item)["id"], 1)
        self.assertEqual(item["lodging_category"], "생활숙박")

    def test_sql_projection_filter_and_resync_preserve_verified_category(self):
        from sync_onbid import Runner
        conn = get_conn()
        unique = uuid.uuid4().hex
        @contextmanager
        def uncommitted():
            yield conn
        try:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO master_buildings(building_name,sgg_text,umd_nm,jibun,
                  road_address,jibun_address,lodging_type,lodging_type_detail) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    ["분류검증-"+unique, "검증시", "검증동", unique, "검증시 검증로 "+unique, "검증시 검증동 "+unique,
                     "생활", self.building["lodging_type_detail"]])
                building_id = cur.fetchone()["id"]
                for suffix, linked, evidence_address, explicit in (
                    ("linked", building_id, None, "기타"),
                    ("snapshot", None, "검증주소", "기타"),
                    ("mismatch", None, "다른주소", "기타"),
                    ("unknown", None, None, "기타"),
                    ("explicit", building_id, None, "호텔"),
                ):
                    raw = {"_building_category_evidence": {
                        "source": "master_building", "address_jibun": evidence_address,
                        "lodging_type": "생활", "lodging_type_detail": self.building["lodging_type_detail"]
                    }} if evidence_address else {}
                    cur.execute("""INSERT INTO auction_items(source,source_item_id,pbct_cdtn_no,
                      lodging_category,master_building_id,address_jibun,usage_name,raw)
                      VALUES('onbid',%s,'test',%s,%s,'검증주소','숙박시설',%s::jsonb)""",
                        [unique+suffix, explicit, linked, json.dumps(raw)])
                cur.execute(f"""SELECT a.source_item_id,({EFFECTIVE_CATEGORY_SQL}) AS category
                  FROM auction_items a WHERE a.source_item_id LIKE %s""", [unique+"%"])
                found = {r["source_item_id"][len(unique):]: r["category"] for r in cur.fetchall()}
                self.assertEqual(found, {"linked": "생활숙박", "snapshot": "생활숙박",
                    "mismatch": "기타", "unknown": "기타", "explicit": "호텔"})
                cur.execute(f"""SELECT COUNT(*) AS n FROM auction_items a
                  WHERE a.source_item_id LIKE %s AND ({EFFECTIVE_CATEGORY_SQL})='생활숙박'""", [unique+"%"])
                self.assertEqual(cur.fetchone()["n"], 2)

            runner = Runner.__new__(Runner)
            runner.master_road, runner.master_jibun = {}, {}
            runner.state, runner.own = {}, lambda: True
            row = {"cltrMngNo": unique+"snapshot", "pbctCdtnNo": "test",
                "cltrUsgSclsCtgrNm": "숙박시설", "onbidCltrNm": "분류 검증 레지던스",
                "zadrNm": "검증주소", "pbctStatCd": "0001",
                "cltrBidBgngDt": (datetime.now(KST)+timedelta(days=2)).strftime("%Y%m%d%H%M"),
                "cltrBidEndDt": (datetime.now(KST)+timedelta(days=3)).strftime("%Y%m%d%H%M")}
            with patch("sync_onbid.get_conn", uncommitted):
                runner.stage_rows({(row["cltrMngNo"], "test"): row})
            with conn.cursor() as cur:
                cur.execute("SELECT lodging_category FROM auction_items WHERE source_item_id=%s", [unique+"snapshot"])
                self.assertEqual(cur.fetchone()["lodging_category"], "생활숙박")
                # A newer, contrary building record must outrank a saved snapshot.
                cur.execute("UPDATE auction_items SET master_building_id=%s,lodging_category='기타' WHERE source_item_id=%s",
                            [building_id, unique+"snapshot"])
                cur.execute("UPDATE master_buildings SET lodging_type='일반',lodging_type_detail='일반숙박시설' WHERE id=%s", [building_id])
                cur.execute(f"SELECT ({EFFECTIVE_CATEGORY_SQL}) AS category FROM auction_items a WHERE a.source_item_id=%s",
                            [unique+"snapshot"])
                self.assertEqual(cur.fetchone()["category"], "기타")
                cur.execute("UPDATE auction_items SET lodging_category='생활숙박' WHERE source_item_id=%s", [unique+"snapshot"])
                cur.execute(f"SELECT ({EFFECTIVE_CATEGORY_SQL}) AS category FROM auction_items a WHERE a.source_item_id=%s",
                            [unique+"snapshot"])
                self.assertEqual(cur.fetchone()["category"], "기타")
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()