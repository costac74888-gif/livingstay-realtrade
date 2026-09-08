const fs = require("fs");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const BUILDING_ID = 101;
const REPRESENTATIVE = "https://images.example.test/hotel-main.jpg";
const EXTRA = "https://images.example.test/hotel-room.jpg";

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

function installKakaoMapStub() {
  class LatLng {
    constructor(lat, lng) { this.lat = Number(lat); this.lng = Number(lng); }
    getLat() { return this.lat; }
    getLng() { return this.lng; }
  }
  class Map {
    constructor(container, options) {
      this.container = container; this.center = options.center; this.level = options.level;
    }
    addControl() {}
    addOverlayMapTypeId() {}
    removeOverlayMapTypeId() {}
    relayout() {}
    setMapTypeId() {}
    setBounds() {}
    setCenter(center) { this.center = center; }
    getCenter() { return this.center; }
    setLevel(level) { this.level = level; }
    getLevel() { return this.level; }
    getBounds() {
      return {
        getSouthWest: () => new LatLng(this.center.getLat() - 1, this.center.getLng() - 1),
        getNorthEast: () => new LatLng(this.center.getLat() + 1, this.center.getLng() + 1),
      };
    }
  }
  class CustomOverlay {
    constructor(options) { this.content = options.content; }
    setMap(map) {
      if (this.content instanceof HTMLElement && this.content.parentElement) this.content.remove();
      if (map && this.content instanceof HTMLElement) map.container.appendChild(this.content);
    }
    setZIndex() {}
  }
  window.kakao = {
    maps: {
      load: (callback) => callback(), Map, LatLng, CustomOverlay,
      Marker: class { setMap() {} }, MarkerImage: class {},
      InfoWindow: class { open() {} close() {} }, ZoomControl: class {},
      Size: class {}, Point: class {}, LatLngBounds: class { extend() {} },
      Polyline: class { setMap() {} },
      ControlPosition: { BOTTOMRIGHT: "BOTTOMRIGHT" },
      MapTypeId: { ROADMAP: "ROADMAP", SKYVIEW: "SKYVIEW", HYBRID: "HYBRID", ROADVIEW: "ROADVIEW" },
      event: { addListener() {}, removeListener() {} },
    },
  };
}

