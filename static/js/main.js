const FAV_KEY = "livingstay_favorites"; // 마이그레이션 호환용 — 직접 쓰기는 하지 않음
// 관리자 모드: URL에 ?admin=1 을 붙이면 50개까지, 아니면 일반 사용자 5개 제한
const IS_ADMIN = new URLSearchParams(location.search).get("admin") === "1";
const MAX_FAVORITES = IS_ADMIN ? 50 : 5;

let regionTree = {};
let state = { si_do:"", sgg_nm:"", umd_nm:"", q:"", year:"all", lodging_type:"", page:1, size:20, favOnly:false, favKey:null };
let defaultYear = "";

// 로그인 회원의 관심키(building_name|address) 인메모리 캐시
// 비로그인 → 항상 빈 Set → 관심 기능 전체가 로그인 유도로 동작
let serverFavKeys = new Set();

function getFavorites(){ return [...serverFavKeys]; }
function favKey(item){ return `${item.building_name}|${item.address}`; }
function isFav(item){ return serverFavKeys.has(favKey(item)); }

// 서버 /api/favorites/mine 에서 내 관심키 전체를 로드해 인메모리 캐시를 채운다.
async function loadServerFavKeys(){
  serverFavKeys = new Set();
  if (!window.__livingstayLoggedIn) return;
  try {
    const res = await fetch("/api/favorites/mine", { credentials: "same-origin" });
    const data = await res.json();
    (data.items || []).forEach(item => serverFavKeys.add(`${item.building_name}|${item.address}`));
  } catch(e) {}
}

// 로그인 유도 헬퍼
function promptLogin(msg){
  if (msg) alert(msg);
  if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
  else location.href = "/?login=1";
}

