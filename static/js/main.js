const FAV_KEY = "livingstay_favorites";
// 관리자 모드: URL에 ?admin=1 을 붙이면 50개까지, 아니면 일반 사용자 5개 제한
// (아직 로그인/계정 시스템이 없어 임시로 URL 파라미터로 구분 — 나중에 계정 붙이면 서버 권한으로 교체 권장)
const IS_ADMIN = new URLSearchParams(location.search).get("admin") === "1";
const MAX_FAVORITES = IS_ADMIN ? 50 : 5;

let regionTree = {};
let state = { si_do:"", sgg_nm:"", umd_nm:"", q:"", year:"all", lodging_type:"", page:1, size:20, favOnly:false, favKey:null };
let defaultYear = "";

function getFavorites(){
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); } catch(e){ return []; }
}
function favKey(item){ return `${item.building_name}|${item.address}`; }
function isFav(item){ return getFavorites().includes(favKey(item)); }
// 로그인 상태(auth.js가 window.__livingstayLoggedIn 을 세팅)일 때만 서버에도 반영한다.
// 비로그인 사용자는 지금처럼 localStorage만 사용 → 하위호환 유지.
function serverFavSync(method, item){
  if (!window.__livingstayLoggedIn) return;
  fetch("/api/favorites/mine", {
    method: method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ building_name: item.building_name, address: item.address })
  }).catch(function(){ /* 서버 반영 실패해도 localStorage는 이미 갱신됨 → 무시 */ });
}
function toggleFav(item){
  let favs = getFavorites();
  const k = favKey(item);
  let clearedActiveFilter = false;
  const wasFav = favs.includes(k);
  if (wasFav){
    favs = favs.filter(x=>x!==k);
    if (state.favKey === k){ state.favKey = null; state.favOnly = false; clearedActiveFilter = true; }
  } else {
    if (favs.length >= MAX_FAVORITES){
      alert(`관심단지는 최대 ${MAX_FAVORITES}개까지 저장할 수 있습니다.`);
      return false;
    }
    favs = [...favs, k];
  }
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
  serverFavSync(wasFav ? "DELETE" : "POST", item);
  updateFavCountLabel();
  renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
  if (clearedActiveFilter){ document.getElementById("chkFavOnly").checked = false; loadBoard(); }
  return true;
}
function removeFav(key){
  const favs = getFavorites().filter(x=>x!==key);
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
  const sep = key.indexOf("|");
  if (sep >= 0){
    serverFavSync("DELETE", { building_name: key.slice(0, sep), address: key.slice(sep + 1) });
  }
  if (state.favKey === key){ state.favKey = null; state.favOnly = false; }
  updateFavCountLabel();
  renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
  loadBoard();
}
// 로그인 직후 migrate 로 localStorage가 갱신됐을 때 auth.js가 호출 → 관심 UI 다시 그린다.
window.refreshFavoritesUI = function(){
  if (typeof updateFavCountLabel === "function") updateFavCountLabel();
  if (typeof renderFavChips === "function") renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
};
function updateFavCountLabel(){
  document.getElementById("favCountLabel").textContent =
    `저장된 관심단지 ${getFavorites().length}/${MAX_FAVORITES}개`;
}

// 실거래 알림 구독 — 서버(user_alert_subscriptions)에 저장한다. 로그인 상태에서만 동작하고,
// 비로그인 시 클릭하면 로그인 안내. 관심저장과 동일한 키(building_name|address)를 쓴다.
//   alertKeySet: 서버에서 내려받은 내 구독 키 집합(로그인 시 로드). B패널 버튼 상태 판정용.
const ALERT_KEY = "livingstay_alerts";           // 비로그인 때 담아둔 값 → 로그인 시 migrate
let alertKeySet = new Set();
let alertsLoaded = false;
function isAlertOn(key){ return alertKeySet.has(key); }
// 서버에서 내 알림구독 목록을 받아 alertKeySet 을 채운다(로그인 상태에서만).
function loadServerAlerts(cb){
  if (!window.__livingstayLoggedIn){ alertKeySet = new Set(); alertsLoaded = true; if (cb) cb(); return; }
  fetch("/api/alerts/mine", { credentials: "same-origin" })
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (d && d.ok && Array.isArray(d.keys)) alertKeySet = new Set(d.keys);
      alertsLoaded = true;
      if (cb) cb();
    })
    .catch(function(){ alertsLoaded = true; if (cb) cb(); });
}
// 로그인 직후 auth.js 가 호출 → 구독 목록 다시 로드 후 열려있는 B패널 버튼 갱신.
window.refreshAlertsUI = function(){
  loadServerAlerts(function(){ if (typeof window.__syncOpenAlertBtn === "function") window.__syncOpenAlertBtn(); });
};

function escapeHtml(v){
  return String(v ?? "").replace(/[&<>"']/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
  ));
}

function renderFavChips(){
  const wrap = document.getElementById("favChips");
  const favs = getFavorites();
  wrap.innerHTML = "";
  favs.forEach(k => {
    const name = k.split("|")[0];
    const chip = document.createElement("span");
    chip.className = "fav-chip" + (state.favKey === k ? " active" : "");
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = "★ " + name;
    label.title = "이 관심단지만 보기";
    label.addEventListener("click", () => filterToFav(k));
    chip.appendChild(label);
    const x = document.createElement("span");
    x.className = "x";
    x.textContent = "✕";
    x.addEventListener("click", (e) => { e.stopPropagation(); removeFav(k); });
    chip.appendChild(x);
    wrap.appendChild(chip);
  });
}

function filterToFav(key){
  if (state.favOnly && state.favKey === key){
    state.favOnly = false; state.favKey = null;
  } else {
    state.favOnly = true; state.favKey = key;
  }
  document.getElementById("chkFavOnly").checked = false;
  state.page = 1;
  renderFavChips();
  loadBoard();
}

async function loadRegions(){
  const res = await fetch("/api/regions");
  regionTree = await res.json();
  const selSiDo = document.getElementById("selSiDo");
  selSiDo.innerHTML = '<option value="">전체</option>' +
    Object.keys(regionTree).sort().map(sd => `<option value="${sd}">${sd} (${regionTree[sd].count})</option>`).join("");
}
function refreshSggOptions(){
  const selSggNm = document.getElementById("selSggNm");
  const selUmdNm = document.getElementById("selUmdNm");
  if (!state.si_do || !regionTree[state.si_do]){
    selSggNm.innerHTML = '<option value="">전체</option>';
    selUmdNm.innerHTML = '<option value="">전체</option>';
    return;
  }
  const sggMap = regionTree[state.si_do].sgg;
  selSggNm.innerHTML = '<option value="">전체</option>' +
    Object.keys(sggMap).sort().map(sg => `<option value="${sg}">${sg} (${sggMap[sg].count})</option>`).join("");
  selUmdNm.innerHTML = '<option value="">전체</option>';
}
function refreshUmdOptions(){
  const selUmdNm = document.getElementById("selUmdNm");
  const sgg = regionTree[state.si_do]?.sgg?.[state.sgg_nm];
  if (!sgg){
    selUmdNm.innerHTML = '<option value="">전체</option>';
    return;
  }
  const umdMap = sgg.umd;
  selUmdNm.innerHTML = '<option value="">전체</option>' +
    Object.keys(umdMap).sort().map(um => `<option value="${um}">${um} (${umdMap[um]})</option>`).join("");
}

async function loadYears(){
  const res = await fetch("/api/years");
  const data = await res.json();
  const sel = document.getElementById("selYear");
  const opts = ['<option value="all">전체 기간</option>'];
  data.years.forEach(y => opts.push(`<option value="${y}">${y}년</option>`));
  sel.innerHTML = opts.join("");
  sel.value = "all";
  state.year = "all";
  defaultYear = "all";
}

function rowHTML(t, idx){
  const fav = isFav(t);
  const typeTag = t.deal_type === "직거래" ? `<span class="tag brk">직거래</span>` : `<span class="tag med">중개거래</span>`;
  const lodgingColors = { "생활": "med", "호텔": "brk", "콘도": "src" };
  const isCombined = (t.lodging_type || "").includes("·");
  const lodgingClass = isCombined ? "mixed" : (lodgingColors[t.lodging_type] || "unknown");
  const lodgingLabel = t.lodging_type || "미확인";
  const lodgingTag = `<span class="tag ${lodgingClass}" style="cursor:pointer;"
      title="${(t.lodging_type_detail||'용도 미확인 — 건축물대장 재검증 필요').replace(/"/g,'&quot;')} (클릭하면 정정 요청)"
      onclick="openCorrectionModal(${idx})">${lodgingLabel} ✎</span>`;
  const priceFormatted = Number(t.price || 0).toLocaleString('ko-KR');
  return `
    <tr>
      <td class="col-star ${fav?'on':''}" onclick="handleStarClick(this)">${fav?'★':'☆'}</td>
      <td class="col-name">${t.building_name != null ? escapeHtml(t.building_name) : "(건물명 미확인)"} ${lodgingTag}</td>
      <td class="col-addr">${escapeHtml(t.si_do||'')} ${escapeHtml(t.sgg_nm||'')} ${escapeHtml(t.umd_nm||'')} ${escapeHtml(t.jibun||'')}</td>
      <td class="col-num col-area">${Number(t.area).toFixed(1)} ㎡</td>
      <td class="col-num col-floor">${t.floor ? t.floor + '<span class="m-only">층</span>' : '-'}</td>
      <td class="col-price">${priceFormatted}<span class="m-only">만원</span></td>
      <td class="col-date">${t.deal_date}</td>
      <td class="col-type">${typeTag}</td>
    </tr>`;
}

let lastItems = [];
function handleStarClick(td){
  const tr = td.parentElement;
  const idx = [...tr.parentElement.children].indexOf(tr);
  const item = lastItems[idx];
  if(!item) return;
  const ok = toggleFav(item);
  if (ok === false) return;  // 상한 초과 시 표시 변경 안 함
  td.classList.toggle("on");
  td.textContent = td.classList.contains("on") ? "★" : "☆";
}

