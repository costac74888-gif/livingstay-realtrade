const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const BUILDING_ID = 2753;
const OUTPUT = path.resolve(".agents/outputs/mj-reports");
const MODES = [
  { mode: "property", suffix: "부동산투자보고서" },
  { mode: "rental", suffix: "임대수익보고서" },
  { mode: "operation", suffix: "숙박운영보고서" },
];

async function startLocalApp() {
  const source = [
    "import json, time",
    "import app as server",
    "from werkzeug.serving import make_server",
    "port = 0",
    "http = make_server('127.0.0.1', port, server.app, threaded=True)",
    "port = http.server_port",
    "expires = int(time.time()) + 3600",
    "modes = ('property', 'rental', 'operation')",
    "tokens = {m: f'2753.{m}.{expires}.' + server._analysis_share_signature(2753, m, expires) for m in modes}",
    "print(json.dumps({'baseUrl': f'http://127.0.0.1:{port}', 'tokens': tokens}), flush=True)",
    "http.serve_forever()",
  ].join("\n");
  const child = spawn("python", ["-u", "-c", source], {
    stdio: ["ignore", "pipe", "ignore"],
  });
  const ready = await new Promise((resolve, reject) => {
    let buffer = "";
    const timeout = setTimeout(() => reject(new Error("로컬 데이터 서버 준비 시간 초과")), 120000);
    child.once("error", () => {
      clearTimeout(timeout);
      reject(new Error("로컬 데이터 서버를 시작하지 못했습니다."));
    });
    child.once("exit", () => {
      clearTimeout(timeout);
      reject(new Error("로컬 데이터 서버가 예상보다 일찍 종료됐습니다."));
    });
    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        try {
          const response = JSON.parse(line);
          if (response.baseUrl && response.tokens) {
            clearTimeout(timeout);
            resolve(response);
            return;
          }
        } catch (_) {}
      }
    });
  });
  return { child, ...ready };
}

async function applyModeInputs(page, mode) {
  if (mode === "rental") {
    await page.waitForFunction(() =>
      Number(document.querySelector("#rentalUnitArea")?.value) === 17.6
        && Number(document.querySelector("#rentalPurchasePrice")?.value) === 4000
        && Number(document.querySelector("#rentalMonthlyRent")?.value) === 50,
    null, { timeout: 20000 });
    await page.locator("#rentalBasisDetails").evaluate((el) => { el.open = true; });
  } else if (mode === "operation") {
    await page.waitForFunction(() => {
      const state = window.__operationAnalysisState;
      return state && state.adr === 70000 && state.occ === 78
        && state.opexRatio === 36 && state.mgmtFeeRatio === 10
        && state.purchasePrice === 4000 && state.compareRent === 50;
    }, null, { timeout: 20000 });
  }
}

