const fs = require("fs");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const BUILDING_ID = 101;
const BUILDING_NAME = "모바일 지도 테스트 스테이";
const BUILDING_ADDRESS = "서울특별시 중구 세종대로 101";

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
      const path = execFileSync("sh", ["-c", `command -v ${command}`], {
        encoding: "utf8",
      }).trim();
      if (path) return path;
    } catch (_) {
      // 다음 실행 파일 후보를 확인한다.
    }
  }
  throw new Error(
    "Chromium 실행 파일을 찾지 못했습니다. Playwright Chromium 또는 시스템 chromium을 설치하세요.",
  );
}

function installKakaoMapStub() {
  class LatLng {
    constructor(lat, lng) {
      this.lat = Number(lat);
      this.lng = Number(lng);
    }
    getLat() { return this.lat; }
    getLng() { return this.lng; }
  }

  class Map {
    constructor(container, options) {
      this.container = container;
      this.center = options.center;
      this.level = options.level;
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
    constructor(options) {
      this.content = options.content;
      this.position = options.position;
      this.map = null;
    }
    setMap(map) {
      if (this.content instanceof HTMLElement && this.content.parentElement) {
        this.content.remove();
      }
      this.map = map;
      if (map && this.content instanceof HTMLElement) {
        this.content.style.position = "absolute";
        this.content.style.left = "50%";
        this.content.style.top = "50%";
        map.container.appendChild(this.content);
      }
    }
    setZIndex() {}
  }

  class Marker {
    constructor(options = {}) {
      this.map = options.map || null;
    }
    setMap(map) { this.map = map; }
  }

  class InfoWindow {
    open() {}
    close() {}
  }

  window.kakao = {
    maps: {
      load: (callback) => callback(),
      Map,
      LatLng,
      CustomOverlay,
      Marker,
      MarkerImage: class {},
      InfoWindow,
      ZoomControl: class {},
      Size: class {},
      Point: class {},
      LatLngBounds: class {
        extend() {}
      },
      Polyline: class {
        setMap() {}
      },
      ControlPosition: { BOTTOMRIGHT: "BOTTOMRIGHT" },
      MapTypeId: {
        ROADMAP: "ROADMAP",
        SKYVIEW: "SKYVIEW",
        HYBRID: "HYBRID",
        ROADVIEW: "ROADVIEW",
      },
      event: {
        addListener() {},
        removeListener() {},
      },
    },
  };
}

function buildingFixture() {
  return {
    id: BUILDING_ID,
    building_id: BUILDING_ID,
    building_name: BUILDING_NAME,
    display_building_name: BUILDING_NAME,
    building_status: "완공",
    lodging_type: "생활",
    lodging_subtype: "",
    road_address: BUILDING_ADDRESS,
    jibun_address: "서울특별시 중구 태평로1가 31",
    address: BUILDING_ADDRESS,
    lat: 37.5665,
    lng: 126.978,
    units: 120,
    detail_fetched_at: "2026-08-30T00:00:00",
    direct_listings: [],
    partner_agents: [],
    lodging_room_total: 0,
  };
}

async function json(route, body) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromiumExecutable(),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  const openSearchPanel = async () => {
    const searchbar = page.locator(".map-searchbar");
    if (await searchbar.evaluate((element) => element.classList.contains("collapsed"))) {
      await page.locator("#btnToggleSearch").click();
    }
    await searchbar.waitFor({ state: "visible" });
  };

  await page.addInitScript(installKakaoMapStub);
  await page.route("**/dapi.kakao.com/**", (route) => route.fulfill({
    status: 200,
    contentType: "application/javascript",
    body: "/* Kakao Maps is provided by the browser test init script. */",
  }));
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("https://unpkg.com/**", (route) => route.fulfill({
    status: 200,
    contentType: "application/javascript",
    body: "window.lucide={createIcons:function(){}};",
  }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/building/${BUILDING_ID}`) {
      return json(route, buildingFixture());
    }
    if (url.pathname === `/api/building/${BUILDING_ID}/area-types`) {
      return json(route, { items: [] });
    }
    if (url.pathname === "/api/favorites") {
      return json(route, {
        total: 1,
        items: [{
          master_building_id: BUILDING_ID,
          building_name: BUILDING_NAME,
          address: BUILDING_ADDRESS,
        }],
      });
    }
    if (url.pathname === "/api/regions") return json(route, {});
    if (url.pathname === "/api/years") return json(route, { years: [2026] });
    if (url.pathname === "/api/auth/me") return json(route, { logged_in: false });
    if (url.pathname === "/api/health") return json(route, {});
    if (url.pathname === "/api/building-count") {
      return json(route, { count: 1, tx_count: 0, by_type: {} });
    }
    return json(route, { ok: true, items: [], total: 0 });
  });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    expect(response && response.ok(), `홈 화면을 열지 못했습니다: ${BASE_URL}`);
    await page.waitForFunction(() =>
      typeof window.openBuildingDetail === "function" && Boolean(kakaoMap),
    );
    await page.evaluate(({ buildingName, buildingAddress }) => {
      localStorage.setItem("hs_welcome_seen_date", new Date().toISOString().slice(0, 10));
      document.getElementById("welcomeOverlay").style.display = "none";
      serverFavKeys = new Set([`${buildingName}|${buildingAddress}`]);
      renderFavChips();
    }, { buildingName: BUILDING_NAME, buildingAddress: BUILDING_ADDRESS });

    await openSearchPanel();
    expect(
      !(await page.locator(".map-searchbar").evaluate((element) => element.classList.contains("collapsed"))),
      "관심단지 칩을 누르기 위해 검색 패널을 열지 못했습니다.",
    );

    const favoriteChip = page.locator("#favChips .fav-chip").filter({ hasText: BUILDING_NAME });
    await favoriteChip.click();
    await page.waitForURL(`**/building/${BUILDING_ID}`);
    await page.locator("#bMapBtn").waitFor({ state: "visible" });

    expect(
      !(await page.locator(".map-searchbar").evaluate((element) => element.classList.contains("collapsed"))),
      "지도위치 클릭 전 검색 패널을 열지 못했습니다.",
    );

    await page.locator("#bMapBtn").click();
    await page.waitForURL((url) => url.pathname === "/");
    expect(
      !(await page.locator(".side-panel").evaluate((element) => element.classList.contains("open"))),
      "지도위치 클릭 후 상세 패널이 닫히지 않았습니다.",
    );
    expect(
      await page.locator(".map-searchbar").evaluate((element) => element.classList.contains("collapsed")),
      "지도위치 클릭 후 검색 패널이 닫히지 않았습니다.",
    );
    await page.locator(`.map-location-target-pin[data-map-building-id="${BUILDING_ID}"]`)
      .waitFor({ state: "visible" });

    await openSearchPanel();
    const recentChip = page.locator("#recentChips .recent-search-chip").filter({ hasText: BUILDING_NAME });
    await recentChip.click();
    await page.waitForURL(`**/building/${BUILDING_ID}`);
    await page.locator("#bHeaderCard").getByText(BUILDING_NAME).waitFor({ state: "visible" });

    await page.locator("#btnBackToList").click();
    await page.waitForURL((url) => url.pathname === "/");
    await page.evaluate(() => renderFavChips());
    await openSearchPanel();
    await page.locator("#favChips .fav-chip").filter({ hasText: BUILDING_NAME }).click();
    await page.waitForURL(`**/building/${BUILDING_ID}`);
    await page.locator("#bHeaderCard").getByText(BUILDING_NAME).waitFor({ state: "visible" });

    const relevantErrors = browserErrors.filter((message) =>
      !message.includes("Failed to fetch") && !message.includes("ERR_FAILED"),
    );
    expect(relevantErrors.length === 0, `브라우저 오류가 발생했습니다: ${relevantErrors.join(" | ")}`);
    console.log("OK  실제 모바일 Chromium 지도위치·관심단지·최근조회 흐름");
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error("FAIL", error);
  process.exitCode = 1;
});