async function loadBoard(){
  const board = document.getElementById("board");
  // 큰 실거래 게시판은 /transactions 전용 페이지로 분리됨 — 지도 홈에는 #board가 없으므로 no-op.
  if (!board) return;
  board.innerHTML = `<div class="loading">불러오는 중…</div>`;

  let items = [], total = 0;

  if (state.favOnly){
    const favs = state.favKey ? [state.favKey] : getFavorites();
    if (favs.length === 0){
      items = []; total = 0;
    } else {
      const res = await fetch(`/api/favorites?keys=${encodeURIComponent(favs.join(","))}`);
      const data = await res.json();
      items = data.items; total = data.total;
    }
  } else {
    const params = new URLSearchParams({
      q: state.q, si_do: state.si_do, sgg_nm: state.sgg_nm, umd_nm: state.umd_nm,
      year: state.year, lodging_type: state.lodging_type, page: state.page, size: state.size
    });
    const res = await fetch(`/api/transactions?${params}`);
    const data = await res.json();
    items = data.items; total = data.total;
  }

  lastItems = items;
  document.getElementById("resultCount").textContent = `총 ${total}건`;

  if (items.length === 0){
    board.innerHTML = `<div class="empty-state"><div class="big">일치하는 거래가 없습니다</div>검색 조건을 조정해보세요.</div>`;
    document.getElementById("pager").innerHTML = "";
    return;
  }

  board.innerHTML = `
    <table class="data-table">
      <thead><tr><th></th><th>건물명</th><th>주소</th><th>면적</th><th>층</th><th>거래금액 (만원)</th><th>계약일</th><th>거래유형</th></tr></thead>
      <tbody>${items.map((t, idx) => rowHTML(t, idx)).join("")}</tbody>
    </table>`;

  if (state.favOnly){
    document.getElementById("pager").innerHTML = "";
  } else {
    const totalPages = Math.max(Math.ceil(total / state.size), 1);
    const pager = document.getElementById("pager");
    pager.innerHTML = `
      <button ${state.page<=1?"disabled":""} id="prevPage">이전</button>
      <span class="cur">${state.page} / ${totalPages}</span>
      <button ${state.page>=totalPages?"disabled":""} id="nextPage">다음</button>`;
    document.getElementById("prevPage")?.addEventListener("click", ()=>{ state.page--; loadBoard(); });
    document.getElementById("nextPage")?.addEventListener("click", ()=>{ state.page++; loadBoard(); });
  }
}

document.getElementById("selSiDo").addEventListener("change", e=>{
  state.si_do = e.target.value; state.sgg_nm=""; state.umd_nm="";
  refreshSggOptions();
});
document.getElementById("selSggNm").addEventListener("change", e=>{
  state.sgg_nm = e.target.value; state.umd_nm="";
  refreshUmdOptions();
});
document.getElementById("selUmdNm").addEventListener("change", e=>{ state.umd_nm = e.target.value; });
document.getElementById("selYear").addEventListener("change", e=>{ state.year = e.target.value; });
document.getElementById("selLodgingType").addEventListener("change", e=>{
  state.lodging_type = e.target.value; state.page = 1; loadBoard();
  loadMapMarkers(mapFiltersFromState(), { fit: true });
});
document.getElementById("chkFavOnly").addEventListener("change", e=>{
  state.favOnly = e.target.checked; state.favKey = null; state.page = 1;
  renderFavChips(); loadBoard();
});
document.getElementById("btnSearch").addEventListener("click", ()=>{
  state.q = document.getElementById("inputQ").value.trim();
  state.page = 1;
  loadBoard();
  loadMapMarkers(mapFiltersFromState(), { fit: true });
});
function resetToHome(){
  const yearSel = document.getElementById("selYear");
  const y = defaultYear || yearSel.value || "all";
  state.si_do=""; state.sgg_nm=""; state.umd_nm=""; state.q="";
  state.lodging_type=""; state.year="all";
  state.favOnly=false; state.favKey=null; state.page=1;
  document.getElementById("selSiDo").value="";
  refreshSggOptions();
  document.getElementById("selLodgingType").value="";
  yearSel.value="all";
  document.getElementById("inputQ").value="";
  document.getElementById("chkFavOnly").checked=false;
  renderFavChips();
  loadBoard();
  resetMapView();
  loadMapMarkers({}, { fit: false });   // 지도도 전체 476개로 복귀
  window.scrollTo({top:0, behavior:"smooth"});
}
document.getElementById("brandHome").addEventListener("click", resetToHome);
document.getElementById("inputQ").addEventListener("keydown", e=>{
  if (e.key === "Enter") document.getElementById("btnSearch").click();
});

async function loadHealth(){
  try{
    const res = await fetch("/api/health");
    const h = await res.json();
    if (h.finished_at){
      document.getElementById("healthStatus").textContent = `최근 갱신: ${String(h.finished_at).slice(0,16).replace('T',' ')} · 누적 ${h.rows_inserted ?? '-'}건`;
    }
  } catch(e){}
}

(async function init(){
  await loadRegions();
  await loadYears();
  updateFavCountLabel();
  renderFavChips();
  loadHealth();

  // 마케팅 사이트의 지역 이미지 클릭 등, 외부에서 ?si_do=서울특별시 형태로
  // 들어오면 그 지역이 미리 선택된 상태로 시작한다.
  const urlParams = new URLSearchParams(location.search);
  const initialSiDo = urlParams.get("si_do");
  if (initialSiDo && regionTree[initialSiDo]) {
    state.si_do = initialSiDo;
    document.getElementById("selSiDo").value = initialSiDo;
    refreshSggOptions();
  }

  loadBoard();
})();

// ---------- 내 건물 추가 요청 ----------
const submitModal = document.getElementById("submitModal");
document.getElementById("btnOpenSubmit").addEventListener("click", () => {
  submitModal.style.display = "flex";
  document.getElementById("submitResult").style.display = "none";
});
document.getElementById("btnCloseSubmit").addEventListener("click", () => {
  submitModal.style.display = "none";
});
document.getElementById("btnSubmitBuilding").addEventListener("click", async () => {
  const road_address = document.getElementById("submitAddress").value.trim();
  const building_name_hint = document.getElementById("submitNameHint").value.trim();
  const suggested_lodging_type = document.getElementById("submitLodgingType").value;
  const resultBox = document.getElementById("submitResult");

  if (!road_address) {
    resultBox.style.display = "block";
    resultBox.style.background = "#FBEBE9";
    resultBox.style.color = "#B3453A";
    resultBox.textContent = "주소를 입력해주세요.";
    return;
  }

  resultBox.style.display = "block";
  resultBox.style.background = "#EEF1F3";
  resultBox.style.color = "var(--ink-soft)";
  resultBox.textContent = "건축물대장을 조회하고 있습니다…";

  try {
    const res = await fetch("/api/submit-building", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ road_address, building_name_hint, suggested_lodging_type }),
    });
    const data = await res.json();

    if (data.status === "verified") {
      resultBox.style.background = "#EAF4EE";
      resultBox.style.color = "#2F7D52";
      resultBox.textContent = "✓ " + data.message;
      loadRegions();
      loadBoard();
    } else {
      resultBox.style.background = "#FBEBE9";
      resultBox.style.color = "#B3453A";
      resultBox.textContent = "✕ " + data.message;
    }
  } catch (e) {
    resultBox.style.background = "#FBEBE9";
    resultBox.style.color = "#B3453A";
    resultBox.textContent = "요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  }
});

// ---------- 용도 정정 요청 ----------
const correctionModal = document.getElementById("correctionModal");
let correctionTarget = null;

function openCorrectionModal(idx){
  const t = lastItems[idx];
  if (!t || !t.sgg_cd) {
    alert("이 항목은 대상 건물 정보가 부족해 정정 요청을 할 수 없습니다.");
    return;
  }
  correctionTarget = t;
  document.getElementById("correctionBuildingName").textContent = t.building_name || "(건물명 미확인)";
  document.getElementById("correctionCurrentLabel").textContent =
    (t.lodging_type || "미확인") + (t.lodging_type_detail ? ` — ${t.lodging_type_detail}` : "");
  document.getElementById("correctionNote").value = "";
  document.getElementById("correctionResult").style.display = "none";
  correctionModal.style.display = "flex";
}
document.getElementById("btnCloseCorrection").addEventListener("click", () => {
  correctionModal.style.display = "none";
});

// ---------- 카카오맵 ----------
const LODGING_COLORS = { "생활": "#378ADD", "호텔": "#7F77DD", "콘도": "#639922" };
const LODGING_LABELS = { "생활": "생활숙박시설", "호텔": "분양형호텔", "콘도": "콘도" };
const DEFAULT_MARKER_COLOR = "#9AA5B1";

// lodging_type이 '생활·호텔'처럼 복합이면 맨 앞 용도 색을 쓰고, 값이 없으면 회색.
function markerColor(lodgingType){
  if (!lodgingType) return DEFAULT_MARKER_COLOR;
  return LODGING_COLORS[lodgingType.split("·")[0]] || DEFAULT_MARKER_COLOR;
}
function lodgingLabelKo(lodgingType){
  if (!lodgingType) return "미분류";
  return lodgingType.split("·").map(t => LODGING_LABELS[t] || t).join("·");
}

let kakaoMap = null;
let currentInfoWindow = null;
let mapOverlays = [];                 // 현재 지도에 찍힌 마커(오버레이) 목록
let mapLabels = [];                   // 마커 옆 '건물명+최근가' 라벨 요소 목록(줌 토글용)
let hoverTooltip = null;              // 마커 호버용 공용 미리보기 툴팁(오버레이)
let hoverHideTimer = null;            // 호버 툴팁 지연 숨김 타이머(간격 통과 시 깜빡임 방지)
let hoverCurrentKey = null;          // 현재 툴팁이 가리키는 마커 키(같은 마커 재진입 시 재생성 방지)
const LABEL_MAX_LEVEL = 6;            // 이 확대 레벨 이하(더 가까이)일 때만 라벨 표시
const MAP_DEFAULT_CENTER = { lat: 36.35, lng: 126.9 }; // 좌측 사이드패널이 지도 위에 겹쳐 한반도가 왼쪽으로 밀려 보이므로 중심 경도를 서쪽으로 낮춰 가로 중앙 정렬(일본 과다 노출 완화)
const MAP_DEFAULT_LEVEL = 12;         // 속초~완도가 세로로 다 보이는 확대 수준

// 검색폼(state)에서 지도용 필터만 추출한다. 기간(year)은 건물 위치와
// 무관하므로 지도에는 적용하지 않는다(게시판 전용).
function mapFiltersFromState(){
  return {
    q: state.q, si_do: state.si_do, sgg_nm: state.sgg_nm,
    umd_nm: state.umd_nm, lodging_type: state.lodging_type,
  };
}

function clearMapMarkers(){
  mapOverlays.forEach(o => o.setMap(null));
  mapOverlays = [];
  mapLabels = [];
  hideHoverTooltip();
}

function resetMapView(){
  if (!kakaoMap) return;
  kakaoMap.setLevel(MAP_DEFAULT_LEVEL);
  kakaoMap.setCenter(new kakao.maps.LatLng(MAP_DEFAULT_CENTER.lat, MAP_DEFAULT_CENTER.lng));
}

