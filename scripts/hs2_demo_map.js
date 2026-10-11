/* Owned schematic SDK, not Kakao tiles. No outbound API, geocoding or real GPS. */
(() => {
  "use strict";
  const MIN_LAT = 37.537, MAX_LAT = 37.551, MIN_LNG = 127.037, MAX_LNG = 127.067;
  class LatLng {
    constructor(lat, lng) { this.lat = lat; this.lng = lng; }
    getLat() { return this.lat; }
    getLng() { return this.lng; }
  }
  class DemoMap {
    constructor(element) {
      this.el = element;
      element.dataset.fixtureMap = "seongsu-schematic";
      element.style.position = "relative";
      element.style.background = "#e8f0fa";
      // Do not stretch the map to the height of fourteen result cards.
      // Fictional positions must remain visible next to the first cards.
      element.style.height = "540px";
      element.style.minHeight = "360px";
      element.style.maxHeight = "640px";
      const surface = document.createElement("div");
      surface.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden";
      surface.innerHTML = `<svg viewBox="0 0 800 600" preserveAspectRatio="none"
        style="width:100%;height:100%" aria-hidden="true">
        <rect width="800" height="600" fill="#e9f1fa"/>
        <g fill="#dce6f1" stroke="#cbd9e9" stroke-width="2">
        <rect x="20" y="25" width="205" height="200" rx="10"/>
        <rect x="260" y="25" width="230" height="200" rx="10"/>
        <rect x="530" y="25" width="245" height="200" rx="10"/>
        <rect x="25" y="275" width="200" height="175" rx="10"/>
        <rect x="260" y="275" width="230" height="175" rx="10"/>
        <rect x="530" y="275" width="245" height="175" rx="10"/>
        </g><path d="M0 250H800 M245 0V600 M510 0V600" stroke="white" stroke-width="22"/>
        <path d="M0 525Q230 480 800 560" stroke="#b7d1eb" stroke-width="70" fill="none"/>
        <g fill="#5f7d9e" font-family="sans-serif" font-size="23">
        <text x="65" y="80">성수동1가</text><text x="560" y="80">성수동2가</text>
        <text x="50" y="430">서울숲 방향</text><text x="290" y="240">성수동 가상 배치도</text>
        </g></svg>`;
      element.prepend(surface);
      const caption = document.createElement("span");
      caption.textContent = "가상 성수동 배치도 · 실제 지도/실재 매물 위치 아님";
      caption.style.cssText = "position:absolute;bottom:8px;left:8px;right:8px;padding:6px;background:#fff;z-index:0;color:#42658c;font:11px/1.4 sans-serif";
      element.append(caption);
    }
    getBounds() {
      return { getSouthWest: () => new LatLng(MIN_LAT, MIN_LNG),
        getNorthEast: () => new LatLng(MAX_LAT, MAX_LNG) };
    }
    relayout() {}
    setCenter() {}
    setLevel() {}
  }
  class Overlay {
    constructor(options) {
      this.content = options.content;
      this.position = options.position;
      if (typeof this.content === "string") {
        const wrapper = document.createElement("div");
        wrapper.innerHTML = this.content;
        this.content = wrapper;
      }
      if (options.map) this.setMap(options.map);
    }
    setMap(map) {
      this.content.remove();
      if (!map) return;
      const x = 100 * (this.position.getLng() - MIN_LNG) / (MAX_LNG - MIN_LNG);
      const y = 100 * (MAX_LAT - this.position.getLat()) / (MAX_LAT - MIN_LAT);
      this.content.style.position = "absolute";
      this.content.style.left = `${x}%`;
      this.content.style.top = `${y}%`;
      map.el.append(this.content);
    }
  }
  window.kakao = { maps: {
    load: callback => callback(), LatLng, Map: DemoMap, CustomOverlay: Overlay,
    Circle: class { setMap() {} },
    event: { addListener(map, event, callback) { map.el[`fixture_${event}`] = callback; },
      removeListener() {} }
  }};
})();
