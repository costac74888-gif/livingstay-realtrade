const fs = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");

const vm = require("vm");
const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const html = read("static", "index.html");
const css = read("static", "css", "main.css");
const js = read("static", "js", "main.js");

const requiredHtml = [
  'id="mapToolbar"',
  'id="mapTypeTool"',
  'id="roadviewTool"',
  'id="measureTool"',
  'id="educationTool"',
  'id="convenienceTool"',
  'id="roadviewPanel"',
  'id="roadviewMiniMap"',
  'id="measurePanel"',
];
const missingHtml = requiredHtml.filter((token) => !html.includes(token));
if (missingHtml.length) {
  throw new Error(`지도 툴바 HTML 요소 누락: ${missingHtml.join(", ")}`);
}

const requiredCss = [
  ".map-toolbar",
  ".map-tool-btn.active",
  ".roadview-panel.open",
  ".roadview-minimap",
  ".map-measure-panel",
  ".map-poi-marker",
  "@media (max-width: 980px)",
];
const missingCss = requiredCss.filter((token) => !css.includes(token));
if (missingCss.length) {
  throw new Error(`지도 툴바 CSS 요소 누락: ${missingCss.join(", ")}`);
}
const requiredJs = [
  "MAP_TYPE_STEPS",
  "RoadviewClient",
  "function _ensureRoadviewMiniMap",
  "function _syncRoadviewMiniMap",
  "new kakao.maps.Map",
  "new kakao.maps.Marker",
  "new kakao.maps.Polyline",
  "new kakao.maps.CustomOverlay",
  "/api/map/poi?",
  "_roadviewRequestSequence",
  "sequence !== _roadviewRequestSequence",
  "POI_REFRESH_DEBOUNCE_MS",
  "new AbortController()",
  "signal: controller.signal",
  "function _schedulePoiRefresh",
  "_poiDisplayedCenterKey",
  "centerKey !== _poiCenterKey(kakaoMap.getCenter())",
  'addListener(kakaoMap, "idle"',
  "function _deactivateMapTool",
  "function _activateMapTool",
  "_loadPoi(_activeMapTool)",
  "clearTimeout(_poiRefreshTimer)",
  "function _bindMapToolMapEvents",
  "_initMapToolControls();",
  "_bindMapToolMapEvents();",
];
const missingJs = requiredJs.filter((token) => !js.includes(token));
if (missingJs.length) {
  throw new Error(`지도 툴바 JS 계약 누락: ${missingJs.join(", ")}`);
}

const activateStart = js.indexOf("function _activateMapTool(tool){");
const activateEnd = js.indexOf("\nfunction _initMapToolControls()", activateStart);
const activateBlock = js.slice(activateStart, activateEnd);
const openRoadviewStart = js.indexOf("function _openRoadviewAt(latLng){");
const openRoadviewEnd = js.indexOf("\nfunction _clearPoiResults()", openRoadviewStart);
const openRoadviewBlock = js.slice(openRoadviewStart, openRoadviewEnd);
const ensureRoadviewStart = js.indexOf("function _ensureRoadview(){");
const ensureRoadviewEnd = js.indexOf("\nfunction _openRoadviewAt(latLng)", ensureRoadviewStart);
const ensureRoadviewBlock = js.slice(ensureRoadviewStart, ensureRoadviewEnd);
if (
  activateStart < 0 ||
  activateEnd < 0 ||
  !activateBlock.includes("addOverlayMapTypeId") ||
  !activateBlock.includes("파란색 도로에서 원하는 지점을 클릭하면 로드뷰가 열립니다.") ||
  activateBlock.includes('panel.classList.add("open")')
) {
  throw new Error("로드뷰 버튼 활성화 시 파란 도로 안내만 표시하고 패널을 즉시 열지 않아야 합니다.");
}
if (
  openRoadviewStart < 0 ||
  openRoadviewEnd < 0 ||
  !openRoadviewBlock.includes('panel.classList.add("open")') ||
  openRoadviewBlock.indexOf('panel.classList.add("open")') >
    openRoadviewBlock.indexOf("if (!_ensureRoadview()) return;")
) {
  throw new Error("로드뷰 지점 클릭 시 패널을 먼저 열고 초기화하는 흐름이 없습니다.");
}
if (
  ensureRoadviewStart < 0 ||
  ensureRoadviewEnd < 0 ||
  !ensureRoadviewBlock.includes("_syncRoadviewMiniMap") ||
  !ensureRoadviewBlock.includes("_roadview.relayout()") ||
  ensureRoadviewBlock.includes("RoadviewMapControl")
) {
  throw new Error("로드뷰 미니맵 동기화 또는 relayout 처리가 없습니다.");
}
if (!openRoadviewBlock.includes("_syncRoadviewMiniMap(latLng)")) {
  throw new Error("로드뷰 위치를 미니맵에 동기화하지 않습니다.");
}

