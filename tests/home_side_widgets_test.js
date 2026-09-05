// 홈 검색영역·좌측 패널의 최근검색/데이터랩 구성을 검증한다.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const index = fs.readFileSync(path.join(__dirname, "..", "static", "index.html"), "utf8");
const header = fs.readFileSync(path.join(__dirname, "..", "static", "js", "header.js"), "utf8");
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
expect(
  index.includes('id="btnTogglePanel"') &&
  index.includes('aria-expanded="true"') &&
  index.includes('data-lodging-type="관광" style="cursor:pointer;"><i style="background:#14B8A6;">') &&
  css.includes(".side-panel.panel-collapsed") &&
  css.includes("body:has(.side-panel.panel-collapsed) .map-list-toggle") &&
  header.includes("window.livingstaySetPanelToggle = setListToggleState") &&
  header.includes('panel.classList.toggle("panel-collapsed", !open)'),
  "데스크톱 좌측 패널 접기·펼치기 계약이 누락됐습니다."
);
expect(
  main.includes('"관광숙박업":           ["관광", LODGING_COLORS["관광"], "#fff"]') &&
  !main.includes('"관광숙박업":           ["관광", "#639922", "#fff"]'),
  "상세페이지 관광숙박 배지가 공용 청록 색상을 사용하지 않습니다."
);
const recentSection = index.slice(recentStart, sidePanelStart);
expect(index.includes('class="recent-search-row" id="recentRow"'), "최근검색이 독립 카드가 아닌 보조 칩 행이 아닙니다.");
expect(recentSection.includes('class="recent-search-chips"'), "최근검색 칩 컨테이너가 없습니다.");
expect(!index.includes("최근 관심물건"), "최근 관심물건 위젯이 홈 마크업에 남아 있습니다.");
expect(!index.includes('id="sideFavList"'), "최근 관심물건 위젯의 목록 컨테이너가 남아 있습니다.");
expect(!index.includes('id="sideRankingCard"'), "거래량 TOP 별도 위젯이 데이터랩 편입 후에도 남아 있습니다.");
expect(index.includes('id="dataLabCard"'), "데이터랩 컨테이너가 없습니다.");
[
  "lodging", "volume", "change", "highest", "consign", "closure",
  "tourism_domestic", "tourism_foreign", "tourism_consume",
].forEach((key) => {
  expect(index.includes(`data-datalab-key="${key}"`), `데이터랩 ${key} 항목이 없습니다.`);
});
const tabKeys = [...index.matchAll(/data-datalab-key="([^"]+)"/g)].map((match) => match[1]);
expect(
  tabKeys.join(",") === "lodging,volume,change,highest,consign,closure,tourism_domestic,tourism_foreign,tourism_consume",
  "기존 데이터랩 6개와 관광 열지도 3개 탭 순서가 아닙니다."
);
expect(index.includes("<span>영업신고현황</span>") && !index.includes("위탁현황"),
  "데이터랩 ⑤ 탭 명칭이 영업신고현황으로 교체되지 않았습니다.");