function toggleFav(item){
  // 사업자 계정(agent/operator/loan_consultant)은 관심저장 불가 — 로그인 체크보다 먼저
  // (__livingstayLoggedIn은 사업자도 false이므로 순서가 반드시 account_type 먼저여야 함)
  if (window.__livingstayAccountType && window.__livingstayAccountType !== "user"){
    alert("관심저장은 일반회원 전용 기능입니다. 개인 이용을 원하시면 별도로 일반회원 가입해주세요.");
    return false;
  }
  // 하드게이트: 비로그인은 저장 불가
  if (!window.__livingstayLoggedIn){
    promptLogin("로그인하고 관심단지를 저장하면, 이 건물의 새 실거래가 등록될 때 알림을 보내드려요");
    return false;
  }
  const k = favKey(item);
  let clearedActiveFilter = false;
  const wasFav = serverFavKeys.has(k);
  if (wasFav){
    serverFavKeys.delete(k);
    if (state.favKey === k){ state.favKey = null; state.favOnly = false; clearedActiveFilter = true; }
    fetch("/api/favorites/mine", {
      method: "DELETE", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ building_name: item.building_name, address: item.address })
    }).catch(function(){});
  } else {
    if (serverFavKeys.size >= MAX_FAVORITES){
      alert(`관심단지는 최대 ${MAX_FAVORITES}개까지 저장할 수 있습니다.`);
      return false;
    }
    serverFavKeys.add(k);
    fetch("/api/favorites/mine", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        building_name: item.building_name,
        address: item.address,
        // 저장 시점에 이미 알고 있는 master_buildings.id를 함께 저장 —
        // 실거래 없는 건물도 마이페이지에서 상세 링크가 끊기지 않게 한다.
        building_id: (item.building_id != null ? item.building_id : undefined)
      })
    }).catch(function(){});
  }
  updateFavCountLabel();
  renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
  if (clearedActiveFilter){ document.getElementById("chkFavOnly").checked = false; loadBoard(); }
  return true;
}
function removeFav(key){
  serverFavKeys.delete(key);
  const sep = key.indexOf("|");
  if (sep >= 0){
    fetch("/api/favorites/mine", {
      method: "DELETE", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ building_name: key.slice(0, sep), address: key.slice(sep + 1) })
    }).catch(function(){});
  }
  if (state.favKey === key){ state.favKey = null; state.favOnly = false; }
  updateFavCountLabel();
  renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
  loadBoard();
}
// auth.js가 로그인/migrate 후 호출 → 서버에서 관심키 재로드 후 UI 갱신
window.refreshFavoritesUI = async function(){
  await loadServerFavKeys();
  if (typeof updateFavCountLabel === "function") updateFavCountLabel();
  if (typeof renderFavChips === "function") renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
};
// livingstay:auth 이벤트 — 이미 로그인된 상태로 페이지에 진입할 때도 관심키를 로드한다.
// auth.js가 window.dispatchEvent()로 발생시키므로 리스너도 window에 등록해야 함.
// (document.addEventListener는 window 이벤트를 수신하지 못함 — 타깃 불일치 버그 수정)
window.addEventListener("livingstay:auth", async function(){
  await loadServerFavKeys();
  if (typeof updateFavCountLabel === "function") updateFavCountLabel();
  if (typeof renderFavChips === "function") renderFavChips();
  if (typeof loadSideFavorites === "function") loadSideFavorites();
});
function updateFavCountLabel(){
  const el = document.getElementById("favCountLabel");
  if (el) el.textContent = `저장된 관심단지 ${serverFavKeys.size}/${MAX_FAVORITES}개`;
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
    label.title = "건물 상세 보기";
    label.addEventListener("click", async () => {
      try {
        const res = await fetch(`/api/favorites?keys=${encodeURIComponent(k)}`);
        const data = await res.json();
        const item = (data.items || [])[0];
        if (item && item.master_building_id) {
          openBuildingDetail(item.master_building_id);
          return;
        }
      } catch(e){ /* fall through */ }
      filterToFav(k);
    });
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
  // sgg 키는 master_buildings.sgg_text 전체값(예: '경기도 수원시 팔달구').
  // value는 필터 매칭에 그대로 사용; 표시 레이블은 si_do 접두사를 제거해 간결하게 표시.
  const sidoPrefix = state.si_do + ' ';
  selSggNm.innerHTML = '<option value="">전체</option>' +
    Object.keys(sggMap).sort().map(sg => {
      const label = sg.startsWith(sidoPrefix) ? sg.slice(sidoPrefix.length) : sg;
      return `<option value="${sg}">${label} (${sggMap[sg].count})</option>`;
    }).join("");
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
  const lodgingColors = { "생활": "med", "관광": "brk", "일반": "src", "복합": "mixed" };
  const lodgingClass = lodgingColors[t.lodging_type] || "unknown";
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
      year: state.year, lodging_type: state.lodging_type, page: state.page, size: state.size,
      with_total: 1,  // COUNT(*) 실행 — 게시판은 페이지네이션에 total 필요
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
  updateMapForZoom(mapFiltersFromState(), { force: true });
});
function _setLegendActive(type) {
  document.querySelectorAll(".map-legend .lg[data-lodging-type]").forEach(el => {
    el.classList.toggle("active", el.dataset.lodgingType === type && type !== "");
  });
}
document.querySelectorAll(".map-legend .lg[data-lodging-type]").forEach(el => {
  el.addEventListener("click", () => {
    const type = el.dataset.lodgingType;
    // 이미 선택된 항목을 다시 클릭하면 필터 해제
    const toggle = state.lodging_type === type ? "" : type;
    state.lodging_type = toggle;
    state.page = 1;
    document.getElementById("selLodgingType").value = toggle;
    _setLegendActive(toggle);
    loadBoard();
    updateMapForZoom(mapFiltersFromState(), { force: true });
  });
});
document.getElementById("mapLegendTitle").addEventListener("click", () => {
  state.lodging_type = "";
  state.page = 1;
  document.getElementById("selLodgingType").value = "";
  _setLegendActive("");
  loadBoard();
  updateMapForZoom({}, { force: true });
});
document.getElementById("chkFavOnly").addEventListener("change", e=>{
  state.favOnly = e.target.checked; state.favKey = null; state.page = 1;
  renderFavChips(); loadBoard();
});
document.getElementById("btnSearch").addEventListener("click", ()=>{
  state.q = document.getElementById("inputQ").value.trim();
  state.page = 1;
  loadBoard();
  // q(건물명·주소)로 검색하면 결과가 현재 뷰 밖에 있을 수 있으므로 fit:true로 지도를 맞춤
  updateMapForZoom(mapFiltersFromState(), { force: true, fit: !!state.q });
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
  localStorage.removeItem("map_last_view"); // 로고 클릭 = "처음부터" 의도 — 저장 위치도 초기화
  updateMapForZoom({}, { force: true });   // 지도도 전체로 복귀 (줌 레벨 기준 클러스터 또는 마커)
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

// URL ?modal=submit 으로 직접 접근 시 모달 자동 오픈
if (new URLSearchParams(location.search).get("modal") === "submit") {
  submitModal.style.display = "flex";
  document.getElementById("submitResult").style.display = "none";
}
document.getElementById("btnSubmitBuilding").addEventListener("click", async () => {
  const road_address = document.getElementById("submitAddress").value.trim();
  const jibun_address_input = (document.getElementById("submitJibunAddress") || {value:""}).value.trim();
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
      body: JSON.stringify({ road_address, jibun_address_input, building_name_hint, suggested_lodging_type }),
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
const LODGING_COLORS = { "생활": "#378ADD", "관광": "#639922", "일반": "#D46BA3", "복합": "#B39DDB", "준공전": "#616161", "미분류": "#E0E0E0" };
const LODGING_LABELS = { "생활": "생활숙박시설", "관광": "관광숙박시설", "일반": "일반숙박시설", "복합": "복합", "준공전": "준공전", "미분류": "미분류" };
const DEFAULT_MARKER_COLOR = "#9AA5B1";

function markerColor(lodgingType, buildingStatus){
  // 4분류 확정 타입 우선 — 준공전 상태여도 타입색 표시
  if (lodgingType && lodgingType.includes("·")) return LODGING_COLORS["복합"];
  if (lodgingType && LODGING_COLORS[lodgingType]) return LODGING_COLORS[lodgingType];
  // 확정 타입 없음 — building_status로 준공전/미분류 구분
  if (buildingStatus === "허가" || buildingStatus === "착공") return LODGING_COLORS["준공전"];
  return LODGING_COLORS["미분류"];
}
// DEFAULT_MARKER_COLOR(회색)는 이제 "준공전" 배지 전용으로만 남겨둠
// (headerCard의 isPreCompletion 분기에서 이미 "#9AA5B1"로 별도 하드코딩해서
// 쓰고 있으므로 이 변경과 충돌 없음)
function lodgingLabelKo(lodgingType){
  if (!lodgingType) return "미분류";
  return LODGING_LABELS[lodgingType] || lodgingType;
}

let kakaoMap = null;
let currentInfoWindow = null;
let mapOverlays = [];                 // 현재 지도에 찍힌 마커(kakao.maps.Marker) 목록
let mapLabelData = [];                // [{b, pos, overlay, el}] — 라벨 lazy 생성용 데이터
let _markerLoadGen = 0;               // loadMapMarkers 호출마다 증가 — 이전 addChunk 루프 폐기용

// 색상별 MarkerImage 캐시 — SVG 데이터 URI를 반복 생성하지 않는다
const _markerImageCache = {};
function _makeMarkerImage(color){
  if (_markerImageCache[color]) return _markerImageCache[color];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14">` +
    `<circle cx="7" cy="7" r="6" fill="${color}" stroke="white" stroke-width="2"/></svg>`;
  const img = new kakao.maps.MarkerImage(
    'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg),
    new kakao.maps.Size(14, 14),
    { offset: new kakao.maps.Point(7, 7) }
  );
  _markerImageCache[color] = img;
  return img;
}

// 라벨 DOM 요소 생성 — updateMarkerLabels 에서 줌인 시 최초 1회만 호출된다
// 전체 주소 문자열에서 시도·시군구 앞부분을 제거하고 동 이하만 반환한다.
// 예) "부산광역시 수영구 광안동 157-1번지" → "광안동 157-1번지"
// 미분류 마커처럼 building_name이 전체 주소인 경우에 사용한다.
function _stripSidoSgg(addr) {
  if (!addr) return addr;
  const tokens = addr.trim().split(/\s+/);
  let i = 0;
  // 시도 토큰: 특별시/광역시/특별자치시(도)/도/시 로 끝남
  if (i < tokens.length &&
      /(?:특별시|광역시|특별자치시도|특별자치시|특별자치도|도|시)$/.test(tokens[i])) i++;
  // 시군구 토큰: 시/군/구 로 끝남
  if (i < tokens.length && /(?:시|군|구)$/.test(tokens[i])) i++;
  const rest = tokens.slice(i).join(" ");
  return rest || addr; // 파싱 실패 시 원본 반환
}

function _buildLabelEl(b, pos){
  const color = markerColor(b.lodging_type, b.building_status);
  const label = document.createElement("div");
  // PC/모바일 모두 pointer-events:auto — 라벨 클릭으로 바로 건물 상세 이동
  label.style.cssText =
    `background:${color}; color:#fff;` +
    "padding:3px 7px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.3);" +
    "white-space:nowrap; text-align:center; line-height:1.25; pointer-events:auto; cursor:pointer;" +
    "text-shadow:0 1px 1px rgba(0,0,0,.28); font-family:'Noto Sans KR',sans-serif;" +
    "margin-bottom:8px;"; // 마커 점과의 간격
  const nameLine = document.createElement("div");
  // 미분류 건물은 building_name이 전체 주소로 채워진 경우가 많으므로
  // 이미 시군구를 알고 있는 지도 화면에서는 동 이하만 표시한다.
  const isMuibunryu = !b.lodging_type || b.lodging_type === "";
  const displayName = isMuibunryu
    ? (_stripSidoSgg(b.building_name) || "(건물명 미확인)")
    : (b.building_name || "(건물명 미확인)");
  nameLine.textContent = displayName;
  nameLine.style.cssText = "font-size:11px; font-weight:700;";
  label.appendChild(nameLine);
  if (b.latest_price != null){
    const priceLine = document.createElement("div");
    priceLine.textContent = Number(b.latest_price).toLocaleString('ko-KR') + "만원";
    priceLine.style.cssText = "font-size:10.5px; font-weight:600; opacity:.96;";
    label.appendChild(priceLine);
    if (b.latest_price_exact === false){
      const refLine = document.createElement("div");
      refLine.textContent = "(필지 내 참고가)";
      refLine.style.cssText = "font-size:9px; font-weight:500; opacity:.9;";
      label.appendChild(refLine);
    }
  }
  // PC/모바일 공통: 라벨 클릭 → 건물 상세 패널 바로 열기
  if (b.id != null){
    label.addEventListener("click", (e) => {
      e.stopPropagation();
      if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
      history.pushState({ buildingId: b.id }, "", "/building/" + b.id);
      if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/building/" + b.id });
      renderBuildingPanel(b.id);
    });
  }
  return label;
}
const LABEL_MAX_LEVEL = 6;            // 이 확대 레벨 이하(더 가까이)일 때만 라벨 표시
// 클러스터 배지 줌 레벨 임계값 — Kakao Maps 레벨: 숫자 클수록 더 넓은 시야
// level ≥ CLUSTER_SIDO_MIN_LEVEL → 시도 집계 배지
// level CLUSTER_SGG_MIN_LEVEL ~ CLUSTER_SIDO_MIN_LEVEL-1 → 시군구 집계 배지
// level CLUSTER_UMD_MIN_LEVEL ~ CLUSTER_SGG_MIN_LEVEL-1 → 읍면동 집계 배지
// level ≤ LABEL_MAX_LEVEL → 기존 개별 마커
const CLUSTER_SIDO_MIN_LEVEL = 10;
const CLUSTER_SGG_MIN_LEVEL  = 8;
const CLUSTER_UMD_MIN_LEVEL  = 7;

// sido 레벨 배지 좌표 — 도청(시청)소재지 기준.
// xAnchor:0 렌더링과 함께 사용 → 배지 왼쪽 끝이 해당 좌표에 고정되어
// 배지가 도시 지명 우측에 자연스럽게 달라붙음.
const SIDO_POSITION_OVERRIDE = {
  "서울특별시":      { lat: 37.50,  lng: 127.06  }, // 시각 보정: 서울 지명 우측·아래
  "경기도":          { lat: 37.13,  lng: 127.13  }, // 시각 보정: 용인-안성 사이(지명 미침범)
  "인천광역시":      { lat: 37.44,  lng: 126.60  }, // 시각 보정: 인천 지명 좌측 바다
  "강원특별자치도":  { lat: 37.342, lng: 127.921 }, // 원주시청(도청)
  "충청북도":        { lat: 36.75,  lng: 127.60  }, // 시각 보정: 북동쪽(대전·세종과 명확히 분리)
  "충청남도":        { lat: 36.601, lng: 126.660 }, // 홍성군청(도청)
  "대전광역시":      { lat: 36.30,  lng: 127.40  }, // 시각 보정: 남쪽으로 이동
  "세종특별자치시":  { lat: 36.55,  lng: 127.15  }, // 시각 보정: 서쪽(대전과 간격 확보)
  "전북특별자치도":  { lat: 35.824, lng: 127.148 }, // 전주시청(도청)
  "전라남도":        { lat: 34.991, lng: 126.481 }, // 무안군청(도청)
  "광주광역시":      { lat: 35.160, lng: 126.851 }, // 광주시청
  "경상북도":        { lat: 36.566, lng: 128.729 }, // 안동시청(도청)
  "대구광역시":      { lat: 35.871, lng: 128.601 }, // 대구시청
  "경상남도":        { lat: 35.228, lng: 128.682 }, // 창원시청(도청)
  "부산광역시":      { lat: 35.180, lng: 129.075 }, // 부산시청
  "울산광역시":      { lat: 35.540, lng: 129.312 }, // 울산시청
  "제주특별자치도":  { lat: 33.489, lng: 126.498 }, // 제주시청(도청)
};

let _clusterOverlays = [];            // 클러스터 배지 CustomOverlay 목록 — clearMapMarkers에서 함께 제거
let _currentMapMode  = null;          // 'sido'|'sgg'|'umd'|'markers' — 불필요한 재로드 방지
let _lastMapFilters  = {};            // 마지막으로 적용된 지도 필터 (zoom 전환 시 재사용)
const MAP_DEFAULT_CENTER = { lat: 36.35, lng: 126.9 }; // 좌측 사이드패널이 지도 위에 겹쳐 한반도가 왼쪽으로 밀려 보이므로 중심 경도를 서쪽으로 낮춰 가로 중앙 정렬(일본 과다 노출 완화)
const MAP_DEFAULT_LEVEL = 12;         // 속초~완도가 세로로 다 보이는 확대 수준
// 모바일(좁은 세로 화면) 전용 초기뷰 — 세로로 길어 같은 값이면 속초·제주가 잘리므로 별도 값 사용.
// PC 값(MAP_DEFAULT_CENTER/LEVEL)은 그대로 두고 폭 480px 이하일 때만 적용된다.
const MAP_MOBILE_MAX_WIDTH = 480;
const MAP_DEFAULT_CENTER_MOBILE = { lat: 35.4, lng: 127.9 }; // 모바일: 동쪽(부산·울산이 줌컨트롤에 가리지 않도록 lng↑) + 속초이북 끝부분에 붙이고 제주 완전 노출
const MAP_DEFAULT_LEVEL_MOBILE = 13;  // 속초~제주가 세로로 한 화면에 들어오는 축소 수준 (레벨 12는 제주 잘림)

function isMobileMapViewport(){
  return window.matchMedia(`(max-width: ${MAP_MOBILE_MAX_WIDTH}px)`).matches;
}
function mapDefaultView(){
  // localStorage에 저장된 마지막 위치가 있으면 우선 사용 (30일 이내)
  try {
    const saved = JSON.parse(localStorage.getItem("map_last_view") || "null");
    if (saved && saved.lat && saved.lng && saved.level
        && (Date.now() - saved.savedAt) < 30 * 24 * 60 * 60 * 1000) {
      return { center: { lat: saved.lat, lng: saved.lng }, level: saved.level };
    }
  } catch(e) {}
  return isMobileMapViewport()
    ? { center: MAP_DEFAULT_CENTER_MOBILE, level: MAP_DEFAULT_LEVEL_MOBILE }
    : { center: MAP_DEFAULT_CENTER, level: MAP_DEFAULT_LEVEL };
}

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
  mapLabelData.forEach(d => { if (d.overlay) d.overlay.setMap(null); });
  mapLabelData = [];
  // 클러스터 배지도 함께 제거
  _clusterOverlays.forEach(o => o.setMap(null));
  _clusterOverlays = [];
}

function resetMapView(){
  if (!kakaoMap) return;
  const dv = mapDefaultView();
  kakaoMap.setLevel(dv.level);
  kakaoMap.setCenter(new kakao.maps.LatLng(dv.center.lat, dv.center.lng));
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
// 라벨 DOM/오버레이는 최초 줌인 시 lazy 생성 — 전국뷰(기본)에서는 생성조차 하지 않는다.
// ★ 성능: viewport 밖 마커는 DOM 생성도 setMap도 건너뜀 — 11,000개 전체 동기처리 동결 방지.
function updateMarkerLabels(){
  if (!kakaoMap) return;
  const show = kakaoMap.getLevel() <= LABEL_MAX_LEVEL;

  if (!show){
    // 라벨 숨김: overlay가 이미 생성된 것만 제거 (미생성 건 skip)
    mapLabelData.forEach(d => { if (d.overlay) d.overlay.setMap(null); });
    return;
  }

  // 라벨 표시: 현재 viewport bounds 안 마커만 생성·표시
  const bounds = kakaoMap.getBounds();
  mapLabelData.forEach(d => {
    const inView = bounds ? bounds.contain(d.pos) : true;
    if (inView){
      if (!d.overlay){
        // 최초 줌인 시 1회만 DOM + CustomOverlay 생성
        d.el = _buildLabelEl(d.b);
        d.overlay = new kakao.maps.CustomOverlay({
          position: d.pos, content: d.el,
          xAnchor: 0.5, yAnchor: 1.0, zIndex: 20, // Kakao 기본 POI(~3)·마커(5)보다 위
          clickable: true,  // 모바일 탭 이벤트가 label DOM에 전달되도록
        });

      }
      d.overlay.setMap(kakaoMap);
    } else {
      // viewport 밖: 이미 표시 중인 경우만 숨김
      if (d.overlay) d.overlay.setMap(null);
    }
  });
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
  // ③ 마커 팝업 최초 1회 툴팁 — localStorage로 노출 여부 제어
  let showMarkerTip = false;
  if (canFav && !favActive){
    try { showMarkerTip = !localStorage.getItem("hs_marker_fav_tip_seen"); } catch(e){}
    if (showMarkerTip){ try { localStorage.setItem("hs_marker_fav_tip_seen", "1"); } catch(e){} }
  }
  const markerTipHtml = showMarkerTip
    ? `<div style="display:inline-block; font-size:11px; color:#B4863F; background:#fffbf3; border:1px solid #f0ddb0; border-radius:6px; padding:2px 8px; margin-bottom:3px;">☆를 눌러 저장해보세요</div><br>`
    : "";
  const favBtn = canFav
    ? markerTipHtml + `<button type="button" data-name="${escapeHtml(b.building_name || "")}" data-address="${escapeHtml(favAddr)}" data-bid="${b.id != null ? b.id : ""}"
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

// filters: {q, si_do, sgg_nm, umd_nm, lodging_type}
// opts.fit: true면 결과가 다 보이도록 bounds에 맞춰 확대/이동
async function loadMapMarkers(filters = {}, opts = {}){
  if (!kakaoMap) return;
  const myGen = ++_markerLoadGen;   // 이 호출의 세대 번호 — 이전 addChunk 루프는 불일치로 자동 종료
  const emptyEl = document.getElementById("mapEmpty");

  const params = new URLSearchParams();
  ["q", "si_do", "sgg_nm", "umd_nm", "lodging_type"].forEach(k => {
    if (filters[k]) params.set(k, filters[k]);
  });

  // 현재 뷰포트 bounds — 화면에 보이는 범위의 건물만 요청해 응답 크기를 줄인다.
  // opts.skipBounds가 true이면 bounds 파라미터를 생략한다 (q 검색 시 전국 대상 조회).
  if (!opts.skipBounds) {
    const _bounds = kakaoMap.getBounds();
    if (_bounds) {
      const _sw = _bounds.getSouthWest();
      const _ne = _bounds.getNorthEast();
      params.set("sw_lat", _sw.getLat());
      params.set("sw_lng", _sw.getLng());
      params.set("ne_lat", _ne.getLat());
      params.set("ne_lng", _ne.getLng());
    }
  }

  const qs = params.toString();

  // AbortController — 더 새로운 loadMapMarkers 호출이 오면 진행 중인 fetch를 취소
  const controller = new AbortController();
  let items = [];
  try {
    const res = await fetch(`/api/buildings-geo${qs ? "?" + qs : ""}`,
      { signal: controller.signal });
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    if (e.name === "AbortError") return;  // 신세대 요청이 이 fetch를 취소함
    console.error("[MAP] 건물 좌표 로드 실패:", e);
    return;
  }

  // fetch 완료 후 세대 번호 재확인 — 응답 대기 중 더 새로운 호출이 왔을 수 있다
  if (_markerLoadGen !== myGen) {
    controller.abort();  // 이미 응답 받았지만 결과를 버린다
    return;
  }

  clearMapMarkers();
  const bounds = new kakao.maps.LatLngBounds();
  let placed = 0;

  // 유효 좌표만 필터링
  // 겹침 우선순위: 생숙 > 관광 > 복합 > 일반 > 준공전 > 미분류
  // Kakao Maps 캔버스는 나중에 추가된 마커가 위에 그려지므로
  // 우선순위 낮은 타입부터 먼저 추가해야 높은 타입이 위에 표시된다.
  const _DRAW_ORDER = { "미분류": 0, "준공전": 1, "일반": 2, "복합": 3, "관광": 4, "생활": 5 };
  function _markerDrawOrder(b){
    if (!b.lodging_type){
      // lodging_type 없음 — building_status로 준공전/미분류 구분
      return (b.building_status === "허가" || b.building_status === "착공") ? 1 : 0;
    }
    if (b.lodging_type.includes("·")) return 3;     // 복합
    return _DRAW_ORDER[b.lodging_type] ?? 0;
  }
  const validItems = items
    .filter(b => b.lat != null && b.lng != null)
    .sort((a, b) => _markerDrawOrder(a) - _markerDrawOrder(b));

  // 마커를 CHUNK_SIZE 단위로 나눠 setTimeout(0)으로 분산 생성 —
  // 한 번에 수천 개를 동기 삽입하면 메인 스레드가 블로킹돼 화면이 굳는다.
  // native kakao.maps.Marker(canvas 렌더)를 사용하므로 CustomOverlay(DOM)보다
  // 훨씬 빠르며, 라벨은 첫 줌인 시에만 lazy 생성한다.
  const CHUNK_SIZE = 300;
  let idx = 0;

  function addChunk(){
    if (_markerLoadGen !== myGen) return; // 더 새로운 loadMapMarkers 호출이 있음 — 이 루프 폐기
    const end = Math.min(idx + CHUNK_SIZE, validItems.length);
    for (; idx < end; idx++){
      const b = validItems[idx];
      const color = markerColor(b.lodging_type, b.building_status);
      const pos = new kakao.maps.LatLng(b.lat, b.lng);

      // 겹침 우선순위: 생숙(9) > 관광(8) > 복합(7) > 일반(6) > 미분류(5)
      const MARKER_Z = { "생활": 9, "관광": 8, "복합": 7, "일반": 6 };
      const mzIndex = (b.lodging_type && b.lodging_type.includes("·"))
        ? 7  // 복합(복수 타입)
        : (MARKER_Z[b.lodging_type] || 5);

      const marker = new kakao.maps.Marker({
        position: pos,
        image: _makeMarkerImage(color),
        title: b.building_name || "",
        clickable: true,
        zIndex: mzIndex,
      });
      marker.setMap(kakaoMap);

      kakao.maps.event.addListener(marker, "click", () => {
        // PC/모바일 공통: 마커 클릭 시 바로 건물 상세 패널 열기
        if (b.id != null) {
          if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
          history.pushState({ buildingId: b.id }, "", "/building/" + b.id);
          if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/building/" + b.id });
          renderBuildingPanel(b.id);
        }
      });

      mapOverlays.push(marker);
      // 라벨 데이터만 저장 — 실제 DOM/오버레이는 updateMarkerLabels 에서 lazy 생성
      mapLabelData.push({ b, pos, overlay: null, el: null });
      bounds.extend(pos);
      placed++;
    }

    if (idx < validItems.length){
      setTimeout(addChunk, 0);
      return;
    }

    // 전체 완료 후 처리
    if (emptyEl) emptyEl.style.display = (placed === 0) ? "flex" : "none";
    if (placed > 0 && opts.fit === true) {
      kakaoMap.setBounds(bounds);
      // 카카오맵은 단일 좌표에 setBounds를 하면 지나치게 넓은 레벨로 남는 특성이 있음.
      // 결과가 1~2건이면 명시적으로 레벨 3으로 확대해 건물이 화면에 꽉 차게 표시한다.
      if (placed <= 2) kakaoMap.setLevel(3);
    }
    updateMarkerLabels();
    console.log(`[MAP] 마커 ${placed}개 표시 (필터: ${qs || "없음"})`);
  }

  addChunk();
}

// 현재 지도 줌 레벨로 클러스터 모드를 결정
function _clusterModeForLevel(lv){
  if (lv >= CLUSTER_SIDO_MIN_LEVEL) return "sido";
  if (lv >= CLUSTER_SGG_MIN_LEVEL)  return "sgg";
  return "markers";
}

// 클러스터 배지(CustomOverlay) 렌더링
// clusterLevel: 'sido'|'sgg'|'umd', filters: mapFiltersFromState()
async function loadClusterOverlays(clusterLevel, filters = {}){
  if (!kakaoMap) return;

  const params = new URLSearchParams({ level: clusterLevel });
  ["q", "si_do", "sgg_nm", "umd_nm", "lodging_type"].forEach(k => {
    if (filters[k]) params.set(k, filters[k]);
  });

  // sgg/umd 레벨은 현재 화면 범위로 집계 제한 — 화면 밖 배지 미표시
  if ((clusterLevel === "sgg" || clusterLevel === "umd") && kakaoMap) {
    const bounds = kakaoMap.getBounds();
    if (bounds) {
      const sw = bounds.getSouthWest();
      const ne = bounds.getNorthEast();
      params.set("sw_lat", sw.getLat());
      params.set("sw_lng", sw.getLng());
      params.set("ne_lat", ne.getLat());
      params.set("ne_lng", ne.getLng());
    }
  }

  let items = [];
  try {
    const res  = await fetch(`/api/buildings-cluster?${params}`);
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    console.error("[CLUSTER] 집계 로드 실패:", e);
    return;
  }

  clearMapMarkers();  // 이전 마커·배지 모두 제거

  // 클러스터 배지 색상 — LODGING_COLORS와 동일 (이중 관리 방지를 위해 참조)
  const BAR_COLORS = [
    { key: "생활",   color: LODGING_COLORS["생활"]   },
    { key: "관광",   color: LODGING_COLORS["관광"]   },
    { key: "일반",   color: LODGING_COLORS["일반"]   },
    { key: "복합",   color: LODGING_COLORS["복합"]   },
    { key: "준공전", color: LODGING_COLORS["준공전"] },
    { key: "미분류", color: LODGING_COLORS["미분류"] },
  ];

  // 클릭 시 드릴다운: 시도→시군구 레벨(9), 시군구→개별마커 레벨(6)
  const drillLevel = clusterLevel === "sido" ? 9 : 6;

  items.forEach(item => {
    if (item.lat == null || item.lng == null) return;
    // sido 레벨에서만 수동 보정 좌표 적용 (sgg/umd는 실제 AVG 좌표 사용)
    const _override = clusterLevel === "sido" ? SIDO_POSITION_OVERRIDE[item.name] : null;
    const _lat = _override ? _override.lat : item.lat;
    const _lng = _override ? _override.lng : item.lng;
    const pos   = new kakao.maps.LatLng(_lat, _lng);
    const total = item.total || 0;
    const bt    = item.by_type || {};

    // 스택바 width% 계산 — 14px 미만 구간(pct < 12%)은 숫자 생략(겹침 방지)
    const BAR_H = 15;
    const barSpans = BAR_COLORS
      .map(c => {
        const cnt = bt[c.key] || 0;
        if (!cnt || !total) return "";
        const pct = cnt / total * 100;
        const pctStr = pct.toFixed(1);
        // 최대폭 120px 기준 14px ≈ 11.7% → 12% 미만이면 숫자 생략
        const numHtml = pct >= 12
          ? `<span style="font-size:9px;color:#fff;font-weight:700;line-height:1;` +
            `pointer-events:none;overflow:hidden;">${cnt}</span>`
          : "";
        return `<span style="display:inline-flex;align-items:center;justify-content:center;` +
               `height:100%;width:${pctStr}%;background:${c.color};overflow:hidden;">${numHtml}</span>`;
      })
      .join("");

    const el = document.createElement("div");
    el.style.cssText =
      "background:#fff;border:1.5px solid #cdd3da;border-radius:8px;" +
      "box-shadow:0 2px 8px rgba(0,0,0,.18);padding:5px 9px 4px;" +
      "cursor:pointer;text-align:center;font-family:'Noto Sans KR',sans-serif;" +
      "min-width:52px;max-width:120px;";
    el.innerHTML =
      `<div style="font-size:11px;font-weight:700;color:#16202E;white-space:nowrap;` +
      `overflow:hidden;text-overflow:ellipsis;max-width:116px;">${escapeHtml(item.name)}</div>` +
      `<div style="font-size:13px;font-weight:800;color:#16202E;line-height:1.3;">` +
      `${total.toLocaleString("ko-KR")}</div>` +
      `<div style="display:flex;height:${BAR_H}px;border-radius:3px;overflow:hidden;` +
      `margin-top:3px;background:${LODGING_COLORS["미분류"]};">` +
      barSpans +
      `</div>`;

    // 클릭: 해당 좌표로 이동 + 한 단계 드릴다운 레벨로 축소
    el.addEventListener("click", () => {
      kakaoMap.setCenter(pos);
      kakaoMap.setLevel(drillLevel);
    });

    // sido 레벨: xAnchor=0(좌측 고정) + yAnchor=0.5(수직 중앙) →
    //   배지 왼쪽 끝이 도청소재지 좌표에 붙어 지명 우측으로 배치됨.
    //   Kakao 지도가 그 좌표에 지명 텍스트를 렌더링하므로, 텍스트 너비만큼
    //   margin-left를 주어 배지가 지명을 가리지 않도록 함.
    //   글자당 약 13px(Kakao 줌12 기준) + 여유 4px, 최소 44px.
    // sgg/umd 레벨: 기존대로 중앙 고정
    const isSido = clusterLevel === "sido";
    if (isSido) {
      // 모바일: 좁은 화면에서 배지가 오른쪽으로 밀려나지 않도록 최소 간격만 적용
      // 데스크톱: 글자당 ~13px 기준으로 Kakao 지명 텍스트 너비만큼 여백 확보
      const nameLen = item.name ? item.name.length : 4;
      el.style.marginLeft = isMobileMapViewport()
        ? "6px"
        : Math.max(44, nameLen * 13 + 4) + "px";
    }
    const overlay = new kakao.maps.CustomOverlay({
      position: pos, content: el,
      xAnchor: isSido ? 0 : 0.5,
      yAnchor: isSido ? 0.5 : 1.0,
      zIndex: 10,
    });
    overlay.setMap(kakaoMap);
    _clusterOverlays.push(overlay);
  });

  console.log(`[CLUSTER] ${clusterLevel} 배지 ${_clusterOverlays.length}개 표시 (필터: ${params})`);
}