const syntax = spawnSync(process.execPath, ["--check", path.join(root, "static", "js", "main.js")], {
  encoding: "utf8",
});

function poiResponse(lat, lng, name) {
  return {
    ok: true,
    json: async () => ({
      ok: true,
      items: [{
        name,
        category: "학교",
        lat,
        lng,
        address: "테스트 주소",
      }],
    }),
  };
}

(async () => {
  await checkPoiMovementBehavior();
  await checkRoadviewMiniMapBehavior();
  console.log("OK  지도 툴바 마크업·모바일 CSS·SDK·POI 이동 갱신 계약");
})().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});

function waitFor(predicate, label) {
  const deadline = Date.now() + 300;
  return new Promise((resolve, reject) => {
    const check = () => {
      if (predicate()) return resolve();
      if (Date.now() >= deadline) return reject(new Error(`시간 안에 완료되지 않음: ${label}`));
      setTimeout(check, 2);
    };
    check();
  });
}

async function checkRoadviewMiniMapBehavior() {
  const blockStart = js.indexOf("const MAP_TYPE_STEPS =");
  const blockEnd = js.indexOf("// 새 레이어가 준비될 때까지 기존 CustomOverlay");
  if (blockStart < 0 || blockEnd < 0) {
    throw new Error("로드뷰 미니맵 테스트용 소스 범위를 찾지 못함");
  }
  const toolCode = js.slice(blockStart, blockEnd);
  const elements = new Map();
  const miniMaps = [];
  class LatLng {
    constructor(lat, lng) {
      this.lat = Number(lat);
      this.lng = Number(lng);
    }
  }
  class MiniMap {
    constructor(element, options) {
      this.element = element;
      this.center = options.center;
      this.relayoutCalls = 0;
      miniMaps.push(this);
    }
    setCenter(position) { this.center = position; }
    relayout() { this.relayoutCalls++; }
  }
  class Marker {
    constructor(options) { this.position = options.position; }
    setPosition(position) { this.position = position; }
  }
  const context = {
    clearTimeout,
    setTimeout,
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {});
        return elements.get(id);
      },
    },
    window: {},
    kakao: {
      maps: {
        Map: MiniMap,
        Marker,
      },
    },
  };
  context.window.kakao = context.kakao;
  vm.createContext(context);
  vm.runInContext(`
    let kakaoMap = { getCenter() { return { lat: 37.5, lng: 127.0 }; } };
    ${toolCode}
    globalThis.__miniMapTest = {
      sync: _syncRoadviewMiniMap,
      marker() { return _roadviewMiniMarker; },
    };
  `, context);

  const first = new LatLng(37.51, 127.01);
  context.__miniMapTest.sync(first);
  if (miniMaps.length !== 1 || miniMaps[0].center !== first) {
    throw new Error("로드뷰 미니맵을 생성하고 첫 위치를 중심으로 설정하지 않음");
  }
  if (context.__miniMapTest.marker().position !== first) {
    throw new Error("로드뷰 미니맵의 현재 위치 마커를 생성하지 않음");
  }
  const second = new LatLng(37.52, 127.02);
  context.__miniMapTest.sync(second);
  if (miniMaps[0].center !== second || context.__miniMapTest.marker().position !== second) {
    throw new Error("로드뷰 위치 변경을 미니맵과 마커에 반영하지 않음");
  }
  await waitFor(() => miniMaps[0].relayoutCalls > 0, "로드뷰 미니맵 relayout");
}

