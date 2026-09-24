const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const BUILDING_ID = 101;
const failures = [];

function expect(condition, message) {
  if (!condition) failures.push(message);
}

function expectNear(actual, expected, message, tolerance = 0.02) {
  expect(Number.isFinite(actual) && Math.abs(actual - expected) <= tolerance,
    `${message}: expected ${expected}, got ${actual}`);
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

async function json(route, value, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

function benchmark() {
  const national = {
    region_code: "00",
    region_level: "national",
    region_name: "전국",
    income_yield: 6.02,
    vacancy_rate: 8.4746,
    property_type: "officetel",
    period: "2026-07-01",
    vacancy_period: "2026-04-01",
  };
  const provinces = [
    ["11", "서울", 4.9],
    ["26", "부산", 5.1],
    ["27", "대구", 4.7],
    ["28", "인천", 5.2],
    ["29", "광주", 5.0],
    ["30", "대전", 4.8],
    ["31", "울산", 5.3],
    ["36", "세종", 4.6],
    ["41", "경기", 5.4],
  ].map(([region_code, region_name, income_yield]) => ({
    region_code, region_level: "province", region_name, income_yield,
    vacancy_rate: 8.4746,
    property_type: "officetel",
    period: "2026-07-01",
    vacancy_period: "2026-04-01",
  }));
  return {
    available: true,
    benchmark: national,
    items: [national, ...provinces],
    source: {
      provider: "한국부동산원 R-ONE",
      status: "ready",
      notice: "지역별 공실률 미수집; 전국 소규모상가 공실률 대체",
    },
  };
}

async function installApiMocks(page) {
  const apiCalls = [];
  await page.route("**/v2/maps/**", (route) => route.abort());
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    apiCalls.push({ method: request.method(), path: url.pathname });
    if (request.method() !== "GET" && request.method() !== "HEAD") {
      return json(route, { ok: true, items: [] });
    }
    if (url.pathname === "/api/auth/me") {
      return json(route, { logged_in: true, user: { id: 1, name: "브라우저 테스트" } });
    }
    if (url.pathname === "/api/analysis/assets") {
      return json(route, {
        generated_at: "2026-09-07T00:00:00Z",
        baselines: { tourism_demand_index: 50, peer_price_gap: 0 },
        filters: { sidos: [], sggs: [], lodging_types: [], period_options: [] },
        summary: {
          registered_buildings: 1,
          transaction_count: 0,
          analyzed_buildings: 1,
          analysis_sample_transaction_count: 0,
        },
        methodology: { comparison_basis: {} },
        trajectory_methodology: {},
        trajectory: [],
        items: [{
          building_id: BUILDING_ID,
          name: "엠제이스톤 레지던스",
          lodging_type: "생활숙박시설",
          sido: "서울특별시",
          sgg: "중구",
          address: "서울특별시 중구 테스트로 1",
          lat: 37.56,
          lng: 126.99,
          tourism_demand_index: 50,
          peer_price_gap: 0,
          peer_scope: "시도 동일유형",
          peer_building_count: 0,
          transaction_count: 0,
        }],
        candidates: { price: [], confidence: [], urgent: [] },
      });
    }
    if (url.pathname === `/api/building/${BUILDING_ID}`) {
      return json(route, {
        building_id: BUILDING_ID,
        building_name: "엠제이스톤 레지던스",
        display_building_name: "엠제이스톤 레지던스",
        road_address: "서울특별시 중구 테스트로 1",
        sido_nm: "서울특별시",
        sgg_cd: "11",
        lodging_type: "생활숙박시설",
      });
    }
    if (url.pathname === `/api/building/${BUILDING_ID}/area-types`) {
      return json(route, { ok: true, items: [{ sqm: 17.6, ho_cnt: 1 }], sqms: [17.6] });
    }
    if (url.pathname === "/api/analysis/rental-benchmark") return json(route, benchmark());
    if (url.pathname === "/api/analysis/rental-market-price") {
      return json(route, {
        ok: true,
        area_sqm: 17.6,
        median_price: 5000,
        latest_deal_date: "2026-08-19",
        sample_count: 3,
        match_type: "exact",
        transactions: [
          { deal_date: "2026-08-19", area_sqm: 17.6, price: 5000, area_match: "exact" },
          { deal_date: "2026-07-10", area_sqm: 17.6, price: 5100, area_match: "exact" },
          { deal_date: "2026-06-01", area_sqm: 17.6, price: 4900, area_match: "exact" },
        ],
      });
    }
    if (url.pathname === "/api/favorites/mine") return json(route, { items: [] });
    if (url.pathname.endsWith("/photos")) return json(route, { photos: [] });
    return json(route, { ok: true, items: [] });
  });
  return apiCalls;
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
      faces,
    };
  });
  if (!fontState.notoLoaded) {
    console.warn("Korean web font unavailable in this environment; screenshot uses browser fallback font.");
  }
  return fontState;
}

async function waitForRental(page) {
  await page.waitForFunction(() => {
    const result = window.__rentalAnalysisResult;
    return result && result.ready && Number(result.purchasePrice) > 0
      && document.querySelectorAll("#rentalSensitivity tbody tr").length === 7;
  }, null, { timeout: 15000 });
}

