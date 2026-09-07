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
        self.assertIn('src="/static/vendor/chart.umd.js"', html)
        self.assertNotIn("cdn.jsdelivr.net/npm/chart.js", html)
        self.assertIn('ROOT / "node_modules" / "chart.js"', build)
        self.assertIn('stage / "js" / "chart.umd.min.js"', build)


if __name__ == "__main__":
    unittest.main()