// 현재 줌 레벨에 따라 클러스터 배지 또는 개별 마커로 자동 전환.
// filters: mapFiltersFromState() 또는 {} (초기화 시)
// opts.fit: true면 개별마커 모드에서 bounds 맞춤 (클러스터 모드에서는 무시)
// opts.force: true면 모드가 같아도 강제 재로드 (필터 변경 시 사용)
async function updateMapForZoom(filters = {}, opts = {}){
  if (!kakaoMap) return;
  _lastMapFilters = filters;

  // 검색어(q)가 있으면 줌 레벨과 무관하게 개별 마커 모드로 강제 전환.
  // 클러스터 배지 단계를 건너뛰어 검색 결과 위치로 바로 확대 이동한다.
  const forceMarkers = !!(filters.q && filters.q.trim());
  const mode = forceMarkers ? "markers" : _clusterModeForLevel(kakaoMap.getLevel());

  if (mode === "markers"){
    _currentMapMode = "markers";
    // forceMarkers일 때는 _currentMapMode 비교 없이 항상 재조회
    // (검색 결과가 이전과 다른 위치일 수 있으므로 캐시 상태 무시)
    //
    // noAutoFit:true = zoom_changed 이벤트에서 호출된 경우.
    // q 검색(forceMarkers)이면 skipBounds:true라 줌 레벨과 무관하게 결과가 같으므로
    // 재조회 자체를 생략한다 — setBounds/setLevel → zoom_changed → loadMapMarkers 무한루프 방지.
    if (forceMarkers && opts.noAutoFit) return;
    await loadMapMarkers(filters, { fit: opts.fit || forceMarkers, skipBounds: forceMarkers });
  } else {
    if (_currentMapMode !== mode || opts.force){
      _currentMapMode = mode;
      await loadClusterOverlays(mode, filters);
    }
    // 같은 클러스터 레벨 내에서 zoom만 바뀐 경우는 재로드 없음
  }
}

async function initMap(){
  const container = document.getElementById("map");
  if (!container) return;

  const dv = mapDefaultView();
  kakaoMap = new kakao.maps.Map(container, {
    center: new kakao.maps.LatLng(dv.center.lat, dv.center.lng),
    level: dv.level,
  });

  // 확대/축소(+/-) 버튼 — 휠/핀치줌이 불안정할 때를 위한 명시적 컨트롤.
  // 우측 하단(BOTTOMRIGHT)에 배치하되, 같은 자리의 범례박스(.map-legend)와
  // 겹치지 않도록 범례 높이만큼 bottom 오프셋을 JS로 계산해 위로 띄운다.
  // (우측 상단은 "🔍 검색" 버튼 자리라 비워둔다)
  kakaoMap.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.BOTTOMRIGHT);
  liftZoomControlAboveLegend();
  window.addEventListener("resize", () => setTimeout(liftZoomControlAboveLegend, 150));

  // 지도 이동·줌 완료 시 마지막 위치를 localStorage에 저장 — 새로고침 후 복원에 사용
  // idle은 이동이 멈춘 뒤 한 번만 발생하므로 디바운스 불필요
  kakao.maps.event.addListener(kakaoMap, "idle", () => {
    const c = kakaoMap.getCenter();
    localStorage.setItem("map_last_view", JSON.stringify({
      lat: c.getLat(), lng: c.getLng(), level: kakaoMap.getLevel(),
      savedAt: Date.now(),
    }));
  });

  // 확대/축소 시 클러스터 배지↔개별마커 전환 (모드 변경 시만 재로드, 같은 모드면 라벨만 갱신)
  // noAutoFit:true — zoom_changed에서 setBounds/setLevel을 다시 호출하면 zoom_changed가 재발해
  // 무한루프(깜빡임→흰 화면)가 생기므로, 이벤트 유발 fit은 반드시 억제한다.
  kakao.maps.event.addListener(kakaoMap, "zoom_changed", () => updateMapForZoom(_lastMapFilters, { noAutoFit: true }));

  // 지도 이동(드래그) 후 같은 클러스터 레벨이면 bounds가 바뀌므로 재조회
  // (sgg/umd 배지는 뷰포트 제한이므로, 이동 시 화면 밖 지역 배지를 갱신해야 함)
  // markers 모드에서 드래그하면 뷰포트가 바뀌어 새 범위의 건물 마커를 재요청해야 한다.
  kakao.maps.event.addListener(kakaoMap, "dragend", () => {
    const mode = _clusterModeForLevel(kakaoMap.getLevel());
    if (mode === "markers"){
      loadMapMarkers(_lastMapFilters);  // 새 뷰포트 bounds로 재요청
    } else if (mode === "sgg" || mode === "umd") {
      loadClusterOverlays(mode, _lastMapFilters);
    }
  });

  // 풀스크린 레이아웃 대응 — 컨테이너 크기가 폰트 로드/헤더 높이 반영/창 크기변경으로
  // 바뀌면 지도 타일이 회색으로 남으므로 렌더를 다시 맞춘다.
  // (relayout은 렌더 갱신일 뿐 — 마커·검색·API 로직에는 영향 없음)
  const relayoutMap = () => { if (kakaoMap) kakaoMap.relayout(); };
  window.addEventListener("resize", relayoutMap);
  window.addEventListener("load", () => setTimeout(relayoutMap, 120));
  setTimeout(relayoutMap, 300);

  // 최초 로드 — 줌 레벨 기반으로 클러스터 또는 개별 마커 결정
  await updateMapForZoom({}, { fit: false });
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
  const bidAttr = btn.getAttribute("data-bid");
  const item = {
    building_name: btn.getAttribute("data-name"),
    address: btn.getAttribute("data-address"),
    building_id: (bidAttr && /^\d+$/.test(bidAttr)) ? Number(bidAttr) : undefined,
  };
  const ok = toggleFav(item);
  if (ok === false) return false; // 상한 초과 시 표시 변경 안 함
  const active = isFav(item);
  btn.textContent = active ? "★ 관심저장됨" : "☆ 관심저장";
  btn.style.color = active ? "#B4863F" : "#8a94a0";
  return false;
};

