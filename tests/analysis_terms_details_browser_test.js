const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const browserPath = fs.existsSync(chromium.executablePath())
  ? chromium.executablePath()
  : execFileSync("sh", ["-c", "command -v chromium"], { encoding: "utf8" }).trim();

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: browserPath });
  try {
    for (const width of [1280, 360]) {
      const context = await browser.newContext({
        viewport: { width, height: 840 },
        // The app intentionally sends HTTP 204 to automated browser UAs.
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/analysis?mode=property`, { waitUntil: "domcontentloaded" });
      const result = await page.evaluate(() => {
        const property = document.getElementById("methodology");
        const rental = document.querySelector("#rentalAnalysis > .analysis-method-details");
        const propertyFormula = property.querySelector(".formula").textContent;
        const rentalFormula = rental.querySelector(".formula").textContent;
        const root = document.querySelector("main.analysis-shell");
        const paragraph = document.createElement("p");
        paragraph.textContent = "ADR · OCC · RevPAR · NOI · DSCR · R-ONE · OTA · GOP · ADR";
        root.appendChild(paragraph);
        const narrow = document.createElement("label");
        narrow.className = "terms-test-narrow";
        narrow.textContent = "ADR";
        document.getElementById("operationSliders").appendChild(narrow);
        return {
          propertyClosed: !property.open,
          rentalClosed: !rental.open,
          propertySummary: property.querySelector("summary").textContent,
          rentalSummary: rental.querySelector("summary").textContent,
          propertyFormula,
          rentalFormula,
          terms: Object.keys(window.livingstayAnalysisTerms.meanings),
        };
      });
      assert(result.propertyClosed && result.rentalClosed, `${width}px 계산 기준은 기본 접힘`);
      assert(result.propertySummary.includes("산식·자료 출처·유의사항")
        && result.rentalSummary.includes("산식·자료 출처·유의사항"));
      assert(result.propertyFormula.includes("관광수요 지수 = 시군구 방문자 수의 전국 백분위 × 100"));
      assert(result.rentalFormula.includes("실투자금 = 매입가 + 취득 부대비용 − 보증금 − 대출금"));
      assert.deepEqual(result.terms, ["ADR", "OCC", "RevPAR", "NOI", "DSCR", "R-ONE", "OTA", "GOP"]);
      await page.waitForFunction(() =>
        document.querySelector("main.analysis-shell > p:last-of-type")?.textContent.includes("ADR(객실 평균요금)"));
      const translated = await page.evaluate(() => {
        const paragraph = document.querySelector("main.analysis-shell > p:last-of-type");
        const narrow = document.querySelector("#operationSliders .terms-test-narrow");
        return { text: paragraph.textContent, short: narrow.textContent, hint: narrow.title };
      });
      for (const term of result.terms) {
        assert(translated.text.includes(windowLabel(term)), `${width}px ${term} 한글 병기`);
      }
      assert(translated.text.endsWith("· ADR"), "같은 문단의 두 번째 약어는 반복 병기하지 않는다");
      assert.equal(translated.short, width === 360 ? "ADR" : "ADR(객실 평균요금)");
      if (width === 360) assert.equal(translated.hint, "ADR(객실 평균요금)");
      await context.close();
    }
    console.log("분석 용어·계산기준 접기 브라우저 테스트 통과");
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

function windowLabel(term) {
  const meaning = {
    ADR: "객실 평균요금", OCC: "객실 이용률", RevPAR: "객실당 매출",
    NOI: "순영업소득", DSCR: "부채상환비율", "R-ONE": "한국부동산원 통계",
    OTA: "온라인 여행사", GOP: "영업총이익",
  };
  return `${term}(${meaning[term]})`;
}