// 실거래 상세(가격·날짜 / 층·전용면적·거래유형) HTML — 클릭 InfoWindow와
// 호버 툴팁이 공유하는 단일 렌더러. 내용이 어긋나지 않도록 한 곳에서만 만든다.
// d: {price, deal_date, floor, area, deal_type, exact}. price가 null/undefined면 '실거래 이력 없음'.
// exact === false면 같은 필지의 대체(참고) 거래이므로 '(필지 내 참고가)' 안내를 덧붙인다.
function dealDetailHtml(d){
  if (!d || d.price == null){
    return `<div style="color:#8a94a0;">실거래 이력 없음</div>`;
  }
  const price = Number(d.price).toLocaleString('ko-KR');
  const date = escapeHtml(d.deal_date || "");
  const floor = d.floor ? escapeHtml(String(d.floor)) + "층" : "-";
  const area = d.area != null ? Number(d.area).toFixed(1) + "㎡" : "-";
  const dealType = escapeHtml(d.deal_type || "-");
  const refNote = (d.exact === false)
    ? `<div style="color:#8a94a0; font-size:11px; margin-top:1px;">(필지 내 참고가)</div>`
    : "";
  return (
    `<div style="margin-top:2px; line-height:1.7;">` +
      `<div><b style="color:#B4863F;">${price}만원</b> · ${date}</div>` +
      `<div>${floor} · 전용 ${area} · ${dealType}</div>` +
      refNote +
    `</div>`
  );
}

// 현재 확대 레벨을 보고 모든 마커 라벨을 표시/숨김 (LABEL_MAX_LEVEL 이하일 때만 표시).
// 축소된 전국뷰에서는 라벨이 겹쳐 지저분해지므로 숨긴다.
function updateMarkerLabels(){
  if (!kakaoMap) return;
  const show = kakaoMap.getLevel() <= LABEL_MAX_LEVEL;
  mapLabels.forEach(l => { l.style.display = show ? "block" : "none"; });
}

// ★ 마커 정보 내용 공용 빌더 — 호버 툴팁과 클릭 InfoWindow가 완전히 동일한
// 내용(건물명·용도·최근 실거래 + ☆관심저장 버튼 + "상세보기 →" 링크)을 쓰도록
// 한 곳에서 HTML을 만든다. 두 곳의 내용이 갈라지며 "이중 마커"처럼 느껴지던
// 문제를 없애기 위한 단일 소스.
function buildingInfoInnerHtml(b){
  const name = escapeHtml(b.building_name || "(건물명 미확인)");
  const typeKo = escapeHtml(lodgingLabelKo(b.lodging_type));
  const dealHtml = dealDetailHtml({
    price: b.latest_price, deal_date: b.latest_deal_date,
    floor: b.latest_floor, area: b.latest_area, deal_type: b.latest_deal_type,
    exact: b.latest_price_exact,
  });

  const detailLink = (b.id != null)
    ? `<a href="/building/${b.id}" onclick="return window.openBuildingDetail(${b.id});" style="color:#B4863F; font-weight:700; text-decoration:none;">상세보기 →</a>`
    : "";

  // 관심저장 — 좌측 목록과 동일한 favKey(building_name|address). 실거래 지번주소
  // 우선, 없으면 마스터 도로명주소 폴백(거래이력 없어도 주소만 있으면 활성화).
  const favAddr = (b.address != null && b.address !== "") ? b.address : (b.road_address || "");
  const canFav = favAddr !== "";
  const favActive = canFav && isFav({ building_name: b.building_name, address: favAddr });
  const favBtn = canFav
    ? `<button type="button" data-name="${escapeHtml(b.building_name || "")}" data-address="${escapeHtml(favAddr)}"
         onclick="return window.toggleFavFromInfo(this);"
         style="border:none; background:none; cursor:pointer; padding:0; font-size:12.5px; font-weight:700; color:${favActive ? "#B4863F" : "#8a94a0"};">
         ${favActive ? "★ 관심저장됨" : "☆ 관심저장"}</button>`
    : "";
  const actionRow = (favBtn || detailLink)
    ? `<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:8px;">${favBtn}${detailLink}</div>`
    : "";

  return (
    `<div style="font-weight:700; font-size:13.5px; margin-bottom:2px;">${name}</div>` +
    `<div style="color:#6b7683; margin-bottom:4px;">${typeKo}</div>` +
    dealHtml +
    actionRow
  );
}

// 호버 미리보기 툴팁 내용 — 클릭 InfoWindow와 완전히 동일한 내용을 공용 빌더로
// 생성한다(버튼 포함, 클릭 가능). 카드 테두리/그림자만 툴팁 고유 스타일.
function hoverTooltipContent(b){
  return (
    `<div style="padding:10px 12px; min-width:170px; max-width:240px; font-size:12.5px;` +
    ` color:#16202E; font-family:'Noto Sans KR',sans-serif; background:#fff;` +
    ` border:1px solid #e2e6ea; border-radius:8px; box-shadow:0 4px 14px rgba(0,0,0,.18);">` +
      buildingInfoInnerHtml(b) +
    `</div>`
  );
}

function showHoverTooltip(b, pos){
  if (!kakaoMap) return;
  // 숨김 예약이 걸려 있으면 취소 — 인접 마커 사이 간격을 지나며 재진입한 경우.
  if (hoverHideTimer){ clearTimeout(hoverHideTimer); hoverHideTimer = null; }
  // 같은 마커에 다시 진입한 것이면 재생성하지 않는다(재생성 시 깜빡임의 원인).
  const key = pos.getLat() + "," + pos.getLng();
  if (hoverTooltip && hoverCurrentKey === key && hoverTooltip.getMap()) return;
  hoverCurrentKey = key;

  const el = document.createElement("div");
  // 마커 위쪽으로 충분히 띄워 상시 라벨 칩(점 위 ~45px)을 가리지 않게 한다.
  // translateY 대신 아래쪽 padding으로 띄우면, 그 여백이 요소 히트영역에 포함돼
  // 마커→툴팁 사이 간격을 마우스가 지나가도 mouseleave가 발생하지 않는
  // 보이지 않는 "다리" 역할을 한다(툴팁이 클릭 전에 사라지는 문제 방지).
  el.style.paddingBottom = "52px";
  el.innerHTML = hoverTooltipContent(b);
  // 툴팁 안의 ☆관심저장·상세보기 버튼을 실제로 누를 수 있어야 하므로
  // pointer-events를 살려 두고, 대신 툴팁 자체에 mouseenter/mouseleave를 걸어
  // 마커→툴팁으로 마우스가 이동하는 동안 숨김 타이머를 취소한다(떨림 방지 겸용).
  el.addEventListener("mouseenter", () => {
    if (hoverHideTimer){ clearTimeout(hoverHideTimer); hoverHideTimer = null; }
  });
  el.addEventListener("mouseleave", hideHoverTooltip);
  // 다리(padding) 영역은 시각적으로 비어 있지만 마커 점 위를 덮으므로,
  // 그 영역을 클릭하면 마커를 클릭한 것과 동일하게 상세 InfoWindow를 연다.
  el.addEventListener("click", (e) => {
    if (e.target === el) openBuildingInfo(b, pos);
  });
  if (!hoverTooltip){
    hoverTooltip = new kakao.maps.CustomOverlay({
      position: pos, content: el, xAnchor: 0.5, yAnchor: 1, clickable: true, zIndex: 9999,
    });
  } else {
    hoverTooltip.setContent(el);
    hoverTooltip.setPosition(pos);
  }
  hoverTooltip.setMap(kakaoMap);
}

// immediate=true면 즉시 숨김(클릭 등). 기본은 짧게 지연해 숨긴다 — 조밀하게 붙은
// 마커 사이 1~2px 간격을 지날 때 숨김→표시가 반복되며 떨리는 현상을 막는다.
// 지연 중 다른 마커로 재진입하면 showHoverTooltip에서 타이머를 취소한다.
function hideHoverTooltip(immediate){
  if (hoverHideTimer){ clearTimeout(hoverHideTimer); hoverHideTimer = null; }
  const doHide = () => {
    if (hoverTooltip) hoverTooltip.setMap(null);
    hoverCurrentKey = null;
    hoverHideTimer = null;
  };
  if (immediate === true){ doHide(); return; }
  // 380ms: 떨림 방지(짧은 이탈 무시)를 유지하면서, 마커→툴팁→"상세보기"까지
  // 마우스를 천천히 옮겨도 끊기지 않을 만큼의 여유를 준다.
  hoverHideTimer = setTimeout(doHide, 380);
}

// filters: {q, si_do, sgg_nm, umd_nm, lodging_type}
// opts.fit: true면 결과가 다 보이도록 bounds에 맞춰 확대/이동
async function loadMapMarkers(filters = {}, opts = {}){
  if (!kakaoMap) return;
  const emptyEl = document.getElementById("mapEmpty");

  const params = new URLSearchParams();
  ["q", "si_do", "sgg_nm", "umd_nm", "lodging_type"].forEach(k => {
    if (filters[k]) params.set(k, filters[k]);
  });
  const qs = params.toString();

  let items = [];
  try {
    const res = await fetch(`/api/buildings-geo${qs ? "?" + qs : ""}`);
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    console.error("[MAP] 건물 좌표 로드 실패:", e);
    return;
  }

  clearMapMarkers();
  const bounds = new kakao.maps.LatLngBounds();
  let placed = 0;
  items.forEach(b => {
    if (b.lat == null || b.lng == null) return;
    const color = markerColor(b.lodging_type);
    const pos = new kakao.maps.LatLng(b.lat, b.lng);

    // 기존 마커 원(색상 점) — 디자인 그대로 유지
    const el = document.createElement("div");
    el.style.cssText = `width:14px; height:14px; border-radius:50%; background:${color};` +
      `border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.4); cursor:pointer;`;
    el.title = b.building_name || "";

    // 점 위에 '건물명 + 실거래가' 칩 라벨을 절대배치로 얹는다.
    // 래퍼는 점과 동일한 14x14라 앵커(0.5/0.5)가 그대로 유지되어 점 위치는 안 바뀐다.
    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative; width:14px; height:14px;";

    // 칩 라벨 — 배경은 마커 점과 같은 색, 글자는 흰색(대비용 그림자 포함).
    const label = document.createElement("div");
    label.style.cssText =
      "position:absolute; left:50%; bottom:100%; transform:translate(-50%,-6px);" +
      `background:${color}; color:#fff;` +
      "padding:3px 7px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.3);" +
      "white-space:nowrap; text-align:center; line-height:1.25; pointer-events:none;" +
      "text-shadow:0 1px 1px rgba(0,0,0,.28); font-family:'Noto Sans KR',sans-serif;";
    const nameLine = document.createElement("div");
    nameLine.textContent = b.building_name || "(건물명 미확인)";
    nameLine.style.cssText = "font-size:11px; font-weight:700;";
    label.appendChild(nameLine);
    if (b.latest_price != null){
      const priceLine = document.createElement("div");
      priceLine.textContent = Number(b.latest_price).toLocaleString('ko-KR') + "만원";
      priceLine.style.cssText = "font-size:10.5px; font-weight:600; opacity:.96;";
      label.appendChild(priceLine);
      // 같은 필지의 대체(참고) 거래이면 확정 거래와 구분되게 작은 안내를 덧붙인다.
      if (b.latest_price_exact === false){
        const refLine = document.createElement("div");
        refLine.textContent = "(필지 내 참고가)";
        refLine.style.cssText = "font-size:9px; font-weight:500; opacity:.9;";
        label.appendChild(refLine);
      }
    }
    label.style.display = "none"; // 초기 숨김 — 확대 레벨에 따라 updateMarkerLabels가 토글
    wrap.appendChild(el);
    wrap.appendChild(label);

    const overlay = new kakao.maps.CustomOverlay({
      position: pos, content: wrap, xAnchor: 0.5, yAnchor: 0.5, clickable: true,
    });
    overlay.setMap(kakaoMap);

    // 클릭 = 고정 InfoWindow(기존 동작 유지), 호버 = 가벼운 미리보기 툴팁
    el.addEventListener("click", () => openBuildingInfo(b, pos));
    wrap.addEventListener("mouseenter", () => showHoverTooltip(b, pos));
    wrap.addEventListener("mouseleave", hideHoverTooltip);

    mapOverlays.push(overlay);
    mapLabels.push(label);
    bounds.extend(pos);
    placed++;
  });

  const countLabel = document.getElementById("mapCount");
  if (countLabel) countLabel.textContent = `(${placed}개 건물)`;

  if (emptyEl) emptyEl.style.display = (placed === 0) ? "flex" : "none";

  if (placed > 0 && opts.fit === true){
    kakaoMap.setBounds(bounds);
  }

  // 새로 만든 라벨들의 표시 여부를 현재 확대 레벨 기준으로 즉시 반영
  updateMarkerLabels();

  console.log(`[MAP] 마커 ${placed}개 표시 (필터: ${qs || "없음"})`);
}