async function createReport(browser, baseUrl, tokens, item) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Mobile Safari/537.36",
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const url = new URL("/analysis", baseUrl);
  url.searchParams.set("building_id", String(BUILDING_ID));
  url.searchParams.set("mode", item.mode);
  url.searchParams.set("share", tokens[item.mode]);
  if (item.mode === "rental") {
    Object.entries({
      r_unit_area: "17.6",
      r_purchase: "4000",
      r_deposit: "400",
      r_rent: "50",
      r_vacancy: "1",
    }).forEach(([key, value]) => url.searchParams.set(key, value));
  } else if (item.mode === "operation") {
    Object.entries({
      adr: "70000",
      occ: "78",
      opex_ratio: "36",
      mgmt_fee: "10",
      buy: "4000",
      rent: "50",
    }).forEach(([key, value]) => url.searchParams.set(key, value));
  }
  const response = await page.goto(url.toString(), { waitUntil: "domcontentloaded", timeout: 90000 });
  if (!response || !response.ok()) throw new Error(`${item.mode}: 분석 화면 응답 실패`);
  await page.waitForFunction(() => {
    const title = document.querySelector("#detailCard .detail-name, #rentalBuildingName");
    return title && title.textContent.includes("엠제이스톤");
  }, null, { timeout: 90000 });
  await page.waitForFunction(() => window.livingstayRenderAnalysisPrintReport instanceof Function);
  await page.waitForTimeout(500);
  await applyModeInputs(page, item.mode);

  const prepared = await page.evaluate((mode) => {
    if (mode === "property" && window.__analysisChartPrintLayout) {
      window.__analysisChartPrintLayout.resize(1120, 560);
    }
    if (mode === "rental" && window.__rentalChartPrintLayout) {
      window.__rentalChartPrintLayout.resize(1120, 560);
    }
    if (mode === "operation" && window.__operationChartRelayout) {
      window.__operationChartRelayout();
    }
    return {
      buildingId: window.livingstaySelectedAnalysisBuilding?.()?.building_id
        || window.__rentalAnalysisBuilding?.building_id
        || window.__operationAnalysisBuilding?.building_id,
      name: document.querySelector("#detailCard .detail-name, #rentalBuildingName")?.textContent,
      generated: document.querySelector("#generatedAt")?.textContent,
      transactions: document.querySelectorAll("#selectedTransactionRows tr").length,
    };
  }, item.mode);
  if (Number(prepared.buildingId) !== BUILDING_ID) {
    throw new Error(`${item.mode}: 다른 건물이 선택되었습니다 (${JSON.stringify(prepared)})`);
  }
  await page.evaluate(() => window.livingstayRenderAnalysisPrintReport());
  await page.emulateMedia({ media: "print" });
  if (item.mode === "operation") {
    const headlineLayout = await page.evaluate(() => {
      const box = document.querySelector("#printReport .print-result-line");
      const note = box?.querySelector(".print-operation-yield-note");
      const overview = document.querySelector("#printReport .print-overview");
      const content = document.querySelector("#printReport #printOverview");
      const rect = (el) => el ? { y: el.getBoundingClientRect().y,
        bottom: el.getBoundingClientRect().bottom, height: el.getBoundingClientRect().height } : null;
      return { box: rect(box), note: rect(note), overview: rect(overview),
        content: rect(content), cssHeight: getComputedStyle(box).height,
        basis: rect(document.querySelector("#printReport .print-basis")),
        paragraphs: Array.from(document.querySelectorAll("#printReport .print-basis > #printBasis > p")).map(rect),
        formula: rect(document.querySelector("#printReport .print-basis .formula")),
        caution: rect(document.querySelector("#printReport .print-caution")),
        legend: rect(document.querySelector("#printReport .print-report-legend")) };
    });
    if (headlineLayout.note.bottom > headlineLayout.content.bottom
      || headlineLayout.caution.bottom > headlineLayout.basis.bottom
      || headlineLayout.legend.bottom > headlineLayout.basis.bottom) {
      throw new Error(`숙박 보고서 텍스트/주의사항/탭 잘림: ${JSON.stringify(headlineLayout)}`);
    }
  }
  const report = await page.evaluate(() => {
    const root = document.querySelector("#printReport");
    const text = root?.innerText || "";
    const pageBox = document.querySelector("#printReport .print-page")?.getBoundingClientRect();
    const quadrants = Array.from(document.querySelectorAll(
      "#printGraph .quad, #printGraph .positioning-quadrant, #printGraph .operation-quadrant",
    )).map((el) => {
      const box = el.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    });
    return {
      mode: root?.dataset.mode,
      title: document.querySelector("#printReportTitle")?.textContent,
      serial: document.querySelector("#printReportSerial")?.textContent,
      generated: document.querySelector("#printReportMeta")?.textContent,
      text,
      pageHeight: pageBox?.height,
      quadrantCount: quadrants.length,
      quadrants,
      graphImage: !!document.querySelector("#printGraph img.print-chart-image"),
    };
  });
  if (report.mode !== item.mode || report.quadrantCount !== 4 || !report.graphImage) {
    throw new Error(`${item.mode}: 보고서 구조/차트 검증 실패: ${JSON.stringify({ ...report, text: undefined })}`);
  }
  if (!report.text.includes("엠제이스톤 레지던스")) {
    throw new Error(`${item.mode}: 인쇄 화면에 건물명이 없습니다: ${JSON.stringify({
      prepared, reportText: report.text.slice(0, 330),
      selected: await page.evaluate(() => window.livingstaySelectedAnalysisBuilding?.()?.building_id),
    })}`);
  }
  if (item.mode !== "property" && report.text.includes("민감도")) {
    throw new Error(`${item.mode}: 인쇄 보고서에 민감도 표가 남아 있습니다.`);
  }
  if (pageErrors.length) {
    throw new Error(`${item.mode}: 브라우저 오류: ${pageErrors.join(" | ")}`);
  }
  if (item.mode === "rental" && (!report.text.includes("17.6㎡")
    || report.text.includes("—㎡") || !report.text.includes("17.6"))) {
    throw new Error("임대 PDF에서 전용면적 17.6㎡ 확인 실패");
  }
  if (item.mode === "operation" && (!report.text.includes("70,000원")
    || !report.text.includes("OCC 78%") || !report.text.includes("36%")
    || !report.text.includes("10%") || !report.text.includes("4,000만원")
    || !report.text.includes("50만원"))) {
    throw new Error("숙박운영 PDF의 입력 조건 표시 확인 실패");
  }

  fs.mkdirSync(OUTPUT, { recursive: true });
  const outPath = path.join(OUTPUT, `홈앤스테이_엠제이스톤_레지던스_2026-09-25_${item.suffix}.pdf`);
  const bytes = await page.pdf({ format: "A4", printBackground: true, displayHeaderFooter: false });
  await page.close();
  await context.close();

  const tmpPath = outPath + ".tmp.pdf";
  fs.writeFileSync(tmpPath, bytes);
  let pdf;
  try {
    const check = execFileSync("python", ["-c", [
      "import fitz,json,sys",
      "d=fitz.open(sys.argv[1])",
      "print(json.dumps({'pages':len(d),'text':d[0].get_text(),'rect':[d[0].rect.width,d[0].rect.height]}))",
    ].join(";"), tmpPath], { encoding: "utf8" });
    pdf = JSON.parse(check.trim().split("\n").filter(Boolean).pop());
    if (pdf.pages !== 1) throw new Error(`${item.mode}: PDF가 ${pdf.pages}페이지입니다.`);
    for (const required of ["엠제이스톤 레지던스", "2026-09-25"]) {
      if (!pdf.text.includes(required)) throw new Error(`${item.mode}: PDF 본문에서 ${required} 확인 실패`);
    }
    if (item.mode === "operation" && !pdf.text.includes("손익분기 OCC")) {
      throw new Error("숙박 PDF 헤드라인 둘째 줄이 잘렸습니다.");
    }
    if (item.mode !== "property" && pdf.text.includes("민감도")) {
      throw new Error(`${item.mode}: PDF에 민감도 표가 인쇄됐습니다.`);
    }
    fs.renameSync(tmpPath, outPath);
  } finally {
    if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
  }
  console.log(JSON.stringify({
    mode: item.mode,
    path: outPath,
    bytes: bytes.length,
    pages: pdf.pages,
    A4: pdf.rect,
    generated: report.generated,
    serial: report.serial,
    building: "엠제이스톤 레지던스 (#2753)",
    transactions: prepared.transactions,
    quadrantCount: report.quadrantCount,
    reportText: report.text.replace(/\s+/g, " ").slice(0, 520),
  }));
}

function chromiumPath() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  return execFileSync("sh", ["-c", "command -v chromium || command -v chromium-browser || command -v google-chrome"], {
    encoding: "utf8",
  }).trim();
}

async function main() {
  const local = await startLocalApp();
  fs.mkdirSync(OUTPUT, { recursive: true });
  let browser = null;
  try {
    browser = await chromium.launch({ headless: true, executablePath: chromiumPath() });
    for (const item of MODES) await createReport(browser, local.baseUrl, local.tokens, item);
  } finally {
    if (browser) await browser.close();
    for (const key of Object.keys(local.tokens)) local.tokens[key] = "";
    local.child.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});