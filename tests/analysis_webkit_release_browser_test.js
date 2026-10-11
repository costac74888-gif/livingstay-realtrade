"use strict";
const { artifactDirectory } = require("./offline_support/capture_artifacts.cjs");

// Safari-engine regression, NOT an iPhone/device certification. WebKit's
// automation protocol exposes native tap only, not held/cancelled touch.
// Held gestures below are explicitly recorded as DOM event sequences.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { webkit, devices } = require("playwright-webkit-compat");
const runtime = process.env.PLAYWRIGHT_WEBKIT_EXECUTABLE_PATH ||
  require("./offline_support/webkit_runtime.cjs");
const { installApiMocks, valueFromLabel, rentalValueFromLabel } =
  require("./operation_redesign_browser_test");

const origin = process.env.OWNED_REGRESSION_ORIGIN || process.env.HOMENSTAY_OWNED_ORIGIN;
assert.ok(origin && process.env.BASE_URL === origin, "Owned fixture required; no live fallback");
assert.ok(process.env.NODE_OPTIONS?.includes("browser_guard.cjs"), "Mandatory transport guard required");
const out = artifactDirectory();
fs.mkdirSync(out, { recursive: true });

async function value(page, input) {
  return Number(await page.locator(input).inputValue());
}

async function instrument(page, input, clickOnly = false) {
  await page.evaluate(({ selector, clickOnly }) => {
    window.__releaseEvidence = { events: [], boundary: null };
    window.__releaseSelector = selector;
    window.__releaseClickOnly = clickOnly;
    if (window.__releaseRecorderInstalled) return;
    window.__releaseRecorderInstalled = true;
    for (const type of ["pointerdown", "pointerup", "pointercancel", "pointerleave",
      "touchstart", "touchend", "touchcancel", "lostpointercapture",
      "click", "blur", "pagehide", "visibilitychange"]) {
      window.addEventListener(type, event => {
        const log = window.__releaseEvidence;
        const current = Number(document.querySelector(window.__releaseSelector)?.value);
        log.events.push({ type, trusted: event.isTrusted, detail: event.detail,
          pointerType: event.pointerType, value: current, target: event.target.id || event.target.tagName });
        if (["pointerup", "pointercancel", "pointerleave", "lostpointercapture",
          "touchend", "touchcancel", "pagehide"].includes(type)
          || (type === "blur" && event.target === window)
          || (type === "visibilitychange" && document.hidden)) log.boundary = current;
      }, true);
    }
    // WebKit performs microtask checkpoints between DOM listeners; a
    // capture-listener microtask is NOT guaranteed to run after the button
    // handler. Use bubbling for the click-only investment baseline instead.
    window.addEventListener("click", () => {
      if (window.__releaseClickOnly) window.__releaseEvidence.boundary =
        Number(document.querySelector(window.__releaseSelector)?.value);
    });
  }, { selector: input, clickOnly });
}

async function stable(page, mode, input, name, records, expected = null) {
  const log = await page.evaluate(() => window.__releaseEvidence);
  assert.notEqual(log.boundary, null, `${mode}/${name}: missing release event baseline`);
  const immediate = await value(page, input);
  assert.equal(immediate, log.boundary, `${mode}/${name}: compatibility click changed value`);
  if (expected !== null) assert.equal(immediate, expected, `${mode}/${name}: exact step`);
  await page.waitForTimeout(720); // Six original repeat intervals, no tolerance.
  assert.equal(await value(page, input), log.boundary, `${mode}/${name}: repeat survived release`);
  records.push({ mode, name, inputMethod: name === "native-tap" ? "trusted WebKit tap" :
    "WebKit DOM event sequence", released: log.boundary, immediate,
    delayed: await value(page, input), events: log.events });
}

async function pointer(page, selector, type) {
  await page.locator(selector).evaluate((element, eventType) => {
    element.dispatchEvent(new PointerEvent(eventType, {
      bubbles: true, pointerId: 7, pointerType: "touch", isPrimary: true,
      button: 0, buttons: eventType === "pointerdown" ? 1 : 0,
    }));
  }, type);
}

