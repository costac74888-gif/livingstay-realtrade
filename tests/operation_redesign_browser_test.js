const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const BUILDING_ID = 101;
const LOW_ADR_BUILDING_ID = 102;
const BUILDING_B_ID = 103;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function near(actual, target, tolerance = 0.05) {
  return Number.isFinite(actual) && Math.abs(actual - target) <= tolerance;
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

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function operationFixture() {
  const items = [
    ["수원시", 135000, 66],
    ["성남시", 154000, 70],
    ["용인시", 148000, 68],
    ["고양시", 141000, 64],
    ["화성시", 132000, 63],
    ["평택시", 119000, 58],
  ].map(([region, adr, occ]) => ({
    region,
    adr,
    occ,
    revpar: Math.round(adr * occ / 100),
    foreign: 4,
  }));
  return {
    ok: true,
    sido: "경기",
    sgg: "수원시",
    source: { name: "한국호텔업협회 호텔업 운영현황", reference_year: 2024 },
    items,
  };
}

function lowAdrOperationFixture() {
  return {
    ok: true,
    sido: "경기",
    sgg: "수원시",
    source: { name: "한국호텔업협회 호텔업 운영현황", reference_year: 2024 },
    items: [
      { region: "수원시", adr: 80000, occ: 66, revpar: 52800, foreign: 4 },
      { region: "성남시", adr: 92000, occ: 68, revpar: 62560, foreign: 5 },
      { region: "용인시", adr: 105000, occ: 65, revpar: 68250, foreign: 3 },
      { region: "고양시", adr: 72000, occ: 60, revpar: 43200, foreign: 2 },
      { region: "오류 비교점", adr: -12000, occ: 55, revpar: -6600, foreign: 0 },
    ],
  };
}

function buildingBOperationFixture() {
  return {
    ok: true,
    sido: "경기",
    sgg: "성남시",
    source: { name: "B 건물 전용 운영 통계", reference_year: 2025 },
    items: [
      { region: "성남시", adr: 154000, occ: 70, revpar: 107800, foreign: 5 },
      { region: "분당구", adr: 161000, occ: 72, revpar: 115920, foreign: 6 },
      { region: "수정구", adr: 143000, occ: 67, revpar: 95810, foreign: 4 },
    ],
  };
}

async function installApiMocks(page, calls, options = {}) {
  await page.route("**/v2/maps/**", (route) => route.abort());
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({ method: request.method(), path: url.pathname, search: url.search });
    if (url.pathname === "/api/auth/me") {
      return json(route, { logged_in: true, user: { id: 1, name: "운영 개편 테스트" } });
    }
    if (url.pathname === "/api/analysis/assets") {
      return json(route, {
        generated_at: "2026-09-24T00:00:00Z",
        baselines: { tourism_demand_index: 50, peer_price_gap: 0 },
        filters: { sidos: [], sggs: [], lodging_types: [], period_options: [] },
        summary: { registered_buildings: 1, transaction_count: 0, analyzed_buildings: 1 },
        methodology: { comparison_basis: {} },
        items: [{
          building_id: BUILDING_ID,
          name: "엠제이스톤 레지던스",
          lodging_type: "생활숙박시설",
          sido: "경기도",
          sgg: "수원시",
          address: "경기도 수원시 테스트로 1",
          lat: 37.2636,
          lng: 127.0286,
          tourism_demand_index: 50,
          peer_price_gap: 0,
          transaction_count: 0,
        }, {
          building_id: LOW_ADR_BUILDING_ID,
          name: "저단가 기준선 테스트 빌딩",
          lodging_type: "생활숙박시설",
          sido: "경기도",
          sgg: "수원시",
          address: "경기도 수원시 테스트로 2",
          lat: 37.26,
          lng: 127.03,
          tourism_demand_index: 50,
          peer_price_gap: 0,
          transaction_count: 0,
        }, {
          building_id: BUILDING_B_ID,
          name: "B운영 테스트 빌딩",
          lodging_type: "생활숙박시설",
          sido: "경기도",
          sgg: "성남시",
          address: "경기도 성남시 테스트로 3",
          lat: 37.42,
          lng: 127.13,
          tourism_demand_index: 50,
          peer_price_gap: 0,
          transaction_count: 0,
        }],
        candidates: { price: [], confidence: [], urgent: [] },
      });
    }
    if (new RegExp(`^/api/building/(${BUILDING_ID}|${LOW_ADR_BUILDING_ID}|${BUILDING_B_ID})$`).test(url.pathname)) {
      const id = Number(url.pathname.split("/").pop());
      const name = id === BUILDING_ID ? "엠제이스톤 레지던스"
        : id === LOW_ADR_BUILDING_ID ? "저단가 기준선 테스트 빌딩" : "B운영 테스트 빌딩";
      return json(route, {
        building_id: id,
        building_name: name,
        display_building_name: name,
        road_address: `경기도 ${id === BUILDING_B_ID ? "성남시" : "수원시"} 테스트로 ${id === BUILDING_ID ? "1" : id === LOW_ADR_BUILDING_ID ? "2" : "3"}`,
        sido: "경기도",
        sido_nm: "경기",
        sgg_nm: id === BUILDING_B_ID ? "성남시" : "수원시",
        lodging_type: "생활숙박시설",
        lodging_room_total: id === BUILDING_B_ID ? 88 : 145,
        lodgings: [{
          biz_name: name,
          room_count: id === BUILDING_B_ID ? 88 : 145,
        }],
      });
    }
    if (/^\/api\/building\/\d+\/area-types$/.test(url.pathname)) {
      return json(route, { ok: true, items: [], sqms: [] });
    }
    if (url.pathname === "/api/analysis/operation-benchmarks") {
      const id = Number(url.searchParams.get("building_id"));
      return json(route, id === LOW_ADR_BUILDING_ID ? lowAdrOperationFixture()
        : id === BUILDING_B_ID ? buildingBOperationFixture() : operationFixture());
    }
    if (url.pathname === "/api/analysis/building-search") {
      return json(route, {
        items: [{
          building_id: BUILDING_B_ID,
          name: "B운영 테스트 빌딩",
          lodging_type: "생활숙박시설",
          address: "경기도 성남시 테스트로 3",
        }],
      });
    }
    if (url.pathname === "/api/analysis/rental-benchmark") {
      if (options.roneDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.roneDelayMs));
      }
      const national = {
        region_code: "00", region_level: "national", region_name: "전국",
        income_yield: 6.02, vacancy_rate: 8.4746, property_type: "officetel",
        property_type_name: "오피스텔",
        period: "2026-07-01", vacancy_period: "2026-04-01",
      };
      return json(route, {
        ok: true,
        available: true,
        benchmark: national,
        items: [national],
        source: { provider: "한국부동산원 R-ONE", status: "ready" },
      });
    }
    if (url.pathname === "/api/analysis/operation-upload") {
      return json(route, {
        ok: true,
        result: {
          period_start: "2026-01-01", period_end: "2026-01-31",
          adr: 162000, occ: 74, room_revenue: 502200000, sold_rooms: 3330,
          occupancy_days: 30,
        },
        processed_file_count: 1,
        retained: false,
      });
    }
    if (url.pathname === "/api/favorites/mine") return json(route, { items: [] });
    if (url.pathname.endsWith("/photos")) return json(route, { photos: [] });
    if (request.method() !== "GET" && request.method() !== "HEAD") {
      return json(route, { ok: true, items: [] });
    }
    return json(route, { ok: true, items: [] });
  });
}

