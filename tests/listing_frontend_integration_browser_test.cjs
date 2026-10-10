// Browser-level frontend contract checks use deterministic API fixtures; no app auth or backend writes are bypassed.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const calls = [];
let queueLoads = 0;
let reviewWrites = [];
const auctionFixture = {
  id: 712, title: "해솔 숙박시설", lodging_category: "호텔", sale_kind: "국유",
  address_road: "서울특별시 강남구 테헤란로 12", appraisal_price: 12345000,
  min_bid_price: 6172500, min_bid_ratio: 50, failed_count: 2,
  bid_end_at: "2026-12-01T10:00:00", status: "bidding"
};
const listingFixtures = ["unit", "whole", "business_rights"].map((target, index) => ({
  id: 741 + index, building_id: 91, building_name: "검사용 숙박시설",
  transaction_target: target, lodging_type: "생활", deal_type: "매매",
  price_krw: 0, monthly_rent_krw: 0, key_money_krw: 0, area_sqm: 25,
  room_count: 12, yield_rate: 0, listing_date: "2026-10-10",
  photos: [], financial_details_visible: true, disclosure_scope: "public",
  business_rights_info: { facility_name: "검사용 영업장" }
}));

function json(res, data, status = 200) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(data));
}
function htmlFile(name, transform) {
  let body = fs.readFileSync(path.join(root, "static", name), "utf8");
  return transform ? transform(body) : body;
}
function fixtureGlobals() {
  return `<script>
    window.LodgingTypes={badge:(x)=>x||"숙박",color:()=>"rgb(60,80,100)"};
    window.LivingstayListingIcons={heart:()=>"",chat:()=>"문의",share:()=>"공유",photoCount:()=>""};
    window.Icons=window.Icons||{messageCircle:()=>"문의"};
    window.confirm=()=>true;
    window.openChat=()=>{};
  </script>`;
}
function stripExternalScripts(source, keep) {
  return source.replace(/<script\s+src=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (tag, src) =>
    keep.some(part => src.includes(part)) ? tag : "");
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/listings") {
    let body = stripExternalScripts(htmlFile("listings.html"), ["format_util.js", "/static/js/icons.js", "listing_icons.js", "listing_modal.js"]);
    body = body.replace('<script>\n(function(){', fixtureGlobals() + '<script>\n(function(){');
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" }); res.end(body); return;
  }
  if (url.pathname === "/broker-review") {
    let body = stripExternalScripts(htmlFile("broker_listing_review.html"), ["broker_listing_review.js"]);
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" }); res.end(body); return;
  }
  if (url.pathname === "/modal-harness") {
    const body = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head><body>
      <button id="openNew">새 등록 모달</button><button id="openEdit">수정 모달</button>${fixtureGlobals()}
      <script src="/static/js/listing_modal.js"></script><script>
      document.getElementById("openNew").onclick=()=>window.openListingRequestModal(91,"테스트 숙박시설",{});
      document.getElementById("openEdit").onclick=()=>window.openListingRequestModal(91,"테스트 숙박시설",{editId:77,prefill:{
        deal_mode:"broker",transaction_target:"business_rights",deal_type:"영업권양도",price_krw:0,
        monthly_rent_krw:0,key_money_krw:0,contact_phone:"010-2456-7890",
        business_rights_info:{facility_name:"편집 영업장",maintenance_fee_krw:0,adr_krw:0,lease_transfer_possible:false}
      }});
      </script></body></html>`;
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" }); res.end(body); return;
  }
  if (url.pathname.startsWith("/static/")) {
    const file = path.join(root, url.pathname);
    if (!file.startsWith(path.join(root, "static"))) { res.writeHead(403); res.end(); return; }
    try {
      const ext = path.extname(file);
      res.writeHead(200, { "content-type": ext === ".css" ? "text/css" : "text/javascript" });
      res.end(fs.readFileSync(file));
    } catch (_) { res.writeHead(404); res.end(); }
    return;
  }
  if (url.pathname === "/api/regions") return json(res, {
    "서울특별시": { sgg: { "서울특별시 강남구": { umd: {} } } },
    "부산광역시": { sgg: {} }
  });
  if (url.pathname === "/api/chat/my-listing-ids") return json(res, { ok: true, items: [] });
  if (url.pathname === "/api/auctions") {
    calls.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) });
    return json(res, {
      ok: true, total: 41, page: Number(url.searchParams.get("page") || 1),
      page_size: Number(url.searchParams.get("page_size") || 20),
      items: [{ ...auctionFixture, id: auctionFixture.id + Number(url.searchParams.get("page") || 1) }]
    });
  }
  if (url.pathname === "/api/listings") {
    const channel = url.searchParams.get("channel") || "direct";
    const target = url.searchParams.get("transaction_target");
    const limited = url.searchParams.get("disclosure_scope") === "limited";
    const items = listingFixtures.filter(item =>
      (!target || item.transaction_target === target) && (!limited || item.transaction_target !== "unit")
    ).map(item => ({
      ...item, deal_mode: channel, listing_channel: channel,
      is_limited_listing: limited, disclosure_scope: limited ? "limited" : "public"
    }));
    return json(res, { ok: true, items, has_more: false });
  }
  if (url.pathname === "/api/auth/me") return json(res, { logged_in: true, id: 23, name: "테스트 회원", phone: "010-2456-7890", phone_verified: true });
  if (url.pathname === "/api/listings/registration-context") return json(res, { ok: true, can_publish_broker: true });
  if (url.pathname.endsWith("/area-types")) return json(res, { ok: true, areas: [] });
  if (url.pathname.endsWith("/lodging-summary")) return json(res, { ok: true, room_count: 0 });
  if (url.pathname === "/api/listing-requests" && req.method === "POST") {
    let raw = ""; req.on("data", chunk => raw += chunk); req.on("end", () => { calls.push({ path: url.pathname, method: "POST", body: JSON.parse(raw) }); json(res, { ok: true, id: 912 }); }); return;
  }
  if (/^\/api\/listing-requests\/\d+$/.test(url.pathname) && req.method === "PUT") {
    let raw = ""; req.on("data", chunk => raw += chunk); req.on("end", () => { calls.push({ path: url.pathname, method: "PUT", body: JSON.parse(raw) }); json(res, { ok: true, id: 77 }); }); return;
  }
  if (/\/photos\/order$/.test(url.pathname)) return json(res, { ok: true });
  if (url.pathname === "/api/admin/broker-listings") {
    queueLoads++;
    return json(res, { ok: true, items: [{
      id: 51, listing_number: "BR-51", review_version: queueLoads === 1 ? "v-old" : "v-new",
      publication_status: queueLoads === 1 ? "pending" : "rejected", publication_reason: "최신 서류 확인",
      building_name: "바람결 스테이", road_address: "부산광역시 해운대구 달맞이길 10",
      deal_type: "월세", transaction_target: "business_rights", price_krw: 0,
      monthly_rent_krw: 125, key_money_krw: 0, monthly_revenue_krw: 0,
      annual_revenue_krw: 38000, operation_status: "영업중", short_stay_ratio: 0,
      ota_revenue_ratio: 38, room_count: 8,
      business_rights_info: { facility_name: "바람결 스테이", maintenance_fee_krw: 0, lease_term: "2년",
        adr_krw: 0, occ: 0, lease_transfer_possible: false, permit_status: "확인 필요" },
      description: "실제 운영과 인수 조건을 설명합니다.",
      office_name: "해안중개", owner_name: "김해안", reg_number: "가1234-5678",
      office_address: "부산광역시 해운대구", office_phone: "051-123-4567",
      phone: "010-1111-2222", registered_by: "등록 담당", created_at: "2026-09-15"
    }] });
  }
  if (/\/api\/admin\/broker-listings\/\d+\/review$/.test(url.pathname) && req.method === "POST") {
    let raw = ""; req.on("data", chunk => raw += chunk); req.on("end", () => {
      const body = JSON.parse(raw); reviewWrites.push(body);
      if (reviewWrites.length === 1) return json(res, { ok: false, message: "stale version" }, 409);
      return json(res, { ok: true, publication_status: body.decision });
    }); return;
  }
  json(res, { ok: true, items: [] });
});

(async () => {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"]
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      if (message.type() === "error" && message.text().startsWith("매물 목록 표시 실패")) {
        errors.push(message.text());
        console.error(message.text());
      }
    });
    await page.goto(`${base}/listings?channel=auction`);
    await page.locator(".ls-card-item").waitFor();
    assert.match(await page.locator(".ls-card-item").innerText(), /12,345,000원/);
    assert.doesNotMatch(await page.locator(".ls-card-item").innerText(), /만원/);
    await page.selectOption("#lsSido", "서울특별시");
    await page.selectOption("#lsSggNm", "서울특별시 강남구");
    await page.fill("#lsQ", "해솔");
    await page.selectOption("#lsAuctionCategory", "호텔");
    await page.selectOption("#lsAuctionKind", "국유");
    await page.selectOption("#lsAuctionStatus", "bidding");
    await page.fill("#lsAuctionRatioMin", "0");
    await page.fill("#lsAuctionRatioMax", "67.5");
    await page.fill("#lsAuctionFailedMin", "0");
    const search = page.waitForResponse(response => response.url().includes("/api/auctions?") && response.url().includes("failed_min=0"));
    await page.click("#lsBtnSearch");
    const response = await search;
    const query = new URL(response.url()).searchParams;
    assert.equal(query.get("region"), "서울특별시 강남구");
    assert.equal(query.get("q"), "해솔");
    assert.equal(query.get("category"), "호텔");
    assert.equal(query.get("kind"), "국유");
    assert.equal(query.get("status"), "bidding");
    assert.equal(query.get("ratio_min"), "0");
    assert.equal(query.get("ratio_max"), "67.5");
    assert.equal(query.get("failed_min"), "0");
    assert.equal(query.get("sort"), "deadline");
    assert.equal(await page.locator("#listingsMore").isVisible(), true);
    const nextPage = page.waitForResponse(response => response.url().includes("/api/auctions?") && new URL(response.url()).searchParams.get("page") === "2");
    await page.click("#listingsMore");
    await nextPage;
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.locator('#lsChannelTabs [data-channel="broker"]').click();
    assert.equal(await page.locator("#listingsTitle").innerText(), "숙박 매물 · 중개");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator('#lsChannelTabs [data-channel="direct"]').click();
    assert.equal(await page.locator("#listingsTitle").innerText(), "숙박 매물 · 직거래");
    assert.equal(await page.locator('a[href="/auctions"]').count(), 1);
    assert.deepEqual(errors, []);

    // Nonempty responses are essential: loadListings catches renderer exceptions.
    // Checking pageerror or only empty API responses cannot detect those failures.
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const channel of ["direct", "broker"]) {
        for (const scope of ["public", "limited"]) {
          await page.goto(`${base}/listings?channel=${channel}&disclosure_scope=${scope}`);
          const expected = scope === "limited" ? 2 : 3;
          await page.waitForFunction(count =>
            document.querySelectorAll("#lsBoardBody tr[data-listing-id]").length === count &&
            document.querySelectorAll(".ls-card-item[data-listing-id]").length === count,
          expected, { timeout: 5000 });
          assert.doesNotMatch(await page.locator("#lsBoardBody").innerText(), /오류가 발생|불러오기 실패/);
          if (width > 520) {
            await page.locator('.ls-view-tabs [data-view="board"]').click();
            assert.equal(await page.locator("#lsBoardBody").isVisible(), true);
          }
          await page.locator('.ls-view-tabs [data-view="card"]').click();
          assert.equal(await page.locator(".ls-card-item").first().isVisible(), true);
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        }
      }
    }
    assert.deepEqual(errors, []);

    const modalPage = await context.newPage();
    const modalErrors = [];
    modalPage.on("pageerror", error => modalErrors.push(error.message));
    await modalPage.goto(`${base}/modal-harness`);
    await modalPage.click("#openNew");
    await modalPage.locator("#lrForm").waitFor({ state: "visible" });
    assert.equal(await modalPage.locator('.lr-target[data-target="unit"]').count(),1);
    await modalPage.locator("#lrSubmit").click();
    await modalPage.locator("#lrDone").waitFor({ state: "visible" });
    assert.equal(calls.findLast(call=>call.path==="/api/listing-requests"&&call.method==="POST").body.transaction_target,"unit");
    await modalPage.locator("#lrClose").click();
    await modalPage.click("#openNew");
    await modalPage.locator("#lrForm").waitFor({ state: "visible" });
    await modalPage.locator('.lr-target[data-target="whole"]').click();
    await modalPage.locator("#lrSubmit").click();
    await modalPage.locator("#lrDone").waitFor({ state: "visible" });
    assert.equal(calls.findLast(call=>call.path==="/api/listing-requests"&&call.method==="POST").body.transaction_target,"whole");
    await modalPage.locator("#lrClose").click();
    await modalPage.click("#openNew");
    await modalPage.locator("#lrForm").waitFor({ state: "visible" });
    for (const target of ["unit", "whole", "business_rights"]) {
      await modalPage.locator(`.lr-target[data-target="${target}"]`).click();
      assert.notEqual(await modalPage.locator(`.lr-target[data-target="${target}"]`).evaluate(el => el.style.background), "rgb(255, 255, 255)");
    }
    await modalPage.locator('.lr-mode[data-mode="broker"]').click();
    await modalPage.locator("#lrRightsDeposit").fill("0");
    await modalPage.locator("#lrRightsRent").fill("0");
    await modalPage.locator("#lrRightsKeyMoney").fill("0");
    await modalPage.locator("#lrRightsMaintenance").fill("0");
    await modalPage.locator("#lrRightsAdr").fill("0");
    await modalPage.locator("#lrRightsFacility").fill("새벽 바다 스테이");
    await modalPage.locator("#lrRightsDeposit").dispatchEvent("input");
    await modalPage.waitForTimeout(80);
    const draft = await modalPage.evaluate(() => JSON.parse(localStorage.getItem("livingstay:listing-draft:23:91")).data);
    assert.equal(draft.transaction_target, "business_rights");
    assert.equal(draft.deal_mode, "broker");
    assert.equal(draft.rights_deposit, "0");
    assert.equal(draft.rights_rent, "0");
    assert.equal(draft.rights_key_money, "0");
    await modalPage.locator("#lrClose").click();
    await modalPage.click("#openNew");
    await modalPage.locator("#lrForm").waitFor({ state: "visible" });
    assert.equal(await modalPage.locator("#lrRightsDeposit").inputValue(), "0");
    assert.equal(await modalPage.locator("#lrRightsRent").inputValue(), "0");
    assert.equal(await modalPage.locator("#lrRightsKeyMoney").inputValue(), "0");
    await modalPage.locator("#lrSubmit").click();
    await modalPage.locator("#lrDone").waitFor({ state: "visible" });
    const created = calls.findLast(call => call.path === "/api/listing-requests" && call.method === "POST");
    assert.equal(created.body.transaction_target, "business_rights");
    assert.equal(created.body.deal_mode, "broker");
    assert.equal(created.body.publish_as_broker, true);
    assert.equal(created.body.price_krw, 0);
    assert.equal(created.body.monthly_rent_krw, 0);
    assert.equal(created.body.key_money_krw, 0);
    assert.match(await modalPage.locator("#lrDone").innerText(), /검수 요청이 접수/);
    assert.doesNotMatch(await modalPage.locator("#lrDone").innerText(), /게시 완료|공개되었습니다/);
    await modalPage.locator("#lrClose").click();
    await modalPage.click("#openEdit");
    await modalPage.locator("#lrForm").waitFor({ state: "visible" });
    assert.equal(await modalPage.locator("#lrRightsFacility").inputValue(), "편집 영업장");
    assert.equal(await modalPage.locator("#lrRightsMaintenance").inputValue(), "0");
    assert.equal(await modalPage.locator("#lrRightsAdr").inputValue(), "0");
    assert.equal(await modalPage.locator("#lrRightsLeaseTransfer").inputValue(), "false");
    await modalPage.locator("#lrSubmit").click();
    await modalPage.locator("#lrDone").waitFor({ state: "visible" });
    const edited = calls.findLast(call => call.path === "/api/listing-requests/77" && call.method === "PUT");
    assert.equal(edited.body.business_rights_info.maintenance_fee_krw, 0);
    assert.equal(edited.body.business_rights_info.adr_krw, 0);
    assert.equal(edited.body.business_rights_info.lease_transfer_possible, false);
    assert.equal(Object.hasOwn(edited.body, "deal_mode"), false);
    assert.deepEqual(modalErrors, []);

    // Ordinary members can request brokerage without publishing an advertisement.
    const memberPage = await context.newPage();
    await memberPage.route("**/api/listings/registration-context", route =>
      route.fulfill({ json: { ok: true, can_publish_broker: false } }));
    await memberPage.goto(`${base}/modal-harness`);
    for (const target of ["unit", "whole", "business_rights"]) {
      await memberPage.click("#openNew");
      await memberPage.locator("#lrForm").waitFor({ state: "visible" });
      const brokerButton = memberPage.locator('.lr-mode[data-mode="broker"]');
      assert.equal(await brokerButton.innerText(), "중개의뢰");
      assert.equal(await brokerButton.isEnabled(), true);
      await brokerButton.click();
      await memberPage.locator(`.lr-target[data-target="${target}"]`).click();
      assert.match(await memberPage.locator("#lrModeHelp").innerText(), /공개 매물로 게시되지 않습니다/);
      await memberPage.locator("#lrSubmit").click();
      await memberPage.locator("#lrDone").waitFor({ state: "visible" });
      const lead = calls.findLast(call => call.path === "/api/listing-requests" && call.method === "POST");
      assert.equal(lead.body.deal_mode, "broker");
      assert.equal(lead.body.publish_as_broker, false);
      assert.equal(lead.body.transaction_target, target);
      assert.match(await memberPage.locator("#lrDone").innerText(), /중개의뢰가 접수/);
      assert.doesNotMatch(await memberPage.locator("#lrDone").innerText(), /검수 요청|게시 승인/);
      await memberPage.locator("#lrClose").click();
    }
    await memberPage.route("**/api/listings/registration-context", route => route.abort());
    await memberPage.click("#openNew");
    await memberPage.locator('.lr-mode[data-mode="broker"]').click();
    assert.equal(await memberPage.locator('.lr-mode[data-mode="broker"]').isEnabled(), true);
    await memberPage.locator("#lrClose").click();

    const reviewPage = await context.newPage();
    await reviewPage.goto(`${base}/broker-review`);
    await reviewPage.locator(".review-card").waitFor();
    const initialReview = await reviewPage.locator(".review-card").innerText();
    for (const text of ["해안중개", "김해안", "가1234-5678", "0만원", "영업중", "2년", "실제 운영과 인수 조건", "검수 대기"]) {
      assert.ok(initialReview.includes(text), `review detail missing ${text}`);
    }
    await reviewPage.locator(".review-card textarea").fill("서류 확인 필요");
    await reviewPage.locator('[data-decision="rejected"]').click();
    await reviewPage.waitForFunction(() => document.querySelector(".review-card")?.dataset.reviewVersion === "v-new");
    assert.equal(reviewWrites[0].review_version, "v-old");
    await reviewPage.locator(".review-card textarea").fill("정보 확인 완료");
    await reviewPage.locator('[data-decision="approved"]').click();
    await reviewPage.waitForFunction(() => !document.querySelector(".review-card"));
    assert.equal(reviewWrites[1].review_version, "v-new");
    assert.deepEqual(errors, []);
    for (const width of [1280, 390]) {
      await reviewPage.setViewportSize({ width, height: 850 });
      assert.ok(await reviewPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    }

    const privacyPage = await context.newPage();
    await privacyPage.goto(`${base}/modal-harness`);
    await privacyPage.evaluate(() => {
      window.openListingDetailModal({
        id: 88, transaction_target: "business_rights", disclosure_scope: "limited",
        is_limited_listing: true, financial_details_visible: false,
        building_name: "비공개 영업장 고유명", road_address: "정확한 주소 비공개",
        description: "운영자 실명과 상세위치 비밀 설명", photo_url: "https://example.test/private.jpg",
        photos: [{url:"https://example.test/private-2.jpg"}],
        business_rights_info: {facility_name:"비공개 영업장 고유명"},
        approx_lat: 37.5, approx_lng: 127.0, lodging_type: "호텔"
      });
    });
    const privateText = await privacyPage.locator("#ls-listing-modal").innerText();
    for (const privateValue of ["비공개 영업장 고유명", "정확한 주소 비공개", "운영자 실명과 상세위치 비밀 설명"]) {
      assert.equal(privateText.includes(privateValue), false);
    }
    assert.equal(await privacyPage.locator("#ls-listing-modal img").count(), 0);
    assert.ok(privateText.includes("반경 500m"));
    for (const label of ["매물정보", "운영정보", "건물정보", "위치정보", "사진·영상", "문의하기"]) {
      assert.equal(await privacyPage.locator(`#ls-listing-modal nav a:has-text("${label}")`).count(), 1);
    }
    assert.ok(await privacyPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await privacyPage.setViewportSize({ width: 390, height: 844 });
    assert.ok(await privacyPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    console.log("PASS: nonempty direct/broker unit+whole+rights board/card public+limited desktop+mobile; auction filters+pagination; rights create/edit/draft/zero; stale review; shared detail/privacy");
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
