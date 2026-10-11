"use strict";
require("./offline_support/capture_preload.cjs");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const { artifactDirectory, artifactPath } = require("./offline_support/capture_artifacts.cjs");

(async () => {
  const root = artifactDirectory();
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  try {
    const context = await browser.newContext();
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage();
    await page.setContent("<h1>Capture isolation</h1>");
    const pagePath = artifactPath("screenshots/capture-contract-page.png");
    const locatorPath = artifactPath("screenshots/capture-contract-locator.png");
    const pdfPath = artifactPath("screenshots/capture-contract.pdf");
    const directPdf = artifactPath("/tmp/capture-contract-direct.pdf");
    const trace = artifactPath("screenshots/capture-contract-trace.zip");
    await page.screenshot({ path: pagePath });
    await page.locator("h1").screenshot({ path: locatorPath });
    await page.pdf({ path: pdfPath });
    fs.writeFileSync(directPdf, await page.pdf());
    await context.tracing.stop({ path: trace });
    for (const file of [pagePath, locatorPath, pdfPath, directPdf, trace]) {
      assert.ok(file.startsWith(root + "/"));
      assert.ok(fs.statSync(file).size > 0);
    }
    assert.equal(fs.readFileSync(pagePath).subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    assert.ok(fs.readFileSync(directPdf).subarray(0, 5).toString().startsWith("%PDF"));
    // A hash-frozen test can retain its literal path while the preload sends
    // page captures to the same run folder. Verify both page creation paths.
    const legacyImage = "screenshots/capture-contract-vetted.png";
    const legacyPDF = "screenshots/capture-contract-vetted.pdf";
    await page.screenshot({ path: legacyImage });
    await page.pdf({ path: legacyPDF });
    assert.ok(fs.statSync(artifactPath(legacyImage)).size > 0);
    assert.ok(fs.statSync(artifactPath(legacyPDF)).size > 0);
    assert.equal(fs.existsSync(legacyImage), false);
    assert.equal(fs.existsSync(legacyPDF), false);
    const directPage = await browser.newPage();
    await directPage.setContent("<h1>Reviewed page</h1>");
    await directPage.screenshot({ path: "screenshots/capture-contract-direct.png" });
    assert.ok(fs.statSync(artifactPath("screenshots/capture-contract-direct.png")).size > 0);
    assert.equal(fs.existsSync("screenshots/capture-contract-direct.png"), false);
    console.log("PASS page, locator, PDF, direct buffer and trace capture isolation");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