async function json(route, body, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function buildingFixture() {
  return {
    id: BUILDING_ID,
    building_id: BUILDING_ID,
    building_name: "부분 갤러리 테스트 호텔",
    display_building_name: "부분 갤러리 테스트 호텔",
    building_status: "완공",
    lodging_type: "관광",
    road_address: "서울특별시 중구 세종대로 101",
    lat: 37.5665,
    lng: 126.978,
    photos: [{ url: REPRESENTATIVE, source: "tourapi", is_primary: true }],
    direct_listings: [],
    partner_agents: [],
  };
}

async function run() {
  const browser = await chromium.launch({
    headless: true, executablePath: chromiumExecutable(),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const browserErrors = [];
  let scenario = "empty";
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.addInitScript(installKakaoMapStub);
  await page.route("**/dapi.kakao.com/**", (route) => route.fulfill({
    status: 200, contentType: "application/javascript", body: "/* browser-test Kakao stub */",
  }));
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("https://images.example.test/**", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="9"><rect width="16" height="9" fill="#b4863f"/></svg>',
  }));
  await page.route("**/apis.data.go.kr/B551011/KorService2/**", async (route) => {
    if (scenario === "error") return json(route, { message: "upstream failed" }, 503);
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/detailImage2")) {
      const items = scenario === "success"
        ? [
          { originimgurl: REPRESENTATIVE, imgname: "대표 외관" },
          { originimgurl: EXTRA, imgname: "객실" },
        ]
        : [];
      return json(route, {
        response: { header: { resultCode: "0000" }, body: { items: { item: items } } },
      });
    }
    return json(route, {
      response: { header: { resultCode: "0000" }, body: { items: { item: [] } } },
    });
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/building/${BUILDING_ID}`) return json(route, buildingFixture());
    if (url.pathname === `/api/building/${BUILDING_ID}/photos`) {
      return json(route, {
        ok: true,
        status: "partial",
        photos: [{ url: REPRESENTATIVE, source: "tourapi", is_primary: true }],
        building_name: "부분 갤러리 테스트 호텔",
        road_address: "서울특별시 중구 세종대로 101",
        tourapi_prewarm: { content_id: "test-content-id", photo_available: true },
      });
    }
    if (url.pathname === `/api/building/${BUILDING_ID}/photos/tourapi`) {
      return json(route, { ok: true, streetview_available: false });
    }
    if (url.pathname === "/api/auth/me") return json(route, { logged_in: false });
    if (url.pathname === "/api/regions") return json(route, {});
    if (url.pathname === "/api/years") return json(route, { years: [2026] });
    if (url.pathname === "/api/buildings-geo") return json(route, { items: [], total: 0 });
    if (url.pathname === "/api/building-count") return json(route, { count: 1, tx_count: 0, by_type: {} });
    return json(route, { ok: true, items: [], total: 0 });
  });

  async function openScenario(nextScenario) {
    scenario = nextScenario;
    await page.evaluate(() => localStorage.clear());
    await page.evaluate((id) => openBuildingDetail(id), BUILDING_ID);
    await page.locator("#photoCounter").waitFor({ state: "visible" });
    await page.waitForTimeout(150);
  }

  try {
    const response = await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    expect(response && response.ok(), "홈 화면을 열지 못했습니다.");
    await page.waitForFunction(() => typeof window.openBuildingDetail === "function");
    await page.evaluate(() => {
      localStorage.setItem("hs_welcome_seen_date", new Date().toISOString().slice(0, 10));
      const welcome = document.getElementById("welcomeOverlay");
      if (welcome) welcome.style.display = "none";
    });

    await openScenario("empty");
    expect(await page.locator(".bld-photo-slide").count() === 1, "추가 이미지 0건 뒤 대표사진이 사라졌습니다.");
    expect(await page.locator("#photoCounter").textContent() === "1 / 1", "추가 이미지 0건 뒤 1 / 1 카운터가 유지되지 않았습니다.");
    expect(await page.locator(".bld-photo-slide img").getAttribute("src") === REPRESENTATIVE, "추가 이미지 0건 뒤 대표사진 URL이 바뀌었습니다.");

    await openScenario("success");
    expect(await page.locator(".bld-photo-slide").count() === 2, "기존 사진과 새 사진이 중복 없이 합쳐지지 않았습니다.");
    expect(await page.locator("#photoCounter").textContent() === "1 / 2", "병합된 사진 수가 카운터에 반영되지 않았습니다.");
    await page.locator(".photo-next").click();
    expect(await page.locator("#photoCounter").textContent() === "2 / 2", "다음 사진 이동이 동작하지 않았습니다.");
    expect((await page.locator("#photoTrack").getAttribute("style") || "").includes("-100%"), "다음 사진으로 트랙이 이동하지 않았습니다.");
    await page.locator(".photo-prev").click();
    expect(await page.locator("#photoCounter").textContent() === "1 / 2", "이전 사진 이동이 동작하지 않았습니다.");

    await openScenario("error");
    expect(await page.locator(".bld-photo-slide").count() === 1, "TourAPI 오류 뒤 대표사진이 사라졌습니다.");
    expect(await page.locator("#photoCounter").textContent() === "1 / 1", "TourAPI 오류 뒤 갤러리 카운터가 비었습니다.");
    expect(!(await page.locator("#bldPhotoWrap").evaluate((node) => node.classList.contains("is-empty"))), "TourAPI 오류 뒤 빈 갤러리로 바뀌었습니다.");
    expect(await page.locator(".bld-photo-slide img").evaluate((image) => image.complete && image.naturalWidth > 0), "TourAPI 오류 뒤 깨진 이미지가 표시됐습니다.");

    const relevantErrors = browserErrors.filter((message) =>
      !message.includes("dataLabLodgingRankLayerActive"),
    );
    expect(relevantErrors.length === 0, `브라우저 오류가 발생했습니다: ${relevantErrors.join(" | ")}`);
    console.log("OK  TourAPI 빈 응답·성공·오류 시 실제 Chromium 갤러리 유지와 이동");
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error("FAIL", error);
  process.exitCode = 1;
});