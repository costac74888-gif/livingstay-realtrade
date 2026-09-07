import pathlib
import unittest


class OperationUploadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = pathlib.Path("app.py").read_text(encoding="utf-8")
        cls.frontend = pathlib.Path("static/js/operation-analysis.js").read_text(encoding="utf-8")
        cls.legacy_frontend = pathlib.Path("static/js/analysis.js").read_text(encoding="utf-8")
        start = cls.app_source.index('@app.route("/api/analysis/operation-upload"')
        end = cls.app_source.index('@app.route("/api/analysis/operation-benchmarks"', start)
        cls.endpoint = cls.app_source[start:end]

    def test_upload_is_immediate_authenticated_and_not_retained(self):
        self.assertIn('"user_id", "agent_id", "operator_id", "loan_consultant_id"', self.endpoint)
        self.assertIn('"retained": False', self.endpoint)
        self.assertNotIn("storage_util.upload", self.endpoint)
        self.assertNotIn("@require_admin", self.endpoint)
        self.assertIn("request.content_length", self.endpoint)
        self.assertIn("parse_documents_isolated(items)", self.endpoint)
        self.assertIn("try_acquire_parse_slot()", self.endpoint)
        self.assertIn('response.headers["Retry-After"]', self.endpoint)

    def test_private_file_details_are_not_logged_or_returned(self):
        self.assertNotIn("upload.filename", self.endpoint.split("except DocumentParseError", 1)[1])
        self.assertIn('exc_info=False', self.endpoint)
        self.assertNotIn("documents.append({", self.endpoint)

    def test_frontend_posts_files_and_applies_occ_and_adr_immediately(self):
        self.assertIn('fetch("/api/analysis/operation-upload"', self.frontend)
        self.assertIn('form.append("files", file)', self.frontend)
        self.assertIn('$("operationOcc").value = appliedOcc', self.frontend)
        self.assertIn('$("operationAdr").value = Math.round(result.adr)', self.frontend)
        self.assertIn("result.occupancy_days", self.frontend)
        self.assertIn("sold / (rooms * days) * 10000", self.frontend)
        self.assertIn("OCC 계산 불가", self.frontend)
        self.assertIn("renderChart();", self.frontend)

    def test_one_frontend_owns_operation_rendering_and_upload_events(self):
        self.assertNotIn("function renderOperation(", self.legacy_frontend)
        self.assertNotIn("analyzeOperationFiles", self.legacy_frontend)
        self.assertNotIn('$("operationFiles").onchange', self.legacy_frontend)
        self.assertIn('addEventListener("change", function () { analyzeFiles(this.files); })', self.frontend)
        self.assertIn("window.__operationAnalysisState", self.frontend)


if __name__ == "__main__":
    unittest.main()