expect(
  main.includes("/api/tourism/heatmap/domestic") &&
  main.includes("/api/tourism/heatmap/foreign") &&
  main.includes("/api/tourism/heatmap/consume") &&
  main.includes("clearDataLabTourismMap"),
  "관광 열지도 API 연결 또는 탭 전환 정리 로직이 없습니다."
);
expect(
  main.includes("compactMap ? 36 : 72") &&
  main.includes("compactMap ? 118 : 172") &&
  main.includes("Math.sqrt(ratio)") &&
  main.includes("외국인 ${Math.round(n / 10000)") &&
  main.includes("도내 소비 ${n.toLocaleString"),
  "관광 열지도 원 크기 비례 또는 지표별 큰 숫자 표기가 없습니다."
);
expect(
  main.includes("rank <= 25") &&
  main.includes('window.matchMedia("(hover: hover)")') &&
  main.includes('bubble.classList.toggle("is-unlabeled"'),
  "모바일 열지도 라벨 밀도 또는 터치 전용 상세정보 처리가 없습니다."
);
expect(
  css.includes('[data-palette="domestic"]') &&
  css.includes('[data-palette="foreign"]') &&
  css.includes('[data-palette="consume"]') &&
  css.includes(".datalab-map-bubble-name") &&
  css.includes(".datalab-map-bubble-value"),
  "관광 열지도 지표별 색상 또는 원 내부 가독성 스타일이 없습니다."
);
expect(
  main.includes("function showTourismMapOnMobile(key)") &&
  main.includes('window.matchMedia("(max-width: 980px)")') &&
  main.includes('toggle.dataset.tourismMapActive = "true"') &&
  main.includes('toggle.click()') &&
  main.includes('>데이터랩</span>') &&
  css.includes('[data-tourism-map-active="true"]') &&
  header.includes('listToggleBtn.dataset.tourismMapActive === "true"'),
  "모바일 관광 열지도에서 패널을 닫고 다시 여는 동작이 없습니다."
);

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
  main.includes('const HS_RECENT_MAX = 5') &&
  main.includes("list.slice(0, HS_RECENT_MAX)"),
  "최근검색 화면 표시 개수가 5개로 제한되지 않았습니다."
);
expect(
  css.includes("grid-template-columns:repeat(3,minmax(0,1fr))") &&
  css.includes(".datalab-content{min-width:0; min-height:420px; margin-top:10px;}") &&
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
  consignRender.includes("<th>시도</th><th>건물수</th><th>호실수</th><th>신고업체</th><th>신고호실</th><th>신고율</th>") &&
  consignRender.includes("<tfoot>") &&
  consignRender.includes("datalab-partial-badge") &&
  !consignRender.includes("건물마스터 + 행안부 영업신고 기준"),
  "영업신고현황이 합계행 포함 단일 테이블로 렌더링되지 않았습니다."
);
expect(main.includes("dataLabFetchController"), "데이터랩 탭 전환 시 이전 요청 취소가 없습니다.");
expect(main.includes("DATA_LAB_CACHE_TTL_MS"), "데이터랩 반복 탭 전환 캐시가 없습니다.");
expect(main.includes("const cacheTtl = DATA_LAB_CACHE_TTL_MS;") &&
  main.includes("DATA_LAB_CONSIGN_REFRESH_MS"),
  "영업신고현황의 공통 브라우저 캐시 TTL 또는 갱신 확인이 없습니다.");
expect(
  main.includes('loadDataLab("consign", "up", { background: true, forceRefresh: true })') &&
  main.includes("if (!forceRefresh && cached && Date.now() - cached.ts < cacheTtl)"),
  "영업신고현황 30초 갱신이 브라우저 캐시를 우회하지 않습니다."
);
expect(main.includes("function setDataLabTabLoading") &&
  main.includes('button.classList.add("is-loading")') &&
  main.includes("contentIsEmpty") &&
  main.includes("if (!background && contentIsEmpty)"),
  "데이터랩 탭 로딩 인디케이터 또는 기존 콘텐츠 유지 처리가 없습니다.");
expect(
  css.includes(".datalab-tab.is-loading::after") &&
  css.includes("animation:datalab-spin .7s linear infinite"),
  "데이터랩 탭 로딩 스피너 CSS가 없습니다."
);
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
expect(main.includes("<strong>⑤ 📋 생활숙박시설 영업신고현황</strong>") && main.includes("<strong>⑥ ⚫ 폐업 현황</strong>"),
  "데이터랩 콘텐츠의 영업신고현황·폐업 현황 순서 또는 명칭이 맞지 않습니다.");
const closureRender = main.slice(main.indexOf("function renderDataLabClosure"), main.indexOf("function renderDataLabConsign"));
expect(closureRender.includes('class="datalab-region"') && !closureRender.includes('class="datalab-building"'),
  "폐업 현황 지역명이 건물명 강조 스타일을 사용하고 있습니다.");