async function initMap(){
  const container = document.getElementById("map");
  if (!container) return;

  kakaoMap = new kakao.maps.Map(container, {
    center: new kakao.maps.LatLng(MAP_DEFAULT_CENTER.lat, MAP_DEFAULT_CENTER.lng),
    level: MAP_DEFAULT_LEVEL,
  });

  // 확대/축소(+/-) 버튼 — 휠/핀치줌이 불안정할 때를 위한 명시적 컨트롤.
  // 우측 하단(BOTTOMRIGHT)에 배치하되, 같은 자리의 범례박스(.map-legend)와
  // 겹치지 않도록 범례 높이만큼 bottom 오프셋을 JS로 계산해 위로 띄운다.
  // (우측 상단은 "🔍 검색" 버튼 자리라 비워둔다)
  kakaoMap.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.BOTTOMRIGHT);
  liftZoomControlAboveLegend();
  window.addEventListener("resize", () => setTimeout(liftZoomControlAboveLegend, 150));

  // 확대/축소 시 마커 라벨 표시 여부 토글 (축소된 전국뷰에서는 라벨 숨김)
  kakao.maps.event.addListener(kakaoMap, "zoom_changed", updateMarkerLabels);

  // 풀스크린 레이아웃 대응 — 컨테이너 크기가 폰트 로드/헤더 높이 반영/창 크기변경으로
  // 바뀌면 지도 타일이 회색으로 남으므로 렌더를 다시 맞춘다.
  // (relayout은 렌더 갱신일 뿐 — 마커·검색·API 로직에는 영향 없음)
  const relayoutMap = () => { if (kakaoMap) kakaoMap.relayout(); };
  window.addEventListener("resize", relayoutMap);
  window.addEventListener("load", () => setTimeout(relayoutMap, 120));
  setTimeout(relayoutMap, 300);

  // 최초 로드 — 전체 건물, 기본 시야 유지(bounds 강제 안 함)
  await loadMapMarkers({}, { fit: false });
}

// 줌 컨트롤을 우측 하단 범례박스(.map-legend) 높이 + 여백만큼 위로 띄워 겹침을 막는다.
// SDK DOM에 클래스가 없어 "확대" 버튼(title="확대")에서 절대배치 래퍼를 거슬러 찾는다.
// 컨트롤 렌더가 살짝 늦을 수 있어 잠시 재시도. 범례는 폭에 따라 줄바꿈되어
// 높이가 변하므로(모바일) 실제 offsetHeight로 매번 계산.
function liftZoomControlAboveLegend(attempt){
  attempt = attempt || 0;
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  // SDK 버전에 따라 확대 버튼이 button[title] / img[alt] / 기타 형태로 렌더될 수 있어
  // 여러 선택자를 순서대로 시도한다.
  const btn = mapEl.querySelector('button[title="확대"]')
    || mapEl.querySelector('img[alt="확대"]')
    || mapEl.querySelector('[title*="확대"]')
    || mapEl.querySelector('[alt*="확대"]');
  let wrap = btn ? btn.parentElement : null;
  while (wrap && wrap !== mapEl && getComputedStyle(wrap).position !== "absolute"){
    wrap = wrap.parentElement;
  }
  if (!btn || !wrap || wrap === mapEl){
    if (attempt < 15){ setTimeout(() => liftZoomControlAboveLegend(attempt + 1), 200); return; }
    console.warn("[MAP] 줌 컨트롤 버튼을 찾지 못함 — SDK DOM 구조 변경 가능성. 기본 위치 유지");
    return;
  }
  const legend = document.querySelector(".map-legend");
  let lift = (legend ? legend.offsetHeight : 0) + 12 + 12; // 범례 높이 + 범례 bottom 여백(12px) + 간격(12px)
  // 방어: 범례 높이가 비정상적으로 크게 계산돼도(레이아웃 깨짐 등)
  // 컨트롤이 지도 밖으로 밀려나지 않도록 상한을 둔다.
  const maxLift = Math.max(24, mapEl.offsetHeight - 120); // 지도 위쪽 120px는 항상 남긴다
  lift = Math.min(lift, 240, maxLift);
  // 주의: wrap의 offsetParent가 높이 0인 요소일 수 있어(bottom 기준이 지도가 아님)
  // bottom 지정 시 화면 밖으로 밀려난다 → 지도 실좌표 기준으로 top을 직접 계산한다.
  const mapRect = mapEl.getBoundingClientRect();
  const parentRect = wrap.offsetParent ? wrap.offsetParent.getBoundingClientRect() : mapRect;
  const topPx = (mapRect.bottom - lift - wrap.offsetHeight) - parentRect.top;
  wrap.style.bottom = "auto";
  wrap.style.top = topPx + "px";
  const r = wrap.getBoundingClientRect();
  console.log(`[MAP] 줌 컨트롤을 범례 위로 ${lift}px 올림 — wrap rect: x=${Math.round(r.x)}, y=${Math.round(r.y)}, w=${Math.round(r.width)}, h=${Math.round(r.height)}, 화면(${window.innerWidth}x${window.innerHeight})`);
}

async function openBuildingInfo(b, pos){
  if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
  hideHoverTooltip(true); // 같은 마커에 호버 툴팁 + InfoWindow가 동시에 뜨지 않게 즉시 닫는다.

  // ★ 내용은 호버 툴팁과 완전히 동일한 공용 빌더(buildingInfoInnerHtml)로 생성.
  // 클릭 InfoWindow는 "고정" 역할만 다르다(마우스를 치워도 유지, X로 닫기).
  const content = `
    <div style="padding:10px 12px; min-width:170px; max-width:240px; font-size:12.5px; color:#16202E; font-family:'Noto Sans KR',sans-serif;">
      ${buildingInfoInnerHtml(b)}
    </div>`;
  currentInfoWindow = new kakao.maps.InfoWindow({ position: pos, content, removable: true });
  currentInfoWindow.open(kakaoMap);
}

// InfoWindow 내용은 문자열이라 클릭 핸들러를 인라인으로 붙인다. 버튼의 data 속성에서
// building_name/address를 읽어 좌측 목록과 동일한 toggleFav를 호출하고 별 표시만 갱신한다.
window.toggleFavFromInfo = function(btn){
  const item = {
    building_name: btn.getAttribute("data-name"),
    address: btn.getAttribute("data-address"),
  };
  const ok = toggleFav(item);
  if (ok === false) return false; // 상한 초과 시 표시 변경 안 함
  const active = isFav(item);
  btn.textContent = active ? "★ 관심저장됨" : "☆ 관심저장";
  btn.style.color = active ? "#B4863F" : "#8a94a0";
  return false;
};

// SDK를 autoload=false로 불렀으므로 명시적으로 로드한 뒤 초기화한다.
// SDK 스크립트 로드가 살짝 늦을 수 있어 잠시 폴링하며 기다린다.
(function waitForKakao(retries){
  if (window.kakao && window.kakao.maps){
    kakao.maps.load(initMap);
    return;
  }
  if (retries <= 0){
    console.warn("[MAP] 카카오맵 SDK가 로드되지 않았습니다 — appkey/도메인 등록 상태를 확인하세요.");
    return;
  }
  setTimeout(function(){ waitForKakao(retries - 1); }, 200);
})(30); // 최대 약 6초 대기
document.getElementById("btnSubmitCorrection").addEventListener("click", async () => {
  if (!correctionTarget) return;
  const suggested_lodging_type = document.getElementById("correctionSuggestedType").value;
  const requester_note = document.getElementById("correctionNote").value.trim();
  const resultBox = document.getElementById("correctionResult");

  resultBox.style.display = "block";
  resultBox.style.background = "#EEF1F3";
  resultBox.style.color = "var(--ink-soft)";
  resultBox.textContent = "건축물대장을 다시 조회하고 있습니다…";

  try {
    const res = await fetch("/api/request-correction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sgg_cd: correctionTarget.sgg_cd,
        umd_nm: correctionTarget.umd_nm,
        jibun: correctionTarget.jibun,
        suggested_lodging_type,
        requester_note,
      }),
    });
    const data = await res.json();

    if (data.status === "verified") {
      resultBox.style.background = data.changed ? "#EAF4EE" : "#EEF1F3";
      resultBox.style.color = data.changed ? "#2F7D52" : "var(--ink-soft)";
      resultBox.textContent = (data.changed ? "✓ " : "ℹ ") + data.message;
      if (data.changed) { loadBoard(); }
    } else {
      resultBox.style.background = "#FBEBE9";
      resultBox.style.color = "#B3453A";
      resultBox.textContent = "✕ " + data.message;
    }
  } catch (e) {
    resultBox.style.background = "#FBEBE9";
    resultBox.style.color = "#B3453A";
    resultBox.textContent = "요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  }
});

