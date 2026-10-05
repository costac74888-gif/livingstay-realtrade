/* Runs production render functions with SDK/HTTP doubles; no network or DB writes. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/js/main.js", "utf8");
function section(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `Missing full signature: ${start}`);
  return source.slice(first, last);
}
class Element {
  constructor() { this.dataset = {}; this.style = {}; this.innerHTML = ""; this.value = ""; }
  addEventListener() {}
  setAttribute() {}
  querySelector() { return new Element(); }
}
class Overlay {
  constructor(options) { Object.assign(this, options); }
  setMap(map) { this.map = map; }
}
function fixture() {
  const empty = new Element();
  const selector = new Element();
  const calls = [];
  const context = {
    console, URLSearchParams, AbortController,
    document: {
      createElement: () => new Element(),
      getElementById: id => id === "mapEmpty" ? empty : selector,
      querySelectorAll: () => [],
    },
    localStorage: { setItem() {} },
    kakao: { maps: { LatLng: class { constructor(lat, lng) { this.lat = lat; this.lng = lng; } }, CustomOverlay: Overlay } },
    kakaoMap: {
      getLevel: () => 5, setCenter() {}, setLevel() {},
      getBounds: () => ({
        getSouthWest: () => ({ getLat: () => 33, getLng: () => 124 }),
        getNorthEast: () => ({ getLat: () => 39, getLng: () => 132 }),
      }),
    },
    _auctionLayerEnabled: true, _currentMapMode: "sido",
    _mapRenderGen: 0, _auctionMapRequest: 0, _mapFetchController: null,
    _auctionMapOverlays: [], _clusterOverlays: [], _pendingFadeOutOverlays: [],
    _lastMapFilters: {}, state: { lodging_type: "호텔" },
    LODGING_COLORS: { "일반": "#red", "미분류": "#gray" },
    SIDO_POSITION_OVERRIDE: {}, SIDO_ANCHOR_LEFT: new Set(), escapeHtml: String,
    isMobileMapViewport: () => false,
    _setLegendActive() {}, clearDataLabLodgingRankMap() {}, clearDataLabTourismMap() {},
    updateMapForZoom() {},
    _beginMapLayerSwap() {
      const old = context._clusterOverlays;
      context._clusterOverlays = [];
      return old;
    },
    _finishMapLayerSwap(old) { old.forEach(overlay => overlay.setMap(null)); },
    showMapEmptyBanner(message) { empty.innerHTML = message || "empty"; empty.style.display = "flex"; },
    fetch: async url => {
      calls.push(url);
      return { ok: true, json: async () => ({
        ok: true, items: [
          { name: "공매지역", lat: 37, lng: 127, auction_count: 3, total: 95, by_type: { "일반": 95 }, visitor_count: 100000 },
          { name: "숙박만지역", lat: 36, lng: 128, auction_count: 0, total: 77, by_type: { "일반": 77 }, visitor_count: 200000 },
        ],
      }) };
    },
  };
  vm.createContext(context);
  vm.runInContext([
    section("function setAuctionMapLayer(enabled, {refresh=true} = {}){", '\ndocument.querySelectorAll(".map-legend [data-auction-layer]").forEach'),
    section("async function loadMapMarkers(filters = {}, opts = {}){", "\nasync function loadAuctionMapOverlays(){"),
    section("async function loadAuctionMapOverlays(){", "\n// 현재 지도 줌 레벨로 클러스터 모드를 결정"),
    section("async function loadClusterOverlays(clusterLevel, filters = {}){", "\n// 현재 줌 레벨에 따라 클러스터 배지"),
  ].join("\n"), context);
  return { context, calls, empty, selector };
}
async function main() {
  for (const level of ["sido", "sgg", "umd"]) {
    const { context: c, calls } = fixture();
    c._currentMapMode = level;
    await c.loadClusterOverlays(level, { lodging_type: "호텔" });
    assert.equal(c._clusterOverlays.length, 1);
    const html = c._clusterOverlays[0].content.innerHTML;
    assert.ok(html.includes("공매 3"));
    assert.ok(html.includes("background:#3d5948"), "Auction cluster uses the reference green");
    assert.ok(!html.includes("숙박만지역") && !html.includes("#red") && !html.includes("cluster-visitor-count"));
    assert.ok(!calls[0].includes("lodging_type"));
    c._auctionLayerEnabled = false;
    await c.loadClusterOverlays(level, { lodging_type: "호텔" });
    assert.equal(c._clusterOverlays.length, 2);
    assert.ok(c._clusterOverlays[0].content.innerHTML.includes("#red"));
    assert.ok(!c._clusterOverlays[0].content.innerHTML.includes("공매 3"));
  }
  const { context: c, calls, empty, selector } = fixture();
  c._currentMapMode = "markers";
  await c.loadMapMarkers();
  assert.equal(calls.length, 1);
  assert.ok(calls[0].startsWith("/api/auctions/map?"));
  assert.equal(c._auctionMapOverlays.length, 2);
  c.fetch=async()=>({ok:true,json:async()=>({ok:true,items:[
    {id:1,lat:37,lng:127,master_building_id:9,status:"bidding",lodging_category:"생활숙박",area_m2:66.116,min_bid_price:180000000},
    {id:2,lat:37,lng:127,master_building_id:10,status:"scheduled",lodging_category:"생활숙박",area_m2:99.174,min_bid_price:320000000},
  ]})});
  c.markerColor=()=>"#123456";
  await c.loadAuctionMapOverlays();
  assert.equal(c._auctionMapOverlays.length,2,"One grouped box plus independently clickable building point");
  const groupedHtml=c._auctionMapOverlays[0].content.innerHTML;
  assert.ok(groupedHtml.includes("2건"));
  assert.ok(groupedHtml.includes("생활숙박") && groupedHtml.includes("20평") && groupedHtml.includes("1.8억"),
    "Grouped marker shows the same representative item's actual use, area and current minimum price");
  assert.ok(!groupedHtml.includes("물건 선택") && !groupedHtml.includes("3.2억"));
  assert.ok(c._auctionMapOverlays[0].content.title.replace(/[,\s]/g,"").includes("180000000원"),
    "Tooltip preserves the exact current minimum price");
  assert.ok(!c._auctionMapOverlays[0].content.innerHTML.includes("/auctions/"));
  assert.ok(c._auctionMapOverlays[0].content.innerHTML.includes("진행"));
  for (const value of [null,"",0,-1,"invalid"]) {
    c.fetch=async()=>({ok:true,json:async()=>({ok:true,items:[
      {id:3,lat:37,lng:127,lodging_category:"호텔",area_m2:value,min_bid_price:value,status:"scheduled"}
    ]})});
    await c.loadAuctionMapOverlays();
    const html=c._auctionMapOverlays[0].content.innerHTML;
    assert.ok(html.includes("미확인") && !html.includes("0평") && !html.includes(">0만"),
      "Missing/invalid auction values must not turn into zero area or price");
  }
  c.setAuctionMapLayer(true, { refresh: false });
  assert.equal(c.state.lodging_type, "");
  assert.equal(selector.value, "");
  assert.equal(c._auctionMapOverlays.length, 0);
  let resolve;
  c.fetch = () => new Promise(done => { resolve = done; });
  const late = c.loadAuctionMapOverlays();
  c.setAuctionMapLayer(false, { refresh: false });
  resolve({ ok: true, json: async () => ({ ok: true, items: [{ lat: 37, lng: 127 }] }) });
  await late;
  assert.equal(c._auctionMapOverlays.length, 0, "Disabled layer must reject a late response");
  c.state.lodging_type = "";
  c._lastMapFilters = {};
  const buildingPoint = new Overlay({ content: new Element() });
  buildingPoint.setMap(c.kakaoMap);
  c._clusterOverlays = [buildingPoint];
  c.fetch = async () => ({ ok: true, json: async () => ({ ok: true, items: [
    {id:4,lat:37,lng:127,master_building_id:9,lodging_category:"생활숙박",area_m2:66,min_bid_price:180000000,status:"bidding"},
  ] }) });
  await c.loadAuctionMapOverlays();
  assert.equal(c._auctionMapOverlays.length, 1, "All view displays the auction box without a duplicate building point");
  assert.equal(c._auctionMapOverlays[0].map, c.kakaoMap);
  assert.equal(buildingPoint.map, c.kakaoMap, "All view retains the ordinary building layer");
  c.state.lodging_type = "호텔";
  c.fetch = async () => { throw new Error("A specific lodging filter must not fetch auction boxes"); };
  await c.loadAuctionMapOverlays();
  assert.equal(c._auctionMapOverlays.length, 0);
  c.state.lodging_type = "";
  c._currentMapMode = "sgg";
  await c.loadAuctionMapOverlays();
  assert.equal(c._auctionMapOverlays.length, 0, "Zoomed-out view keeps regional clusters");
  c._currentMapMode = "markers";
  empty.innerHTML = "건물 조회 안내";
  empty.style.display = "none";
  c.fetch = async () => ({ ok: true, json: async () => ({ ok: true, items: [] }) });
  await c.loadAuctionMapOverlays();
  assert.equal(empty.innerHTML, "건물 조회 안내", "Empty auction results must not replace the all-view banner");
  assert.equal(empty.style.display, "none");
  c.fetch = async () => ({ ok: false, json: async () => ({ ok: false }) });
  await c.loadAuctionMapOverlays();
  assert.equal(empty.innerHTML, "건물 조회 안내", "An auction error must not replace the all-view building feedback");
  assert.equal(empty.style.display, "none");
  c.fetch = () => new Promise(done => { resolve = done; });
  const lateAll = c.loadAuctionMapOverlays();
  c.setAuctionMapLayer(true, { refresh: false });
  resolve({ ok: true, json: async () => ({ ok: true, items: [{ lat: 37, lng: 127 }] }) });
  await lateAll;
  assert.equal(c._auctionMapOverlays.length, 0, "Switching to auction-only rejects a late all-view response");
  c._auctionLayerEnabled = true;
  c.fetch = async () => ({ ok: true, json: async () => ({ ok: true, items: [] }) });
  await c.loadAuctionMapOverlays();
  assert.ok(empty.innerHTML.includes("공매 물건이 없습니다"));
  c.fetch = async () => ({ ok: false, json: async () => ({ ok: false }) });
  await c.loadAuctionMapOverlays();
  assert.ok(empty.innerHTML.includes("불러오지 못했습니다"));
  console.log("PASS all-view auction boxes, exclusive filters, zoom transitions, late-response fencing, empty/error isolation");
}
main().catch(error => { console.error(error); process.exitCode = 1; });