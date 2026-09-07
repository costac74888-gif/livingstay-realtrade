const fs = require("fs");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const SELECTED_ID = 101;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function chromiumExecutable() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  const bundled = chromium.executablePath();
  if (bundled && fs.existsSync(bundled)) return bundled;
  for (const command of ["chromium", "chromium-browser", "google-chrome"]) {
    try {
      const path = execFileSync("sh", ["-c", `command -v ${command}`], { encoding: "utf8" }).trim();
      if (path) return path;
    } catch (_) {}
  }
  throw new Error("Chromium 실행 파일을 찾지 못했습니다.");
}

function item(id, name, sido, sgg, growth, price, quadrant, representative = false) {
  return {
    building_id: id, name, sido, sgg, address: `${sido} ${sgg}`,
    lodging_type: "생활숙박시설", tourism_growth: null,
    tourism_demand_index: 50 + growth, peer_price_gap: price, quadrant,
    peer_price_median: 200, building_period_price_median: 200 * (1 + price / 100),
    peer_scope: "시군구·동일유형", peer_building_count: 8, sample_level: "표본 양호",
    is_representative: representative, transaction_count: 3, last_deal_date: "2026-08-12",
  };
}

function fixture(incompleteSelected = false, incompleteFinalTrajectory = false) {
  const payload = {
    generated_at: "2026-09-07T00:00:00Z",
    baselines: { tourism_growth: null, tourism_demand_index: 50, peer_price_gap: 0 },
    filters: { sidos: ["강원특별자치도"], sggs: ["속초시"], lodging_types: [], period_options: [] },
    summary: { registered_buildings: 7, transaction_count: 20, analyzed_buildings: 7, analysis_sample_transaction_count: 20 },
    methodology: {},
    trajectory_methodology: { price: "월별 ㎡당 중앙값", tourism: "거래월 관광자료", missing: "관광자료 누락은 회색 표시" },
    trajectory: [
      { month: "202601", tourism_month: "202601", tourism_value: -8, price_change: -5, price_per_sqm_median: 410, previous_price_per_sqm_median: 431.6, transaction_count: 2, transactions: [{ deal_date: "2026-01-03", price: 41000, area: 100, price_per_sqm: 410 }] },
      { month: "202603", tourism_month: null, tourism_value: null, price_change: 12, price_per_sqm_median: 459.2, previous_price_per_sqm_median: 410, transaction_count: 1, transactions: [{ deal_date: "2026-03-10", price: 45920, area: 100, price_per_sqm: 459.2 }] },
      { month: "202606", tourism_month: "202606", tourism_value: 14, price_change: 18, price_per_sqm_median: 541.9, previous_price_per_sqm_median: 459.2, transaction_count: 3, transactions: [{ deal_date: "2026-06-22", price: 54190, area: 100, price_per_sqm: 541.9 }] },
    ],
    items: [
      item(SELECTED_ID, "선택 테스트 자산", "강원특별자치도", "속초시", 14, 18, "수요 프리미엄"),
      item(102, "같은 지역 비교", "강원특별자치도", "속초시", -13, 10, "가격 부담"),
      item(201, "가격부담대표자산", "서울특별시", "중구", -24, 27, "가격 부담", true),
      item(202, "수요프리미엄대표", "부산광역시", "해운대구", 25, 24, "수요 프리미엄", true),
      item(203, "저가수요확인대표", "전라남도", "목포시", -22, -25, "저가·수요 확인 필요", true),
      item(204, "수요대비저평가대표", "제주특별자치도", "제주시", 23, -22, "수요 대비 저평가 후보", true),
    ],
  };
  for (let id = 401; id <= 408; id += 1) {
    payload.items.push(item(id, `추가 비교 자산 ${id}`, "경기도", "가평군", id - 400, (id - 404) * 2, "비교 자산"));
  }
  if (incompleteSelected) {
    payload.items[0].tourism_demand_index = null;
    payload.items[0].peer_price_gap = 0.8;
    payload.items[0].quadrant = "관광 비교자료 부족";
    payload.items[0].transaction_count = 229;
    payload.items.push(item(301, "비선택 극단값", "경상남도", "통영시", null, 4464, "관광 비교자료 부족"));
  }
  if (incompleteFinalTrajectory) {
    payload.trajectory[2].tourism_month = null;
    payload.trajectory[2].tourism_value = null;
  }
  return payload;
}

