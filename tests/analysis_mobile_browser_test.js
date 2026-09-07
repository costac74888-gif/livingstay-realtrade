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
    lodging_type: "생활숙박시설", tourism_growth: growth,
    tourism_demand_index: 50 + growth, price_change: price, quadrant,
    is_representative: representative, transaction_count: 3,
  };
}

function fixture(incompleteSelected = false) {
  const payload = {
    generated_at: "2026-09-07T00:00:00Z",
    baselines: { tourism_growth: 17, tourism_demand_index: 53, price_change: 12 },
    filters: { sidos: ["강원특별자치도"], sggs: ["속초시"], lodging_types: [], period_options: [] },
    summary: { registered_buildings: 7, transaction_count: 20, analyzed_buildings: 7, analysis_sample_transaction_count: 20 },
    methodology: {},
    items: [
      item(SELECTED_ID, "선택 테스트 자산", "강원특별자치도", "속초시", 14, 18, "슈퍼 에셋"),
      item(102, "같은 지역 비교", "강원특별자치도", "속초시", -13, 10, "가격 선행과열"),
      item(201, "가격선행과열대표자산", "서울특별시", "중구", -24, 27, "가격 선행과열", true),
      item(202, "관광가격동반상승대표", "부산광역시", "해운대구", 25, 24, "슈퍼 에셋", true),
      item(203, "관광가격동반하락대표", "전라남도", "목포시", -22, -25, "침체·약세", true),
      item(204, "관광상승저평가대표자산", "제주특별자치도", "제주시", 23, -22, "저평가 알짜", true),
    ],
  };
  if (incompleteSelected) {
    payload.items[0].tourism_growth = null;
    payload.items[0].price_change = 0.8;
    payload.items[0].quadrant = "관광 비교기간 부족";
    payload.items[0].transaction_count = 229;
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
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return json(route, { logged_in: true, user: { id: 1, name: "테스트 회원" } });
    if (url.pathname === "/api/analysis/assets") return json(route, fixture(incompleteSelected));
    if (url.pathname === "/api/favorites/mine") return json(route, { items: [] });
    if (url.pathname.endsWith("/photos")) return json(route, { photos: [] });
    return json(route, { ok: true, items: [] });
  });

  try {
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 720 });
      const response = await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
      expect(response && response.ok(), `${width}px 인증 모바일 투자분석 화면을 열지 못했습니다.`);
      await page.waitForFunction(() => {
        const layout = window.__analysisChartLayout;
        return layout && layout.ready && layout.labels && layout.labels.length === 4
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
        loggedInWorkspace: !document.getElementById("workspace").classList.contains("hidden"),
      };
      });

      expect(result.loggedInWorkspace, `${width}px 로그인 상태인데 분석 작업영역이 표시되지 않았습니다.`);
    expect(result.baselineText[0] === "0%" && result.baselineText[1] === "0%", "증감률 사분면 기준이 0%가 아닙니다.");
    const { baseline, points, labels, quadrantText } = result.layout;
    expect(Math.abs(baseline.x - baseline.quadrantRight[0]) < 0.6 && Math.abs(baseline.x - baseline.quadrantRight[1]) < 0.6,
      "세로 0% 점선과 사분면 배경 경계가 일치하지 않습니다.");
    expect(Math.abs(baseline.y - baseline.quadrantBottom[0]) < 0.6 && Math.abs(baseline.y - baseline.quadrantBottom[1]) < 0.6,
      "가로 0% 점선과 사분면 배경 경계가 일치하지 않습니다.");
    expect(baseline.valueX === 0 && baseline.valueY === 0, "증감률 차트의 점선이 실제 0% 좌표를 사용하지 않습니다.");

    const selected = points.find((point) => point.selected);
    const nearby = points.find((point) => point.sameRegion && !point.selected);
    const representatives = points.filter((point) => point.representative);
    expect(selected && selected.color === "#102a43" && selected.radius === 10, "선택 건물의 색상 또는 크기가 다릅니다.");
    expect(nearby && nearby.color === "#168f91" && nearby.radius === 5.5, "같은 시군구 비교군의 색상 또는 크기가 다릅니다.");
      expect(representatives.length === 4 && representatives.every((point) => point.radius === 8),
      "사분면 대표 표본 네 개의 표시 크기가 다릅니다.");
      const expectedRepresentatives = {
        201: { quadrant: "가격 선행과열", color: "#df5b57", name: "가격선행과열대표자산", region: "중구" },
        202: { quadrant: "슈퍼 에셋", color: "#168cc4", name: "관광가격동반상승대표", region: "해운대구" },
        203: { quadrant: "침체·약세", color: "#758596", name: "관광가격동반하락대표", region: "목포시" },
        204: { quadrant: "저평가 알짜", color: "#2aa96f", name: "관광상승저평가대표자산", region: "제주시" },
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
      quadrantText.forEach((text) => expect(
        !overlaps(label, text),
        `대표 라벨 ${label.id}가 사분면 설명과 겹칩니다: ${JSON.stringify({ label, text })}`,
      ));
      });
      for (let i = 0; i < labels.length; i += 1) {
      for (let j = i + 1; j < labels.length; j += 1) {
        expect(!overlaps(labels[i], labels[j]), `대표 라벨 ${labels[i].id}와 ${labels[j].id}가 겹칩니다.`);
      }
      }
    }
    incompleteSelected = true;
    await page.goto(`${BASE_URL}/analysis?building_id=${SELECTED_ID}`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => {
      const layout = window.__analysisChartLayout;
      return layout && layout.ready && layout.points
        && layout.points.some((point) => point.selected && point.color === "#758596");
    });
    const incompleteResult = await page.evaluate(() => {
      const layout = window.__analysisChartLayout;
      return {
        selected: layout.points.find((point) => point.selected),
        baseline: layout.baseline,
        detail: document.querySelector(".detail-quadrant").textContent,
        transactionCount: document.querySelector(".detail-metrics").textContent,
      };
    });
    expect(incompleteResult.selected.radius === 10, "비교기간 부족 선택 건물의 점 크기가 유지되지 않았습니다.");
    expect(Math.abs(incompleteResult.selected.x - incompleteResult.baseline.x) < 0.6,
      "관광 비교기간 부족 건물이 관광 0% 기준선에 표시되지 않았습니다.");
    expect(Math.abs(incompleteResult.selected.y - incompleteResult.baseline.y) > 0.6,
      "가격변동 값이 있는 건물이 중앙점으로 잘못 표시됐습니다.");
    expect(incompleteResult.detail.includes("관광 비교기간 부족"),
      "부족한 비교축이 관광 자료임을 구체적으로 안내하지 않습니다.");
    expect(incompleteResult.transactionCount.includes("229건"),
      "기간 거래건수가 비교기간 부족 안내와 함께 보존되지 않았습니다.");
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