/* ================= 좌측 사이드 패널 (지도/검색/게시판과 독립) ================= */
let sideTrendChart = null;

async function loadTrendChart(){
  const canvas = document.getElementById("trendChart");
  if (!canvas || typeof Chart === "undefined") return;
  let items = [];
  let granularity = "month";
  try {
    const res = await fetch("/api/monthly-trend");
    const data = await res.json();
    items = data.items || [];
    granularity = data.granularity || "month";
  } catch(e){ console.error("[SIDE] 추세 로드 실패:", e); return; }

  // 월 "2025-08"→"25/08", 분기 "2025-Q1"→"25Q1"
  const labels = items.map(i => granularity === "quarter"
    ? i.ym.slice(2).replace("-", "")
    : i.ym.slice(2).replace("-", "/"));
  const noteEl = document.getElementById("trendGranularityNote");
  if (noteEl) noteEl.textContent = granularity === "quarter" ? "분기별 표시 (기간 24개월 초과)" : "";
  const counts = items.map(i => i.count);
  const sums = items.map(i => Math.round((i.sum_price || 0) / 10000)); // 만원 → 억원

  sideTrendChart = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        { type:"bar", label:"거래건수", data:counts, yAxisID:"y",
          backgroundColor:"#B4863F", borderRadius:3, order:2 },
        { type:"line", label:"거래금액(억)", data:sums, yAxisID:"y1",
          borderColor:"#378ADD", backgroundColor:"#378ADD", borderWidth:2,
          pointRadius:2, tension:.3, order:1 },
      ],
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:"index", intersect:false },
      plugins:{
        legend:{ display:false },
        tooltip:{ callbacks:{ label:(c)=> c.dataset.type === "line"
          ? ` 거래금액 ${c.parsed.y.toLocaleString('ko-KR')}억`
          : ` 거래건수 ${c.parsed.y.toLocaleString('ko-KR')}건` } },
      },
      scales:{
        x:{ grid:{ display:false }, ticks:{ font:{ size:9 } } },
        y:{ position:"left", beginAtZero:true, ticks:{ font:{ size:9 }, precision:0 }, grid:{ color:"#EEF1F3" } },
        y1:{ position:"right", beginAtZero:true, ticks:{ font:{ size:9 } }, grid:{ display:false } },
      },
    },
  });
}

function renderSideTx(t, rank){
  const name = escapeHtml(t.building_name || "(건물명 미확인)");
  const price = Number(t.price || 0).toLocaleString('ko-KR');
  const region = escapeHtml([t.sgg_nm, t.umd_nm].filter(Boolean).join(" "));
  const metaRight = t.deal_date ? ` · ${escapeHtml(t.deal_date)}` : "";
  const rankHtml = rank ? `<span class="st-rank">${rank}</span>` : "";
  // master_building_id가 있으면 건물상세 좌측패널 전환(페이지 이동 없이) — 기존 로직 재사용.
  const mbid = t.master_building_id;
  const clickable = mbid != null && mbid !== "";
  const clickAttrs = clickable
    ? ` class="side-tx is-clickable" onclick="openBuildingDetail(${Number(mbid)}); return false;" title="건물 상세 보기"`
    : ` class="side-tx"`;
  return `<div${clickAttrs}>
    <div class="st-left">
      <div class="st-name">${rankHtml}${name}</div>
      <div class="st-meta">${region}${metaRight}</div>
    </div>
    <div class="st-price">${price}<span style="font-size:10px;">만</span></div>
  </div>`;
}

async function loadSideTx(size){
  const box = document.getElementById("sideTxList");
  const moreBtn = document.getElementById("btnMoreTx");
  if (!box) return;
  box.innerHTML = `<div class="side-empty">불러오는 중…</div>`;
  let items = [];
  try {
    const res = await fetch(`/api/transactions?size=${size}&page=1`);
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    box.innerHTML = `<div class="side-empty">불러오기 오류</div>`;
    return;
  }
  if (!items.length){
    box.innerHTML = `<div class="side-empty">실거래 내역이 없습니다.</div>`;
    if (moreBtn) moreBtn.style.display = "none";
    return;
  }
  box.innerHTML = items.map(t => renderSideTx(t)).join("");
  if (moreBtn) moreBtn.style.display = (size <= 5) ? "block" : "none";
}

async function loadSideFavorites(){
  const box = document.getElementById("sideFavList");
  if (!box) return;
  const favKeys = (typeof getFavorites === "function" ? getFavorites() : [])
    .slice().reverse().slice(0, 5); // 최근 저장 우선, 최대 5개
  if (!favKeys.length){
    box.innerHTML = `<div class="side-empty">저장된 관심물건이 없습니다.<br>목록에서 ☆를 눌러 추가하세요.</div>`;
    return;
  }
  box.innerHTML = `<div class="side-empty">불러오는 중…</div>`;
  let items = [];
  try {
    const res = await fetch(`/api/favorites?keys=${encodeURIComponent(favKeys.join(","))}`);
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    box.innerHTML = `<div class="side-empty">불러오기 오류</div>`;
    return;
  }
  // 저장 순서(최근 우선)를 유지하려고 favKeys 순서대로 재정렬한다.
  // /api/favorites는 deal_date DESC 정렬 → 관심키별 첫 항목(최신 거래)을 유지한다.
  const byKey = {};
  items.forEach(t => {
    const key = `${t.building_name}|${t.address}`;
    if (!(key in byKey)) byKey[key] = t;
  });
  const ordered = favKeys.map(k => byKey[k]).filter(Boolean);
  if (!ordered.length){
    box.innerHTML = `<div class="side-empty">관심물건 정보를 찾을 수 없습니다.</div>`;
    return;
  }
  box.innerHTML = ordered.map((t, i) => renderSideTx(t, i + 1)).join("");
}

/* ================= 건물 상세: 좌측 패널 전환 ================= */
/* /building/<id> 를 별도 페이지로 이동하지 않고, 지도는 그대로 둔 채
   좌측 패널(.side-panel) 내용만 건물 상세로 통째로 교체한다.
   (static/building.html에 있던 HTML/차트 코드를 그대로 가져와 사용) */

// 기본(홈) 좌측 패널의 원본 HTML을 최초 1회 저장해두고, "전체 목록으로" 복귀 시 되돌린다.
const DEFAULT_SIDE_PANEL_HTML = document.querySelector(".side-panel").innerHTML;

// ---- 메인 좌측 패널: 행정(전국 신고율) + 위탁정보/하우스키핑/금융(등록 업체 수) 집계 ----
// 등록 수가 이 값 미만이면 숫자를 노출하지 않고 모집 문구만 보여준다 (전속중개사/위탁/하우스키핑/금융 공통)
const SIDE_COUNT_THRESHOLD = 10;
async function loadSideStats(){
  const regBox = document.getElementById("sideRegRate");
  if (regBox){
    try {
      const res = await fetch("/api/stats/registration-rate");
      const d = await res.json();
      if (res.ok && d.ok && d.rate !== null){
        regBox.classList.remove("side-soon");
        regBox.innerHTML =
          `<div style="font-size:20px; font-weight:700; color:var(--brass-dark);">전국 ${d.rate}%</div>` +
          `<div style="font-size:12px; color:var(--ink-soft); margin-top:3px;">총 ${d.buildings.toLocaleString()}개 건물 · ${d.total_units.toLocaleString()}실 중 ${d.biz_units.toLocaleString()}실 신고</div>`;
      } else {
        regBox.textContent = "신고율 데이터를 불러오지 못했습니다.";
      }
    } catch(e){
      regBox.textContent = "신고율 데이터를 불러오지 못했습니다.";
    }
  }

  // 전속중개사 카드 — 승인된 중개사 수 (하우스 계정 제외, 공개 API)
  // 노출 기준: SIDE_COUNT_THRESHOLD(10) 미만이면 숫자를 감추고 모집 문구만 노출 (내부 정보 취급)
  const agentBox = document.getElementById("sideAgentCount");
  if (agentBox){
    try {
      const res = await fetch("/api/stats/agent-count");
      const d = await res.json();
      if (res.ok && d.ok){
        const n = d.count || 0;
        if (n >= SIDE_COUNT_THRESHOLD){
          agentBox.classList.remove("side-soon");
          agentBox.innerHTML = `<div style="font-size:14px; font-weight:700; color:var(--ink);">등록된 전속중개사 ${n}명</div>`;
        } else {
          agentBox.textContent = "건물별 전속중개사를 모집하고 있습니다.";
        }
      } else {
        agentBox.textContent = "중개사 정보를 불러오지 못했습니다.";
      }
    } catch(e){
      agentBox.textContent = "중개사 정보를 불러오지 못했습니다.";
    }
  }

  const opBoxes = {
    consign: document.getElementById("sideOpConsign"),
    housekeeping: document.getElementById("sideOpHousekeeping"),
    finance: document.getElementById("sideOpFinance"),
  };
  if (opBoxes.consign || opBoxes.housekeeping || opBoxes.finance){
    let counts = null;
    try {
      const res = await fetch("/api/stats/operator-counts");
      const d = await res.json();
      if (res.ok && d.ok) counts = d;
    } catch(e){ /* 아래 공통 처리 */ }
    Object.keys(opBoxes).forEach((k) => {
      const box = opBoxes[k];
      if (!box) return;
      if (!counts){ box.textContent = "업체 정보를 불러오지 못했습니다."; return; }
      const n = counts[k] || 0;
      if (n >= SIDE_COUNT_THRESHOLD){
        box.classList.remove("side-soon");
        box.innerHTML = `<div style="font-size:14px; font-weight:700; color:var(--ink);">등록된 업체 ${n}곳</div>`;
      } else {
        // 10곳 미만이면 실제 숫자는 감추고 모집 문구만 (내부 정보 취급)
        box.textContent = "지원업체를 찾고 있습니다.";
      }
    });
  }
}

function initDefaultSidePanel(){
  document.getElementById("btnMoreTx")?.addEventListener("click", () => loadSideTx(20));
  loadTrendChart();
  loadSideTx(5);
  loadSideFavorites();
  loadSideStats();
}

// 건물 상세 전용 상태/차트
let buildingDetailChart = null;
// 실거래목록은 페이지네이션 대신 "더보기" 방식: 처음 5건 → 누를 때마다 20건씩 더 불러온다.
const B_TX_INITIAL = 5;
const B_TX_STEP = 20;
let bTxShown = B_TX_INITIAL, bTxTotal = 0;

const B_LODGING_BADGE = { "생활": "생숙", "호텔": "호텔", "콘도": "콘도" };
function detailBadgeLabel(v){
  if (!v) return "미분류";
  return v.split("·").map(x => B_LODGING_BADGE[x] || x).join("·");
}

