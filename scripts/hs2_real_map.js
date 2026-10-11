/* Owned listing adapters on the ORIGINAL Kakao Maps SDK + original tool code.
 * No fake tiles/geometry provider, production API, login or payment credentials.
 */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const names = { stay: "단기임대", sale: "매매", business: "영업권 양도", auction: "공매" };
  const colors = { stay: "#245bad", sale: "#e78428", business: "#8a52ba", auction: "#da4b4b" };
  const active = new Set(Object.keys(names));
  const originalFetch = window.fetch.bind(window);
  let map = null, items = [], overlays = [], selected = null, stationOverlays = [];
  let sequence = 0, subwaySequence = 0, framed = false;
  let pendingCandidate = null;
  const money = n => Number.isSafeInteger(n) ? n.toLocaleString("ko-KR") + "원" : "미확인";
  const rateDate = window.HS2PreviewRateDate;
  const isDemo = document.body.dataset.hs2Demo === "seongsu";
  const presentation = (row) => rateDate && isDemo
    ? rateDate.basePresentation(row.stay_kind || row.preview_demo?.category,
      row.base_rates, row.quote, byId("check_in").value, byId("check_out").value) : null;
  const compactMoney = n => {
    if (!Number.isSafeInteger(n)) return "미확인";
    const unit = n >= 100000000 ? 100000000 : 10000;
    return (n / unit).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + (unit === 10000 ? "만원" : "억");
  };
  const text = (tag, className, value) => {
    const node = document.createElement(tag); node.className = className; node.textContent = value; return node;
  };
  function setSyntheticPhoto(image, meta) {
    if (!isDemo) {
      if (Array.isArray(meta?.photos) && typeof meta.photos[0] === "string") image.src = meta.photos[0];
      image.alt = "가상 공간 이미지";
      return;
    }
    const photo = Array.isArray(meta?.photos) ? meta.photos[0] : "";
    if (typeof photo === "string" && photo.startsWith("/__development__/seongsu/assets/") &&
        !photo.split("/").includes("..")) {
      image.src = photo; image.alt = "가상 공간 이미지";
    } else image.alt = "가상 이미지를 제공하지 않음";
  }
  function notice(message) { byId("statusMessage").textContent = message; }
  function poiCategories(type) {
    return type === "education" ? [["SC4", "학교"], ["AC5", "학원"]]
      : type === "convenience" ? [["CS2", "편의점"], ["HP8", "병원"], ["PM9", "약국"], ["PK6", "주차장"]]
      : [["SW8", "지하철역"]];
  }
  async function places(type, lat, lng, signal) {
    if (!window.kakao?.maps?.services) throw new Error("실제 카카오 장소 SDK가 연결되지 않았습니다.");
    const client = new kakao.maps.services.Places();
    const groups = await Promise.all(poiCategories(type).map(([code, label]) => new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(new DOMException("Cancelled", "AbortError"));
      client.categorySearch(code, (rows, status) => {
        if (signal?.aborted) return reject(new DOMException("Cancelled", "AbortError"));
        if (status === kakao.maps.services.Status.ZERO_RESULT) return resolve([]);
        if (status !== kakao.maps.services.Status.OK) return reject(new Error("실제 장소 조회 실패"));
        resolve(rows.map(row => ({ id: row.id, name: row.place_name,
          category: label, category_label: label, lat: Number(row.y), lng: Number(row.x),
          address: row.road_address_name || row.address_name, url: row.place_url })));
      }, { location: new kakao.maps.LatLng(lat, lng), radius: 1500, size: 15 });
    })));
    return [...new Map(groups.flat().map(row => [row.id, row])).values()];
  }
  // Keep the original _loadPoi tool and its API shape; the owned shell adapts
  // only the transport to read-only browser Places SDK, using identical categories.
  // No REST key, production backend/database or arbitrary URL proxy is provided.
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.origin);
    if (url.origin === location.origin && url.pathname === "/api/v1/m/6b4") {
      const type = url.searchParams.get("type");
      if (!["education", "convenience"].includes(type)) return new Response("{}", { status: 400 });
      try {
        const data = await places(type, Number(url.searchParams.get("lat")), Number(url.searchParams.get("lng")), options.signal);
        return Response.json({ ok: true, items: data });
      } catch (error) {
        if (error.name === "AbortError") throw error;
        return Response.json({ ok: false, message: error.message }, { status: 503 });
      }
    }
    if (url.origin === location.origin && url.pathname === "/api/tourism/attractions/top20") {
      notice("관광 데이터랩 원장은 격리 Preview에 연결하지 않았습니다. 지도·주변 시설은 실제 카카오 조회입니다.");
      return Response.json({ ok: false, message: "Preview 관광 원장 미연결" }, { status: 503 });
    }
    return originalFetch(input, options);
  };
  function getFilters() {
    const params = new URLSearchParams();
    for (const key of ["q", "check_in", "check_out", "guests", "min_area", "rooms", "kind", "min_total", "max_total"]) {
      const el = byId(key); if (el?.value) params.set(key, el.value);
    }
    const options = [...document.querySelectorAll('input[name="options"]:checked')].map(el => el.value);
    if (options.length) params.set("options", options.join(","));
    params.set("layers", [...active].join(","));
    if (byId("sort").value === "price_asc") params.set("sort", "total_asc");
    else if (isDemo && ["price_desc", "area_desc"].includes(byId("sort").value))
      params.set("sort", byId("sort").value);
    return params;
  }
  function syncAddress() {
    if (!isDemo) return;
    const params = getFilters();
    history.replaceState(null, "", location.pathname + (params.size ? "?" + params : ""));
  }
  function rateHeadline(row) {
    const rates = row.base_rates;
    if (row.layer !== "stay" || !rates) return "기준 요금 비공개";
    if (row.stay_kind === "lodging" && rateDate?.isRate(rates.night))
      return `1박 ${rateDate.won(rates.night)}`;
    if (row.stay_kind === "non_lodging") {
      return rateDate.basePresentation(row.stay_kind, rates).headline;
    }
    return "기준 요금 비공개";
  }
  function appendCandidates(container, row) {
    if (!rateDate) return;
    if (rateDate.quoteIssue(row) !== "EXACT_PERIOD_QUOTE_UNAVAILABLE") {
      if (!presentation(row)?.quote)
        container.append(text("span", "preview-quote", "선택 기간 견적 없음"));
      return;
    }
    container.append(text("span", "preview-period-issue", "주·월 요금에 맞는 기간을 선택해 주세요"));
    const candidates = rateDate.candidateDates(row);
    if (!candidates.length) return;
    const group = text("span", "preview-candidates", "");
    candidates.forEach(date => {
      const button = text("button", "preview-candidate", date); button.type = "button";
      button.addEventListener("click", () => {
        byId("check_out").value = date;
        byId("check_out").dispatchEvent(new Event("change", { bubbles: true }));
        pendingCandidate = { publicId: row.public_id, checkOut: date };
        syncAddress(); search();
      });
      group.append(button);
    });
    container.append(group);
  }
  async function verifyMissingCandidate(payload, run) {
    if (!pendingCandidate) return;
    const candidate = pendingCandidate;
    pendingCandidate = null;
    if (payload.items.some(row => row.public_id === candidate.publicId)) return;
    try {
      const query = new URLSearchParams({ public_id: candidate.publicId,
        check_in: byId("check_in").value, check_out: candidate.checkOut });
      const response = await originalFetch("/__development__/seongsu/quote-check?" + query);
      const result = await response.json();
      if (run !== sequence) return;
      notice(result.ok === true
        ? "선택한 기간의 견적은 확인됐지만 현재 검색 조건과 맞는 목록에는 없습니다."
        : (typeof result.message === "string" ? result.message : "선택한 기간의 견적을 확인할 수 없습니다."));
    } catch (_) { notice("선택한 기간의 견적 확인에 실패했습니다. 검색 조건을 다시 확인해 주세요."); }
  }
  function appendDateHelpers() {
    if (!isDemo || !rateDate) return;
    const form = byId("searchForm"), row = form.querySelector(".search-primary-row");
    const helper = text("div", "preview-date-helpers", "");
    helper.setAttribute("aria-label", "빠른 기간 선택"); helper.id = "previewDateHelpers";
    row.after(helper);
    const kind = byId("kind");
    const render = () => {
      helper.replaceChildren();
      for (const [value, label] of [["all", "전체"], ["lodging", "숙박형"], ["non_lodging", "주·월형"]]) {
        const tab = text("button", "preview-kind-tab", label); tab.type = "button";
        tab.setAttribute("aria-pressed", String(kind.value === value));
        tab.addEventListener("click", () => {
          if (kind.value === value) return;
          kind.value = value; kind.dispatchEvent(new Event("change"));
        });
        helper.append(tab);
      }
      helper.append(text("span", "preview-date-label", "기간"));
      rateDate.quickPeriods(kind.value === "non_lodging" ? "non_lodging" : "lodging").forEach(period => {
        const button = text("button", "preview-date-button", period.label); button.type = "button";
        button.addEventListener("click", () => {
          if (!byId("check_in").value) return;
          byId("check_out").value = rateDate.checkoutFor(byId("check_in").value, period);
          syncAddress(); search();
        });
        helper.append(button);
      });
    };
    form.addEventListener("preview-restore", render);
    render();
    kind.addEventListener("change", () => {
      if (kind.value === "non_lodging" && byId("check_in").value)
        byId("check_out").value = rateDate.addDays(byId("check_in").value, 7);
      render(); syncAddress(); search();
    });
  }
  function previewStatus(payload) {
    if (!isDemo) return;
    const bar = byId("statusMessage");
    const hiddenCount = Number.isSafeInteger(payload.period_hidden_count) && payload.period_hidden_count > 0
      ? payload.period_hidden_count : 0;
    if (!hiddenCount) { bar.querySelector(".preview-period-hidden")?.remove(); return; }
    let note = bar.querySelector(".preview-period-hidden");
    if (!note) { note = text("span", "preview-period-hidden", ""); bar.append(note); }
    note.replaceChildren();
    note.append(document.createTextNode(`주·월형 ${hiddenCount}개는 7일 이상 선택 시 표시됩니다`));
    if (hiddenCount) {
      const button = text("button", "preview-week-toggle", "1주로 보기"); button.type = "button";
      button.addEventListener("click", () => {
        byId("kind").value = "non_lodging";
        byId("kind").dispatchEvent(new Event("change", { bubbles: true }));
      });
      note.append(button);
    }
    note.hidden = !hiddenCount;
  }
  function price(row) {
    if (isDemo && row.layer === "stay" && rateDate) {
      const view = presentation(row);
      if (view?.quote) return view.quote.text;
      return rateHeadline(row);
    }
    const meta = row.preview_demo;
    if (row.layer === "stay") return row.quote ? money(row.quote.total_krw) + " / 선택기간"
      : meta.calendar_setup_required ? "달력·요금 확인 필요"
      : meta.category === "non_lodging" ? money(meta.weekly_krw) + "/주"
      : money(meta.nightly_krw) + "/박";
    const basis = row.layer === "auction" ? "가상 최저가" : row.layer === "business" ? "가상 양도금액" : "가상 매매가";
    return basis + " " + money(meta.test_asking_krw);
  }
  function detailHref(row) {
    const query = new URLSearchParams({ public_id: row.public_id, restoredReturn: location.pathname });
    for (const k of ["check_in", "check_out", "guests"]) if (byId(k).value) query.set(k, byId(k).value);
    return "/hs2/details/?" + query;
  }
  function select(row) {
    selected = row.public_id;
    const meta = row.preview_demo, detail = byId("selectedDetail").querySelector(".detail-content");
    detail.replaceChildren();
    const image = new Image();
    setSyntheticPhoto(image, meta);
    detail.append(image, text("span", "detail-type", names[row.layer] === "단기임대"
        ? (row.stay_kind === "lodging" ? "숙박형 단기임대" : "주·월 단기임대") : names[row.layer]),
      text("h2", "", meta.name), text("p", "", meta.description),
      text("p", "detail-facts", `${meta.area_m2}㎡${meta.guests ? " · 최대 " + meta.guests + "명" : ""}`),
      text("p", "detail-price", isDemo && row.layer === "stay" ? rateHeadline(row) : price(row)));
    if (isDemo && row.layer === "stay") {
      const view = presentation(row);
      if (view?.quote) detail.append(text("p", "preview-quote", view.quote.text));
      if (row.base_rate_notice) detail.append(text("p", "preview-rate-notice", row.base_rate_notice));
      if (!row.base_rates) detail.append(text("p", "preview-rate-notice", "기준 요금 비공개"));
      appendCandidates(detail, row);
    }
    detail.append(text("p", "detail-amenities", (meta.amenities || []).join(" · ")),
      text("p", "demo-warning", "테스트용 가상 물건 · 실제 위치/실재·법적 운영 확인 아님"));
    if (row.layer === "stay") {
      const link = text("a", "detail-primary", "날짜·상세·예약 조건 확인"); link.href = detailHref(row); detail.append(link);
    } else {
      const link = text("a", "detail-primary", "가상 원본 요약 확인");
      link.href = "/hs2/search/api/detail/" + row.layer + "/" + row.public_id + "?layers=" + row.layer;
      link.target = "_blank"; link.rel = "noopener"; detail.append(link);
      detail.append(text("p", "", "이 예시는 실제 계약·양도·입찰로 진행되지 않습니다."));
    }
    byId("selectedDetail").hidden = false; byId("listingList").hidden = true; byId("detailBack").hidden = false;
    byId("resultsPane").closest(".map-workspace").classList.remove("results-collapsed");
    byId("panelToggle").setAttribute("aria-expanded", "true");
    document.querySelectorAll("[data-public-id]").forEach(el => {
      el.classList.toggle("is-selected", el.dataset.publicId === selected);
      el.setAttribute("aria-pressed", String(el.dataset.publicId === selected));
    });
    if (map) map.panTo(new kakao.maps.LatLng(meta.point.lat, meta.point.lng));
    notice(`${meta.name} 선택 · 실제 지도 위 테스트용 가상 좌표입니다.`);
  }
  function renderCards() {
    const list = byId("listingList"); list.replaceChildren();
    for (const row of items) {
      const meta = row.preview_demo;
      if (meta?.synthetic !== true) throw new Error("가상 데이터 외에는 표시하지 않습니다.");
      const card = text("button", "listing-card", ""); card.type = "button";
      card.dataset.publicId = row.public_id; card.dataset.layer = row.layer;
      const image = new Image(); setSyntheticPhoto(image, meta); image.loading = "lazy";
      const copy = text("span", "listing-card-copy", "");
      const tag = text("span", "listing-type", names[row.layer]); tag.style.color = colors[row.layer];
      if (isDemo && row.layer === "stay") tag.textContent =
        row.stay_kind === "lodging" ? "숙박형 단기임대" : "주·월 단기임대";
      copy.append(tag, text("strong", "listing-title", meta.name), text("span", "listing-meta",
        `${meta.neighborhood} · ${meta.area_m2}㎡${meta.guests ? " · 최대 " + meta.guests + "명" : ""}`),
        text("span", "listing-price", isDemo && row.layer === "stay" ? rateHeadline(row) : price(row)));
      const wrapper = isDemo && row.layer === "stay" ? text("div", "preview-map-card", "") : null;
      if (wrapper) wrapper.append(card);
      if (isDemo && row.layer === "stay") {
        const view = presentation(row);
        if (view?.quote) wrapper.append(text("span", "preview-quote", view.quote.text));
        else appendCandidates(wrapper, row);
        if (row.base_rate_notice) wrapper.append(text("span", "preview-rate-notice", row.base_rate_notice));
        if (!row.base_rates) wrapper.append(text("span", "preview-rate-notice", "기준 요금 비공개"));
      }
      copy.append(text("span", "demo-warning", "테스트용 가상 매물 · 가상 이미지"));
      card.append(image, copy); card.addEventListener("click", () => select(row));
      list.append(wrapper || card);
    }
    byId("resultCount").textContent = items.length + "개";
    for (const layer of Object.keys(names)) document.querySelector(`[data-layer-count="${layer}"]`).textContent =
      items.filter(row => row.layer === layer).length;
    if (!items.length) list.append(text("p", "", "선택 조건에 해당하는 가상 물건이 없습니다."));
  }
  function renderMarkers() {
    overlays.forEach(overlay => overlay.setMap(null)); overlays = [];
    if (!map) return;
    if (!framed && items.length) {
      const bounds = new kakao.maps.LatLngBounds();
      items.forEach(row => bounds.extend(new kakao.maps.LatLng(
        row.preview_demo.point.lat, row.preview_demo.point.lng)));
      map.setBounds(bounds, 40, 90, 35, window.innerWidth > 760 ? 450 : 35);
      framed = true;
    }
    for (const row of items) {
      const p = row.preview_demo.point;
      let bubble = compactMoney(row.preview_demo.test_asking_krw);
      if (isDemo && row.layer === "stay") {
        const rates = row.base_rates;
        bubble = row.stay_kind === "lodging" && rateDate?.isRate(rates?.night)
          ? `${rateDate.won(rates.night)}/박`
          : row.stay_kind === "non_lodging" && rateDate?.isRate(rates?.week)
            ? `${rateDate.won(rates.week)}/주`
            : row.stay_kind === "non_lodging" && rateDate?.isRate(rates?.month)
              ? `${rateDate.won(rates.month)}/월` : "기준 요금 비공개";
      } else if (row.layer === "stay") {
        const amount = row.quote?.total_krw ?? row.preview_demo.weekly_krw ?? row.preview_demo.nightly_krw;
        bubble = compactMoney(amount);
      }
      const content = text("button", "real-map-marker", bubble);
      content.type = "button"; content.style.background = colors[row.layer];
      content.title = `${row.preview_demo.name} · ${names[row.layer]} · ${
        isDemo && row.layer === "stay" ? rateHeadline(row) : price(row)} · 가상 물건`;
      content.dataset.publicId = row.public_id; content.dataset.layer = row.layer;
      content.setAttribute("aria-label", row.preview_demo.name + " 지도에서 선택");
      content.addEventListener("click", () => select(row));
      const overlay = new kakao.maps.CustomOverlay({ position: new kakao.maps.LatLng(p.lat, p.lng),
        content, map, yAnchor: 1.2, zIndex: 10 });
      overlays.push(overlay);
    }
    byId("mapStatus").textContent = "기존 카카오 지도 · 가상 물건 " + overlays.length + "개";
  }
  async function search() {
    const run = ++sequence;
    byId("searchForm").setAttribute("aria-busy", "true");
    try {
      const response = await originalFetch("/hs2/search/api/results?" + getFilters());
      const payload = await response.json();
      if (run !== sequence) return;
      if (!response.ok || !payload.ok) throw new Error("검색 조건 또는 원장 조회 오류");
      items = payload.items;
      if (byId("sort").value === "area_desc") items.sort((a, b) => b.preview_demo.area_m2 - a.preview_demo.area_m2);
      if (byId("sort").value === "price_desc") items.sort((a, b) => (b.quote?.total_krw || 0) - (a.quote?.total_krw || 0));
      byId("selectedDetail").hidden = true; byId("listingList").hidden = false; byId("detailBack").hidden = true;
      renderCards(); renderMarkers();
      notice("실제 지도 위 성수동 가상 매물입니다. 실제 소유자·연락처·운영 확인 정보가 아닙니다.");
      await verifyMissingCandidate(payload, run);
      previewStatus(payload);
    } catch (error) {
      notice(error.message);
      await verifyMissingCandidate({ items: [] }, run);
    } finally {
      if (run === sequence) byId("searchForm").setAttribute("aria-busy", "false");
    }
  }
  function mapError(message) {
    byId("mapError").hidden = false; byId("mapError").textContent = message;
    byId("mapStatus").textContent = "실제 지도 연결 확인 필요 · 대체 지도 없음";
    document.querySelectorAll(".map-tool-btn, #subwayTool").forEach(el => { el.disabled = true; });
  }
  function initializeMap() {
    if (!window.kakao?.maps?.load) {
      mapError("기존 카카오 지도 SDK를 불러오지 못했습니다. 개발 도메인 등록·키 설정·브라우저 네트워크를 확인하세요. 가상 지도는 사용하지 않습니다.");
      return;
    }
    setTimeout(() => {
      if (!map) mapError("카카오 SDK 초기 리소스/CDN이 완료되지 않았습니다. 브라우저 차단·네트워크를 확인하세요. 대체 지도는 없습니다.");
    }, 15000);
    kakao.maps.load(() => queueMicrotask(() => {
      try {
        map = new kakao.maps.Map(byId("mapCanvas"), { center: new kakao.maps.LatLng(37.5448, 127.0526), level: 5 });
        window.HS2LegacyMapTools.mount(map);
        map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.BOTTOMRIGHT);
        byId("mapError").hidden = true;
        document.querySelectorAll(".map-tool-btn, #subwayTool").forEach(el => { el.disabled = false; });
        renderMarkers();
        window.addEventListener("resize", () => map.relayout());
      } catch (_) { mapError("실제 지도 초기화 실패: 기존 SDK 기능/네트워크를 확인하세요. 다른 지도로 대체하지 않습니다."); }
    }));
  }
  const now = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const tomorrow = new Date(now + "T00:00:00Z"); tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  byId("check_in").value = tomorrow.toISOString().slice(0, 10); tomorrow.setUTCDate(tomorrow.getUTCDate() + 7);
  byId("check_out").value = tomorrow.toISOString().slice(0, 10);
  const args = new URLSearchParams(location.search);
  if (args.has("layers")) {
    active.clear();
    args.get("layers").split(",").filter(layer => Object.hasOwn(names, layer)).forEach(layer => active.add(layer));
    document.querySelectorAll(".layer-button[data-layer]").forEach(button =>
      button.setAttribute("aria-pressed", String(active.has(button.dataset.layer))));
  }
  const restoreKeys = isDemo
    ? ["q", "check_in", "check_out", "guests", "min_area", "rooms", "kind", "min_total", "max_total"]
    : ["q", "check_in", "check_out", "guests"];
  for (const key of restoreKeys)
    if (args.has(key)) byId(key).value = args.get(key);
  if (isDemo && args.has("options")) {
    const selectedOptions = args.get("options").split(",");
    document.querySelectorAll('input[name="options"]').forEach(el => { el.checked = selectedOptions.includes(el.value); });
  }
  if (isDemo && args.get("sort") === "total_asc") byId("sort").value = "price_asc";
  if (isDemo && args.has("sort") && args.get("sort") !== "total_asc") byId("sort").value = args.get("sort");
  byId("searchForm").addEventListener("submit", event => { event.preventDefault(); syncAddress(); search(); });
  if (isDemo) {
    for (const id of ["q", "check_in", "check_out", "guests", "min_area", "rooms", "kind", "min_total", "max_total", "sort"])
      byId(id)?.addEventListener("change", syncAddress);
    document.querySelectorAll('input[name="options"]').forEach(el => el.addEventListener("change", syncAddress));
  }
  appendDateHelpers();
  if (isDemo) window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    for (const key of ["q", "check_in", "check_out", "guests", "min_area", "rooms", "kind", "min_total", "max_total"])
      if (params.has(key)) byId(key).value = params.get(key);
      else if (byId(key)) byId(key).value = key === "kind" ? "all" : "";
    if (!byId("check_in").value) byId("check_in").value = rateDate.addDays(now, 1);
    if (!byId("check_out").value) byId("check_out").value = rateDate.addDays(byId("check_in").value, 7);
    byId("sort").value = params.get("sort") === "total_asc" ? "price_asc" : params.get("sort") || "recommended";
    byId("searchForm").dispatchEvent(new Event("preview-restore"));
    const options = (params.get("options") || "").split(",");
    document.querySelectorAll('input[name="options"]').forEach(el => { el.checked = options.includes(el.value); });
    active.clear();
    (params.has("layers") ? params.get("layers").split(",") : Object.keys(names))
      .filter(layer => Object.hasOwn(names, layer)).forEach(layer => active.add(layer));
    document.querySelectorAll(".layer-button[data-layer]").forEach(button =>
      button.setAttribute("aria-pressed", String(active.has(button.dataset.layer))));
    byId("sort").value = params.get("sort") === "total_asc" ? "price_asc" :
      ["price_desc", "area_desc"].includes(params.get("sort")) ? params.get("sort") : "recommended";
    search();
  });
  const filterRow = document.querySelector(".search-filter-row");
   let filterGroup = filterRow.closest("details.mobile-filter-group");
   if (!filterGroup) {
     filterGroup = document.createElement("details");
     filterGroup.className = "mobile-filter-group";
     filterGroup.append(text("summary", "", "면적·편의시설·가격 필터"));
     filterRow.before(filterGroup); filterGroup.append(filterRow);
   }
   filterGroup.open = innerWidth > 760;
  window.addEventListener("resize", () => { filterGroup.open = innerWidth > 760; });
  const rail = document.createElement("aside");
  rail.className = "map-tool-rail"; rail.setAttribute("aria-label", "매물 유형과 기존 지도 도구");
  byId("mapCanvas").parentElement.append(rail);
  for (const el of [document.querySelector(".layer-tools"), byId("subwayTool"), byId("mapToolbar")])
    rail.append(el);
   // Original floating panels must not inherit the narrow scrolling rail's
   // clipping. Their handlers still own the same DOM IDs and controls.
   for (const id of ["measurePanel", "roadviewPanel"]) {
     const panel = byId(id);
     if (panel) byId("mapCanvas").parentElement.append(panel);
   }
  const layerIcons = {stay: "home", sale: "building", business: "storeIcon", auction: "gavel"};
  document.querySelectorAll(".layer-button[data-layer]").forEach(button => {
    const icon = window.Icons?.[layerIcons[button.dataset.layer]] || window.Icons?.home;
    const marker = button.querySelector(".layer-mark");
    button.style.color = colors[button.dataset.layer];
    if (icon) marker.innerHTML = icon(20);
    if (button.dataset.layer === "stay") button.querySelector(".layer-name").textContent = "단기임대";
  });
  document.querySelectorAll("[data-layer]").forEach(button => {
    if (!button.classList.contains("layer-button")) return;
    button.addEventListener("click", () => {
      const layer = button.dataset.layer; active.has(layer) ? active.delete(layer) : active.add(layer);
      button.setAttribute("aria-pressed", String(active.has(layer))); syncAddress(); search();
    });
  });
  byId("detailBack").addEventListener("click", () => {
    byId("selectedDetail").hidden = true; byId("listingList").hidden = false; byId("detailBack").hidden = true;
  });
  byId("panelToggle").addEventListener("click", () => {
    const collapsed = byId("resultsPane").closest(".map-workspace").classList.toggle("results-collapsed");
    byId("panelToggle").setAttribute("aria-expanded", String(!collapsed));
    if (map) queueMicrotask(() => map.relayout());
  });
  byId("subwayTool").addEventListener("click", async () => {
    const button = byId("subwayTool"), run = ++subwaySequence;
    stationOverlays.forEach(o => o.setMap(null)); stationOverlays = [];
    if (button.getAttribute("aria-pressed") === "true") { button.setAttribute("aria-pressed", "false"); return; }
    button.setAttribute("aria-pressed", "true");
    try {
      const center = map.getCenter(), rows = await places("subway", center.getLat(), center.getLng());
      if (run !== subwaySequence) return;
      rows.forEach(row => stationOverlays.push(new kakao.maps.CustomOverlay({ map,
        position: new kakao.maps.LatLng(row.lat, row.lng),
        content: text("span", "real-station-marker", row.name), zIndex: 15 })));
      notice("실제 카카오 주변 지하철역 " + rows.length + "개 (노선도 대체 아님)");
    } catch (_) { button.setAttribute("aria-pressed", "false"); notice("실제 지하철역 조회 실패 · 네트워크를 확인하세요."); }
  });
  // Resize from the actual owned notice, not a fixed imagined warning height.
  const banner = document.querySelector('aside[role="note"]');
  if (banner) {
    const update = () => document.documentElement.style.setProperty("--warning-banner-height", banner.getBoundingClientRect().height + "px");
    new ResizeObserver(update).observe(banner); update();
  }
  window.HS2PreviewMap = { state: () => ({ provider: "existing_kakao_maps", ready: !!map,
    markers: overlays.length, layers: [...active], selected, stations: stationOverlays.length }),
    map: () => map };
  search(); initializeMap();
})();