async function compatibilityClick(page, selector) {
  await page.locator(selector).evaluate(element => element.dispatchEvent(
    new MouseEvent("click", { bubbles: true, detail: 0 })));
}

async function run() {
  const records = [], errors = [], calls = [];
  const browser = await webkit.launch({ headless: true, timeout: 15000,
    executablePath: runtime });
  const context = await browser.newContext({ ...devices["iPhone 13"],
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", error => errors.push(error.message));
  await installApiMocks(page, calls);
  // Give the investment controls actual peer/market evidence without changing
  // the original operation fixture/assertions.
  await page.route("**/api/analysis/assets?*", async route => {
    calls.push({ method: route.request().method(), path: "/api/analysis/assets" });
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      generated_at: "2026-10-01T00:00:00Z",
      baselines: { tourism_demand_index: 50, peer_price_gap: 0 },
      filters: { sidos: [], sggs: [], lodging_types: [], period_options: [] },
      summary: { registered_buildings: 1, transaction_count: 5, analyzed_buildings: 1 },
      methodology: { comparison_basis: {} }, candidates: { price: [], confidence: [], urgent: [] },
      items: [{ building_id: 101, name: "WebKit 격리 건물", lodging_type: "생활숙박시설",
        sido: "경기도", sgg: "수원시", address: "경기도 수원시 테스트로 1",
        tourism_demand_index: 50, peer_price_gap: 0, transaction_count: 5,
        peer_price_median: 200, building_period_price_median: 200, peer_building_count: 4,
        lat: 37.26, lng: 127.03 }],
    }) });
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  try {
    await page.goto(new URL("/analysis?building_id=101&mode=operation&rent=200&r_unit_area=30", origin).href);
    await page.waitForFunction(() => window.__operationAnalysisState?.adr > 0);
    await page.locator("#rentalUnitArea").fill("30");
    await page.locator("#rentalUnitArea").dispatchEvent("input");
    await page.locator("#rentalUnitArea").dispatchEvent("change");
    const modes = [
      { mode: "operation", tab: "operation", input: "#operationOcc",
        plus: '[data-operation-step="occ"][data-slider-direction="1"]',
        minus: '[data-operation-step="occ"][data-slider-direction="-1"]',
        reset: () => valueFromLabel(page, "occ", 50), delta: 1 },
      { mode: "rental", tab: "rental", input: "#rentalMonthlyRent",
        plus: '[data-rental-step="rentalMonthlyRent"][data-slider-direction="1"]',
        minus: '[data-rental-step="rentalMonthlyRent"][data-slider-direction="-1"]',
        reset: () => rentalValueFromLabel(page, "rentalMonthlyRent", 50), delta: 1 },
      { mode: "property", tab: "property", input: "#propertyPurchasePrice",
        plus: '[data-property-step="purchase"][data-direction="1"]',
        minus: '[data-property-step="purchase"][data-direction="-1"]',
        // Investment controls are click-only, not bindStepButtons repeaters.
        reset: async () => {
          await page.locator("#propertyPurchasePrice").fill("5000");
          await page.locator("#propertyPurchasePrice").dispatchEvent("input");
        }, delta: 100, clickOnly: true },
    ];
    for (const config of modes) {
      const { mode, input, plus, minus, reset, delta, clickOnly } = config;
      await page.locator(`#analysisTabs [data-analysis-mode="${config.tab}"]`).click();
      await page.locator(plus).waitFor({ state: "visible" });
      assert.equal(await page.locator(plus).isEnabled(), true, `${mode}: control must be active`);
      await reset();
      await page.locator(plus).scrollIntoViewIfNeeded();
      await instrument(page, input, clickOnly);
      const before = await value(page, input);
      await page.locator(plus).tap();
      await stable(page, mode, input, "native-tap", records,
        before + delta);
      const native = records.at(-1);
      assert.ok(native.events.some(e => e.type === "click" && e.trusted), `${mode}: native click required`);
      if (clickOnly) {
        // Click-only investment changes at click AFTER pointerup; its baseline
        // is captured separately by the click recorder in instrument().
        assert.equal(native.immediate, before + delta);
      }
      // A short press with Safari-style detail=0 compatibility click is a
      // separate assertion from the native tap's observed detail=1.
      if (!clickOnly) {
        await reset();
        await instrument(page, input);
        const start = await value(page, input);
        await pointer(page, plus, "pointerdown");
        await page.waitForTimeout(80);
        await pointer(page, plus, "pointerup");
        await compatibilityClick(page, plus);
        await stable(page, mode, input, "short-detail-zero-click", records, start + delta);
      }
      for (const boundary of ["pointerup", "touchend", "pointercancel", "touchcancel",
        "pointerleave", "lostpointercapture", "blur", "pagehide", "visibilitychange"]) {
        await reset();
        await instrument(page, input, clickOnly);
        const start = await value(page, input);
        await pointer(page, plus, "pointerdown");
        await page.waitForTimeout(900);
        const held = await value(page, input);
        if (clickOnly) assert.equal(held, start, `${mode}: remains click-only`);
        else assert.ok(held >= start + 3 * delta, `${mode}: must really repeat before ${boundary}`);
        if (["pointerleave", "lostpointercapture"].includes(boundary)) {
          await pointer(page, plus, boundary);
        } else if (boundary.startsWith("pointer")) {
          await pointer(page, "body", boundary); // Release OUTSIDE button.
        } else if (boundary.startsWith("touch")) {
          await page.locator("body").evaluate((element, type) => {
            // Safari exposes TouchEvent but does not support its constructor.
            const event = document.createEvent("TouchEvent");
            event.initEvent(type, true, true);
            element.dispatchEvent(event);
          }, boundary);
        } else if (boundary === "visibilitychange") {
          await page.evaluate(() => {
            Object.defineProperty(document, "hidden", { configurable: true, value: true });
            document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
          });
        } else {
          await page.evaluate(type => window.dispatchEvent(new Event(type)), boundary);
        }
        if (!clickOnly && !boundary.includes("cancel")) await compatibilityClick(page, plus);
        await stable(page, mode, input, `hold-outside-${boundary}`, records, clickOnly ? start : null);
        if (boundary === "visibilitychange") {
          await page.evaluate(() => { delete document.hidden; });
        }
      }
      await reset();
      const keyboardStart = await value(page, input);
      await page.locator(plus).press("Enter");
      assert.equal(await value(page, input), keyboardStart + delta, `${mode}: Enter preserved after touch`);
      await page.locator(minus).press("Space");
      assert.equal(await value(page, input), keyboardStart, `${mode}: Space preserved after touch`);
      if (mode === "operation") await valueFromLabel(page, "occ", 47.5);
      else if (mode === "rental") await rentalValueFromLabel(page, "rentalMonthlyRent", 47.5);
      else {
        await page.locator(input).fill("4751");
        await page.locator(input).dispatchEvent("input");
      }
      const direct = mode === "property" ? 4751 : 47.5;
      assert.equal(await value(page, input), direct, `${mode}: direct entry preserved`);
      await page.waitForTimeout(720);
      assert.equal(await value(page, input), direct, `${mode}: no old repeat after direct entry`);
      records.push({ mode, name: "keyboard-and-direct-entry", value: direct });
      await page.screenshot({ path: path.join(out, `${mode}-webkit.png`) });
    }
    assert.deepEqual(errors, [], "No page errors");
    // Same bootstrap mock allowances as the original suite; all are fulfilled
    // by installApiMocks (never forwarded to the owned HTTP server).
    assert.deepEqual(calls.filter(c => !["GET", "HEAD"].includes(c.method)
      && !["/api/analysis/recent", "/api/favorites/migrate", "/api/alerts/migrate"].includes(c.path)),
    [], "No unexpected mock writes");
    console.log("PASS WebKit analysis release boundaries", records.length);
  } finally {
    await context.tracing.stop({ path: path.join(out, "webkit-release-trace.zip") });
    fs.writeFileSync(path.join(out, "webkit-release.json"), JSON.stringify({
      engine: "WebKit", version: browser.version(),
      runtime,
      userAgent: await page.evaluate(() => navigator.userAgent).catch(() => null),
      limitation: "Native tap; held/cancel/pagehide sequences are DOM-injected, not physical iOS gestures.",
      records, errors, calls,
    }, null, 2));
    await browser.close();
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