function overlaps(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

async function json(route, body) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

async function run() {
  const browser = await chromium.launch({
    headless: true, executablePath: chromiumExecutable(),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
  });
  const page = await context.newPage();
  const errors = [];
  let incompleteSelected = false;
  let incompleteFinalTrajectory = false;
  let rentalTransactionRequest = "";
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return json(route, { logged_in: true, user: { id: 1, name: "테스트 회원" } });
    if (url.pathname === "/api/analysis/building-search") return json(route, {
      items: [{
        building_id: SELECTED_ID,
        name: "선택 테스트 자산",
        lodging_type: "생활숙박시설",
        address: "강원특별자치도 속초시 테스트로 1",
      }],
    });
    if (url.pathname === "/api/analysis/assets") return json(route, fixture(incompleteSelected, incompleteFinalTrajectory));
    if (url.pathname === "/api/transactions") {
      rentalTransactionRequest = url.search;
      return json(route, { total: 1, page: 1, size: 1, transaction_scope: "unit", items: [{
        price: 9876, area: 32.45, floor: 8, deal_date: "2026-08-19",
        transaction_scope: "unit", match_confidence: "exact",
      }] });
    }
    if (url.pathname === "/api/analysis/operation-benchmarks") return json(route, {
      ok: true, sido: "강원", sgg: "속초시",
      source: { name: "한국호텔업협회 호텔업 운영현황", reference_year: 2024 },
      items: [
        { region: "속초시", adr: 210000, occ: 80, revpar: 168000, foreign: 12 },
        { region: "강릉시", adr: 208511, occ: 62.23, revpar: 129756, foreign: 3.94 },
        { region: "평창군", adr: 190000, occ: 60, revpar: 114000, foreign: 5 },
        { region: "양양군", adr: 170000, occ: 61, revpar: 103700, foreign: 4 },
        { region: "고성군", adr: 135489, occ: 59.46, revpar: 80562, foreign: 8 },
        { region: "춘천시", adr: 113000, occ: 55, revpar: 62150, foreign: 2 },
      ],
    });
    if (url.pathname === "/api/favorites/mine") return json(route, { items: [] });
    if (url.pathname.endsWith("/photos")) return json(route, { photos: [] });
    if (url.pathname === `/api/building/${SELECTED_ID}`) return json(route, {
      building_name: "선택 테스트 자산", road_address: "강원특별자치도 속초시 테스트로 1",
      sido: "강원특별자치도", lodging_type: "생활숙박시설",
      lodging_room_total: 348,
      lodgings: [
        { biz_name: "테스트 호텔", room_count: 200 },
        { biz_name: "테스트 레지던스", room_count: 148 },
      ],
    });
    return json(route, { ok: true, items: [] });
  });

  try {
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({ width, height: width === 1280 ? 900 : width === 390 ? 844 : 720 });
      const response = await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
      expect(response && response.ok(), `${width}px 인증 투자분석 화면을 열지 못했습니다.`);
      await page.waitForFunction(() => {
        const layout = window.__analysisChartLayout;
        return layout && layout.ready && layout.baseline && layout.baseline.valueX === 50
          && layout.labels && layout.labels.length === 4
          && layout.points && layout.points.some((point) => point.selected);
      });

      const result = await page.evaluate(() => {
      const layout = window.__analysisChartLayout;
      const wrap = document.querySelector(".chart-wrap").getBoundingClientRect();
      const canvas = document.getElementById("scatterChart").getBoundingClientRect();
      return {
        layout,
        wrap: { w: wrap.width, h: wrap.height },
        canvas: { left: canvas.left - wrap.left, top: canvas.top - wrap.top, right: canvas.right - wrap.left, bottom: canvas.bottom - wrap.top },
        baselineText: [document.getElementById("tourismBaseline").textContent, document.getElementById("priceBaseline").textContent],
         quadrants: Array.from(document.querySelectorAll(".chart-wrap .quad")).map((node) => {
           const rect = node.getBoundingClientRect();
           const label = node.querySelector("b").getBoundingClientRect();
           return { text: node.textContent.trim(), left: rect.left - wrap.left, width: rect.width, labelLeft: label.left - wrap.left };
         }),
         detailButtons: Array.from(document.querySelectorAll("#detailCard .detail-actions .am-btn")).map((node) => node.textContent.trim()),
         detailSections: Array.from(document.querySelectorAll("#detailCard .detail-analysis, #detailCard .quadrant-guide, #detailCard .detail-disclaimer, #detailCard .detail-section-title")).map((node) => node.textContent.trim()),
         recommendations: Array.from(document.querySelectorAll("#recommendationRows tr[data-id]")).map((node) => node.dataset.id),
        loggedInWorkspace: !document.getElementById("workspace").classList.contains("hidden"),
      };
      });

      expect(result.loggedInWorkspace, `${width}px 로그인 상태인데 분석 작업영역이 표시되지 않았습니다.`);
    expect(result.baselineText[0] === "50" && result.baselineText[1] === "0%", "관광수요 50점·유사자산 가격 0% 기준선 표시가 다릅니다.");
    const { baseline, points, labels } = result.layout;
    expect(result.quadrants.length === 4 && result.quadrants.every((quad) => quad.text !== ""),
      "그래프의 ①~④ 사분면 설명문구가 누락됐습니다.");
    expect(result.quadrants[1].labelLeft >= result.quadrants[1].left + 8
      && result.quadrants[1].labelLeft < result.quadrants[1].left + result.quadrants[1].width
      && result.quadrants[3].labelLeft >= result.quadrants[3].left + 8
      && result.quadrants[3].labelLeft < result.quadrants[3].left + result.quadrants[3].width,
      "①·④ 설명문구가 해당 사분면 안에 표시되지 않았습니다.");
    expect(result.detailSections.some((text) => text.includes("현재 수요·상대가격 위치"))
      && result.detailButtons.join("|") === "상세 페이지|실거래 전부보기|인쇄|공유",
      "우측 패널 설명 순서 또는 하단 4개 버튼이 다릅니다.");
    expect(result.recommendations.length > 0 && result.recommendations.length <= 5,
      "가격 매력 후보 TOP 5에 수요 대비 저평가 후보가 표시되지 않았습니다.");
    expect(Math.abs(baseline.x - baseline.quadrantRight[0]) < 0.6 && Math.abs(baseline.x - baseline.quadrantRight[1]) < 0.6,
      "세로 0% 점선과 사분면 배경 경계가 일치하지 않습니다.");
    expect(Math.abs(baseline.y - baseline.quadrantBottom[0]) < 0.6 && Math.abs(baseline.y - baseline.quadrantBottom[1]) < 0.6,
      "가로 0% 점선과 사분면 배경 경계가 일치하지 않습니다.");
    expect(baseline.valueX === 50 && baseline.valueY === 0,
      "관광수요 50점·유사자산 가격 0% 기준선이 적용되지 않았습니다.");

    const selected = points.find((point) => point.selected);
    const nearby = points.find((point) => point.sameRegion && !point.selected);
    const representatives = points.filter((point) => point.representative);
    expect(points.every((point) => point.radius > 0), "기본 관광수요 지수의 전체 비교 건물 분포가 숨겨졌습니다.");
    expect(selected && selected.color === "#102a43" && selected.radius === 10, "선택 건물의 색상 또는 크기가 다릅니다.");
    expect(nearby && nearby.color === "#168f91" && nearby.radius === 5.5, "같은 시군구 비교군의 색상 또는 크기가 다릅니다.");
      expect(representatives.length === 4 && representatives.every((point) => point.radius === 8),
      "사분면 대표 표본 네 개의 표시 크기가 다릅니다.");
      const expectedRepresentatives = {
        201: { quadrant: "가격 부담", color: "#df5b57", name: "가격부담대표자산", region: "중구" },
        202: { quadrant: "수요 프리미엄", color: "#168cc4", name: "수요프리미엄대표", region: "해운대구" },
        203: { quadrant: "저가·수요 확인 필요", color: "#758596", name: "저가수요확인대표", region: "목포시" },
        204: { quadrant: "수요 대비 저평가 후보", color: "#2aa96f", name: "수요대비저평가대표", region: "제주시" },
      };
      representatives.forEach((point) => expect(
        expectedRepresentatives[point.id] && point.color === expectedRepresentatives[point.id].color,
        `대표 표본 ${point.id}의 사분면 색상이 다릅니다.`,
      ));

      labels.forEach((label) => {
      const expected = expectedRepresentatives[label.id];
      expect(expected && label.quadrant === expected.quadrant && label.color === expected.color,
        `대표 라벨 ${label.id}의 사분면 또는 색상이 다릅니다.`);
      const fullLabel = label.name === expected.name.slice(0, 10) && label.region === expected.region;
      const compactLabel = label.name === expected.name.slice(0, 6) && label.region === "";
      expect(fullLabel || compactLabel,
        `대표 라벨 ${label.id}의 건물명 또는 지역명이 다릅니다.`);
      expect(label.x >= result.canvas.left && label.y >= result.canvas.top
        && label.x + label.w <= result.canvas.right && label.y + label.h <= result.canvas.bottom,
      `대표 라벨 ${label.id}가 차트 화면 밖으로 벗어났습니다.`);
      });
      for (let i = 0; i < labels.length; i += 1) {
      for (let j = i + 1; j < labels.length; j += 1) {
        expect(!overlaps(labels[i], labels[j]), `대표 라벨 ${labels[i].id}와 ${labels[j].id}가 겹칩니다.`);
      }
      }
    }
    incompleteSelected = true;
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      if (window.__analysisChartLayout) window.__analysisChartLayout.ready = false;
      document.getElementById("selTourismAxis").dispatchEvent(new Event("change", { bubbles: true }));
      document.getElementById("applyBtn").click();
    });
    await page.waitForFunction(() => {
      const layout = window.__analysisChartLayout;
      return layout && layout.ready && layout.points
        && layout.points.some((point) => point.selected && point.color === "#758596");
    });
    const incompleteResult = await page.evaluate(() => {
      const layout = window.__analysisChartLayout;
      return {
        selected: layout.points.find((point) => point.selected),
        pointIds: layout.points.map((point) => point.id),
        incompletePoints: layout.points.filter((point) => point.color === "#758596" || point.color === "#b8c1ca"),
        baseline: layout.baseline,
        detail: document.querySelector(".quadrant-guide").textContent,
        transactionCount: document.querySelector(".detail-metrics").textContent,
      };
    });
    expect(incompleteResult.selected.radius === 10, "비교기간 부족 선택 건물의 점 크기가 유지되지 않았습니다.");
    expect(incompleteResult.pointIds.includes("301") && incompleteResult.incompletePoints.length > 1,
      "비선택 표본 부족 건물의 회색 점이 표시되지 않았습니다.");
    expect(Math.abs(incompleteResult.selected.x - incompleteResult.baseline.x) > 0.6,
      "관광 비교기간 부족 건물이 중앙 기준선에 겹쳐 표시됐습니다.");
    expect(Math.abs(incompleteResult.selected.y - incompleteResult.baseline.y) > 0.6,
      "가격변동 값이 있는 건물이 중앙점으로 잘못 표시됐습니다.");
    expect(incompleteResult.detail.includes("관광 비교자료 부족"),
      "부족한 비교축이 관광 자료임을 구체적으로 안내하지 않습니다.");
    expect(incompleteResult.transactionCount.includes("229건"),
      "기간 거래건수가 비교기간 부족 안내와 함께 보존되지 않았습니다.");
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}&mode=operation`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.getElementById("operationRoomCount").textContent.includes("200실"));
    await page.fill("#operationRoomCountInput", "180");
    const defaultOperationName = await page.inputValue("#operationBusinessName");
    await page.fill("#operationBusinessName", "사용자 수정 상호");
    await page.fill("#operationOcc", "74");
    await page.fill("#operationAdr", "162000");
    await page.click("#operationRun");
    const operationResult = await page.evaluate(() => ({
      operationVisible: !document.getElementById("operationAnalysis").classList.contains("hidden"),
      propertyHidden: document.getElementById("propertyAnalysis").classList.contains("hidden"),
      selectedTab: document.getElementById("operationTab").getAttribute("aria-selected"),
      roomCount: document.getElementById("operationRoomCount").textContent,
      appliedRoomCount: document.getElementById("operationRoomCountInput").value,
      detail: document.getElementById("operationDetail").textContent,
      topRows: document.querySelectorAll("#operationTopRows tr").length,
      chart: !!Chart.getChart("operationChart"),
      lodgingOptions: document.querySelectorAll("#operationLodging option").length,
      adrBaseline: document.getElementById("operationAdrBaseline").textContent,
      hiddenFilters: getComputedStyle(document.getElementById("analysisFilter")).display === "none",
      operationLayout: window.__operationChartLayout,
      operationName: document.getElementById("operationBusinessName").value,
    }));
    expect(operationResult.operationVisible && operationResult.propertyHidden && operationResult.selectedTab === "true",
      "운영분석 탭 전환 상태가 올바르지 않습니다.");
    expect(operationResult.roomCount.includes("200실"), "선택 영업신고 업소의 객실 수가 운영분석에 자동 적용되지 않았습니다.");
    expect(operationResult.detail.includes("119,880원") && operationResult.detail.includes("자동분석"),
      `OCC·ADR 입력으로 RevPAR 운영분석 결과가 표시되지 않았습니다: ${operationResult.detail}`);
    expect(operationResult.topRows === 5 && operationResult.chart,
      "운영 포지셔닝 차트 또는 지역 TOP 5가 표시되지 않았습니다.");
    expect(operationResult.lodgingOptions === 2 && operationResult.roomCount.includes("200실"),
      "한 건물의 영업신고 업소 선택과 업소별 객실 수 자동 적용이 올바르지 않습니다.");
    expect(operationResult.appliedRoomCount === "180",
      "자동 입력된 신고 객실 수를 사용자가 임의 수정할 수 없습니다.");
    expect(defaultOperationName === "선택 테스트 자산"
      && operationResult.operationName === "사용자 수정 상호"
      && operationResult.detail.includes("사용자 수정 상호"),
      "분석 상호가 건물명을 기본값으로 사용하거나 사용자 수정값을 반영하지 않습니다.");
    expect(operationResult.adrBaseline.includes("원") && operationResult.hiddenFilters,
      "지역 평균 기준선 또는 운영분석의 불필요한 주소 필터 숨김이 적용되지 않았습니다.");
    expect(operationResult.operationLayout.comparisonPoints === 6
      && operationResult.operationLayout.comparisonColor === "#8798a8"
      && operationResult.operationLayout.selectedRadius === 11
      && operationResult.operationLayout.pulseVisible
      && operationResult.operationLayout.baselineRegion === "속초시"
      && operationResult.operationLayout.baselineAdr === 210000
      && operationResult.operationLayout.baselineOcc === 80
      && Math.abs(operationResult.operationLayout.baselinePixelX
        - operationResult.operationLayout.chartCenterX) < 0.6
      && Math.abs(operationResult.operationLayout.baselinePixelY
        - operationResult.operationLayout.chartCenterY) < 0.6,
    "운영분석의 회색 비교점 또는 선택 건물의 큰 점멸 표시가 없습니다.");
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}&mode=rental`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.getElementById("rentalBuildingName").textContent === "선택 테스트 자산");
    await page.waitForFunction(() => document.getElementById("rentalMarketPrice").value === "9876");
    const automaticMarketPrice = await page.evaluate(() => ({
      price: document.getElementById("rentalMarketPrice").value,
      hint: document.getElementById("rentalMarketPriceHint").textContent,
    }));
    expect(automaticMarketPrice.price === "9876"
      && automaticMarketPrice.hint.includes("2026.08.19")
      && automaticMarketPrice.hint.includes("전용 32.45㎡")
      && rentalTransactionRequest.includes("transaction_scope=unit")
      && rentalTransactionRequest.includes("size=1"),
      "선택 건물의 최근 호실 실거래가가 자동 반영되지 않았습니다.");
    await page.fill("#rentalPurchasePrice", "10000");
    const acquisitionCosts = await page.evaluate(() => ({
      acquisitionTax: document.getElementById("rentalAcquisitionTax").value,
      brokerFee: document.getElementById("rentalBrokerFee").value,
    }));
    expect(acquisitionCosts.acquisitionTax === "460" && acquisitionCosts.brokerFee === "90",
      "매입가 기준 취득세 4.6%와 중개보수 0.9%가 자동 계산되지 않았습니다.");
    await page.fill("#rentalMarketPrice", "11000");
    await page.fill("#rentalDeposit", "300");
    await page.fill("#rentalMonthlyRent", "50");
    await page.fill("#rentalLoanAmount", "6000");
    await page.fill("#rentalLoanRate", "4.5");
    await page.selectOption("#rentalLoanMethod", "interest");
    await page.click("#rentalCalculate");
    const rentalResult = await page.evaluate(() => ({
      visible: !document.getElementById("rentalAnalysis").classList.contains("hidden"),
      selectedTab: document.getElementById("rentalTab").getAttribute("aria-selected"),
      tax: document.getElementById("rentalPropertyTax").value,
      text: document.getElementById("rentalResults").textContent,
      calculation: window.__rentalAnalysisResult,
    }));
    expect(rentalResult.visible && rentalResult.selectedTab === "true",
      "임대수익분석 탭이 선택 상태로 표시되지 않았습니다.");
    expect(Number(rentalResult.tax) > 0 && rentalResult.text.includes("자기자본 수익률")
      && rentalResult.text.includes("DSCR") && rentalResult.text.includes("현재 실거래 기준 수익률"),
      "재산세·대출·현재 실거래를 반영한 임대수익 결과가 없습니다.");
    expect(Math.abs(rentalResult.calculation.annualRent - 600) < 0.01
      && Math.abs(rentalResult.calculation.debtService - 270) < 0.01
      && Math.abs(rentalResult.calculation.invested - 4250) < 0.01,
      "보증금·월세·대출을 반영한 임대수익 계산값이 올바르지 않습니다.");
    for (const tab of [
      { id: "propertyTab", mode: null },
      { id: "rentalTab", mode: "rental" },
      { id: "operationTab", mode: "operation" },
    ]) {
      await page.click(`#${tab.id}`);
      await page.fill("#buildingSearch", "선택 테스트");
      await page.waitForSelector("#searchResults .search-result");
      await page.click("#searchResults .search-result");
      const pendingBuilding = await page.evaluate(() => ({
        status: document.getElementById("buildingSelectionStatus").textContent,
        disabled: document.getElementById("buildingSelectionApply").disabled,
      }));
      expect(pendingBuilding.status.includes("선택 예정") && !pendingBuilding.disabled,
        `${tab.id}에서 검색 결과를 건물 선택 버튼으로 확정하는 흐름이 없습니다.`);
      await page.click("#buildingSelectionApply");
      await page.waitForFunction((expectedMode) => {
        const query = new URLSearchParams(location.search);
        return query.get("building_id") === "101" && query.get("mode") === expectedMode;
      }, tab.mode);
      await page.waitForFunction(() =>
        document.getElementById("buildingSelectionStatus").textContent.includes("선택 건물 · 선택 테스트 자산"));
    }
    await page.click("#propertyTab");
    await page.waitForFunction(() => document.querySelectorAll("#assetRows tr").length === 10);
    expect(await page.locator("#tableMoreBtn").isVisible(),
      "건물 비교 목록의 10개 이후 더보기 버튼이 보이지 않습니다.");
    await page.click("#tableMoreBtn");
    expect(await page.locator("#assetRows tr").count() > 10,
      "건물 더보기 후 나머지 건물이 표시되지 않았습니다.");

    await page.click("#buildingSelectionClear");
    await page.waitForFunction(() => !new URLSearchParams(location.search).has("building_id"));
    expect((await page.textContent("#buildingSelectionStatus")).includes("검색 결과에서 건물을 선택"),
      "건물명 × 버튼으로 공통 선택 건물이 지워지지 않았습니다.");
    await page.click("#rentalTab");
    await page.waitForFunction(() =>
      document.getElementById("rentalBuildingName").textContent === "분석할 건물을 선택해 주세요");
    expect(await page.inputValue("#rentalMarketPrice") === "",
      "공통 건물 삭제 후 임대분석의 자동 실거래가가 남아 있습니다.");

    await page.fill("#rentalMonthlyRent", "77");
    await page.click("#operationTab");
    await page.fill("#operationOcc", "71");
    await page.fill("#buildingSearch", "선택 테스트");
    await page.waitForSelector("#searchResults .search-result");
    await page.click("#searchResults .search-result");
    await page.click("#buildingSelectionApply");
    await page.click("#analysisResetAll");
    await page.waitForFunction(() => !new URLSearchParams(location.search).has("building_id"));
    expect(await page.inputValue("#buildingSearch") === ""
      && await page.inputValue("#operationOcc") === "",
      "전체 초기화가 검색어·선택 건물·숙박운영 입력을 지우지 못했습니다.");
    await page.click("#rentalTab");
    expect(await page.inputValue("#rentalMonthlyRent") === ""
      && await page.inputValue("#rentalVacancyRate") === "5",
      "전체 초기화가 임대수익 입력을 기본값으로 되돌리지 못했습니다.");
    expect(errors.length === 0, `브라우저 오류가 발생했습니다: ${errors.join(" | ")}`);
    console.log("OK  인증된 모바일 투자분석 차트 경계·색상·라벨 배치");
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error("FAIL", error);
  process.exitCode = 1;
});