function buildingPanelSkeleton(){
  return `
    <section class="side-card">
      <button id="btnBackToList" class="side-more" style="margin-top:0; text-align:left;">← 전체 목록으로</button>
    </section>

    <section class="side-card" id="bHeaderCard">
      <div class="side-empty">불러오는 중…</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">실거래추세 <span class="side-sub" id="bTrendGranularityNote"></span></div>
      <div class="side-chart-wrap"><canvas id="bTrendChart"></canvas></div>
      <div class="side-legend">
        <span><i class="lg-bar"></i>거래건수</span>
        <span><i class="lg-line"></i>거래금액(억)</span>
      </div>
      <div id="bTrendEmpty" class="side-empty" style="display:none;">실거래 내역이 없습니다.</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">실거래목록 <span class="side-sub" id="bTxTotalLabel"></span></div>
      <div id="bTxTableWrap" style="overflow-x:auto;"><div class="side-empty">불러오는 중…</div></div>
      <div id="bTxMoreWrap" style="display:none; text-align:center; margin-top:12px;">
        <button id="bTxMore" class="side-more" style="width:auto; padding:7px 18px; margin-top:0;">더보기</button>
      </div>
      <div style="text-align:center; margin-top:8px;">
        <a id="bTxAllLink" class="side-more" style="display:none; width:auto; padding:7px 18px; margin-top:0; text-decoration:none;" href="/transactions">이 건물 전체 실거래 보기 →</a>
      </div>
    </section>

    <section class="side-card">
      <div class="side-card-title">전속중개사</div>
      <div id="bAgentBox"><div class="side-empty">불러오는 중…</div></div>
    </section>

    <section class="side-card" id="bAdminCard">
      <div class="side-card-title">행정 <span class="side-sub">숙박업영업신고율</span></div>
      <div class="side-empty">불러오는 중…</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">위탁운영</div>
      <div id="bOperatorBox">
        <div style="text-align:center; padding:14px 12px; background:#EEF6E6; border:1px dashed #CFE4B8; border-radius:8px;">
          <div style="font-size:22px; margin-bottom:6px;">🏨</div>
          <div style="font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:4px;">위탁운영 지원업체를 찾고 있습니다</div>
          <div style="font-size:11.5px; color:var(--ink-soft); margin-bottom:10px;">이 건물의 운영을 맡아줄 파트너를 모집합니다.</div>
          <a id="lnkOperatorApply" href="/apply/operator" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:7px 16px; background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8; text-decoration:none;">지원업체로 신청하기</a>
        </div>
      </div>
    </section>

    <section class="side-card">
      <div class="side-card-title">하우스키핑</div>
      <div id="bHousekeepingBox">
        <div style="text-align:center; padding:14px 12px; background:#EEF6E6; border:1px dashed #CFE4B8; border-radius:8px;">
          <div style="font-size:22px; margin-bottom:6px;">🧹</div>
          <div style="font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:4px;">하우스키핑 지원업체를 찾고 있습니다</div>
          <div style="font-size:11.5px; color:var(--ink-soft); margin-bottom:10px;">이 건물의 객실관리를 맡아줄 파트너를 모집합니다.</div>
          <a id="lnkHousekeepingApply" href="/apply/operator" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:7px 16px; background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8; text-decoration:none;">지원업체로 신청하기</a>
        </div>
      </div>
    </section>

    <section class="side-card">
      <div class="side-card-title">금융 <span class="side-sub">대출상품</span></div>
      <div style="overflow-x:auto; margin-bottom:12px;">
        <table class="b-info-table">
          <thead><tr><th>금융기관</th><th>최저이율</th><th>취급지역</th><th>바로가기</th></tr></thead>
          <tbody><tr><td colspan="4" style="text-align:center; color:var(--ink-soft); padding:14px;">등록된 대출상품이 없습니다.</td></tr></tbody>
        </table>
      </div>
      <div style="text-align:center; padding:14px 12px; background:var(--brass-tint); border:1px dashed #EAD9B8; border-radius:8px;">
        <div style="font-size:22px; margin-bottom:6px;">💰</div>
        <div style="font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:4px;">대출상담사를 찾고 계신가요?</div>
        <div style="font-size:11.5px; color:var(--ink-soft); margin-bottom:10px;">매입·잔금 대출 상담 전문가를 연결해 드립니다.</div>
        <button class="side-more" style="width:auto; margin-top:0; padding:7px 16px;">대출상담 문의하기</button>
      </div>
    </section>

    <section class="side-card" id="bBldgInfoCard">
      <div class="side-card-title">건축정보 <span class="side-sub">표제부</span></div>
      <div class="side-empty">불러오는 중…</div>
    </section>

    <section class="side-card" id="bStoresCard">
      <div class="side-card-title">상거래정보 <span class="side-sub">주변 상가업소</span></div>
      <div class="side-soon">준비 중
        <div class="side-soon-desc">주변 상가업소 정보를 준비하고 있습니다.</div>
      </div>
    </section>`;
}

function bStat(label, value){
  // value/label은 내부에서 escape → 호출부에서 별도 escapeHtml 불필요(누락 시 XSS 방지)
  return `<div style="flex:1; min-width:100px;">
    <div style="font-size:11px; color:var(--ink-soft); font-weight:600; margin-bottom:3px;">${escapeHtml(String(label))}</div>
    <div style="font-family:'JetBrains Mono',monospace; font-size:16px; font-weight:700; color:var(--ink);">${escapeHtml(String(value))}</div>
  </div>`;
}

