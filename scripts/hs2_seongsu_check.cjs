/* Explicitly owned synthetic Preview only. All requests run in same-origin
 * browser fetch. No provider keys, arbitrary origin or APIRequestContext. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  assert(process.env.REPLIT_DEV_DOMAIN, "Development domain required");
  const origin = `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const output = path.resolve("generated-artifacts/seongsu-preview");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.HS2_CHROMIUM,
    headless: true, args: ["--no-sandbox", "--disable-gpu"] });
  const results = [], errors = [], blocked = [];
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
    userAgent: "Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36" });
  await context.route("**/*", route => {
    const u = new URL(route.request().url());
    if (u.origin === origin || ["data:", "blob:"].includes(u.protocol)) return route.continue();
    blocked.push(u.origin);
    return route.abort();
  });
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  async function api(url, body, token, status = 200) {
    const response = await page.evaluate(async ({ url, body, token }) => {
      if (!url.startsWith("/hs2/") && !url.startsWith("/__development__/"))
        throw new Error("Owned route required");
      const response = await fetch(url, { credentials: "include",
        method: body === undefined ? "GET" : "POST",
        headers: { Accept: "application/json", ...(body === undefined ? {} : {
          "Content-Type": "application/json", "X-CSRF-Token": token || "" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      return { status: response.status, data: await response.json() };
    }, { url, body, token });
    assert.equal(response.status, status, `${url}: ${response.data.code || response.status}`);
    return response.data;
  }
  function pass(name) { results.push({ name, status: "PASS" }); }
  function datePlus(value, n) {
    const d = new Date(`${value}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  try {
    await page.goto(origin + "/hs2/consumer");
    const status = await api("/__development__/status");
    assert.equal(status.database, "owned_ephemeral");
    assert.equal(status.synthetic_data_only, true);
    assert.equal(status.actual_toss, false);
    assert.equal(status.external_delivery, false);
    assert.equal(status.production_entrypoint, false);
    pass("Owned ephemeral / no actual Toss / no delivery / no production");
    const catalog = await api("/hs2/api/consumer/search?q=" + encodeURIComponent("성수"));
    assert.equal(catalog.items.length, 14);
    assert.equal(new Set(catalog.items.map(r => {
      const p = r.preview_demo.point; return `${p.lat},${p.lng}`;
    })).size, 14);
    for (const row of catalog.items) {
      const m = row.preview_demo;
      assert.equal(m.synthetic, true);
      assert(m.name.includes("가상") && m.description.includes("실제"));
      assert(m.photos.length && m.area_m2 > 0 && m.guests >= 2 && m.amenities.length);
      assert(m.available_from < m.available_until);
    }
    pass("14 populated Seongsu stays at 14 distinct fictional coordinates");
    const all = await api("/hs2/search/api/results?layers=stay,sale,business,auction");
    assert.deepEqual(all.counts, { stay: 14, sale: 3, business: 3, auction: 3 });
    assert.equal(all.markers.length, 23);
    assert.equal(new Set(all.markers.map(m => `${m.point.lat},${m.point.lng}`)).size, 23);
    for (const layer of ["sale", "business", "auction"]) {
      const row = all.items.find(r => r.layer === layer);
      const detail = await api(`/hs2/search/api/detail/${layer}/${row.public_id}?layers=${layer}`);
      assert(detail.item.preview_demo.synthetic);
      assert.equal(detail.item.preview_demo.booking_supported, false);
    }
    pass("Sale / business / auction separate synthetic detail paths and 23 markers");
    const filtered = await api("/hs2/api/consumer/search?q=" + encodeURIComponent("성수동2가")
      + "&guests=4&min_area=35&options=wifi");
    assert(filtered.items.length > 0 && filtered.items.length < 14);
    assert(filtered.items.every(r => r.preview_demo.neighborhood === "성수동2가"
      && r.preview_demo.guests >= 4 && r.preview_demo.area_m2 >= 35));
    pass("Neighborhood / guests / area / amenities filters enforce source fields");
    const closed = catalog.items.find(r => r.stay_kind === "lodging" && r.preview_demo.blocked_dates.length);
    const blockedDate = closed.preview_demo.blocked_dates[0];
    const closedQuote = await api(`/hs2/details/api/items/${closed.public_id}/quote?check_in=${blockedDate}&check_out=${datePlus(blockedDate, 1)}&guests=2`,
      undefined, undefined, 400);
    assert.equal(closedQuote.ok, false);
    const apartment = catalog.items.find(r => r.stay_kind === "non_lodging" && !r.preview_demo.blocked_dates.length);
    const first = apartment.preview_demo.available_from;
    const weekly = await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${datePlus(first, 7)}&guests=2`);
    assert.equal(weekly.quote.total_krw, apartment.preview_demo.weekly_krw);
    const month = new Date(`${first}T00:00:00Z`);
    month.setUTCMonth(month.getUTCMonth() + 1);
    const monthly = await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${month.toISOString().slice(0, 10)}&guests=2`);
    assert.equal(monthly.quote.total_krw, apartment.preview_demo.monthly_krw);
    await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${datePlus(first, 1)}&guests=2`,
      undefined, undefined, 400);
    pass("Closed dates blocked; exact weekly/calendar-month prices; non-lodging 1 night rejected");

    await page.waitForFunction(() => document.querySelectorAll("#listingList .listing-card").length === 14);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(origin + "/hs2/consumer");
      await page.waitForFunction(() => document.querySelectorAll("#listingList .listing-card").length === 14);
      // Exercise actual lazy-image loading, including below-fold mobile cards.
      for (const image of await page.locator("#listingList img").all())
        await image.scrollIntoViewIfNeeded();
      await page.waitForFunction(() => [...document.querySelectorAll("#listingList img")].every(i => i.complete && i.naturalWidth > 0));
      await page.evaluate(() => { document.querySelector("#listingList").scrollTop = 0; window.scrollTo(0, 0); });
      assert(await page.locator("#listingList img").count() >= 14);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.equal(await page.locator("#guests").isDisabled(), false);
      await page.screenshot({ path: path.join(output, `consumer-${width}.png`), fullPage: true });
      await page.goto(origin + (width === 390 ? "/hs2/search/mobile/" : "/hs2/search/"));
      await page.waitForSelector(".listing-card", { state: "attached" });
      if (width === 390) {
        await page.locator("#mobile-map-btn").click();
        assert.equal(await page.locator("#mobile-map-btn").getAttribute("aria-pressed"), "true");
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(output, `map-${width}.png`), fullPage: true });
      pass(`Photocards / enabled filters / no horizontal overflow at ${width}px`);
    }
    // Newly created quote, booking, operator approval, and financial contract.
    // Nothing is marked paid until explicit owned signed mock capture.
    const lodging = catalog.items.find(r => r.stay_kind === "lodging");
    let start = datePlus(lodging.preview_demo.available_from, 60);
    while ([start, datePlus(start, 1)].some(d => lodging.preview_demo.blocked_dates.includes(d)))
      start = datePlus(start, 2);
    const end = datePlus(start, 2);
    const selection = { check_in: start, check_out: end, guests: 2 };
    const detailPath = `/hs2/details/?public_id=${lodging.public_id}&check_in=${start}&check_out=${end}&guests=2`;
    await page.goto(origin + detailPath);
    await page.waitForSelector(".demo-gallery img");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(output, "detail-390.png"), fullPage: true });
    const q = (await api(`/hs2/details/api/items/${lodging.public_id}/quote?check_in=${start}&check_out=${end}&guests=2`)).quote;
    const detailSession = await api("/hs2/details/api/session");
    const receipt = (await api(`/hs2/details/api/items/${lodging.public_id}/confirm-quote`,
      { ...selection, request_id: crypto.randomUUID(), acknowledged: true,
        expected_source_version: q.source_version }, detailSession.csrf_token)).receipt;
    const bookingSession = await api("/hs2/bookings/api/session");
    const booking = (await api("/hs2/bookings/api/request", {
      receipt_id: receipt.receipt_id, request_id: crypto.randomUUID(), acknowledged: true
    }, bookingSession.consumer_csrf)).booking;
    assert.equal(booking.status, "pending_operator");
    const approved = (await api(`/hs2/bookings/api/operator/${booking.booking_id}/action`,
      { action: "approve", revision: booking.revision }, bookingSession.operator_csrf)).booking;
    assert.equal(approved.status, "awaiting_payment");
    assert.equal(approved.payment_verified, false);
    const finance = await api("/hs2/finance/api/session");
    assert.equal(finance.preview_demo_capture_available, true);
    const terms = (await api(`/hs2/finance/api/quote/${booking.booking_id}`)).quote;
    const contract = (await api("/hs2/finance/api/contracts", {
      booking_id: booking.booking_id, request_id: crypto.randomUUID(), acknowledged: true,
      expected_terms_sha256: terms.terms_sha256
    }, finance.consumer_csrf)).contract;
    assert.equal(contract.status, "awaiting_payment");
    pass("Detail quote → persisted receipt → booking → operator approval → financial terms");
    await api(`/__development__/seongsu/payments/${contract.contract_id}/capture`,
      { acknowledged: true }, "invalid", 403);
    await api(`/__development__/seongsu/payments/${contract.contract_id}/capture`,
      { acknowledged: false }, finance.consumer_csrf, 400);
    await page.goto(origin + `/hs2/finance/?contract_id=${contract.contract_id}`);
    const card = page.locator(`[data-contract-id="${contract.contract_id}"]`).first();
    await card.waitFor();
    const capture = card.getByRole("button", { name: /모의 결제 진행/ });
    await capture.waitFor();
    assert.equal(await capture.isDisabled(), true);
    await card.locator("input.demo-capture-ack").check();
    const pending = page.waitForResponse(r => r.url().includes(`/payments/${contract.contract_id}/capture`));
    await capture.click();
    const captured = await (await pending).json();
    assert.equal(captured.actual_toss, false);
    assert.equal(captured.actual_money_executed, false);
    assert.equal(captured.contract.status, "captured");
    assert.equal(captured.contract.payment_verified, true);
    const again = await api(`/__development__/seongsu/payments/${contract.contract_id}/capture`,
      { acknowledged: true }, finance.consumer_csrf);
    assert.equal(again.contract.events.filter(e => e.kind === "capture").length, 1);
    const mine = await api("/hs2/bookings/api/consumer");
    assert(mine.bookings.some(b => b.booking_id === booking.booking_id && b.status === "confirmed"));
    await page.goto(origin + "/hs2/bookings/");
    await page.waitForSelector(`[data-booking-id="${booking.booking_id}"]`);
    await page.goto(origin + "/hs2/dashboard/");
    await page.waitForFunction(() => document.querySelector("#dashboard-feedback")?.dataset.state === "ready");
    assert(await page.locator("#dashboard-bookings").innerText());
    assert(await page.locator("#dashboard-contracts [data-contract-id]").count() >= 2);
    pass("Consent-gated signed mock payment UI → confirmed My Bookings → operator dashboard; replay idempotent");
    // The same original template without the server-only demo flag must not
    // promote synthetic metadata into the normal/private consumer contract.
    const normal = await context.newPage();
    const template = await fs.readFile("hs2_consumer/web/main.html", "utf8");
    assert(!template.includes('data-hs2-demo="seongsu"'));
    await normal.route("**/hs2/consumer", route =>
      route.fulfill({ status: 200, contentType: "text/html", body: template }));
    await normal.goto(origin + "/hs2/consumer");
    await normal.waitForSelector("#listingList .listing-card");
    assert.equal(await normal.locator("#listingList img").count(), 0);
    assert.equal(await normal.locator("#guests").isDisabled(), true);
    assert.equal(await normal.locator(".demo-test-badge").count(), 0);
    assert.equal(await normal.locator("#listingList").innerText().then(t => t.includes("[가상]")), false);
    await normal.close();
    pass("Normal shared template retains withheld photos/metadata and disabled protected filters");
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked.filter(host => ![
      "https://fonts.googleapis.com", "https://fonts.gstatic.com"
    ].includes(host)), []);
    pass("No page errors; external font attempts blocked; no external provider traffic");
    const summary = { status: "PASS", checks: results, actual_toss: false,
      actual_money_executed: false, production_data: false,
      blocked_font_requests: blocked.length };
    await fs.writeFile(path.join(output, "summary.json"), JSON.stringify(summary, null, 2));
    console.log(JSON.stringify(summary));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
