import pathlib
import unittest


class OperationBenchmarkContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = pathlib.Path("app.py").read_text(encoding="utf-8")
        start = source.index('@app.route("/api/analysis/operation-benchmarks")')
        end = source.index("def _analysis_growth", start)
        cls.endpoint = source[start:end]
        cls.frontend = pathlib.Path("static/js/analysis.js").read_text(encoding="utf-8")

    def test_endpoint_uses_building_sido_and_real_sgg_overall_rows(self):
        self.assertIn("FROM master_buildings WHERE id=%s", self.endpoint)
        self.assertIn("NULLIF(road_address, '')", self.endpoint)
        self.assertIn("NULLIF(jibun_address, '')", self.endpoint)
        self.assertIn("m.sgg_name IS NOT NULL AND m.grade='전체'", self.endpoint)
        self.assertIn("m.sido_name=%s", self.endpoint)
        self.assertIn(
            "ORDER BY m.revpar DESC, m.occupancy_rate DESC, m.adr DESC",
            self.endpoint,
        )
        self.assertNotIn("LIMIT 5\n        \"\"\", (sido,))", self.endpoint)
        self.assertIn("실제 시군구 전체 운영지표", self.endpoint)
        self.assertIn('"source": source', self.endpoint)

    def test_schema_and_importer_deduplicate_the_same_source_archive(self):
        schema = pathlib.Path("db.py").read_text(encoding="utf-8")
        importer = pathlib.Path("import_hotel_operation.py").read_text(encoding="utf-8")
        self.assertIn("source_sha256 TEXT NOT NULL UNIQUE", schema)
        self.assertIn("ON CONFLICT (source_sha256) DO NOTHING", importer)
        self.assertIn("validate_operation_records(records)", importer)
        self.assertIn("_seed_hotel_operation_metrics(cur)", schema)
        self.assertIn("2024_호텔업운영현황_1788781907828.zip", schema)

    def test_frontend_fetches_benchmarks_without_hardcoded_regions(self):
        self.assertIn("/api/analysis/operation-benchmarks?building_id=", self.frontend)
        self.assertIn("seq!==operationSeq", self.frontend)
        self.assertIn("state.targetBuildingId=String(i.building_id)", self.frontend)
        self.assertIn("해당 시도의 공개 운영지표가 없습니다.", self.frontend)
        self.assertNotIn('{region:"서울",adr:', self.frontend)


if __name__ == "__main__":
    unittest.main()