async function loadBuildingHeader(id){
  const headerCard = document.getElementById("bHeaderCard");
  const adminCard = document.getElementById("bAdminCard");
  let b;
  try {
    const res = await fetch("/api/building/" + id);
    if (!res.ok) throw new Error(res.status);
    b = await res.json();
  } catch(e){
    headerCard.innerHTML = `<div class="side-empty">건물 정보를 불러오지 못했습니다.</div>`;
    return;
  }

  const color = markerColor(b.lodging_type);
  const badge = `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:${color}; padding:2px 9px; border-radius:6px; vertical-align:middle;">${escapeHtml(detailBadgeLabel(b.lodging_type))}</span>`;
  const units = b.units != null ? Number(b.units).toLocaleString('ko-KR') + "실" : "-";
  const bizUnits = b.biz_units != null ? Number(b.biz_units).toLocaleString('ko-KR') + "실" : "-";
  const bName = b.building_name || "(건물명 미확인)";

  // 실거래목록 하단 "이 건물 전체 실거래 보기" — 건물명이 있을 때만 노출.
  const txAllLink = document.getElementById("bTxAllLink");
  if (txAllLink && b.building_name){
    txAllLink.href = "/transactions?q=" + encodeURIComponent(b.building_name);
    txAllLink.style.display = "inline-block";
  }

  // 주용도1/2 — lodging_type("호텔·콘도")을 분리해 전체 명칭으로 표시. 없으면 "-".
  const useParts = (b.lodging_type || "").split("·").filter(Boolean);
  const use1 = useParts[0] ? (LODGING_LABELS[useParts[0]] || useParts[0]) : "-";
  const use2 = useParts[1] ? (LODGING_LABELS[useParts[1]] || useParts[1]) : "-";

  // 관심저장/실거래알림은 좌측 목록과 동일한 키(building_name|address)를 사용. address가
  // 없는(=거래이력 없는) 건물은 두 버튼을 비활성화한다.
  // 실거래 지번주소(b.address)가 있으면 그대로(좌측 목록과 키 일치), 없으면 마스터
  // 도로명주소(b.road_address)로 폴백 → 거래이력 없어도 주소만 있으면 버튼 활성화.
  const favAddr = (b.address != null && b.address !== "") ? b.address : (b.road_address || "");
  const favItem = { building_name: b.building_name, address: favAddr };
  const favKeyStr = favKey(favItem); // 관심저장과 동일한 키 규칙으로 알림도 저장한다
  const canFav = favAddr !== "";

  // 표제부 백필값 — 헤더 요약에도 반영 (없으면 "-")
  const useAprShort = (b.use_apr_day != null && b.use_apr_day !== "")
    ? String(b.use_apr_day).slice(0, 7).replace("-", ".") : "-";
  const pkngTxt = (b.tot_pkng_cnt != null && b.tot_pkng_cnt !== "")
    ? Number(b.tot_pkng_cnt).toLocaleString("ko-KR") + "대" : "-";
  const flrTxt = (b.grnd_flr_cnt != null || b.ugrnd_flr_cnt != null)
    ? `${b.grnd_flr_cnt != null ? b.grnd_flr_cnt : "-"} / ${b.ugrnd_flr_cnt != null ? b.ugrnd_flr_cnt : "-"}` : "-";

  headerCard.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px;">
      <h1 style="font-size:17px; font-weight:700; color:var(--ink); margin:0;">${escapeHtml(bName)}</h1>
      ${badge}
    </div>
    <div style="font-size:12px; color:var(--ink-soft); margin-bottom:12px;">${escapeHtml(b.road_address || "주소 미확인")}</div>
    <div class="b-actions">
      <button type="button" id="bAlertBtn" class="b-icon-btn" title="실거래 알림">🔔<span class="b-icon-label">실거래알림</span></button>
      <button type="button" id="bFavBtn" class="b-icon-btn" title="관심 저장">⭐<span class="b-icon-label">관심저장</span></button>
      <button type="button" id="bShareBtn" class="b-icon-btn" title="공유">🔗<span class="b-icon-label">공유</span></button>
    </div>
    <div style="display:flex; gap:14px; flex-wrap:wrap; border-top:1px solid var(--line); padding-top:12px;">
      ${bStat("주용도1", use1)}
      ${bStat("주용도2", use2)}
      ${bStat("준공월", useAprShort)}
      ${bStat("총 호실", units)}
      ${bStat("영업신고 호수", bizUnits)}
      ${bStat("총주차", pkngTxt)}
      ${bStat("층수(지상/지하)", flrTxt)}
    </div>`;

  // 헤더 액션 버튼 배선 — 관심저장/실거래알림 상태 동기화 + 공유
  const alertBtn = document.getElementById("bAlertBtn");
  const favBtn = document.getElementById("bFavBtn");
  const shareBtn = document.getElementById("bShareBtn");
  function syncFavBtn(){
    const on = canFav && isFav(favItem);
    favBtn.classList.toggle("on", on);
    favBtn.querySelector(".b-icon-label").textContent = on ? "저장됨" : "관심저장";
  }
  function syncAlertBtn(){
    const on = canFav && isAlertOn(favKeyStr);
    alertBtn.classList.toggle("on", on);
    alertBtn.querySelector(".b-icon-label").textContent = on ? "알림켜짐" : "실거래알림";
  }
  // 헤더 알림 새로고침(refreshAlertsUI) 시 현재 열린 B패널 버튼을 다시 그리기 위한 훅.
  window.__syncOpenAlertBtn = function(){ if (canFav) syncAlertBtn(); };
  if (canFav){
    // 서버 구독 목록이 아직 로드 전이면 로드 후 버튼 상태 반영.
    if (window.__livingstayLoggedIn && !alertsLoaded) loadServerAlerts(syncAlertBtn);
    syncFavBtn(); syncAlertBtn();
    favBtn.addEventListener("click", () => { const ok = toggleFav(favItem); if (ok !== false) syncFavBtn(); });
    alertBtn.addEventListener("click", () => {
      if (!window.__livingstayLoggedIn){ alert("실거래 알림은 로그인이 필요합니다."); return; }
      const wasOn = alertKeySet.has(favKeyStr);
      // 낙관적 업데이트 → 서버 반영. 실패하면 되돌린다.
      if (wasOn) alertKeySet.delete(favKeyStr); else alertKeySet.add(favKeyStr);
      syncAlertBtn();
      fetch("/api/alerts/mine", {
        method: wasOn ? "DELETE" : "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ building_name: favItem.building_name, address: favItem.address })
      })
      .then(function(r){ if (!r.ok) throw new Error("fail"); })
      .catch(function(){
        if (wasOn) alertKeySet.add(favKeyStr); else alertKeySet.delete(favKeyStr);
        syncAlertBtn();
        alert("알림 설정에 실패했습니다. 잠시 후 다시 시도해주세요.");
      });
    });
  } else {
    [favBtn, alertBtn].forEach(btn => {
      btn.disabled = true;
      btn.classList.add("disabled");
      btn.title = "실거래 이력이 있는 건물만 이용할 수 있습니다";
    });
  }
  shareBtn.addEventListener("click", async () => {
    const url = location.href;
    const shareData = { title: `${bName} 실거래 · 홈앤스테이`, url };
    if (navigator.share){
      try { await navigator.share(shareData); } catch(e){ /* 사용자가 취소 */ }
    } else if (navigator.clipboard){
      try { await navigator.clipboard.writeText(url); alert("링크가 복사되었습니다."); }
      catch(e){ prompt("아래 주소를 복사하세요:", url); }
    } else {
      prompt("아래 주소를 복사하세요:", url);
    }
  });

  // [2] 행정운영 표 — 숙박업 영업신고 현황을 표로 정리. 담당부처/연락처는 준비중.
  let rateDisplay;
  if (b.biz_units != null && b.units != null && Number(b.units) > 0){
    rateDisplay = Math.round(Number(b.biz_units) / Number(b.units) * 100) + "%";
  } else {
    rateDisplay = "확인 불가";
  }
  const notReported = (b.units != null && b.biz_units != null)
    ? Math.max(Number(b.units) - Number(b.biz_units), 0).toLocaleString('ko-KR') + "실"
    : "-";
  // 담당부처/연락처: 매칭된 경우만 표시. 시/도 대표 폴백이면 부서명 뒤에 작은 회색 꼬리표.
  const authMatched = b.authority_dept != null && b.authority_dept !== "";
  const fallbackTag = (b.authority_source === "fallback")
    ? ` <span style="color:var(--ink-soft); font-size:12px;">(시/도 대표)</span>` : "";
  const deptCell = authMatched
    ? `${escapeHtml(b.authority_dept)}${fallbackTag}`
    : `<span style="color:var(--ink-soft);">확인중</span>`;
  const phoneCell = authMatched
    ? ((b.authority_phone && b.authority_phone !== "-") ? escapeHtml(b.authority_phone) : "-")
    : `<span style="color:var(--ink-soft);">확인중</span>`;
  adminCard.innerHTML = `
    <div class="side-card-title">행정운영 <span class="side-sub">숙박업영업신고</span></div>
    <table class="b-info-table" style="margin-bottom:12px;">
      <tbody>
        <tr><th>신고율</th><td>${rateDisplay}</td></tr>
        <tr><th>호실수</th><td>${units}</td></tr>
        <tr><th>신고</th><td>${bizUnits}</td></tr>
        <tr><th>미신고</th><td>${notReported}</td></tr>
        <tr><th>담당부처</th><td>${deptCell}</td></tr>
        <tr><th>연락처</th><td>${phoneCell}</td></tr>
      </tbody>
    </table>
    <a href="https://jnjclub.co.kr/" target="_blank" rel="noopener noreferrer" style="display:block; margin-top:0;" title="숙박업등록·위탁운영 무료 상담 신청">
      <img src="/static/banner_biz_report.png" alt="우수부동산서비스인증 — 숙박업등록·위탁운영 의뢰하기, 무료 상담 신청" style="display:block; width:100%; height:auto; border-radius:10px;" />
    </a>`;

  renderBuildingAgent(b.agent, id, bName);

  // 위탁운영/하우스키핑 카드의 "지원업체로 신청하기" 링크에 건물 정보 연결
  // (실제 업종(category) 선택은 신청폼 안에서 함 — agent 신청 링크와 동일 패턴)
  const operApplyHref = `/apply/operator?building_id=${id != null ? encodeURIComponent(id) : ""}&building_name=${encodeURIComponent(bName || "")}`;
  ["lnkOperatorApply", "lnkHousekeepingApply"].forEach((lid) => {
    const a = document.getElementById(lid);
    if (a) a.href = operApplyHref;
  });

  // 담당 운영업체가 등록된 건물이면 유치 문구 대신 업체명 + 프로필 링크 표시
  renderBuildingOperators(b.operators);

  // 건축정보(표제부) — 표제부 백필 전까지는 값이 없어 "-"로 표시. 백엔드가 아래 필드를
  // /api/building/<id> 응답에 채우면 코드 수정 없이 자동으로 값이 나타난다.
  const bldgInfoCard = document.getElementById("bBldgInfoCard");
  if (bldgInfoCard){
    const fmtNum = (v, suffix) => (v != null && v !== "") ? Number(v).toLocaleString('ko-KR') + suffix : "-";
    const fmtTxt = (v) => (v != null && v !== "") ? escapeHtml(String(v)) : "-";
    const pairs = [
      ["연면적", fmtNum(b.tot_area, " ㎡")],
      ["대지면적", fmtNum(b.plat_area, " ㎡")],
      ["세대수", fmtNum(b.hhld_cnt, "세대")],
      ["준공월", fmtTxt(b.use_apr_day)],
      ["구조", fmtTxt(b.strct_nm)],
      ["지상층수", fmtNum(b.grnd_flr_cnt, "층")],
      ["지하층수", fmtNum(b.ugrnd_flr_cnt, "층")],
      ["총주차대수", fmtNum(b.tot_pkng_cnt, "대")],
    ];
    const cells = pairs.map(([k, v]) => `
      <div class="b-bldg-cell">
        <div class="b-bldg-k">${k}</div>
        <div class="b-bldg-v">${v}</div>
      </div>`).join("");
    bldgInfoCard.innerHTML = `
      <div class="side-card-title">건축정보 <span class="side-sub">표제부</span></div>
      <div class="b-bldg-grid">${cells}</div>`;
  }

  // 상거래정보(이 건물의 상가업소) — 실패/0건이면 기존 "준비 중" 카드 유지
  loadBuildingStores(id);
}

// 상거래정보 카드 — /api/building/<id>/nearby-stores 로 이 건물(지번)의
// 상가업소를 업종별 요약 + 층별 목록으로 그린다. 최대 15개 먼저 보여주고 "더보기".
async function loadBuildingStores(buildingId){
  const card = document.getElementById("bStoresCard");
  if (!card) return;
  let data;
  try {
    const res = await fetch(`/api/building/${buildingId}/nearby-stores`);
    if (!res.ok) return; // 실패 → "준비 중" 유지
    data = await res.json();
  } catch(e){ return; }
  if (!data || !data.available || !Array.isArray(data.stores) || data.stores.length === 0) return;

  const summary = (data.categories || [])
    .map(c => `${escapeHtml(c.category)} <b>${Number(c.count).toLocaleString('ko-KR')}</b>`)
    .join(" · ");

  const rowHtml = (s) => {
    let floorTxt = "";
    if (s.floor !== "" && s.floor != null){
      const n = Number(s.floor);
      floorTxt = isNaN(n) ? String(s.floor) : (n < 0 ? `지하 ${Math.abs(n)}층` : `${n}층`);
    }
    return `
      <div style="display:flex; align-items:center; gap:8px; padding:6px 2px; border-bottom:1px solid var(--line, #eee); font-size:12.5px;">
        <span style="flex:0 0 52px; color:var(--brass-dark); font-weight:700;">${floorTxt ? escapeHtml(floorTxt) : "-"}</span>
        <span style="flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink);">${escapeHtml(s.name)}</span>
        <span style="flex:0 0 auto; color:var(--ink-soft); font-size:11.5px;">${escapeHtml(s.category || "")}</span>
      </div>`;
  };

  const FIRST = 15;
  const first = data.stores.slice(0, FIRST).map(rowHtml).join("");
  const rest = data.stores.slice(FIRST).map(rowHtml).join("");

  card.innerHTML = `
    <div class="side-card-title">상거래정보 <span class="side-sub">건물 내 상가업소 ${Number(data.total).toLocaleString('ko-KR')}곳</span></div>
    ${summary ? `<div style="font-size:12.5px; color:var(--ink-soft); margin:2px 0 8px; line-height:1.6;">${summary}</div>` : ""}
    <div style="max-height:280px; overflow-y:auto;">
      <div>${first}</div>
      ${rest ? `<div id="bStoresRest" style="display:none;">${rest}</div>` : ""}
    </div>
    ${rest ? `<button type="button" class="side-more" id="bStoresMoreBtn">더보기 (${data.stores.length - FIRST}곳)</button>` : ""}
    <div style="font-size:11px; color:var(--ink-soft); margin-top:8px;">출처: 소상공인시장진흥공단 상가(상권)정보</div>`;

  const moreBtn = document.getElementById("bStoresMoreBtn");
  if (moreBtn){
    moreBtn.addEventListener("click", () => {
      const restBox = document.getElementById("bStoresRest");
      if (restBox) restBox.style.display = "";
      moreBtn.remove();
    });
  }
}

// 위탁운영/하우스키핑 카드 — 이 건물의 담당 운영업체(operator_buildings 등록 + approved)가
// 있으면 유치(모집) 문구 대신 업체명 + "프로필 보기 →" 링크를 보여준다. 없으면 기본 HTML 유지.
//   위탁운영 카드 ← category '위탁운영'
//   하우스키핑 카드 ← category '청소' | '세탁' | '용품'
function renderBuildingOperators(operators){
  const ops = Array.isArray(operators) ? operators : [];
  const pick = (cats) => ops.find(o => cats.includes(o.category));
  const paint = (boxId, op) => {
    if (!op) return; // 담당 업체 없음 → 기존 유치 카드 그대로
    const box = document.getElementById(boxId);
    if (!box) return;
    box.innerHTML = `
      <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        <div style="width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center; font-size:18px;">🏨</div>
        <div style="flex:1; min-width:130px;">
          <div style="font-size:14px; font-weight:700; color:var(--ink);">${escapeHtml(op.company_name || "-")}</div>
          <div style="font-size:12px; color:var(--ink-soft); margin-top:2px;">${escapeHtml(op.category || "")} 담당 업체</div>
        </div>
      </div>
      ${op.subdomain_slug ? `<div style="margin-top:8px; text-align:right;"><a href="/operator/${encodeURIComponent(op.subdomain_slug)}" style="font-size:12px; font-weight:600; color:var(--brass-dark); text-decoration:none;">프로필 보기 →</a></div>` : ""}`;
  };
  paint("bOperatorBox", pick(["위탁운영"]));
  paint("bHousekeepingBox", pick(["청소", "세탁", "용품"]));
}

function renderBuildingAgent(agent, buildingId, buildingName){
  const box = document.getElementById("bAgentBox");
  if (!box) return;
  if (agent){
    box.innerHTML = `
      <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        <div style="width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center; font-size:18px;">🏢</div>
        <div style="flex:1; min-width:130px;">
          <div style="font-size:14px; font-weight:700; color:var(--ink);">${escapeHtml(agent.office_name || "-")}</div>
          <div style="font-size:12px; color:var(--ink-soft); margin-top:2px;">대표 ${escapeHtml(agent.owner_name || "-")}</div>
        </div>
        ${agent.phone ? `<a href="tel:${escapeHtml(agent.phone)}" class="side-more" style="width:auto; margin-top:0; padding:7px 14px; text-decoration:none; text-align:center;">📞 ${escapeHtml(agent.phone)}</a>` : ""}
      </div>
      ${agent.subdomain_slug ? `<div style="margin-top:8px; text-align:right;"><a href="/agent/${encodeURIComponent(agent.subdomain_slug)}" style="font-size:12px; font-weight:600; color:var(--brass-dark); text-decoration:none;">프로필 보기 →</a></div>` : ""}`;
  } else {
    box.innerHTML = `
      <div style="text-align:center; padding:16px 12px; background:var(--brass-tint); border:1px dashed #EAD9B8; border-radius:8px;">
        <div style="font-size:24px; margin-bottom:6px;">🔎</div>
        <div style="font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:4px;">이 건물의 전속 중개사를 찾고 있습니다</div>
        <div style="font-size:11.5px; color:var(--ink-soft); margin-bottom:10px;">이 건물을 전담할 중개사무소를 모집합니다.</div>
        <a href="/apply/agent?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:7px 16px; text-decoration:none;">이 건물에 전속중개사로 신청하기</a>
      </div>`;
  }
}

async function loadBuildingTrend(id){
  const canvas = document.getElementById("bTrendChart");
  if (!canvas || typeof Chart === "undefined") return;
  let items = [];
  let granularity = "month";
  try {
    const res = await fetch("/api/monthly-trend?building_id=" + id);
    const data = await res.json();
    items = data.items || [];
    granularity = data.granularity || "month";
  } catch(e){ console.error("[상세] 추세 로드 실패:", e); return; }

  if (!items.length || items.every(i => !i.count)){
    canvas.style.display = "none";
    const empty = document.getElementById("bTrendEmpty");
    if (empty) empty.style.display = "block";
    return;
  }

  const noteEl = document.getElementById("bTrendGranularityNote");
  if (noteEl) noteEl.textContent = granularity === "quarter" ? "분기별 표시 (기간 24개월 초과)" : "";
  // 월 "2025-08"→"25/08", 분기 "2025-Q1"→"25Q1"
  const labels = items.map(i => granularity === "quarter"
    ? i.ym.slice(2).replace("-", "")
    : i.ym.slice(2).replace("-", "/"));
  const counts = items.map(i => i.count);
  const sums = items.map(i => Math.round((i.sum_price || 0) / 10000));

  buildingDetailChart = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        { type:"bar", label:"거래건수", data:counts, yAxisID:"y",
          backgroundColor:"#B4863F", borderRadius:3, order:2 },
        { type:"line", label:"거래금액(억)", data:sums, yAxisID:"y1",
          borderColor:"#378ADD", backgroundColor:"#378ADD", borderWidth:2,
          pointRadius:2, tension:.3, order:1 },
      ],
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:"index", intersect:false },
      plugins:{
        legend:{ display:false },
        tooltip:{ callbacks:{ label:(c)=> c.dataset.type === "line"
          ? ` 거래금액 ${c.parsed.y.toLocaleString('ko-KR')}억`
          : ` 거래건수 ${c.parsed.y.toLocaleString('ko-KR')}건` } },
      },
      scales:{
        x:{ grid:{ display:false }, ticks:{ font:{ size:9 } } },
        y:{ position:"left", beginAtZero:true, ticks:{ font:{ size:9 }, precision:0 }, grid:{ color:"#EEF1F3" } },
        y1:{ position:"right", beginAtZero:true, ticks:{ font:{ size:9 } }, grid:{ display:false } },
      },
    },
  });
}

function bDealTypeTag(v){
  return v === "직거래"
    ? `<span class="tag brk">직거래</span>`
    : `<span class="tag med">중개거래</span>`;
}

async function loadBuildingTx(id){
  const wrap = document.getElementById("bTxTableWrap");
  const moreWrap = document.getElementById("bTxMoreWrap");
  if (!wrap) return;
  wrap.innerHTML = `<div class="side-empty">불러오는 중…</div>`;

  // /api/transactions 는 요청당 size 상한이 200이라, 목표 건수(bTxShown)가 200을 넘으면
  // 200건씩 여러 페이지를 이어 받아 합친 뒤 앞에서 bTxShown개만 보여준다.
  let items = [];
  bTxTotal = 0;
  try {
    const size = Math.min(bTxShown, 200);
    let page = 1;
    while (true){
      const res = await fetch(`/api/transactions?building_id=${id}&page=${page}&size=${size}`);
      const data = await res.json();
      bTxTotal = data.total || 0;
      const batch = data.items || [];
      items = items.concat(batch);
      if (items.length >= bTxShown || items.length >= bTxTotal || batch.length < size) break;
      page++;
    }
  } catch(e){
    wrap.innerHTML = `<div class="side-empty">실거래 목록을 불러오지 못했습니다.</div>`;
    return;
  }
  items = items.slice(0, bTxShown);
  const totalLabel = document.getElementById("bTxTotalLabel");
  if (totalLabel) totalLabel.textContent = bTxTotal ? `총 ${bTxTotal.toLocaleString('ko-KR')}건` : "";

  if (!items.length){
    wrap.innerHTML = `<div class="side-empty">실거래 이력이 없습니다.</div>`;
    if (moreWrap) moreWrap.style.display = "none";
    return;
  }

  // 건물명·주소는 이미 헤더에 있으므로 목록에서는 생략하고 일자·전용·층·금액·종류만 보여준다.
  // 패널 폭이 좁아 계약일은 YY.MM.DD로 압축하고, 표는 b-tx-table(table-layout:fixed)로 가로 스크롤을 막는다.
  const fmtDealDate = (d) => d ? escapeHtml(d.slice(2).replace(/-/g, ".")) : "-";
  const rows = items.map(t => `
    <tr>
      <td class="col-date">${fmtDealDate(t.deal_date)}</td>
      <td class="col-area">${t.area != null ? Number(t.area).toFixed(1) : "-"}</td>
      <td class="col-floor">${t.floor ? escapeHtml(String(t.floor)) + "층" : "-"}</td>
      <td class="col-price">${t.price != null ? Number(t.price).toLocaleString('ko-KR') : "-"}</td>
      <td class="col-type">${bDealTypeTag(t.deal_type)}</td>
    </tr>`).join("");

  wrap.innerHTML = `
    <table class="b-tx-table">
      <colgroup><col class="c-date"><col class="c-area"><col class="c-floor"><col class="c-price"><col class="c-type"></colgroup>
      <thead><tr><th>계약일</th><th class="ta-r">전용㎡</th><th class="ta-r">층</th><th class="ta-r">거래금액(만원)</th><th class="ta-r">유형</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  if (moreWrap) moreWrap.style.display = (items.length < bTxTotal) ? "block" : "none";
}