async function valueFromLabel(page, field, value) {
  await page.locator(`[data-operation-value="${field}"]`).click();
  const input = page.locator(`[data-operation-value="${field}"] input`);
  await input.fill(String(value));
  await input.press("Enter");
  await page.waitForTimeout(80);
}

async function rentalValueFromLabel(page, field, value) {
  await page.locator(`[data-rental-value="${field}"]`).click();
  const input = page.locator(`[data-rental-value="${field}"] input`);
  await input.fill(String(value));
  await input.press("Enter");
  await page.waitForTimeout(80);
}

async function ready(page) {
  await page.waitForFunction(() => window.__operationAnalysisState?.ready === true, null, {
    timeout: 20000,
  });
}

async function awaitScreenshotFonts(page) {
  const fontState = await page.evaluate(async () => {
    await document.fonts.ready;
    const faces = Array.from(document.fonts).map((face) => ({
      family: face.family.replace(/["']/g, ""),
      status: face.status,
    }));
    return {
      status: document.fonts.status,
      notoLoaded: faces.some((face) => /Noto Sans KR/i.test(face.family) && face.status === "loaded"),
    };
  });
  if (!fontState.notoLoaded) {
    console.warn("Korean web font unavailable in this environment; screenshot uses browser fallback font.");
  }
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromiumExecutable(),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    permissions: ["clipboard-read", "clipboard-write"],
  });
  const page = await context.newPage();
  const errors = [];
  const calls = [];
  page.on("dialog", (dialog) => dialog.accept());
  page.on("pageerror", (error) => errors.push(error.message));
  await installApiMocks(page, calls);

  try {
    const start = new URL("/analysis", BASE_URL);
    start.searchParams.set("building_id", BUILDING_ID);
    start.searchParams.set("mode", "operation");
    start.searchParams.set("rent", "200");
    const response = await page.goto(start.toString(), { waitUntil: "domcontentloaded" });
    expect(response && response.ok(), "운영 분석 화면을 열지 못했습니다.");
    await ready(page);

    const first = await page.evaluate(() => {
      const state = window.__operationAnalysisState;
      const chart = Chart.getChart(document.getElementById("operationChart"));
      const own = chart?.data.datasets.flatMap((set) => set.data)
        .find((point) => point.item?.selected);
      return {
        state,
        own,
        content: document.getElementById("operationAnalysis").textContent,
        assumptions: Array.from(document.querySelectorAll("#operationSliders [data-operation-assumption]"))
          .map((badge) => `${badge.closest("[data-operation-row]")?.dataset.operationRow}:${badge.textContent.trim()}`),
        sliderCount: document.querySelectorAll("#operationSliders [data-operation-slider]").length,
        metricCount: document.querySelectorAll("#operationCoreMetrics .operation-metric").length,
        costShare: document.getElementById("operationCostShare")?.textContent || "",
        source: document.querySelector("#operationAnalysis .operation-benchmark-note")?.textContent || "",
        sliderLimits: Object.fromEntries(Array.from(document.querySelectorAll(
          "#operationSliders .operation-slider-bounds",
        )).map((node) => [node.closest("[data-operation-row]")?.dataset.operationRow,
          Array.from(node.querySelectorAll("[data-slider-bound]")).map((child) => child.textContent.trim())])),
        emptyPanel: document.querySelector("#operationAnalysis .detail-empty"),
        resultsColumn: document.querySelector(".operation-results-column")?.getBoundingClientRect().toJSON(),
        sensitivityBox: document.getElementById("operationSensitivity").getBoundingClientRect().toJSON(),
        verdictBox: document.getElementById("operationVerdict").getBoundingClientRect().toJSON(),
      };
    });
    expect(first.state.roomCount === 145, "신고 객실 수 145실이 적용되지 않았습니다.");
    expect(first.state.baseAdr === 135000 && first.state.baseOcc === 66,
      "지역 수원시 호텔 비교값의 정확 기준선이 적용되지 않았습니다.");
    expect(first.state.opexRatio === 27 && first.state.mgmtFeeRatio === 30,
      "비용 가정값 27%·30%이 적용되지 않았습니다.");
    expect(near(first.state.monthlyDays, 30.4, 0.001), "월 일수 30.4 정의값이 적용되지 않았습니다.");
    expect(first.costShare.includes("48.9%") && first.costShare.includes("51.1%"),
    "실질 공제율 48.9%와 소유주 몫 51.1%가 일치하지 않습니다.");
    expect(first.sliderCount === 4 && first.metricCount === 5
      && !first.content.includes("비교 조건"),
      "운영·비용 4개 슬라이더만 보여야 하며 비교 조건 가로바는 없어야 합니다.");
    expect(first.sliderLimits.adr?.length === 2
      && first.sliderLimits.adr[0] === "1만원"
      && first.sliderLimits.adr[1] === "200만원"
      && first.sliderLimits.opexRatio[1] === "80%",
    `ADR·운영경비율의 단위/한도가 표시되지 않았습니다: ${JSON.stringify(first.sliderLimits)}`);
    expect(first.assumptions.length >= 4, "지역 ADR/OCC 및 비용 기본값 가정 배지가 표시되지 않습니다.");
    expect(!first.emptyPanel, "자료 입력 전 빈 결과 패널이 남아 있습니다.");
    expect(first.source.includes("호텔") && first.source.includes("생활숙박"),
      "호텔업 통계와 생활숙박 위탁운영 실적 간의 차이를 고지하지 않았습니다.");
    expect(first.verdictBox.top >= first.sensitivityBox.bottom
      && first.verdictBox.top - first.sensitivityBox.bottom < 36,
    `운영 판정 카드가 민감도 표 바로 아래에 배치되지 않았습니다: ${JSON.stringify({
      sensitivity: first.sensitivityBox, verdict: first.verdictBox,
    })}`);
    expect(near(first.state.monthlyRevenue / 10000, 270.864, 0.08),
      `월 매출 계산이 틀렸습니다: ${first.state.monthlyRevenue}`);
    expect(near(first.state.monthlyProfit / 10000, 197.73, 0.1),
      `운영경비를 차감한 매출이익 계산이 틀렸습니다: ${first.state.monthlyProfit}`);
    expect(near(first.state.monthlyNet / 10000, 138.41, 0.1),
      `위탁수수료 차감 후 월 순수익 계산이 틀렸습니다: ${first.state.monthlyNet}`);
    expect(first.own?.item?.selected, "내 호실이 차트 데이터에 반영되지 않았습니다.");
    const desktopAxis = await page.evaluate(() => window.__operationChartLayout);
    expect(desktopAxis?.ready
      && Math.abs(desktopAxis.baselinePixelX - desktopAxis.chartCenterX) < 2
      && Math.abs(desktopAxis.baselinePixelY - desktopAxis.chartCenterY) < 2,
    `데스크톱 기준선이 차트 중앙에 있지 않습니다: ${JSON.stringify(desktopAxis)}`);
    const datasetNames = await page.evaluate(() => Chart.getChart(document.getElementById("operationChart"))
      ?.data.datasets.map((set) => set.label || set.key || "").join("|") || "");
    expect(datasetNames.includes("매출선") || datasetNames.includes("RevPAR"),
      "차트에 지역·내 등수익 곡선이 없습니다.");

    if (process.env.SKIP_OPERATION_SCREENSHOTS !== "1") {
      fs.mkdirSync("screenshots", { recursive: true });
      await awaitScreenshotFonts(page);
      await page.screenshot({ path: "screenshots/operation-desktop-1280.png", fullPage: true });
      await page.locator("#operationSliders").screenshot({ path: "screenshots/operation-slider-controls-1280.png" });
      await page.locator(".operation-results-column").screenshot({
        path: "screenshots/slider-operation-verdict-1280.png",
      });
    }
    const adrTrack = page.locator('[data-operation-slider="adr"]');
    expect(await adrTrack.getAttribute("min") === "0"
      && await adrTrack.getAttribute("max") === "600"
      && await adrTrack.getAttribute("step") === "1",
    "ADR 가로바의 고정 위치 눈금이 잘못되었습니다.");
    for (const [tick, amount] of [[0, 10000], [200, 100000], [600, 2000000]]) {
      await adrTrack.evaluate((slider, next) => {
        slider.value = String(next);
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      }, tick);
      await page.waitForFunction((expected) => window.__operationAnalysisState?.adr === expected, amount);
      expect(Number(await page.locator("#operationAdr").inputValue()) === amount
        && await adrTrack.getAttribute("aria-valuetext") === `${amount.toLocaleString("ko-KR")}원`,
      `ADR 위치 ${tick}에서 ${amount}원이 적용되지 않았습니다.`);
    }
    await valueFromLabel(page, "adr", 50000);
    expect(Number(await adrTrack.inputValue()) === 89
      && await adrTrack.getAttribute("max") === "600",
    "ADR 5만원은 첫 1/3 구간 안에 위치하고 직접입력 후 범위가 고정돼야 합니다.");

    const anchor = await page.evaluate(() => document.querySelector("#operationCoreMetrics")
      .getBoundingClientRect().toJSON());
    const selected = await page.evaluate(() => ({
      result: window.__operationAnalysisState,
      metrics: document.getElementById("operationCoreMetrics").textContent,
      table: document.getElementById("operationSensitivity").textContent,
      tableCurrentNet: document.getElementById("operationSensitivity").dataset.currentMonthlyNet,
      rows: document.querySelectorAll("#operationSensitivity tbody tr").length,
      columns: document.querySelectorAll("#operationSensitivity thead th").length,
      selectedCell: document.querySelector("#operationSensitivity td.selected")?.textContent.trim(),
    }));
    expect(selected.rows === 7 && selected.columns === 8, "ADR×OCC 민감도 표가 7×7 형태가 아닙니다.");
    expect(selected.selectedCell && Number(selected.selectedCell.replace(/[^\d.-]/g, "")) > 0,
      "민감도 표의 현재 입력 교차 칸이 표시되지 않습니다.");
    expect(selected.tableCurrentNet === String(selected.result.monthlyNet),
      `운영 민감도 표의 현재 칸 기준값이 핵심 월 순수익과 다릅니다: ${selected.tableCurrentNet} / ${selected.result.monthlyNet}`);

    await valueFromLabel(page, "adr", 162000);
    await valueFromLabel(page, "occ", 74);
    const direct = await page.evaluate(() => ({
      state: window.__operationAnalysisState,
      adrSlider: Number(document.querySelector('[data-operation-slider="adr"]').value),
      occSlider: Number(document.querySelector('[data-operation-slider="occ"]').value),
    }));
    expect(direct.state.adr === 162000 && direct.adrSlider === 213 && direct.state.occ === 74,
      "ADR 정확값과 1만원 단위 근접 슬라이더 위치를 보존하지 못했습니다.");
    expect(direct.occSlider === 74, "OCC 직접 입력값이 정확한 슬라이더 위치에 반영되지 않았습니다.");

    await valueFromLabel(page, "adr", 180000);
    await valueFromLabel(page, "occ", 66.6);
    const isoMovement = await page.evaluate(() => {
      const chart = Chart.getChart(document.getElementById("operationChart"));
      const selected = chart?.data.datasets.find((set) => set.key === "selected")?.data[0];
      const curve = chart?.data.datasets.find((set) => set.key === "selectedRevpar");
      const curveRevpars = (curve?.data || []).map((point) => {
        const actualOcc = point.y <= 50
          ? 32 + (66 - 32) * point.y / 50
          : 66 + (100 - 66) * (point.y - 50) / 50;
        return point.x * actualOcc / 100;
      });
      return { state: window.__operationAnalysisState, selected, curveRevpars };
    });
    expect(near(isoMovement.state.revpar, direct.state.revpar, 0.1)
      && isoMovement.selected?.actualAdr === 180000
      && near(isoMovement.selected?.actualOcc, 66.6, 0.001)
      && isoMovement.curveRevpars.length > 0
      && isoMovement.curveRevpars.every((revpar) => near(revpar, isoMovement.state.revpar, 0.1)),
    "ADR 상승·OCC 하락의 등수익 곡선 이동에서 동일 RevPAR를 유지하지 못했습니다.");

    const initialNet = direct.state.monthlyNet;
    const initialDifference = direct.state.monthlyNet / 10000 - direct.state.compareRent;
    const initialGreen = await page.locator("#operationSensitivity td.above").count();
    await valueFromLabel(page, "mgmtFeeRatio", 20);
    const afterFee = await page.evaluate(() => window.__operationAnalysisState);
    const newGreen = await page.locator("#operationSensitivity td.above").count();
    expect(afterFee.monthlyNet > initialNet, "위탁수수료 30%→20% 조정 후 순수익이 증가하지 않았습니다.");
    expect(newGreen > initialGreen, "위탁수수료 하향 후 월세보다 유리한 민감도 셀이 늘지 않았습니다.");
    expect(initialDifference < 0 && afterFee.monthlyNet / 10000 - afterFee.compareRent > 0
      && afterFee.breakEvenOcc < isoMovement.state.breakEvenOcc,
    "위탁수수료 조정으로 월세 대비 부호와 손익 교차 OCC가 바뀌지 않았습니다.");

    await valueFromLabel(page, "adr", 60000);
    const impossible = await page.evaluate(() => ({
      result: window.__operationAnalysisState,
      verdict: document.getElementById("operationVerdict").textContent,
    }));
    expect(impossible.result.breakEvenOcc > 100
      && impossible.verdict.includes("100%"),
    "ADR 60,000원의 100% 초과 손익교차 OCC 경고가 없습니다.");

    await page.locator("#operationFiles").setInputFiles({
      name: "monthly.csv", mimeType: "text/csv",
      buffer: Buffer.from("date,adr,occ\n2026-01,162000,74\n"),
    });
    await page.waitForFunction(() => window.__operationAnalysisState?.adr === 162000
      && window.__operationAnalysisState?.occ === 74);
    const uploadedBadges = await page.locator(
      '#operationSliders [data-operation-row="adr"] [data-operation-assumption], #operationSliders [data-operation-row="occ"] [data-operation-assumption]',
    ).evaluateAll((badges) => badges.filter((badge) => !badge.classList.contains("hidden")).length);
    expect(uploadedBadges === 0, "업로드에서 확인된 ADR·OCC에 지역 평균 가정 배지가 남았습니다.");

    await page.setViewportSize({ width: 360, height: 800 });
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      card: document.getElementById("operationCoreMetrics").getBoundingClientRect().toJSON(),
      graph: document.getElementById("operationChartCard").getBoundingClientRect().toJSON(),
      chartLayout: window.__operationChartLayout,
      detailsClosed: Array.from(document.querySelectorAll("#operationAnalysis details"))
        .every((details) => !details.open),
      sliderTouchAction: getComputedStyle(document.querySelector('[data-operation-slider="adr"]')).touchAction,
      sliderRowHeight: document.querySelector('[data-operation-row="adr"]').getBoundingClientRect().height,
       endpointStyle: getComputedStyle(document.querySelector(
         '[data-operation-row="adr"] .operation-slider-bounds',
       )).fontSize,
    }));
    expect(mobile.scroll <= mobile.viewport && mobile.body <= mobile.viewport,
      `360px 모바일 가로 넘침: ${JSON.stringify(mobile)}`);
    expect(mobile.detailsClosed, "접이식 산출근거·TOP5·건물환산 세부가 기본으로 열려 있습니다.");
    expect(mobile.sliderTouchAction === "pan-y" && mobile.sliderRowHeight >= 44,
      `모바일 운영 슬라이더의 터치 영역·세로 스크롤 설정이 부족합니다: ${JSON.stringify(mobile)}`);
    expect(mobile.endpointStyle === "11px",
      `모바일 ADR 범위 글씨가 11px가 아닙니다: ${mobile.endpointStyle}`);
    expect(mobile.chartLayout
      && Math.abs(mobile.chartLayout.baselinePixelX - mobile.chartLayout.chartCenterX) < 2
      && Math.abs(mobile.chartLayout.baselinePixelY - mobile.chartLayout.chartCenterY) < 2,
    "모바일 ADR/OCC 기준선이 차트 한가운데에 배치되지 않았습니다.");
    if (process.env.SKIP_OPERATION_SCREENSHOTS !== "1") {
      await awaitScreenshotFonts(page);
      await page.screenshot({ path: "screenshots/operation-mobile-360.png", fullPage: true });
      await page.locator("#operationSliders").screenshot({ path: "screenshots/operation-slider-controls-360.png" });
    }

    await page.evaluate(() => window.livingstayRenderAnalysisPrintReport());
    const printed = await page.evaluate(() => ({
      overview: document.getElementById("printOverview").textContent,
      graph: document.getElementById("printGraph").textContent,
      image: document.querySelector("#printGraph .print-chart-image")?.getAttribute("src") || "",
      basis: document.getElementById("printBasis").textContent,
    }));
    expect(printed.overview.includes("ADR") && printed.overview.includes("OCC")
      && printed.overview.includes("운영경비율") && printed.overview.includes("위탁수수료율"),
    "인쇄 개요에서 여섯 입력 조건 및 가정 배지를 일반 텍스트로 출력하지 않습니다.");
    expect(printed.image.startsWith("data:image/png")
      && printed.graph.includes("민감도")
      && printed.graph.includes("건물 전체 환산")
      && printed.graph.includes("시군구"),
    "인쇄 미리보기에 차트·민감도·접이식 세부가 포함되지 않았습니다.");

    await valueFromLabel(page, "adr", 168000);
    await valueFromLabel(page, "occ", 72);
    await valueFromLabel(page, "opexRatio", 35);
    await valueFromLabel(page, "mgmtFeeRatio", 20);
    const beforeBuildingSwitch = await page.evaluate(() => ({
      state: window.__operationAnalysisState,
      uploadStatus: document.getElementById("operationFileStatus").textContent,
      source: window.__operationBenchmarkSource,
      rentalPurchase: document.getElementById("rentalPurchasePrice")?.value || "",
      rentalRent: document.getElementById("rentalMonthlyRent")?.value || "",
    }));
    expect(beforeBuildingSwitch.state.adr === 168000 && beforeBuildingSwitch.state.occ === 72
      && beforeBuildingSwitch.state.opexRatio === 35 && beforeBuildingSwitch.state.mgmtFeeRatio === 20
      && beforeBuildingSwitch.uploadStatus.includes("162,000"),
    `건물 전환 전 A의 입력·업로드 상태가 준비되지 않았습니다: ${JSON.stringify(beforeBuildingSwitch)}`);
    await page.locator("#buildingSearch").fill("B운영 테스트 빌딩");
    await page.locator(`#searchResults [data-id="${BUILDING_B_ID}"]`).waitFor({ timeout: 10000 });
    await page.locator(`#searchResults [data-id="${BUILDING_B_ID}"]`).click();
    await page.locator("#buildingSelectionApply").click();
    await page.waitForFunction((expectedId) => window.__operationAnalysisState?.ready === true
      && window.__operationAnalysisState?.roomCount === 88
      && window.__operationAnalysisState?.baseAdr === 154000
      && new URLSearchParams(location.search).get("building_id") === String(expectedId),
    BUILDING_B_ID, { timeout: 20000 });
    await page.waitForTimeout(350);
    const afterBuildingSwitch = await page.evaluate(() => {
      const chart = Chart.getChart(document.getElementById("operationChart"));
      const comparison = chart?.data.datasets.find((set) => set.key === "comparison")?.data || [];
      return {
        state: window.__operationAnalysisState,
        building: window.__operationAnalysisBuilding,
        source: window.__operationBenchmarkSource,
        region: window.__operationChartLayout?.baselineRegion,
        comparisonRegions: comparison.map((point) => point.item?.region || ""),
        uploadStatus: document.getElementById("operationFileStatus").textContent,
        rentSource: document.getElementById("operationRoneRentSource")?.textContent || "",
        businessName: document.getElementById("operationBusinessName").value,
        lodging: document.getElementById("operationLodging").textContent,
        url: Object.fromEntries(new URLSearchParams(location.search).entries()),
      };
    });
    expect(afterBuildingSwitch.state.selectedName === "B운영 테스트 빌딩"
      && afterBuildingSwitch.building?.building_id === BUILDING_B_ID
      && afterBuildingSwitch.businessName === "B운영 테스트 빌딩"
      && afterBuildingSwitch.lodging.includes("B운영 테스트 빌딩"),
    `B 건물 정보가 선택되지 않았습니다: ${JSON.stringify(afterBuildingSwitch)}`);
    expect(afterBuildingSwitch.state.roomCount === 88
      && afterBuildingSwitch.state.baseAdr === 154000 && afterBuildingSwitch.state.baseOcc === 70
      && afterBuildingSwitch.state.adr === 155000 && afterBuildingSwitch.state.occ === 70
      && afterBuildingSwitch.state.assumed.adr && afterBuildingSwitch.state.assumed.occ,
    `B의 신고 객실수·성남시 기준선으로 새 운영 조건이 초기화되지 않았습니다: ${JSON.stringify(afterBuildingSwitch.state)}`);
    expect(afterBuildingSwitch.state.opexRatio === 27 && afterBuildingSwitch.state.mgmtFeeRatio === 30
      && afterBuildingSwitch.state.assumed.opexRatio && afterBuildingSwitch.state.assumed.mgmtFeeRatio,
    `A의 비용 입력이 B로 누출되었습니다: ${JSON.stringify(afterBuildingSwitch.state)}`);
    expect(afterBuildingSwitch.source.includes("B 건물 전용 운영 통계")
      && !afterBuildingSwitch.source.includes("엠제이스톤")
      && afterBuildingSwitch.region === "성남시"
      && !afterBuildingSwitch.comparisonRegions.includes("평택시"),
    `A의 지역·비교 데이터·출처가 B에 남아 있습니다: ${JSON.stringify(afterBuildingSwitch)}`);
    expect(afterBuildingSwitch.uploadStatus.includes("올리면")
      && !afterBuildingSwitch.uploadStatus.includes("162,000")
      && !afterBuildingSwitch.uploadStatus.includes("2026-01")
      && !afterBuildingSwitch.rentSource.includes("6.02%")
      && !afterBuildingSwitch.rentSource.includes("2026-07-01"),
    `A의 업로드 또는 R-ONE 월세 출처가 B로 누출되었습니다: ${JSON.stringify(afterBuildingSwitch)}`);
    expect(["adr", "occ", "opex_ratio", "mgmt_fee", "buy", "rent"]
      .every((key) => afterBuildingSwitch.url[key] == null),
    `건물 전환 시 A의 시나리오 값이 URL에 남아 있습니다: ${JSON.stringify(afterBuildingSwitch.url)}`);

    const shared = new URL("/analysis", BASE_URL);
    shared.searchParams.set("building_id", BUILDING_ID);
    shared.searchParams.set("mode", "operation");
    shared.searchParams.set("adr", "162000");
    shared.searchParams.set("occ", "74");
    shared.searchParams.set("opex_ratio", "27");
    shared.searchParams.set("mgmt_fee", "20");
    shared.searchParams.set("buy", "5000");
    shared.searchParams.set("rent", "80");
    shared.searchParams.set("share", "test-signed-token");
    await page.goto(shared.toString(), { waitUntil: "domcontentloaded" });
    await ready(page);
    const restored = await page.evaluate(() => window.__operationAnalysisState);
    expect(restored.adr === 162000 && restored.occ === 74 && restored.opexRatio === 27
      && restored.mgmtFeeRatio === 20 && restored.purchasePrice === 5000
      && restored.compareRent === 80,
    `숙박운영 공유 URL의 6개 조건이 복원되지 않았습니다: ${JSON.stringify(restored)}`);
    const signedBeforeEdit = await page.evaluate(() => Object.fromEntries(new URLSearchParams(location.search).entries()));
    expect(signedBeforeEdit.share === "test-signed-token"
      && signedBeforeEdit.adr === "162000" && signedBeforeEdit.rent === "80",
    `서명 공유 시나리오 초기 파라미터가 유지되지 않습니다: ${signedBeforeEdit}`);
    await valueFromLabel(page, "opexRatio", 28);
    await page.waitForTimeout(350);
    const signedAfterEdit = await page.evaluate(() => Object.fromEntries(new URLSearchParams(location.search).entries()));
    expect(signedAfterEdit.share === "test-signed-token"
      && signedAfterEdit.adr === "162000" && signedAfterEdit.occ === "74"
      && signedAfterEdit.opex_ratio === "28" && signedAfterEdit.mgmt_fee === "20"
      && signedAfterEdit.buy === "5000" && signedAfterEdit.rent === "80",
    `운영 조건 조정 후 서명 공유 링크의 기존 시나리오가 보존되지 않습니다: ${signedAfterEdit}`);

    const rentalUrl = new URL("/analysis", BASE_URL);
    rentalUrl.searchParams.set("building_id", BUILDING_ID);
    rentalUrl.searchParams.set("mode", "rental");
    await page.goto(rentalUrl.toString(), { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => window.__rentalAnalysisResult?.ready === true);
    await rentalValueFromLabel(page, "rentalMonthlyRent", 80);
    await page.locator("#operationTab").click();
    await ready(page);
    const linkedRent = await page.evaluate(() => window.__operationAnalysisState.compareRent);
    expect(linkedRent === 80, `임대 탭에서 지정한 월세 80만원을 운영 비교에 반영하지 않았습니다: ${linkedRent}`);

    const ordinaryContext = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    });
    const ordinaryPage = await ordinaryContext.newPage();
    ordinaryPage.on("pageerror", (error) => errors.push(error.message));
    const sliderWarnings = [];
    ordinaryPage.on("console", (message) => {
      if (message.type() === "warning" && message.text().startsWith("[slider] 비정상 값 무시:")) {
        sliderWarnings.push(message.text());
      }
    });
    await installApiMocks(ordinaryPage, []);
    const ordinaryUrl = new URL("/analysis", BASE_URL);
    ordinaryUrl.searchParams.set("building_id", BUILDING_ID);
    ordinaryUrl.searchParams.set("mode", "operation");
    ordinaryUrl.searchParams.set("adr", "140000");
    ordinaryUrl.searchParams.set("occ", "68");
    ordinaryUrl.searchParams.set("rent", "70");
    await ordinaryPage.goto(ordinaryUrl.toString(), { waitUntil: "domcontentloaded" });
    await ready(ordinaryPage);
    const ordinaryInitial = await ordinaryPage.evaluate(() => window.__operationAnalysisState);
    expect(ordinaryInitial.adr === 140000 && ordinaryInitial.occ === 68
      && ordinaryInitial.compareRent === 70,
    `일반 운영 분석 링크의 ADR·OCC·월세 초기값이 복원되지 않았습니다: ${JSON.stringify(ordinaryInitial)}`);
    await ordinaryPage.locator("#rentalTab").click();
    await ordinaryPage.waitForFunction(() => window.__rentalAnalysisResult?.ready === true, null, {
      timeout: 15000,
    });
    await rentalValueFromLabel(ordinaryPage, "rentalPurchasePrice", 5200);
    await rentalValueFromLabel(ordinaryPage, "rentalMonthlyRent", 90);
    await ordinaryPage.locator("#operationTab").click();
    await ordinaryPage.waitForFunction(() => window.__operationAnalysisState?.purchasePrice === 5200
      && window.__operationAnalysisState?.compareRent === 90, null, { timeout: 15000 });
    const ordinaryReturned = await ordinaryPage.evaluate(() => ({
      state: window.__operationAnalysisState,
      params: Object.fromEntries(new URLSearchParams(location.search).entries()),
    }));
    expect(ordinaryReturned.state.adr === 140000 && ordinaryReturned.state.occ === 68
      && ordinaryReturned.state.purchasePrice === 5200 && ordinaryReturned.state.compareRent === 90,
    `일반 운영 링크에서 임대 탭의 매입가·월세 수정값이 숙박운영으로 돌아오지 않았습니다: ${JSON.stringify(ordinaryReturned.state)}`);
    expect(ordinaryReturned.params.share == null && ordinaryReturned.params.adr === "140000"
      && ordinaryReturned.params.occ === "68" && ordinaryReturned.params.buy === "5200"
      && ordinaryReturned.params.rent === "90",
    `일반 링크의 시나리오 파라미터가 임대 탭 왕복 후 보존되지 않았습니다: ${JSON.stringify(ordinaryReturned.params)}`);

    const operationControls = async () => ordinaryPage.evaluate(() =>
      Object.fromEntries(["adr", "occ", "opexRatio", "mgmtFeeRatio"].map((field) => {
        const slider = document.querySelector(`[data-operation-slider="${field}"]`);
        const hidden = document.getElementById({
          adr: "operationAdr", occ: "operationOcc",
          opexRatio: "operationOpexRatio", mgmtFeeRatio: "operationMgmtFeeRatio",
        }[field]);
        return [field, { value: hidden.value, min: slider.min, max: slider.max, step: slider.step }];
      })));
    expect(await ordinaryPage.locator('[data-operation-slider="purchasePrice"], [data-operation-slider="compareRent"]').count() === 0,
      "삭제한 비교 조건의 가로바가 화면에 남았습니다.");
    for (const [moving, next] of [["adr", "211"], ["occ", "72"],
      ["opexRatio", "35"], ["mgmtFeeRatio", "20"]]) {
      const before = await operationControls();
      await ordinaryPage.locator(`[data-operation-slider="${moving}"]`).evaluate((slider, nextValue) => {
        slider.value = nextValue;
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      }, next);
      await ordinaryPage.waitForTimeout(400);
      const after = await operationControls();
      for (const field of ["adr", "occ", "opexRatio", "mgmtFeeRatio"]) {
        if (field !== moving) {
          expect(JSON.stringify(after[field]) === JSON.stringify(before[field]),
            `${moving} 가로바 조작이 ${field} 가로바에 영향을 주었습니다.`);
        }
      }
    }

    const malformedOperation = new URL("/analysis", BASE_URL);
    malformedOperation.searchParams.set("building_id", String(BUILDING_ID));
    malformedOperation.searchParams.set("mode", "operation");
    malformedOperation.searchParams.set("adr", "999999999");
    malformedOperation.searchParams.set("occ", "105");
    malformedOperation.searchParams.set("opex_ratio", "99");
    malformedOperation.searchParams.set("mgmt_fee", "100");
    malformedOperation.searchParams.set("buy", "356240000");
    malformedOperation.searchParams.set("rent", "85129212260000");
    malformedOperation.searchParams.set("preserve", "1");
    await ordinaryPage.goto(malformedOperation.toString(), { waitUntil: "domcontentloaded" });
    await ready(ordinaryPage);
    await ordinaryPage.waitForFunction(() => {
      const params = new URLSearchParams(location.search);
      return ["adr", "occ", "opex_ratio", "mgmt_fee", "buy", "rent"]
        .every((key) => !params.has(key)) && params.get("preserve") === "1";
    });
    const cleanedOperation = await ordinaryPage.evaluate(() => ({
      state: window.__operationAnalysisState,
      params: Object.fromEntries(new URLSearchParams(location.search)),
    }));
    expect(cleanedOperation.params.preserve === "1"
      && cleanedOperation.state.adr >= 10000 && cleanedOperation.state.adr <= 2000000
      && cleanedOperation.state.occ >= 0 && cleanedOperation.state.occ <= 100
      && cleanedOperation.state.opexRatio <= 90 && cleanedOperation.state.mgmtFeeRatio <= 90
      && cleanedOperation.state.purchasePrice == null
      && cleanedOperation.state.compareRent <= 1000,
    `잘못된 운영 URL 값이 정화되지 않았습니다: ${JSON.stringify(cleanedOperation)}`);
    expect(sliderWarnings.length === 6,
      `잘못된 운영 URL 값 6개에 대한 경고가 필요합니다: ${JSON.stringify(sliderWarnings)}`);
    await ordinaryContext.close();

    const lowAdrPage = await context.newPage();
    const lowAdrCalls = [];
    lowAdrPage.on("pageerror", (error) => errors.push(error.message));
    await installApiMocks(lowAdrPage, lowAdrCalls);
    const lowAdrUrl = new URL("/analysis", BASE_URL);
    lowAdrUrl.searchParams.set("building_id", LOW_ADR_BUILDING_ID);
    lowAdrUrl.searchParams.set("mode", "operation");
    await lowAdrPage.goto(lowAdrUrl.toString(), { waitUntil: "domcontentloaded" });
    await ready(lowAdrPage);
    const lowAdrChart = await lowAdrPage.evaluate(() => {
      const chart = Chart.getChart(document.getElementById("operationChart"));
      const comparisons = chart?.data.datasets.find((set) => set.key === "comparison")?.data || [];
      return {
        state: window.__operationAnalysisState,
        scaleMin: chart?.scales.x.min,
        baseline: chart?.data.datasets.find((set) => set.key === "baseline")?.data[0]?.x,
        comparisonPoints: comparisons.map((point) => ({ adr: point.x, sourceAdr: point.item?.adr })),
        layout: window.__operationChartLayout,
      };
    });
    expect(lowAdrChart.state.baseAdr === 80000 && lowAdrChart.scaleMin < 0,
      `저단가 시나리오에서 음수 x축 범위가 형성되지 않았습니다: ${JSON.stringify(lowAdrChart)}`);
    expect(lowAdrChart.comparisonPoints.length === 4
      && lowAdrChart.comparisonPoints.every((point) => point.adr > 0 && point.sourceAdr > 0)
      && !lowAdrChart.comparisonPoints.some((point) => point.adr === -12000),
    `음수 ADR 비교점이 차트에 생성되거나 유효 비교점이 누락됐습니다: ${JSON.stringify(lowAdrChart.comparisonPoints)}`);
    expect(near(lowAdrChart.baseline, 80000, 0.01)
      && Math.abs(lowAdrChart.layout.baselinePixelX - lowAdrChart.layout.chartCenterX) < 2,
    `x축 최솟값이 음수일 때 지역 ADR 기준선이 중앙에 있지 않습니다: ${JSON.stringify(lowAdrChart.layout)}`);
    await lowAdrPage.close();

    const fallbackContext = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    });
    const fallbackPage = await fallbackContext.newPage();
    const fallbackCalls = [];
    fallbackPage.on("pageerror", (error) => errors.push(error.message));
    await installApiMocks(fallbackPage, fallbackCalls);
    const fallbackUrl = new URL("/analysis", BASE_URL);
    fallbackUrl.searchParams.set("building_id", BUILDING_ID);
    fallbackUrl.searchParams.set("mode", "operation");
    fallbackUrl.searchParams.set("buy", "5000");
    fallbackUrl.searchParams.set("r_rent", "");
    await fallbackPage.goto(fallbackUrl.toString(), { waitUntil: "domcontentloaded" });
    await ready(fallbackPage);
    await fallbackPage.waitForFunction(() => window.__operationAnalysisState?.compareRent === 25, null, {
      timeout: 15000,
    });
    const fallback = await fallbackPage.evaluate(() => ({
      state: window.__operationAnalysisState,
      rentalRent: document.getElementById("rentalMonthlyRent")?.value ?? null,
      assumption: document.querySelector(
        '#operationSliders [data-operation-row="compareRent"] [data-operation-assumption]',
      )?.textContent.trim() || "",
      source: document.getElementById("operationRoneRentSource")?.textContent || "",
    }));
    expect(fallback.rentalRent === "25" && fallback.rentalRent !== "150"
      && fallback.state.purchasePrice === 5000 && fallback.state.compareRent === 25
      && fallback.state.assumed.compareRent,
    `매입가 5,000만원 조건의 R-ONE 기준 월세 25만원이 임대 탭에 연결되지 않았거나 기존 월세가 누출되었습니다: ${JSON.stringify(fallback)}`);
    expect(!fallback.assumption && !fallback.source,
      `삭제한 비교 조건의 안내가 화면에 남았습니다: ${JSON.stringify(fallback)}`);
    expect(fallbackCalls.some((call) => call.path === "/api/analysis/rental-benchmark"),
      "R-ONE 비교 월세 대체값 산출을 위해 임대 벤치마크를 조회하지 않았습니다.");

    const fallbackSelected = await fallbackPage.evaluate(() => ({
      state: window.__operationAnalysisState,
      selected: document.querySelector("#operationSensitivity td.selected")?.getAttribute("aria-current"),
      tableCurrentNet: document.getElementById("operationSensitivity").dataset.currentMonthlyNet,
    }));
    expect(fallbackSelected.selected === "true"
      && fallbackSelected.tableCurrentNet === String(fallbackSelected.state.monthlyNet),
    "운영 민감도 표에서 현재 ADR×OCC 칸이 핵심 월 순수익과 일치하지 않습니다.");
    await fallbackContext.close();

    const largePricePage = await context.newPage();
    largePricePage.on("pageerror", (error) => errors.push(error.message));
    await installApiMocks(largePricePage, []);
    const largePriceUrl = new URL("/analysis", BASE_URL);
    largePriceUrl.searchParams.set("building_id", BUILDING_ID);
    largePriceUrl.searchParams.set("mode", "operation");
    largePriceUrl.searchParams.set("buy", "52000");
    largePriceUrl.searchParams.set("rent", "32");
    await largePricePage.goto(largePriceUrl.toString(), { waitUntil: "domcontentloaded" });
    await ready(largePricePage);
    const highPrice = await largePricePage.evaluate(() => ({
      purchase: window.__operationAnalysisState.purchasePrice,
      rent: window.__operationAnalysisState.compareRent,
      controls: document.querySelectorAll('[data-operation-slider="purchasePrice"], [data-operation-slider="compareRent"]').length,
    }));
    expect(highPrice.purchase === 52000 && highPrice.rent === 32 && highPrice.controls === 0,
      `고액 매입가·월세는 내부 계산에 유지하되 비교 조건 UI는 제거해야 합니다: ${JSON.stringify(highPrice)}`);
    await largePricePage.close();

    const staleContext = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    });
    const stalePage = await staleContext.newPage();
    const staleCalls = [];
    stalePage.on("pageerror", (error) => errors.push(error.message));
    await installApiMocks(stalePage, staleCalls, { roneDelayMs: 800 });
    const staleUrl = new URL("/analysis", BASE_URL);
    staleUrl.searchParams.set("building_id", BUILDING_ID);
    staleUrl.searchParams.set("mode", "operation");
    staleUrl.searchParams.set("buy", "5000");
    staleUrl.searchParams.set("r_rent", "");
    await stalePage.goto(staleUrl.toString(), { waitUntil: "domcontentloaded" });
    await ready(stalePage);
    const requestDeadline = Date.now() + 5000;
    while (!staleCalls.some((call) => call.path === "/api/analysis/rental-benchmark")
      && Date.now() < requestDeadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    expect(staleCalls.some((call) => call.path === "/api/analysis/rental-benchmark"),
      "지연 응답 경쟁 조건 시나리오에서 R-ONE 요청이 시작되지 않았습니다.");
    await stalePage.locator("#rentalTab").click();
    await stalePage.waitForFunction(() => window.__rentalAnalysisResult?.ready === true);
    await rentalValueFromLabel(stalePage, "rentalMonthlyRent", 80);
    await stalePage.locator("#operationTab").click();
    await ready(stalePage);
    await stalePage.waitForTimeout(900);
    const afterStaleResponse = await stalePage.evaluate(() => window.__operationAnalysisState);
    expect(afterStaleResponse.compareRent === 80 && afterStaleResponse.assumed.compareRent === false,
      `지연된 R-ONE 응답이 사용자가 입력한 비교 월세를 덮어썼습니다: ${JSON.stringify(afterStaleResponse)}`);
    await staleContext.close();

    const writes = calls.filter(({ method, path }) => method !== "GET" && method !== "HEAD"
      && path !== "/api/analysis/operation-upload"
      && path !== "/api/analysis/share-link"
      && !["/api/favorites/migrate", "/api/alerts/migrate"].includes(path));
    expect(writes.length === 0, `예상 밖 API 쓰기: ${JSON.stringify(writes)}`);
    expect(errors.length === 0, `브라우저 오류: ${errors.join(" | ")}`);
    console.log("숙박운영 개편 브라우저 회귀 테스트 통과");
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});