/* Synthetic geometry/DOM only. No tiles, geocoder, provider key or network. */
(() => {
  const listeners = new WeakMap();
  const event = {
    addListener(target, name, callback) {
      const events = listeners.get(target) || {};
      (events[name] ||= []).push(callback); listeners.set(target, events);
    },
    removeListener(target, name, callback) {
      const events = listeners.get(target) || {};
      events[name] = (events[name] || []).filter(fn => fn !== callback);
    },
    trigger(target, name) {
      for (const callback of (listeners.get(target)?.[name] || [])) callback();
    },
  };
  class LatLng {
    constructor(lat, lng) { this.lat = Number(lat); this.lng = Number(lng); }
    getLat() { return this.lat; } getLng() { return this.lng; }
  }
  class LatLngBounds {
    constructor(sw = new LatLng(33, 124), ne = new LatLng(39, 132)) { this.sw = sw; this.ne = ne; }
    extend() {}
    getSouthWest() { return this.sw; } getNorthEast() { return this.ne; }
    contain() { return true; }
  }
  class Map {
    constructor(container, options) {
      this.container = container; this.center = options.center; this.level = options.level;
      setTimeout(() => event.trigger(this, "tilesloaded"), 0);
    }
    addControl() {} addOverlayMapTypeId() {} removeOverlayMapTypeId() {}
    relayout() {} setMapTypeId() {} getMapTypeId() { return 1; }
    getCenter() { return this.center; } getLevel() { return this.level; }
    getBounds() { return new LatLngBounds(); }
    setCenter(center) { this.center = center; event.trigger(this, "idle"); }
    panTo(center) { this.setCenter(center); }
    setLevel(level) { this.level = level; event.trigger(this, "zoom_changed"); event.trigger(this, "idle"); }
    setBounds() { event.trigger(this, "idle"); }
  }
  class CustomOverlay {
    constructor(options = {}) {
      this.position = options.position; this.content = options.content; this.setMap(options.map || null);
    }
    setMap(map) {
      this.element?.remove(); this.map = map;
      if (map && this.content) {
        const node = document.createElement("div");
        node.className = "offline-map-overlay";
        node.style.cssText = "position:absolute;left:50%;top:50%";
        if (typeof this.content === "string") node.innerHTML = this.content;
        else node.append(this.content);
        map.container.append(node); this.element = node;
      }
    }
    getMap() { return this.map; } getContent() { return this.content; }
    setContent(content) { this.content = content; this.setMap(this.map); }
    setPosition(position) { this.position = position; } getPosition() { return this.position; }
    setZIndex() {}
  }
  class Marker {
    constructor(options = {}) { this.map = options.map; this.position = options.position; }
    setMap(map) { this.map = map; } setPosition(position) { this.position = position; }
    getPosition() { return this.position; } setImage() {} setZIndex() {}
  }
  window.kakao = {maps: {
    load: callback => setTimeout(callback, 0), Map, LatLng, LatLngBounds, CustomOverlay, Marker, event,
    InfoWindow: class { open() {} close() {} }, MarkerImage: class {}, ZoomControl: class {},
    Size: class {}, Point: class {}, Polyline: class { setMap() {} },
    ControlPosition: {BOTTOMRIGHT: "BOTTOMRIGHT"},
    MapTypeId: {ROADMAP: 1, SKYVIEW: 2, HYBRID: 3, ROADVIEW: 4},
  }};
  window.__offlineKakaoSDK = true;
})();
