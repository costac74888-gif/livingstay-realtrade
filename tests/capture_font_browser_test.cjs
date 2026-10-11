"use strict";
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const { chromium } = require("playwright");
const { prepareCaptureFont, captureFontCSS } = require("./offline_support/capture_font.cjs");
const { artifactPath } = require("./offline_support/capture_artifacts.cjs");

(async () => {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage();
    const requests = [];
    page.on("request", request => requests.push(request.url()));
    await page.route("**/*", route => route.abort());
    await page.setContent(`<style>
      body {font-family: "Noto Sans KR", sans-serif}
      #bold {font-weight: 700}
    </style><p id="regular">한글 숙박자산 분석 보고서</p><p id="bold">객실매출 손익분기 기준</p>`);
    delete process.env.SAVE_ANALYSIS_SCREENSHOTS;
    await prepareCaptureFont(page);
    assert.equal(await page.locator("#offline-analysis-capture-font").count(), 0);
    process.env.SAVE_ANALYSIS_SCREENSHOTS = "1";
    assert.doesNotMatch(captureFontCSS(), /https?:|@import/);
    await prepareCaptureFont(page);
    await prepareCaptureFont(page);
    assert.equal(await page.locator("#offline-analysis-capture-font").count(), 1);

    // FontFace.check alone can pass on fallback tofu. Chromium must actually
    // render the Korean nodes with our embedded custom Korean fixture font.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("DOM.enable");
    await cdp.send("CSS.enable");
    const { root } = await cdp.send("DOM.getDocument");
    for (const selector of ["#regular", "#bold"]) {
      const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
      const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
      assert.ok(fonts.length > 0);
      assert.ok(fonts.every(font => font.isCustomFont && /NanumGothic|Nanum Gothic/.test(font.familyName)
        && font.glyphCount > 0), JSON.stringify(fonts));
    }
    const png = artifactPath("screenshots/offline-korean-font.png");
    const pdf = artifactPath("screenshots/offline-korean-font.pdf");
    await page.screenshot({ path: png });
    const buffer = await page.pdf({ path: pdf });
    assert.equal(fs.readFileSync(png).subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    assert.match(buffer.toString("latin1"), /\/FontFile2\b/);
    assert.deepEqual(requests, [], "Local capture fonts must not issue any network requests");

    await page.setContent("<p>새 보고서 한글</p>");
    await prepareCaptureFont(page);
    assert.equal(await page.locator("#offline-analysis-capture-font").count(), 1);
    console.log("PASS offline Korean font: no-op, idempotence, glyphs, PNG, embedded PDF, new document");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
