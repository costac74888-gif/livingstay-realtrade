from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    js = (ROOT / "static/js/analysis-print.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/analysis.css").read_text(encoding="utf-8")
    html = (ROOT / "static/analysis.html").read_text(encoding="utf-8")
    required_js = [
        "function kstTimestamp(value)",
        "function kstDay(value)",
        "Intl.DateTimeFormat",
        'timeZone:"Asia/Seoul"',
        "function scalePrintQuadrants(html,width,height)",
        'if(!node.closest(".positioning-toggle"))node.remove()',
        "scalePrintQuadrants(report.graph,1120,500)",
        "scalePrintQuadrants(report.graph,1120,560)",
        "scalePrintQuadrants(report.graph,1120,650)",
        "annualYield=numeric(\"annualYield\")",
        "numeric(\"annualHoldingCosts\")",
        "numeric(\"acquisitionCosts\")",
        "numeric(\"investmentBasis\")",
        "오전|오후",
        "UTC|GMT",
        "function correctRentalReport(report)",
        'report.graphTitle="3.1 임대수익 포지션"',
        'window.__analysisPrintChartCapture=true',
        'report.graph=graph.firstElementChild?graph.firstElementChild.outerHTML:report.graph',
        'report.graphTitle="3.1 ADR × OCC 포지션 · 등수익 곡선"',
        "면적 미선택",
        "공실·보유비용·대출이자 반영 현금흐름 기준",
        "function correctOperationReport(report)",
        "연 수익률은 임대수익분석과 같은 기준(보유비용 차감, 취득부대 포함)입니다.",
        "월세 대비",
        "print-operation-yield-note",
        "function formatMoneyText(value)",
    ]
    required_css = [
        '#printReport[data-mode="rental"] .print-rental-position',
        '#printReport[data-mode="rental"] .print-side-summary',
        "positioning-copy h3{font-size:14px!important}",
        "positioning-copy p{font-size:10px!important",
        ".print-operation-yield-note{font-size:6pt",
        ".operation-chart-explanation{font-size:10px!important",
        "grid-template-rows:24mm 48mm 165mm",
        '.print-rental-position .rental-positioning{background:#f4fbf8!important',
        '.print-basis .formula{font-size:9px!important;line-height:1.35!important',
    ]
    missing = [token for token in required_js if token not in js]
    missing += [token for token in required_css if token not in css]
    if '#printReport[data-mode="rental"] .print-rental-position .positioning-toggle{display:none}' in css:
        missing.append("임대 포지셔닝 선택 토글 인쇄 숨김 규칙")
    rental_print = js.split("correctRentalReport=function(report){")[-1].split(
        "correctOperationReport=function(report){", 1
    )[0]
    if 'report.graph=\'<div class="print-rental-position">\'+chartSnapshot(' not in rental_print:
        missing.append("임대 인쇄 그래프에 민감도 카드 미포함")
    operation_print = js.split("correctOperationReport=function(report){")[-1].split(
        "propertyReport=function()", 1
    )[0]
    if "report.graph=graph.firstElementChild?graph.firstElementChild.outerHTML:report.graph" not in operation_print:
        missing.append("숙박 인쇄 그래프에 민감도 카드 미포함")
    if html.count('class="print-page"') != 1 or '@page{size:A4 portrait' not in css:
        missing.append("A4 1페이지 인쇄 프레임 계약")
    if missing:
        raise AssertionError(f"분석 보고서 세부 표시 계약 누락: {missing}")
    print("analysis print detail checks passed")


if __name__ == "__main__":
    main()