const fs = require("fs");

const html = fs.readFileSync("static/analysis.html", "utf8");
const js = fs.readFileSync("static/js/analysis.js", "utf8");
const operationJs = fs.readFileSync("static/js/operation-analysis.js", "utf8");
const rentalJs = fs.readFileSync("static/js/rental-analysis.js", "utf8");
const css = fs.readFileSync("static/css/analysis.css", "utf8");
const mobileCss = fs.readFileSync("static/css/analysis-mobile.css", "utf8");
const chartCss = fs.readFileSync("static/css/analysis-chart-fixes.css", "utf8");
const menu = fs.readFileSync("static/menu.html", "utf8");
const printJs = fs.readFileSync("static/js/analysis-print.js", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(
  html.indexOf('class="reading-note analysis-guide"') < html.indexOf('class="analysis-heading"'),
  "세 가지 분석 안내가 분석 화면 맨 위에 배치되지 않았습니다.",
);
expect(
  html.includes('id="rentalReportActions"')
    && operationJs.includes('id="operationReportActions"')
    && js.includes("livingstayAnalysisReportActions")
    && printJs.includes('mode==="rental"') && printJs.includes("임대조건 요약")
    && printJs.includes("운영 핵심지표")
    && operationJs.includes("quadrantBoxes")
    && operationJs.includes("operation-empty-actions"),
  "세 분석의 공통 상세·실거래·인쇄·공유 버튼 또는 분석별 한 장 보고서 구성이 없습니다.",
);
expect(
  html.includes('id="transactionTrendChart"') && html.includes('id="printTransactionTable"')
    && html.indexOf('id="selectedTransactionCard"') > html.indexOf('id="transactionTrendCard"')
    && html.indexOf('id="selectedTransactionCard"') < html.indexOf('id="recommendationCard"')
    && js.includes("renderSelectedTransactions") && js.includes("selectedTransactionRows")
    && html.includes('id="transactionAreaSelect"') && js.includes("allTransactions:transactions")
    && js.includes('label:"평균 거래금액(만원)"') && js.includes("spanGaps:true")
    && js.includes('y:{position:"left",beginAtZero:true') && js.includes('y1:{position:"right",beginAtZero:true')
    && printJs.includes("<th>층</th><th>거래금액</th>")
    && js.includes("Number(tx.price)") && js.includes("transactionTrendChart=new Chart")
    && printJs.includes("printFilename") && printJs.includes('toLocaleDateString("sv-SE")')
    && printJs.includes('"홈앤스테이_"+name+"_"+day+"_부동산투자보고서"')
    && printJs.includes("print-map-preparing") && printJs.includes("map.relayout")
    && printJs.includes("print-map-property-point") && css.includes(".print-map-property-point")
    && css.includes(".print-map-preparing #printMap")
    && printJs.includes("livingstayPrintAnalysisReport") && css.includes("writing-mode:vertical-rl"),
  "화면·인쇄 실거래 그래프, 최근 거래표 또는 건물명·날짜 출력 파일명이 없습니다.",
);
expect(
  html.indexOf('id="transactionTrendCard"') < html.indexOf('id="detailCard"')
    && css.includes('grid-template-areas:"position detail" "trend detail"')
    && css.includes('grid-template-areas:"position" "detail" "trend"'),
  "데스크톱 실거래 추이 그래프가 포지셔닝 그래프 아래 왼쪽 열에 배치되지 않았습니다.",
);
expect(
  html.includes("세 가지 분석 한눈에 보기")
    && html.includes("관광수요와 유사자산 가격으로 투자 매력을 확인합니다.")
    && html.includes("월세·비용·대출을 반영한 실제 수익을 확인합니다.")
    && html.includes("객실가격과 판매율로 숙박 운영성과를 확인합니다."),
  "최상단에 세 가지 분석의 제목과 쉬운 의미가 모두 표시되지 않았습니다.",
);
expect(
  js.includes("수요 프리미엄") && js.includes("가격 부담")
    && js.includes("저가·수요 확인 필요") && js.includes("수요 대비 저평가 후보")
    && js.includes("현재 수요·상대가격 위치"),
  "우측 패널의 사분면별 평가와 설명이 없습니다.",
);
expect(
  css.includes(".q-top-left") && css.includes(".q-top-right")
    && css.includes(".q-bottom-left") && css.includes(".q-bottom-right"),
  "사분면별 컬러 배경이 없습니다.",
);
expect(
  !html.includes('id="analysisFilter"')
    && !html.includes('id="selType"')
    && !html.includes('id="selPeriod"')
    && html.includes("선택 건물의 숙박유형을 자동 적용")
    && html.includes("가격 비교기간 = 최근 12개월 고정")
    && html.includes("관광 기준 = 관광수요 지수 고정"),
  "중복 조건 입력 제거 또는 자동 적용 산출근거가 반영되지 않았습니다.",
);
expect(
  js.includes("/api/analysis/building-search?q=")
    && js.includes("주소는 건물 구분을 위한 보조 정보")
    && js.includes("검색 결과가 없습니다")
    && js.includes("임의 가격을 만들지 않으니"),
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
  html.includes("같은 시군구") && html.includes('id="regionBaseline"')
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
  html.includes('id="printReportSerial"') && html.includes('id="printMap"')
    && html.includes("3.3 지도위치") && html.includes("주의사항")
    && html.includes("/static/home_stay_report_logo.png")
    && printJs.includes('"tilesloaded"')
    && printJs.includes("pages:1")
    && printJs.includes("보고서 생성 일련번호") && printJs.includes("kakao.maps.Map")
    && printJs.includes("reportTypeMarkup(mode,true)") && printJs.includes('title:"부동산투자분석 보고서"'),
  "인쇄 보고서의 로고형 헤더, 일련번호, 실제 지도, 주의사항 또는 보고서 종류 설명이 없습니다.",
);
expect(
  js.includes("/photos") && js.includes("/streetview?view=building-v9")
    && html.includes("유사자산 대비 가격 =")
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
    && js.includes('"hs_recent_buildings"') && js.includes("viewed_at:Date.now()")
    && js.includes("favorites.slice(0,3)") && js.includes("+더보기(")
    && js.includes('window.addEventListener("storage"')
    && js.includes('window.addEventListener("pageshow"'),
  "관심단지 또는 최근 조회가 홈 지도 검색영역과 같은 기준으로 동기화되지 않았습니다.",
);
expect(
  html.includes('id="rentalBuildingIdentity"')
    && html.includes('id="operationBuildingIdentity"')
    && js.includes("livingstayRenderAnalysisBuildingIdentity")
    && js.includes('"/photos",{credentials:"same-origin"}')
    && js.includes('"/streetview?view=building-v9"')
    && rentalJs.includes('livingstayRenderAnalysisBuildingIdentity($("rentalBuildingIdentity"), data)')
    && operationJs.includes('livingstayRenderAnalysisBuildingIdentity($("operationBuildingIdentity"), building)')
    && css.includes(".analysis-building-identity"),
  "임대수익·숙박운영분석에 선택 건물 사진·주소 안내가 없습니다.",
);
expect(
  html.includes("가격 부담") && html.includes("기타 단지")
    && js.includes('sameRegion(i)?"#168f91"')
    && js.includes("i.is_representative?8:c.raw.incomplete?4.5:4")
    && js.includes("representativeLabelsPlugin"),
  "사분면 설명 또는 지역·대표 표본 색상 구분이 없습니다.",
);
expect(
  js.includes("loadSeq") && js.includes("if(seq!==loadSeq)return")
    && html.includes('id="quadTopLeft"') && js.includes("quadrantGuide")
    && js.includes("관광수요는 낮지만 유사자산보다 가격이 높은 구간"),
  "연속 선택의 오래된 응답 차단 또는 비교축별 사분면 설명이 없습니다.",
);
expect(
  js.includes("baselineX=n(x.tourism_demand_index)") && js.includes("baselineY=symlog(x.peer_price_gap)")
    && js.includes("__analysisChartLayout") && js.includes("candidates.find"),
  "모바일 실렌더링 검증용 0% 기준선 또는 대표 라벨 충돌 회피 계약이 없습니다.",
);
expect(
  js.includes('id="favoriteBtn"') && js.includes('data-report-action="favorite"')
    && js.includes("관심저장") && js.includes("/api/favorites/mine")
    && css.includes("repeat(4,minmax(0,1fr))"),
  "세 분석의 상세·관심저장·인쇄·공유 4개 버튼이 나란히 배치되지 않았습니다.",
);
expect(
  html.includes("③ 가격 부담") && html.includes("(관광수요 낮음 / 가격 높음)")
    && html.includes("② 수요 프리미엄") && html.includes("강한 관광수요가 가격에 반영된 구간")
    && html.includes("④ 저가·수요 확인 필요")
    && html.includes("① 수요 대비 저평가 후보"),
  "검증된 관광수요·유사자산 가격 사분면 문구가 반영되지 않았습니다.",
);
expect(
  html.includes("가격 매력 후보 TOP 5") && html.includes("①</i> 수요 대비 저평가 후보 중심")
    && html.includes('id="recommendationRows"') && html.includes('id="recommendationSort"')
    && html.includes('id="recommendationSortAsc"') && html.includes('id="recommendationSortDesc"')
    && js.includes("recommendationSort") && js.includes("recommendationDir")
    && js.includes("renderRecommendations")
    && js.includes('i.quadrant==="수요 대비 저평가 후보"')
    && js.includes("peer_price_gap")
    && js.includes('class="recommendation-building-link"')
    && js.includes('detailUrl="/building/"+encodeURIComponent(i.building_id)')
    && css.includes(".recommendation-building-link"),
  "수요 대비 저평가 후보 중심 TOP 5가 없습니다.",
);
expect(
  js.includes("loadSeq===0&&!state.payload")
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
  js.includes('i.quadrant==="수요 대비 저평가 후보"')
    && js.includes("관광수요가 높고 유사자산보다 가격이 낮은 후보가 없습니다"),
  "검증 기준에 맞는 가격 매력 후보의 빈 상태 안내가 없습니다.",
);
expect(
  html.includes('id="propertyTab"') && html.includes('id="operationTab"')
    && html.includes('id="rentalTab"')
    && html.indexOf("부동산투자분석") < html.indexOf("임대수익분석")
    && html.indexOf("임대수익분석") < html.indexOf("숙박운영분석")
    && html.includes('id="operationInputs"') && html.includes('id="operationChart"')
    && operationJs.includes("lodging_room_total") && operationJs.includes("benchmarks")
    && html.includes('id="operationLodging"') && html.includes('id="operationRoomCountInput"')
    && html.includes('id="operationBusinessName"')
    && html.includes('id="buildingSelectionApply"') && html.includes('id="buildingSelectionStatus"')
    && html.includes('id="buildingSelectionClear"') && html.includes('id="analysisResetAll"')
    && js.includes("applyBuildingSelection") && js.includes("pendingBuilding")
    && html.includes('id="operationSelectedPulse"')
    && html.includes("장기임대(월세)인 경우에는 ‘임대수익분석’을 활용하세요.")
    && html.includes('id="operationRentalGuide"')
    && js.includes('$("operationRentalGuide").onclick=function(){setAnalysisMode("rental")}')
    && operationJs.includes("regionalBaseline()") && operationJs.includes("officialRooms")
    && operationJs.includes("building.display_building_name || building.building_name")
    && operationJs.includes("comparisonPoints: benchmarks.length")
    && html.includes('id="operationAdrBaseline"') && html.includes("운영분석 산정근거")
    && html.includes("[가상 산정 예시] A 생활숙박시설")
    && html.includes("Percentile Rank·백분위 순위")
    && html.includes("[가상 산정 예시] B 숙박시설의 30일 운영실적")
    && html.includes("Revenue per Available Room·판매가능객실당매출")
    && html.includes("해당 지역 우수 숙박 운영지표 TOP 5"),
  "부동산분석 다음 운영분석 탭 또는 운영 포지셔닝 화면이 없습니다.",
);
expect(
  !html.includes('data-sort="address"')
    && html.includes('id="tableExpandBtn"')
    && js.includes("tableExpanded:false")
    && js.includes("updateTableVisibility")
    && js.includes("rows.length-10")
    && js.includes("index>=10")
    && js.includes('"목록 접기"')
    && html.indexOf('id="methodology"') < html.indexOf('id="summaryGrid"')
    && !html.includes('id="rentalBuildingAddress"'),
  "건물 비교표 주소 제거·10개 펼침/접기, 하단 산출 숫자 또는 임대분석 주소 제거가 반영되지 않았습니다.",
);
expect(
  html.includes("<h1>홈앤스테이 숙박자산 분석</h1>")
    && html.includes("부동산투자·임대수익·숙박운영을 함께 분석합니다.")
    && !html.includes("홈앤스테이 숙박자산 지도"),
  "상단 소개 문구가 세 가지 숙박자산 분석을 반영하지 않습니다.",
);
expect(
  html.includes('id="rentalPurchasePrice"')
    && html.includes('id="rentalUnitArea"')
    && html.includes('id="rentalUnitAreaOptions"')
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
  rentalJs.includes("/api/analysis/rental-market-price")
    && rentalJs.includes("/area-types")
    && rentalJs.includes("표본 ")
    && rentalJs.includes("사용자 수정값 사용 중")
    && rentalJs.includes("result.match_type"),
  "선택 면적의 최근 실거래 중앙값·표본 근거 또는 자동값/수정값 구분이 없습니다.",
);
expect(
  html.includes("별도 승인 없이 바로 분석")
    && html.includes("실제 운영 기준에 맞게 수정")
    && !html.includes("식음 매출액")
    && operationJs.includes("analyzeFiles")
    && operationJs.includes("/api/analysis/operation-upload")
    && !js.includes("analyzeOperationFiles"),
  "신고 객실 자동 적용 또는 자기자료 즉시 분석 원칙이 반영되지 않았습니다.",
);

console.log("analysis frontend contract checks passed");