// SDK 로드 완료 즉시 initMap 호출 — 200ms 폴링 방식 대체.
// index.html의 SDK <script defer onload="..."> 와 연동:
//   · SDK가 main.js 실행 후 로드 완료 → onload 콜백이 __onKakaoSdkLoad() 호출
//   · SDK가 main.js 실행 전 이미 로드(캐시 히트 등) → __kakaoSdkLoaded 플래그 즉시 확인
window.__onKakaoSdkLoad = function() {
  if (window.kakao && window.kakao.maps) {
    kakao.maps.load(initMap);
  } else {
    console.warn("[MAP] 카카오맵 SDK가 로드되지 않았습니다 — appkey/도메인 등록 상태를 확인하세요.");
  }
};
if (window.__kakaoSdkLoaded) window.__onKakaoSdkLoad();
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
  // 실거래 없는 관심단지(master fallback)는 가격 대신 "실거래 없음" 표기
  const hasPrice = t.price != null && t.price !== "";
  const priceHtml = hasPrice
    ? `${Number(t.price).toLocaleString('ko-KR')}<span style="font-size:10px;">만</span>`
    : `<span style="font-size:11px; color:var(--ink-soft); font-weight:400;">실거래 없음</span>`;
  const region = escapeHtml([t.sgg_nm, t.umd_nm].filter(Boolean).join(" "));
  const metaRight = t.deal_date ? ` · ${escapeHtml(t.deal_date)}` : "";
  const rankHtml = rank ? `<span class="st-rank">${rank}</span>` : "";
  // 지도 범례와 동일한 markerColor()로 색점 생성 — LODGING_COLORS를 이중 관리하지 않음
  const dot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${markerColor(t.lodging_type)}; margin-right:5px; flex-shrink:0; vertical-align:middle;"></span>`;
  // master_building_id가 있으면 건물상세 좌측패널 전환(페이지 이동 없이) — 기존 로직 재사용.
  const mbid = t.master_building_id;
  const clickable = mbid != null && mbid !== "";
  const clickAttrs = clickable
    ? ` class="side-tx is-clickable" onclick="openBuildingDetail(${Number(mbid)}); return false;" title="건물 상세 보기"`
    : ` class="side-tx"`;
  return `<div${clickAttrs}>
    <div class="st-left">
      <div class="st-name">${rankHtml}${dot}${name}</div>
      <div class="st-meta">${region}${metaRight}</div>
    </div>
    <div class="st-price">${priceHtml}</div>
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

// ---- 메인 좌측 패널: 행정(전국 신고율) + 위탁정보/운영지원업체(하우스키핑)/금융(등록 업체 수) 집계 ----
// 등록 수가 이 값 미만이면 숫자를 노출하지 않고 모집 문구만 보여준다 (전속중개사/위탁/운영지원업체(하우스키핑)/금융 공통)
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
          agentBox.innerHTML = `<div style="font-size:14px; font-weight:700; color:var(--ink);">등록된 담당중개사 ${n}명</div>`;
        } else {
          agentBox.classList.remove("side-soon");
          agentBox.innerHTML = recruitBoxHTML("agent");
          hideAdjacentApplyBanner(agentBox);
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
        box.classList.remove("side-soon");
        box.innerHTML = (k === "finance") ? financeEmptyHTML() : recruitBoxHTML(k);
        hideAdjacentApplyBanner(box);
      }
    });
  }
}

// 모집 박스에 자체 신청 버튼이 있으므로, 바로 아래 배너형 신청 링크는 중복이라 숨긴다 (A화면 전용)
function hideAdjacentApplyBanner(box){
  const next = box.nextElementSibling;
  if (next && next.classList && next.classList.contains("side-apply-banner")) next.style.display = "none";
}

// ---- 공통 모집(빈 상태) 박스 컴포넌트 — A화면(메인 좌측패널)과 B화면(건물상세)이 함께 사용 ----
// kind: agent | consign | housekeeping | finance
// opts: { href(버튼 링크 재정의), btnText(버튼 문구 재정의), linkId(버튼 a태그 id — B화면 동적 href 주입용) }
function recruitBoxHTML(kind, opts = {}){
  const KINDS = {
    agent: {
      bg: "var(--brass-tint)", border: "#EAD9B8", icon: "🔎", iconSize: 24, pad: "16px 12px",
      title: "건물별 담당중개사를 모집하고 있습니다",
      desc: "건물별 담당 중개사무소를 모집합니다.",
      btnText: "담당중개사로 신청하기", href: "/partner", btnStyle: "",
    },
    consign: {
      bg: "#EEF6E6", border: "#CFE4B8", icon: "🏨", iconSize: 22, pad: "14px 12px",
      title: "위탁운영 지원업체를 찾고 있습니다",
      desc: "",
      btnText: "지원업체로 신청하기", href: "/partner",
      btnStyle: "background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8;",
    },
    housekeeping: {
      bg: "#EEF6E6", border: "#CFE4B8", icon: "🧹", iconSize: 22, pad: "14px 12px",
      title: "",
      desc: `<span style="font-weight:700;">청소 · 세탁 · 용품 · 소독 · 세무 · 인테리어</span>`,
      btnText: "지원업체로 신청하기", href: "/partner",
      btnStyle: "background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8;",
    },
    finance: {
      bg: "var(--brass-tint)", border: "#EAD9B8", icon: "💰", iconSize: 22, pad: "14px 12px",
      title: "금융 파트너(대출상담사)를 모집합니다",
      desc: "",
      btnText: "대출상담사로 등록하기", href: "/partner", btnStyle: "",
    },
  };
  const PRE_COMPLETION_OVERRIDE = {
    agent: { title: "🏗 준공 전 선점 기회", desc: "이 프로젝트의 첫 담당중개사가 되어보세요." },
    consign: { title: "🏗 준공 전 선점 기회", desc: "이 프로젝트의 첫 위탁운영 파트너가 되어보세요." },
    housekeeping: { title: "🏗 준공 전 선점 기회", desc: "이 프로젝트의 첫 운영지원 파트너가 되어보세요." },
    finance: { title: "🏗 준공 전 선점 기회", desc: "이 프로젝트의 첫 대출상담 파트너가 되어보세요." },
  };
  let k = KINDS[kind];
  if (!k) return "";
  if (opts.preCompletion && PRE_COMPLETION_OVERRIDE[kind]) {
    k = Object.assign({}, k, PRE_COMPLETION_OVERRIDE[kind], {
      bg: "#F1F2F4", border: "#C7CCD1",  // 회색 포인트(준공전 전용 색과 통일)
    });
  }
  const btnText = opts.btnText || k.btnText;
  const href = (opts.href !== undefined) ? opts.href : k.href;
  const btn = href
    ? `<a ${opts.linkId ? `id="${opts.linkId}" ` : ""}href="${href}" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:7px 16px; text-decoration:none; ${k.btnStyle}">${btnText}</a>`
    : `<button class="side-more" style="width:auto; margin-top:0; padding:7px 16px; ${k.btnStyle}">${btnText}</button>`;
  return `
    <div style="text-align:center; padding:${k.pad}; background:${k.bg}; border:1px dashed ${k.border}; border-radius:8px;">
      <div style="font-size:${k.iconSize}px; margin-bottom:6px;">${k.icon}</div>
      <div style="font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:6px;">${k.title}</div>
      ${k.desc ? `<div style="font-size:11.5px; color:var(--ink-soft); margin-bottom:10px; line-height:1.5;">${k.desc}</div>` : ""}
      ${btn}
    </div>`;
}

