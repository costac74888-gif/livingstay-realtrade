const fs = require("fs");

const html = fs.readFileSync("static/analysis.html", "utf8");
const js = fs.readFileSync("static/js/analysis.js", "utf8");
const css = fs.readFileSync("static/css/analysis.css", "utf8");
const menu = fs.readFileSync("static/menu.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(
  html.indexOf('class="reading-note"') < html.indexOf('class="analysis-heading"'),
  "자료 읽는 법이 분석 화면 맨 위에 배치되지 않았습니다.",
);
expect(
  html.includes("슈퍼 에셋") && html.includes("가격 선행 지역")
    && html.includes("침체·약세") && html.includes("저평가 알짜"),
  "사분면별 평가와 설명이 없습니다.",
);
expect(
  css.includes(".q-top-left") && css.includes(".q-top-right")
    && css.includes(".q-bottom-left") && css.includes(".q-bottom-right"),
  "사분면별 컬러 배경이 없습니다.",
);
expect(
  js.includes("/api/analysis/building-search?q=")
    && js.includes("주소는 건물 구분을 위한 보조 정보")
    && js.includes("검색 결과가 없습니다")
    && js.includes("임의의 다른 건물로 분석하지 않으니"),
  "건물명 우선 검색 또는 명확한 검색 실패 안내가 없습니다.",
);
expect(
  js.includes("res.status===401") && js.includes("livingstayOpenLogin"),
  "분석 화면 로그인 필수 흐름이 없습니다.",
);
expect(
  js.includes("analysis_sample_transaction_count")
    && js.includes("transaction_start_date")
    && js.includes("확인 실거래"),
  "전체 실거래와 분석 표본 거래가 분리되지 않았습니다.",
);
expect(
  js.includes("pointRadius") && js.includes("?10:sameRegion(i)?6:4.5")
    && css.includes(".selected-pulse") && css.includes("@keyframes selectedAssetPulse"),
  "선택 건물 점의 두 배 강조와 점멸 효과가 없습니다.",
);
expect(
  html.includes("같은 시군구") && html.includes('id="regionBaseline"')
    && js.includes("sameRegion") && js.includes('"#b9c2cc"')
    && css.includes(".legend-nearby") && css.includes(".legend-other"),
  "선택 건물의 시군구 비교 강조 또는 범례가 없습니다.",
);
expect(
  css.includes(".q-top-left{padding-left:82px")
    && css.includes(".q-bottom-left{padding-left:82px"),
  "왼쪽 사분면 설명이 Y축 눈금 밖의 그래프 안쪽에 배치되지 않았습니다.",
);
expect(
  js.includes("window.print()") && js.includes("navigator.share")
    && js.includes('location.origin+"/analysis?building_id="')
    && css.includes("@media print"),
  "한 장 보고서 출력 또는 홈앤스테이 분석 링크 공유 기능이 없습니다.",
);
expect(
  js.includes("/photos") && js.includes("/streetview?view=building-v6")
    && html.includes("가격변동률 =")
    && html.includes("사분면 기준선 ="),
  "건물 사진 또는 보고서 산정 근거가 없습니다.",
);
expect(menu.includes('href="/analysis"'), "모바일 전체 메뉴에 투자분석 링크가 없습니다.");

console.log("analysis frontend contract checks passed");