async function setValueFromLabel(page, field, value) {
  await page.locator(`[data-rental-value="${field}"]`).click();
  const input = page.locator(`[data-rental-value="${field}"] input`);
  await input.fill(String(value));
  await input.press("Enter");
  await page.waitForTimeout(50);
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
  const pageErrors = [];
  const sliderWarnings = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "warning" && message.text().startsWith("[slider] 비정상 값 무시:")) {
      sliderWarnings.push(message.text());
    }
  });
  const apiCalls = await installApiMocks(page);

  try {
    const firstUrl = new URL("/analysis", BASE_URL);
    firstUrl.searchParams.set("building_id", BUILDING_ID);
    firstUrl.searchParams.set("mode", "rental");
    firstUrl.searchParams.set("r_unit_area", "17.6");
    firstUrl.searchParams.set("r_purchase", "4000");
    firstUrl.searchParams.set("r_deposit", "300");
    firstUrl.searchParams.set("r_rent", "100");
    firstUrl.searchParams.set("r_vacancy", "");
    firstUrl.searchParams.set("r_loan", "0");
    firstUrl.searchParams.set("r_rate", "4.5");
    firstUrl.searchParams.set("r_years", "20");
    firstUrl.searchParams.set("r_method", "interest");
    firstUrl.searchParams.set("share", "mock-signed-token");

    const response = await page.goto(firstUrl.toString(), { waitUntil: "domcontentloaded" });
    expect(response && response.ok(), "분석 화면을 열지 못했습니다. 실행 중인 미리보기 주소를 확인하세요.");
    await waitForRental(page);
    await page.waitForFunction(() => Number(document.getElementById("rentalMarketPrice").value) === 5000
      && document.querySelector('[data-rental-limits="rentalPurchasePrice"] span').textContent === "3,000만");

    const initial = await page.evaluate(() => {
      const result = window.__rentalAnalysisResult;
      const chart = window.Chart && Chart.getChart(document.getElementById("rentalPositionChart"));
      const own = chart && chart.data.datasets.find((set) => set.key === "selected");
      return {
        title: document.getElementById("rentalBuildingName").textContent,
        area: document.getElementById("rentalUnitArea").value,
        purchase: Number(document.getElementById("rentalPurchasePrice").value),
        deposit: Number(document.getElementById("rentalDeposit").value),
        rent: Number(document.getElementById("rentalMonthlyRent").value),
        vacancy: Number(document.getElementById("rentalVacancyMonths").value),
        vacancyAssumption: document.querySelector("[data-vacancy-assumption]")?.textContent.trim() || "",
        result,
        own: own && own.data[0],
        sensitivityRows: document.querySelectorAll("#rentalSensitivity tbody tr").length,
        sensitivityCells: document.querySelectorAll("#rentalSensitivity tbody tr:first-child td").length,
      sliders: Object.fromEntries(Array.from(document.querySelectorAll("#rentalSliders [data-rental-slider]"))
        .map((slider) => [slider.dataset.rentalSlider, {
          min: Number(slider.min), max: Number(slider.max), step: Number(slider.step),
        }])),
      sliderLimits: Object.fromEntries(Array.from(document.querySelectorAll("#rentalSliders [data-rental-limits]"))
        .map((node) => [node.dataset.rentalLimits, Array.from(node.querySelectorAll("span"))
          .map((span) => span.textContent.trim())])),
      positionCard: document.getElementById("rentalPositioning").getBoundingClientRect().toJSON(),
      positionMap: document.querySelector("#rentalPositioning .positioning-map").getBoundingClientRect().toJSON(),
      positionChart: document.getElementById("rentalPositionChart").getBoundingClientRect().toJSON(),
      sensitivityOverflow: (() => {
        const scroll = document.querySelector(
          "#rentalSensitivity .rental-sensitivity-scroll, #rentalSensitivity .sensitivity-scroll",
        );
        return scroll.scrollWidth - scroll.clientWidth;
      })(),
        vacancyParam: new URLSearchParams(location.search).get("r_vacancy"),
        hasVacancyParam: new URLSearchParams(location.search).has("r_vacancy"),
        apiCalls: window.__rentalAnalysisApiCalls || [],
      };
    });
    expect(initial.title === "엠제이스톤 레지던스", "선택 건물명이 로드되지 않았습니다.");
    expect(initial.area === "17.6", "공유 URL의 전용면적이 복원되지 않았습니다.");
    expect(initial.purchase === 4000 && initial.deposit === 300 && initial.rent === 100,
      "공유 URL의 매입·보증금·월세 값이 복원되지 않았습니다.");
    expect(initial.vacancy === 1 && initial.vacancyAssumption === "가정값",
      "공실 기본 가정값 또는 가정 배지가 복원되지 않았습니다.");
    expectNear(initial.result.returnBasis, 3920, "보증금을 반영한 수익률 분모");
    expectNear(initial.result.netYield, initial.result.noi / 3920 * 100, "첨부 지시문 순수익률");
    expect(initial.result.netYield > 16.02 && initial.own.offscale === true,
      "초과 수익률이 차트 경계의 방향 삼각형 데이터로 표시되지 않았습니다.");
    expect(initial.sensitivityRows === 7 && initial.sensitivityCells === 7,
      "민감도 표는 공실 0~6개월과 월세 7개 열이어야 합니다.");
    expect(initial.sliders.rentalPurchasePrice.min === 0
      && initial.sliders.rentalPurchasePrice.max === 900
      && initial.sliders.rentalPurchasePrice.step === 1
      && initial.sliders.rentalLoanAmount.max === 1000
      && initial.sliders.rentalLoanAmount.step === 1,
    `시세 5,000만원 매수가 가상 눈금·간격이 잘못되었습니다: ${JSON.stringify(initial.sliders.rentalPurchasePrice)}`);
    expect(!await page.locator("[data-rental-loan-cap]").count()
      && !(await page.locator('[data-rental-row="rentalLoanAmount"]').textContent()).includes("매수가 이내"),
      "대출금에 매수가 이내 제한 안내가 남아 있습니다.");
    expect(initial.sliders.rentalDeposit.max === 5000 && initial.sliders.rentalDeposit.step === 100,
      `보증금 상한·간격이 잘못되었습니다: ${JSON.stringify(initial.sliders.rentalDeposit)}`);
    expect(initial.sliders.rentalMonthlyRent.min === 50
      && initial.sliders.rentalMonthlyRent.max === 1000
      && initial.sliders.rentalMonthlyRent.step === 1
      && initial.sliders.rentalVacancyMonths.max === 12
      && initial.sliders.rentalVacancyMonths.step === 1,
    `월세·공실 슬라이더 범위가 기준 규칙과 다릅니다: ${JSON.stringify(initial.sliders)}`);
    expect(JSON.stringify(initial.sliderLimits.rentalPurchasePrice) === JSON.stringify(["3,000만", "50억"])
      && JSON.stringify(initial.sliderLimits.rentalLoanAmount) === JSON.stringify(["0만", "40억"])
      && JSON.stringify(initial.sliderLimits.rentalDeposit) === JSON.stringify(["0만", "5,000만"])
      && JSON.stringify(initial.sliderLimits.rentalMonthlyRent) === JSON.stringify(["50만", "1,000만"])
      && JSON.stringify(initial.sliderLimits.rentalVacancyMonths) === JSON.stringify(["0개월", "12개월"]),
    `슬라이더 아래 양 끝 범위 표시가 없거나 잘못되었습니다: ${JSON.stringify(initial.sliderLimits)}`);
    expect(await page.locator('[data-rental-limits="rentalPurchasePrice"] small').textContent()
      === "천만원 단위"
      && await page.locator('[data-rental-limits="rentalLoanAmount"] small').textContent()
      === "천만원 단위 · 절대 상한 40억"
      && await page.locator('[data-rental-limits="rentalDeposit"] small').textContent()
      === "백만원 단위"
      && await page.locator('[data-rental-limits="rentalMonthlyRent"] small').textContent()
      === "만원 단위",
    "가로바의 조정 단위가 표시되지 않았습니다.");
    const purchaseValueRect = await page.locator('[data-rental-value="rentalPurchasePrice"]').evaluate((element) => ({
      client: element.clientWidth, scroll: element.scrollWidth, whiteSpace: getComputedStyle(element).whiteSpace,
    }));
    expect(purchaseValueRect.client >= purchaseValueRect.scroll && purchaseValueRect.whiteSpace === "nowrap",
      `매수가 값 라벨이 잘리거나 줄바꿈됩니다: ${JSON.stringify(purchaseValueRect)}`);
    expect(Math.abs(initial.positionChart.width - initial.positionMap.width) <= 2
      && Math.abs(initial.positionMap.height - 360) < 2,
    `데스크톱 임대 포지셔닝 차트가 카드 전체 폭·360px 높이가 아닙니다: ${JSON.stringify({
      card: initial.positionCard, map: initial.positionMap, chart: initial.positionChart,
    })}`);
    expect(initial.sensitivityOverflow <= 2,
      `데스크톱 임대 민감도 표의 7개 열에 가로 스크롤이 필요합니다: ${initial.sensitivityOverflow}px`);
    expect(initial.hasVacancyParam && initial.vacancyParam === "",
      "가정 공실이 공유 URL에서 직접 입력값으로 바뀌었습니다.");
    fs.mkdirSync("screenshots", { recursive: true });
    await awaitScreenshotFonts(page);
    await page.screenshot({ path: "screenshots/rental-desktop-1280.png", fullPage: true });
    await page.locator("#rentalSliders").screenshot({ path: "screenshots/rental-slider-controls-1280.png" });
    await page.locator("#rentalPositioning").screenshot({
      path: "screenshots/slider-rental-chart-1280.png",
    });
    await page.locator("#rentalSensitivity").screenshot({
      path: "screenshots/slider-rental-sensitivity-1280.png",
    });

    await setValueFromLabel(page, "rentalMonthlyRent", 30);
    const roneCallsBeforeRelease = apiCalls.filter((call) => call.path === "/api/analysis/rental-benchmark").length;
    const rangeFreeze = await page.evaluate(() => {
      const slider = document.querySelector('[data-rental-slider="rentalMonthlyRent"]');
      const before = { min: slider.min, max: slider.max, step: slider.step };
      slider.value = "32";
      slider.dispatchEvent(new Event("input", { bubbles: true }));
      const during = { min: slider.min, max: slider.max, step: slider.step };
      slider.dispatchEvent(new Event("change", { bubbles: true }));
      return { before, during };
    });
    expect(rangeFreeze.before.min === "15" && rangeFreeze.before.max === "1000"
      && rangeFreeze.before.step === "1"
      && JSON.stringify(rangeFreeze.during) === JSON.stringify(rangeFreeze.before),
    `월세 드래그 중 활성 슬라이더 범위가 고정되지 않았습니다: ${JSON.stringify(rangeFreeze)}`);
    expect(apiCalls.filter((call) => call.path === "/api/analysis/rental-benchmark").length === roneCallsBeforeRelease,
    "월세 슬라이더 input 중 R-ONE 조회가 추가로 발생했습니다.");
    await page.waitForTimeout(400);
    const rangeAfterRelease = await page.evaluate(() => {
      const slider = document.querySelector('[data-rental-slider="rentalMonthlyRent"]');
      const result = window.__rentalAnalysisResult;
      const headers = Array.from(document.querySelectorAll("#rentalSensitivity thead th"))
        .slice(1).map((header) => header.textContent.trim());
      const selected = document.querySelector("#rentalSensitivity td.selected");
      return {
        min: Number(slider.min), max: Number(slider.max), step: Number(slider.step),
        annualRent: result.annualRent, rent: result.annualRent / 12, headers,
        selectedValue: selected && Number(selected.textContent.trim().replace("%", "")),
        expectedValue: result.netYield,
      };
    });
    expect(rangeAfterRelease.min === 15 && rangeAfterRelease.max === 1000
      && rangeAfterRelease.step === 1 && rangeAfterRelease.rent === 32,
    `월세 슬라이더 change 후 고정 중심 범위가 유지되지 않았습니다: ${JSON.stringify(rangeAfterRelease)}`);
    expect(JSON.stringify(rangeAfterRelease.headers)
      === JSON.stringify(["17만원", "22만원", "27만원", "32만원", "37만원", "42만원", "47만원"]),
    `월세 32만원 민감도 열이 17~47만원으로 이동하지 않았습니다: ${JSON.stringify(rangeAfterRelease.headers)}`);
    expectNear(rangeAfterRelease.selectedValue, rangeAfterRelease.expectedValue,
      "월세 민감도 현재 칸과 핵심 순수익률");

    await setValueFromLabel(page, "rentalMonthlyRent", 47);
    await page.waitForFunction(() => Number(window.__rentalAnalysisResult?.annualRent) === 564);
    const directValue = await page.evaluate(() => ({
      exactRent: Number(document.getElementById("rentalMonthlyRent").value),
      slider: Number(document.querySelector('[data-rental-slider="rentalMonthlyRent"]').value),
      headers: Array.from(document.querySelectorAll("#rentalSensitivity thead th")).map((node) => node.textContent.trim()),
      highlighted: document.querySelector("#rentalSensitivity tbody td.selected")?.title || "",
      selectedCell: Number(document.querySelector("#rentalSensitivity tbody td.selected")?.textContent.trim().replace("%", "")),
      returnBasis: window.__rentalAnalysisResult.returnBasis,
      netYield: window.__rentalAnalysisResult.netYield,
      noi: window.__rentalAnalysisResult.noi,
    }));
    expect(directValue.exactRent === 47 && directValue.slider === 47,
      `직접 입력 47만원을 가장 가까운 슬라이더 위치에 표시해야 합니다: ${JSON.stringify({
        exactRent: directValue.exactRent, slider: directValue.slider,
      })}`);
    expect(directValue.headers.includes("47만원") && directValue.highlighted.includes("월세 47만원"),
      "민감도 표에 직접 입력값 47만원 열과 정확한 현재 조건 툴팁이 표시되어야 합니다.");
    expectNear(directValue.selectedCell, directValue.netYield, "월세 47 민감도 현재 칸과 순수익률");
    expectNear(directValue.netYield, directValue.noi / 3920 * 100,
      "월세 직접 입력 후 수익률");

    await setValueFromLabel(page, "rentalMonthlyRent", 30);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.annualRent === 360);
    const rentRangeBeforePurchaseChanges = await page.locator(
      '[data-rental-slider="rentalMonthlyRent"]',
    ).getAttribute("max");
    for (let index = 0; index < 5; index++) {
      await page.locator('[data-rental-slider="rentalMonthlyRent"]').evaluate((element) => {
        element.value = element.max;
        element.dispatchEvent(new Event("input", { bubbles: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await page.waitForTimeout(350);
      await page.locator('[data-rental-slider="rentalPurchasePrice"]').evaluate((element, cycle) => {
        element.value = cycle % 2 === 0 ? element.min : element.max;
        element.dispatchEvent(new Event("input", { bubbles: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
      }, index);
      await page.waitForTimeout(350);
      await page.locator('[data-rental-slider="rentalMonthlyRent"]').evaluate((element) => {
        element.value = element.max;
        element.dispatchEvent(new Event("input", { bubbles: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await page.waitForTimeout(350);
    }
    expect(await page.locator('[data-rental-slider="rentalMonthlyRent"]').getAttribute("max")
      === rentRangeBeforePurchaseChanges,
    "매수가를 바꿀 때 월세 상한이 계단식으로 증가합니다.");
    await setValueFromLabel(page, "rentalMonthlyRent", 30);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.annualRent === 360);
    const stableRentBeforeInvalidEntry = Number(await page.locator("#rentalMonthlyRent").inputValue());
    await setValueFromLabel(page, "rentalMonthlyRent", 5000);
    const rejectedRent = await page.evaluate(() => ({
      value: Number(document.getElementById("rentalMonthlyRent").value),
      message: document.querySelector('[data-rental-input-error="rentalMonthlyRent"]')?.textContent || "",
    }));
    expect(rejectedRent.value === stableRentBeforeInvalidEntry
      && rejectedRent.message === "월세는 1~1,000만원 범위로 입력하세요",
    `월세 5,000만원 직접 입력이 거부·안내되지 않았습니다: ${JSON.stringify(rejectedRent)}`);
    await page.waitForTimeout(400);
    await setValueFromLabel(page, "rentalPurchasePrice", 4000);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.purchasePrice === 4000);
    const debtFree = await page.evaluate(() => ({
      result: window.__rentalAnalysisResult,
      selectedCell: document.querySelector("#rentalSensitivity tbody td.selected")?.textContent.trim(),
      cards: document.getElementById("rentalCoreMetrics").textContent,
      debtCards: document.getElementById("rentalExtraMetrics").textContent,
    }));
    expectNear(debtFree.result.netYield, debtFree.result.cashReturn,
      "대출 0일 때 순수익률과 자기자본 수익률 일치");
    expect(debtFree.selectedCell === debtFree.result.netYield.toFixed(2) + "%",
      "월세 30·공실 1의 민감도 강조 칸과 핵심 카드 수익률이 일치하지 않습니다.");
    expect(!debtFree.debtCards.includes("DSCR") && !debtFree.debtCards.includes("월 대출 상환액"),
      "대출 0일 때 대출 상세 지표가 표시됩니다.");

    await setValueFromLabel(page, "rentalLoanAmount", 1500);
    expect(await page.locator('[data-rental-slider="rentalLoanAmount"]').getAttribute("max") === "1000",
      "대출금 직접입력 후에도 가로바의 고정 눈금이 유지되어야 합니다.");
    await page.waitForFunction(() => window.__rentalAnalysisResult?.loan === 1500);
    const leveraged = await page.evaluate(() => ({
      result: window.__rentalAnalysisResult,
      details: document.getElementById("rentalExtraMetrics").textContent,
    }));
    expectNear(leveraged.result.cashReturn,
      (leveraged.result.noi - 1500 * 0.045) / leveraged.result.invested * 100,
      "대출 1,500만원의 자기자본 수익률은 연 이자만 차감");
    expect(leveraged.details.includes("DSCR") && leveraged.details.includes("월 대출 상환액"),
      "대출 1,500만원의 상세 상환 지표를 표시해야 합니다.");
    await page.locator('[data-rental-slider="rentalLoanAmount"]').evaluate((element) => {
      element.value = "7";
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForFunction(() => window.__rentalAnalysisResult?.loan === 1000);
    expect(await page.locator('[data-rental-slider="rentalLoanAmount"]').getAttribute("aria-valuetext")
      === "1,000만원", "대출금 가로바의 천만원 단위 값과 접근성 안내가 맞지 않습니다.");
    await setValueFromLabel(page, "rentalLoanAmount", 4500);
    expect(Number(await page.locator("#rentalLoanAmount").inputValue()) === 4500
      && !(await page.locator('[data-rental-input-error="rentalLoanAmount"]').textContent()),
    "매수가보다 큰 대출금도 직접 입력할 수 있어야 합니다.");
    await page.waitForTimeout(400);
    await setValueFromLabel(page, "rentalLoanAmount", 1500);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.loan === 1500);
    const loanBeforePurchaseDrag = await page.evaluate(() => ({
      amount: document.getElementById("rentalLoanAmount").value,
      position: document.querySelector('[data-rental-slider="rentalLoanAmount"]').value,
      max: document.querySelector('[data-rental-slider="rentalLoanAmount"]').max,
    }));
    await page.locator('[data-rental-slider="rentalPurchasePrice"]').evaluate((element) => {
      element.value = "3000";
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.waitForTimeout(400);
    const loanAfterPurchaseDrag = await page.evaluate(() => ({
      amount: document.getElementById("rentalLoanAmount").value,
      position: document.querySelector('[data-rental-slider="rentalLoanAmount"]').value,
      max: document.querySelector('[data-rental-slider="rentalLoanAmount"]').max,
    }));
    expect(JSON.stringify(loanAfterPurchaseDrag) === JSON.stringify(loanBeforePurchaseDrag),
      `매수가를 움직일 때 대출금 바가 따라 움직였습니다: ${JSON.stringify({
        before: loanBeforePurchaseDrag, after: loanAfterPurchaseDrag,
      })}`);
    await setValueFromLabel(page, "rentalPurchasePrice", 4000);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.purchasePrice === 4000);

    await page.locator("#rentalDeposit").evaluate((element) => {
      element.value = "4220";
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForFunction(() => window.__rentalAnalysisResult?.returnBasis === 0);
    expect(await page.locator("#rentalCoreMetrics").textContent().then((text) => text.includes("계산불가")),
      "실투자금이 0 이하인 극단값은 오류 대신 계산불가로 표시해야 합니다.");
    await page.locator("#rentalDeposit").evaluate((element) => {
      element.value = "300";
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForFunction(() => window.__rentalAnalysisResult?.returnBasis === 3920);

    await page.locator('[data-rental-slider="rentalLoanAmount"]').evaluate((element) => {
      element.value = element.max;
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForTimeout(400);
    await setValueFromLabel(page, "rentalPurchasePrice", 2000);
    const independentLoan = await page.evaluate(() => ({
      purchase: Number(document.getElementById("rentalPurchasePrice").value),
      loan: Number(document.getElementById("rentalLoanAmount").value),
      max: Number(document.querySelector('[data-rental-slider="rentalLoanAmount"]').max),
    }));
    expect(independentLoan.purchase === 2000 && independentLoan.loan === 400000
      && independentLoan.max === 1000,
      `매입가 하향 시 대출금 40억이 유지되지 않았습니다: ${JSON.stringify(independentLoan)}`);
    expect(!(await page.locator('[data-rental-input-error="rentalLoanAmount"]').textContent()),
      "매수가 하향으로 대출 제한 오류가 표시되면 안 됩니다.");
    await page.locator('[data-rental-slider="rentalLoanAmount"]').evaluate((element) => {
      element.value = "333";
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(Number(await page.locator("#rentalPurchasePrice").inputValue()) === 2000
      && Number(await page.locator("#rentalLoanAmount").inputValue()) === 50000
      && await page.locator('[data-rental-slider="rentalLoanAmount"]').getAttribute("aria-valuetext") === "5억원"
      && await page.locator('[data-rental-value="rentalLoanAmount"]').textContent() === "5억원",
    "매수가 2,000만원이어도 대출금 바의 1/3 지점에서 5억원을 선택·표시해야 합니다.");

    const vacancySlider = page.locator('[data-rental-slider="rentalVacancyMonths"]');
    await vacancySlider.evaluate((element) => {
      element.value = "0";
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForFunction(() => window.__rentalAnalysisResult?.vacancyMonths === 0);
    const zeroVacancy = await page.evaluate(() => ({
      vacancy: window.__rentalAnalysisResult.vacancyMonths,
      assumptionHidden: document.querySelector("[data-vacancy-assumption]").classList.contains("hidden"),
      highlighted: document.querySelector("#rentalSensitivity tbody td.selected")?.textContent.trim(),
    }));
    expect(zeroVacancy.vacancy === 0 && zeroVacancy.assumptionHidden,
      "공실 0개월 직접 조정 시 가정 배지가 남거나 값이 변하지 않았습니다.");
    expect(zeroVacancy.highlighted && zeroVacancy.highlighted !== "—",
      "민감도 표에서 현재 조건 교차 셀이 강조되지 않았습니다.");

    await setValueFromLabel(page, "rentalVacancyMonths", 0.5);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.vacancyMonths === 0.5);
    const fractionalVacancy = await page.evaluate(() => {
      const headers = Array.from(document.querySelectorAll("#rentalSensitivity tbody th"))
        .map((header) => header.textContent.trim().replace(/\s+/g, " "));
      const selected = document.querySelector("#rentalSensitivity tbody td.selected");
      return {
        headers,
        rows: document.querySelectorAll("#rentalSensitivity tbody tr").length,
        selectedTitle: selected?.title || "",
        selectedValue: selected && Number(selected.textContent.trim().replace("%", "")),
        expectedValue: window.__rentalAnalysisResult.netYield,
      };
    });
    expect(fractionalVacancy.rows === 7 && fractionalVacancy.headers.some((header) => /0[,.]5개월/.test(header)),
      `공실 0.5개월이 정확한 민감도 행으로 표시되지 않았습니다: ${JSON.stringify(fractionalVacancy.headers)}`);
    expect(fractionalVacancy.selectedTitle.includes("공실 0.5개월 기준"),
      `공실 0.5개월 현재 칸의 계산 설명이 정확하지 않습니다: ${fractionalVacancy.selectedTitle}`);
    expectNear(fractionalVacancy.selectedValue, fractionalVacancy.expectedValue,
      "공실 0.5개월 민감도 현재 칸과 핵심 순수익률");

    await page.setViewportSize({ width: 360, height: 800 });
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      detailsCollapsed: !document.getElementById("rentalBasisDetails").open
        && !document.getElementById("rentalDetails").open,
      visibleSliderCount: document.querySelectorAll("#rentalSliders [data-rental-slider]").length,
      tableScrollWidth: document.querySelector(
        "#rentalSensitivity .rental-sensitivity-scroll, #rentalSensitivity .sensitivity-scroll",
      ).scrollWidth,
      tableClientWidth: document.querySelector(
        "#rentalSensitivity .rental-sensitivity-scroll, #rentalSensitivity .sensitivity-scroll",
      ).clientWidth,
      positionMap: document.querySelector("#rentalPositioning .positioning-map").getBoundingClientRect().toJSON(),
      sliderTouchAction: getComputedStyle(document.querySelector('[data-rental-slider="rentalMonthlyRent"]')).touchAction,
      sliderRowHeight: document.querySelector('[data-rental-row="rentalMonthlyRent"]').getBoundingClientRect().height,
      endpointStyle: getComputedStyle(document.querySelector('[data-rental-limits="rentalMonthlyRent"]')).fontSize,
    }));
    expect(mobile.scroll <= mobile.viewport && mobile.body <= mobile.viewport,
      `360px 화면에 가로 페이지 넘침이 있습니다: ${JSON.stringify(mobile)}`);
    expect(mobile.visibleSliderCount === 5, "모바일 화면에서 5개 입력 슬라이더가 모두 렌더링되어야 합니다.");
    expect(mobile.detailsCollapsed, "계산 근거·상세 지표는 기본 접힘 상태여야 합니다.");
    expect(mobile.tableScrollWidth > mobile.tableClientWidth,
      "모바일 임대 민감도 표는 가로 스크롤을 허용해야 합니다.");
    expect(Math.abs(mobile.positionMap.height - 300) < 2,
      `모바일 임대 포지셔닝 차트가 300px 높이가 아닙니다: ${mobile.positionMap.height}px`);
    expect(mobile.sliderTouchAction === "pan-y" && mobile.sliderRowHeight >= 44,
      `모바일 슬라이더의 터치 영역·세로 스크롤 설정이 부족합니다: ${JSON.stringify(mobile)}`);
    expect(mobile.endpointStyle === "11px", `모바일 월세 범위 글씨가 11px가 아닙니다: ${mobile.endpointStyle}`);
    await page.locator("#rentalUnitArea").focus();
    expect(await page.evaluate(() => document.activeElement?.id) === "rentalUnitArea",
      "모바일 키패드 종료 확인 전 면적 입력칸이 활성화되지 않았습니다.");
    await page.locator("#rentalUnitArea").press("Enter");
    expect(await page.evaluate(() => document.activeElement?.id !== "rentalUnitArea"),
      "전용면적 입력 완료 후 키패드 포커스가 남습니다.");
    await page.locator("#rentalLoanRate").focus();
    expect(await page.evaluate(() => document.activeElement?.id) === "rentalLoanRate",
      "금리 입력칸이 활성화되지 않았습니다.");
    await page.locator('[data-rental-slider="rentalPurchasePrice"]').dispatchEvent("pointerdown");
    expect(await page.evaluate(() => document.activeElement?.id !== "rentalLoanRate"),
      "모바일에서 슬라이더를 터치해도 숫자 입력칸 포커스가 남습니다.");
    await awaitScreenshotFonts(page);
    await page.screenshot({ path: "screenshots/rental-mobile-360.png", fullPage: true });
    await page.locator("#rentalSliders").screenshot({ path: "screenshots/rental-slider-controls-360.png" });

    const printReady = await page.evaluate(async () => {
      await window.livingstayRenderAnalysisPrintReport();
      const image = document.querySelector("#printGraph .print-chart-image");
      return {
        ready: window.__analysisPrintReport?.ready === true,
        hasImage: (image?.getAttribute("src") || "").startsWith("data:image/png"),
        summary: document.getElementById("printOverview").textContent,
        graphHasSensitivity: document.getElementById("printGraph").textContent.includes("민감도"),
        details: document.querySelector("#printGraph .print-rental-details")?.textContent || "",
      };
    });
    expect(printReady.ready && printReady.hasImage,
      `임대 분석 인쇄용 차트 렌더링이 준비되지 않았습니다: ${JSON.stringify(printReady)}`);
    expect(printReady.summary.includes("매수가 2000만원")
      && printReady.summary.includes("월세 30만원")
      && printReady.graphHasSensitivity,
      `인쇄 미리보기에서 현재 조건·민감도 표를 확인할 수 없습니다: ${JSON.stringify({
        hasPurchase: printReady.summary.includes("매수가 2000만원"),
        hasRent: printReady.summary.includes("월세 30만원"),
        graphHasSensitivity: printReady.graphHasSensitivity,
      })}`);

    const unexpectedWrites = apiCalls.filter((call) =>
      call.method !== "GET" && call.method !== "HEAD"
        && !["/api/favorites/migrate", "/api/alerts/migrate"].includes(call.path));
    expect(unexpectedWrites.length === 0,
      `테스트 중 알 수 없는 쓰기 API가 호출되었습니다: ${JSON.stringify(unexpectedWrites)}`);
    expect(pageErrors.length === 0, `브라우저 JS 오류: ${pageErrors.join(" | ")}`);

    const malformed = new URL("/analysis", BASE_URL);
    malformed.searchParams.set("building_id", String(BUILDING_ID));
    malformed.searchParams.set("mode", "rental");
    malformed.searchParams.set("r_unit_area", "17.6");
    malformed.searchParams.set("r_rent", "85129212260000");
    malformed.searchParams.set("r_purchase", "356240000");
    malformed.searchParams.set("preserve", "1");
    await page.goto(malformed.toString(), { waitUntil: "domcontentloaded" });
    await waitForRental(page);
    await page.waitForFunction(() => {
      const params = new URLSearchParams(location.search);
      return !params.has("r_rent") && !params.has("r_purchase")
        && params.get("preserve") === "1";
    });
    const cleanedUrl = await page.evaluate(() => ({
      params: Object.fromEntries(new URLSearchParams(location.search)),
      rent: Number(document.getElementById("rentalMonthlyRent").value),
      purchase: Number(document.getElementById("rentalPurchasePrice").value),
      rentMax: Number(document.querySelector('[data-rental-slider="rentalMonthlyRent"]').max),
    }));
    expect(Number.isFinite(cleanedUrl.rent) && cleanedUrl.rent <= 1000
      && Number.isFinite(cleanedUrl.purchase) && cleanedUrl.purchase <= 300000
      && cleanedUrl.rentMax <= 1000,
    `잘못된 URL의 월세·매입가가 정화되지 않았습니다: ${JSON.stringify(cleanedUrl)}`);
    expect(sliderWarnings.length === 2,
      `잘못된 URL 값 2개에 대한 경고가 필요합니다: ${JSON.stringify(sliderWarnings)}`);
    await setValueFromLabel(page, "rentalPurchasePrice", 500000);
    const largePurchase = await page.evaluate(() => ({
      purchase: Number(document.getElementById("rentalPurchasePrice").value),
      loanMax: Number(document.querySelector('[data-rental-slider="rentalLoanAmount"]').max),
      loanLabel: document.querySelector('[data-rental-limits="rentalLoanAmount"] span:last-child').textContent,
    }));
    expect(largePurchase.purchase === 500000 && largePurchase.loanMax === 1000
      && largePurchase.loanLabel === "40억",
    `50억 매수가·40억 대출금 한도가 맞지 않습니다: ${JSON.stringify(largePurchase)}`);
    await setValueFromLabel(page, "rentalDeposit", 5001);
    expect(Number(await page.locator("#rentalDeposit").inputValue()) <= 5000,
      "보증금 직접입력에서 5,000만원 상한을 초과했습니다.");
    const rentalControls = async () => page.evaluate(() =>
      Object.fromEntries(["rentalPurchasePrice", "rentalLoanAmount", "rentalDeposit",
        "rentalMonthlyRent", "rentalVacancyMonths"].map((field) => {
        const slider = document.querySelector(`[data-rental-slider="${field}"]`);
        return [field, {
          value: document.getElementById(field).value,
          min: slider.min, max: slider.max, step: slider.step,
        }];
      })));
    for (const [moving, next] of [["rentalLoanAmount", "1000"], ["rentalDeposit", "400"],
      ["rentalMonthlyRent", "30"], ["rentalVacancyMonths", "2"],
      ["rentalPurchasePrice", "400000"]]) {
      const before = await rentalControls();
      await page.locator(`[data-rental-slider="${moving}"]`).evaluate((slider, nextValue) => {
        slider.value = nextValue;
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      }, next);
      await page.waitForTimeout(400);
      const after = await rentalControls();
      for (const field of Object.keys(before)) {
        if (field === moving) continue;
        if (moving === "rentalPurchasePrice" && field === "rentalLoanAmount") {
          expect(after[field].value === before[field].value,
            "매수가 범위 변경이 한도 이내의 대출금 값까지 바꾸었습니다.");
        } else {
          expect(JSON.stringify(after[field]) === JSON.stringify(before[field]),
            `${moving} 가로바 조작이 ${field} 가로바에 영향을 주었습니다.`);
        }
      }
    }
    // 5억 is one third of both physical tracks. The visible limits and stored
    // financial values must remain the original absolute amounts.
    const purchaseTrack = page.locator('[data-rental-slider="rentalPurchasePrice"]');
    const loanTrack = page.locator('[data-rental-slider="rentalLoanAmount"]');
    for (const [tick, amount] of [[0, 3000], [300, 50000], [900, 500000]]) {
      await purchaseTrack.evaluate((slider, value) => {
        slider.value = String(value);
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      }, tick);
      expect(Number(await page.locator("#rentalPurchasePrice").inputValue()) === amount
        && await purchaseTrack.getAttribute("aria-valuetext") ===
          (amount >= 10000 ? amount / 10000 + "억원" : amount.toLocaleString("ko-KR") + "만원"),
      `매수가 ${tick} 눈금에서 ${amount}만원이 선택되지 않았습니다.`);
    }
    await setValueFromLabel(page, "rentalLoanAmount", 0);
    for (const [tick, amount] of [[0, 0], [333, 50000], [1000, 400000]]) {
      await loanTrack.evaluate((slider, value) => {
        slider.value = String(value);
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      }, tick);
      expect(Number(await page.locator("#rentalLoanAmount").inputValue()) === amount,
        `대출금 ${tick} 눈금에서 ${amount}만원이 선택되지 않았습니다.`);
    }
    await setValueFromLabel(page, "rentalPurchasePrice", 56321);
    expect(Number(await page.locator("#rentalPurchasePrice").inputValue()) === 56321
      && Number(await purchaseTrack.inputValue()) > 300
      && await purchaseTrack.getAttribute("max") === "900",
    "정확한 매수가 직접입력은 유지하고 바 위치만 5억 이후 구간에 맞춰야 합니다.");
    await setValueFromLabel(page, "rentalLoanAmount", 400001);
    expect(Number(await page.locator("#rentalLoanAmount").inputValue()) === 400000
      && (await page.locator('[data-rental-input-error="rentalLoanAmount"]').textContent()).includes("40억"),
    "대출금 직접입력은 40억까지만 허용해야 합니다.");
    const independentUrl = new URL(firstUrl);
    independentUrl.searchParams.set("r_loan", "50000");
    await page.goto(independentUrl.toString(), { waitUntil: "domcontentloaded" });
    await waitForRental(page);
    expect(Number(await page.locator("#rentalPurchasePrice").inputValue()) === 4000
      && Number(await page.locator("#rentalLoanAmount").inputValue()) === 50000
      && Number(await page.locator('[data-rental-slider="rentalLoanAmount"]').inputValue()) === 333,
    "공유 링크에서도 매수가보다 큰 대출금 5억원이 복원되어야 합니다.");
    if (failures.length) throw new Error(`임대수익 개편 회귀 실패:\n- ${failures.join("\n- ")}`);
    console.log("임대수익 개편 브라우저 회귀 테스트 통과");
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});