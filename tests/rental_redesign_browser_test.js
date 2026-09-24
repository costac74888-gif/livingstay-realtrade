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
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
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
  page.on("pageerror", (error) => pageErrors.push(error.message));
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
    expect(initial.hasVacancyParam && initial.vacancyParam === "",
      "가정 공실이 공유 URL에서 직접 입력값으로 바뀌었습니다.");
    fs.mkdirSync("screenshots", { recursive: true });
    await page.screenshot({ path: "screenshots/rental-desktop-1280.png", fullPage: true });

    await setValueFromLabel(page, "rentalMonthlyRent", 47);
    await page.waitForFunction(() => Number(window.__rentalAnalysisResult?.annualRent) === 564);
    const directValue = await page.evaluate(() => ({
      exactRent: Number(document.getElementById("rentalMonthlyRent").value),
      slider: Number(document.querySelector('[data-rental-slider="rentalMonthlyRent"]').value),
      headers: Array.from(document.querySelectorAll("#rentalSensitivity thead th")).map((node) => node.textContent.trim()),
      highlighted: document.querySelector("#rentalSensitivity tbody td.selected")?.title || "",
      returnBasis: window.__rentalAnalysisResult.returnBasis,
      netYield: window.__rentalAnalysisResult.netYield,
      noi: window.__rentalAnalysisResult.noi,
    }));
    expect(directValue.exactRent === 47 && directValue.slider === 45,
      `직접 입력 47만원을 슬라이더 위치 45로 함께 표시해야 합니다: ${JSON.stringify({
        exactRent: directValue.exactRent, slider: directValue.slider,
      })}`);
    expect(directValue.headers.includes("45만원") && directValue.highlighted.includes("입력값 47만원"),
      "민감도 표는 45만원 인접 칸을 강조하고 직접 입력값을 툴팁에 표시해야 합니다.");
    expectNear(directValue.netYield, directValue.noi / 3920 * 100,
      "월세 직접 입력 후 수익률");

    await setValueFromLabel(page, "rentalMonthlyRent", 30);
    await page.waitForFunction(() => window.__rentalAnalysisResult?.annualRent === 360);
    const debtFree = await page.evaluate(() => ({
      result: window.__rentalAnalysisResult,
      selectedCell: document.querySelector("#rentalSensitivity tbody td.selected")?.textContent.trim(),
      cards: document.getElementById("rentalCoreMetrics").textContent,
      debtCards: document.getElementById("rentalExtraMetrics").textContent,
    }));
    expectNear(debtFree.result.netYield, debtFree.result.cashReturn,
      "대출 0일 때 순수익률과 자기자본 수익률 일치");
    expect(debtFree.selectedCell === debtFree.result.netYield.toFixed(1) + "%",
      "월세 30·공실 1의 민감도 강조 칸과 핵심 카드 수익률이 일치하지 않습니다.");
    expect(!debtFree.debtCards.includes("DSCR") && !debtFree.debtCards.includes("월 대출 상환액"),
      "대출 0일 때 대출 상세 지표가 표시됩니다.");

    await setValueFromLabel(page, "rentalLoanAmount", 1500);
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
    await page.waitForTimeout(80);
    await setValueFromLabel(page, "rentalPurchasePrice", 2000);
    const loanCap = await page.evaluate(() => ({
      purchase: Number(document.getElementById("rentalPurchasePrice").value),
      loan: Number(document.getElementById("rentalLoanAmount").value),
      max: Number(document.querySelector('[data-rental-slider="rentalLoanAmount"]').max),
    }));
    expect(loanCap.purchase === 2000 && loanCap.loan === 1400 && loanCap.max === 1400,
      `매입가 하향 시 대출 한도가 1,400만원으로 조정되지 않았습니다: ${JSON.stringify(loanCap)}`);

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

    await page.setViewportSize({ width: 360, height: 800 });
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      detailsCollapsed: !document.getElementById("rentalBasisDetails").open
        && !document.getElementById("rentalDetails").open,
      visibleSliderCount: document.querySelectorAll("#rentalSliders [data-rental-slider]").length,
    }));
    expect(mobile.scroll <= mobile.viewport && mobile.body <= mobile.viewport,
      `360px 화면에 가로 페이지 넘침이 있습니다: ${JSON.stringify(mobile)}`);
    expect(mobile.visibleSliderCount === 5, "모바일 화면에서 5개 입력 슬라이더가 모두 렌더링되어야 합니다.");
    expect(mobile.detailsCollapsed, "계산 근거·상세 지표는 기본 접힘 상태여야 합니다.");
    await page.screenshot({ path: "screenshots/rental-mobile-360.png", fullPage: true });

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