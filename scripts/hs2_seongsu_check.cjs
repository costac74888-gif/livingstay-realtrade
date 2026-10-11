/* Owned synthetic Preview. Actual read-only Kakao Maps/Places CDN is allowed;
 * all booking/registration/payment requests remain owned same-origin only. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  assert(process.env.REPLIT_DEV_DOMAIN, "Development domain required");
  const origin = `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const output = path.resolve(process.env.HS2_PREVIEW_ARTIFACT_DIR || "generated-artifacts/seongsu-preview");
  assert(output.startsWith(path.resolve("generated-artifacts") + path.sep), "Generated output only");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.HS2_CHROMIUM,
    headless: true, args: ["--no-sandbox", "--disable-gpu"] });
  const results = [], errors = [], blocked = [];
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
    userAgent: "Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36" });
  await context.route("**/*", route => {
    const u = new URL(route.request().url());
    const maps = ["dapi.kakao.com", "map.kakao.com", "rv.map.kakao.com",
      "fonts.googleapis.com", "fonts.gstatic.com"].includes(u.hostname)
      || /\.daumcdn\.net$|\.kakaocdn\.net$/.test(u.hostname);
    if (u.origin === origin || ["data:", "blob:"].includes(u.protocol)) return route.continue();
    if (u.protocol === "https:" && maps && ["GET", "HEAD"].includes(route.request().method())) return route.continue();
    blocked.push(u.origin);
    return route.abort();
  });
  const page = await context.newPage();
  const navigate = url => page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
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
  function pass(name) { results.push({ name, status: "PASS" }); console.log("PASS", name); }
  function datePlus(value, n) {
    const d = new Date(`${value}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  try {
    await navigate(origin + "/hs2/consumer?layers=stay");
    const status = await api("/__development__/status");
    assert.equal(status.database, "owned_ephemeral");
    assert.equal(status.synthetic_data_only, false);
    assert.equal(status.transaction_data_synthetic_only, true);
    assert.equal(status.public_facility_snapshot.synthetic, false);
    assert.equal(status.actual_toss, false);
    assert.equal(status.external_delivery, false);
    assert.equal(status.production_entrypoint, false);
    pass("Owned ephemeral transactions / no actual Toss / no delivery / no production writes");
    const catalog = await api("/hs2/api/consumer/search?q=" + encodeURIComponent("성수"));
    const ownedFixtures = await api("/__development__/seongsu/catalog");
    assert.equal(ownedFixtures.synthetic, true);
    assert.equal(ownedFixtures.actual_toss, false);
    const fixtureById = new Map(ownedFixtures.items.map(row => [row.public_id, row]));
    assert.equal(catalog.items.length, 14);
    assert.equal(new Set(catalog.items.map(r => {
      const p = r.preview_demo.point; return `${p.lat},${p.lng}`;
    })).size, 14);
    for (const row of catalog.items) {
      const m = row.preview_demo;
      assert.equal(m.synthetic, true);
      assert(m.name.includes("가상") && m.description.includes("실제"));
      assert(m.photos.length && m.area_m2 > 0 && m.guests >= 2 && m.amenities.length);
      const fixture = fixtureById.get(row.public_id);
      assert(fixture.available_from < fixture.available_until);
      for (const key of ["application_id", "blocked_dates", "nightly_krw", "weekly_krw", "monthly_krw",
          "available_from", "available_until"]) assert(!Object.hasOwn(m,key));
      assert(row.base_rates !== null);
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
    const closed = catalog.items.find(r => r.stay_kind === "lodging" && fixtureById.get(r.public_id).blocked_dates.length);
    const blockedDate = fixtureById.get(closed.public_id).blocked_dates[0];
    const closedQuote = await api(`/hs2/details/api/items/${closed.public_id}/quote?check_in=${blockedDate}&check_out=${datePlus(blockedDate, 1)}&guests=2`,
      undefined, undefined, 400);
    assert.equal(closedQuote.ok, false);
    const apartment = catalog.items.find(r => r.stay_kind === "non_lodging" && !fixtureById.get(r.public_id).blocked_dates.length
        && r.base_rates.week > 0 && r.base_rates.month > 0);
    const first = fixtureById.get(apartment.public_id).available_from;
    const weekly = await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${datePlus(first, 7)}&guests=2`);
    assert.equal(weekly.quote.total_krw, apartment.base_rates.week);
    const month = require("./hs2_demo_assets/preview-rate-date.js").addMonthsClamped(first,1);
    const monthly = await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${month}&guests=2`);
    assert.equal(monthly.quote.total_krw, apartment.base_rates.month);
    await api(`/hs2/details/api/items/${apartment.public_id}/quote?check_in=${first}&check_out=${datePlus(first, 1)}&guests=2`,
      undefined, undefined, 400);
    pass("Closed dates blocked; exact weekly/calendar-month prices; non-lodging 1 night rejected");

    await page.waitForFunction(() => document.querySelectorAll("#listingList .listing-card").length === 14);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await navigate(origin + "/hs2/consumer?layers=stay");
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
      await navigate(origin + (width === 390 ? "/hs2/search/mobile/" : "/hs2/search/"));
      await page.waitForSelector(".listing-card", { state: "attached" });
      if (width === 390) {
        await page.locator("#panelToggle").click();
        assert.equal(await page.locator("#panelToggle").getAttribute("aria-expanded"), "false");
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(output, `map-${width}.png`), fullPage: true });
      pass(`Photocards / enabled filters / no horizontal overflow at ${width}px`);
    }
    // Newly created quote, booking, operator approval, and financial contract.
    // Nothing is marked paid until explicit owned signed mock capture.
    const lodging = catalog.items.find(r => r.stay_kind === "lodging" && r.base_rates.night > 0);
    let start;
    for (let offset = 60; offset < 150; offset += 3) {
      const candidate = datePlus(fixtureById.get(lodging.public_id).available_from, offset);
      const url = `/hs2/details/api/items/${lodging.public_id}/quote?check_in=${candidate}&check_out=${datePlus(candidate, 2)}&guests=2`;
      const available = await page.evaluate(async url => {
        const r = await fetch(url); return { status: r.status, data: await r.json() };
      }, url);
      if (available.status === 400 && available.data.code === "INVENTORY_UNAVAILABLE") continue;
      assert.equal(available.status, 200, "Availability probe: " + available.data.code);
      start = candidate; break;
    }
    assert(start, "No vacant synthetic two-night interval");
    const end = datePlus(start, 2);
    const selection = { check_in: start, check_out: end, guests: 2 };
    const detailPath = `/hs2/details/?public_id=${lodging.public_id}&check_in=${start}&check_out=${end}&guests=2`;
    await navigate(origin + detailPath);
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
    await page.setViewportSize({ width: 390, height: 1000 });
    await navigate(origin + "/hs2/workspace/?booking_id=" + booking.booking_id);
    await page.waitForFunction(() => document.querySelector("#workspace-feedback")?.dataset.state === "ready");
    await page.locator(".entry-action").click();
    await page.waitForFunction(() => document.querySelector("#workspace-feedback")?.textContent.includes("대화가 서버에서 확인"));
    const threads = await api("/hs2/workspace/api/threads?view=consumer");
    const thread = threads.items.find(t => t.booking_id === booking.booking_id);
    assert(thread, "New reservation must have a participant chat");
    await page.locator(`[data-thread-id="${thread.thread_id}"]`).click();
    const message = "[가상] 예약자 질문 " + crypto.randomUUID();
    await page.locator("#message-body").fill(message); await page.click("#send-message");
    await page.waitForFunction(m => document.querySelector("#messages-list")?.textContent.includes(m), message);
    await navigate(origin + "/hs2/workspace/?view=operator&thread_id=" + thread.thread_id);
    await page.waitForFunction(m => document.querySelector("#messages-list")?.textContent.includes(m), message);
    const reply = "[가상] 운영자 답변 " + crypto.randomUUID();
    await page.locator("#message-body").fill(reply); await page.click("#send-message");
    await page.waitForFunction(m => document.querySelector("#messages-list")?.textContent.includes(m), reply);
    await page.screenshot({ path: path.join(output, "operator-booking-chat-390.png"), fullPage: true });
    await navigate(origin + "/hs2/workspace/?view=consumer&thread_id=" + thread.thread_id);
    await page.waitForFunction(m => document.querySelector("#messages-list")?.textContent.includes(m), reply);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(m => document.querySelector("#messages-list")?.textContent.includes(m), reply);
    await page.screenshot({ path: path.join(output, "consumer-booking-chat-390.png"), fullPage: true });
    pass("New reservation chat: consumer sends, operator replies, consumer reload retains reply");
    await api(`/__development__/seongsu/payments/${contract.contract_id}/capture`,
      { acknowledged: true }, "invalid", 403);
    await api(`/__development__/seongsu/payments/${contract.contract_id}/capture`,
      { acknowledged: false }, finance.consumer_csrf, 400);
    await navigate(origin + `/hs2/finance/?contract_id=${contract.contract_id}`);
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
    await navigate(origin + "/hs2/bookings/");
    await page.waitForSelector(`[data-booking-id="${booking.booking_id}"]`);
    await navigate(origin + "/hs2/dashboard/");
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
    await normal.goto(origin + "/hs2/consumer", { waitUntil: "domcontentloaded", timeout: 60000 });
    await normal.waitForSelector("#listingList .listing-card");
    assert.equal(await normal.locator("#listingList img").count(), 0);
    assert.equal(await normal.locator("#guests").isDisabled(), true);
    assert.equal(await normal.locator(".demo-test-badge").count(), 0);
    assert.equal(await normal.locator("#listingList").innerText().then(t => t.includes("[가상]")), false);
    await normal.close();
    pass("Normal shared template retains withheld photos/metadata and disabled protected filters");
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    pass("No page errors; only read-only approved map/font hosts; no other outbound traffic");
    const summary = { status: "PASS", checks: results, actual_toss: false,
      actual_money_executed: false, production_writes: false,
      private_production_data: false,
      public_facility_source: status.public_facility_snapshot.source,
      blocked_font_requests: blocked.length };
    await fs.writeFile(path.join(output, "summary.json"), JSON.stringify(summary, null, 2));
    console.log(JSON.stringify(summary));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
