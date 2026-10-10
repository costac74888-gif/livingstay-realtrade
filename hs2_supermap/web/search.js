(() => {
  "use strict";

  const form = document.getElementById("searchForm");
  const list = document.getElementById("listingList");
  const status = document.getElementById("statusMessage");
  const statusCopy = status.querySelector("span:last-child");
  const resultCount = document.getElementById("resultCount");
  const errorPanel = document.getElementById("errorPanel");
  const errorTitle = document.getElementById("errorTitle");
  const errorCopy = document.getElementById("errorCopy");
  const retryButton = document.getElementById("retryButton");
  const emptyPanel = document.getElementById("emptyPanel");
  const selectedSummary = document.getElementById("selectedSummary");
  const searchButton = form.querySelector(".search-button");
  const checkIn = document.getElementById("check_in");
  const checkOut = document.getElementById("check_out");
  const minTotal = document.getElementById("min_total");
  const maxTotal = document.getElementById("max_total");
  const priceHint = document.getElementById("priceHint");
  const mapCanvas = document.getElementById("mapCanvas");
  const mapPlaceholder = document.getElementById("mapPlaceholder");
  const mapMessage = document.getElementById("mapMessage");
  const mapDetail = document.getElementById("mapDetail");
  const mapStatus = document.getElementById("mapStatus");
  const mapFooter = document.getElementById("mapFooter");
  const layerInputs = [...document.querySelectorAll('input[name="layer"]')];
  const layerNames = { stay: "숙박", sale: "매매", business: "영업권 양도", auction: "공매" };
  const layerGlyphs = { stay: "체", sale: "매", business: "영", auction: "공" };
  let lastCriteria = {};
  let currentItems = [];
  let mapInstance = null;
  let mapSdkUrl = "";
  let mapScript = null;
  let markerOverlays = [];
  let privacyCircles = [];
  let boundsTimer = null;
  let skipNextIdle = false;
  let restoringHistory = false;
  let lastBoundsString = "";
  let controller = null;
  let resultPayload = null;
  let markerMenuSequence = 0;

  function setStatus(text, state) {
    statusCopy.textContent = text;
    status.dataset.state = state || "idle";
  }

  function isValidDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  }

  function datesAreUsable() {
    return isValidDate(checkIn.value) && isValidDate(checkOut.value) && checkOut.value > checkIn.value;
  }

  function updatePriceControls() {
    const enabled = datesAreUsable();
    minTotal.disabled = !enabled;
    maxTotal.disabled = !enabled;
    priceHint.textContent = enabled ? "선택한 기간의 총액만 비교합니다." : "입실일과 퇴실일을 모두 선택해 주세요.";
    if (!enabled) {
      minTotal.value = "";
      maxTotal.value = "";
    }
    checkOut.min = checkIn.value || "";
    checkIn.max = checkOut.value || "";
  }

  function collectCriteria() {
    const params = {};
    const value = (id) => document.getElementById(id).value;
    const add = (key, raw) => { if (raw !== "" && raw !== null && raw !== undefined) params[key] = String(raw); };
    add("q", value("q").trim());
    add("check_in", checkIn.value);
    add("check_out", checkOut.value);
    if (datesAreUsable()) {
      add("min_total", minTotal.value);
      add("max_total", maxTotal.value);
    }
    add("rooms", value("rooms"));
    add("kind", value("kind") || "all");
    add("min_area", value("min_area"));
    add("guests", value("guests"));
    const options = [...document.querySelectorAll('input[name="options"]:checked')].map((input) => input.value);
    if (options.length) params.options = options.join(",");
    params.instant = document.getElementById("instant").checked ? "1" : "0";
    params.discount = document.getElementById("discount").checked ? "1" : "0";
    params.sort = value("sort") === "total_asc" ? "total_asc" : "id";
    return params;
  }

  function paramsToQuery(params) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if ((key === "layers" || value !== "") && value !== null && value !== undefined) query.set(key, Array.isArray(value) ? value.join(",") : String(value));
    });
    return query;
  }

  function viewUrl(view) {
    const query = paramsToQuery(view.params);
    const layers = (view.layers || ["stay"]).join(",");
    query.set("layers", layers);
    if (view.selection) {
      query.set("selected_layer", view.selection.layer);
      query.set("selected_id", view.selection.id);
    } else {
      query.delete("selected_layer");
      query.delete("selected_id");
    }
    return `${window.location.pathname}?${query.toString()}`;
  }

  function persistState(mode) {
    if (restoringHistory) return;
    const view = controller.view();
    const url = viewUrl(view);
    if (mode === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }

  function setLoading() {
    errorPanel.hidden = true;
    emptyPanel.hidden = true;
    selectedSummary.hidden = true;
    list.replaceChildren();
    for (let index = 0; index < 3; index += 1) {
      const skeleton = document.createElement("div");
      skeleton.className = "skeleton-card";
      skeleton.setAttribute("aria-hidden", "true");
      list.append(skeleton);
    }
    resultCount.textContent = "검색 중";
    setStatus("공개된 정보를 확인하고 있습니다.", "loading");
  }

  function formatWon(value) {
    return new Intl.NumberFormat("ko-KR").format(value);
  }

  function validCount(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function safeItem(item) {
    return item && typeof item === "object" && typeof item.public_id === "string" &&
      item.public_id.length > 0 && Object.hasOwn(layerNames, item.layer) &&
      (item.point === null || (item.point && Number.isFinite(item.point.lat) && Number.isFinite(item.point.lng) &&
        ["approx", "exact"].includes(item.point.precision)));
  }

  function itemTitle(item) {
    if (item.layer === "stay") return item.stay_kind === "non_lodging" ? "주·월 단기임대" : "숙박형 단기임대";
    return typeof item.title === "string" && item.title ? item.title : ({ sale: "매매 매물", business: "영업권 양도", auction: "공매 물건" })[item.layer];
  }

  function quoteText(item) {
    if (item.layer !== "stay") return {value:"공개 요약",label:layerNames[item.layer]+" 정보"};
    const quote = item.quote;
    if (!datesAreUsable()) return { value: "날짜 선택", label: "기간 총액" };
    if (quote && Number.isSafeInteger(quote.total_krw) && quote.total_krw >= 0) {
      return { value: `${formatWon(quote.total_krw)}원`, label: "선택 기간 총액" };
    }
    return { value: "기간 총액 견적 없음", label: "선택 기간 총액" };
  }

  function addMeta(container, text) {
    const span = document.createElement("span");
    span.textContent = text;
    container.append(span);
  }

  function selectItem(item) {
    closeMarkerMenus(null, false);
    controller.select(item.layer, item.public_id);
  }

  function renderCard(item, selected) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "listing-card";
    button.dataset.layer = item.layer;
    button.dataset.publicId = item.public_id;
    button.setAttribute("aria-pressed", selected ? "true" : "false");
    button.setAttribute("aria-label", `${layerNames[item.layer]} · ${itemTitle(item)} · 항목 ${item.public_id}`);

    const glyph = document.createElement("span");
    glyph.className = "stay-glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = layerGlyphs[item.layer];
    const copy = document.createElement("span");
    copy.className = "listing-copy";
    const type = document.createElement("span");
    type.className = "listing-type";
    type.textContent = layerNames[item.layer];
    const title = document.createElement("span");
    title.className = "listing-title";
    title.textContent = itemTitle(item);
    const meta = document.createElement("span");
    meta.className = "listing-meta";
    addMeta(meta, item.point ? (item.point.precision === "approx" ? "대략적 위치" : "공개 위치") : "위치 비공개");
    const reference = document.createElement("span");
    reference.className = "public-reference";
    reference.textContent = `항목 ${item.public_id}`;
    meta.append(reference);
    copy.append(type, title, meta);

    const price = document.createElement("span");
    price.className = "listing-price";
    const pricing = quoteText(item);
    const label = document.createElement("span");
    label.className = "price-label";
    label.textContent = pricing.label;
    const amount = document.createElement("span");
    amount.className = item.quote && datesAreUsable() && Number.isSafeInteger(item.quote.total_krw) ? "price-value" : "price-unavailable";
    amount.textContent = pricing.value;
    price.append(label, amount);
    button.append(glyph, copy, price);
    button.addEventListener("click", () => selectItem(item));
    return button;
  }

  function renderList(items, view) {
    const selected = view.selection;
    list.replaceChildren();
    items.forEach((item) => list.append(renderCard(item, !!selected && selected.layer === item.layer && selected.id === item.public_id)));
    currentItems = items;
    emptyPanel.hidden = items.length > 0;
    const count = resultPayload && resultPayload.items.length;
    resultCount.textContent = count === undefined ? `${items.length}개 표시` : `${formatWon(count)}개`;
    if (items.length) {
      const hiddenCount = validCount(resultPayload?.withheld_count) ? resultPayload.withheld_count : null;
      setStatus(hiddenCount ? `${formatWon(items.length)}개 표시 · 위치 비공개 ${formatWon(hiddenCount)}개` : `${formatWon(items.length)}개 결과를 확인했습니다.`, "ready");
    } else {
      setStatus("현재 조건으로 확인된 결과가 없습니다.", "empty");
    }
  }

  function renderDetail(item, view) {
    if (!item) {
      selectedSummary.hidden = true;
      selectedSummary.replaceChildren();
      list.querySelectorAll(".listing-card").forEach((card) => card.setAttribute("aria-pressed", "false"));
      return;
    }
    const summary = document.createElement("div");
    if (item.layer === "stay") {
      const link = document.createElement("a");
      link.className = "detail-open-link";
      const url = new URL("/hs2/details/",window.location.origin);
      url.searchParams.set("public_id",item.public_id);
      for (const key of ["check_in","check_out","guests"]) {
        if (view.params[key]) url.searchParams.set(key,view.params[key]);
      }
      url.searchParams.set("return",window.location.pathname+window.location.search);
      link.href = url.pathname+url.search;link.textContent="매물 상세·예약 조건 확인";
      summary.append(link);
    }
    const overline = document.createElement("span");
    overline.className = "summary-overline";
    overline.textContent = `${layerNames[item.layer]} · 선택한 공개 항목`;
    const title = document.createElement("strong");
    title.className = "summary-title";
    title.textContent = itemTitle(item);
    const info = document.createElement("p");
    info.className = "summary-copy";
    info.textContent = `${item.point ? item.point.label || "공개 위치" : "위치 비공개"} · 항목 ${item.public_id}. 거래 또는 예약 확정 정보가 아닙니다.`;
    summary.append(overline, title, info);
    const facts = document.createElement("div");
    facts.className = "summary-facts";
    if (item.layer === "stay" && item.summary && typeof item.summary === "object") {
      const details = [
        ["rooms", (value) => value === 0 ? "원룸·스튜디오" : `${value}개 방`],
        ["area_m2", (value) => `${value}㎡`],
        ["guests", (value) => `${value}명`],
        ["min_stay", (value) => `최소 ${value}박`]
      ];
      details.forEach(([key, formatter]) => {
        const value = item.summary[key];
        if (typeof value === "number" && Number.isFinite(value) && value >= 0) addFact(facts, formatter(value));
      });
      if (Array.isArray(item.summary.options)) {
        const labels = { wifi: "와이파이", kitchen: "주방", parking: "주차", washer: "세탁기" };
        item.summary.options.filter((option) => labels[option]).forEach((option) => addFact(facts, labels[option]));
      }
      if (item.summary.instant === true) addFact(facts, "즉시입주");
      if (item.summary.discount === true) addFact(facts, "할인");
    }
    if (facts.childElementCount) summary.append(facts);
    selectedSummary.replaceChildren(summary);
    selectedSummary.hidden = false;
    list.querySelectorAll(".listing-card").forEach((card) => card.setAttribute("aria-pressed",
      card.dataset.layer === view.selection?.layer && card.dataset.publicId === view.selection?.id ? "true" : "false"));
  }

  function addFact(container, text) {
    const fact = document.createElement("span");
    fact.className = "summary-fact";
    fact.textContent = text;
    container.append(fact);
  }

  function setMapState(text, detail, state) {
    if (mapPlaceholder.parentElement !== mapCanvas) mapCanvas.append(mapPlaceholder);
    mapPlaceholder.hidden = false;
    mapMessage.textContent = text;
    mapDetail.textContent = detail;
    mapCanvas.classList.remove("is-live");
    mapFooter.dataset.state = state || "unavailable";
    mapStatus.textContent = state === "error" ? "지도 연결 오류" : "지도 연결 필요";
  }

  function validateSdkUrl(raw) {
    if (typeof raw !== "string") return null;
    try {
      const url = new URL(raw, window.location.origin);
      const fixture = url.origin === window.location.origin && url.pathname === "/hs2/supermap-fixture-sdk.js" && !url.search && !url.hash;
      const kakao = url.protocol === "https:" && url.hostname === "dapi.kakao.com" &&
        url.pathname === "/v2/maps/sdk.js" && !url.username && !url.password && !url.search && !url.hash;
      return fixture || kakao ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function getMaps() {
    return window.kakao && window.kakao.maps;
  }

  function clearOverlays() {
    markerOverlays.forEach((overlay) => overlay.setMap(null));
    privacyCircles.forEach((circle) => circle.setMap(null));
    markerOverlays = [];
    privacyCircles = [];
  }

  function pointPosition(point) {
    const maps = getMaps();
    if (!maps || typeof maps.LatLng !== "function") throw new Error("지도 위치 기능을 사용할 수 없습니다.");
    return new maps.LatLng(point.lat, point.lng);
  }

  function selectionChoice(layer, id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "hs2-marker-choice";
    button.dataset.layer = layer;
    button.dataset.publicId = id;
    button.textContent = `${layerNames[layer]} · 항목 ${id}`;
    button.setAttribute("aria-label", `${layerNames[layer]} 항목 ${id} 선택`);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const item = currentItems.find((row) => row.layer === layer && row.public_id === id);
      if (item) {
        closeMarkerMenus(null, true);
        selectItem(item);
      }
    });
    return button;
  }

  function closeMarkerMenus(except, restoreFocus) {
    mapCanvas.querySelectorAll(".hs2-marker-group.is-open").forEach((group) => {
      if (group === except) return;
      const toggle = group.querySelector(".hs2-marker-toggle");
      const choices = group.querySelector(".hs2-marker-choices");
      group.classList.remove("is-open");
      if (choices) choices.hidden = true;
      if (toggle) {
        toggle.setAttribute("aria-expanded", "false");
        if (restoreFocus) toggle.focus();
      }
    });
  }

  function openMarkerMenu(group, toggle, choices) {
    closeMarkerMenus(group, false);
    group.classList.add("is-open");
    choices.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    const firstChoice = choices.querySelector(".hs2-marker-choice");
    if (firstChoice) firstChoice.focus();
  }

  function createMarkerContent(marker, datesValid) {
    const wrap = document.createElement("div");
    wrap.className = "hs2-marker-group";
    wrap.dataset.layer = marker.layer;
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", `${layerNames[marker.layer]} 지도 표시 ${marker.ids.length}개`);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "hs2-marker-toggle";
    toggle.dataset.layer = marker.layer;
    const approxLabel = marker.point.precision === "approx" && typeof marker.point.label === "string" ? marker.point.label : "";
    toggle.setAttribute("aria-label", `${layerNames[marker.layer]} ${marker.ids.length}개${approxLabel ? ` · ${approxLabel}` : ""}`);
    toggle.title = approxLabel || `${layerNames[marker.layer]} ${marker.ids.length}개`;
    if (marker.layer === "stay") {
      const price = document.createElement("span");
      price.className = "hs2-marker-price";
      const hasQuote = datesValid && Number.isSafeInteger(marker.total_krw) && marker.total_krw >= 0;
      price.dataset.unpriced = hasQuote ? "false" : "true";
      price.textContent = hasQuote ? `${formatWon(marker.total_krw)}원` : "날짜 선택";
      toggle.append(price);
    }
    const symbol = document.createElement("span");
    symbol.className = "hs2-marker-shape";
    symbol.dataset.layer = marker.layer;
    symbol.setAttribute("aria-hidden", "true");
    const symbolRow = document.createElement("span");
    symbolRow.className = "hs2-marker-symbol-row";
    symbolRow.append(symbol);
    const count = document.createElement("span");
    count.className = "hs2-marker-count";
    count.textContent = String(marker.ids.length);
    count.setAttribute("aria-hidden", "true");
    symbolRow.append(count);
    toggle.append(symbolRow);
    if (marker.ids.length === 1) {
      toggle.dataset.publicId = marker.ids[0];
      toggle.addEventListener("click", () => {
        const item = currentItems.find((row) => row.layer === marker.layer && row.public_id === marker.ids[0]);
        if (item) selectItem(item);
      });
    }

    const choices = document.createElement("div");
    choices.className = "hs2-marker-choices";
    choices.id = `hs2-marker-options-${++markerMenuSequence}`;
    choices.setAttribute("aria-label", `${layerNames[marker.layer]} 항목 선택`);
    choices.hidden = true;
    marker.ids.forEach((id) => choices.append(selectionChoice(marker.layer, id)));
    if (marker.ids.length > 1) {
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-controls", choices.id);
      toggle.addEventListener("click", () => {
        if (wrap.classList.contains("is-open")) {
          closeMarkerMenus(wrap, false);
          wrap.classList.remove("is-open");
          choices.hidden = true;
          toggle.setAttribute("aria-expanded", "false");
        } else {
          openMarkerMenu(wrap, toggle, choices);
        }
      });
      choices.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closeMarkerMenus(null, true);
        }
      });
    }
    wrap.append(toggle, choices);
    return wrap;
  }

  function renderMapMarkers(payload) {
    if (!mapInstance || !payload) return;
    const maps = getMaps();
    if (!maps || typeof maps.CustomOverlay !== "function" || typeof maps.Circle !== "function") {
      setMapState("지도를 표시할 수 없습니다.", "지도 SDK에 CustomOverlay 또는 Circle 기능이 없습니다.", "error");
      return;
    }
    clearOverlays();
    const active = new Set(controller.view().layers);
    payload.markers.forEach((marker) => {
      if (!marker || !active.has(marker.layer) || !Array.isArray(marker.ids) || !marker.ids.length || !marker.point ||
          !Number.isFinite(marker.point.lat) || !Number.isFinite(marker.point.lng)) return;
      const position = pointPosition(marker.point);
      const content = createMarkerContent(marker, datesAreUsable());
      const overlay = new maps.CustomOverlay({ content, position, map: mapInstance, xAnchor: 0.5, yAnchor: 0.5, clickable: true });
      markerOverlays.push(overlay);
      if (marker.point.precision === "approx" && marker.point.radius_m === 500) {
        const circle = new maps.Circle({
          center: position, radius: 500,
          strokeWeight: 1, strokeColor: "#28615b", strokeOpacity: .48,
          strokeStyle: "dashed", fillColor: "#9bbba4", fillOpacity: .16
        });
        circle.setMap(mapInstance);
        privacyCircles.push(circle);
      }
    });
    mapPlaceholder.hidden = true;
    mapCanvas.classList.add("is-live");
    mapFooter.dataset.state = "ready";
    mapStatus.textContent = "지도 표시 중 · 보호 위치는 약 500m 범위";
  }

  function readBounds() {
    if (!mapInstance || typeof mapInstance.getBounds !== "function") return null;
    const bounds = mapInstance.getBounds();
    if (!bounds || typeof bounds.getSouthWest !== "function" || typeof bounds.getNorthEast !== "function") return null;
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    const values = [sw.getLat(), sw.getLng(), ne.getLat(), ne.getLng()];
    if (values.some((value) => !Number.isFinite(value)) || values[0] >= values[2] || values[1] >= values[3]) return null;
    return values;
  }

  function scheduleBoundsRefresh() {
    if (skipNextIdle) {
      skipNextIdle = false;
      return;
    }
    window.clearTimeout(boundsTimer);
    boundsTimer = window.setTimeout(() => {
      const bounds = readBounds();
      if (!bounds) return;
      const key = bounds.map((value) => value.toFixed(5)).join(",");
      if (key === lastBoundsString) return;
      lastBoundsString = key;
      controller.bounds(bounds);
      persistState("replace");
    }, 300);
  }

  function initializeMap(payload) {
    const sdkUrl = validateSdkUrl(payload?.map_config?.sdk_url);
    if (!sdkUrl) {
      clearOverlays();
      setMapState("지도 연결 정보를 확인할 수 없습니다.", "허용된 지도 SDK 주소가 검색 응답에 없습니다.", "error");
      return;
    }
    if (mapInstance) {
      renderMapMarkers(payload);
      return;
    }
    if (getMaps() && typeof getMaps().Map === "function") {
      makeMap(payload);
      return;
    }
    if (mapScript && mapSdkUrl === sdkUrl) return;
    if (mapScript) mapScript.remove();
    mapSdkUrl = sdkUrl;
    setMapState("지도를 연결하고 있습니다.", "허용된 지도 SDK 응답을 기다리는 중입니다.", "loading");
    const script = document.createElement("script");
    script.src = sdkUrl;
    script.async = true;
    script.onload = () => {
      if (mapScript !== script || mapSdkUrl !== sdkUrl) return;
      if (getMaps() && typeof getMaps().Map === "function") makeMap(resultPayload || payload);
      else setMapState("지도를 연결할 수 없습니다.", "SDK 응답에서 지도 기능을 확인할 수 없습니다.", "error");
    };
    script.onerror = () => {
      if (mapScript === script) setMapState("지도를 연결할 수 없습니다.", "지도 SDK 서버에 연결하지 못했습니다.", "error");
    };
    mapScript = script;
    document.head.append(script);
  }

  function makeMap(payload) {
    const maps = getMaps();
    const firstMarker = payload.markers.find((marker) => marker && marker.point &&
      Number.isFinite(marker.point.lat) && Number.isFinite(marker.point.lng));
    if (!firstMarker) {
      setMapState("표시할 공개 위치가 없습니다.", "목록은 확인할 수 있지만 공개 가능한 좌표는 지도에 표시되지 않습니다.", "unavailable");
      return;
    }
    try {
      if (typeof maps.Map !== "function" || typeof maps.LatLng !== "function" ||
          !maps.event || typeof maps.event.addListener !== "function") throw new Error("지도 엔진 API가 올바르지 않습니다.");
      mapCanvas.replaceChildren();
      mapInstance = new maps.Map(mapCanvas, { center: new maps.LatLng(firstMarker.point.lat, firstMarker.point.lng), level: 6 });
      skipNextIdle = true;
      maps.event.addListener(mapInstance, "idle", scheduleBoundsRefresh);
      window.addEventListener("resize", relayoutMap);
      renderMapMarkers(payload);
    } catch (error) {
      mapInstance = null;
      setMapState("지도를 표시할 수 없습니다.", error.message || "지도 엔진 초기화에 실패했습니다.", "error");
    }
  }

  function relayoutMap() {
    if (!mapInstance || typeof mapInstance.relayout !== "function") return;
    mapInstance.relayout();
    window.clearTimeout(boundsTimer);
    boundsTimer = window.setTimeout(() => {
      const bounds = readBounds();
      if (!bounds) return;
      lastBoundsString = bounds.map((value) => value.toFixed(5)).join(",");
    }, 220);
  }

  function updateLayerCounts(counts) {
    document.querySelectorAll("[data-count-layer]").forEach((node) => {
      const count = counts && counts[node.dataset.countLayer];
      node.textContent = validCount(count) ? formatWon(count) : "—";
    });
  }

  function handleResults(payload, view) {
    if (!payload) {
      resultPayload = null;
      currentItems = [];
      setLoading();
      clearOverlays();
      updateLayerCounts(null);
      return;
    }
    if (!Array.isArray(payload.items) || !Array.isArray(payload.markers) ||
        payload.items.some((item) => !safeItem(item))) {
      onError(new Error("검색 응답에 공개 항목 형식 오류가 있습니다."), view);
      return;
    }
    resultPayload = payload;
    updateLayerCounts(payload.counts);
    renderList(payload.items, view);
    initializeMap(payload);
    persistState("replace");
  }

  function onError(error, view) {
    errorPanel.hidden = false;
    emptyPanel.hidden = true;
    list.replaceChildren();
    resultCount.textContent = "확인 필요";
    const code = error && typeof error.message === "string" ? error.message : "검색 정보를 불러오지 못했습니다.";
    errorTitle.textContent = "검색 결과를 불러오지 못했습니다.";
    errorCopy.textContent = `${code} 조건은 유지됩니다. 잠시 후 다시 시도해 주세요.`;
    setStatus("검색 또는 상세 정보를 불러오지 못했습니다.", "error");
    if (view && !view.selection) {
      selectedSummary.hidden = true;
    }
    clearOverlays();
    if (!mapInstance) setMapState("지도 연결에 실패했습니다.", "지도 기능은 검색 응답과 SDK 연결이 필요합니다.", "error");
  }

  async function fetchJson(url, signal) {
    const response = await fetch(url, { method: "GET", headers: { Accept: "application/json" }, credentials: "include", signal });
    let payload;
    try { payload = await response.json(); }
    catch (_) { throw new Error("서버 응답을 읽을 수 없습니다."); }
    if (!response.ok || payload.ok !== true) {
      const error = new Error(typeof payload.code === "string" ? payload.code : "SOURCE_UNAVAILABLE");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function createController() {
    return new window.HS2MapController({
      fetchSearch: (params, signal) => fetchJson(`/hs2/search/api/results?${paramsToQuery(params).toString()}`, signal),
      fetchDetail: (layer, id, params, signal) =>
        fetchJson(`/hs2/search/api/detail/${encodeURIComponent(layer)}/${encodeURIComponent(id)}?${paramsToQuery(params).toString()}`, signal),
      onResults: handleResults,
      onDetail: (item, view) => {
        if (item) {
          errorPanel.hidden = true;
          renderDetail(item, view);
          persistState("push");
        } else {
          renderDetail(null, view);
        }
      },
      onError
    });
  }

  function dateRangeValid() {
    if (checkIn.value && checkOut.value && checkOut.value <= checkIn.value) {
      checkOut.setCustomValidity("퇴실일은 입실일보다 늦어야 합니다.");
      checkOut.reportValidity();
      checkOut.setCustomValidity("");
      return false;
    }
    return true;
  }

  function readAddress() {
    const query = new URLSearchParams(window.location.search);
    const params = {};
    const allowed = ["q", "check_in", "check_out", "min_total", "max_total", "rooms", "kind", "min_area", "guests", "options", "instant", "discount", "sort", "bounds"];
    allowed.forEach((key) => {
      if (query.has(key)) params[key] = query.get(key);
    });
    params.kind = ["all", "lodging", "non_lodging"].includes(params.kind) ? params.kind : "all";
    params.sort = params.sort === "total_asc" ? "total_asc" : "id";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(params.check_in || "")) delete params.check_in;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(params.check_out || "") ||
        (params.check_in && params.check_out <= params.check_in)) delete params.check_out;
    if (!datesValidFromParams(params)) {
      delete params.min_total;
      delete params.max_total;
    }
    if (params.q) params.q = params.q.slice(0, 100);
    const validLayers = ["stay", "sale", "business", "auction"];
    const requested = (query.has("layers") ? query.get("layers") : "stay").split(",").filter((layer) => validLayers.includes(layer));
    const layers = [...new Set(requested)];
    return {
      params,
      layers,
      selection: query.has("selected_layer") && query.has("selected_id") &&
        validLayers.includes(query.get("selected_layer")) ?
        { layer: query.get("selected_layer"), id: query.get("selected_id") } : null
    };
  }

  function datesValidFromParams(params) {
    return isValidDate(params.check_in || "") && isValidDate(params.check_out || "") && params.check_out > params.check_in;
  }

  function restoreForm(params) {
    const set = (id, value) => { document.getElementById(id).value = value || ""; };
    ["q", "check_in", "check_out", "min_total", "max_total", "rooms", "kind", "min_area", "guests", "sort"].forEach((key) => set(key, params[key]));
    const options = new Set((params.options || "").split(",").filter(Boolean));
    document.querySelectorAll('input[name="options"]').forEach((input) => { input.checked = options.has(input.value); });
    document.getElementById("instant").checked = params.instant === "1";
    document.getElementById("discount").checked = params.discount === "1";
    updatePriceControls();
  }

  async function restoreAddress() {
    const saved = readAddress();
    restoreForm(saved.params);
    lastCriteria = { ...saved.params };
    layerInputs.forEach((input) => { input.checked = saved.layers.includes(input.value); });
    restoringHistory = true;
    try {
      await controller.restore(saved);
    } finally {
      restoringHistory = false;
      persistState("replace");
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!dateRangeValid()) return;
    updatePriceControls();
    lastCriteria = collectCriteria();
    controller.search(lastCriteria);
    persistState("push");
  });

  checkIn.addEventListener("change", updatePriceControls);
  checkOut.addEventListener("change", updatePriceControls);
  retryButton.addEventListener("click", () => controller.search({ ...lastCriteria }));
  layerInputs.forEach((input) => input.addEventListener("change", () => {
    const active = controller.view().layers;
    controller.toggle(input.value, input.checked);
    const next = input.checked ? [...new Set([...active, input.value])] : active.filter((layer) => layer !== input.value);
    layerInputs.forEach((layerInput) => { layerInput.checked = next.includes(layerInput.value); });
    persistState("push");
  }));

  window.addEventListener("popstate", () => {
    restoringHistory = true;
    restoreAddress();
  });

  // Preserve the API's entire declared range and exact room-count semantics.
  for (let n = 4; n <= 30; n++) {
    const option = document.createElement("option"); option.value = String(n);
    option.textContent = `${n}개`; document.getElementById("rooms").append(option);
  }
  for (let n = 1; n <= 100; n++) {
    const select = document.getElementById("guests");
    if (!select.querySelector(`option[value="${n}"]`)) {
      const option = document.createElement("option"); option.value = String(n);
      option.textContent = `${n}명 이상`; select.append(option);
    }
  }
  controller = createController();
  updatePriceControls();
  lastCriteria = collectCriteria();
  restoreAddress();
})();
