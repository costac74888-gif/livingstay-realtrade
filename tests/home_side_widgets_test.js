// 홈 검색영역·좌측 패널의 최근검색/데이터랩 구성을 검증한다.
const fs = require("fs");
const path = require("path");

const index = fs.readFileSync(path.join(__dirname, "..", "static", "index.html"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "static", "css", "main.css"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const recentStart = index.indexOf('id="recentRow"');
const favChipsStart = index.indexOf('id="favChips"');
const sidePanelStart = index.indexOf('<aside class="side-panel">');
expect(
  recentStart > favChipsStart && recentStart < sidePanelStart,
  "최근검색이 관심단지 칩 바로 아래 검색영역에 있지 않습니다."
);
const recentSection = index.slice(recentStart, sidePanelStart);
expect(index.includes('class="recent-search-row" id="recentRow"'), "최근검색이 독립 카드가 아닌 보조 칩 행이 아닙니다.");
expect(recentSection.includes('class="recent-search-chips"'), "최근검색 칩 컨테이너가 없습니다.");
expect(!index.includes("최근 관심물건"), "최근 관심물건 위젯이 홈 마크업에 남아 있습니다.");
expect(!index.includes('id="sideFavList"'), "최근 관심물건 위젯의 목록 컨테이너가 남아 있습니다.");
expect(!index.includes('id="sideRankingCard"'), "거래량 TOP 별도 위젯이 데이터랩 편입 후에도 남아 있습니다.");
expect(index.includes('id="dataLabCard"'), "데이터랩 컨테이너가 없습니다.");
["lodging", "volume", "change", "highest", "consign", "closure"].forEach((key) => {
  expect(index.includes(`data-datalab-key="${key}"`), `데이터랩 ${key} 항목이 없습니다.`);
});
const tabKeys = [...index.matchAll(/data-datalab-key="([^"]+)"/g)].map((match) => match[1]);
expect(
  tabKeys.join(",") === "lodging,volume,change,highest,consign,closure",
  "데이터랩 ⑤ 위탁현황·⑥ 폐업 현황 탭 순서가 아닙니다."
);
expect(index.includes("<span>위탁현황</span>") && !index.includes("영업신고율"),
  "데이터랩 ⑤ 탭 명칭이 위탁현황으로 교체되지 않았습니다.");

expect(main.includes('const HS_RECENT_KEY = "hs_recent_buildings"'), "최근검색 localStorage 키가 바뀌었습니다.");
expect(main.includes("function trackRecentBuilding"), "최근검색 기록 함수가 사라졌습니다.");
expect(main.includes("function renderRecentChips"), "최근검색 렌더링 함수가 사라졌습니다.");
expect(main.includes("renderRecentChips(); // 페이지 로드 시 최근 본 건물 칩 복원"),
  "페이지 로드 시 최근검색 복원 호출이 사라졌습니다.");

const sideFavoriteCallSites = main.match(/(?:^|[^\w])loadSideFavorites\s*\(/g) || [];
expect(sideFavoriteCallSites.length === 1 && main.includes("async function loadSideFavorites"),
  "관심물건 위젯 데이터 로드 호출부가 남아 있습니다.");
expect(main.includes("function loadDataLab"), "데이터랩 전환 로더가 없습니다.");
expect(
  index.indexOf('id="trendChart"') < index.indexOf('id="sideTxList"') &&
  index.indexOf('id="sideTxList"') < index.indexOf('id="dataLabNav"') &&
  index.indexOf('id="recentRow"') < index.indexOf('<aside class="side-panel">'),
  "홈 순서가 검색영역 최근검색 → 실거래추세 → 실거래목록 → 데이터랩이 아닙니다."
);
expect(
  main.includes('const HS_RECENT_MAX = 3') &&
  main.includes("list.slice(0, HS_RECENT_MAX)"),
  "최근검색 화면 표시 개수가 3개로 제한되지 않았습니다."
);
expect(
  css.includes("grid-template-columns:repeat(3,minmax(0,1fr))") &&
  css.includes(".datalab-content{min-width:0; min-height:210px; margin-top:10px;}") &&
  css.includes(".datalab-loading") &&
  css.includes(".datalab-error"),
  "데이터랩이 3열 탭 그리드와 탭 아래 콘텐츠 구조가 아닙니다."
);
expect(main.includes("/api/stats/price-change-top"), "가격변동 데이터랩 API 연결이 없습니다.");
expect(main.includes("data-datalab-price-order") && main.includes("최고</button>") && main.includes("최저</button>"),
  "데이터랩 최고가/최저가 토글이 없습니다.");
expect(main.includes("/api/stats/consign-by-sido"), "위탁현황 데이터랩 API 연결이 없습니다.");
expect(!main.includes("/api/stats/report-rate-by-sido") && !main.includes("function renderDataLabRate"),
  "구 영업신고율 데이터랩 연결 또는 렌더링이 남아 있습니다.");
const consignRender = main.slice(main.indexOf("function renderDataLabConsign"), main.indexOf("function setDataLabActive"));
expect(
  consignRender.includes("<th>시도</th><th>건물수</th><th>호실수</th><th>위탁업체수</th><th>위탁호실수</th><th>위탁비율</th>") &&
  consignRender.includes("<tfoot>") &&
  consignRender.includes("datalab-partial-badge") &&
  consignRender.includes("생활숙박시설 기준"),
  "위탁현황이 합계행 포함 단일 테이블로 렌더링되지 않았습니다."
);
expect(main.includes("dataLabFetchController"), "데이터랩 탭 전환 시 이전 요청 취소가 없습니다.");
expect(main.includes("DATA_LAB_CACHE_TTL_MS"), "데이터랩 반복 탭 전환 캐시가 없습니다.");
expect(main.includes("function moveDataLabBuildingToMap"), "데이터랩 건물명의 지도 이동 함수가 없습니다.");
expect(main.includes("data-datalab-lat") && main.includes("data-datalab-lng"),
  "데이터랩 건물 버튼에 지도 좌표가 연결되지 않았습니다.");
expect(main.includes("function showDataLabBuildingHighlight") &&
  main.includes("selectedDataLabOverlay") &&
  main.includes("datalab-map-highlight"),
  "데이터랩 선택 건물의 지도 강조 오버레이가 연결되지 않았습니다.");
expect(main.includes("clearDataLabBuildingHighlight") &&
  main.includes("selectedDataLabOverlay.setMap(null)"),
  "새 데이터랩 건물 선택 시 이전 지도 강조 오버레이 정리가 보장되지 않습니다.");
expect(main.includes('aria-pressed="${selected}"') &&
  main.includes("datalab-building-selected"),
  "데이터랩 선택 건물의 접근성·선택 상태 표시가 없습니다.");
expect(main.includes("지도 좌표 없음") && main.includes("datalab-building-disabled"),
  "지도 좌표가 없는 데이터랩 건물의 비활성 안내가 없습니다.");
const datalabClickBinding = main.slice(
  main.indexOf("function bindDataLabBuildingButtons"),
  main.indexOf("function dataLabRankList")
);
expect(!datalabClickBinding.includes("openBuildingDetail"),
  "데이터랩 건물 클릭이 지도 이동 대신 상세 패널을 열고 있습니다.");
expect(main.includes("<strong>⑤ 🏨 위탁현황</strong>") && main.includes("<strong>⑥ ⚫ 폐업 현황</strong>"),
  "데이터랩 콘텐츠의 위탁현황·폐업 현황 순서 또는 명칭이 맞지 않습니다.");
const closureRender = main.slice(main.indexOf("function renderDataLabClosure"), main.indexOf("function renderDataLabConsign"));
expect(closureRender.includes('class="datalab-region"') && !closureRender.includes('class="datalab-building"'),
  "폐업 현황 지역명이 건물명 강조 스타일을 사용하고 있습니다.");
expect(css.includes(".datalab-region") && css.includes("font-size:12px; font-weight:400"),
  "폐업 현황 지역명이 건물명 크기·일반 굵기로 지정되지 않았습니다.");
expect(main.includes("dataLabArea(item.area_sqm)"), "가격변동 데이터랩에 동일 전용면적 표시가 없습니다.");
expect(main.includes("<span class=\"datalab-caption\">현재수집 기준</span>"), "전국숙박업통계 캡션이 현재수집 기준이 아닙니다.");
expect(main.includes("<th>건물수</th><th>호실수</th><th>신고업체</th><th>신고호실</th><th>신고율</th>") &&
  !main.includes("영업신고업체</th>") &&
  !main.includes("영업신고호실</th>") &&
  !main.includes("영업신고율</th>"),
  "전국숙박업통계 헤더가 축약되지 않았습니다.");
expect(!main.includes("datalab-note") && !css.includes(".datalab-note") &&
  !main.includes("datalab-caption-bottom"),
  "데이터랩 하단 설명문이 남아 있습니다.");
expect(main.includes("<td>${escapeHtml(sub.type)}</td>") && !main.includes("└ ${escapeHtml(sub.type)}") &&
  !css.includes(".datalab-sub-name"),
  "숙박통계 서브행 들여쓰기가 남아 있습니다.");
expect(css.includes("--panel-w:440px") &&
  css.includes(".datalab-table{width:100%; min-width:260px;") &&
  css.includes(".datalab-table th{padding:6px 4px;") &&
  css.includes(".datalab-table td{padding:6px 4px;"),
  "데이터랩 패널·테이블 폭 축소 CSS가 반영되지 않았습니다.");
expect(!main.includes("row.favorites") && !main.includes("row.listing_requests"),
  "전국숙박업통계 렌더링에 내부 운영지표가 남아 있습니다.");

console.log("OK  홈 최근검색 위치·실거래추세·데이터랩 로딩·localStorage 회귀");