expect(css.includes(".datalab-region") && css.includes("font-size:12px; font-weight:400"),
  "폐업 현황 지역명이 건물명 크기·일반 굵기로 지정되지 않았습니다.");
expect(main.includes("dataLabArea(item.area_sqm)"), "가격변동 데이터랩에 동일 전용면적 표시가 없습니다.");
expect(main.includes("<span class=\"datalab-caption\">현재수집 기준</span>"), "전국숙박업통계 캡션이 현재수집 기준이 아닙니다.");
expect(main.includes("function _hygieneBadge") &&
  main.includes("const badge = _hygieneBadge(l.hygiene_type)") &&
  main.includes('"외국인관광도시민박업":     ["에어비앤비"') &&
  main.includes('"농어촌민박업":           ["농어촌민박"') &&
  main.includes('"한옥체험업":            ["한옥"'),
  "영업신고 업종별 상세 용도 뱃지가 없습니다.");
expect(main.includes('class="datalab-head-stack">건물수<small>(시설수)</small>') &&
  main.includes('title="건축물대장 표제부 hoCnt 합계입니다. 생활 외 유형은 신고객실수와 직접 비교하지 않습니다."><span class="datalab-head-stack">호실수<small>(사이트수)</small>') &&
  main.includes('title="현재 정상영업 중인 신고업체 수입니다."><span class="datalab-head-stack">신고업체<small>(정상)</small>') &&
  main.includes('title="생활은 객실 기준, 일반은 업체 기준, 캠핑은 시설 매칭 기준, 그 밖의 유형은 건물 커버리지 기준입니다."><span class="datalab-head-stack">신고율</span>') &&
  main.includes('const buildingCoverageTypes = new Set(["관광", "에어비앤비", "농어촌민박", "캠핑", "한옥", "복합"])') &&
  !main.includes("영업신고업체</th>") &&
  !main.includes("영업신고호실</th>") &&
  !main.includes("영업신고율</th>"),
  main.includes('class="datalab-head-stack">신고객실수<small>(사이트수)</small>'),
  "전국숙박업통계의 건물수(시설수)·호실수(사이트수)·신고업체(정상)·신고객실수(사이트수) 구분이 누락됐습니다.");
expect(!main.includes("datalab-note") && !css.includes(".datalab-note") &&
  !main.includes("datalab-caption-bottom"),
  "데이터랩 하단 설명문이 남아 있습니다.");
expect(main.includes('<td class="datalab-sub-name">${escapeHtml(sub.type)}</td>') &&
  css.includes(".datalab-sub-name") &&
  css.includes('content:"└"'),
  "일반숙박 세부행의 세로 들여쓰기가 없습니다.");
expect(main.includes('["일반야영", mergeCampingDetails("general_only")]') &&
  main.includes('["자동차야영", mergeCampingDetails("auto_only")]') &&
  main.includes('["글램핑", mergeCampingDetails("glamping_only")]') &&
  main.includes('["카라반", mergeCampingDetails("caravan_only")]') &&
  main.includes('["복합·미확인", mergeCampingDetails("confirmed_mixed", "unknown")]') &&
  main.includes("detail.matchedFacilityCount") &&
  main.includes("detail.matchedSiteCount") &&
  main.includes("return base + campingSubRows + subRows;"),
  "캠핑 세부 5개 행에 신고시설·신고사이트 집계가 표시되지 않습니다.");
expect(main.includes('row.type === "캠핑"') &&
  main.includes("? row.camping_facility_count") &&
  main.includes("? row.camping_site_count"),
  "캠핑 합계 행이 시설수·사이트수 합계를 유지하지 않습니다.");
expect(css.includes("--panel-w:440px") &&
  css.includes(".datalab-table-wrap{overflow-x:hidden;") &&
  css.includes(".datalab-table{width:100%; min-width:0; table-layout:fixed;") &&
  css.includes(".datalab-table th{padding:6px 2px;") &&
  css.includes(".datalab-table td{padding:6px 2px;"),
  "데이터랩 패널·테이블 폭 축소 CSS가 반영되지 않았습니다.");