async function checkPoiMovementBehavior() {
  const blockStart = js.indexOf("const MAP_TYPE_STEPS =");
  const blockEnd = js.indexOf("// 새 레이어가 준비될 때까지 기존 CustomOverlay");
  if (blockStart < 0 || blockEnd < 0) {
    throw new Error("POI 도구 동작 테스트용 소스 범위를 찾지 못함");
  }
  const toolCode = js.slice(blockStart, blockEnd)
    .replace("const POI_REFRESH_DEBOUNCE_MS = 180;", "const POI_REFRESH_DEBOUNCE_MS = 5;");
  const visibleOverlays = [];
  const elements = new Map();
  const element = () => ({
    classList: { add() {}, remove() {}, toggle() {} },
    getAttribute() { return ""; },
    setAttribute() {},
    addEventListener() {},
    hidden: false,
    textContent: "",
  });
  const requests = [];
  class LatLng {
    constructor(lat, lng) {
      this.lat = Number(lat);
      this.lng = Number(lng);
    }
    getLat() { return this.lat; }
    getLng() { return this.lng; }
  }
  class CustomOverlay {
    constructor(options) {
      this.position = options.position;
    }
    setMap(map) {
      const index = visibleOverlays.indexOf(this);
      if (map && index < 0) visibleOverlays.push(this);
      if (!map && index >= 0) visibleOverlays.splice(index, 1);
    }
  }
  const context = {
    AbortController,
    URL,
    URLSearchParams,
    clearTimeout,
    console,
    setTimeout,
    visibleOverlays,
    document: {
      createElement: element,
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, element());
        return elements.get(id);
      },
    },
    window: { open() {} },
    showFallbackToast() {},
    kakao: {
      maps: {
        CustomOverlay,
        LatLng,
        Polyline: class {},
        event: { addListener() {} },
      },
    },
    fetch(url, options) {
      return new Promise((resolve, reject) => {
        requests.push({ url, options, resolve, reject });
      });
    },
  };
  vm.createContext(context);
  vm.runInContext(`
    let kakaoMap = null;
    ${toolCode}
    globalThis.__poiTest = {
      activate: _activateMapTool,
      schedule: _schedulePoiRefresh,
      setMap(map) { kakaoMap = map; },
      visible() { return ${"visibleOverlays"}.slice(); },
    };
  `, context);

  const center = (lat, lng) => new LatLng(lat, lng);
  const map = {
    center: center(37.5, 127.0),
    getCenter() { return this.center; },
  };
  context.__poiTest.setMap(map);
  context.__poiTest.activate("education");
  await waitFor(() => requests.length === 1, "최초 POI 요청");
  requests[0].resolve(poiResponse(37.5, 127.0, "A 학교"));
  await waitFor(() => visibleOverlays.length === 1, "최초 A 마커 표시");

  // A → B → A: B 타이머는 취소되고, 화면에서 지워진 A 결과를 다시 불러와야 한다.
  map.center = center(37.6, 127.1);
  context.__poiTest.schedule();
  if (visibleOverlays.length !== 0) {
    throw new Error("새 지도 중심을 기다리는 동안 이전 POI 마커가 지워지지 않음");
  }
  map.center = center(37.5, 127.0);
  context.__poiTest.schedule();
  await waitFor(() => requests.length === 2, "A 복귀 후 POI 재요청");
  const returnUrl = new URL(requests[1].url, "https://test.invalid");
  if (returnUrl.searchParams.get("lat") !== "37.5" || returnUrl.searchParams.get("lng") !== "127") {
    throw new Error("A로 복귀한 뒤 최신 지도 중심을 요청하지 않음");
  }
  requests[1].resolve(poiResponse(37.5, 127.0, "A 복귀 학교"));
  await waitFor(() => visibleOverlays.length === 1, "A 복귀 마커 표시");

  // B 응답이 늦게 와도 취소 뒤 A 결과를 덮어쓰면 안 된다.
  map.center = center(37.6, 127.1);
  context.__poiTest.schedule();
  await waitFor(() => requests.length === 3, "B 이동 후 POI 요청");
  map.center = center(37.5, 127.0);
  context.__poiTest.schedule();
  if (!requests[2].options.signal.aborted) {
    throw new Error("새 지도 중심에서 이전 POI 요청을 취소하지 않음");
  }
  requests[2].resolve(poiResponse(37.6, 127.1, "늦은 B 학교"));
  await waitFor(() => requests.length === 4, "B 취소 후 A 재요청");
  if (visibleOverlays.length !== 0) {
    throw new Error("취소된 B 응답이 최신 A 요청보다 먼저 마커를 표시함");
  }
  requests[3].resolve(poiResponse(37.5, 127.0, "최신 A 학교"));
  await waitFor(() => visibleOverlays.length === 1, "최신 A 마커 표시");
  if (visibleOverlays[0].position.getLat() !== 37.5 || visibleOverlays[0].position.getLng() !== 127) {
    throw new Error("늦은 응답이 최신 지도 중심의 POI 마커를 덮어씀");
  }
}
