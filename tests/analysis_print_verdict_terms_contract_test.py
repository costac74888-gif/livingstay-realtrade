from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    script = (ROOT / "static/js/analysis-print.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/analysis.css").read_text(encoding="utf-8")
    html = (ROOT / "static/analysis.html").read_text(encoding="utf-8")

    required_script = [
        "function updateRentalPrintSummary(report)",
        "function updateOperationPrintSummary(report)",
        '<small>임대수익 평가</small><strong>',
        '<small>숙박운영 평가</small><strong>',
        "print-evidence-line",
        "#rentalVerdict strong",
        '"숙박위탁 유리"',
        '"장기임대 유리"',
        "window.livingstayAnalysisTerms",
        'if(!terms||typeof terms.expand!=="function")throw Error(',
        "terms.expand(node.nodeValue,{seen:context.seen})",
        "new Set()",
        "function expandPrintTerms(element)",
        '["printReportTitle","printReportTypes","printReportLegend","printOverview","printGraphTitle","printGraph","printBasis","printSideTitle","printTransactionTrend","printTransactionTable"]',
    ]
    required_css = [
        ".print-result-line .print-evidence-line",
        ".print-result-line.print-verdict-positive strong",
        ".print-result-line.print-verdict-caution strong",
        ".print-result-line.print-verdict-pending strong",
        "font-size:20px!important",
        "font-size:10px!important;line-height:1.4!important",
    ]
    missing = [token for token in required_script if token not in script]
    missing += [token for token in required_css if token not in css]
    if "printTermFallbacks" in script or "function printTermLabel" in script:
        missing.append("중복된 인쇄 전용 용어 사전")
    if html.count('class="print-page"') != 1 or "@page{size:A4 portrait" not in css:
        missing.append("기존 A4 1페이지 인쇄 프레임")
    if missing:
        raise AssertionError(f"인쇄 평가요약·전문용어 계약 누락: {missing}")
    print("analysis print verdict and terms checks passed")


if __name__ == "__main__":
    main()