expect(!main.includes("row.favorites") && !main.includes("row.listing_requests"),
  "전국숙박업통계 렌더링에 내부 운영지표가 남아 있습니다.");
const buildingPhotoLoader = main.slice(
  main.indexOf("async function loadOnDemandBuildingPhotos"),
  main.indexOf("function buildingPanelSkeleton")
);
expect(
  buildingPhotoLoader.includes("data.streetview_available === true") &&
  buildingPhotoLoader.includes("await savePhotosToServer(buildingId, [])") &&
  buildingPhotoLoader.includes("saved?.streetview_available === true && !gocampingInitial.length") &&
  !buildingPhotoLoader.includes("const initialHasPhotos") &&
  main.includes('onerror="handleBuildingPhotoError(this)"') &&
  main.includes("matchedItem?.firstimage") &&
  main.includes("const timeout = setTimeout(() => controller.abort(), 15000)"),
  "TourAPI no_match가 서버에 기록되지 않거나 Street View 실패 이미지가 숨겨지지 않습니다."
);

async function verifyForcedConsignRefreshFetchesPastRecentBrowserCache() {
  const sourceStart = main.indexOf("async function loadDataLab");
  const sourceEnd = main.indexOf("\nfunction initDataLab", sourceStart);
  expect(sourceStart >= 0 && sourceEnd > sourceStart, "데이터랩 로더를 동작 검증에 분리할 수 없습니다.");

  const content = {
    textContent: "기존 영업신고현황",
    innerHTML: "기존 영업신고현황",
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  let fetchCalls = 0;
  const context = {
    AbortController,
    Date,
    encodeURIComponent,
    console,
    dataLabRequestSequence: 0,
    dataLabFetchController: null,
    DATA_LAB_CACHE_TTL_MS: 600000,
    dataLabResponseCache: new Map([
      ["consign:up", {
        ts: Date.now(),
        data: { ok: true, marker: "cached" },
      }],
    ]),
    document: {
      getElementById: () => content,
    },
    setDataLabActive: () => {},
    setDataLabTabLoading: () => {},
    bindDataLabControls: () => {},
    dataLabLoadingHTML: () => "로딩",
    dataLabErrorHTML: () => "오류",
    clearDataLabTourismMap: () => {},
    resetTourismMapMobileToggle: () => {},
    showTourismMapOnMobile: () => {},
    DATA_LAB_TOURISM_KEYS: new Set(["tourism_domestic", "tourism_foreign", "tourism_consume"]),
    paintDataLabTourismMap: () => {},
    renderDataLabLodging: () => "",
    renderDataLabVolume: () => "",
    renderDataLabChange: () => "",
    renderDataLabHighest: () => "",
    renderDataLabClosure: () => "",
    renderDataLabConsign: (data) => `영업신고현황:${data.marker}`,
    renderDataLabTourism: () => "",
    fetch: async () => {
      fetchCalls += 1;
      return {
        ok: true,
        json: async () => ({ ok: true, marker: "fresh" }),
      };
    },
  };
  vm.createContext(context);
  vm.runInContext(`${main.slice(sourceStart, sourceEnd)}\nglobalThis.runDataLab = loadDataLab;`, context);
  await context.runDataLab("consign", "up", {
    background: true,
    forceRefresh: true,
  });
  expect(fetchCalls === 1, "최근 브라우저 캐시가 있어도 강제 영업신고 갱신이 네트워크 요청을 보내지 않았습니다.");
  expect(content.innerHTML === "영업신고현황:fresh", "강제 영업신고 갱신 결과가 기존 콘텐츠를 대체하지 않았습니다.");
}

verifyForcedConsignRefreshFetchesPastRecentBrowserCache()
  .then(() => console.log("OK  홈 최근검색 위치·실거래추세·데이터랩 로딩·localStorage 회귀"))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
