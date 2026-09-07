import unittest
from pathlib import Path


class AnalysisTransientRetryTest(unittest.TestCase):
    def test_analysis_retries_transient_http_and_network_failures_once(self):
        source = Path("static/js/analysis.js").read_text(encoding="utf-8")
        self.assertIn("async function fetchAnalysis(url)", source)
        self.assertIn("[429,502,503,504].indexOf(res.status)>=0", source)
        self.assertIn("for(var attempt=0;attempt<2;attempt++)", source)
        self.assertIn(
            'fetchAnalysis("/api/analysis/assets?"+q.toString())',
            source,
        )
        self.assertIn('console.error("[투자분석] 자료 로딩 실패",e)', source)

    def test_analysis_chart_library_is_bundled_in_the_frontend_release(self):
        html = Path("static/analysis.html").read_text(encoding="utf-8")
        build = Path("scripts/build_frontend.py").read_text(encoding="utf-8")
        self.assertIn('src="/vendor/chart.umd.js?v=4.4.4"', html)
        self.assertNotIn("cdn.jsdelivr.net/npm/chart.js", html)
        self.assertIn('ROOT / "node_modules" / "chart.js"', build)
        self.assertIn('stage / "js" / "chart.umd.min.js"', build)

    def test_source_html_chart_fallback_is_served_locally(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn('@app.route("/vendor/chart.umd.js")', app_source)
        self.assertIn('"node_modules", "chart.js", "dist", "chart.umd.js"', app_source)

    def test_chart_style_callbacks_accept_chartjs_empty_context(self):
        source = Path("static/js/analysis.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("c.raw&&c.raw.item"), 3)
        self.assertIn("if(!i)return 0", source)
        self.assertIn('if(!i)return"#758596"', source)
        self.assertIn("return i&&i.is_representative?2.5:1.5", source)


if __name__ == "__main__":
    unittest.main()