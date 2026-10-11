(() => {
  "use strict";

  const API_URL = "/hs2/api/consumer/search";
  const isSeongsuDemo = document.body.dataset.hs2Demo === "seongsu";
  const form = document.getElementById("searchForm");
  const listingList = document.getElementById("listingList");
  const statusMessage = document.getElementById("statusMessage");
  const statusCopy = statusMessage.querySelector("span:last-child");
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
  const mapFooter = mapStatus.parentElement;
  let activeController = null;
  let requestSequence = 0;
  let lastCriteria = null;
  let selectedId = null;
  let mapScriptUrl = null;
  let consumerMap = null;
  let demoMapOverlays = [];
  let visibleItems = [];

  const inputs = {
    q: document.getElementById("q"),
    check_in: checkIn,
    check_out: checkOut,
    min_total: minTotal,
    max_total: maxTotal,
    rooms: document.getElementById("rooms"),
    min_area: document.getElementById("min_area"),
    guests: document.getElementById("guests"),
    kind: document.getElementById("kind"),
    sort: document.getElementById("sort")
  };

  function setStatus(text, state) {
    statusCopy.textContent = text;
    statusMessage.dataset.state = state || "idle";
  }

  function datesAreUsable() {
    const isRealDate = (value) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
      const [year, month, day] = value.split("-").map(Number);
      const date = new Date(Date.UTC(year, month - 1, day));
      return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
    };
    return Boolean(isRealDate(checkIn.value) && isRealDate(checkOut.value) && checkOut.value > checkIn.value);
  }

  function updatePriceControls() {
    const enabled = datesAreUsable();
    minTotal.disabled = !enabled;
    maxTotal.disabled = !enabled;
    priceHint.textContent = enabled ? "선택한 입·퇴실 기간의 총액으로 비교합니다." : "입실일과 퇴실일을 선택하면 사용할 수 있어요.";
    if (!enabled) {
      minTotal.value = "";
      maxTotal.value = "";
    }
    checkOut.min = checkIn.value || "";
    checkIn.max = checkOut.value || "";
  }

  function appendIf(params, key, value) {
    if (value !== "" && value !== null && value !== undefined) params.set(key, String(value));
  }

  function collectCriteria() {
    const params = new URLSearchParams();
    appendIf(params, "q", inputs.q.value.trim());
    appendIf(params, "check_in", inputs.check_in.value);
    appendIf(params, "check_out", inputs.check_out.value);
    const validDates = datesAreUsable();
    if (validDates) {
      appendIf(params, "min_total", inputs.min_total.value);
      appendIf(params, "max_total", inputs.max_total.value);
    }
    if (isSeongsuDemo) {
      appendIf(params, "rooms", inputs.rooms.value);
      appendIf(params, "min_area", inputs.min_area.value);
      appendIf(params, "guests", inputs.guests.value);
      const options = [...document.querySelectorAll('input[name="options"]:checked')].map((input) => input.value);
      appendIf(params, "options", options.join(","));
      appendIf(params, "instant", document.getElementById("instant").checked ? "1" : "0");
      appendIf(params, "discount", document.getElementById("discount").checked ? "1" : "0");
    }
    appendIf(params, "kind", inputs.kind.value || "all");
    params.set("sort", inputs.sort.value === "total_asc" ? "total_asc" : "id");
    return params;
  }

  function updateAddress(params) {
    const query = params.toString();
    const nextUrl = window.location.pathname + (query ? `?${query}` : "");
    window.history.replaceState(null, "", nextUrl);
  }

  function restoreFromAddress() {
    const params = new URLSearchParams(window.location.search);
    const datePattern = /^\d{4}-\d{2}-\d{2}$/;
    const numericPattern = /^\d{1,12}$/;
    inputs.q.value = (params.get("q") || "").slice(0, 100);
    const start = params.get("check_in") || "";
    const end = params.get("check_out") || "";
    if (datePattern.test(start)) checkIn.value = start;
    if (datePattern.test(end) && (!checkIn.value || end > checkIn.value)) checkOut.value = end;
    if (numericPattern.test(params.get("min_total") || "")) minTotal.value = params.get("min_total");
    if (numericPattern.test(params.get("max_total") || "")) maxTotal.value = params.get("max_total");
    if (["all", "lodging", "non_lodging"].includes(params.get("kind"))) inputs.kind.value = params.get("kind");
    if (["id", "total_asc"].includes(params.get("sort"))) inputs.sort.value = params.get("sort");
    updatePriceControls();
    if (!datesAreUsable()) {
      minTotal.value = "";
      maxTotal.value = "";
    }
    if (isSeongsuDemo) {
      ["rooms", "min_area", "guests"].forEach((id) => { document.getElementById(id).disabled = false; });
      document.querySelectorAll('input[name="options"], #instant, #discount').forEach((input) => { input.disabled = false; });
      ["rooms", "guests"].forEach((id) => {
        const value = params.get(id);
        const select = document.getElementById(id);
        if (/^\d{1,3}$/.test(value || "") && [...select.options].some((option) => option.value === value)) select.value = value;
      });
      if (/^\d{1,6}$/.test(params.get("min_area") || "")) inputs.min_area.value = params.get("min_area");
      const options = (params.get("options") || "").split(",");
      document.querySelectorAll('input[name="options"]').forEach((input) => { input.checked = options.includes(input.value); });
      document.getElementById("instant").checked = params.get("instant") === "1";
      document.getElementById("discount").checked = params.get("discount") === "1";
      if (!checkIn.value) {
        const seoulToday = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
        const tomorrow = new Date(`${seoulToday}T00:00:00Z`);
        tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
        checkIn.value = tomorrow.toISOString().slice(0, 10);
        const nextDay = new Date(tomorrow);
        // A full week includes both lodging and non-lodging demo inventory.
        // A one-night default hid every 7-day-minimum synthetic apartment.
        nextDay.setUTCDate(nextDay.getUTCDate() + 7);
        if (!checkOut.value) checkOut.value = nextDay.toISOString().slice(0, 10);
      }
      updatePriceControls();
    }
  }

  function setLoading() {
    errorPanel.hidden = true;
    emptyPanel.hidden = true;
    selectedSummary.hidden = true;
    listingList.replaceChildren();
    for (let index = 0; index < 3; index += 1) {
      const skeleton = document.createElement("div");
      skeleton.className = "skeleton-card";
      skeleton.setAttribute("aria-hidden", "true");
      listingList.append(skeleton);
    }
    resultCount.textContent = "검색 중";
    setStatus("검색 조건에 맞는 정보를 확인하고 있어요.", "loading");
  }

  function formatWon(value) {
    return new Intl.NumberFormat("ko-KR").format(value);
  }

  function safeCount(value) {
    return Number.isInteger(value) && value >= 0 ? value : null;
  }

  function addMeta(container, text) {
    const item = document.createElement("span");
    item.textContent = text;
    container.append(item);
  }

  function demoDetailUrl(item) {
    const url = new URL("/hs2/details/", window.location.origin);
    url.searchParams.set("public_id", item.public_id);
    for (const key of ["check_in", "check_out"]) if (inputs[key].value) url.searchParams.set(key, inputs[key].value);
    if (inputs.guests.value) url.searchParams.set("guests", inputs.guests.value);
    url.searchParams.set("return", `${window.location.pathname}${window.location.search}`);
    return `${url.pathname}${url.search}`;
  }

  function appendDemoPhoto(container, demo, className) {
    if (!isSeongsuDemo || !demo || !Array.isArray(demo.photos) || !demo.photos.length) return;
    const raw = demo.photos[0];
    if (typeof raw !== "string" || !raw.startsWith("/__development__/seongsu/assets/")) return;
    const wrap = document.createElement("span");
    wrap.className = "demo-photo-wrap";
    const image = document.createElement("img");
    image.className = className;
    image.src = raw;
    image.alt = "가상 공간 이미지";
    image.loading = "lazy";
    image.decoding = "async";
    const caption = document.createElement("span");
    caption.className = "demo-photo-caption";
    caption.textContent = "가상 공간 이미지";
    wrap.append(image, caption);
    container.append(wrap);
  }

  function appendDemoBadge(container) {
    const badge = document.createElement("span");
    badge.className = "demo-test-badge";
    badge.textContent = "테스트용 가상 매물 · 실재/법적 운영 확인 아님";
    container.append(badge);
  }

  function validDemoPoint(point) {
    return point && Number.isFinite(point.lat) && Number.isFinite(point.lng) &&
      point.lat >= -90 && point.lat <= 90 && point.lng >= -180 && point.lng <= 180;
  }

  function renderConsumerDemoMarkers() {
    const maps = window.kakao && window.kakao.maps;
    if (!isSeongsuDemo || !consumerMap || !maps || typeof maps.CustomOverlay !== "function") return;
    demoMapOverlays.forEach((overlay) => overlay.setMap(null));
    demoMapOverlays = [];
    visibleItems.forEach((item) => {
      const demo = item.preview_demo;
      if (!demo || demo.synthetic !== true || !validDemoPoint(demo.point)) return;
      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = "consumer-demo-map-marker";
      marker.textContent = typeof demo.name === "string" ? demo.name : "가상 체류 공간";
      marker.setAttribute("aria-label", `${demo.neighborhood || "성수동"} 시뮬레이션 구역 · ${marker.textContent} · 테스트용 가상 매물`);
      marker.addEventListener("click", () => window.location.assign(demoDetailUrl(item)));
      const overlay = new maps.CustomOverlay({
        content: marker,
        position: new maps.LatLng(demo.point.lat, demo.point.lng),
        map: consumerMap,
        xAnchor: 0.5,
        yAnchor: 1,
        clickable: true
      });
      demoMapOverlays.push(overlay);
    });
  }

  function validItem(item) {
    return item && typeof item === "object" &&
      typeof item.public_id === "string" && item.public_id.length > 0 &&
      typeof item.stay_kind === "string" &&
      item.location_precision === "withheld";
  }

  function renderItem(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "listing-card";
    button.dataset.publicId = item.public_id;
    button.setAttribute("aria-pressed", item.public_id === selectedId ? "true" : "false");

    const demo = isSeongsuDemo && item.preview_demo && item.preview_demo.synthetic === true ? item.preview_demo : null;
    if (demo) button.classList.add("has-demo-photo", "synthetic-demo-card");
    appendDemoPhoto(button, demo, "demo-card-photo");
    const glyph = document.createElement("span");
    glyph.className = "stay-glyph";
    glyph.dataset.kind = item.stay_kind === "non_lodging" ? "non_lodging" : "lodging";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = item.stay_kind === "non_lodging" ? "공간" : "체류";

    const copy = document.createElement("span");
    copy.className = "listing-copy";
    const title = document.createElement("span");
    title.className = "listing-title";
    title.textContent = demo && typeof demo.name === "string" ? demo.name : item.stay_kind === "non_lodging" ? "비숙박 체류 항목" : "숙박 체류 항목";
    copy.append(title);

    const meta = document.createElement("span");
    meta.className = "listing-meta";
    addMeta(meta, "위치 비공개");
    if (demo && demo.neighborhood) addMeta(meta, demo.neighborhood);
    const reference = document.createElement("span");
    reference.className = "public-reference";
    reference.textContent = `항목 ${item.public_id}`;
    meta.append(reference);
    copy.append(meta);
    if (demo) appendDemoBadge(copy);

    const price = document.createElement("span");
    price.className = "listing-price";
    const priceLabel = document.createElement("span");
    priceLabel.className = "price-label";
    priceLabel.textContent = "선택 기간 총액";
    price.append(priceLabel);
    const quoteValid = item.quote && Number.isSafeInteger(item.quote.total_krw) &&
      item.quote.total_krw >= 0 && item.quote.check_in === checkIn.value &&
      item.quote.check_out === checkOut.value && datesAreUsable();
    if (quoteValid) {
      const amount = document.createElement("span");
      amount.className = "price-value";
      amount.textContent = `${formatWon(item.quote.total_krw)}원`;
      price.append(amount);
    } else {
      const noPrice = document.createElement("span");
      noPrice.className = "price-unavailable";
      noPrice.textContent = "기간 총액 견적 없음";
      price.append(noPrice);
    }
    if (demo) {
      const base = document.createElement("span");
      base.className = "demo-base-price";
      if (item.stay_kind === "non_lodging") {
        const week = Number.isSafeInteger(demo.weekly_krw) ? `${formatWon(demo.weekly_krw)}원/주` : "주 요금 미설정";
        const month = Number.isSafeInteger(demo.monthly_krw) ? `${formatWon(demo.monthly_krw)}원/월` : "월 요금 미설정";
        base.textContent = `${week} · 달력 1개월 ${month}`;
      } else {
        base.textContent = Number.isSafeInteger(demo.nightly_krw) ? `기준 ${formatWon(demo.nightly_krw)}원/박` : "기준 요금 미설정";
      }
      price.append(base);
    }

    button.append(glyph, copy, price);
    button.addEventListener("click", () => {
      if (demo) {
        selectItem(item);
        window.location.assign(demoDetailUrl(item));
      } else selectItem(item);
    });
    return button;
  }

  function selectItem(item) {
    selectedId = item.public_id;
    const title = document.createElement("strong");
    title.className = "summary-title";
    const demo = item.preview_demo && item.preview_demo.synthetic === true ? item.preview_demo : null;
    title.textContent = demo && demo.name || (item.stay_kind === "non_lodging" ? "비숙박 체류 항목" : "숙박 체류 항목");
    const overline = document.createElement("span");
    overline.className = "summary-overline";
    overline.textContent = "선택한 항목 · 안전 요약";
    const summary = document.createElement("p");
    summary.className = "summary-copy";
    summary.textContent = demo
      ? `${demo.neighborhood || "성수동"} · 테스트용 가상 매물 · 상세에서 실제 견적 흐름을 확인해 보세요.`
      : `항목 ${item.public_id} · 정확한 위치와 보호 메타데이터는 표시하지 않습니다.`;
    selectedSummary.replaceChildren(overline, title, summary);
    selectedSummary.hidden = false;
    listingList.querySelectorAll(".listing-card").forEach((card) => {
      card.setAttribute("aria-pressed", card.dataset.publicId === selectedId ? "true" : "false");
    });
  }

  function updateMap(config) {
    let safeSdk = false;
    if (config && typeof config.sdk_url === "string") {
      try {
        const url = new URL(config.sdk_url, window.location.origin);
        safeSdk = (url.origin === window.location.origin &&
          url.pathname === "/hs2/consumer-fixture-sdk.js" && !url.search) ||
          (url.protocol === "https:" && url.hostname === "dapi.kakao.com" &&
            url.pathname === "/v2/maps/sdk.js" && !url.username && !url.password);
      } catch (_) { safeSdk = false; }
    }
    if (!safeSdk) {
      mapStatus.textContent = "지도 연결 정보 없음";
      mapFooter.dataset.state = "unavailable";
      mapMessage.textContent = "지도를 연결할 수 없습니다.";
      mapDetail.textContent = "검색 응답에 유효한 지도 SDK 연결 정보가 없습니다.";
      return;
    }
    if (window.kakao && window.kakao.maps) {
      initializeKakaoMap();
      return;
    }
    mapMessage.textContent = "지도를 연결하고 있습니다.";
    mapDetail.textContent = "지도 SDK 응답을 기다리는 중입니다.";
    mapStatus.textContent = "지도 SDK 연결 중";
    if (mapScriptUrl === config.sdk_url) return;
    mapScriptUrl = config.sdk_url;
    const script = document.createElement("script");
    script.src = config.sdk_url;
    script.async = true;
    script.onload = () => {
      if (window.kakao && window.kakao.maps) initializeKakaoMap();
      else showMapUnavailable("지도 SDK에 연결할 수 없습니다.", "지도 SDK 응답에서 지도 기능을 확인할 수 없습니다.");
    };
    script.onerror = () => showMapUnavailable("지도를 연결할 수 없습니다.", "지도 서버 연결을 확인해 주세요.");
    document.head.append(script);
  }

  function initializeKakaoMap() {
    const kakao = window.kakao;
    if (!kakao || !kakao.maps || typeof kakao.maps.load !== "function" || typeof kakao.maps.Map !== "function") {
      showMapUnavailable("지도를 연결할 수 없습니다.", "지도 엔진을 사용할 수 없습니다.");
      return;
    }
    if (isSeongsuDemo && consumerMap) {
      renderConsumerDemoMarkers();
      return;
    }
    try {
      kakao.maps.load(() => {
        try {
          mapCanvas.replaceChildren();
          mapCanvas.classList.add("is-live");
          if (isSeongsuDemo) {
            const point = visibleItems.find((item) =>
              item.preview_demo?.synthetic === true && validDemoPoint(item.preview_demo.point))?.preview_demo.point;
            const options = point ? { center: new kakao.maps.LatLng(point.lat, point.lng), level: 5 } : {};
            consumerMap = new kakao.maps.Map(mapCanvas, options);
            renderConsumerDemoMarkers();
            mapMessage.textContent = "성수동 시뮬레이션 지도";
            mapDetail.textContent = "가상 위치로 배치한 테스트 매물입니다. 실제 지도 좌표가 아닙니다.";
          } else {
            // Deliberately omit fabricated coordinates and markers for withheld locations.
            new kakao.maps.Map(mapCanvas, {});
          }
          mapStatus.textContent = isSeongsuDemo ? "시뮬레이션 구역 지도 연결됨 · 가상 위치" : "지도 연결됨 · 보호된 위치는 표시하지 않음";
          mapFooter.dataset.state = "ready";
        } catch (_error) {
          showMapUnavailable("지도를 표시할 수 없습니다.", "지도 엔진 연결 또는 설정을 확인해 주세요.");
        }
      });
    } catch (_error) {
      showMapUnavailable("지도를 표시할 수 없습니다.", "지도 엔진 연결을 확인해 주세요.");
    }
  }

  function showMapUnavailable(title, detail) {
    mapCanvas.classList.remove("is-live");
    mapPlaceholder.hidden = false;
    mapCanvas.replaceChildren(mapPlaceholder);
    mapMessage.textContent = title;
    mapDetail.textContent = detail;
    mapStatus.textContent = "지도 연결 필요";
    mapFooter.dataset.state = "unavailable";
  }

  function renderResponse(payload) {
    if (!payload || payload.ok !== true || !Array.isArray(payload.items) ||
        payload.price_basis !== "selected_stay_total") {
      throw new Error("검색 응답 형식이 올바르지 않습니다.");
    }
    const items = payload.items.filter(validItem);
    if (items.length !== payload.items.length) {
      throw new Error("공개 매물 응답 형식이 올바르지 않습니다.");
    }
    listingList.replaceChildren();
    visibleItems = items;
    items.forEach((item) => listingList.append(renderItem(item)));
    selectedSummary.hidden = true;
    selectedId = null;
    const count = safeCount(payload.count);
    resultCount.textContent = count === null ? `${items.length}개 표시` : `${formatWon(count)}개`;
    emptyPanel.hidden = items.length > 0;
    if (items.length) {
      const unquoted = safeCount(payload.unquoted_count);
      const note = unquoted === null ? "검색 결과를 확인했습니다." : `검색 결과 ${formatWon(items.length)}개 · 기간 총액 견적 없음 ${formatWon(unquoted)}개`;
      setStatus(note, "ready");
    } else {
      setStatus("현재 조건으로 확인된 결과가 없습니다.", "empty");
    }
    updateMap(payload.map_config);
  }

  async function search(params) {
    if (activeController) activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    const currentRequest = ++requestSequence;
    lastCriteria = new URLSearchParams(params);
    updateAddress(params);
    setLoading();
    searchButton.disabled = true;
    try {
      const response = await fetch(`${API_URL}?${params.toString()}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "include",
        signal: controller.signal
      });
      let payload;
      try { payload = await response.json(); }
      catch (_error) { throw new Error("검색 서버에서 읽을 수 있는 응답을 받지 못했습니다."); }
      if (currentRequest !== requestSequence) return;
      if (!response.ok || payload.ok !== true) {
        const message = typeof payload.message === "string" ? payload.message : "검색 서버에 연결할 수 없습니다.";
        const code = typeof payload.code === "string" ? payload.code : "";
        throw Object.assign(new Error(message), { code, status: response.status });
      }
      renderResponse(payload);
    } catch (error) {
      if (error.name === "AbortError" || currentRequest !== requestSequence) return;
      visibleItems = [];
      demoMapOverlays.forEach((overlay) => overlay.setMap(null));
      demoMapOverlays = [];
      consumerMap = null;
      listingList.replaceChildren();
      emptyPanel.hidden = true;
      errorPanel.hidden = false;
      errorTitle.textContent = error.status === 400 ? "검색 조건을 확인해 주세요." :
        error.status === 503 ? "검색 정보를 잠시 사용할 수 없습니다." : "검색 결과를 불러오지 못했습니다.";
      errorCopy.textContent = error.message || "연결을 확인한 뒤 다시 시도해 주세요. 입력한 조건은 유지됩니다.";
      resultCount.textContent = "확인 필요";
      setStatus("검색에 실패했습니다. 조건은 유지되어 있습니다.", "error");
      updateMap(null);
    } finally {
      if (currentRequest === requestSequence) {
        searchButton.disabled = false;
        activeController = null;
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (checkIn.value && checkOut.value && checkOut.value <= checkIn.value) {
      checkOut.setCustomValidity("퇴실일은 입실일보다 늦어야 합니다.");
      checkOut.reportValidity();
      checkOut.setCustomValidity("");
      return;
    }
    search(collectCriteria());
  });
  checkIn.addEventListener("change", updatePriceControls);
  checkOut.addEventListener("change", updatePriceControls);
  retryButton.addEventListener("click", () => {
    if (lastCriteria) search(new URLSearchParams(lastCriteria));
  });

  restoreFromAddress();
  search(collectCriteria());
})();