// 좌측 패널을 건물 상세로 교체하고 데이터를 채운다.
function renderBuildingPanel(id){
  const panel = document.querySelector(".side-panel");
  if (!panel) return;
  if (sideTrendChart){ sideTrendChart.destroy(); sideTrendChart = null; }
  if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }

  panel.innerHTML = buildingPanelSkeleton();
  panel.scrollTop = 0;
  panel.classList.add("open"); // 모바일에서도 상세가 보이도록 패널을 펼친다

  document.getElementById("btnBackToList").addEventListener("click", () => {
    history.pushState({}, "", "/");
    restoreDefaultPanel();
  });
  document.getElementById("bTxMore").addEventListener("click", () => {
    bTxShown += B_TX_STEP;
    loadBuildingTx(id);
  });

  bTxShown = B_TX_INITIAL;
  bTxTotal = 0;
  loadBuildingHeader(id);
  loadBuildingTrend(id);
  loadBuildingTx(id);
}

// 기본(홈) 좌측 패널로 되돌린다.
function restoreDefaultPanel(){
  const panel = document.querySelector(".side-panel");
  if (!panel) return;
  if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }
  if (sideTrendChart){ sideTrendChart.destroy(); sideTrendChart = null; }
  panel.classList.remove("open");
  panel.innerHTML = DEFAULT_SIDE_PANEL_HTML;
  initDefaultSidePanel();
}

// InfoWindow "상세보기 →" 클릭 → 페이지 이동 없이 패널 전환 + URL만 교체
window.openBuildingDetail = function(id){
  history.pushState({ buildingId: id }, "", "/building/" + id);
  if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
  hideHoverTooltip(true); // 호버 툴팁에서 눌러 들어온 경우 툴팁도 즉시 닫는다.
  renderBuildingPanel(id);
  return false;
};

// 브라우저 뒤로/앞으로 가기 대응
window.addEventListener("popstate", () => {
  const m = location.pathname.match(/^\/building\/(\d+)/);
  if (m) renderBuildingPanel(Number(m[1]));
  else restoreDefaultPanel();
});

// 최초 로드: 기본 패널 초기화 후, URL이 /building/<id>면 자동으로 상세를 연다.
initDefaultSidePanel();
(function(){
  const m = location.pathname.match(/^\/building\/(\d+)/);
  if (m) renderBuildingPanel(Number(m[1]));
})();