// 금융 섹션 빈 상태: 문구 + 대출상담 모집 박스 (A/B 공통)
function financeEmptyHTML(){
  return `
    ${recruitBoxHTML("finance")}`;
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

let bCurrentName = ""; // 현재 열린 건물상세의 건물명 (매물 내놓기 모달용)

// ── 매물 내놓기 모달 (B화면) ──────────────────────────────────
// 제출 시 기존 POST /api/listing-requests 호출 (로그인 필수, 서버가 중개사 라우팅+SMS 처리)
function openListingRequestModal(buildingId, buildingName){
  document.getElementById("listingReqOverlay")?.remove();
  const ov = document.createElement("div");
  ov.id = "listingReqOverlay";
  ov.style.cssText = "position:fixed; inset:0; background:rgba(22,32,46,.45); z-index:3000; display:flex; align-items:center; justify-content:center; padding:16px;";
  const FLD = "width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font-size:13.5px; font-family:inherit;";
  ov.innerHTML = `
    <div style="background:#fff; border-radius:14px; width:100%; max-width:400px; padding:22px 20px; box-shadow:0 10px 40px rgba(0,0,0,.2);" role="dialog" aria-modal="true">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
        <div style="font-size:16px; font-weight:800; color:var(--ink);">매물 내놓기</div>
        <button id="lrClose" style="background:none; border:none; font-size:20px; cursor:pointer; color:var(--ink-soft);" aria-label="닫기">×</button>
      </div>
      <div style="font-size:12.5px; color:var(--ink-soft); margin-bottom:14px;">${escapeHtml(buildingName)}</div>
      <div id="lrForm">
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">의뢰인</div>
        <input id="lrName" type="text" readonly value="" placeholder="로그인 정보에서 자동 표시" style="${FLD} margin-bottom:12px; background:#F6F5F2; color:var(--ink-soft);" />
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">거래유형</div>
        <div id="lrDealTypes" style="display:flex; gap:6px; margin-bottom:12px;">
          ${["매매","전세","월세","단기임대"].map((t,i) => `<button type="button" data-dt="${t}" class="side-more" style="flex:1; margin-top:0; padding:8px 0; ${i===0 ? "background:var(--brass); color:#fff; border-color:var(--brass);" : ""}">${t}</button>`).join("")}
        </div>
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">희망가 <span style="font-weight:400; color:var(--ink-soft);">(선택)</span></div>
        <div id="lrPriceSale">
          <input id="lrSalePrice" type="number" min="1" inputmode="numeric" placeholder="매매가 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="lrPriceJeonse" style="display:none;">
          <input id="lrJeonseDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="lrPriceWolse" style="display:none; gap:6px; margin-bottom:12px;">
          <input id="lrWolseDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} flex:1;" />
          <input id="lrWolseRent" type="number" min="1" inputmode="numeric" placeholder="월세 (만원)" style="${FLD} flex:1;" />
        </div>
        <div id="lrPriceShort" style="display:none;">
          <input id="lrShortPrice" type="text" maxlength="100" placeholder="예) 1박 8만원 / 주 단위 협의" style="${FLD} margin-bottom:12px;" />
        </div>
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">연락처</div>
        <input id="lrPhone" type="tel" maxlength="13" placeholder="010-1234-5678" style="${FLD}" />
        <div id="lrMsg" style="font-size:12px; color:var(--brick); min-height:16px; margin-top:6px;"></div>
        <button id="lrSubmit" class="btn-search" style="width:100%; padding:12px; margin-top:6px;">매물의뢰 접수하기</button>
        <div style="font-size:11.5px; color:var(--ink-soft); line-height:1.7; margin-top:10px; padding:10px 12px; background:#F4F1EA; border-radius:8px;">
          <div style="font-weight:700; color:var(--ink); margin-bottom:6px;">[공지사항]</div>
          -매물의뢰는 단지부동산, 지역부동산 순으로 자동으로 순차배정되며 배정된 부동산에서 중개상담차 전화를 연결할 수 있습니다.<br><br>
          -홈앤스테이는 부동산중개사무소가 아니며 중개행위에 관여하지 않고, 중개수수료를 받지 않습니다.<br><br>
          -"매물의뢰"는 매물내놓기 무료서비스이며, 중개의뢰는 배정된 중개사를 통하여 별도로 상담을 진행하여 주시기 바랍니다.
        </div>
      </div>
      <div id="lrDone" style="display:none; text-align:center; padding:18px 4px;">
        <div style="font-size:34px; margin-bottom:10px;">✅</div>
        <div style="font-size:14.5px; font-weight:700; color:var(--ink); margin-bottom:6px;">매물의뢰가 접수됐습니다</div>
        <div style="font-size:12.5px; color:var(--ink-soft); line-height:1.6;">담당 중개사가 곧 연락드립니다.<br/>접수 현황은 마이페이지에서 확인할 수 있습니다.</div>
        <button id="lrDoneClose" class="side-more" style="width:auto; padding:8px 22px; margin-top:14px;">닫기</button>
      </div>
    </div>`;
  document.body.appendChild(ov);

  // 의뢰인 이름 자동 표시 (로그인 정보, 읽기전용)
  fetch("/api/auth/me", { credentials: "same-origin" })
    .then((r) => r.json())
    .then((d) => { if (d && d.logged_in && d.name) ov.querySelector("#lrName").value = d.name; })
    .catch(() => {});

  let dealType = "매매";
  const PRICE_BOXES = { "매매": "lrPriceSale", "전세": "lrPriceJeonse", "월세": "lrPriceWolse", "단기임대": "lrPriceShort" };
  function showPriceBox(){
    Object.entries(PRICE_BOXES).forEach(([dt, id]) => {
      const el = ov.querySelector("#" + id);
      el.style.display = (dt === dealType) ? (dt === "월세" ? "flex" : "block") : "none";
    });
  }
  ov.querySelectorAll("#lrDealTypes button").forEach((b) => {
    b.addEventListener("click", () => {
      dealType = b.dataset.dt;
      showPriceBox();
      ov.querySelectorAll("#lrDealTypes button").forEach((x) => {
        const on = x === b;
        x.style.background = on ? "var(--brass)" : "";
        x.style.color = on ? "#fff" : "";
        x.style.borderColor = on ? "var(--brass)" : "";
      });
    });
  });
  const close = () => ov.remove();
  ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  ov.querySelector("#lrClose").addEventListener("click", close);
  ov.querySelector("#lrDoneClose").addEventListener("click", close);

  ov.querySelector("#lrSubmit").addEventListener("click", async () => {
    const msg = ov.querySelector("#lrMsg");
    const phone = ov.querySelector("#lrPhone").value.trim();
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)){
      msg.textContent = "연락처 형식이 올바르지 않습니다. 예) 010-1234-5678";
      return;
    }
    // 거래유형별 구조화 희망가 → 숫자값 + 사람이 읽는 문자열(desired_price) 동시 구성
    const numVal = (id) => {
      const v = parseInt(ov.querySelector("#" + id).value, 10);
      return (Number.isFinite(v) && v > 0) ? v : null;
    };
    const fmt = (n) => n.toLocaleString("ko-KR");
    let priceKrw = null, monthlyRentKrw = null, desiredPrice = "";
    if (dealType === "매매"){
      priceKrw = numVal("lrSalePrice");
      if (priceKrw) desiredPrice = `매매가 ${fmt(priceKrw)}만원`;
    } else if (dealType === "전세"){
      priceKrw = numVal("lrJeonseDeposit");
      if (priceKrw) desiredPrice = `보증금 ${fmt(priceKrw)}만원`;
    } else if (dealType === "월세"){
      priceKrw = numVal("lrWolseDeposit");
      monthlyRentKrw = numVal("lrWolseRent");
      const parts = [];
      if (priceKrw) parts.push(`보증금 ${fmt(priceKrw)}만원`);
      if (monthlyRentKrw) parts.push(`월세 ${fmt(monthlyRentKrw)}만원`);
      desiredPrice = parts.join("·");
    } else {
      desiredPrice = ov.querySelector("#lrShortPrice").value.trim();
    }
    msg.textContent = "";
    const btn = ov.querySelector("#lrSubmit");
    btn.disabled = true; btn.textContent = "접수 중…";
    try {
      const res = await fetch("/api/listing-requests", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          master_building_id: buildingId,
          deal_type: dealType,
          desired_price: desiredPrice,
          price_krw: priceKrw,
          monthly_rent_krw: monthlyRentKrw,
          contact_phone: phone,
        }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.status === 401){
        close();
        if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
        return;
      }
      if (!res.ok || d.ok === false){
        msg.textContent = d.message || "접수에 실패했습니다. 잠시 후 다시 시도해주세요.";
        btn.disabled = false; btn.textContent = "매물의뢰 접수하기";
        return;
      }
      ov.querySelector("#lrForm").style.display = "none";
      ov.querySelector("#lrDone").style.display = "block";
      // GA4: 매물의뢰 완료 — API 성공 응답 직후(서버 저장 확정 시점)
      if (typeof gtag === "function") gtag("event", "generate_lead_listing");
    } catch(e){
      msg.textContent = "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      btn.disabled = false; btn.textContent = "매물의뢰 접수하기";
    }
  });
}

// ── 매수의뢰 모달 (B화면) ────────────────────────────────────
function openBuyRequestModal(buildingId, buildingName){
  document.getElementById("buyReqOverlay")?.remove();
  const ov = document.createElement("div");
  ov.id = "buyReqOverlay";
  ov.style.cssText = "position:fixed; inset:0; background:rgba(22,32,46,.45); z-index:3000; display:flex; align-items:center; justify-content:center; padding:16px;";
  const FLD = "width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font-size:13.5px; font-family:inherit;";
  ov.innerHTML = `
    <div style="background:#fff; border-radius:14px; width:100%; max-width:400px; padding:22px 20px; box-shadow:0 10px 40px rgba(0,0,0,.2);" role="dialog" aria-modal="true">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
        <div style="font-size:16px; font-weight:800; color:var(--ink);">매수의뢰</div>
        <button id="brClose" style="background:none; border:none; font-size:20px; cursor:pointer; color:var(--ink-soft);" aria-label="닫기">×</button>
      </div>
      <div style="font-size:12.5px; color:var(--ink-soft); margin-bottom:14px;">${escapeHtml(buildingName)}</div>
      <div id="brForm">
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">의뢰인</div>
        <input id="brName" type="text" readonly value="" placeholder="로그인 정보에서 자동 표시" style="${FLD} margin-bottom:12px; background:#F6F5F2; color:var(--ink-soft);" />
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">거래유형</div>
        <div id="brDealTypes" style="display:flex; gap:6px; margin-bottom:12px;">
          ${["매매","전세","월세","단기임대"].map((t,i) => `<button type="button" data-dt="${t}" class="side-more" style="flex:1; margin-top:0; padding:8px 0; ${i===0 ? "background:#3B7DD8; color:#fff; border-color:#3B7DD8;" : ""}">${t}</button>`).join("")}
        </div>
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">희망가 <span style="font-weight:400; color:var(--ink-soft);">(선택)</span></div>
        <div id="brPriceSale">
          <input id="brSalePrice" type="number" min="1" inputmode="numeric" placeholder="매매가 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="brPriceJeonse" style="display:none;">
          <input id="brJeonseDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="brPriceWolse" style="display:none; gap:6px; margin-bottom:12px;">
          <input id="brWolseDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} flex:1;" />
          <input id="brWolseRent" type="number" min="1" inputmode="numeric" placeholder="월세 (만원)" style="${FLD} flex:1;" />
        </div>
        <div id="brPriceShort" style="display:none;">
          <input id="brShortPrice" type="text" maxlength="100" placeholder="예) 1박 8만원 / 주 단위 협의" style="${FLD} margin-bottom:12px;" />
        </div>
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">연락처</div>
        <input id="brPhone" type="tel" maxlength="13" placeholder="010-1234-5678" style="${FLD}" />
        <div id="brMsg" style="font-size:12px; color:var(--brick); min-height:16px; margin-top:6px;"></div>
        <button id="brSubmit" class="btn-search" style="width:100%; padding:12px; margin-top:6px; background:#3B7DD8; border-color:#3B7DD8;">매수의뢰 접수하기</button>
        <div style="font-size:11.5px; color:var(--ink-soft); line-height:1.7; margin-top:10px; padding:10px 12px; background:#F4F1EA; border-radius:8px;">
          <div style="font-weight:700; color:var(--ink); margin-bottom:6px;">[공지사항]</div>
          -매수의뢰는 단지부동산, 지역부동산 순으로 자동으로 순차배정되며 배정된 부동산에서 중개상담차 전화를 연결할 수 있습니다.<br><br>
          -홈앤스테이는 부동산중개사무소가 아니며 중개행위에 관여하지 않고, 중개수수료를 받지 않습니다.<br><br>
          -"매수의뢰"는 무료서비스이며, 중개의뢰는 배정된 중개사를 통하여 별도로 상담을 진행하여 주시기 바랍니다.
        </div>
      </div>
      <div id="brDone" style="display:none; text-align:center; padding:18px 4px;">
        <div style="font-size:34px; margin-bottom:10px;">✅</div>
        <div style="font-size:14.5px; font-weight:700; color:var(--ink); margin-bottom:6px;">매수의뢰가 접수됐습니다</div>
        <div style="font-size:12.5px; color:var(--ink-soft); line-height:1.6;">담당 중개사가 곧 연락드립니다.<br/>접수 현황은 마이페이지에서 확인할 수 있습니다.</div>
        <button id="brDoneClose" class="side-more" style="width:auto; padding:8px 22px; margin-top:14px;">닫기</button>
      </div>
    </div>`;
  document.body.appendChild(ov);

  fetch("/api/auth/me", { credentials: "same-origin" })
    .then((r) => r.json())
    .then((d) => { if (d && d.logged_in && d.name) ov.querySelector("#brName").value = d.name; })
    .catch(() => {});

  let dealType = "매매";
  const PRICE_BOXES = { "매매": "brPriceSale", "전세": "brPriceJeonse", "월세": "brPriceWolse", "단기임대": "brPriceShort" };
  function showPriceBox(){
    Object.entries(PRICE_BOXES).forEach(([dt, id]) => {
      const el = ov.querySelector("#" + id);
      el.style.display = (dt === dealType) ? (dt === "월세" ? "flex" : "block") : "none";
    });
  }
  ov.querySelectorAll("#brDealTypes button").forEach((b) => {
    b.addEventListener("click", () => {
      dealType = b.dataset.dt;
      showPriceBox();
      ov.querySelectorAll("#brDealTypes button").forEach((x) => {
        const on = x === b;
        x.style.background = on ? "#3B7DD8" : "";
        x.style.color = on ? "#fff" : "";
        x.style.borderColor = on ? "#3B7DD8" : "";
      });
    });
  });
  const close = () => ov.remove();
  ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  ov.querySelector("#brClose").addEventListener("click", close);
  ov.querySelector("#brDoneClose").addEventListener("click", close);

  ov.querySelector("#brSubmit").addEventListener("click", async () => {
    const msg = ov.querySelector("#brMsg");
    const phone = ov.querySelector("#brPhone").value.trim();
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)){
      msg.textContent = "연락처 형식이 올바르지 않습니다. 예) 010-1234-5678";
      return;
    }
    const numVal = (id) => {
      const v = parseInt(ov.querySelector("#" + id).value, 10);
      return (Number.isFinite(v) && v > 0) ? v : null;
    };
    const fmt = (n) => n.toLocaleString("ko-KR");
    let priceKrw = null, monthlyRentKrw = null, desiredPrice = "";
    if (dealType === "매매"){
      priceKrw = numVal("brSalePrice");
      if (priceKrw) desiredPrice = `매매가 ${fmt(priceKrw)}만원`;
    } else if (dealType === "전세"){
      priceKrw = numVal("brJeonseDeposit");
      if (priceKrw) desiredPrice = `보증금 ${fmt(priceKrw)}만원`;
    } else if (dealType === "월세"){
      priceKrw = numVal("brWolseDeposit");
      monthlyRentKrw = numVal("brWolseRent");
      const parts = [];
      if (priceKrw) parts.push(`보증금 ${fmt(priceKrw)}만원`);
      if (monthlyRentKrw) parts.push(`월세 ${fmt(monthlyRentKrw)}만원`);
      desiredPrice = parts.join("·");
    } else {
      desiredPrice = ov.querySelector("#brShortPrice").value.trim();
    }
    msg.textContent = "";
    const btn = ov.querySelector("#brSubmit");
    btn.disabled = true; btn.textContent = "접수 중…";
    try {
      const res = await fetch("/api/buy-requests", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          master_building_id: buildingId,
          deal_type: dealType,
          desired_price: desiredPrice,
          price_krw: priceKrw,
          monthly_rent_krw: monthlyRentKrw,
          contact_phone: phone,
        }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.status === 401){
        close();
        if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
        return;
      }
      if (!res.ok || d.ok === false){
        msg.textContent = d.message || "접수에 실패했습니다. 잠시 후 다시 시도해주세요.";
        btn.disabled = false; btn.textContent = "매수의뢰 접수하기";
        return;
      }
      ov.querySelector("#brForm").style.display = "none";
      ov.querySelector("#brDone").style.display = "block";
    } catch(e){
      msg.textContent = "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      btn.disabled = false; btn.textContent = "매수의뢰 접수하기";
    }
  });
}

const B_LODGING_BADGE = { "생활": "생숙", "관광": "관광숙박", "일반": "일반숙박", "복합": "복합" };
function detailBadgeLabel(v, subtype){
  if (!v) return "미분류";
  const base = B_LODGING_BADGE[v] || v;
  return subtype ? `${base}(${subtype})` : base;
}

function buildingPanelSkeleton(){
  return `
    <section class="side-card b-panel-topbar">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
        <button id="btnBackToList" class="side-more" style="margin-top:0; text-align:left; width:auto; white-space:nowrap; font-size:12px; padding:6px 10px;">← 전체목록</button>
        <button id="btnListingRequest" class="side-more" style="margin-top:0; width:auto; padding:6px 10px; background:var(--brass); color:#fff; border-color:var(--brass); font-weight:700; white-space:nowrap; font-size:12px;">매물내놓기</button>
        <button id="btnBuyRequest" class="side-more" style="margin-top:0; width:auto; padding:6px 10px; background:#3B7DD8; color:#fff; border-color:#3B7DD8; font-weight:700; white-space:nowrap; font-size:12px;">매수의뢰</button>
      </div>
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

    <section class="side-card" id="bTimelineCard" style="display:none;">
      <div class="side-card-title">진행단계 <span class="side-sub">건축인허가</span></div>
      <div id="bTimelineBody"></div>
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
      <div class="side-card-title">담당중개사</div>
      <div id="bAgentBox"><div class="side-empty">불러오는 중…</div></div>
    </section>

    <section class="side-card" id="bAdminCard">
      <div class="side-card-title">행정 <span class="side-sub">숙박업영업신고율</span></div>
      <div class="side-empty">불러오는 중…</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">위탁운영</div>
      <div id="bOperatorBox">${recruitBoxHTML("consign", { linkId: "lnkOperatorApply" })}</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">운영지원업체</div>
      <div id="bHousekeepingBox">${recruitBoxHTML("housekeeping", { linkId: "lnkHousekeepingApply" })}</div>
    </section>

    <section class="side-card">
      <div class="side-card-title">금융 <span class="side-sub">대출상담</span></div>
      <div id="bFinanceBox">${financeEmptyHTML()}</div>
    </section>

    <section class="side-card" id="bBldgInfoCard">
      <div class="side-card-title">건축정보 <span class="side-sub">표제부</span></div>
      <div class="side-empty">불러오는 중…</div>
    </section>

    <section class="side-card" id="bStoresCard">
      <div class="side-card-title">상가정보 <span class="side-sub">주변 상가업소</span></div>
      <div class="side-soon">준비 중
        <div class="side-soon-desc">주변 상가업소 정보를 준비하고 있습니다.</div>
      </div>
    </section>`;
}

// opts.rawValue=true → value를 이스케이프하지 않고 innerHTML로 삽입 (HTML 배지 등에 사용)
function bStat(label, value, opts = {}){
  const valueHtml = opts.rawValue ? String(value) : escapeHtml(String(value));
  return `<div style="flex:1; min-width:100px;">
    <div style="font-size:11px; color:var(--ink-soft); font-weight:600; margin-bottom:3px;">${escapeHtml(String(label))}</div>
    <div style="font-family:'JetBrains Mono',monospace; font-size:16px; font-weight:700; color:var(--ink);">${valueHtml}</div>
  </div>`;
}

// ---- 건축정보 카드 공유 렌더러 + 백그라운드 폴링 ----
let _detailPollTimer        = null;
let _detailPollBuildingId   = null;

function _cancelDetailPoll(){
  if (_detailPollTimer !== null){ clearTimeout(_detailPollTimer); _detailPollTimer = null; }
  _detailPollBuildingId = null;
}

// bBldgInfoCard + bTimelineCard(준공전)을 렌더. loadBuildingHeader와 폴링 콜백이 공유.
function _renderDetailCards(b){
  const bldgInfoCard = document.getElementById("bBldgInfoCard");
  if (!bldgInfoCard) return;
  const fmtNum = (v, suffix) => (v != null && v !== "") ? Number(v).toLocaleString('ko-KR') + suffix : "-";
  const fmtTxt = (v) => (v != null && v !== "") ? escapeHtml(String(v)) : "-";
  const fmtDay = (v) => (v != null && v !== "") ? String(v).slice(0, 10).replace(/-/g, ".") : "-";
  const fmtFlr = (g, u) => (g != null || u != null)
    ? `${g != null ? g : "-"}층 / ${u != null ? u : "-"}층` : "-";
  const isPreC = b.building_status && b.building_status !== "완공";
  const fmtDayPlus3Y = (v) => {
    if (!v) return "-";
    const d = new Date(String(v).slice(0, 10));
    if (isNaN(d)) return "-";
    d.setFullYear(d.getFullYear() + 3);
    return d.toISOString().slice(0, 10).replace(/-/g, ".");
  };
  const pairs = [
    ["명칭",          fmtTxt(b.building_name)],
    ["호수",          fmtNum(b.units, "호")],
    ["대지면적",      fmtNum(b.plat_area, " ㎡")],
    ["건축면적",      fmtNum(b.arch_area, " ㎡")],
    ["연면적",        fmtNum(b.tot_area, " ㎡")],
    ["건폐율",        fmtNum(b.bc_rat, "%")],
    ["용적률",        fmtNum(b.vl_rat, "%")],
    ["지상/지하층수", fmtFlr(b.grnd_flr_cnt, b.ugrnd_flr_cnt)],
    ["높이",          fmtNum(b.heit, " m")],
    ["용도지역",      fmtTxt(b.jiyuk_nm)],
    ["지구",          fmtTxt(b.jigu_nm)],
    ["구역",          fmtTxt(b.guyuk_nm)],
    ["주용도",        fmtTxt(b.main_purps_nm)],
    ["구조",          fmtTxt(b.strct_nm)],
    ["자주식 주차",   fmtNum((b.indr_auto_utcnt ?? 0) + (b.oudr_auto_utcnt ?? 0) || null, "대")],
    ["기계식 주차",   fmtNum((b.indr_mech_utcnt ?? 0) + (b.oudr_mech_utcnt ?? 0) || null, "대")],
    ["승용승강기",    fmtNum(b.ride_use_elvt_cnt, "대")],
    ["비상승강기",    fmtNum(b.emgen_use_elvt_cnt, "대")],
    ["건축허가일",    fmtDay(b.permit_day)],
    ["착공일",        fmtDay(b.actual_start_day)],
    ["사용승인일",    fmtDay(b.use_apr_day)],
    ["정기점검(완료)", fmtDay(b.last_inspection_submit_day)],
    ["정기점검유효일", fmtDayPlus3Y(b.last_inspection_submit_day)],
    ["점검기관",      fmtTxt(b.last_inspection_agency)],
  ];
  const cells = pairs.map(([k, v]) => `
    <div class="b-bldg-cell">
      <div class="b-bldg-k">${k}</div>
      <div class="b-bldg-v">${v}</div>
    </div>`).join("");
  const hint = b.detail_fetched_at ? ""
    : ` <span style="font-size:11px;color:#8a94a0;font-weight:500;margin-left:4px;">조회 중…</span>`;
  bldgInfoCard.innerHTML = `
    <div class="side-card-title">건축정보 <span class="side-sub">${isPreC ? "건축인허가" : "표제부"}</span>${hint}</div>
    <div class="b-bldg-grid">${cells}</div>`;

  // 타임라인(준공전 전용)
  if (isPreC){
    const tlCard = document.getElementById("bTimelineCard");
    const tlBody = document.getElementById("bTimelineBody");
    if (tlCard && tlBody){
      const fmtDay8 = (v) => {
        const s = (v == null) ? "" : String(v).trim();
        return /^\d{8}$/.test(s) ? `${s.slice(0,4)}.${s.slice(4,6)}.${s.slice(6,8)}` : "-";
      };
      const fmtExpected = (v) => {
        if (!v) return "-";
        const s = String(v).trim();
        if (/^\d{8}$/.test(s)) return `${s.slice(0,4)}.${s.slice(4,6)}.${s.slice(6,8)}`;
        if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0,10).replace(/-/g, ".");
        try {
          const d = new Date(s);
          if (!isNaN(d)) {
            const y = d.getUTCFullYear();
            const m = String(d.getUTCMonth()+1).padStart(2,"0");
            return `${y}.${m}`;
          }
        } catch(e){}
        return "-";
      };
      const steps = [
        { label: "건축허가", date: fmtDay8(b.permit_day),                       done: !!(b.permit_day) },
        { label: "착공",     date: fmtDay8(b.actual_start_day),                 done: !!(b.actual_start_day) },
        { label: "준공예정", date: fmtExpected(b.completion_expected_date),     done: false },
        { label: "사용승인", date: fmtDay8(b.use_apr_day),                      done: !!(b.use_apr_day) },
      ];
      const tcells = steps.map((s, i) => `
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;position:relative;">
          ${i > 0 ? `<div style="position:absolute;top:9px;left:-50%;width:100%;height:2px;background:${s.done ? "#378ADD" : "#D5DAE0"};"></div>` : ""}
          <div style="position:relative;z-index:1;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;background:${s.done ? "#378ADD" : "#C7CCD1"};">${s.done ? "✓" : ""}</div>
          <div style="margin-top:6px;font-size:12px;font-weight:700;color:${s.done ? "var(--ink)" : "var(--ink-soft)"};">${s.label}</div>
          <div style="margin-top:2px;font-size:11.5px;font-family:'JetBrains Mono',monospace;color:var(--ink-soft);">${s.date}</div>
        </div>`).join("");
      tlBody.innerHTML = `<div style="display:flex;align-items:flex-start;padding:6px 4px 2px;">${tcells}</div>`;
      tlCard.style.display = "";
    }
  }
}

// 백그라운드 조회 완료까지 폴링 — detail_fetched_at이 채워지면 카드 자동 갱신.
function _startDetailPoll(buildingId){
  _cancelDetailPoll();
  _detailPollBuildingId = buildingId;
  const MAX_TRIES  = 12;   // 최대 60초 (5s × 12)
  const INTERVAL   = 5000;
  let tries = 0;
  async function poll(){
    if (_detailPollBuildingId !== buildingId) return; // 다른 건물 열림 → 중단
    tries++;
    try {
      const res = await fetch("/api/building/" + buildingId);
      if (res.ok){
        const fresh = await res.json();
        if (_detailPollBuildingId !== buildingId) return;
        if (fresh.detail_fetched_at){
          _detailPollBuildingId = null;
          _renderDetailCards(fresh);
          return;
        }
      }
    } catch(e){ /* 네트워크 오류 — 다음 회차에 재시도 */ }
    if (tries < MAX_TRIES) _detailPollTimer = setTimeout(poll, INTERVAL);
  }
  _detailPollTimer = setTimeout(poll, INTERVAL);
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


  const isPreCompletion = b.building_status && b.building_status !== "완공";
  const hasType = !!(b.lodging_type && b.lodging_type !== "mixed_use_excluded");
  const typeBadge = hasType
    ? `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:${markerColor(b.lodging_type, "완공")}; padding:2px 9px; border-radius:6px; vertical-align:middle;">${escapeHtml(detailBadgeLabel(b.lodging_type, b.lodging_subtype))}</span>`
    : "";
  const preBadge = isPreCompletion
    ? `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:#9AA5B1; padding:2px 9px; border-radius:6px; vertical-align:middle; margin-left:${hasType ? "5px" : "0"};">🏗 준공예정 ${b.completion_expected_date ? escapeHtml(String(b.completion_expected_date)) : "미정"}</span>`
    : "";
  const badge = hasType || isPreCompletion
    ? `${typeBadge}${preBadge}`
    : `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:${LODGING_COLORS["미분류"]}; padding:2px 9px; border-radius:6px; vertical-align:middle;">미분류</span>`;
  const units = b.units != null ? Number(b.units).toLocaleString('ko-KR') + "실" : "-";
  // 영업신고 호수: 행안부 lodgings 합산값(행정운영 '신고'와 동일 소스) 우선, 없으면 master_buildings.biz_units fallback
  const lodgingRoomTotal = (b.lodging_room_total != null && Number(b.lodging_room_total) > 0)
    ? Number(b.lodging_room_total) : null;
  const bizUnitsNum = b.biz_units != null ? Number(b.biz_units) : null;
  const effectiveBizUnits = lodgingRoomTotal ?? bizUnitsNum;
  const bizUnits = effectiveBizUnits != null ? effectiveBizUnits.toLocaleString('ko-KR') + "실" : "-";
  // 신고율: lodging_report_rate 또는 effectiveBizUnits / units 즉석 계산
  const unitsNum = b.units != null ? Number(b.units) : null;
  let headerRate = "-";
  if (b.lodging_report_rate != null) {
    headerRate = Math.round(Number(b.lodging_report_rate)) + "%";
  } else if (effectiveBizUnits != null && unitsNum && unitsNum > 0) {
    headerRate = Math.round(effectiveBizUnits * 100 / unitsNum) + "%";
  }
  const bName = b.building_name || "(건물명 미확인)";
  bCurrentName = bName; // "매물 내놓기" 모달 제목 등에서 사용

  // 실거래목록 하단 "이 건물 전체 실거래 보기" — 건물명이 있을 때만 노출.
  const txAllLink = document.getElementById("bTxAllLink");
  if (txAllLink && b.building_name){
    txAllLink.href = "/transactions?q=" + encodeURIComponent(b.building_name);
    txAllLink.style.display = "inline-block";
  }

  // 주용도 — lodging_type("호텔·콘도")을 분리해 전체 명칭으로 표시. 복합이면 "·"로 이어 한 칸에 표시.
  const useParts = (b.lodging_type || "").split("·").filter(Boolean);
  const use1 = useParts[0]
    ? (LODGING_LABELS[useParts[0]] || useParts[0])
    : (b.lodging_type_detail ? escapeHtml(b.lodging_type_detail).slice(0, 30) : "-");
  const use2 = useParts[1] ? (LODGING_LABELS[useParts[1]] || useParts[1]) : "-";
  const useCombined = (use2 && use2 !== "-") ? `${use1}·${use2}` : use1;

  // 운영확인(OTA 등록) 배지 — 사실확인 톤만 유지, 행동유도 문구 없음
  const bookingBadge = b.booking_url
    ? `<span style="display:inline-block;font-size:12px;font-weight:700;color:#1a7a3c;` +
      `background:#E6F4EA;border:1px solid #B7E0C4;border-radius:5px;padding:2px 8px;cursor:pointer;" ` +
      `onclick="window.open('${escapeHtml(b.booking_url)}','_blank','noopener,noreferrer')">✓ OTA 등록확인</span>`
    : `<span style="font-size:12px;color:var(--ink-soft);">미확인</span>`;

  // 관심저장/실거래알림은 좌측 목록과 동일한 키(building_name|address)를 사용. address가
  // 없는(=거래이력 없는) 건물은 두 버튼을 비활성화한다.
  // 실거래 지번주소(b.address)가 있으면 그대로(좌측 목록과 키 일치), 없으면 마스터
  // 도로명주소(b.road_address)로 폴백 → 거래이력 없어도 주소만 있으면 버튼 활성화.
  const favAddr = (b.address != null && b.address !== "") ? b.address : (b.road_address || "");
  const favItem = { building_name: b.building_name, address: favAddr, building_id: b.id };
  const favKeyStr = favKey(favItem); // 관심저장과 동일한 키 규칙으로 알림도 저장한다
  const canFav = favAddr !== "";

  // 표제부 백필값 — 헤더 요약에도 반영 (없으면 "-")
  const useAprShort = isPreCompletion
    ? "준공전"
    : (b.use_apr_day != null && b.use_apr_day !== ""
        ? String(b.use_apr_day).slice(0, 7).replace("-", ".") : "-");
  const _autoP = (b.indr_auto_utcnt ?? 0) + (b.oudr_auto_utcnt ?? 0);
  const _mechP = (b.indr_mech_utcnt ?? 0) + (b.oudr_mech_utcnt ?? 0);
  const _calcPkng = _autoP + _mechP;
  const pkngTxt = _calcPkng > 0 ? _calcPkng.toLocaleString("ko-KR") + "대"
    : (b.tot_pkng_cnt != null && b.tot_pkng_cnt !== "" ? Number(b.tot_pkng_cnt).toLocaleString("ko-KR") + "대" : "-");
  const flrTxt = (b.grnd_flr_cnt != null || b.ugrnd_flr_cnt != null)
    ? `${b.grnd_flr_cnt != null ? b.grnd_flr_cnt : "-"} / ${b.ugrnd_flr_cnt != null ? b.ugrnd_flr_cnt : "-"}` : "-";

  headerCard.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px;">
      <h1 style="font-size:17px; font-weight:700; color:var(--ink); margin:0;">${escapeHtml(bName)}</h1>
      ${b.name_pending ? '<span style="font-size:11px; font-weight:600; color:#8a6d1f; background:#fdf6e3; border:1px solid #e8d9a0; border-radius:10px; padding:2px 8px; white-space:nowrap;">정식명칭 확인중</span>' : ""}
      ${badge}
    </div>
    ${(b.road_address || b.jibun_address || b.zip_code) ? `
    <div style="font-size:12px; color:var(--ink-soft); margin-bottom:12px;">
      <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
        <span style="width:44px; flex-shrink:0; white-space:nowrap; color:var(--ink-soft2,#999);">도로명</span>
        <span>${escapeHtml(b.road_address || "-")}</span>
        ${b.road_address ? `<button type="button" class="b-addr-copy" data-addr="${escapeHtml(b.road_address)}" title="도로명주소 복사" style="border:none;background:none;cursor:pointer;padding:2px;flex-shrink:0;color:var(--ink-soft2,#999);display:flex;align-items:center;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="4.5" width="8" height="8" rx="1.3"/><path d="M2 9.5V2.8A.8.8 0 0 1 2.8 2H9.5"/></svg></button>` : ""}
      </div>
      <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
        <span style="width:44px; flex-shrink:0; white-space:nowrap; color:var(--ink-soft2,#999);">지번</span>
        <span>${escapeHtml(b.jibun_address || "-")}</span>
        ${b.jibun_address ? `<button type="button" class="b-addr-copy" data-addr="${escapeHtml(b.jibun_address)}" title="지번주소 복사" style="border:none;background:none;cursor:pointer;padding:2px;flex-shrink:0;color:var(--ink-soft2,#999);display:flex;align-items:center;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="4.5" width="8" height="8" rx="1.3"/><path d="M2 9.5V2.8A.8.8 0 0 1 2.8 2H9.5"/></svg></button>` : ""}
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
        <span style="width:52px; flex-shrink:0; white-space:nowrap; color:var(--ink-soft2,#999);">우편번호</span>
        <span>${escapeHtml(b.zip_code || "-")}</span>
        ${b.zip_code ? `<button type="button" class="b-addr-copy" data-addr="${escapeHtml(b.zip_code)}" title="우편번호 복사" style="border:none;background:none;cursor:pointer;padding:2px;flex-shrink:0;color:var(--ink-soft2,#999);display:flex;align-items:center;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="4.5" width="8" height="8" rx="1.3"/><path d="M2 9.5V2.8A.8.8 0 0 1 2.8 2H9.5"/></svg></button>` : ""}
      </div>
    </div>` : `<div style="font-size:12px; color:var(--ink-soft); margin-bottom:12px;">주소 미확인</div>`}
    ${b.name_pending && b.sgg_cd && b.umd_nm && b.jibun ? `
    <div id="bNameSuggest" style="margin:-4px 0 12px;">
      <button type="button" id="bNameSuggestOpen" style="background:none; border:none; padding:0; cursor:pointer; font-size:12px; font-weight:600; color:var(--brass-dark); text-decoration:underline;">✏️ 건물명 제안하기</button>
      <div id="bNameSuggestBox" style="display:none; margin-top:8px; padding:10px 12px; border:1px solid var(--line); border-radius:9px; background:#fbfaf7;">
        <div style="font-size:12.5px; font-weight:600; color:var(--ink); margin-bottom:7px;">정확한 건물명을 알고 계신가요?</div>
        <div style="display:flex; gap:6px;">
          <input type="text" id="bNameSuggestInput" maxlength="60" placeholder="예: ○○스테이 서천"
                 style="flex:1; min-width:0; border:1px solid var(--line); border-radius:7px; padding:7px 9px; font-size:13px;">
          <button type="button" id="bNameSuggestSubmit"
                  style="border:none; border-radius:7px; background:var(--brass); color:#fff; font-size:12.5px; font-weight:700; padding:7px 12px; cursor:pointer; white-space:nowrap;">제안하기</button>
        </div>
        <div id="bNameSuggestMsg" style="display:none; margin-top:7px; font-size:12px;"></div>
      </div>
    </div>` : ""}
    <div class="b-actions">
      <button type="button" id="bAlertBtn" class="b-icon-btn" title="실거래 알림">🔔<span class="b-icon-label">실거래알림</span></button>
      <button type="button" id="bFavBtn" class="b-icon-btn" title="관심 저장">⭐<span class="b-icon-label">관심저장</span></button>
      <button type="button" id="bShareBtn" class="b-icon-btn" title="공유">🔗<span class="b-icon-label">공유</span></button>
      ${b.lat != null && b.lng != null ? `<button type="button" id="bMapLocBtn" class="b-icon-btn" title="지도 위치 보기">📍<span class="b-icon-label">지도위치</span></button>` : ""}
    </div>
    ${canFav ? `<div id="bFavHint" style="font-size:11.5px; color:var(--ink-soft); margin:2px 0 8px; text-align:center;">저장하면 이 건물의 새 실거래를 이메일로 알려드립니다</div>` : ""}
    <div style="display:flex; gap:14px; flex-wrap:wrap; border-top:1px solid var(--line); padding-top:12px;">
      ${bStat("주용도", useCombined)}
      ${bStat("운영확인", bookingBadge, { rawValue: true })}
      ${bStat("준공월", useAprShort)}
      ${bStat("총 호실", units)}
      ${bStat("영업신고 호수", bizUnits)}
      ${bStat("신고율", headerRate)}
      ${bStat("총주차", pkngTxt)}
      ${bStat("층수(지상/지하)", flrTxt)}
    </div>`;

  // 건물명 제안하기(명칭 미확정 건물 전용) — 기존 /api/request-correction의
  // suggested_building_name 파라미터를 그대로 재사용한다(새 엔드포인트 없음).
  const nameSuggestOpen = document.getElementById("bNameSuggestOpen");
  if (nameSuggestOpen){
    const boxEl = document.getElementById("bNameSuggestBox");
    const inputEl = document.getElementById("bNameSuggestInput");
    const submitEl = document.getElementById("bNameSuggestSubmit");
    const msgEl = document.getElementById("bNameSuggestMsg");
    nameSuggestOpen.addEventListener("click", () => {
      const open = boxEl.style.display !== "none";
      boxEl.style.display = open ? "none" : "block";
      if (!open) inputEl.focus();
    });
    const showMsg = (text, ok) => {
      msgEl.style.display = "block";
      msgEl.style.color = ok ? "#2F7D52" : "#B3453A";
      msgEl.textContent = text;
    };
    const doSubmit = async () => {
      const name = inputEl.value.trim();
      if (!name){ showMsg("건물명을 입력해주세요.", false); inputEl.focus(); return; }
      submitEl.disabled = true;
      showMsg("제안을 접수하고 있습니다…", true);
      try {
        const res = await fetch("/api/request-correction", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sgg_cd: b.sgg_cd, umd_nm: b.umd_nm, jibun: b.jibun,
            suggested_building_name: name,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && (data.status === "verified" || data.status === "name_review")){
          // 즉시 반영되는 것처럼 오해하지 않도록 고정 문구(관리자 확인 후 반영).
          if (data.name_changed){
            showMsg("✓ " + (data.message || "건축물대장에서 명칭이 확인되어 반영되었습니다."), true);
            setTimeout(() => renderBuildingPanel(id), 1800);
          } else {
            showMsg("✓ 제안이 접수됐습니다. 확인 후 반영되며, 영업일 기준 1~2일 정도 소요될 수 있습니다.", true);
            inputEl.value = "";
          }
        } else {
          showMsg(data.message || "제안 접수에 실패했습니다. 잠시 후 다시 시도해주세요.", false);
          submitEl.disabled = false;
        }
      } catch(e){
        showMsg("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", false);
        submitEl.disabled = false;
      }
    };
    submitEl.addEventListener("click", doSubmit);
    inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") doSubmit(); });
  }

  // 헤더 액션 버튼 배선 — 관심저장/실거래알림 상태 동기화 + 공유
  const alertBtn = document.getElementById("bAlertBtn");
  const favBtn = document.getElementById("bFavBtn");
  const shareBtn = document.getElementById("bShareBtn");
  function syncFavBtn(){
    const on = canFav && isFav(favItem);
    favBtn.classList.toggle("on", on);
    favBtn.querySelector(".b-icon-label").textContent = on ? "저장됨" : "관심저장";
    // ② 저장됐을 때 안내 문구 숨김
    const hint = document.getElementById("bFavHint");
    if (hint) hint.style.display = on ? "none" : "";
  }
  function syncAlertBtn(){
    const on = canFav && isAlertOn(favKeyStr);
    alertBtn.classList.toggle("on", on);
    alertBtn.querySelector(".b-icon-label").textContent = on ? "실거래알림켜짐" : "실거래알림";
  }
  // 헤더 알림 새로고침(refreshAlertsUI) 시 현재 열린 B패널 버튼을 다시 그리기 위한 훅.
  window.__syncOpenAlertBtn = function(){ if (canFav) syncAlertBtn(); };
  if (canFav){
    // 서버 구독 목록이 아직 로드 전이면 로드 후 버튼 상태 반영.
    if (window.__livingstayLoggedIn && !alertsLoaded) loadServerAlerts(syncAlertBtn);
    syncFavBtn(); syncAlertBtn();
    favBtn.addEventListener("click", () => { const ok = toggleFav(favItem); if (ok !== false) syncFavBtn(); });
    alertBtn.addEventListener("click", () => {
      // 사업자 체크를 비로그인 체크보다 먼저 (사업자도 __livingstayLoggedIn=false임)
      if (window.__livingstayAccountType && window.__livingstayAccountType !== "user"){ alert("실거래 알림은 일반회원 전용 기능입니다. 개인 이용을 원하시면 별도로 일반회원 가입해주세요."); return; }
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
    const shareData = { title: `${bName} | 숙박시설 실거래가 & 위탁운영 플랫폼 . 홈앤스테이`, url };
    if (navigator.share){
      try { await navigator.share(shareData); } catch(e){ /* 사용자가 취소 */ }
    } else if (navigator.clipboard){
      try { await navigator.clipboard.writeText(url); alert("링크가 복사되었습니다."); }
      catch(e){ prompt("아래 주소를 복사하세요:", url); }
    } else {
      prompt("아래 주소를 복사하세요:", url);
    }
  });

  // 지도위치 버튼 — 좌표가 있는 건물에만 렌더링됨
  const mapLocBtn = document.getElementById("bMapLocBtn");
  if (mapLocBtn){
    mapLocBtn.addEventListener("click", () => {
      if (!kakaoMap || b.lat == null || b.lng == null) return;
      // level 3 = 개별마커 모드(_clusterModeForLevel 기준), 클러스터 단계 생략
      kakaoMap.setLevel(3);
      kakaoMap.setCenter(new kakao.maps.LatLng(b.lat, b.lng));
      updateMapForZoom(mapFiltersFromState(), { force: true });
    });
  }

  // 주소 복사 버튼 — 도로명/지번/우편번호 3줄 공통 (이벤트 위임)
  headerCard.querySelectorAll(".b-addr-copy").forEach(btn => {
    btn.addEventListener("click", async () => {
      const addr = btn.dataset.addr;
      if (!addr) return;
      if (navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(addr);
          const orig = btn.textContent;
          btn.textContent = "✅";
          setTimeout(() => { btn.textContent = orig; }, 1200);
        } catch(e) { alert("복사에 실패했습니다."); }
      } else {
        prompt("아래 주소를 복사하세요:", addr);
      }
    });
  });

  if (isPreCompletion) {
    adminCard.innerHTML = `
      <div class="side-card-title">행정운영 <span class="side-sub">숙박업영업신고</span></div>
      <div class="side-empty">준공 전입니다. 사용승인 후 영업신고 정보가 표시됩니다.</div>
    `;

    // 타임라인은 _renderDetailCards()가 담당 (폴링 갱신과 공유)
  } else {
    // [2] 행정운영 표 — 행안부 영업신고 데이터(영업/정상만) 기반.
    //     신고율 = 영업 중 객실수 합 / 총 호실수(units). 데이터 미수집이면 "확인 불가".
    const lodgings = Array.isArray(b.lodgings) ? b.lodgings : [];
    const roomTotal = Number(b.lodging_room_total || 0);
    let rateDisplay;
    const _adminUnits = b.units != null ? Number(b.units) : 0;
    if (b.lodging_report_rate != null){
      rateDisplay = Math.round(Number(b.lodging_report_rate)) + "%";
    } else if (roomTotal > 0 && _adminUnits > 0){
      // lodging_room_total(행안부 합산)로 즉석 계산 — 헤더 신고율과 동일 소스
      rateDisplay = Math.round(roomTotal * 100 / _adminUnits) + "%";
    } else if (_adminUnits > 0 && lodgings.length === 0){
      rateDisplay = "0%";
    } else {
      rateDisplay = "확인 불가";
    }
    const reportedRooms = roomTotal > 0 ? roomTotal.toLocaleString('ko-KR') + "실" : "-";
    const notReported = (b.units != null && Number(b.units) > 0)
      ? Math.max(Number(b.units) - roomTotal, 0).toLocaleString('ko-KR') + "실"
      : "-";
    // 영업신고 사업장 목록 — 서버가 이미 등록운영업체(priority 순) → 미등록(랜덤)으로 정렬해서 내려줌
    const lodgingRows = lodgings.map((l) => {
      const name = l.registered && l.operator_slug
        ? `<a href="/operator/${encodeURIComponent(l.operator_slug)}?building_id=${b.id}&building_name=${encodeURIComponent(b.building_name||"")}" style="display:inline-block; font-size:12.5px; font-weight:700; color:#fff; background:var(--brass-dark); border-radius:5px; padding:2px 8px; text-decoration:none;">${escapeHtml(l.biz_name)}</a>`
        : escapeHtml(l.biz_name);
      const rooms = (l.room_count != null && Number(l.room_count) > 0)
        ? Number(l.room_count).toLocaleString('ko-KR') + "실" : "-";
      return `<tr><td style="text-align:left;">${name}</td><td style="white-space:nowrap;">${rooms}</td></tr>`;
    }).join("");
    const lodgingListHtml = lodgings.length
      ? `<div style="font-size:12px; font-weight:700; color:var(--ink-soft); margin:10px 0 4px;">영업 중 신고업소 ${lodgings.length}곳</div>
         <table class="b-info-table" style="margin-bottom:12px;"><tbody>${lodgingRows}</tbody></table>`
      : "";
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
          <tr><th>신고</th><td>${reportedRooms}</td></tr>
          <tr><th>미신고</th><td>${notReported}</td></tr>
          <tr><th>담당부처</th><td>${deptCell}</td></tr>
          <tr><th>연락처</th><td>${phoneCell}</td></tr>
        </tbody>
      </table>
      ${lodgingListHtml}
      <a href="https://jnjclub.co.kr/" target="_blank" rel="noopener noreferrer" style="display:block; margin-top:0;" title="숙박업등록·위탁운영 무료 상담 신청">
        <img src="/static/banner_biz_report.png" alt="우수부동산서비스인증 — 숙박업등록·위탁운영 의뢰하기, 무료 상담 신청" style="display:block; width:100%; height:auto; border-radius:10px;" />
      </a>`;
  }

  renderBuildingAgents(b.agents || (b.agent ? [b.agent] : []), b.more_agents || [], id, bName, b.building_status);

  // 위탁운영/운영지원업체(하우스키핑) 카드의 "지원업체로 신청하기" 링크에 건물 정보 연결
  // (실제 업종(category) 선택은 신청폼 안에서 함 — agent 신청 링크와 동일 패턴)
  const operApplyHref = `/apply/operator?building_id=${id != null ? encodeURIComponent(id) : ""}&building_name=${encodeURIComponent(bName || "")}`;
  ["lnkOperatorApply", "lnkHousekeepingApply"].forEach((lid) => {
    const a = document.getElementById(lid);
    if (a) a.href = operApplyHref;
  });

  // 담당 운영지원업체가 등록된 건물이면 유치 문구 대신 업체명 + 프로필 링크 표시
  renderBuildingOperators(b.operator_by_category, id, bName);

  // 금융 카드 — 이 건물에 연결된(loan_consultant_buildings) 승인 대출상담사가 있으면 상담사 카드로 교체,
  // 없으면 "이 건물에 대출상담사로 신청하기" 모집 카드 표시
  renderBuildingLoanConsultants(b.loan_consultants, id, bName, b.building_status);

  // 건축정보(표제부) + 타임라인 — _renderDetailCards 공유 렌더러로 그린다.
  // detail_fetched_at이 없으면 "조회 중…" 힌트가 표시되고 폴링이 자동 시작된다.
  _renderDetailCards(b);
  if (!b.detail_fetched_at
      && b.sgg_cd && b.umd_nm && b.jibun) {
    _startDetailPoll(id);
  }

  return b.building_status || "완공";
}

// 상거래정보 카드 — /api/building/<id>/nearby-stores 로 이 건물(지번)의
// 상가업소를 업종별 요약 + 층별 목록으로 그린다. 최대 15개 먼저 보여주고 "더보기".
async function loadBuildingStores(buildingId){
  const card = document.getElementById("bStoresCard");
  if (!card) return;
  let data;
  // 백그라운드 스레드 완료 대기 — pending:true 시 4초 간격 최대 4회 재조회
  for (let _poll = 0; _poll <= 4; _poll++) {
    try {
      const res = await fetch(`/api/building/${buildingId}/nearby-stores`);
      if (!res.ok) return;
      data = await res.json();
    } catch(e){ return; }
    if (!data.pending) break;
    if (_poll < 4) await new Promise(r => setTimeout(r, 4000));
  }
  // 실패 사유를 콘솔에 남겨 다음 번에 브라우저 콘솔만 봐도 원인을 알 수 있게 함
  if (data && data.reason) console.warn("[상거래정보] 실패 사유:", data.reason);
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
    <div class="side-card-title">상가정보 <span class="side-sub">건물 내 상가업소 ${Number(data.total).toLocaleString('ko-KR')}곳</span></div>
    ${summary ? `<div style="font-size:12.5px; color:var(--ink-soft); margin:2px 0 8px; line-height:1.6;">${summary}</div>` : ""}
    <div style="max-height:280px; overflow-y:auto;">
      <div>${first}</div>
      ${rest ? `<div id="bStoresRest" style="display:none;">${rest}</div>` : ""}
    </div>
    ${rest ? `<button type="button" class="side-more" id="bStoresMoreBtn">더보기 (${data.stores.length - FIRST}곳)</button>` : ""}
    `;

  const moreBtn = document.getElementById("bStoresMoreBtn");
  if (moreBtn){
    moreBtn.addEventListener("click", () => {
      const restBox = document.getElementById("bStoresRest");
      if (restBox) restBox.style.display = "";
      moreBtn.remove();
    });
  }
}

// 위탁운영 카드 — '위탁운영' 카테고리 담당 업체가 있으면 업체 카드 표시,
// 없으면 기본 모집 박스(recruitBoxHTML "consign") 그대로 유지.
// ※ 청소·세탁·용품·소독·세무·인테리어 업종 행은 이 카드에서 표시하지 않는다
//   (해당 업종 모집은 운영지원업체 섹션에서 일괄 안내).
function renderBuildingOperators(operatorByCategory, buildingId, buildingName){
  const box = document.getElementById("bOperatorBox");
  if (!box) return;
  const all = Array.isArray(operatorByCategory) ? operatorByCategory : [];
  // 위탁운영 카테고리만 추려낸다
  const consignItems = all.filter(it => it.category === "위탁운영" && it.company_name);
  if (!consignItems.length) return;  // 담당 없으면 기본 모집 박스 유지

  const applyHref = `/apply/operator?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}`;
  box.innerHTML = consignItems.map(it => {
    const badge = it.tier === "premium" ? "🧭" : "📍";
    const nameEl = it.tier === "premium" && it.subdomain_slug
      ? `<a href="/operator/${encodeURIComponent(it.subdomain_slug)}?building_id=${buildingId}&building_name=${encodeURIComponent(buildingName||"")}" style="font-size:13px; font-weight:700; color:var(--ink); text-decoration:none;">${escapeHtml(it.company_name)}</a>`
      : `<span style="font-size:13px; font-weight:600; color:var(--ink);">${escapeHtml(it.company_name)}</span>`;
    return `<div style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 2px; border-bottom:1px solid var(--line,#eee);">
      <span style="font-size:11.5px; color:var(--ink-soft); width:52px; flex-shrink:0;">${badge} 위탁</span>
      <span style="flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${nameEl}</span>
      ${it.phone ? `<a href="tel:${escapeHtml(it.phone)}" style="font-size:16px; text-decoration:none;" onclick="event.stopPropagation();">📞</a>` : ""}
    </div>`;
  }).join("");
}

// 금융/대출상담 카드 — 지역매칭 상담사 전원 골드 스타일로 바로 노출
function renderBuildingLoanConsultants(consultants, buildingId, buildingName, buildingStatus){
  const box = document.getElementById("bFinanceBox");
  if (!box) return;
  const isPreCompletion = buildingStatus && buildingStatus !== "완공";
  const items = Array.isArray(consultants) ? consultants : [];
  const applyHref = `/apply/loan?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}`;

  if (!items.length){
    box.innerHTML = `
      ${recruitBoxHTML("finance", { href: applyHref, btnText: "이 건물에 대출상담사로 신청하기", preCompletion: isPreCompletion })}`;
    return;
  }

  const mkCard = (c, isGold) => {
    const avatar = c.logo_src
      ? `<img src="${escapeHtml(c.logo_src)}" alt="로고" style="width:40px;height:40px;border-radius:50%;object-fit:cover;background:#fff;border:1px solid var(--line,#eee);" onerror="this.outerHTML='<div style=&quot;width:40px;height:40px;border-radius:50%;background:var(--brass-tint);color:var(--brass-dark);display:flex;align-items:center;justify-content:center;font-size:18px;&quot;>💰</div>'" />`
      : `<div style="width:40px;height:40px;border-radius:50%;background:var(--brass-tint);color:var(--brass-dark);display:flex;align-items:center;justify-content:center;font-size:18px;">💰</div>`;
    const kakaoUrl = /^https?:\/\//i.test(String(c.kakao_chat_url || "")) ? c.kakao_chat_url : null;
    const wrap = isGold
      ? `style="background:var(--brass-tint);border-radius:10px;padding:10px;margin-bottom:6px;"`
      : `style="padding:10px 0;border-bottom:1px solid var(--line,#eee);"`;
    const nameEl = isGold && c.subdomain_slug
      ? `<a href="/loan-consultant/${encodeURIComponent(c.subdomain_slug)}?building_id=${buildingId}&building_name=${encodeURIComponent(buildingName||"")}" style="font-size:14px;font-weight:700;color:var(--brass-dark);text-decoration:none;">${escapeHtml(c.office_name || "-")}</a>`
      : `<div style="font-size:14px;font-weight:600;color:var(--ink);">${escapeHtml(c.office_name || "-")}</div>`;
    const contactRow = c.phone ? `
      <div style="display:flex;gap:14px;margin-top:6px;">
        <a href="tel:${escapeHtml(c.phone)}" style="font-size:18px;text-decoration:none;" onclick="event.stopPropagation();" aria-label="전화">📞</a>
        <a href="sms:${escapeHtml(c.phone)}" style="font-size:18px;text-decoration:none;" onclick="event.stopPropagation();" aria-label="문자">💬</a>
        ${isGold && kakaoUrl ? `<a href="${escapeHtml(kakaoUrl)}" target="_blank" rel="noopener noreferrer" style="font-size:18px;text-decoration:none;" aria-label="카카오">💛</a>` : ""}
      </div>` : "";
    return `<div ${wrap}><div style="display:flex;align-items:center;gap:12px;">${avatar}<div style="flex:1;min-width:0;">${nameEl}</div>${contactRow}</div></div>`;
  };

  let html = items.map(c => mkCard(c, true)).join("");

  // 상담 신청은 프로필 페이지에서 처리 — 여기서는 버튼 없음
  html += `
    <div style="font-size:11px;color:var(--ink-soft);margin-top:8px;">모든 상담은 무료이며, 상담 시 수수료를 요구하는 것은 불법입니다.</div>
    <div style="margin-top:8px;text-align:right;"><a href="/loan-consultants" style="font-size:12px;font-weight:600;color:var(--brass-dark);text-decoration:none;">전체 대출상담사 보기 →</a></div>`;
  box.innerHTML = html;
}

function renderBuildingAgents(agents, moreAgents, buildingId, buildingName, buildingStatus){
  const isPreCompletion = buildingStatus && buildingStatus !== "완공";
  const box = document.getElementById("bAgentBox");
  if (!box) return;
  const list = Array.isArray(agents) ? agents : [];
  if (list.length){
    // 최대 3명 카드 스택 — 기존 단일 카드 스타일을 세로로 나열 (서버가 priority_score DESC, RANDOM()으로 최대 3명 반환)
    box.innerHTML = list.map((agent) => {
      // 프로필 사진(photo_src)이 있으면 원형 썸네일, 없으면 기존 🏢 아이콘 (아실 스타일)
      const avatar = agent.photo_src
        ? `<img src="${escapeHtml(agent.photo_src)}" alt="담당중개사 사진" style="width:44px; height:44px; border-radius:50%; object-fit:cover; border:1px solid var(--line); flex-shrink:0;" onerror="this.outerHTML='<div style=&quot;width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center; font-size:18px;&quot;>🏢</div>'">`
        : `<div style="width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center; font-size:18px;">🏢</div>`;
      // 이 건물 한정 매물 건수 배지 4개 — 값이 0이어도 표시, 한 줄 고정 (agent_buildings 기준)
      const cnt = (v) => (v == null ? 0 : v);
      const badge = (label, v) => `<span style="display:inline-flex; align-items:center; font-size:8.4px; font-weight:700; color:var(--brass-dark); white-space:nowrap;">${label}(${cnt(v)})</span>`;
      const badges = `<div style="display:flex; gap:4px; margin-top:6px;">
        ${badge("매매", agent.sale_count)}${badge("전세", agent.jeonse_count)}${badge("월세", agent.wolse_count)}${badge("단기", agent.shortterm_count)}
      </div>`;
      const isRegion = !!agent.is_region_agent;
      const hasBadge = agent.has_priority_badge && !isRegion;
      const avatarWrap = `<div style="position:relative; flex-shrink:0; padding-bottom:${hasBadge || isRegion ? "14" : "0"}px;">
        ${avatar}
        ${hasBadge ? `<span style="position:absolute; bottom:0; left:50%; transform:translateX(-50%); display:inline-flex; align-items:center; gap:2px; font-size:9.5px; font-weight:700; color:#fff; background:var(--brass-dark); padding:2px 7px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.3); white-space:nowrap;">🧭 단지</span>` : ""}
        ${isRegion ? `<span style="position:absolute; bottom:0; left:50%; transform:translateX(-50%); display:inline-flex; align-items:center; gap:2px; font-size:9.5px; font-weight:700; color:#fff; background:#9AA5B1; padding:2px 7px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.3); white-space:nowrap;">📍 지역담당</span>` : ""}
      </div>`;
      return `
      <div style="padding:10px 0; border-bottom:1px solid var(--line, #eee);">
        <div style="display:flex; align-items:flex-start; gap:12px;">
          ${avatarWrap}
          <div style="flex:1; min-width:0;">
            ${(!isRegion && agent.subdomain_slug)
              ? `<a href="/agent/${encodeURIComponent(agent.subdomain_slug)}?building_id=${buildingId}" style="font-size:14px; font-weight:600; color:var(--ink); text-decoration:none;">${escapeHtml(agent.office_name || "-")}</a>`
              : `<div style="font-size:14px; font-weight:600; color:var(--ink);">${escapeHtml(agent.office_name || "-")}</div>`}
            ${isRegion ? "" : badges}
            ${agent.phone ? `<div style="display:flex; gap:24px; margin-top:6px;">
              <a href="tel:${escapeHtml(agent.phone)}" style="font-size:12px; color:var(--brass-dark); text-decoration:none;" onclick="event.stopPropagation();">📞 전화</a>
              <a href="sms:${escapeHtml(agent.phone)}" style="font-size:12px; color:var(--brass-dark); text-decoration:none;" onclick="event.stopPropagation();">💬 문자</a>
            </div>` : ""}
            ${agent.office_phone ? `<div style="font-size:12.5px; color:var(--ink-soft); margin-top:2px;">☎️ ${escapeHtml(window.formatPhone ? formatPhone(agent.office_phone) : agent.office_phone)}</div>` : ""}
          </div>
        </div>
      </div>`;
    }).join("");
  } else {
    box.innerHTML = recruitBoxHTML("agent", {
      href: `/apply/agent?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}`,
      btnText: "이 건물에 담당중개사로 신청하기",
      preCompletion: isPreCompletion,
    });
  }
  if (moreAgents && moreAgents.length) {
    const moreHtml = moreAgents.map(agent => `
      <div style="padding:8px 0; border-bottom:1px solid var(--line, #eee); display:flex; align-items:center; gap:10px;">
        <div style="flex:1; min-width:0; font-size:13px; color:var(--ink);">${escapeHtml(agent.office_name || "-")}</div>
        ${agent.phone ? `<a href="tel:${escapeHtml(agent.phone)}" style="font-size:11.5px; color:var(--brass-dark); text-decoration:none;" onclick="event.stopPropagation();">📞 전화</a>` : ""}
      </div>`).join("");
    box.innerHTML += `
      <details style="margin-top:8px;">
        <summary style="cursor:pointer; font-size:12.5px; color:var(--ink-soft); padding:6px 0;">등록된 부동산 더보기 (${moreAgents.length})</summary>
        <div style="margin-top:4px;">${moreHtml}</div>
      </details>`;
  }
}

async function loadBuildingTrend(id, buildingStatus){
  const canvas = document.getElementById("bTrendChart");
  const empty = document.getElementById("bTrendEmpty");
  if (buildingStatus && buildingStatus !== "완공") {
    // 병렬 시작된 첫 번째 호출(null status)이 차트를 이미 그렸을 수 있으므로 파기
    if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }
    canvas.style.display = "none";
    empty.style.display = "block";
    empty.textContent = "준공 전입니다. 준공 후 실거래 정보가 제공됩니다.";
    return;  // API 호출 자체를 생략(불필요한 요청 절약)
  }
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

async function loadBuildingTx(id, buildingStatus){
  if (buildingStatus && buildingStatus !== "완공") {
    document.getElementById("bTxTableWrap").innerHTML =
      '<div class="side-empty">준공 전입니다. 준공 후 실거래 목록이 표시됩니다.</div>';
    return;
  }
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
      const res = await fetch(`/api/transactions?building_id=${id}&page=${page}&size=${size}&with_total=1`);
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
  _cancelDetailPoll(); // 이전 건물의 폴링이 살아있으면 즉시 중단
  if (sideTrendChart){ sideTrendChart.destroy(); sideTrendChart = null; }
  if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }

  panel.innerHTML = buildingPanelSkeleton();
  panel.scrollTop = 0;
  panel.classList.add("open"); // 모바일에서도 상세가 보이도록 패널을 펼친다

  // "← 전체 목록으로" 링크: 기본 패널 복귀 + URL "/"
  const closeDetail = () => {
    history.pushState({}, "", "/");
    if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/" });
    restoreDefaultPanel();
  };
  document.getElementById("btnBackToList").addEventListener("click", closeDetail);
  document.getElementById("btnListingRequest").addEventListener("click", () => {
    if (!window.__livingstayLoggedIn){
      if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
      else location.href = "/?login=1";
      return;
    }
    openListingRequestModal(id, bCurrentName || "");
  });
  document.getElementById("btnBuyRequest").addEventListener("click", () => {
    if (!window.__livingstayLoggedIn){
      if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
      else location.href = "/?login=1";
      return;
    }
    openBuyRequestModal(id, bCurrentName || "");
  });
  document.getElementById("bTxMore").addEventListener("click", () => {
    bTxShown += B_TX_STEP;
    loadBuildingTx(id);
  });

  bTxShown = B_TX_INITIAL;
  bTxTotal = 0;
  // 4개 카드를 동시에 시작 — 헤더 응답을 기다리지 않음(B-2 병렬화)
  loadBuildingStores(id);
  loadBuildingTrend(id, null);   // null = 완공 가정으로 즉시 API 시작
  loadBuildingTx(id, null);      // 동일
  loadBuildingHeader(id).then(status => {
    // 헤더 응답 후 준공전이면 trend/tx를 status 기준으로 덮어씀
    if (status && status !== "완공") {
      loadBuildingTrend(id, status);
      loadBuildingTx(id, status);
    }
  });
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
  if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/building/" + id });
  if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
  renderBuildingPanel(id);
  return false;
};

// 브라우저 뒤로/앞으로 가기 대응
window.addEventListener("popstate", () => {
  const m = location.pathname.match(/^\/building\/(\d+)/);
  if (m) {
    renderBuildingPanel(Number(m[1]));
    if (typeof gtag === "function") gtag("event", "page_view", { page_path: location.pathname });
  } else {
    restoreDefaultPanel();
    if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/" });
  }
});

// 범례 타이틀 + 용도별 건물 수 — 통계 대시보드와 동일한 집계 기준
// by_type 매핑: 생활·관광·일반·복합·준공전·미분류
// 범례의 '복합' 항목 = 실제복합 + mixed_use_excluded + NULL(대시보드 기준과 동일)
async function loadBuildingCountLabel(){
  const countEl = document.getElementById("mapCount");
  try {
    const res = await fetch("/api/building-count");
    const d = await res.json();

    // 타이틀: "1,399건/실거래 10,726건"
    if (countEl && typeof d.count === "number") {
      const bldStr = d.count.toLocaleString("ko-KR") + "건";
      const txStr  = typeof d.tx_count === "number"
        ? "/실거래 " + d.tx_count.toLocaleString("ko-KR") + "건"
        : "";
      countEl.textContent = `(${bldStr}${txStr})`;
    }

    // 범례 항목별 숫자 (대시보드 기준 by_type)
    if (d.by_type) {
      document.querySelectorAll(".map-legend .lg[data-lodging-type]").forEach(el => {
        const type = el.dataset.lodgingType;
        const cnt = d.by_type[type] || 0;
        let cntEl = el.querySelector(".lg-count");
        if (!cntEl) {
          cntEl = document.createElement("span");
          cntEl.className = "lg-count";
          el.appendChild(cntEl);
        }
        cntEl.textContent = cnt ? cnt.toLocaleString("ko-KR") : "";
      });
    }
  } catch(e){ console.error("[지도] 건물 건수 로드 실패:", e); }
}

// 최초 로드: 기본 패널 초기화 후, URL이 /building/<id>면 자동으로 상세를 연다.
initDefaultSidePanel();
loadBuildingCountLabel();
(function(){
  const m = location.pathname.match(/^\/building\/(\d+)/);
  if (m) renderBuildingPanel(Number(m[1]));
})();
