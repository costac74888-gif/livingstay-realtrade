const fs = require("fs");

const html = fs.readFileSync("static/analysis.html", "utf8");
const js = fs.readFileSync("static/js/analysis.js", "utf8");
const operationJs = fs.readFileSync("static/js/operation-analysis.js", "utf8");
const css = fs.readFileSync("static/css/analysis.css", "utf8");
const mobileCss = fs.readFileSync("static/css/analysis-mobile.css", "utf8");
const chartCss = fs.readFileSync("static/css/analysis-chart-fixes.css", "utf8");
const menu = fs.readFileSync("static/menu.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(
  html.indexOf('class="reading-note"') < html.indexOf('class="analysis-heading"'),
  "자료 읽는 법이 분석 화면 맨 위에 배치되지 않았습니다.",
);
expect(
  js.includes("슈퍼 에셋") && js.includes("가격 선행과열")
    && js.includes("침체·약세") && js.includes("저평가 알짜")
    && js.includes("해당 사분면 설명"),
  "우측 패널의 사분면별 평가와 설명이 없습니다.",
);
expect(
  css.includes(".q-top-left") && css.includes(".q-top-right")
    && css.includes(".q-bottom-left") && css.includes(".q-bottom-right"),
  "사분면별 컬러 배경이 없습니다.",
);
expect(
  mobileCss.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"),
  "모바일 분석 조건이 2열로 배치되지 않았습니다.",
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
  js.includes("pointRadius") && js.includes("?10:sameRegion(i)?5.5:i.is_representative?8:c.raw.incomplete?4.5:4")
    && css.includes(".selected-pulse") && css.includes("@keyframes selectedAssetPulse"),
  "선택 건물 점의 두 배 강조와 점멸 효과가 없습니다.",
);
expect(
  html.includes("주요 단지") && html.includes('id="regionBaseline"')
    && js.includes("sameRegion") && js.includes('sameRegion(i)?"#168f91"')
    && css.includes(".legend-nearby") && css.includes(".legend-other"),
  "선택 건물의 시군구 비교 강조 또는 범례가 없습니다.",
);
expect(
  html.includes('id="quadTopLeft"') && html.includes('id="quadBottomLeft"')
    && chartCss.includes(".q-top-right")
    && chartCss.includes("padding-left: 17px"),
  "②·③ 설명 유지 또는 ①·④의 그래프 우측 빈 공간 이동이 반영되지 않았습니다.",
);
expect(
  js.includes("place(quadrants[0],0,0,xp,yp)")
    && js.includes("place(quadrants[1],xp,0,c.width-xp,yp)")
    && js.includes("place(quadrants[3],xp,yp,c.width-xp,c.height-yp)"),
  "사분면 배경 경계가 실제 중앙 기준선 위치를 따르지 않습니다.",
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
expect(menu.includes('href="/analysis">📊 자산분석</a>'), "모바일 전체 메뉴에 📊 자산분석 링크가 없습니다.");
expect(
  fs.readFileSync("static/js/header.js", "utf8").includes('<span class="hnav-label">📊 자산분석</span>'),
  "PC 상단 메뉴에 📊 자산분석 링크가 없습니다.",
);
expect(
  html.includes('id="quickBuildings"') && js.includes("/api/favorites/mine")
    && js.includes('"hs_recent_buildings"'),
  "관심단지 또는 최근 조회 건물 바로가기가 없습니다.",
);
expect(
  html.includes("가격 선행 지역") && html.includes("기타 단지")
    && js.includes('sameRegion(i)?"#168f91"')
    && js.includes("i.is_representative?8:c.raw.incomplete?4.5:4")
    && js.includes("representativeLabelsPlugin"),
  "사분면 설명 또는 지역·대표 표본 색상 구분이 없습니다.",
);
expect(
  js.includes("loadSeq") && js.includes("if(seq!==loadSeq)return")
    && html.includes('id="quadTopLeft"') && js.includes("quadrantGuide")
    && js.includes("가격변동은 비교 기준보다 높지만 관광수요 지수는 낮은 구간"),
  "연속 선택의 오래된 응답 차단 또는 비교축별 사분면 설명이 없습니다.",
);
expect(
  js.includes("baselineX=growth?0") && js.includes('textContent=growth?"0%"')
    && js.includes("__analysisChartLayout") && js.includes("candidates.find"),
  "모바일 실렌더링 검증용 0% 기준선 또는 대표 라벨 충돌 회피 계약이 없습니다.",
);
expect(
  js.includes('id="transactionsBtn"') && js.includes("#txTableWrap")
    && js.includes("실거래 전부보기") && css.includes("repeat(4,minmax(0,1fr))"),
  "상세·실거래·인쇄·공유 4개 버튼이 나란히 배치되지 않았습니다.",
);
expect(
  html.includes("② 가격 선행 지역") && html.includes("(관광 감소 / 가격 상승)")
    && html.includes("관광 수요는 줄지만 가격이 높은 지역")
    && html.includes("① 슈퍼 에셋 지역") && html.includes("관광과 시세가 함께 상승하는 우수 지역")
    && html.includes("③ 침체 구역") && html.includes("관광 수요와 가격이 모두 하락한 지역")
    && html.includes("④ 저평가 알짜 지역") && html.includes("관광객은 늘지만 가격이 아직 저렴한 지역"),
  "첨부 기준의 사분면 문구가 그대로 반영되지 않았습니다.",
);
expect(
  html.includes("추천 단지 TOP 5") && html.includes("④</i> 저평가 알짜 지역 중심")
    && html.includes('id="recommendationRows"') && js.includes("renderRecommendations")
    && js.includes('i.quadrant==="저평가 알짜"') && js.includes("demandBase")
    && js.includes('growth==null?"자료 부족"'),
  "저평가 알짜 중심 추천 단지 TOP 5가 없습니다.",
);
expect(
  js.includes("if(loadSeq===0&&!state.payload)load()")
    && js.includes("기존 분석 유지 · 갱신 실패"),
  "초기 중복 요청 차단 또는 후속 갱신 실패 시 정상 화면 보존이 없습니다.",
);
expect(
  js.includes("incomplete=tourism==null||price==null")
    && js.includes("priceDisplayCap") && js.includes("Math.abs(price)>priceDisplayCap")
    && js.includes('String(i.building_id)===String(state.selected)')
    && js.includes('if(c.raw.incomplete)return c.raw.displayOnly?"#b8c1ca":"#758596"')
    && js.includes('points[idx].incomplete?"#758596"')
    && js.includes("displayOffset(i.building_id")
    && js.includes("displayOnly=tourism==null&&price==null"),
  "비교기간이 부족한 건물의 회색 분산 표시가 없습니다.",
);
expect(
  js.includes('priceOnly=true') && js.includes("가격 저평가 후보")
    && js.includes("비교 가능한 가격·관광 자료가 없습니다"),
  "관광자료 전체 부족 시 차트와 추천표가 모두 비는 것을 막는 보조 표시가 없습니다.",
);
expect(
  html.includes('id="propertyTab"') && html.includes('id="operationTab"')
    && html.includes('id="rentalTab"')
    && html.indexOf("부동산투자분석") < html.indexOf("임대수익분석")
    && html.indexOf("임대수익분석") < html.indexOf("숙박운영분석")
    && html.includes('id="operationInputs"') && html.includes('id="operationChart"')
    && js.includes("lodging_room_total") && js.includes("operationBenchmarks")
    && html.includes('id="operationLodging"') && html.includes('id="operationRoomCountInput"')
    && html.includes('id="operationBusinessName"')
    && html.includes('id="buildingSelectionApply"') && html.includes('id="buildingSelectionStatus"')
    && html.includes('id="buildingSelectionClear"') && html.includes('id="analysisResetAll"')
    && js.includes("applyBuildingSelection") && js.includes("pendingBuilding")
    && html.includes('id="operationSelectedPulse"')
    && operationJs.includes("regionalBaseline()") && operationJs.includes("officialRooms")
    && operationJs.includes("building.display_building_name || building.building_name")
    && operationJs.includes("comparisonPoints: benchmarks.length")
    && html.includes('id="operationAdrBaseline"') && html.includes("운영분석 산정근거")
    && html.includes("해당 지역 우수 숙박 운영지표 TOP 5"),
  "부동산분석 다음 운영분석 탭 또는 운영 포지셔닝 화면이 없습니다.",
);
expect(
  html.includes('id="tableMoreBtn"')
    && js.includes("tableLimit:10")
    && js.includes("list.slice(0,state.tableLimit)")
    && html.indexOf('id="methodology"') < html.indexOf('id="summaryGrid"')
    && !html.includes('id="rentalBuildingAddress"'),
  "건물 목록 10개·더보기, 하단 산출 숫자 또는 임대분석 주소 제거가 반영되지 않았습니다.",
);
expect(
  html.includes("<h1>홈앤스테이 숙박자산 분석</h1>")
    && html.includes("부동산투자·임대수익·숙박운영을 함께 분석합니다.")
    && !html.includes("홈앤스테이 숙박자산 지도"),
  "상단 소개 문구가 세 가지 숙박자산 분석을 반영하지 않습니다.",
);
expect(
  html.includes('id="rentalPurchasePrice"')
    && html.includes('id="rentalDeposit"')
    && html.includes('id="rentalMonthlyRent"')
    && html.includes('id="rentalMarketPriceHint"')
    && html.includes('id="rentalAcquisitionTax"')
    && html.includes('id="rentalBrokerFee"')
    && html.includes("취득세 등 (4.6%)")
    && html.includes("중개보수 (0.9%)")
    && html.includes('id="rentalPropertyTax"')
    && html.includes('id="rentalLoanAmount"')
    && html.includes('id="rentalLoanMethod"')
    && html.includes('id="rentalResults"'),
  "임대수익분석의 매입·임대·보유세·대출 입력란 또는 결과 영역이 없습니다.",
);
expect(
  html.includes("별도 승인 없이 바로 분석")
    && html.includes("실제 운영 기준에 맞게 수정")
    && !html.includes("식음 매출액")
    && js.includes("analyzeOperationFiles"),
  "신고 객실 자동 적용 또는 자기자료 즉시 분석 원칙이 반영되지 않았습니다.",
);

console.log("analysis frontend contract checks passed");