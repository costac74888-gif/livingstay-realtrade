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
function toggleFav(item){
  let favs = getFavorites();
  const k = favKey(item);
  let clearedActiveFilter = false;
  if (favs.includes(k)){
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
  updateFavCountLabel();
  renderFavChips();
  if (clearedActiveFilter){ document.getElementById("chkFavOnly").checked = false; loadBoard(); }
  return true;
}
function removeFav(key){
  const favs = getFavorites().filter(x=>x!==key);
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
  if (state.favKey === key){ state.favKey = null; state.favOnly = false; }
  updateFavCountLabel();
  renderFavChips();
  loadBoard();
}
function updateFavCountLabel(){
  document.getElementById("favCountLabel").textContent =
    `저장된 관심단지 ${getFavorites().length}/${MAX_FAVORITES}개`;
}
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
});
document.getElementById("chkFavOnly").addEventListener("change", e=>{
  state.favOnly = e.target.checked; state.favKey = null; state.page = 1;
  renderFavChips(); loadBoard();
});
document.getElementById("btnSearch").addEventListener("click", ()=>{
  state.q = document.getElementById("inputQ").value.trim();
  state.page = 1;
  loadBoard();
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

async function initMap(){
  const container = document.getElementById("map");
  if (!container) return;

  kakaoMap = new kakao.maps.Map(container, {
    center: new kakao.maps.LatLng(36.2, 127.9), // 대한민국 중앙 근처
    level: 13,                                   // 전국이 한눈에 보이는 확대 수준
  });

  let items = [];
  try {
    const res = await fetch("/api/buildings-geo");
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    console.error("[MAP] 건물 좌표 로드 실패:", e);
    return;
  }

  let placed = 0;
  items.forEach(b => {
    if (b.lat == null || b.lng == null) return;
    const color = markerColor(b.lodging_type);
    const pos = new kakao.maps.LatLng(b.lat, b.lng);
    const el = document.createElement("div");
    el.style.cssText = `width:14px; height:14px; border-radius:50%; background:${color};` +
      `border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.4); cursor:pointer;`;
    el.title = b.building_name || "";
    const overlay = new kakao.maps.CustomOverlay({
      position: pos, content: el, xAnchor: 0.5, yAnchor: 0.5, clickable: true,
    });
    overlay.setMap(kakaoMap);
    el.addEventListener("click", () => openBuildingInfo(b, pos));
    placed++;
  });

  const countLabel = document.getElementById("mapCount");
  if (countLabel) countLabel.textContent = `(${placed}개 건물)`;
  console.log(`[MAP] 카카오맵 마커 ${placed}개 표시 완료 (전체 ${items.length}건)`);
}

async function openBuildingInfo(b, pos){
  if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }

  const name = escapeHtml(b.building_name || "(건물명 미확인)");
  const typeKo = escapeHtml(lodgingLabelKo(b.lodging_type));

  let dealHtml = `<div style="color:#8a94a0;">실거래 이력 없음</div>`;
  try {
    const params = new URLSearchParams({ q: b.building_name || "", size: 1, page: 1 });
    const res = await fetch(`/api/transactions?${params}`);
    const data = await res.json();
    const t = (data.items || [])[0];
    if (t){
      const price = Number(t.price || 0).toLocaleString('ko-KR');
      const area = t.area != null ? Number(t.area).toFixed(1) + "㎡" : "-";
      const floor = t.floor ? t.floor + "층" : "-";
      const dealType = escapeHtml(t.deal_type || "-");
      dealHtml = `
        <div style="margin-top:2px; line-height:1.7;">
          <div><b style="color:#B4863F;">${price}만원</b> · ${escapeHtml(t.deal_date || "")}</div>
          <div>${floor} · 전용 ${area} · ${dealType}</div>
        </div>`;
    }
  } catch(e){
    dealHtml = `<div style="color:#B3453A;">실거래 조회 오류</div>`;
  }

  const content = `
    <div style="padding:10px 12px; min-width:170px; max-width:240px; font-size:12.5px; color:#16202E; font-family:'Noto Sans KR',sans-serif;">
      <div style="font-weight:700; font-size:13.5px; margin-bottom:2px;">${name}</div>
      <div style="color:#6b7683; margin-bottom:4px;">${typeKo}</div>
      ${dealHtml}
    </div>`;
  currentInfoWindow = new kakao.maps.InfoWindow({ position: pos, content, removable: true });
  currentInfoWindow.open(kakaoMap);
}

// SDK를 autoload=false로 불렀으므로 명시적으로 로드한 뒤 초기화한다.
if (window.kakao && window.kakao.maps){
  kakao.maps.load(initMap);
} else {
  console.warn("[MAP] 카카오맵 SDK가 로드되지 않았습니다 — appkey/도메인 등록 상태를 확인하세요.");
}
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
