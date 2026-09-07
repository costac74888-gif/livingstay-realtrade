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


if __name__ == "__main__":
    unittest.main()