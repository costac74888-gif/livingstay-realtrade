from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    script = (ROOT / "static/js/analysis-print.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/analysis.css").read_text(encoding="utf-8")
    required_script = [
        "function operationReport()",
        "window.__operationAnalysisState",
        '"#operationChartCard","#operationChart"',
        '"operationSensitivity"',
        '"operationBasisDetails"',
        '"operationTopDetails"',
        '"operationBuildingDetails"',
        '"#operationCoreMetrics .metric-card',
        "월세 손익분기 OCC",
        "운영경비율",
        "위탁수수료율",
        "비교 기준·자료 출처",
        '[["적용 객실"',
        '<b>비교지역</b>',
    ]
    required_css = [
        '#printReport[data-mode="operation"] .print-side-metrics',
        '#printReport[data-mode="operation"] .print-graph .operation-quadrant',
    ]
    missing = [token for token in required_script if token not in script]
    missing += [token for token in required_css if token not in css]
    if missing:
        raise AssertionError(f"운영보고서 품질 보완 누락: {missing}")
    print("operation print report quality checks passed")


if __name__ == "__main__":
    main()