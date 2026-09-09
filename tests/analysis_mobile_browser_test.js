const fs = require("fs");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const SELECTED_ID = 101;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectSinglePageReport(page, mode, titleText, graphRequired) {
  await page.evaluate(() => window.livingstayRenderAnalysisPrintReport());
  await page.emulateMedia({ media: "print" });
  const report = await page.evaluate(() => ({
    display: getComputedStyle(document.getElementById("printReport")).display,
    mode: document.getElementById("printReport").dataset.mode,
    zones: document.querySelectorAll("#printReport .print-zone").length,
    title: document.getElementById("printReportTitle").textContent,
    graphImage: document.querySelector("#printGraph .print-chart-image")?.getAttribute("src") || "",
    exampleIncluded: document.getElementById("printBasis").textContent.includes("가상 산정 예시"),
    mapLayout: window.__analysisPrintMapLayout || null,
    propertyPoint: !!document.querySelector("#printMap .print-map-property-point"),
    address: document.querySelector("#printOverview .print-building span")?.textContent || "",
    result: document.querySelector("#printOverview .print-result-line")?.textContent || "",
    metricLabels: Array.from(document.querySelectorAll("#printOverview .print-metrics small")).map(node => node.textContent),
    sideMetricCount: document.querySelectorAll("#printTransactionTrend .print-side-metrics article").length,
    sideMetricValues: Array.from(document.querySelectorAll("#printTransactionTrend .print-side-metrics strong")).map(node => node.textContent),
    operationQuadrantsFit: Array.from(document.querySelectorAll("#printGraph .operation-quadrant")).every(node => {
      const rect = node.getBoundingClientRect();
      const wrap = node.parentElement.getBoundingClientRect();
      return rect.left >= wrap.left - 1 && rect.right <= wrap.right + 1
        && rect.top >= wrap.top - 1 && rect.bottom <= wrap.bottom + 1;
    }),
  }));
  const pdf = await page.pdf({ format: "A4", printBackground: true, displayHeaderFooter: false });
  if (process.env.SAVE_OPERATION_PRINT && mode === "operation") {
    fs.writeFileSync(process.env.SAVE_OPERATION_PRINT, pdf);
  }
  const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length;
  await page.emulateMedia({ media: "screen" });
  expect(report.display === "block" && report.mode === mode && report.zones === 5
    && report.title.includes(titleText) && !report.exampleIncluded
    && (!graphRequired || report.graphImage.startsWith("data:image/png"))
    && (mode !== "property" || (report.mapLayout
      && report.mapLayout.preparedWidth >= 200
      && report.mapLayout.preparedHeight >= 155
      && report.mapLayout.propertyPoint === true
      && report.propertyPoint))
    && (mode !== "operation" || (report.address && !report.address.includes("—")
      && report.result.includes("지역 평균 대비 ADR")
      && report.metricLabels.join("|") === "ADR|OCC|RevPAR|적용 객실|지역 평균 ADR|지역 평균 OCC"
      && report.sideMetricCount === 4
      && report.sideMetricValues.every(value => value && !value.startsWith("—"))
      && report.operationQuadrantsFit))
    && pages === 1,
  `${titleText} 인쇄보고서가 A4 한 장·5개 존으로 구성되지 않았습니다. pages=${pages} report=${JSON.stringify(report)}`);
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
    lat: 37.2636, lng: 127.0286,
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
      { month: "202601", tourism_month: "202601", tourism_value: -8, price_change: -5, price_per_sqm_median: 410, previous_price_per_sqm_median: 431.6, transaction_count: 2, transactions: [{ deal_date: "2026-01-03", price: 41000, area: 100, floor: 12, price_per_sqm: 410 }, { deal_date: "2026-01-18", price: 32000, area: 80, floor: 8, price_per_sqm: 400 }] },
      { month: "202603", tourism_month: null, tourism_value: null, price_change: 12, price_per_sqm_median: 459.2, previous_price_per_sqm_median: 410, transaction_count: 1, transactions: [{ deal_date: "2026-03-10", price: 45920, area: 100, price_per_sqm: 459.2 }] },
      { month: "202606", tourism_month: "202606", tourism_value: 14, price_change: 18, price_per_sqm_median: 541.9, previous_price_per_sqm_median: 459.2, transaction_count: 3, transactions: [{ deal_date: "2026-06-22", price: 54190, area: 100, floor: 16, price_per_sqm: 541.9 }, { deal_date: "2026-06-27", price: 36000, area: 80, floor: 10, price_per_sqm: 450 }] },
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
  let comparisonItemCount = 6;
  let rentalMarketRequest = "";
  let uploadHasOccupancyBasis = true;
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
    if (url.pathname === "/api/analysis/assets") {
      const payload = fixture(incompleteSelected, incompleteFinalTrajectory);
      const incompleteItem = payload.items.find((entry) => entry.building_id === 301);
      payload.items = payload.items
        .filter((entry) => entry.building_id !== 301)
        .slice(0, comparisonItemCount - (incompleteItem ? 1 : 0));
      if (incompleteItem) payload.items.push(incompleteItem);
      while (payload.items.length < comparisonItemCount) {
        const id = 400 + payload.items.length;
        payload.items.push(item(id, `비교 자산 ${id}`, "경기도", "수원시", 5, -3, "비교 자산"));
      }
      return json(route, payload);
    }
    if (url.pathname === `/api/building/${SELECTED_ID}/area-types`) {
      return json(route, {
        ok: true,
        items: [
          { sqm: 18.1, ho_cnt: 8 },
          { sqm: 18.2, ho_cnt: 18 },
          { sqm: 18.3, ho_cnt: 3 },
          { sqm: 21.2, ho_cnt: 1 },
          { sqm: 32.5, ho_cnt: 12 },
        ],
        sqms: [18.1, 18.2, 18.3, 21.2, 32.5],
      });
    }
    if (url.pathname === "/api/analysis/rental-benchmark") {
      return json(route, {
        ok: true,
        available: true,
        benchmark: {
          period: "2026-04-01",
          region_code: "42",
          region_name: "강원 조사권역",
          region_level: "province",
          property_type: "small_retail",
          property_type_name: "소규모 상가",
          income_yield: 5.2,
          vacancy_rate: 10,
          stability_score: 90,
          fallback_level: "province",
        },
        items: [
          { region_name: "강원 조사권역", income_yield: 5.2, vacancy_rate: 10, stability_score: 90 },
          { region_name: "인접 조사권역", income_yield: 4.8, vacancy_rate: 13, stability_score: 87 },
        ],
        source: {
          provider: "한국부동산원 R-ONE",
          status: "ready",
          notice: "생활숙박시설과 동일 자산군이 아닌 소규모 상가 통계를 이용한 대체 투자상품 참고 비교입니다.",
        },
      });
    }
    if (url.pathname === "/api/analysis/rental-market-price") {
      rentalMarketRequest = url.search;
      if (url.searchParams.get("area_sqm") === "99") {
        return json(route, {
          ok: false, area_sqm: 99, sample_count: 0,
          reason: "자료 부족: 최근 36개월 내 동일·유사 면적의 매매 실거래가 2건 미만입니다.",
        });
      }
      return json(route, {
        ok: true, area_sqm: 32.5, median_price: 9876,
        latest_deal_date: "2026-08-19", sample_count: 3, match_type: "exact",
        area_range: { min: 32.45, max: 32.51 }, period_months: 36,
        transactions: [
          { deal_date: "2026-08-19", area_sqm: 32.5, price: 10000, area_match: "exact" },
          { deal_date: "2026-07-10", area_sqm: 32.45, price: 9876, area_match: "exact" },
          { deal_date: "2026-06-01", area_sqm: 32.51, price: 9000, area_match: "exact" },
        ],
      });
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
    if (url.pathname === "/api/analysis/operation-upload") return json(route, {
      ok: true,
      result: uploadHasOccupancyBasis ? {
        period_start: "2026-01-01", period_end: "2026-01-31",
        adr: 162000, room_revenue: 502200000, sold_rooms: 3100,
        occupancy_days: 31,
      } : {
        adr: 162000, room_revenue: 16200000, sold_rooms: 100,
      },
      processed_file_count: 1,
      retained: false,
    });
    if (url.pathname === "/api/favorites/mine") return json(route, { items: [] });
    if (url.pathname.endsWith("/photos")) return json(route, {
      photos: [
        { url: "/missing-analysis-photo.jpg" },
        { url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='2' height='2'%3E%3Crect width='2' height='2' fill='%23ddd'/%3E%3C/svg%3E" },
      ],
    });
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
        const photo = document.querySelector("#detailCard .detail-photo");
        return layout && layout.ready && layout.baseline && layout.baseline.valueX === 50
          && layout.labels && layout.labels.length === 4
          && layout.points && layout.points.some((point) => point.selected)
          && photo && photo.dataset.photoState === "loaded";
      });

      const result = await page.evaluate(() => {
      const layout = window.__analysisChartLayout;
      const wrap = document.querySelector(".chart-wrap").getBoundingClientRect();
      const canvas = document.getElementById("scatterChart").getBoundingClientRect();
       const yAxis = document.querySelector(".y-axis-guide");
       const yAxisRect = yAxis.getBoundingClientRect();
      return {
        layout,
        wrap: { w: wrap.width, h: wrap.height },
        canvas: { left: canvas.left - wrap.left, top: canvas.top - wrap.top, right: canvas.right - wrap.left, bottom: canvas.bottom - wrap.top },
         yAxis: {
           width: yAxisRect.width,
           titleWritingMode: getComputedStyle(yAxis.querySelector("strong")).writingMode,
         },
        baselineText: [document.getElementById("tourismBaseline").textContent, document.getElementById("priceBaseline").textContent],
         quadrants: Array.from(document.querySelectorAll(".chart-wrap .quad")).map((node) => {
           const rect = node.getBoundingClientRect();
           const label = node.querySelector("b").getBoundingClientRect();
           return { text: node.textContent.trim(), left: rect.left - wrap.left, width: rect.width, labelLeft: label.left - wrap.left };
         }),
         detailButtons: Array.from(document.querySelectorAll("#detailCard .detail-actions .am-btn")).map((node) => node.textContent.trim()),
         detailSections: Array.from(document.querySelectorAll("#detailCard .detail-analysis, #detailCard .quadrant-guide, #detailCard .detail-disclaimer, #detailCard .detail-section-title")).map((node) => node.textContent.trim()),
          photo: {
            state: document.querySelector("#detailCard .detail-photo").dataset.photoState,
            src: document.querySelector("#detailCard .detail-photo img").getAttribute("src"),
          },
         recommendations: Array.from(document.querySelectorAll("#recommendationRows tr[data-id]")).map((node) => node.dataset.id),
        loggedInWorkspace: !document.getElementById("workspace").classList.contains("hidden"),
      };
      });

      expect(result.loggedInWorkspace, `${width}px 로그인 상태인데 분석 작업영역이 표시되지 않았습니다.`);
     if (width <= 650) {
       expect(result.yAxis.width <= 28 && result.yAxis.titleWritingMode === "vertical-rl",
         `${width}px 가격축 문구가 세로형으로 압축되지 않아 사분면이 오른쪽으로 밀렸습니다.`);
        expect(result.layout.baseline.x < result.wrap.w * 0.56
          && result.layout.axis.xMax - 50 > (50 - result.layout.axis.xMin) * 1.5,
          `${width}px 관광수요 중심선이 모바일 그래프의 왼쪽으로 충분히 이동하지 않았습니다.`);
     }
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
    expect(result.photo.state === "loaded" && result.photo.src.startsWith("data:image/svg+xml"),
      "첫 건물사진이 깨졌을 때 다음 사진으로 대체되지 않았습니다.");
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
    expect(selected && selected.color === "#A66F00" && selected.radius === 10
      && result.layout.selectedDrawnOnTop === true
      && result.layout.selectedLabel
      && result.layout.selectedLabel.text.startsWith("내 자산 · "),
      "내 자산의 황금색 포인트와 설명이 다른 포인트와 라벨보다 위에 표시되지 않습니다.");
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
    expect(await page.locator("#assetRows tr:visible").count() === 6
      && await page.locator("#tableExpandBtn").evaluate((node) => node.classList.contains("hidden")),
    "10개 이하 건물 비교 목록에서 펼침 버튼이 숨겨지지 않았습니다.");
    expect(!(await page.locator(".table-card thead").textContent()).includes("위치"),
      "건물 비교표에 제거한 주소·위치 열이 다시 표시됐습니다.");
    expect(await page.locator("#methodology #summaryGrid").count() === 1,
      "분석 요약 카드가 계산 기준과 산출근거 내부에 배치되지 않았습니다.");

    comparisonItemCount = 12;
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelectorAll("#assetRows tr").length === 12);
    const collapsedComparison = await page.evaluate(() => ({
      visible: Array.from(document.querySelectorAll("#assetRows tr"))
        .filter((row) => getComputedStyle(row).display !== "none").length,
      button: document.getElementById("tableExpandBtn").textContent,
      expanded: document.getElementById("tableExpandBtn").getAttribute("aria-expanded"),
    }));
    expect(collapsedComparison.visible === 10 && collapsedComparison.button.includes("나머지 2개")
      && collapsedComparison.expanded === "false", "건물 비교 목록이 처음 10개로 접히지 않았습니다.");
    await page.click("#tableExpandBtn");
    expect(await page.locator("#assetRows tr:visible").count() === 12
      && await page.getAttribute("#tableExpandBtn", "aria-expanded") === "true",
    "건물 비교 목록의 나머지 항목이 펼쳐지지 않았습니다.");
    await page.click("#tableExpandBtn");
    expect(await page.locator("#assetRows tr:visible").count() === 10
      && await page.getAttribute("#tableExpandBtn", "aria-expanded") === "false",
    "건물 비교 목록이 다시 10개로 접히지 않았습니다.");
    comparisonItemCount = 6;

    incompleteSelected = true;
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      if (window.__analysisChartLayout) window.__analysisChartLayout.ready = false;
      window.dispatchEvent(new CustomEvent("livingstay:auth", { detail: { loggedIn: true } }));
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
    const operationActionsBeforeInput = await page.evaluate(() => ({
      count: document.querySelectorAll("#operationReportActions .am-btn").length,
      labels: document.getElementById("operationReportActions")?.textContent || "",
    }));
    expect(operationActionsBeforeInput.count === 4
      && operationActionsBeforeInput.labels.includes("상세 페이지")
      && operationActionsBeforeInput.labels.includes("실거래 전부보기")
      && operationActionsBeforeInput.labels.includes("인쇄")
      && operationActionsBeforeInput.labels.includes("공유"),
      "숙박운영 자료 입력 전 공통 4개 버튼이 표시되지 않았습니다.");
    await page.setInputFiles("#operationFiles", {
      name: "operation.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("기간,OCC,객실매출,판매객실 수\n2026-01,74,16200000,100"),
    });
    await page.waitForFunction(() => {
      const state = window.__operationAnalysisState;
      return state && state.selectedName === "선택 테스트 자산" && state.roomCount === 200
        && state.occ === 50 && state.adr === 162000 && state.benchmarkCount === 6
        && document.getElementById("operationFileStatus").textContent.includes("자동 인식 완료");
    });
    await page.waitForTimeout(80);
    const uploadedOperationResult = await page.evaluate(() => ({
      roomCount: document.getElementById("operationRoomCount").textContent,
      appliedRoomCount: document.getElementById("operationRoomCountInput").value,
      detail: document.getElementById("operationDetail").textContent,
      adrBaseline: document.getElementById("operationAdrBaseline").textContent,
      occBaseline: document.getElementById("operationOccBaseline").textContent,
      uploadStatus: document.getElementById("operationFileStatus").textContent,
      renderState: window.__operationAnalysisState,
    }));
    await page.fill("#operationRoomCountInput", "180");
    const defaultOperationName = await page.inputValue("#operationBusinessName");
    await page.fill("#operationBusinessName", "사용자 수정 상호");
    await page.waitForFunction(() => window.__operationAnalysisState
      && window.__operationAnalysisState.roomCount === 180
      && window.__operationAnalysisState.selectedName === "사용자 수정 상호");
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
      occBaseline: document.getElementById("operationOccBaseline").textContent,
      uploadStatus: document.getElementById("operationFileStatus").textContent,
      renderState: window.__operationAnalysisState,
      hiddenFilters: document.getElementById("analysisFilter") === null,
      operationLayout: window.__operationChartLayout,
      operationName: document.getElementById("operationBusinessName").value,
    }));
    expect(operationResult.operationVisible && operationResult.propertyHidden && operationResult.selectedTab === "true",
      "운영분석 탭 전환 상태가 올바르지 않습니다.");
    expect(operationResult.roomCount.includes("200실"), "선택 영업신고 업소의 객실 수가 운영분석에 자동 적용되지 않았습니다.");
    expect(uploadedOperationResult.roomCount.includes("200실")
      && uploadedOperationResult.appliedRoomCount === "200"
      && uploadedOperationResult.detail.includes("선택 테스트 자산")
      && uploadedOperationResult.detail.includes("200실")
      && uploadedOperationResult.detail.includes("81,000원")
      && uploadedOperationResult.detail.includes("자동분석"),
      `업로드 후 선택 건물 기준 운영분석 결과가 유지되지 않았습니다: ${uploadedOperationResult.detail}`);
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
    expect(uploadedOperationResult.adrBaseline.includes("원")
      && uploadedOperationResult.occBaseline.includes("%")
      && uploadedOperationResult.uploadStatus.includes("OCC 50% 자동계산")
      && uploadedOperationResult.uploadStatus.includes("객실매출 502,200,000원")
      && uploadedOperationResult.renderState.selectedName === "선택 테스트 자산"
      && uploadedOperationResult.renderState.roomCount === 200 && operationResult.hiddenFilters,
      "지역 평균 기준선 또는 운영분석의 불필요한 주소 필터 숨김이 적용되지 않았습니다.");
    expect(operationResult.appliedRoomCount === "180"
      && operationResult.renderState.roomCount === 180
      && operationResult.renderState.occ === 55.56
      && operationResult.detail.includes("180실"),
      "자동 입력된 신고 객실 수를 사용자가 임의 수정할 수 없습니다.");
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
        - operationResult.operationLayout.chartCenterY) < 0.6
      && operationResult.operationLayout.quadrantBoxes.length === 4
      && Math.abs(operationResult.operationLayout.quadrantBoxes[0].left
        + operationResult.operationLayout.quadrantBoxes[0].width
        - operationResult.operationLayout.baselinePixelX) < 0.6
      && Math.abs(operationResult.operationLayout.quadrantBoxes[0].top
        + operationResult.operationLayout.quadrantBoxes[0].height
        - operationResult.operationLayout.baselinePixelY) < 0.6,
    "운영분석의 회색 비교점 또는 선택 건물의 큰 점멸 표시가 없습니다.");
    await expectSinglePageReport(page, "operation", "숙박운영분석", true);
    await page.click("#operationRentalGuide");
    expect(await page.getAttribute("#rentalTab", "aria-selected") === "true"
      && !await page.locator("#rentalAnalysis").evaluate((el) => el.classList.contains("hidden")),
      "장기임대 안내에서 임대수익분석으로 이동하지 못했습니다.");
    await page.click("#operationTab");
    uploadHasOccupancyBasis = false;
    await page.setInputFiles("#operationFiles", {
      name: "missing-period.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("객실매출,판매객실 수\n16200000,100"),
    });
    await page.waitForFunction(() => {
      const status = document.getElementById("operationFileStatus").textContent;
      return !document.getElementById("operationOcc").value
        && status.includes("운영분석 보류") && status.includes("OCC 계산 불가");
    });
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}&mode=rental`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.getElementById("rentalBuildingName").textContent === "선택 테스트 자산");
    await page.waitForFunction(() => document.querySelectorAll("#rentalUnitAreaOptions option").length === 5);
    const areaOptions = await page.locator("#rentalUnitAreaOptions option").evaluateAll((options) =>
      options.map((option) => option.value));
    expect(areaOptions.join("|") === "18.1㎡|18.2㎡|18.3㎡|21.2㎡|32.5㎡"
      && await page.locator("#rentalUnitArea").inputValue() === "",
      "임대수익분석 전용면적 목록이 중복 없이 ㎡ 단위로 모두 표시되어야 합니다.");
    await page.fill("#rentalUnitArea", "32.5");
    await page.waitForFunction(() => document.getElementById("rentalMarketPrice").value === "9876");
    const automaticMarketPrice = await page.evaluate(() => ({
      area: document.getElementById("rentalUnitArea").value,
      price: document.getElementById("rentalMarketPrice").value,
      hint: document.getElementById("rentalMarketPriceHint").textContent,
      source: document.getElementById("rentalMarketPrice").dataset.valueSource,
    }));
    expect(automaticMarketPrice.area === "32.5"
      && automaticMarketPrice.price === "9876"
      && automaticMarketPrice.hint.includes("2026.08.19")
      && automaticMarketPrice.hint.includes("표본 3건")
      && automaticMarketPrice.hint.includes("중앙값")
      && automaticMarketPrice.source === "automatic"
      && rentalMarketRequest.includes("area_sqm=32.5"),
      "선택 면적의 최근 호실 실거래 중앙값과 근거가 자동 반영되지 않았습니다.");
    await page.click("#rentalMarketEvidenceSummary");
    const marketEvidence = await page.evaluate(() => ({
      summary: document.getElementById("rentalMarketEvidenceSummary").textContent,
      rows: Array.from(document.querySelectorAll(".rental-market-evidence-row")).map((row) => row.textContent),
    }));
    expect(marketEvidence.summary.includes("3건")
      && marketEvidence.rows.length === 3
      && marketEvidence.rows[0].includes("동일 면적")
      && marketEvidence.rows[0].includes("2026.08.19")
      && marketEvidence.rows[0].includes("32.5㎡")
      && marketEvidence.rows[0].includes("10,000만원"),
      "자동 기준가에 사용된 공개 거래일·면적·가격 표본을 펼쳐 확인할 수 없습니다.");
    await page.fill("#rentalUnitArea", "99");
    await page.waitForFunction(() =>
      document.getElementById("rentalMarketPriceHint").textContent.includes("자료 부족"));
    expect(await page.inputValue("#rentalMarketPrice") === ""
      && (await page.getAttribute("#rentalMarketPrice", "data-value-source")) === "unavailable",
      "실거래 표본이 부족할 때 임의 자동값 대신 자료 부족 사유가 표시되지 않았습니다.");
    await page.fill("#rentalUnitArea", "32.5");
    await page.waitForFunction(() => document.getElementById("rentalMarketPrice").value === "9876");
    await page.fill("#rentalPurchasePrice", "10000");
    const acquisitionCosts = await page.evaluate(() => ({
      acquisitionTax: document.getElementById("rentalAcquisitionTax").value,
      brokerFee: document.getElementById("rentalBrokerFee").value,
    }));
    expect(acquisitionCosts.acquisitionTax === "460" && acquisitionCosts.brokerFee === "90",
      "매입가 기준 취득세 4.6%와 중개보수 0.9%가 자동 계산되지 않았습니다.");
    await page.fill("#rentalMarketPrice", "11000");
    expect((await page.textContent("#rentalMarketPriceHint")).includes("사용자 수정값 사용 중"),
      "자동 실거래 기준가를 수정했을 때 사용자 수정값으로 구분되지 않습니다.");
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
      vacancyMonths: document.getElementById("rentalVacancyMonths").value,
      vacancyRate: document.getElementById("rentalVacancyRate").value,
      vacancyHint: document.getElementById("rentalVacancyMonthsHint").textContent,
      positioning: document.getElementById("rentalPositioning").textContent,
      peerCount: document.querySelectorAll("#rentalPositioning .positioning-peer").length,
      calculation: window.__rentalAnalysisResult,
    }));
    expect(rentalResult.visible && rentalResult.selectedTab === "true",
      "임대수익분석 탭이 선택 상태로 표시되지 않았습니다.");
    expect(Number(rentalResult.tax) > 0 && rentalResult.text.includes("자기자본 수익률")
      && rentalResult.text.includes("DSCR") && rentalResult.text.includes("현재 실거래 기준 수익률"),
      "재산세·대출·현재 실거래를 반영한 임대수익 결과가 없습니다.");
    expect(rentalResult.text.includes("내가 실제 넣은 돈 대비 연간 수익")
      && rentalResult.text.includes("공실·운영비를 뺀 실제 수익률")
      && rentalResult.text.includes("임대수익으로 대출을 갚을 수 있는 정도"),
      "임대수익 전문용어 옆의 쉬운 설명이 누락됐습니다.");
    expect(Math.abs(rentalResult.calculation.annualRent - 600) < 0.01
      && Math.abs(rentalResult.calculation.debtService - 270) < 0.01
      && Math.abs(rentalResult.calculation.invested - 4250) < 0.01
      && rentalResult.vacancyMonths === ""
      && rentalResult.vacancyRate === "10.0"
      && rentalResult.vacancyHint.includes("R-ONE 평균 1.2개월")
      && rentalResult.positioning.includes("수익개선 검토")
      && rentalResult.positioning.includes("지역 평균 가정")
      && rentalResult.positioning.includes("동일 자산군이 아닌")
      && rentalResult.positioning.includes("2026년 2분기")
      && rentalResult.peerCount === 2
      && rentalResult.calculation.vacancySource === "rone",
      "보증금·월세·대출을 반영한 임대수익 계산값이 올바르지 않습니다.");
    await page.fill("#rentalVacancyMonths", "3");
    await page.click("#rentalCalculate");
    const userVacancy = await page.evaluate(() => ({
      rate: document.getElementById("rentalVacancyRate").value,
      positioning: document.getElementById("rentalPositioning").textContent,
      calculation: window.__rentalAnalysisResult,
    }));
    expect(userVacancy.rate === "25.0"
      && userVacancy.positioning.includes("사용자 입력")
      && userVacancy.positioning.includes("R-ONE")
      && userVacancy.calculation.vacancySource === "user"
      && Math.abs(userVacancy.calculation.vacancyRate - 25) < 0.01,
      "사용자 공실 개월 입력이 R-ONE 평균보다 우선 적용되지 않았습니다.");
    await expectSinglePageReport(page, "rental", "임대수익분석", false);
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
    await page.waitForFunction(() => document.querySelectorAll("#assetRows tr").length === 6);
    const transactionTrend = await page.evaluate(() => {
      const card = document.getElementById("transactionTrendCard");
      const canvas = document.getElementById("transactionTrendChart");
      const rect = canvas.getBoundingClientRect();
      return {
        visible: getComputedStyle(card).display !== "none",
        width: rect.width,
        height: rect.height,
        months: window.__analysisTransactionTrend?.months || 0,
        area: window.__analysisTransactionTrend?.area || "",
        options: Array.from(document.getElementById("transactionAreaSelect").options).map(option => option.value),
        lineLabel: Chart.getChart(canvas)?.data.datasets.find(dataset => dataset.type === "line")?.label,
        lineValues: Chart.getChart(canvas)?.data.datasets.find(dataset => dataset.type === "line")?.data || [],
        priceMin: Chart.getChart(canvas)?.options.scales.price.min,
        priceMax: Chart.getChart(canvas)?.options.scales.price.max,
      };
    });
    expect(transactionTrend.visible && transactionTrend.width > 240
      && transactionTrend.height >= 200 && transactionTrend.months > 0
      && transactionTrend.area === "100.0"
      && transactionTrend.options.join("|") === "80.0|100.0"
      && transactionTrend.lineLabel === "거래금액(만원)"
      && transactionTrend.lineValues.includes(41000)
      && !transactionTrend.lineValues.includes(410)
      && transactionTrend.priceMin < Math.min(...transactionTrend.lineValues.filter(Number.isFinite))
      && transactionTrend.priceMax > Math.max(...transactionTrend.lineValues.filter(Number.isFinite)),
      `모바일 실거래 추이 그래프가 정상 표시되지 않았습니다. ${JSON.stringify(transactionTrend)}`);
    await page.selectOption("#transactionAreaSelect", "80.0");
    await page.waitForFunction(() => window.__analysisTransactionTrend?.area === "80.0");
    const selectedAreaTrend = await page.evaluate(() => ({
      subtitle: document.getElementById("transactionTrendSubtitle").textContent,
      rows: Array.from(document.querySelectorAll("#selectedTransactionRows tr")).map(row => row.textContent),
      values: Chart.getChart("transactionTrendChart").data.datasets.find(dataset => dataset.type === "line").data,
    }));
    expect(selectedAreaTrend.subtitle.includes("80.0㎡")
      && selectedAreaTrend.rows.every(row => row.includes("80㎡"))
      && selectedAreaTrend.values.includes(32000)
      && selectedAreaTrend.values.includes(36000),
      `전유면적 선택이 그래프와 최근 거래표에 함께 반영되지 않았습니다. ${JSON.stringify(selectedAreaTrend)}`);
    const selectedTransactions = await page.evaluate(() => ({
      visible: !document.getElementById("selectedTransactionCard").classList.contains("hidden"),
      title: document.getElementById("selectedTransactionTitle").textContent,
      rows: Array.from(document.querySelectorAll("#selectedTransactionRows tr")).map((row) => row.textContent),
      beforeRecommendations: !!(document.getElementById("selectedTransactionCard")
        .compareDocumentPosition(document.getElementById("recommendationCard")) & Node.DOCUMENT_POSITION_FOLLOWING),
    }));
    expect(selectedTransactions.visible && selectedTransactions.title.includes("선택 테스트 자산")
      && selectedTransactions.rows.length > 0 && selectedTransactions.rows.length <= 5
      && selectedTransactions.rows[0].includes("만원") && selectedTransactions.beforeRecommendations,
      `선택 건물 최근 실거래표가 그래프와 가격 매력 후보 사이에 표시되지 않았습니다. ${JSON.stringify(selectedTransactions)}`);
    await page.evaluate(() => window.livingstayRenderAnalysisPrintReport());
    await page.emulateMedia({ media: "print" });
    const printReport = await page.evaluate(() => {
      const report = document.getElementById("printReport");
      const rect = report.getBoundingClientRect();
      return {
        display: getComputedStyle(report).display,
        mode: report.dataset.mode,
        zones: report.querySelectorAll(".print-zone").length,
        title: document.getElementById("printReportTitle").textContent,
        graphImage: document.querySelector("#printGraph .print-chart-image")?.getAttribute("src") || "",
        reportHeight: rect.height,
        recommendationDisplay: getComputedStyle(document.getElementById("recommendationCard")).display,
        exampleIncluded: document.getElementById("printBasis").textContent.includes("가상 산정 예시"),
        transactionHeaders: Array.from(document.querySelectorAll("#printTransactionTable th")).map(th => th.textContent),
        transactionRows: Array.from(document.querySelectorAll("#printTransactionTable tbody tr")).map(row => row.textContent),
        transactionCellsNoWrap: Array.from(document.querySelectorAll("#printTransactionTable th,#printTransactionTable td")).every(cell => getComputedStyle(cell).whiteSpace === "nowrap"),
      };
    });
    const printPdf = await page.pdf({ format: "A4", printBackground: true, displayHeaderFooter: false });
    const printPageCount = (printPdf.toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length;
    expect(printReport.display === "block" && printReport.mode === "property"
      && printReport.zones === 5 && printReport.title.includes("부동산투자분석")
      && printReport.graphImage.startsWith("data:image/png")
      && printReport.reportHeight <= 1075
      && printReport.recommendationDisplay === "none"
      && !printReport.exampleIncluded
      && printReport.transactionHeaders.join("|") === "계약일|면적|층|거래금액"
      && printReport.transactionRows.every(row => row.includes("80㎡") && row.includes("층"))
      && printReport.transactionCellsNoWrap
      && printPageCount === 1,
      `부동산투자분석 인쇄보고서가 A4 한 장·5개 존으로 구성되지 않았습니다. pages=${printPageCount} report=${JSON.stringify(printReport)}`);
    await page.emulateMedia({ media: "screen" });

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
      && await page.inputValue("#rentalVacancyMonths") === ""
      && await page.inputValue("#rentalVacancyRate") === "",
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
