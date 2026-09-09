from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    script = (ROOT / "static/js/analysis-print.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/analysis.css").read_text(encoding="utf-8")
    required_script = [
        '"#operationDetail .detail-address"',
        "운영분석 완료",
        '"지역 평균 대비 ADR "',
        '["지역 평균 ADR"',
        '["지역 평균 OCC"',
        "normalizeOperation:true",
        "normalizeOperation:true",
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