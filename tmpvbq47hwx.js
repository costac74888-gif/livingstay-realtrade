
(function(){
  "use strict";

  // ── 유틸 ──────────────────────────────────────────────────────────────
  function esc(s){ const d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; }
  function fmtN(v){ return v != null ? Number(v).toLocaleString() : "-"; }
  function formatKrw(v){ return v != null && Number.isFinite(Number(v)) ? fmtN(Math.round(Number(v))) + "만원" : "-"; }
  function fmtPrice(deal_type, price_krw, monthly_rent_krw, price_krw_max){
    if (typeof window.formatLrPrice === "function")
      return window.formatLrPrice(deal_type, price_krw, monthly_rent_krw, price_krw_max);
    if (deal_type === "매매" || deal_type === "전세") {
      return (price_krw_max != null ? fmtN(price_krw) + " ~ " + fmtN(price_krw_max) : fmtN(price_krw)) + "만원";
    }
    if (deal_type === "월세") return price_krw_max != null ? fmtN(price_krw) + " ~ " + fmtN(price_krw_max) + "만원" : "보" + fmtN(price_krw) + "/" + fmtN(monthly_rent_krw) + "만";
    if (deal_type === "단기임대") return price_krw != null ? fmtN(price_krw) + (price_krw_max != null ? " ~ " + fmtN(price_krw_max) : "") + "만원" : "-";
    return "-";
  }
  function businessStayPriceText(item){
    if (item.room_price_min != null && item.room_price_max != null) {
      return "장기임대 가능 · " + fmtN(item.room_price_min) + "~" +
        fmtN(item.room_price_max) + "만원/월";
    }
    return "현재 문의 가능 여부는 채팅으로 확인해주세요";
  }
  function listingPriceText(item){
    if (item.transaction_target === "whole" || item.is_whole_listing) {
      if (item.deal_type === "매매") return item.price_krw != null ? "매매가 " + fmtN(item.price_krw) + "만원" : "매매 조건 협의";
      var lease = item.price_krw != null ? "보증금 " + fmtN(item.price_krw) + "만원" : "조건 협의";
      return item.monthly_rent_krw != null ? lease + " / 월 " + fmtN(item.monthly_rent_krw) + "만원" : lease;
    }
    return item.is_business_listing
      ? businessStayPriceText(item)
      : fmtPrice(item.deal_type, item.price_krw, item.monthly_rent_krw, item.price_krw_max);
  }
  function operationStatusText(item){
    if (!(item.is_whole_listing || item.transaction_target === "whole") || !item.operation_status) return "";
    const icon = item.operation_status === "영업중" ? "🟢" : (item.operation_status === "휴업" ? "🟡" : "⚫");
    const closedDate = item.operation_status === "폐업" && (item.closed_at || item.closed_date)
      ? "(" + (item.closed_at || item.closed_date) + ")" : "";
    return "영업상태: " + icon + item.operation_status + closedDate;
  }
  function operationStatusHtml(item){
    const text = operationStatusText(item);
    if (!text) return "";
    const color = item.operation_status === "폐업" ? "#222" : (item.operation_status === "휴업" ? "#A06D18" : "#4A7A18");
    return `<span style="display:inline-block;margin-top:4px;color:${color};font-size:11.5px;font-weight:700;">${esc(text)}</span>`;
  }
  function permitBadgeHtml(item){
    if (!item || !item.permit_number_masked) return "";
    return `<span title="인증된 숙박업 신고번호의 일부를 마스킹해 표시합니다." style="display:inline-block;margin-left:5px;padding:1px 5px;border-radius:4px;background:#EDF6EC;color:#356212;font-size:10px;font-weight:800;vertical-align:middle;white-space:nowrap;">신고 ${esc(item.permit_number_masked)}</span>`;
  }
  function urgentBadgeHtml(item){
    if (!item || item.urgent_tier !== "urgent") return "";
    const urgentTitle = item.is_urgent
      ? "판매자가 급매로 등록한 매물"
      : "최신 실거래가보다 낮은 매물";
    return `<span class="urgent-tier-badge" title="${urgentTitle}" style="display:inline-block;padding:2px 7px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;letter-spacing:0.3px;">급매</span>`;
  }
  function operationRatioBadgesHtml(item){
    const badges = [];
    if (item && item.short_stay_ratio != null) badges.push(`대실 ${Number(item.short_stay_ratio).toLocaleString()}%`);
    if (item && item.ota_revenue_ratio != null) badges.push(`OTA ${Number(item.ota_revenue_ratio).toLocaleString()}%`);
    return badges.map(label => `<span style="display:inline-block;margin:4px 4px 0 0;padding:1px 5px;border-radius:4px;background:#EEF5FF;color:#275B88;font-size:10px;font-weight:800;">${esc(label)}</span>`).join("");
  }

  // ── 상태 ──────────────────────────────────────────────────────────────
  const boardBody = document.getElementById("lsBoardBody");
  const cardGrid  = document.getElementById("lsCardGrid");
  const moreBtn   = document.getElementById("listingsMore");
  const countEl   = document.getElementById("lsTotalCount");
  function lodgingLabel(raw, subtype){ return window.LodgingTypes.badge(raw, subtype); }
  function lodgeBadgeHtml(raw, subtype){
    const lbl = lodgingLabel(raw, subtype);
    const col = window.LodgingTypes.color(raw);
    return `<span style="display:inline-block;font-size:10px;font-weight:700;color:#fff;background:${col};padding:1px 6px;border-radius:4px;margin-right:5px;white-space:nowrap;vertical-align:middle;">${esc(lbl)}</span>`;
  }
   const DEAL_TYPE_COLORS = { "매매":"#C85A36", "전세":"#378ADD", "월세":"#639922", "단기임대":"#8B6BB1" };
   function dealTypeBadgeHtml(raw){
     const label = raw || "-";
     const col = DEAL_TYPE_COLORS[label] || "#7B8794";
     return `<span class="ls-deal-type-badge" style="background:${col};">${esc(label)}</span>`;
   }

  const requestedDisclosureScope = new URLSearchParams(location.search).get("disclosure_scope");
  const state = {
    sido:"", sgg_nm:"", umd_nm:"", q:"", deal_type:"", date_range:"", lodging_type:"",
    disclosure_scope: requestedDisclosureScope === "limited" ? "limited" : "public",
    urgent_only: false
  };
  let offset = 0;
  const PAGE = 20;
  let loading = false;
  let totalLoaded = 0;

  let myChattingIds = new Set();
  let chatFilterId  = null;
  let boardSortKey = null;
  let boardSortDirection = "asc";

  // ── 뷰 전환 ────────────────────────────────────────────────────────────
  const STORAGE_KEY = "listingsViewMode";
  const isMobile = window.matchMedia("(max-width: 520px)").matches;
  let currentView = localStorage.getItem(STORAGE_KEY)
    || (isMobile ? "card" : "board");

  function setView(mode){
    currentView = mode;
    localStorage.setItem(STORAGE_KEY, mode);
    document.body.classList.remove("view-board", "view-card");
    document.body.classList.add("view-" + mode);
    // 카드형일 때 grid 복원 (초기 display:none 덮어씀)
    if (mode === "card") cardGrid.style.display = "";
    else cardGrid.style.display = "none";
    document.querySelectorAll(".ls-view-tabs button[data-view]").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.view === mode);
    });
  }

  document.querySelectorAll(".ls-view-tabs button[data-view]").forEach(btn => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  const urgentToggle = document.getElementById("lsUrgentToggle");
  urgentToggle.addEventListener("click", () => {
    state.urgent_only = !state.urgent_only;
    urgentToggle.classList.toggle("active", state.urgent_only);
    urgentToggle.setAttribute("aria-pressed", state.urgent_only ? "true" : "false");
    loadListings(true);
  });
  document.querySelectorAll("[data-disclosure-scope]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.disclosure_scope = btn.dataset.disclosureScope;
      chatFilterId = null;
      document.querySelectorAll("[data-disclosure-scope]").forEach(other => {
        const active = other === btn;
        other.classList.toggle("active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      });
      loadListings(true);
    });
  });
  document.querySelectorAll("[data-disclosure-scope]").forEach(btn => {
    const active = btn.dataset.disclosureScope === state.disclosure_scope;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });

  function sortBoardRows(){
    if (!boardSortKey) return;
    const rows = Array.from(boardBody.querySelectorAll("tr[data-listing-id]"));
    const keyName = "sort" + boardSortKey.charAt(0).toUpperCase() + boardSortKey.slice(1);
    const numericKeys = new Set(["price", "yield", "area"]);
    rows.sort((a, b) => {
      const av = a.dataset[keyName] || "";
      const bv = b.dataset[keyName] || "";
      const aMissing = av === "";
      const bMissing = bv === "";
      if (aMissing || bMissing) return aMissing === bMissing ? 0 : (aMissing ? 1 : -1);
      let result;
      if (numericKeys.has(boardSortKey)){
        result = Number(av) - Number(bv);
      } else {
        result = av.localeCompare(bv, "ko");
      }
      return boardSortDirection === "asc" ? result : -result;
    });
    rows.forEach(row => boardBody.appendChild(row));
  }

  document.querySelectorAll(".ls-sort-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const nextKey = btn.dataset.sort;
      if (boardSortKey === nextKey) boardSortDirection = boardSortDirection === "asc" ? "desc" : "asc";
      else {
        boardSortKey = nextKey;
        boardSortDirection = "asc";
      }
      document.querySelectorAll(".ls-sort-btn").forEach(other => {
        const active = other === btn;
        other.classList.toggle("is-active", active);
        other.querySelector(".ls-sort-arrow").textContent = active ? (boardSortDirection === "asc" ? "↑" : "↓") : "↕";
        other.closest("th").setAttribute("aria-sort", active ? (boardSortDirection === "asc" ? "ascending" : "descending") : "none");
      });
      sortBoardRows();
    });
  });

  // 초기 뷰 적용
  setView(currentView);

  // ── 공유 ────────────────────────────────────────────────────────────────
  let _toastTimer = null;
  function showToast(msg){
    const el = document.getElementById("lsShareToast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
  }

  function copyShareUrl(url, message){
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(url).then(
        () => showToast(message || "매물 링크가 복사되었습니다"),
        () => window.prompt("아래 매물 링크를 복사하세요:", url)
      );
    }
    window.prompt("아래 매물 링크를 복사하세요:", url);
    return Promise.resolve();
  }

  function shareItem(item){
    let url;
    try {
      const configuredOrigin = String(window.LIVINGSTAY_PUBLIC_BASE_URL || "").trim();
      const shareOrigin = (/^https?:\/\//i.test(configuredOrigin) ? configuredOrigin : location.origin).replace(/\/+$/, "");
      const shareUrl = item.is_limited_listing
        ? new URL("/listings", shareOrigin)
        : new URL(`/building/${encodeURIComponent(item.building_id)}`, shareOrigin);
      shareUrl.searchParams.set("listing", String(item.id));
      if (item.is_limited_listing) shareUrl.searchParams.set("disclosure_scope", "limited");
      url = shareUrl.toString();
    } catch (error) {
      showToast("공유 링크를 만들지 못했습니다");
      return;
    }
    const title = item.building_name || "직거래 매물";
    const text  = `직거래 매물 - ${item.deal_type || ""} ${listingPriceText(item)}`;
    const isMobileShare = !!navigator.share && window.matchMedia("(pointer: coarse)").matches;
    if (!isMobileShare) {
      copyShareUrl(url);
      return;
    }
    showToast("공유창을 여는 중입니다");
    navigator.share({ title, text, url }).then(
      () => showToast("공유가 완료되었습니다"),
      (error) => {
        if (error && error.name === "AbortError") {
          showToast("공유를 취소했습니다");
          return;
        }
        copyShareUrl(url, "공유창을 열지 못해 링크를 복사했습니다");
      }
    );
  }

  // ── 지역 드롭다운 ───────────────────────────────────────────────────
  let regionTree = {};

  async function loadRegions(){
    try {
      const res = await fetch("/api/regions");
      regionTree = await res.json();
    } catch(e){ return; }
    const selSiDo = document.getElementById("lsSido");
    selSiDo.innerHTML = '<option value="">전체</option>' +
      Object.keys(regionTree).sort().map(sd =>
        `<option value="${esc(sd)}">${esc(sd)}</option>`
      ).join("");
  }

  function refreshSggOptions(){
    const selSgg = document.getElementById("lsSggNm");
    const selUmd = document.getElementById("lsUmdNm");
    const sd = document.getElementById("lsSido").value;
    if (!sd || !regionTree[sd]){
      selSgg.innerHTML = '<option value="">전체</option>';
      selUmd.innerHTML = '<option value="">전체</option>';
      return;
    }
    const sggMap = regionTree[sd].sgg;
    selSgg.innerHTML = '<option value="">전체</option>' +
      Object.keys(sggMap).sort().map(sg =>
        `<option value="${esc(sg)}">${esc(sg)}</option>`
      ).join("");
    selUmd.innerHTML = '<option value="">전체</option>';
  }

  function refreshUmdOptions(){
    const selUmd = document.getElementById("lsUmdNm");
    const sd  = document.getElementById("lsSido").value;
    const sg  = document.getElementById("lsSggNm").value;
    const sgg = regionTree[sd] && regionTree[sd].sgg[sg];
    if (!sgg){ selUmd.innerHTML = '<option value="">전체</option>'; return; }
    selUmd.innerHTML = '<option value="">전체</option>' +
      Object.keys(sgg.umd).sort().map(um =>
        `<option value="${esc(um)}">${esc(um)}</option>`
      ).join("");
  }

  document.getElementById("lsSido").addEventListener("change",  () => refreshSggOptions());
  document.getElementById("lsSggNm").addEventListener("change", () => refreshUmdOptions());

  // ── 채팅중 칩 바 ────────────────────────────────────────────────────
  async function loadMyChatListings(){
    try {
      const res = await fetch("/api/chat/my-listing-ids", { credentials: "same-origin" });
      const d   = await res.json().catch(() => ({}));
      if (!d.ok || !d.items || d.items.length === 0) return;

      myChattingIds = new Set(d.items.map(it => it.listing_request_id));
      const bar   = document.getElementById("lsChatBar");
      const chips = document.getElementById("lsChatChips");
      bar.style.display = "";
      chips.innerHTML = "";

      const allChip = document.createElement("span");
      allChip.className = "fav-chip active";
      allChip.style.cursor = "pointer";
      allChip.textContent = "전체";
      allChip.addEventListener("click", () => {
        chatFilterId = null;
        chips.querySelectorAll(".fav-chip").forEach(c => c.classList.remove("active"));
        allChip.classList.add("active");
        loadListings(true);
      });
      chips.appendChild(allChip);

      d.items.forEach(it => {
        const chip = document.createElement("span");
        chip.className = "fav-chip";
        chip.style.cursor = "pointer";
        const lbl = document.createElement("span");
        lbl.className = "label";
        lbl.innerHTML = Icons.messageCircle(14) + " " + esc(it.building_name || "(건물명 없음)");
        lbl.title = "이 매물만 보기";
        lbl.addEventListener("click", () => {
          chatFilterId = it.listing_request_id;
          chips.querySelectorAll(".fav-chip").forEach(c => c.classList.remove("active"));
          chip.classList.add("active");
          loadListings(true);
        });
        chip.appendChild(lbl);
        chips.appendChild(chip);
      });
    } catch(e){ /* 비로그인 or 오류 무시 */ }
  }

  // ── 채팅방 열기 ─────────────────────────────────────────────────────
  function openChat(listingRequestId){
    return window.LivingstayChat.startListingChat(listingRequestId, function(roomId){
      window.location.href = "/mypage?openChat=" + roomId;
    });
  }

  function syncListingLikeButtons(item){
    document.querySelectorAll(`[data-listing-id="${item.id}"] .listing-like-btn`).forEach(button => {
      button.classList.toggle("is-liked", !!item.liked);
      const count = button.querySelector(".like-cnt");
      if (count) count.textContent = item.like_count || 0;
    });
  }

  function openListingDetail(item){
    if (typeof window.openListingDetailModal !== "function") return;
    window.openListingDetailModal(item, {
      onChat: () => openChat(item.id),
      onShare: () => shareItem(item),
      onLike: syncListingLikeButtons,
    });
  }
  const trackedWholeListingViews = new Set();
  const liveWholeListingViews = new Set();
  let wholeViewerRefreshTimer = null;
  async function refreshWholeListingViewCounts(){
    const ids = [...liveWholeListingViews];
    if (!ids.length) return;
    try {
      const query = ids.map(id => `listing_ids=${encodeURIComponent(id)}`).join("&");
      const res = await fetch(`/api/listings/views?${query}`, { credentials: "same-origin" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) return;
      (data.items || []).forEach(item => {
        document.querySelectorAll(`[data-listing-id="${item.id}"] .whole-viewers, [data-listing-id="${item.id}"] .b-whole-viewers`).forEach(el => {
          el.textContent = `최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명`;
        });
        document.querySelectorAll(`[data-listing-viewer-count="${item.id}"]`).forEach(el => {
          el.textContent = `최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명`;
        });
      });
    } catch (err) {}
  }
  function startWholeViewerRefresh(){
    if (wholeViewerRefreshTimer) return;
    wholeViewerRefreshTimer = setInterval(refreshWholeListingViewCounts, 15000);
  }
  async function recordWholeListingViews(items){
    const listingIds = (items || [])
      .filter(item => (item.is_whole_listing || item.transaction_target === "whole")
        && !trackedWholeListingViews.has(item.id))
      .map(item => item.id);
    if (!listingIds.length) return;
    listingIds.forEach(id => trackedWholeListingViews.add(id));
    listingIds.forEach(id => liveWholeListingViews.add(id));
    startWholeViewerRefresh();
    try {
      const res = await fetch("/api/listings/views", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ listing_ids: listingIds }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error("view record failed");
      (data.items || []).forEach(item => {
        document.querySelectorAll(`[data-listing-id="${item.id}"] .whole-viewers`).forEach(el => {
          el.textContent = `최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명`;
        });
      });
      refreshWholeListingViewCounts();
    } catch (err) {
      // 일시 네트워크 오류면 다음 목록 새로고침에서 다시 시도한다.
      listingIds.forEach(id => trackedWholeListingViews.delete(id));
    }
  }
  function wholeLocationHint(item){
    if (!(item.is_whole_listing || item.transaction_target === "whole") || item.is_limited_listing || !item.building_id) return "";
    return `<div class="whole-location-hint" data-location-building-id="${esc(item.building_id)}" style="font-size:11px;color:var(--ink-soft);">입지정보 불러오는 중…</div>`;
  }
  const wholeLocationContextCache = new Map();
  function wholeLocationText(context){
    if (!context) return "입지정보를 확인할 수 없습니다.";
    const nearby = context.nearby_lodgings || {};
    const total = Number(nearby["일반"] || 0) + Number(nearby["관광"] || 0)
      + Number(nearby["복합"] || 0) + Number(nearby["생활"] || 0);
    const subway = context.subway;
    const station = subway && (subway.station_name || subway.name);
    let text = `경쟁업소 ${total.toLocaleString()}곳`;
    if (station && subway.walk_minutes != null) text += ` · ${station}까지 도보 약 ${Number(subway.walk_minutes).toLocaleString()}분`;
    return text;
  }
  async function loadWholeLocationHints(items){
    const buildingIds = [...new Set((items || [])
      .filter(item => (item.is_whole_listing || item.transaction_target === "whole")
        && !item.is_limited_listing && item.building_id)
      .map(item => String(item.building_id)))];
    const missingIds = buildingIds.filter(id => !wholeLocationContextCache.has(id));
    if (missingIds.length) {
      try {
        const res = await fetch("/api/whole-listing-contexts", {
          method: "POST", credentials: "same-origin",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({building_ids: missingIds}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) throw new Error("location contexts failed");
        missingIds.forEach(id => wholeLocationContextCache.set(id, (data.items || {})[id] || null));
      } catch (err) {
        // 실패는 캐시하지 않아 다음 목록 로드에서 재시도할 수 있게 한다.
      }
    }
    buildingIds.forEach((buildingId) => {
      const text = wholeLocationText(wholeLocationContextCache.get(buildingId));
      document.querySelectorAll(`[data-location-building-id="${buildingId}"]`).forEach(el => {
        el.textContent = text;
      });
    });
  }

  // ── 썸네일 HTML ─────────────────────────────────────────────────────
  function thumbHtml(photoUrl, isCard, photoCount, photoSource){
    const countBadge = window.LivingstayListingIcons.photoCount(photoCount);
    const alt = photoSource ? "건물 참고사진 (매물 촬영 사진 아님)" : "매물 사진";
    if (isCard){
      return `<span class="ls-photo-frame">${photoUrl
        ? `<img src="${esc(photoUrl)}" alt="${alt}" loading="lazy" style="width:100%;height:100%;object-fit:cover;" onerror="this.parentElement.innerHTML=window.Icons.home(44)">`
        : `${Icons.home(44)}`}${countBadge}</span>`;
    }
    return `<span class="ls-photo-frame">${photoUrl
      ? `<img class="td-thumb" src="${esc(photoUrl)}" alt="${alt}" loading="lazy" onerror="this.outerHTML='<span class=td-thumb-placeholder>'+window.Icons.home(24)+'</span>'">`
      : `<span class="td-thumb-placeholder">${Icons.home(24)}</span>`}${countBadge}</span>`;
  }

  // ── NEW 뱃지 ────────────────────────────────────────────────────────
  const THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000;
  function newBadge(dateStr){
    if (!dateStr) return "";
    const ms = Date.now() - new Date(dateStr + "T00:00:00").getTime();
    if (ms < THREE_DAYS_MS)
      return `<span style="display:inline-block;font-size:9px;font-weight:800;color:#fff;background:#E03333;border-radius:3px;padding:1px 5px;margin-left:4px;vertical-align:middle;">NEW</span>`;
    return "";
  }

  // ── 게시판형 행 ─────────────────────────────────────────────────────
  function renderBoardRow(item){
    const tr = document.createElement("tr");
    tr.dataset.listingId = item.id;
    tr.dataset.sortLodging = lodgingLabel(item.lodging_type);
    tr.dataset.sortBuilding = item.building_name || "";
    tr.dataset.sortDealType = item.deal_type || "";
    tr.dataset.sortPrice = item.is_business_listing
      ? (item.room_price_min != null ? item.room_price_min : "")
      : (item.price_krw != null ? item.price_krw : "");
    tr.dataset.sortYield = item.yield_rate != null ? item.yield_rate : "";
    tr.dataset.sortArea = item.area_sqm != null ? item.area_sqm : "";
    tr.dataset.sortDate = item.listing_date || "";
    const isChatting   = myChattingIds.has(item.id);
    const chatBtnClass = "listing-chat-btn" + (isChatting ? " is-chatting" : "");
    const chatTitle    = isChatting ? "채팅 이어하기" : "문의하기";
    const isWholeListing = item.is_whole_listing || item.transaction_target === "whole";
    const sqm  = !isWholeListing && item.area_sqm ? parseFloat(item.area_sqm).toFixed(1) + "㎡" : "-";
    const yld  = item.yield_rate != null ? parseFloat(item.yield_rate).toFixed(1) + "%" : "-";
    const rooms = !item.is_whole_listing && !item.is_business_listing && item.room_count != null && Number(item.room_count) > 0
      ? " · 총 " + Number(item.room_count).toLocaleString() + "실" : "";
    const desc = item.description ? (item.description.slice(0, 20) + (item.description.length > 20 ? "…" : "")) : "";
    const bName = esc(item.building_name || "(건물명 없음)");
    const buildingLabel = item.is_limited_listing
      ? `<span class="ls-bldg-private" style="cursor:default;">${bName}</span>`
      : `<span class="ls-bldg-link" data-bid="${item.building_id || ""}" style="cursor:pointer;">${bName}${newBadge(item.listing_date)}</span>`;

    const photoCount = Array.isArray(item.photos) ? item.photos.length : 0;
    tr.innerHTML = `
      <td class="td-photo">${thumbHtml(item.photo_url, false, photoCount, item.photo_source)}</td>
      <td class="td-lodging ls-hide-mobile">${lodgeBadgeHtml(item.lodging_type, item.lodging_subtype)}</td>
      <td class="td-bldg" title="${bName}">
          ${buildingLabel}${urgentBadgeHtml(item)}${permitBadgeHtml(item)}${operationStatusHtml(item)}${operationRatioBadgesHtml(item)}
      </td>
      <td class="td-type">${dealTypeBadgeHtml(item.deal_type)}</td>
      <td class="td-price">${esc(listingPriceText(item) + rooms)}</td>
      <td class="td-yield ls-hide-mobile">${esc(yld)}</td>
      <td class="td-area ls-hide-mobile">${esc(sqm)}</td>
      <td class="td-date ls-hide-mobile">${esc(item.listing_date || "")}</td>
        <td class="td-action">
         <button type="button" class="listing-like-btn${item.liked ? " is-liked" : ""}" title="찜">${window.LivingstayListingIcons.heart(!!item.liked)}<span class="like-cnt">${item.like_count || 0}</span></button>
       </td>
       <td class="td-action">
         <button type="button" class="${chatBtnClass}" title="${chatTitle}">${window.LivingstayListingIcons.chat()}</button>
       </td>
       <td class="td-action ls-hide-mobile">
         <button type="button" class="listing-share-btn" title="링크 공유">${window.LivingstayListingIcons.share()}</button>
      </td>`;

    const photoCell = tr.querySelector(".td-photo");
    photoCell.style.cursor = "pointer";
    photoCell.title = "매물 상세 보기";
    photoCell.addEventListener("click", (e) => {
      e.stopPropagation();
      openListingDetail(item);
    });
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".listing-chat-btn, .listing-share-btn, .listing-like-btn, .ls-bldg-link")) return;
      openListingDetail(item);
    });
    tr.querySelector(".ls-bldg-link")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (item.building_id) window.location.href = `/building/${item.building_id}`;
    });
    tr.querySelector(".listing-chat-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      openChat(item.id);
    });
    tr.querySelector(".listing-like-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        const res = await fetch(`/api/listing-requests/${item.id}/like`, { method:"POST", credentials:"same-origin" });
        const d = await res.json().catch(() => ({}));
        if (res.ok && d.ok) {
          const count = e.currentTarget.querySelector(".like-cnt");
          if (count) count.textContent = d.like_count;
          e.currentTarget.classList.toggle("is-liked", !!d.liked);
          e.currentTarget.querySelector(".listing-icon")?.replaceWith(
            document.createRange().createContextualFragment(window.LivingstayListingIcons.heart(!!d.liked))
          );
        }
      } catch (err) {}
    });
    tr.querySelector(".listing-share-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      shareItem(item);
    });
    return tr;
  }

  // ── 카드형 카드 ─────────────────────────────────────────────────────
  function renderWholeListingCard(item){
    const div = document.createElement("div");
    const isLimitedListing = !!item.is_limited_listing;
    div.className = "ls-card-item whole-listing-card" + (isLimitedListing ? " is-limited" : "");
    div.dataset.listingId = item.id;
    const price = Number(item.price_krw || 0);
    const loan = Number(item.succession_loan_krw || 0);
    const keyMoney = Number(item.key_money_krw || 0);
    const hasFinance = item.financial_details_visible;
    const acquisition = price > 0 && hasFinance
      ? price - loan + keyMoney + (price * 0.061) : null;
    const recentlyClosed = item.operation_status === "폐업" && item.closed_at
      && Date.now() - new Date(item.closed_at).getTime() <= 90 * 24 * 60 * 60 * 1000;
    const badges = [
      urgentBadgeHtml(item),
      recentlyClosed ? '<span class="whole-badge whole-badge-closed">최근 폐업</span>' : "",
       item.has_monthly_revenue ? '<span class="whole-badge whole-badge-revenue">매출정보 있음</span>' : "",
       operationRatioBadgesHtml(item)
    ].filter(Boolean).join("");
    const roomPriceText = item.price_krw != null && Number(item.room_count) > 0
      && Number(item.price_krw) > 0
      ? `객실당 ${Math.round(Number(item.price_krw) / Number(item.room_count)).toLocaleString()}만원` : "";
    const roomText = item.room_count != null && Number(item.room_count) > 0
      ? `객실 ${Number(item.room_count).toLocaleString()}실${roomPriceText ? " · " + roomPriceText : ""}`
      : "객실 정보 없음";
    const parkingText = item.parking_count != null
      ? `주차 ${Number(item.parking_count).toLocaleString()}대` : "주차 정보 없음";
    const landText = item.land_area_pyeong != null
      ? `대지 ${Number(item.land_area_pyeong).toFixed(1)}평` : "대지 정보 없음";
    const grossText = item.gross_area_pyeong != null
      ? `연면적 ${Number(item.gross_area_pyeong).toFixed(1)}평` : "연면적 정보 없음";
    const financeText = hasFinance
      ? `실인수가 ${acquisition != null ? formatKrw(acquisition) : "-"} · 융자 ${item.has_succession_loan ? formatKrw(loan) : "없음"} · 권리금 ${item.has_key_money ? formatKrw(keyMoney) : "없음"}`
      : `실인수가 🔒 로그인하고 보기 · 융자${item.has_succession_loan ? " 🔒 로그인하고 보기" : " 없음"} · 권리금${item.has_key_money ? " 🔒 로그인하고 보기" : " 없음"}`;
    const revenueText = item.has_monthly_revenue
      ? (hasFinance ? `월 매출 ${formatKrw(item.monthly_revenue_krw)}` : "월 매출 🔒 로그인하고 보기")
      : "";
    const visibleValue = (value, formatter) => value != null && value !== "" ? formatter(value) : "";
    const financeValues = hasFinance
      ? [
          acquisition != null ? `실인수가 ${formatKrw(acquisition)}` : "",
          item.has_succession_loan ? `승계융자 ${formatKrw(loan)}` : "",
          item.has_key_money ? `권리금 ${formatKrw(keyMoney)}` : ""
        ].filter(Boolean)
      : ["실인수가·승계융자·권리금은 로그인 후 확인"];
    const operationValues = [
      hasFinance && item.has_monthly_revenue ? `월평균매출 ${formatKrw(item.monthly_revenue_krw)}` : (item.has_monthly_revenue ? "월평균매출은 로그인 후 확인" : ""),
      hasFinance ? visibleValue(item.annual_revenue_krw, v => `연매출 ${formatKrw(v)}`) : (item.annual_revenue_krw != null ? "연매출은 로그인 후 확인" : ""),
      visibleValue(item.short_stay_ratio, v => `대실 ${Number(v).toLocaleString()}%`),
      visibleValue(item.ota_revenue_ratio, v => `OTA ${Number(v).toLocaleString()}%`),
      item.operation_status ? `운영상태 ${item.operation_status}` : "",
      item.closed_at ? `폐업일 ${item.closed_at}` : ""
    ].filter(Boolean);
    const facilityValues = [roomText, parkingText, landText, grossText].filter(Boolean);
    const extraValues = [
      item.remodeling_info ? `리모델링 ${item.remodeling_info}` : "",
      `공개범위 ${isLimitedListing ? "제한공개" : "전체공개"}`,
      item.permit_number_masked ? `영업신고 인증 ${item.permit_number_masked}` : ""
    ].filter(Boolean);
    const groupHtml = (title, values, extraClass) => values.length
      ? `<div class="whole-info-group${extraClass ? " " + extraClass : ""}"><div class="whole-info-title">${esc(title)}</div><div class="whole-info-values">${values.map(esc).join("<br>")}</div></div>`
      : "";
    const chatTitle = myChattingIds.has(item.id) ? "채팅 이어하기" : "문의하기";
    const photoCount = Array.isArray(item.photos) ? item.photos.length : 0;
    const photoClass = isLimitedListing ? "ls-card-photo-top" : "ls-card-photo-right";
    const cardPhotoHtml = `<div class="${photoClass}" title="${isLimitedListing ? "제한공개 매물 사진" : "매물 상세 보기"}">${thumbHtml(item.photo_url, true, photoCount, item.photo_source)}</div>`;
    const limitedNotice = isLimitedListing
      ? '<div class="whole-limited-notice">상세한 매물 내용은 채팅 상담으로 직접 문의해 주시기 바랍니다.</div>'
      : "";
    const description = String(item.description || "").trim();
    const descriptionIsLong = description.length > 180 || description.split(/\r?\n/).length > 5;
    const limitedDescription = isLimitedListing && description
      ? `<div class="whole-listing-description">
          <div class="whole-listing-description-title">매물 설명</div>
          <div class="whole-listing-description-text${descriptionIsLong ? " is-collapsed" : ""}">${esc(description)}</div>
          ${descriptionIsLong ? '<button type="button" class="whole-listing-description-toggle" aria-expanded="false">설명 전체보기</button>' : ""}
        </div>`
      : "";
    const hasApproximateLocation = isLimitedListing
      && Number.isFinite(Number(item.approx_lat))
      && Number.isFinite(Number(item.approx_lng));
    const approximateLocationButton = hasApproximateLocation
      ? `<button type="button" class="whole-approx-location-btn">◎ 반경 500m 위치 보기</button>`
      : "";
    const checklistButton = isLimitedListing
      ? ""
      : '<button type="button" class="listing-checklist-open">숙박업소 거래 체크리스트 열어보기</button>';
    const buildingLabel = item.is_limited_listing
      ? `<span class="ls-card-bldg">${lodgeBadgeHtml(item.lodging_type, item.lodging_subtype)}<span class="whole-badge" style="background:var(--brass,#B4863F);color:#fff;">건물전체</span><span class="whole-badge" style="background:#6B7280;color:#fff;">제한공개</span>${dealTypeBadgeHtml(item.deal_type)}${esc(item.building_name || "지역 비공개")}</span>`
      : `<span class="ls-card-bldg ls-bldg-link" data-bid="${item.building_id || ""}">${lodgeBadgeHtml(item.lodging_type, item.lodging_subtype)}<span class="whole-badge" style="background:var(--brass,#B4863F);color:#fff;">건물전체</span>${dealTypeBadgeHtml(item.deal_type)}${esc(item.building_name || "(건물명 없음)")}</span>`;

    div.innerHTML = `
      ${isLimitedListing ? cardPhotoHtml : ""}
      <div class="ls-card-info">
        <div class="ls-card-l1">${buildingLabel}${permitBadgeHtml(item)}${operationStatusHtml(item)}</div>
        <div class="ls-card-l2">${esc(listingPriceText(item))}</div>
        <div class="whole-info-groups">
          ${groupHtml("거래 조건", [listingPriceText(item)])}
          ${groupHtml("금융 · 인수", financeValues)}
          ${groupHtml("운영 · 매출", operationValues)}
          ${groupHtml("시설 · 건물", facilityValues)}
          ${groupHtml("추가 정보", extraValues, "whole-info-more")}
          <button type="button" class="whole-info-toggle" aria-expanded="false">전체 정보 보기</button>
        </div>
        <div class="whole-badges">${badges}</div>
        ${wholeLocationHint(item)}
        <div class="whole-viewers">최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명</div>
        <div class="whole-caution">※ 실제 인수금은 거래금액·승계융자·권리금·부대비용 기준의 참고값입니다.</div>
        ${limitedDescription}
        ${approximateLocationButton}
        ${limitedNotice}
        ${checklistButton}
        <div class="ls-card-l4">
          ${item.listing_number ? `<span class="ls-card-number">${esc(item.listing_number)}</span>` : ""}
          <span class="ls-card-date">${esc(item.listing_date || "")}</span>
          <span class="ls-card-actions">
            <button type="button" class="listing-like-btn${item.liked ? " is-liked" : ""}" title="찜">${window.LivingstayListingIcons.heart(!!item.liked)}<span class="like-cnt">${item.like_count || 0}</span></button>
            <button type="button" class="listing-chat-btn${myChattingIds.has(item.id) ? " is-chatting" : ""}" title="${chatTitle}">${window.LivingstayListingIcons.chat()}</button>
            <button type="button" class="listing-share-btn" title="링크 공유">${window.LivingstayListingIcons.share()}</button>
          </span>
        </div>
      </div>
      ${isLimitedListing ? "" : cardPhotoHtml}`;

    // 카드 전체와 사진에서 공용 상세 팝업을 연다.
    div.addEventListener("click", (e) => {
      if (e.target.closest(".ls-card-actions button, .listing-checklist-open, .ls-bldg-link, .ls-card-photo-right, .ls-card-photo-top, .whole-listing-description-toggle, .whole-info-toggle")) return;
      openListingDetail(item);
    });
    div.querySelector(".whole-listing-description-toggle")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const button = e.currentTarget;
      const text = div.querySelector(".whole-listing-description-text");
      const expanding = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", expanding ? "true" : "false");
      text?.classList.toggle("is-collapsed", !expanding);
      button.textContent = expanding ? "설명 접기" : "설명 전체보기";
    });
    const moreInfo = div.querySelector(".whole-info-more");
    const moreButton = div.querySelector(".whole-info-toggle");
    if (moreInfo && moreButton) {
      moreInfo.hidden = true;
      moreButton.addEventListener("click", (e) => {
        e.stopPropagation();
        const expanding = moreButton.getAttribute("aria-expanded") !== "true";
        moreButton.setAttribute("aria-expanded", expanding ? "true" : "false");
        moreInfo.hidden = !expanding;
        moreButton.textContent = expanding ? "정보 접기" : "전체 정보 보기";
      });
    } else if (moreButton) {
      moreButton.remove();
    }
    div.querySelector(".whole-approx-location-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof window.openApproximateLocationMap === "function") {
        window.openApproximateLocationMap(Number(item.approx_lat), Number(item.approx_lng), e.currentTarget);
      }
    });
    div.querySelector("." + photoClass).addEventListener("click", (e) => {
      e.stopPropagation();
      openListingDetail(item);
    });
    div.querySelector(".listing-checklist-open")?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.LivingstayListingChecklist?.open(item.id);
    });
    div.querySelector(".ls-bldg-link")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (item.building_id) window.location.href = `/building/${item.building_id}?listing=${item.id}`;
    });
    div.querySelector(".listing-chat-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      openChat(item.id);
    });
    div.querySelector(".listing-share-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      shareItem(item);
    });
    div.querySelector(".listing-like-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        const res = await fetch(`/api/listing-requests/${item.id}/like`, { method:"POST", credentials:"same-origin" });
        const d = await res.json().catch(() => ({}));
        if (res.ok && d.ok) {
          e.currentTarget.classList.toggle("is-liked", !!d.liked);
          const count = e.currentTarget.querySelector(".like-cnt");
          if (count) count.textContent = d.like_count;
          const oldIcon = e.currentTarget.querySelector(".listing-icon");
          if (oldIcon) oldIcon.replaceWith(document.createRange().createContextualFragment(window.LivingstayListingIcons.heart(!!d.liked)));
        }
      } catch(e2){}
    });
    return div;
  }

  function renderCardItem(item){
    if (item.is_whole_listing || item.transaction_target === "whole") {
      return renderWholeListingCard(item);
    }
    const div = document.createElement("div");
    div.className = "ls-card-item";
    div.dataset.listingId = item.id;
    const isWholeListing = item.is_whole_listing || item.transaction_target === "whole";
    const sqm     = !isWholeListing && item.area_sqm ? parseFloat(item.area_sqm).toFixed(1) + "㎡" : "";
    const priceStr = listingPriceText(item);
    const floorValue = item.floor ?? item.floor_no ?? item.floor_number;
    const floor    = floorValue != null && String(floorValue).trim() ? String(floorValue).trim() + "층" : null;
    const rooms    = !isWholeListing && !item.is_business_listing && item.room_count != null && Number(item.room_count) > 0
      ? "총 " + Number(item.room_count).toLocaleString() + "실" : null;
    const yld      = item.yield_rate != null ? "수익률 " + parseFloat(item.yield_rate).toFixed(1) + "%" : null;
    const desc     = item.description ? item.description.slice(0, 40) + (item.description.length > 40 ? "…" : "") : null;
    const detailText = [sqm, floor, rooms, yld, desc].filter(Boolean).join(" · ") || "-";
    const likeCount = item.like_count || 0;
    const photoCount = Array.isArray(item.photos) ? item.photos.length : 0;
    const chatTitle = myChattingIds.has(item.id) ? "채팅 이어하기" : "문의하기";

    div.innerHTML = `
      <div class="ls-card-info">
        <div class="ls-card-l1">
           <span class="ls-card-bldg ls-bldg-link" data-bid="${item.building_id || ""}">${lodgeBadgeHtml(item.lodging_type, item.lodging_subtype)}${isWholeListing ? '<span style="display:inline-block;margin-right:5px;padding:1px 6px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;">건물전체</span>' : ""}${esc(item.building_name || "(건물명 없음)")}${newBadge(item.listing_date)}</span>${urgentBadgeHtml(item)}${permitBadgeHtml(item)}
        </div>
        <div class="ls-card-l2">${dealTypeBadgeHtml(item.deal_type)}${esc(priceStr)}</div>
        <div class="ls-card-l3" title="${esc(detailText)}">${esc(detailText)}${operationStatusHtml(item)}${operationRatioBadgesHtml(item)}</div>
        <div class="ls-card-l4">
          ${item.listing_number ? `<span class="ls-card-number">${esc(item.listing_number)}</span>` : ""}
          <span class="ls-card-date">${esc(item.listing_date || "")}</span>
          <span class="ls-card-actions">
            <button type="button" class="listing-like-btn${item.liked ? " is-liked" : ""}" title="찜">${window.LivingstayListingIcons.heart(!!item.liked)}<span class="like-cnt">${likeCount}</span></button>
             <button type="button" class="listing-chat-btn${myChattingIds.has(item.id) ? " is-chatting" : ""}" title="${chatTitle}">${window.LivingstayListingIcons.chat()}</button>
             <button type="button" class="listing-share-btn" title="링크 공유">${window.LivingstayListingIcons.share()}</button>
          </span>
        </div>
      </div>
      <div class="ls-card-photo-right" title="매물 상세 보기">${thumbHtml(item.photo_url, true, photoCount, item.photo_source)}</div>`;

    // 카드 전체와 사진에서 공용 상세 팝업을 연다.
    div.addEventListener("click", (e) => {
      if (e.target.closest(".ls-card-actions button, .listing-checklist-open, .ls-bldg-link, .ls-card-photo-right, .ls-card-photo-top")) return;
      openListingDetail(item);
    });
    div.querySelector(".ls-card-photo-right").addEventListener("click", (e) => {
      e.stopPropagation();
      openListingDetail(item);
    });
    div.querySelectorAll(".ls-bldg-link").forEach(el => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        if (item.building_id) window.location.href = `/building/${item.building_id}`;
      });
    });
    div.querySelector(".listing-chat-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      openChat(item.id);
    });
    div.querySelector(".listing-share-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      shareItem(item);
    });
    div.querySelector(".listing-like-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        const res = await fetch(`/api/listing-requests/${item.id}/like`, { method:"POST", credentials:"same-origin" });
        const d = await res.json().catch(() => ({}));
        if (res.ok && d.ok) {
          e.currentTarget.classList.toggle("is-liked", !!d.liked);
          const count = e.currentTarget.querySelector(".like-cnt");
          if (count) count.textContent = d.like_count;
          const oldIcon = e.currentTarget.querySelector(".listing-icon");
          if (oldIcon) oldIcon.replaceWith(document.createRange().createContextualFragment(window.LivingstayListingIcons.heart(!!d.liked)));
        }
      } catch(e2){}
    });
    return div;
  }

  // ── 목록 로드 ────────────────────────────────────────────────────────
  async function loadListings(reset){
    if (loading) return;
    loading = true;

    if (reset){
      boardBody.innerHTML = `<tr><td colspan="11" class="listings-loading">불러오는 중…</td></tr>`;
      cardGrid.innerHTML  = `<div class="listings-loading" style="grid-column:1/-1;">불러오는 중…</div>`;
      offset = 0;
      totalLoaded = 0;
      countEl.textContent = "";
    }

    try {
      if (chatFilterId != null){
        const urgentParam = state.urgent_only ? "&urgent_only=1" : "";
        const res = await fetch(`/api/listings?limit=50&offset=0&disclosure_scope=${encodeURIComponent(state.disclosure_scope)}${urgentParam}`, { credentials: "same-origin" });
        const d = await res.json().catch(() => ({}));
        const filtered = (d.items || []).filter(it => it.id === chatFilterId);
        boardBody.innerHTML = "";
        cardGrid.innerHTML  = "";
        moreBtn.style.display = "none";
        if (!filtered.length){
           boardBody.innerHTML = `<tr><td colspan="11" class="listings-empty">해당 매물을 찾을 수 없습니다.</td></tr>`;
        } else {
          filtered.forEach(it => { boardBody.appendChild(renderBoardRow(it)); cardGrid.appendChild(renderCardItem(it)); });
          recordWholeListingViews(filtered);
          loadWholeLocationHints(filtered);
        }
        return;
      }

      const params = new URLSearchParams({ limit: PAGE, offset });
      params.set("disclosure_scope", state.disclosure_scope);
      if (state.urgent_only) params.set("urgent_only", "1");
      if (state.sido)       params.set("sido",       state.sido);
      if (state.sgg_nm)     params.set("sgg_nm",     state.sgg_nm);
      if (state.umd_nm)     params.set("umd_nm",     state.umd_nm);
      if (state.q)          params.set("q",          state.q);
      if (state.deal_type)    params.set("deal_type",    state.deal_type);
      if (state.date_range)  params.set("date_range",  state.date_range);
      if (state.lodging_type) params.set("lodging_type", state.lodging_type);

      const res = await fetch(`/api/listings?${params}`, { credentials: "same-origin" });
      const d   = await res.json().catch(() => ({}));

      if (!res.ok || !d.ok){
         boardBody.innerHTML = `<tr><td colspan="11" class="listings-empty">불러오기 실패. 새로고침 해주세요.</td></tr>`;
        cardGrid.innerHTML  = `<div class="listings-empty" style="grid-column:1/-1;">불러오기 실패.</div>`;
        return;
      }

      if (reset){ boardBody.innerHTML = ""; cardGrid.innerHTML = ""; }

      if (!d.items || d.items.length === 0){
        if (reset){
           boardBody.innerHTML = `<tr><td colspan="11" class="listings-empty">현재 공개된 직거래 매물이 없습니다.</td></tr>`;
          cardGrid.innerHTML  = `<div class="listings-empty" style="grid-column:1/-1;">현재 공개된 직거래 매물이 없습니다.</div>`;
        }
        moreBtn.style.display = "none";
      } else {
        d.items.forEach(item => {
          boardBody.appendChild(renderBoardRow(item));
          cardGrid.appendChild(renderCardItem(item));
        });
        recordWholeListingViews(d.items);
        loadWholeLocationHints(d.items);
         sortBoardRows();
        offset      += d.items.length;
        totalLoaded += d.items.length;
        countEl.textContent = `총 ${totalLoaded}건${d.has_more ? "+" : ""}`;
        moreBtn.style.display = d.has_more ? "" : "none";
      }
    } catch(e){
      if (reset){
         boardBody.innerHTML = `<tr><td colspan="11" class="listings-empty">오류가 발생했습니다.</td></tr>`;
        cardGrid.innerHTML  = `<div class="listings-empty" style="grid-column:1/-1;">오류가 발생했습니다.</div>`;
      }
    } finally {
      loading = false;
    }
  }

  // ── 검색 버튼 ────────────────────────────────────────────────────────
  document.getElementById("lsBtnSearch").addEventListener("click", () => {
    chatFilterId = null;
    document.querySelectorAll("#lsChatChips .fav-chip").forEach(c => c.classList.remove("active"));
    const allChip = document.querySelector("#lsChatChips .fav-chip");
    if (allChip) allChip.classList.add("active");
    state.sido       = document.getElementById("lsSido").value;
    state.sgg_nm     = document.getElementById("lsSggNm").value;
    state.umd_nm     = document.getElementById("lsUmdNm").value;
    state.q          = document.getElementById("lsQ").value.trim();
    state.deal_type    = document.getElementById("lsDealType").value;
    state.date_range   = document.getElementById("lsDateRange").value;
    state.lodging_type = document.getElementById("lsLodgingType").value;
    loadListings(true);
  });

  document.getElementById("lsQ").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("lsBtnSearch").click();
  });

  moreBtn.addEventListener("click", () => loadListings(false));

  // ── 초기 로드 ────────────────────────────────────────────────────────
  Promise.all([
    loadRegions(),
    loadMyChatListings(),
  ]).then(() => loadListings(true));

})();
