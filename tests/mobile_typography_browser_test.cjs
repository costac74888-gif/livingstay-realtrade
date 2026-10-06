/* Real page rendering with read-only intercepted fixture APIs; never collect,
 * log in, send notifications, or persist test data. */
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const assert = require("node:assert/strict");

const origin = process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;
const id = 77777777;
const auctionId = 987654321;
const address = "인천광역시 서해구 석남동 511-16 해경스테이 1차 B동 407호";
const item = {
  id: auctionId, source: "onbid", source_item_id: "typography-fixture",
  title: "해경스테이 1차 B동 407호 생활숙박시설",
  address_jibun: address, address_road: "인천광역시 서해구 석남로 100",
  master_building_id: id, lodging_category: "생활", usage_name: "생활숙박시설",
  status: "bidding", area_m2: 36.514, min_bid_price: 5670286682,
  appraisal_price: 12639000000, management_no: "2026-000001-001",
  round_no: 6, failed_count: 5, bid_start_at: "2026-10-06T14:00:00",
  bid_end_at: "2026-10-07T17:00:00", agency: "한국자산관리공사",
};
const building = {
  building_id: id, id, building_name: "해경스테이 1차 - B동",
  lodging_type: "생활", road_address: item.address_road, jibun_address: address,
  umd_nm: "석남동", sgg_text: "인천광역시 서해구", units: 103,
  tot_area: 3874.37, area_m2: 36.514, detail_fetched_at: "2026-10-06",
  photos: [], agents: [], operators: [], loan_consultants: [],
  operating_records: [], membership_access: { required: true, info_url: "/membership" },
};

async function fixture(page) {
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    // No API mutation from the browser test is ever sent to the application.
    if (request.method() !== "GET") return route.fulfill({ json: { ok: true } });
    if (path === "/api/auth/me") {
      const signedInFixture = /\/(mypage|analysis)(?:\?|$)/.test(page.url());
      return route.fulfill({ json: signedInFixture ? {
        logged_in: true, id: 99999999, name: "가독성 검사", email: "test@example.invalid",
        account_type: "user", email_alert: false, weekly_email: false, phone_verified: false,
      } : { logged_in: false, user: null } });
    }
    if (path === "/api/auctions") return route.fulfill({ json: {
      ok: true, items: [item], total: 1, pages: 1, page: 1, page_size: 10,
    } });
    if (path === `/api/auctions/${auctionId}`) return route.fulfill({ json: {
      ok: true, item, building: { id, building_name: building.building_name },
      photos: [], rounds: [],
    } });
    if (path === `/api/auctions/${auctionId}/survey-info`) return route.fulfill({ json: {
      ok: true, membership_access: { required: true, info_url: "/membership" },
    } });
    if (path === `/api/building/${id}`) return route.fulfill({ json: building });
    if (path === `/api/building/${id}/auctions`) return route.fulfill({ json: {
      ok: true, items: [item], count: 1,
    } });
    // Unrelated read APIs use the real endpoint; no private records are required.
    return route.continue();
  });
}

async function fontAtLeast(page, selector, minimum) {
  const node = page.locator(selector).first();
  await node.waitFor({ state: "visible" });
  const size = await node.evaluate(el => parseFloat(getComputedStyle(el).fontSize));
  assert.ok(size >= minimum, `${selector}: ${size}px < ${minimum}px`);
}

