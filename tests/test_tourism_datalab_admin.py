import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path

import import_tourism_stats as importer
import tourism_datalab_admin as admin

RAW = ("광역시/도,시/군/구,관광지ID,관광지명,중분류 카테고리,순위,검색건수\n"
       "서울특별시,중구,x,호텔,숙박,1,20\n").encode()

class Upload:
    def __init__(self, name, data): self.filename, self.data = name, data
    def read(self): return self.data

class Cursor:
    def __init__(self, stage=None): self.calls=[]; self.stage=stage; self.token="secure-token"
    def execute(self, sql, params=None): self.calls.append((sql, params))
    def fetchone(self):
        if self.stage is not None: return self.stage
        return {"token": self.token}
    def close(self): pass
class Conn:
    def __init__(self, stage=None): self.cur=Cursor(stage); self.commits=0; self.rollbacks=0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1

def zipped(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        for name,data in entries: z.writestr(name,data)
    return stream.getvalue()

class TourismDatalabAdminTests(unittest.TestCase):
    def test_owner_rejects_missing_bool_and_string(self):
        for value in (None, True, "1", 0):
            with self.assertRaises(ValueError): admin.preview(Conn(), [Upload("x.csv",RAW)], value)

    def test_cp949_success(self):
        raw=RAW.decode().encode("cp949")
        result=admin.preview(Conn(),[Upload("지역별 관광지 검색순위.csv",raw)],1)
        self.assertEqual(result["supported_rows"],1)

    def test_duplicate_and_blank_headers_rejected(self):
        for raw in (b"a,a\n1,2\n", b"a,\n1,2\n"):
            with self.assertRaises(ValueError): admin._csv_rows("x.csv",raw)

    def test_unclosed_quote_and_width_rejected(self):
        with self.assertRaises(ValueError): admin._csv_rows("x.csv",b"a,b\n\"bad,ok\n")
        with self.assertRaises(ValueError): admin._csv_rows("x.csv",b"a,b\none,two,three\n")

    def test_valid_zip_directory_is_skipped(self):
        data=zipped([("folder/",b""),("지역별 관광지 검색순위.csv",RAW)])
        self.assertEqual(len(admin._members("x.zip",data)),1)

    def test_traversal_directory_rejected_before_skip(self):
        with self.assertRaises(ValueError): admin._members("x.zip",zipped([("../bad/",b"")]))

    def test_nested_zip_rejected(self):
        with self.assertRaises(ValueError): admin._members("x.zip",zipped([("nested.zip",b"x")]))

    def test_symlink_rejected(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            info=zipfile.ZipInfo("x.csv"); info.external_attr=(0o120777 << 16); z.writestr(info,b"x")
        with self.assertRaises(ValueError): admin._members("x.zip",stream.getvalue())

    def test_empty_and_unsupported_rejected(self):
        with self.assertRaises(ValueError): admin.preview(Conn(),[Upload("empty.zip",zipped([]))],1)
        with self.assertRaises(ValueError): admin.preview(Conn(),[Upload("unknown.csv",b"a,b\n1,2\n")],1)

    def test_duplicate_upload_and_content_rejected(self):
        with self.assertRaises(ValueError): admin.preview(Conn(),[Upload("x.csv",RAW),Upload("x.csv",RAW)],1)
        with self.assertRaises(ValueError): admin.preview(Conn(),[Upload("지역별 관광지 검색순위.csv",RAW),Upload("관광숙박 검색순위.csv",RAW)],1)

    def test_canonical_rows_and_hash_parity(self):
        rows, kind, skipped=importer.build_member_metric_rows("a.csv::지역별 관광지 검색순위.csv","지역별 관광지 검색순위.csv",
            admin._csv_rows("x.csv",RAW),"202601-202602")
        self.assertEqual((kind,len(rows),skipped),("lodging_search_rank",1,0))
        result=admin.preview(Conn(),[Upload("지역별 관광지 검색순위.csv",RAW)],1)
        self.assertEqual(result["supported_rows"],len(rows))
        self.assertEqual(rows[0][10], importer.build_lodging_rank_row(admin._csv_rows("x.csv",RAW)[0],"a.csv::지역별 관광지 검색순위.csv","202601-202602",2)[10])

    def test_preview_inserts_explicit_token(self):
        conn=Conn(); result=admin.preview(conn,[Upload("지역별 관광지 검색순위.csv",RAW)],1)
        sql,params=conn.cur.calls[-1]
        self.assertIn("token,admin_user_id",sql); self.assertGreater(len(params[0]),30)

    def test_apply_hash_mismatch_happens_before_delete(self):
        conn=Conn({"manifest":{"rows":[]}, "manifest_hash":"bad"})
        with self.assertRaises(ValueError): admin.apply(conn,"t",1)
        self.assertFalse(any("DELETE FROM tourism_stats" in q for q,_ in conn.cur.calls))

    def test_apply_claim_and_retry_failure_state_sql(self):
        manifest={"members":[],"rows":[["x",None,None,None,"m",1,"", "f",None,"{}", "h"]],"unsupported_members":[]}
        digest=hashlib.sha256(json.dumps(manifest,ensure_ascii=False,separators=(",",":"),default=str).encode()).hexdigest()
        conn=Conn({"manifest":manifest,"manifest_hash":digest})
        # Force matching failure after the atomic claim; test never executes DB data.
        old=importer.match_lodging_rank_to_buildings
        old_values=admin.execute_values
        importer.match_lodging_rank_to_buildings=lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        admin.execute_values=lambda *a, **k: None
        try:
            with self.assertRaises(RuntimeError): admin.apply(conn,"t",1)
        finally:
            importer.match_lodging_rank_to_buildings=old
            admin.execute_values=old_values
        calls="\n".join(q for q,_ in conn.cur.calls)
        self.assertIn("state='applying'",calls); self.assertIn("state IN ('previewed','failed')",calls)
        self.assertIn("pg_advisory_xact_lock",calls)
        self.assertLess(calls.index("pg_advisory_xact_lock"), calls.index("DELETE FROM tourism_stats"))
        self.assertGreaterEqual(conn.rollbacks,1)

    def test_source_lock_keys_are_stable_signed_and_sorted_contract(self):
        self.assertEqual(admin.source_lock_key("a"), admin.source_lock_key("a"))
        self.assertTrue(-(2**63) <= admin.source_lock_key("a") < 2**63)

    def test_latest_source_order_contract(self):
        sql=importer.latest_source_order_sql("t")
        self.assertIn("search_ranking",sql)
        self.assertLess(sql.index("collected_at"),sql.index("split_part"))
        with self.assertRaises(ValueError): importer.latest_source_order_sql("t; DROP TABLE x")

    def test_production_schema_boot_contract(self):
        start=Path("scripts/start-prod.sh").read_text(encoding="utf-8")
        schema=Path("scripts/ensure_tourism_datalab_schema.py").read_text(encoding="utf-8")
        self.assertLess(start.index("ensure_tourism_datalab_schema.py"),start.index("exec gunicorn"))
        self.assertIn("SKIP_STARTUP_SCHEMA_INIT=1",start)
        for text in ("pg_advisory_xact_lock","CREATE TABLE IF NOT EXISTS tourism_datalab_stages",
                     "REFERENCES admin_users(id) ON DELETE CASCADE","manifest_hash TEXT NOT NULL"):
            self.assertIn(text,schema)

    def test_all_actual_ten_assets_validate_together(self):
        paths=sorted(Path("attached_assets").glob("*데이터랩*.zip"))
        paths += sorted(Path("attached_assets").glob("*관광지_검색순위*.csv"))
        self.assertEqual(len(paths),10)
        result=admin.preview(Conn(),[Upload(p.name,p.read_bytes()) for p in paths],1)
        self.assertGreater(result["supported_rows"],0)
        self.assertEqual(set(result["types"]), {kind for _,kind in importer.TYPE_RULES})

    def test_generic_row_cannot_partially_emit_blank_metric(self):
        raw=("광역지자체명,기초지자체명,기초지자체 방문자 수,기초지자체 방문자 비율\n"
             "서울특별시,중구,100,\n").encode()
        with self.assertRaises(ValueError):
            admin.preview(Conn(),[Upload("지역별 방문자 수(기초지자체별).csv",raw)],1)

    def test_generic_row_rejects_nonnumeric_and_nonfinite_metric(self):
        for bad in ("not-a-number","NaN","Infinity"):
            raw=("광역지자체명,기초지자체명,기초지자체 방문자 수,기초지자체 방문자 비율\n"
                 f"서울특별시,중구,100,{bad}\n").encode()
            with self.assertRaises(ValueError):
                admin.preview(Conn(),[Upload("지역별 방문자 수(기초지자체별).csv",raw)],1)

    def test_invalid_lodging_rank_is_rejected_not_silently_skipped(self):
        raw=("광역시/도,시/군/구,관광지ID,관광지명,중분류 카테고리,순위,검색건수\n"
             "서울특별시,중구,x,호텔,숙박,not-rank,20\n").encode()
        with self.assertRaises(ValueError):
            admin.preview(Conn(),[Upload("관광숙박 검색순위.csv",raw)],1)

    def test_three_distribution_contracts_emit_exact_metrics(self):
        fixtures=[
            ("캠핑장 업종별 분포.csv","기준년도,업종명,현황수,분포율\n2026,일반야영장,10,50\n",2),
            ("캠핑사이트 유형별 현황.csv","기준년도,업종명,현황수\n2026,자동차야영장,10\n",1),
            ("업종별 분포.csv","기준년도,업종명,숙박영업현황수,분포율\n2026,호텔업,10,50\n",2),
        ]
        for filename,text,count in fixtures:
            with self.subTest(filename=filename):
                result=admin.preview(Conn(),[Upload(filename,text.encode())],1)
                self.assertEqual(result["supported_rows"],count)