async function fitsViewport(page, label) {
  const result = await page.evaluate(() => ({
    width: innerWidth,
    scroll: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  assert.ok(result.scroll <= result.width + 2, `${label}: page overflow ${JSON.stringify(result)}`);
}

async function tabsFit(page) {
  const tabs = await page.locator(".b-detail-tab").evaluateAll(nodes => nodes.map(el => {
    const r = el.getBoundingClientRect();
    return {
      left: r.left, right: r.right, width: r.width,
      scroll: el.scrollWidth, client: el.clientWidth, text: el.textContent.trim(),
    };
  }));
  assert.equal(tabs.length, 3);
  for (const tab of tabs) {
    assert.ok(tab.width > 0 && tab.left >= -1 && tab.right <= page.viewportSize().width + 1,
      `Tab outside viewport: ${JSON.stringify(tab)}`);
    assert.ok(tab.scroll <= tab.client + 2, `Clipped tab: ${JSON.stringify(tab)}`);
  }
  for (let i = 1; i < tabs.length; i++) {
    assert.ok(tabs[i].left >= tabs[i - 1].right - 1, "Tabs overlap");
  }
}

async function main() {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  fs.mkdirSync("screenshots/mobile-typography", { recursive: true });
  try {
    for (const width of [360, 390, 430, 1280]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 }, ignoreHTTPSErrors: true, locale: "ko-KR",
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      });
      await fixture(page);
      await page.goto(origin + "/auctions", { waitUntil: "domcontentloaded" });
      await page.locator(".auction-row").first().waitFor();
      if (width < 768) {
        await fontAtLeast(page, ".auction-title", 17);
        await fontAtLeast(page, ".auction-prices .auction-minimum b", 18);
        await fontAtLeast(page, ".auction-address", 16);
        await fitsViewport(page, `auction list ${width}`);
        const pricesFit = await page.locator(".auction-prices b").evaluateAll(nodes =>
          nodes.every(el => {
            const r = el.getBoundingClientRect();
            const parent = el.closest(".auction-prices").getBoundingClientRect();
            return r.height <= parseFloat(getComputedStyle(el).lineHeight) + 2
              && r.left >= parent.left && r.right <= parent.right;
          }));
        assert.ok(pricesFit, `Long prices must fit without splitting digits at ${width}px`);
      } else {
        const titleSize = await page.locator(".auction-title").first()
          .evaluate(el => parseFloat(getComputedStyle(el).fontSize));
        assert.ok(titleSize < 17, "Mobile enlargement must not change desktop titles");
      }
      if (width === 390) {
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({
          path: "screenshots/mobile-typography/auction-list-390.png", fullPage: true,
        });
      }
      await page.goto(origin + `/?auction=${auctionId}`, { waitUntil: "domcontentloaded" });
      await page.locator("#bTabAuctions").waitFor({ state: "visible" });
      await page.locator("#bTabAuctions").click();
      await page.locator(".auction-panel-general").waitFor();
      if (width < 768) {
        await tabsFit(page);
        await fontAtLeast(page, ".b-detail-tab", 16);
        await fontAtLeast(page, ".auction-panel-facts dd", 17);
        await fitsViewport(page, `auction detail ${width}`);
      }
      for (const [tab, panel] of [
        ["bTabProperty", "bPropertyPanel"],
        ["bTabOperations", "bOperationsPanel"],
        ["bTabAuctions", "bAuctionPanel"],
      ]) {
        await page.locator("#" + tab).click();
        await page.locator("#" + panel).waitFor({ state: "visible" });
        if (width < 768) {
          await tabsFit(page);
          await fitsViewport(page, `${panel} ${width}`);
        }
        if (width === 390) {
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(250);
          await page.screenshot({ path: `screenshots/mobile-typography/${panel}-390.png` });
        }
      }
      if (width < 768) {
        await page.locator("#bTabOperations").click();
        await fontAtLeast(page, ".b-membership-notice p", 16);
        await page.locator("#bTabProperty").click();
        await fontAtLeast(page, ".b-bldg-v", 17);
        await fontAtLeast(page, ".b-building-addresses", 16);
      } else {
        assert.equal(await page.locator(".b-detail-tab").first()
          .evaluate(el => parseFloat(getComputedStyle(el).fontSize)), 12);
      }
      console.log(`PASS ${width}px: auction list, three panels, font hierarchy and viewport`);
      if (width === 390) {
        for (const path of [
          "/menu", "/listings", "/transactions", "/notices", "/guide",
          "/membership", "/partner", "/agents", "/operators", "/loan-partners",
          "/terms", "/privacy", "/agent/login", "/operator/login",
          "/loan-consultant/login", "/reset-password", "/mypage", "/analysis",
        ]) {
          await page.goto(origin + path, { waitUntil: "domcontentloaded" });
          if (path === "/mypage") await page.locator("#myMain").waitFor({ state: "visible" });
          await page.waitForTimeout(150);
          await fitsViewport(page, path);
          const size = await page.locator("body")
            .evaluate(el => parseFloat(getComputedStyle(el).fontSize));
          assert.ok(size >= 17, `${path}: common mobile body ${size}px`);
          const input = page.locator('input:not([type=hidden]):visible, select:visible, textarea:visible').first();
          if (await input.count()) await fontAtLeast(page,
            'input:not([type=hidden]):visible, select:visible, textarea:visible', 16);
          console.log(`PASS public/gated entry ${path}: common type and no horizontal overflow`);
        }
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
