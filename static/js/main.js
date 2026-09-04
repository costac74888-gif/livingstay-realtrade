const FAV_KEY = "livingstay_favorites"; // 마이그레이션 호환용 — 직접 쓰기는 하지 않음
// 관리자 모드: URL에 ?admin=1 을 붙이면 50개까지, 아니면 일반 사용자 5개 제한
const IS_ADMIN = new URLSearchParams(location.search).get("admin") === "1";
const MAX_FAVORITES = IS_ADMIN ? 50 : 30;

let regionTree = {};
let state = { si_do:"", sgg_nm:"", umd_nm:"", q:"", year:"all", lodging_type:"", page:1, size:20, favOnly:false, favKey:null };
let defaultYear = "";

// 로그인 회원의 관심키(building_name|address) 인메모리 캐시
// 비로그인 → 항상 빈 Set → 관심 기능 전체가 로그인 유도로 동작
let serverFavKeys = new Set();
let serverFavBuildingIds = new Map();

function getFavorites(){ return [...serverFavKeys]; }
function favKey(item){ return `${item.building_name}|${item.address}`; }
function isFav(item){ return serverFavKeys.has(favKey(item)); }
function addFavoriteFirst(key){
  serverFavKeys = new Set([key, ...serverFavKeys]);
}

// 관심저장 실패로 낙관적 상태를 되돌릴 때, 열려 있는 건물상세 버튼과 게시판 별도 함께 맞춘다.
function syncFavBtn(){
  if (typeof window.__syncOpenFavBtn === "function") window.__syncOpenFavBtn();
  const board = document.getElementById("board");
  if (!board) return;
  board.querySelectorAll(".col-star").forEach(function(td){
    const row = td.parentElement;
    const idx = [...row.parentElement.children].indexOf(row);
    const item = lastItems[idx];
    if (!item) return;
    const on = isFav(item);
    td.classList.toggle("on", on);
    td.innerHTML = Icons.heart(16, on);
  });
}

// 서버 /api/favorites/mine 에서 내 관심키 전체를 로드해 인메모리 캐시를 채운다.
async function loadServerFavKeys(){
  serverFavKeys = new Set();
  serverFavBuildingIds = new Map();
  if (!window.__livingstayLoggedIn) return;
  try {
    const res = await fetch("/api/favorites/mine", { credentials: "same-origin" });
    const data = await res.json();
    (data.items || []).forEach(item => {
      const key = `${item.building_name}|${item.address}`;
      serverFavKeys.add(key);
      const buildingId = Number(item.building_id ?? item.master_building_id);
      if (Number.isInteger(buildingId) && buildingId > 0) {
        serverFavBuildingIds.set(key, buildingId);
      }
    });
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
    promptLogin("로그인하고 관심단지를 저장하면, 새 실거래가 등록될 때 알림을 보내드려요");
    return false;
  }
  const k = favKey(item);
  let clearedActiveFilter = false;
  const wasFav = serverFavKeys.has(k);
  const previousFavOrder = [...serverFavKeys];
  const previousFavBuildingIds = new Map(serverFavBuildingIds);
  const restoreActiveFilter = wasFav && state.favKey === k;
  if (wasFav){
    serverFavKeys.delete(k);
    serverFavBuildingIds.delete(k);
    if (state.favKey === k){ state.favKey = null; state.favOnly = false; clearedActiveFilter = true; }
    fetch("/api/favorites/mine", {
      method: "DELETE", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ building_name: item.building_name, address: item.address })
    })
    .then(function(r){
      if (!r.ok) throw new Error("save-failed");
      return r.json().catch(function(){ return {}; });
    })
    .then(function(result){
      if (!result.ok) throw new Error(result.message || "save-failed");
    })
    .catch(function(){
      // 저장 실패 — 낙관적으로 바꿔둔 로컬 상태 롤백
      if (wasFav) {
        serverFavKeys = new Set(previousFavOrder);
        serverFavBuildingIds = new Map(previousFavBuildingIds);
        if (restoreActiveFilter) {
          state.favKey = k;
          state.favOnly = true;
          const chkFavOnly = document.getElementById("chkFavOnly");
          if (chkFavOnly) chkFavOnly.checked = true;
        }
      } else {
        serverFavKeys.delete(k);
      }
      updateFavCountLabel();
      renderFavChips();
      syncFavBtn();
      if (restoreActiveFilter) loadBoard();
      alert("관심단지 저장에 실패했습니다. 잠시 후 다시 시도해주세요.");
    });
  } else {
    if (serverFavKeys.size >= MAX_FAVORITES){
      alert(`관심단지는 최대 ${MAX_FAVORITES}개까지 저장할 수 있습니다.`);
      return false;
    }
    addFavoriteFirst(k);
    const buildingId = Number(item.building_id);
    if (Number.isInteger(buildingId) && buildingId > 0) {
      serverFavBuildingIds.set(k, buildingId);
    }
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
    })
    .then(function(r){
      if (!r.ok) throw new Error("save-failed");
      return r.json().catch(function(){ return {}; });
    })
    .then(function(result){
      if (!result.ok) throw new Error(result.message || "save-failed");
      if (result.duplicate) {
        // 같은 건물이 다른 관심키로 이미 저장돼 있으면 낙관적으로 추가한
        // 새 키를 제거하고 기존 관심단지 한 건만 유지한다.
        serverFavKeys.delete(k);
        updateFavCountLabel();
        renderFavChips();
        syncFavBtn();
      }
    })
    .catch(function(){
      // 저장 실패 — 낙관적으로 바꿔둔 로컬 상태 롤백
      if (wasFav) { serverFavKeys.add(k); }
      else {
        serverFavKeys.delete(k);
        serverFavBuildingIds.delete(k);
      }
      updateFavCountLabel();
      renderFavChips();
      syncFavBtn();
      alert("관심단지 저장에 실패했습니다. 잠시 후 다시 시도해주세요.");
    });
  }
  updateFavCountLabel();
  renderFavChips();
  if (clearedActiveFilter){ document.getElementById("chkFavOnly").checked = false; loadBoard(); }
  return true;
}
function removeFav(key){
  serverFavKeys.delete(key);
  serverFavBuildingIds.delete(key);
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
  loadBoard();
}
// auth.js가 로그인/migrate 후 호출 → 서버에서 관심키 재로드 후 UI 갱신
window.refreshFavoritesUI = async function(){
  await loadServerFavKeys();
  if (typeof updateFavCountLabel === "function") updateFavCountLabel();
  if (typeof renderFavChips === "function") renderFavChips();
};
// livingstay:auth 이벤트 — 이미 로그인된 상태로 페이지에 진입할 때도 관심키를 로드한다.
// auth.js가 window.dispatchEvent()로 발생시키므로 리스너도 window에 등록해야 함.
// (document.addEventListener는 window 이벤트를 수신하지 못함 — 타깃 불일치 버그 수정)
window.addEventListener("livingstay:auth", async function(){
  await loadServerFavKeys();
  if (typeof updateFavCountLabel === "function") updateFavCountLabel();
  if (typeof renderFavChips === "function") renderFavChips();
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

// 채팅방 열기 — listing_request_id로 방 생성 후 채팅 모달 오픈
function _openListingChat(listingRequestId){
  return window.LivingstayChat.startListingChat(listingRequestId, openChatModal);
}

// 인앱 채팅 모달 — room_id로 메시지 조회·전송
function openChatModal(roomId){
  document.getElementById("chatModalOverlay")?.remove();
  const ov = document.createElement("div");
  ov.id = "chatModalOverlay";
  ov.style.cssText = "position:fixed; inset:0; background:rgba(22,32,46,.45); z-index:4000; display:flex; align-items:flex-end; justify-content:center;";

  ov.innerHTML = `
    <div id="chatModalBox" style="width:100%; max-width:520px; background:#fff; border-radius:16px 16px 0 0; display:flex; flex-direction:column; max-height:80vh; box-shadow:0 -4px 24px rgba(0,0,0,.18);">
      <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 18px 12px; border-bottom:1px solid var(--line); flex-shrink:0;">
        <span style="font-size:15px; font-weight:700; color:var(--ink); display:inline-flex; align-items:center; gap:5px;">${Icons.messageCircle(17)}<span id="chatOpponentName">상대방</span></span>
        <button id="chatModalClose" style="background:none; border:none; font-size:22px; color:var(--ink-soft); cursor:pointer; line-height:1; padding:0 4px;">×</button>
      </div>
      <div id="chatMsgList" style="flex:1; overflow-y:auto; padding:14px 16px; display:flex; flex-direction:column; gap:8px;">
        <div style="text-align:center; color:var(--ink-soft); font-size:13px;">불러오는 중…</div>
      </div>
       <div id="chatSafetyNotice" role="status" style="display:none; margin:0 16px 8px; padding:9px 10px; border-radius:8px; background:#FFF7E6; border:1px solid #FFD898; color:#7D4A00; font-size:11.5px; line-height:1.55;"></div>
      <div id="chatAttachPreview" style="display:none; padding:6px 14px; background:#fafafa; border-top:1px solid var(--line); font-size:12px; color:var(--ink-soft); display:flex; align-items:center; gap:6px;"></div>
      <div id="chatTemplateChips" style="display:none; flex-direction:column; align-items:flex-start; gap:6px; padding:0 16px 8px;"></div>
      <div style="padding:10px 12px; border-top:1px solid var(--line); display:flex; gap:8px; flex-shrink:0; background:#fafafa;">
        <input type="file" id="chatFileInput" accept=".jpg,.jpeg,.png,.pdf" style="display:none;" />
        <button id="chatAttachBtn" title="파일 첨부" style="background:none; border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:17px; cursor:pointer; color:var(--ink-soft); line-height:1;">📎</button>
        <input id="chatInput" type="text" maxlength="500" placeholder="메시지를 입력하세요…" style="flex:1; border:1px solid var(--line); border-radius:8px; padding:9px 12px; font-size:14px; font-family:inherit; outline:none;" />
        <button id="chatSendBtn" style="background:var(--brass,#B4863F); color:#fff; border:none; border-radius:8px; padding:9px 18px; font-size:14px; font-weight:600; cursor:pointer; white-space:nowrap;">전송</button>
      </div>
    </div>`;

  document.body.appendChild(ov);

  let myUserId = null;
  let myRole = null;
  let pollTimer = null;
  let pendingAttachment = null; // { key, name }
  let messageLoadSequence = 0;

  const listEl      = ov.querySelector("#chatMsgList");
  const inputEl     = ov.querySelector("#chatInput");
  const sendBtn     = ov.querySelector("#chatSendBtn");
  const closeBtn    = ov.querySelector("#chatModalClose");
  const attachBtn   = ov.querySelector("#chatAttachBtn");
  const fileInputEl = ov.querySelector("#chatFileInput");
  const attachPrev  = ov.querySelector("#chatAttachPreview");
  const chipsEl     = ov.querySelector("#chatTemplateChips");
  const safetyEl    = ov.querySelector("#chatSafetyNotice");
  const _tplStorageKey = "chatUsedTpl_" + roomId;
  let usedTemplates = new Set();
  try {
    const storedTemplates = JSON.parse(localStorage.getItem(_tplStorageKey) || "[]");
    if (Array.isArray(storedTemplates)) usedTemplates = new Set(storedTemplates);
  } catch(e) {}

  function _refreshChipVisibility() {
    chipsEl.querySelectorAll(".chat-template-chip").forEach((btn) => {
      const tpl = btn.getAttribute("data-tpl");
      btn.style.display = usedTemplates.has(tpl) ? "none" : "inline-flex";
    });
    chipsEl.style.display = chipsEl.querySelector(".chat-template-chip:not([style*='display: none'])")
      ? "flex" : "none";
  }

  function _renderTemplateChips() {
    if (myRole !== "buyer" && myRole !== "seller") {
      chipsEl.innerHTML = "";
      chipsEl.style.display = "none";
      return;
    }
    const templates = window.LivingstayChat.getRoleQuickReplies(myRole);
    const roleClass = myRole === "seller" ? "seller" : "buyer";
    chipsEl.innerHTML = templates.map((tpl) =>
      `<button class="chat-template-chip ${roleClass}" data-tpl="${escapeHtml(tpl)}">${escapeHtml(tpl)}</button>`
    ).join("");
    _refreshChipVisibility();
  }

  // 칩 클릭 → 입력창 채우기 (자동전송 아님)
  chipsEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-template-chip");
    if (!btn) return;
    window.LivingstayChat.fillQuickReply(inputEl, btn.getAttribute("data-tpl"));
  });

  function _fmtChatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      const today = new Date();
      const sameDay = d.getFullYear() === today.getFullYear() &&
                      d.getMonth()    === today.getMonth()    &&
                      d.getDate()     === today.getDate();
      const hhmm = d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
      if (sameDay) return hhmm;
      const yyyy = d.getFullYear(), mm = String(d.getMonth()+1).padStart(2,"0"), dd = String(d.getDate()).padStart(2,"0");
      return `${yyyy}-${mm}-${dd} ${hhmm}`;
    } catch(e) { return isoStr; }
  }

  function _renderMessages(messages){
    if (!messages.length){
      listEl.innerHTML = `<div style="text-align:center; color:var(--ink-soft); font-size:13px; padding:24px 0;">아직 메시지가 없습니다. 먼저 인사를 건네보세요!</div>`;
      return;
    }
    const wasAtBottom = listEl.scrollHeight - listEl.scrollTop <= listEl.clientHeight + 40;
    listEl.innerHTML = messages.map(m => {
      const isMine = String(m.sender_user_id) === String(myUserId);
      const bg    = isMine ? "var(--brass,#B4863F)" : "#f0f0f0";
      const clr   = isMine ? "#fff" : "var(--ink)";
      const align = isMine ? "flex-end" : "flex-start";
      const br    = isMine ? "14px 14px 4px 14px" : "14px 14px 14px 4px";
      let contentHtml = "";
      if (m.body) {
        contentHtml += `<div style="background:${bg}; color:${clr}; border-radius:${br}; padding:8px 12px; max-width:75%; font-size:14px; line-height:1.5; word-break:break-word;">${escapeHtml(m.body)}</div>`;
      }
      if (m.attachment_key) {
        const ext = m.attachment_key.split(".").pop().toLowerCase();
        const url = `/api/chat/attachments/${m.attachment_key}`;
        if (["jpg","jpeg","png"].includes(ext)) {
          contentHtml += `<a href="${url}" target="_blank" rel="noopener" style="display:block; max-width:75%;"><img src="${url}" style="max-width:100%; max-height:200px; border-radius:8px; display:block; margin-top:${m.body ? "4px" : "0"};" /></a>`;
        } else {
          contentHtml += `<a href="${url}" target="_blank" rel="noopener" style="background:${bg}; color:${clr}; border-radius:${br}; padding:8px 12px; max-width:75%; font-size:13px; display:inline-block; text-decoration:none; margin-top:${m.body ? "4px" : "0"};">📎 ${escapeHtml(m.attachment_name || "첨부파일")}</a>`;
        }
      }
      return `<div style="display:flex; flex-direction:column; align-items:${align}; gap:2px;">
        ${!isMine ? `<span style="font-size:11px; color:var(--ink-soft);">${escapeHtml(m.sender_name || "")}</span>` : ""}
        ${contentHtml}
        <span style="font-size:10.5px; color:var(--ink-soft);">${_fmtChatTime(m.sent_at)}</span>
      </div>`;
    }).join("");
    if (wasAtBottom) listEl.scrollTop = listEl.scrollHeight;
  }

  async function _loadMessages(){
    const loadSequence = ++messageLoadSequence;
    try {
      const res = await fetch(`/api/chat/rooms/${roomId}/messages`, { credentials: "same-origin" });
      if (!res.ok) return;
      const d = await res.json().catch(() => ({}));
      // 먼저 시작된 느린 요청이 최신 응답을 덮어써 빈 방 UI를 다시 보이지 않게 한다.
      if (!d.ok || loadSequence !== messageLoadSequence) return;
      myUserId = d.my_user_id;
      if (d.my_role && d.my_role !== myRole) {
        myRole = d.my_role;
        _renderTemplateChips();
      }
      const opponentNameEl = ov.querySelector("#chatOpponentName");
      if (opponentNameEl) opponentNameEl.textContent = d.opponent_name || "상대방";
      const messages = d.messages || [];
      _renderMessages(messages);
    } catch(e){ /* 조용히 실패 — 폴링이 재시도 */ }
  }

  async function _uploadFile(file){
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/chat/rooms/${roomId}/attachments`, {
      method: "POST", credentials: "same-origin", body: fd,
    });
    const d = await res.json().catch(() => ({}));
    if (!d.ok) throw new Error(d.message || "업로드 실패");
    return { key: d.key, name: d.name };
  }

  async function _send(){
    const body = inputEl.value.trim();
    const att  = pendingAttachment;
    if (!body && !att) return;
    const sentText = body; // 전송 직전 텍스트 보존 (칩 매칭용)
    inputEl.value = "";
    pendingAttachment = null;
    attachPrev.style.display = "none";
    attachPrev.innerHTML = "";
    sendBtn.disabled = true;
    try {
      const payload = { body };
      if (att) { payload.attachment_key = att.key; payload.attachment_name = att.name; }
      const res = await fetch(`/api/chat/rooms/${roomId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const matchedChip = Array.from(chipsEl.querySelectorAll(".chat-template-chip"))
          .find((b) => b.getAttribute("data-tpl") === sentText);
        if (matchedChip) {
          usedTemplates.add(sentText);
          localStorage.setItem(_tplStorageKey, JSON.stringify([...usedTemplates]));
          _refreshChipVisibility();
        }
        window.LivingstayChat.showSafetyNoticeForMessage(sentText, safetyEl);
        await _loadMessages();
      }
      else {
        const d = await res.json().catch(() => ({}));
        inputEl.value = body;
        if (att) { pendingAttachment = att; attachPrev.style.display = "flex"; attachPrev.innerHTML = `📎 ${escapeHtml(att.name)}`; }
        alert(d.message || "전송에 실패했습니다.");
      }
    } catch(e){
      inputEl.value = body;
      if (att) pendingAttachment = att;
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // 파일 첨부 버튼
  attachBtn.addEventListener("click", () => fileInputEl.click());
  fileInputEl.addEventListener("change", async () => {
    const file = fileInputEl.files[0];
    if (!file) return;
    fileInputEl.value = "";
    attachPrev.style.display = "flex";
    attachPrev.innerHTML = `<span>📎 ${escapeHtml(file.name)} 업로드 중…</span>`;
    try {
      const att = await _uploadFile(file);
      pendingAttachment = att;
      attachPrev.innerHTML = `<span>📎 ${escapeHtml(att.name)}</span><button id="chatAttachRm" style="margin-left:6px;background:none;border:none;cursor:pointer;color:#c00;font-size:14px;padding:0;">✕</button>`;
      document.getElementById("chatAttachRm")?.addEventListener("click", () => {
        pendingAttachment = null;
        attachPrev.style.display = "none";
        attachPrev.innerHTML = "";
      });
    } catch(e) {
      pendingAttachment = null;
      attachPrev.style.display = "none";
      attachPrev.innerHTML = "";
      alert(e.message || "파일 업로드에 실패했습니다.");
    }
  });

  const _close = () => {
    clearInterval(pollTimer);
    ov.remove();
  };

  closeBtn.addEventListener("click", _close);
  ov.addEventListener("click", (e) => { if (e.target === ov) _close(); });
  sendBtn.addEventListener("click", _send);
  inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey){ e.preventDefault(); _send(); } });

  // 초기 로드 + 5초 폴링
  _loadMessages();
  pollTimer = setInterval(_loadMessages, 5000);
  setTimeout(() => inputEl.focus(), 100);
}

// header.js에서 알림 드롭다운 채팅 항목 클릭 시 사용
window.openChatModal = openChatModal;

let _fallbackToastTimer = null;
function showFallbackToast(msg){
  const wrap = document.getElementById("fallbackToast");
  if (!wrap) return;
  // 이전 타이머 취소 후 새 메시지로 갱신
  if (_fallbackToastTimer) { clearTimeout(_fallbackToastTimer); _fallbackToastTimer = null; }
  wrap.innerHTML = `<div class="fallback-toast-inner">${escapeHtml(msg)}</div>`;
  wrap.style.display = "block";
  const inner = wrap.querySelector(".fallback-toast-inner");
  // 2.8초 후 페이드아웃, 0.4초 뒤 숨김
  _fallbackToastTimer = setTimeout(function(){
    if (inner) inner.classList.add("fading");
    _fallbackToastTimer = setTimeout(function(){
      wrap.style.display = "none";
      wrap.innerHTML = "";
      _fallbackToastTimer = null;
    }, 420);
  }, 2800);
}

function showMapEmptyBanner(msg = "이 지역은 아직 등록된 매물이 없어요"){
  const emptyEl = document.getElementById("mapEmpty");
  if (!emptyEl) return;
  emptyEl.textContent = msg;
  emptyEl.style.display = "flex";
}

let _favOverflowPopover = null;
let _favOverflowPopoverButton = null;
function closeFavOverflowPopover(){
  if (_favOverflowPopoverButton) {
    _favOverflowPopoverButton.setAttribute("aria-expanded", "false");
    _favOverflowPopoverButton = null;
  }
  if (_favOverflowPopover) {
    _favOverflowPopover.remove();
    _favOverflowPopover = null;
  }
}
function createFavChip(key){
  const chip = document.createElement("span");
  chip.className = "fav-chip" + (state.favKey === key ? " active" : "");
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = "★ " + key.split("|")[0];
  label.title = "건물 상세 보기";
  label.addEventListener("click", async () => {
    // 팝오버 안에서 상세로 이동해도 팝오버가 상세 패널 위에 잔류하지 않게 한다.
    closeFavOverflowPopover();
    const knownBuildingId = serverFavBuildingIds.get(key);
    if (knownBuildingId) {
      openBuildingDetail(knownBuildingId);
      return;
    }
    try {
      const res = await fetch(`/api/favorites?keys=${encodeURIComponent(key)}`);
      const data = await res.json();
      const item = (data.items || [])[0];
      if (item && item.master_building_id) {
        openBuildingDetail(item.master_building_id);
        return;
      }
      // 기존 관심단지 중 master_building_id가 비어 있는 행은 건물명으로
      // 현재 마스터를 다시 찾되, 저장 주소까지 맞는 유일한 후보만 상세를 연다.
      if (item && item.building_name) {
        try {
          const sep = key.indexOf("|");
          const address = sep >= 0 ? key.slice(sep + 1) : "";
          const sr = await fetch(
            `/api/buildings/search?q=${encodeURIComponent(item.building_name)}` +
            `&address=${encodeURIComponent(address)}`
          );
          const sd = await sr.json();
          const found = sd.items || sd.buildings || [];
          if (found.length === 1 && found[0].id) {
            openBuildingDetail(found[0].id);
            return;
          }
        } catch(e){ /* fall through */ }
      }
    } catch(e){ /* fall through */ }
    filterToFav(key);
  });
  chip.appendChild(label);
  const x = document.createElement("span");
  x.className = "x";
  x.textContent = "✕";
  x.addEventListener("click", (e) => { e.stopPropagation(); removeFav(key); });
  chip.appendChild(x);
  return chip;
}
function openFavOverflowPopover(button, hiddenKeys){
  closeFavOverflowPopover();
  const popover = document.createElement("div");
  popover.className = "fav-overflow-popover";
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-label", "전체 관심단지");
  hiddenKeys.forEach(key => popover.appendChild(createFavChip(key)));
  document.body.appendChild(popover);
  _favOverflowPopover = popover;
  _favOverflowPopoverButton = button;
  const rect = button.getBoundingClientRect();
  const width = Math.min(430, window.innerWidth - 24);
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
  popover.style.left = left + "px";
  popover.style.top = Math.min(rect.bottom + 6, window.innerHeight - popover.offsetHeight - 12) + "px";
  button.setAttribute("aria-expanded", "true");
}
function renderFavChips(){
  const wrap = document.getElementById("favChips");
  const favs = getFavorites();
  if (!wrap) return;
  closeFavOverflowPopover();
  wrap.innerHTML = "";
  const visibleKeys = favs.slice(0, 3);
  const hiddenKeys = favs.slice(3);
  visibleKeys.forEach(k => wrap.appendChild(createFavChip(k)));
  if (hiddenKeys.length) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "fav-more-btn";
    more.textContent = `+더보기(${hiddenKeys.length})`;
    more.setAttribute("aria-expanded", "false");
    more.addEventListener("click", () => {
      if (_favOverflowPopover) {
        closeFavOverflowPopover();
        more.setAttribute("aria-expanded", "false");
      } else {
        openFavOverflowPopover(more, hiddenKeys);
      }
    });
    wrap.appendChild(more);
  }
}
document.addEventListener("click", (e) => {
  if (_favOverflowPopover && !e.target.closest(".fav-overflow-popover, .fav-more-btn")) closeFavOverflowPopover();
});

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

function closeMapSearchbar(){
  const searchbar = document.querySelector(".map-searchbar");
  if (!searchbar) return;
  searchbar.classList.add("collapsed");
  const toggle = document.getElementById("btnToggleSearch");
  if (!toggle) return;
  const icon = toggle.querySelector("#searchToggleIcon");
  const label = toggle.querySelector("span:last-child");
  if (icon && window.Icons) icon.innerHTML = Icons.search(15);
  if (label) label.textContent = "검색";
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
  const lodgingLabel = window.LodgingTypes.badge(t.lodging_type, t.lodging_subtype);
  const lodgingColor = window.LodgingTypes.color(t.lodging_type);
  const lodgingTag = `<span class="tag" style="cursor:pointer;background:${lodgingColor};color:#fff;"
      title="${(t.lodging_type_detail||'용도 미확인 — 건축물대장 재검증 필요').replace(/"/g,'&quot;')} (클릭하면 정정 요청)"
      onclick="openCorrectionModal(${idx})">${escapeHtml(lodgingLabel)} ✎</span>`;
  const priceFormatted = Number(t.price || 0).toLocaleString('ko-KR');
  return `
    <tr>
      <td class="col-star ${fav?'on':''}" onclick="handleStarClick(this)">${Icons.heart(16, fav)}</td>
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
  td.innerHTML = Icons.heart(16, td.classList.contains("on"));
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
document.getElementById("btnSearch").addEventListener("click", async ()=>{
  state.q = document.getElementById("inputQ").value.trim();
  state.page = 1;
  loadBoard();
  // 검색 후 검색바를 닫아 지도가 보이게 한다 (모바일에서 검색바가 화면을 덮는 문제 해결)
  const _sb = document.querySelector(".map-searchbar");
  const _sbt = document.getElementById("btnToggleSearch");
  if (_sb && !_sb.classList.contains("collapsed")){
    _sb.classList.add("collapsed");
    if (_sbt) {
      const icon = _sbt.querySelector("#searchToggleIcon");
      const label = _sbt.querySelector("span:last-child");
      if (icon) icon.innerHTML = Icons.search(15);
      if (label) label.textContent = "검색";
    }
  }
  // q(건물명·주소) 또는 지역 필터(si_do/sgg_nm/umd_nm)가 있으면 fit:true로 지도를 해당 지역으로 이동
  const hasFit = !!(state.q || state.si_do || state.sgg_nm || state.umd_nm);

  // 텍스트 검색어 없이 지역 드롭다운만 선택한 경우:
  // fit 옵션이 markers 모드에서만 동작하므로, 선택된 필터 구체성에 맞는
  // 줌 레벨로 지도를 강제 이동시킨 뒤 해당 레벨의 클러스터를 재조회한다.
  // 이렇게 해야 "주교동까지 선택 → 배지가 주교동 단위로 표시"가 동작함.
  //
  // 폴백: 선택한 레벨(umd)에 건물이 없으면 sgg → sido 순으로 한 단계씩 올라가
  // 인근 배지를 보여준다. 모두 없으면 loadClusterOverlays 가 mapEmpty를 표시한다.
  //
  // 중요: 폴백 성공 시 지도 갱신은 실제로 결과가 있는 레벨의 필터로 호출해야 한다.
  // mapFiltersFromState()를 그대로 쓰면 원래 umd_nm이 살아있어 배지가 다시 사라진다.
  let _effectiveMapFilters = mapFiltersFromState(); // 기본: 사용자 선택 그대로
  if (!state.q && hasFit && kakaoMap){
    try {
      // 선택 단계에 따라 시도할 레벨 목록을 가장 구체적인 것부터 준비한다.
      const _lodging = state.lodging_type || "";
      const _fallbacks = [];
      if (state.umd_nm){
        _fallbacks.push({ name: "umd", level: CLUSTER_UMD_MIN_LEVEL,
          filters: { si_do: state.si_do, sgg_nm: state.sgg_nm, umd_nm: state.umd_nm, lodging_type: _lodging } });
      }
      if (state.sgg_nm){
        _fallbacks.push({ name: "sgg", level: CLUSTER_SGG_MIN_LEVEL,
          filters: { si_do: state.si_do, sgg_nm: state.sgg_nm, lodging_type: _lodging } });
      }
      if (state.si_do){
        _fallbacks.push({ name: "sido", level: CLUSTER_SIDO_MIN_LEVEL,
          filters: { si_do: state.si_do, lodging_type: _lodging } });
      }

      for (let _fbi = 0; _fbi < _fallbacks.length; _fbi++){
        const fb = _fallbacks[_fbi];
        const _p = new URLSearchParams({ level: fb.name });
        Object.entries(fb.filters).forEach(([k, v]) => { if (v) _p.set(k, v); });
        const _r = await fetch(`/api/buildings-cluster?${_p}`);
        const _d = await _r.json();
        const _items = _d.items || [];
        if (_items.length > 0){
          // 단일 결과면 그 좌표로, 여럿이면 평균 중심으로 이동
          const _cLat = _items.reduce((s, i) => s + i.lat, 0) / _items.length;
          const _cLng = _items.reduce((s, i) => s + i.lng, 0) / _items.length;
          // setLevel 이 zoom_changed 이벤트를 즉시 발생시키고,
          // 핸들러가 _lastMapFilters 로 클러스터를 재조회하므로
          // setCenter/setLevel 호출 전에 미리 올바른 필터로 갱신해둔다.
          _lastMapFilters = fb.filters;
          _effectiveMapFilters = fb.filters;
          kakaoMap.setCenter(new kakao.maps.LatLng(_cLat, _cLng));
          kakaoMap.setLevel(fb.level);
          // 폴백이 실제로 발생한 경우(처음 선택한 레벨에 건물 없음) 사용자에게 안내.
          // 메시지는 실제로 결과가 발견된 레벨(fb.name)을 기준으로 결정한다.
          if (_fbi > 0){
            const _orig = _fallbacks[0].name; // 사용자가 처음 선택한 레벨
            const _resolved = fb.name;        // 실제로 건물이 있는 레벨
            let _toastMsg;
            if (_resolved === "sgg"){
              _toastMsg = "선택한 읍면동에 등록 건물이 없어 시군구 단위로 인근 배지를 표시합니다";
            } else if (_resolved === "sido"){
              if (_orig === "umd"){
                _toastMsg = "선택한 읍면동·시군구에 등록 건물이 없어 시/도 단위로 표시합니다";
              } else {
                _toastMsg = "이 시군구에 등록 건물이 없어 시/도 단위로 표시합니다";
              }
            }
            if (_toastMsg) showFallbackToast(_toastMsg);
          }
          break; // 첫 번째 결과가 있는 레벨에서 중단
        }
        // 해당 레벨에 건물 없음 → 다음 상위 레벨로 폴백
      }
    } catch(e){ console.warn("[SEARCH] 지역 중심 좌표 조회 실패:", e); }
  }

  updateMapForZoom(_effectiveMapFilters, { force: true, fit: hasFit });
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
  localStorage.removeItem("map_last_view"); // 검색 초기화는 저장된 지도 위치도 초기화
  updateMapForZoom({}, { force: true });   // 지도도 전체로 복귀 (줌 레벨 기준 클러스터 또는 마커)
  window.scrollTo({top:0, behavior:"smooth"});
}

const MAP_LAST_VIEW_KEY = "map_last_view";
const MAP_PREVIOUS_VIEW_KEY = "map_previous_view";

function readStoredMapView(key){
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null");
    if (saved && Number.isFinite(Number(saved.lat)) && Number.isFinite(Number(saved.lng))
        && Number.isFinite(Number(saved.level))) {
      return {
        lat: Number(saved.lat),
        lng: Number(saved.lng),
        level: Number(saved.level),
        savedAt: Number(saved.savedAt) || Date.now(),
      };
    }
  } catch(e) {}
  return null;
}

function rememberCurrentMapView(){
  let view = null;
  if (kakaoMap && kakaoMap.getCenter){
    const center = kakaoMap.getCenter();
    view = {
      lat: center.getLat(),
      lng: center.getLng(),
      level: kakaoMap.getLevel(),
      savedAt: Date.now(),
    };
  } else {
    view = readStoredMapView(MAP_LAST_VIEW_KEY);
  }
  if (view){
    try { localStorage.setItem(MAP_PREVIOUS_VIEW_KEY, JSON.stringify(view)); } catch(e) {}
  }
}

// 로고 마크는 현재 화면을 직전 지도 슬롯에 보관한 뒤, 필터·상세 상태까지
// 버리고 "/"를 다시 읽어 전국 초기지도로 시작한다.
function resetToNationwide(){
  rememberCurrentMapView();
  try { localStorage.removeItem(MAP_LAST_VIEW_KEY); } catch(e) {}
  window.location.replace("/");
}

// 상호를 누르면 로고를 누르기 직전의 중심·줌으로 전체 지도 화면을 다시 연다.
function restorePreviousMap(){
  const previous = readStoredMapView(MAP_PREVIOUS_VIEW_KEY);
  if (!previous) return;
  previous.savedAt = Date.now();
  try { localStorage.setItem(MAP_LAST_VIEW_KEY, JSON.stringify(previous)); } catch(e) {}
  window.location.replace("/");
}

function bindKeyboardClick(element, handler){
  if (!element) return;
  element.addEventListener("click", handler);
  element.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " "){
      event.preventDefault();
      handler(event);
    }
  });
}

bindKeyboardClick(document.getElementById("brandHomeLogo"), resetToNationwide);
bindKeyboardClick(document.getElementById("brandPreviousMap"), restorePreviousMap);
document.getElementById("btnResetSearch").addEventListener("click", resetToHome);
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

  // 이메일 등 외부 링크의 ?q=건물명 파라미터 — 홈에서 자동 검색 실행
  const initialQ = urlParams.get("q");
  if (initialQ) {
    const inp = document.getElementById("inputQ");
    if (inp) inp.value = initialQ;
    state.q = initialQ;
  }

  loadBoard();
})();

// ---------- 검색패널 터치 스크롤 보호 ----------
// 카카오맵 SDK가 지도 컨테이너에 touchmove preventDefault를 등록해 패널 위에서
// 손가락 스크롤이 안 되는 문제 방지. capture:true로 지도 쪽 핸들러보다 먼저 잡아
// 패널 안에서의 수직 드래그 이벤트가 지도로 전파되지 않도록 차단한다.
(function(){
  const _sb = document.querySelector(".map-searchbar");
  if (!_sb) return;
  function _blockMapTouch(e){ e.stopPropagation(); }
  _sb.addEventListener("touchstart", _blockMapTouch, { passive: true, capture: true });
  _sb.addEventListener("touchmove",  _blockMapTouch, { passive: true, capture: true });
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
  const suggested_lodging_type = document.getElementById("correctionSuggestedType").value;
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
const LODGING_COLORS = window.LodgingTypes.colors;
const LODGING_LABELS = window.LodgingTypes.labels;
const DEFAULT_MARKER_COLOR = "#9AA5B1";

function markerColor(lodgingType, buildingStatus){
  return window.LodgingTypes.color(lodgingType, buildingStatus);
}
// DEFAULT_MARKER_COLOR(회색)는 이제 "준공전" 배지 전용으로만 남겨둠
// (headerCard의 isPreCompletion 분기에서 이미 "#9AA5B1"로 별도 하드코딩해서
// 쓰고 있으므로 이 변경과 충돌 없음)
function lodgingLabelKo(lodgingType, buildingStatus){
  return window.LodgingTypes.label(lodgingType, buildingStatus);
}

let kakaoMap = null;
let currentInfoWindow = null;
let mapOverlays = [];                 // 현재 지도에 찍힌 마커(kakao.maps.Marker) 목록
let mapLabelData = [];                // [{b, pos, overlay, el}] — 원형 배지 lazy 생성용 데이터
let _mapRenderGen = 0;                // 마커·클러스터 공용 세대 — 늦게 도착한 이전 응답 폐기용
let _mapFetchController = null;       // 다음 지도 요청이 이전 네트워크 요청을 취소한다.
let selectedDataLabBuilding = null;   // 데이터랩에서 마지막으로 선택한 건물
let selectedDataLabOverlay = null;    // 선택 건물 전용 CustomOverlay — 레이어 교체와 분리
let mapLocationTargetId = null;       // 지도위치 버튼으로 선택된 건물 원형의 지속 강조 대상

function clearMapLocationTarget(){
  mapLocationTargetId = null;
  document.querySelectorAll(".map-location-target").forEach(el => {
    el.classList.remove("map-location-target");
  });
}

function syncMapLocationTargetElement(el, buildingId){
  if (!el || buildingId == null) return;
  const id = String(buildingId);
  el.dataset.mapBuildingId = id;
  el.classList.toggle(
    "map-location-target",
    mapLocationTargetId != null && String(mapLocationTargetId) === id
  );
}

function applyMapLocationTarget(){
  const targetId = mapLocationTargetId == null ? null : String(mapLocationTargetId);
  document.querySelectorAll(".map-location-target").forEach(el => {
    if (targetId == null || el.dataset.mapBuildingId !== targetId) {
      el.classList.remove("map-location-target");
    }
  });
  if (targetId == null) return;

  mapOverlays.forEach(overlay => {
    if (String(overlay.__buildingId) !== targetId || !overlay.__contentEl) return;
    syncMapLocationTargetElement(overlay.__contentEl, overlay.__buildingId);
  });
  mapLabelData.forEach(data => {
    if (String(data.b?.id) !== targetId || !data.el) return;
    syncMapLocationTargetElement(data.el, data.b.id);
  });
}

function setMapLocationTarget(buildingId){
  if (buildingId == null) return;
  mapLocationTargetId = String(buildingId);
  applyMapLocationTarget();
}

// 색상별 0건 점 마커 캐시 — SVG 데이터 URI를 반복 생성하지 않는다.
// 거래·매물 합계가 1건 이상인 건물은 CustomOverlay 원형 숫자 배지로 표시한다.
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

function _syncDataLabBuildingSelection(){
  const selectedId = selectedDataLabBuilding ? String(selectedDataLabBuilding.id) : null;
  document.querySelectorAll("[data-datalab-building]").forEach(button => {
    const selected = selectedId !== null && button.dataset.datalabBuilding === selectedId;
    button.classList.toggle("datalab-building-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function clearDataLabBuildingHighlight(){
  if (selectedDataLabOverlay){
    selectedDataLabOverlay.setMap(null);
    selectedDataLabOverlay = null;
  }
  selectedDataLabBuilding = null;
  _syncDataLabBuildingSelection();
}

function showDataLabBuildingHighlight(building){
  if (!kakaoMap || !building) return;
  const lat = Number(building.lat);
  const lng = Number(building.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  clearDataLabBuildingHighlight();
  selectedDataLabBuilding = {
    id: Number(building.id),
    name: building.name || "건물명 미확인",
    lat,
    lng,
  };

  const label = document.createElement("div");
  label.className = "datalab-map-highlight";
  label.setAttribute("role", "status");
  label.setAttribute("aria-live", "polite");
  label.setAttribute("aria-label", `선택한 건물: ${selectedDataLabBuilding.name}`);
  const dot = document.createElement("span");
  dot.className = "datalab-map-highlight-dot";
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.textContent = selectedDataLabBuilding.name;
  label.append(dot, text);

  const position = new kakao.maps.LatLng(lat, lng);
  selectedDataLabOverlay = new kakao.maps.CustomOverlay({
    position,
    content: label,
    xAnchor: 0.5,
    yAnchor: 1.0,
    zIndex: 40,
    clickable: false,
  });
  selectedDataLabOverlay.__contentEl = label;
  selectedDataLabOverlay.setMap(kakaoMap);
  _syncDataLabBuildingSelection();
}

function _openBuildingFromMap(b){
  if (b.id == null) return;
  clearMapLocationTarget();
  if (currentInfoWindow){ currentInfoWindow.close(); currentInfoWindow = null; }
  history.pushState({ buildingId: b.id }, "", "/building/" + b.id);
  if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/building/" + b.id });
  renderBuildingPanel(b.id);
}

// 거래·매물 합계가 있는 건물의 원형 숫자 배지.
// updateMarkerLabels에서 가까운 줌 레벨에 진입한 뒤 최초 1회만 생성한다.
function _buildCircleBadgeEl(b){
  const total = Math.max(0, Number(b.total_count) || 0);
  if (total < 1) return null;
  const color = markerColor(b.lodging_type, b.building_status);
  const badge = document.createElement("button");
  badge.type = "button";
  badge.title = `${b.building_name || "건물"} · 거래/매물 ${total.toLocaleString("ko-KR")}건`;
  badge.setAttribute("aria-label", badge.title);
  badge.textContent = total > 999 ? "999+" : total.toLocaleString("ko-KR");
  badge.style.cssText =
    `width:34px;height:34px;padding:0;border:2px solid #fff;border-radius:50%;background:${color};` +
    "color:#fff;display:flex;align-items:center;justify-content:center;box-sizing:border-box;" +
    "font-family:'Noto Sans KR',sans-serif;font-size:12px;font-weight:800;line-height:1;" +
    "text-shadow:0 1px 1px rgba(0,0,0,.22);box-shadow:0 2px 7px rgba(0,0,0,.28);" +
    "cursor:pointer;pointer-events:auto;transition:opacity .18s ease,transform .18s ease;";
  syncMapLocationTargetElement(badge, b.id);
  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    _openBuildingFromMap(b);
  });
  return badge;
}
const LABEL_MAX_LEVEL = 5;            // 이 확대 레벨 이하(더 가까이)일 때만 라벨 표시
// 클러스터 배지 줌 레벨 임계값 — Kakao Maps 레벨: 숫자 클수록 더 넓은 시야
// level ≥ CLUSTER_SIDO_MIN_LEVEL → 시도 집계 배지
// level CLUSTER_SGG_MIN_LEVEL ~ CLUSTER_SIDO_MIN_LEVEL-1 → 시군구 집계 배지
// level CLUSTER_UMD_MIN_LEVEL ~ CLUSTER_SGG_MIN_LEVEL-1 → 읍면동 집계 배지
// level ≤ LABEL_MAX_LEVEL → 기존 개별 마커
const CLUSTER_SIDO_MIN_LEVEL = 10;
const CLUSTER_SGG_MIN_LEVEL  = 8;
const CLUSTER_UMD_MIN_LEVEL  = 6;

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

// xAnchor:1(배지 오른쪽 끝이 좌표에 고정) → 배지가 좌표 왼쪽에 표시되는 시도 목록.
// 기본(xAnchor:0)은 배지 왼쪽 끝 고정(배지가 우측에 표시). 인접 배지 겹침 방지용.
const SIDO_ANCHOR_LEFT = new Set(["경상남도"]);

let _clusterOverlays = [];            // 클러스터 배지 CustomOverlay 목록
let _currentMapMode  = null;          // 'sido'|'sgg'|'umd'|'markers' — 불필요한 재로드 방지
let _lastMapFilters  = {};            // 마지막으로 적용된 지도 필터 (zoom 전환 시 재사용)
const MAP_OVERLAY_FADE_MS = 180;
let _pendingFadeOutOverlays = [];
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

// 지도 우측 도구 모음은 기존 건물 레이어와 별도의 수명주기를 갖는다.
// 줌/검색으로 건물 레이어가 교체되어도 로드뷰·측정·POI가 같이 사라지지
// 않도록 도구 전용 오버레이와 활성 상태를 분리해 관리한다.
const MAP_TYPE_STEPS = [
  { key: "roadmap", label: "일반", id: "ROADMAP" },
  { key: "skyview", label: "위성", id: "SKYVIEW" },
  { key: "hybrid", label: "혼합", id: "HYBRID" },
];
let _mapTypeIndex = 0;
let _activeMapTool = null; // null | roadview | measure | education | convenience
let _mapToolOverlays = [];
let _roadviewClient = null;
let _roadview = null;
let _roadviewMiniMap = null;
let _roadviewMiniMarker = null;
let _roadviewMiniCamera = null;
let _roadviewMiniMapResizeBound = false;
let _roadviewMiniMapResizeObserver = null;
let _measurePoints = [];
let _measureLine = null;
let _measureLabel = null;
let _measureFinished = false;
let _poiRequestSequence = 0;
let _roadviewRequestSequence = 0;

const POI_REFRESH_DEBOUNCE_MS = 180;
let _poiRefreshTimer = null;
let _poiFetchController = null;
let _poiPendingCenterKey = null;
let _poiScheduledCenterKey = null;
let _poiDisplayedCenterKey = null;

function _mapTypeId(key){
  return (window.kakao && kakao.maps && kakao.maps.MapTypeId)
    ? kakao.maps.MapTypeId[key] : null;
}

function _setMapToolButtonState(){
  const buttons = {
    roadview: document.getElementById("roadviewTool"),
    measure: document.getElementById("measureTool"),
    education: document.getElementById("educationTool"),
    convenience: document.getElementById("convenienceTool"),
  };
  Object.entries(buttons).forEach(([tool, button]) => {
    if (!button) return;
    const active = _activeMapTool === tool;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute("aria-label", active
      ? `${button.getAttribute("title") || tool} 끄기`
      : `${button.getAttribute("title") || tool} 켜기`);
  });
}

function _clearMapToolOverlays(){
  _mapToolOverlays.forEach(overlay => overlay.setMap(null));
  _mapToolOverlays = [];
}

function _closeRoadviewPanel(){
  const panel = document.getElementById("roadviewPanel");
  if (panel){
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
  }
}

function _roadviewMiniMapCenter(){
  return kakaoMap && kakaoMap.getCenter ? kakaoMap.getCenter() : null;
}

function _roadviewMiniMapResizeLimits(wrap){
  const panel = document.getElementById("roadviewPanel");
  const panelRect = panel && panel.getBoundingClientRect ? panel.getBoundingClientRect() : null;
  const panelWidth = Number(panelRect && panelRect.width) || Number(window.innerWidth) || 1280;
  const panelHeight = Number(panelRect && panelRect.height) || Number(window.innerHeight) || 720;
  let left = 16;
  let bottom = 50;
  if (typeof window.getComputedStyle === "function"){
    const computed = window.getComputedStyle(wrap);
    left = Number.parseFloat(computed.left) || left;
    bottom = Number.parseFloat(computed.bottom) || bottom;
  }
  return {
    minWidth: 140,
    minHeight: 96,
    // 미니맵 박스는 로드뷰와 나란히 볼 수 있도록 화면 절반까지만 확장한다.
    maxWidth: Math.max(140, panelWidth * 0.5 - left),
    maxHeight: Math.max(96, panelHeight - bottom - 8),
  };
}

function _resizeRoadviewMiniMap(width, height){
  const wrap = document.getElementById("roadviewMiniMapWrap");
  if (!wrap) return;
  const limits = _roadviewMiniMapResizeLimits(wrap);
  const nextWidth = Math.max(limits.minWidth, Math.min(limits.maxWidth, Number(width) || limits.minWidth));
  const nextHeight = Math.max(limits.minHeight, Math.min(limits.maxHeight, Number(height) || limits.minHeight));
  wrap.style.width = `${Math.round(nextWidth)}px`;
  wrap.style.height = `${Math.round(nextHeight)}px`;
  if (_roadviewMiniMap) _roadviewMiniMap.relayout();
}

function _setRoadviewMiniMapRoadviewLayer(enabled){
  if (!_roadviewMiniMap || !kakao.maps || !kakao.maps.MapTypeId) return;
  const roadviewType = kakao.maps.MapTypeId.ROADVIEW;
  if (!roadviewType) return;
  const method = enabled ? "addOverlayMapTypeId" : "removeOverlayMapTypeId";
  if (typeof _roadviewMiniMap[method] === "function"){
    _roadviewMiniMap[method](roadviewType);
  }
}

function _bindRoadviewMiniMapResize(){
  if (_roadviewMiniMapResizeBound) return;
  const wrap = document.getElementById("roadviewMiniMapWrap");
  const handle = document.getElementById("roadviewMiniMapResize");
  if (!wrap || !handle || !handle.addEventListener) return;
  _roadviewMiniMapResizeBound = true;

  let resizeState = null;
  const finishResize = (event) => {
    if (!resizeState || (event && event.pointerId !== resizeState.pointerId)) return;
    resizeState = null;
    document.removeEventListener("pointermove", moveResize);
    document.removeEventListener("pointerup", finishResize);
    document.removeEventListener("pointercancel", finishResize);
  };
  const moveResize = (event) => {
    if (!resizeState || event.pointerId !== resizeState.pointerId) return;
    _resizeRoadviewMiniMap(
      resizeState.width + event.clientX - resizeState.clientX,
      resizeState.height - event.clientY + resizeState.clientY,
    );
  };
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    const rect = wrap.getBoundingClientRect ? wrap.getBoundingClientRect() : null;
    resizeState = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      width: Number(rect && rect.width) || wrap.offsetWidth || 190,
      height: Number(rect && rect.height) || wrap.offsetHeight || 132,
    };
    if (handle.setPointerCapture) handle.setPointerCapture(event.pointerId);
    document.addEventListener("pointermove", moveResize);
    document.addEventListener("pointerup", finishResize);
    document.addEventListener("pointercancel", finishResize);
    if (event.preventDefault) event.preventDefault();
  });
  handle.addEventListener("keydown", (event) => {
    const increments = {
      ArrowRight: [16, 0],
      ArrowLeft: [-16, 0],
      ArrowUp: [0, 16],
      ArrowDown: [0, -16],
    };
    const increment = increments[event.key];
    if (!increment) return;
    const rect = wrap.getBoundingClientRect ? wrap.getBoundingClientRect() : null;
    _resizeRoadviewMiniMap(
      (Number(rect && rect.width) || wrap.offsetWidth || 190) + increment[0],
      (Number(rect && rect.height) || wrap.offsetHeight || 132) + increment[1],
    );
    if (event.preventDefault) event.preventDefault();
  });
  if (typeof ResizeObserver !== "undefined"){
    _roadviewMiniMapResizeObserver = new ResizeObserver(() => {
      if (_roadviewMiniMap) _roadviewMiniMap.relayout();
    });
    _roadviewMiniMapResizeObserver.observe(wrap);
  }
}

function _syncRoadviewMiniCamera(){
  if (!_roadview || !_roadviewMiniCamera || !_roadview.getViewpoint) return;
  const viewpoint = _roadview.getViewpoint();
  const pan = Number(viewpoint && viewpoint.pan);
  if (Number.isFinite(pan)){
    _roadviewMiniCamera.style.transform = `rotate(${pan}deg)`;
  }
}

function _ensureRoadviewMiniMap(position){
  if (!window.kakao || !kakao.maps || !kakao.maps.Map || !kakao.maps.CustomOverlay) return false;
  const element = document.getElementById("roadviewMiniMap");
  const center = position || _roadviewMiniMapCenter();
  if (!element || !center) return false;
  _bindRoadviewMiniMapResize();
  if (!_roadviewMiniMap){
    _roadviewMiniMap = new kakao.maps.Map(element, {
      center,
      level: 3,
      draggable: true,
      zoomable: true,
      scrollwheel: true,
      disableDoubleClick: false,
    });
    _roadviewMiniCamera = document.createElement("div");
    _roadviewMiniCamera.className = "roadview-mini-camera";
    _roadviewMiniCamera.setAttribute("aria-hidden", "true");
    _roadviewMiniMarker = new kakao.maps.CustomOverlay({
      position: center,
      content: _roadviewMiniCamera,
      xAnchor: 0.5,
      yAnchor: 0.5,
      zIndex: 10,
    });
    _roadviewMiniMarker.setMap(_roadviewMiniMap);
    _setRoadviewMiniMapRoadviewLayer(_activeMapTool === "roadview");
    if (kakao.maps.event && kakao.maps.event.addListener){
      kakao.maps.event.addListener(_roadviewMiniMap, "click", event => {
        if (_activeMapTool !== "roadview" || !event || !event.latLng) return;
        _openRoadviewAt(event.latLng);
      });
    }
  }
  return true;
}

function _syncRoadviewMiniMap(position){
  if (!_ensureRoadviewMiniMap(position)) return;
  if (position){
    _roadviewMiniMap.setCenter(position);
    if (_roadviewMiniMarker) _roadviewMiniMarker.setPosition(position);
  }
  _syncRoadviewMiniCamera();
  // 패널을 막 연 직후에는 미니맵 컨테이너의 크기가 확정되지 않아 타일이
  // 회색으로 남을 수 있다. 레이아웃이 반영된 다음 다시 맞춘다.
  setTimeout(() => {
    if (_roadviewMiniMap) _roadviewMiniMap.relayout();
  }, 0);
}

function _clearMeasure(){
  _measurePoints = [];
  _measureFinished = false;
  if (_measureLine){ _measureLine.setMap(null); _measureLine = null; }
  if (_measureLabel){ _measureLabel.setMap(null); _measureLabel = null; }
  const panel = document.getElementById("measurePanel");
  const status = document.getElementById("measureStatus");
  if (panel) panel.hidden = true;
  if (status) status.textContent = "지도를 클릭해 측정을 시작하세요.";
}

function _formatMapDistance(meters){
  if (meters < 1000) return `${Math.round(meters)}m`;
  return `${(meters / 1000).toFixed(2)}km`;
}

function _distanceBetween(a, b){
  const earthRadius = 6371000;
  const toRad = value => value * Math.PI / 180;
  const dLat = toRad(b.getLat() - a.getLat());
  const dLng = toRad(b.getLng() - a.getLng());
  const lat1 = toRad(a.getLat());
  const lat2 = toRad(b.getLat());
  const sinLat = Math.sin(dLat / 2);
  const sinLng = Math.sin(dLng / 2);
  const h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLng * sinLng;
  return 2 * earthRadius * Math.asin(Math.min(1, Math.sqrt(h)));
}

function _measureTotal(){
  let total = 0;
  for (let i = 1; i < _measurePoints.length; i++){
    total += _distanceBetween(_measurePoints[i - 1], _measurePoints[i]);
  }
  return total;
}

function _renderMeasureLabel(){
  const panel = document.getElementById("measurePanel");
  const status = document.getElementById("measureStatus");
  if (!panel || !status) return;
  if (_measureFinished && _measurePoints.length > 1){
    status.textContent = `측정 완료 · 총 거리 ${_formatMapDistance(_measureTotal())}`;
    panel.hidden = false;
    return;
  }
  panel.hidden = false;
  if (_measurePoints.length < 2){
    status.textContent = "지도를 클릭해 두 번째 점을 추가하세요.";
    return;
  }
  const total = _measureTotal();
  status.textContent = `총 거리 ${_formatMapDistance(total)} · ${_measurePoints.length}개 지점`;
  if (_measureLabel) _measureLabel.setMap(null);
  const labelEl = document.createElement("div");
  labelEl.className = "map-measure-label";
  labelEl.textContent = _formatMapDistance(total);
  _measureLabel = new kakao.maps.CustomOverlay({
    position: _measurePoints[_measurePoints.length - 1],
    content: labelEl,
    xAnchor: 0,
    yAnchor: 1.4,
    zIndex: 35,
    clickable: false,
  });
  _measureLabel.setMap(kakaoMap);
}

function _addMeasurePoint(latLng){
  if (!kakaoMap || _measureFinished) return;
  _measurePoints.push(latLng);
  if (!_measureLine){
    _measureLine = new kakao.maps.Polyline({
      map: kakaoMap,
      path: _measurePoints,
      strokeWeight: 4,
      strokeColor: "#B4863F",
      strokeOpacity: 0.9,
      strokeStyle: "solid",
    });
  } else {
    _measureLine.setPath(_measurePoints);
  }
  _renderMeasureLabel();
}

function _ensureRoadview(){
  if (_roadview && _roadviewClient){
    _syncRoadviewMiniMap();
    return true;
  }
  if (!window.kakao || !kakao.maps || !kakao.maps.Roadview ||
      !kakao.maps.RoadviewClient){
    showFallbackToast("로드뷰를 불러올 수 없습니다. 카카오 지도 SDK 설정을 확인해주세요.");
    return false;
  }
  const element = document.getElementById("roadview");
  if (!element) return false;
  _roadviewClient = new kakao.maps.RoadviewClient();
  _roadview = new kakao.maps.Roadview(element);
  _syncRoadviewMiniMap();
  if (kakao.maps.event && kakao.maps.event.addListener){
    kakao.maps.event.addListener(_roadview, "panoid_changed", () => {
      if (!_roadview || _activeMapTool !== "roadview") return;
      _syncRoadviewMiniMap(_roadview.getPosition());
    });
    kakao.maps.event.addListener(_roadview, "viewpoint_changed", () => {
      if (!_roadview || _activeMapTool !== "roadview") return;
      _syncRoadviewMiniCamera();
    });
  }
  setTimeout(() => {
    if (_roadview) _roadview.relayout();
    _syncRoadviewMiniMap();
  }, 0);
  return true;
}

function _openRoadviewAt(latLng){
  const sequence = ++_roadviewRequestSequence;
  const hint = document.getElementById("roadviewHint");
  const panel = document.getElementById("roadviewPanel");
  if (panel){
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
  }
  if (!_ensureRoadview()) return;
  if (hint) hint.textContent = "가까운 로드뷰를 찾는 중…";
  _roadviewClient.getNearestPanoId(latLng, 40, (panoId) => {
    if (sequence !== _roadviewRequestSequence || _activeMapTool !== "roadview") return;
    if (!panoId){
      if (hint) hint.textContent = "이 위치 주변에는 로드뷰가 없습니다. 다른 지점을 클릭해보세요.";
      showFallbackToast("이 위치 주변에는 로드뷰가 없습니다.");
      return;
    }
    _roadview.setPanoId(panoId, latLng);
    _syncRoadviewMiniMap(latLng);
    _syncRoadviewMiniCamera();
    if (hint) hint.textContent = "지도를 다시 클릭하면 다른 위치의 로드뷰를 확인합니다.";
  });
}

function _clearPoiResults(){
  _poiRequestSequence++;
  if (_poiRefreshTimer !== null){
    clearTimeout(_poiRefreshTimer);
    _poiRefreshTimer = null;
  }
  _poiScheduledCenterKey = null;
  _poiPendingCenterKey = null;
  _poiDisplayedCenterKey = null;
  if (_poiFetchController){
    _poiFetchController.abort();
    _poiFetchController = null;
  }
  _clearMapToolOverlays();
}

function _poiCenterKey(center){
  if (!center || typeof center.getLat !== "function" || typeof center.getLng !== "function"){
    return "";
  }
  return `${center.getLat().toFixed(6)},${center.getLng().toFixed(6)}`;
}

function _schedulePoiRefresh(){
  if (!kakaoMap || (_activeMapTool !== "education" && _activeMapTool !== "convenience")){
    return;
  }
  const centerKey = _poiCenterKey(kakaoMap.getCenter());
  if (!centerKey || centerKey === _poiDisplayedCenterKey || centerKey === _poiPendingCenterKey){
    return;
  }
  // 같은 이동/줌 동작에서 이어지는 idle 이벤트는 마지막 이벤트 하나로 합친다.
  if (_poiRefreshTimer !== null && _poiScheduledCenterKey === centerKey) return;
  if (_poiRefreshTimer !== null){
    clearTimeout(_poiRefreshTimer);
    _poiRefreshTimer = null;
  }
  _poiScheduledCenterKey = centerKey;

  // 지도 중심이 바뀌면 이전 위치의 요청·마커를 즉시 폐기한다. AbortController를
  // 무시하는 fetch 구현에서도 sequence 검사로 늦은 응답이 되살아나지 않는다.
  _poiRequestSequence++;
  if (_poiFetchController){
    _poiFetchController.abort();
    _poiFetchController = null;
  }
  _poiPendingCenterKey = null;
  _poiDisplayedCenterKey = null;
  _clearMapToolOverlays();

  _poiRefreshTimer = setTimeout(() => {
    _poiRefreshTimer = null;
    _poiScheduledCenterKey = null;
    if (_activeMapTool !== "education" && _activeMapTool !== "convenience") return;
    const currentCenterKey = _poiCenterKey(kakaoMap.getCenter());
    if (currentCenterKey !== centerKey){
      _schedulePoiRefresh();
      return;
    }
    _loadPoi(_activeMapTool);
  }, POI_REFRESH_DEBOUNCE_MS);
}

function _renderPoiResults(items){
  _clearMapToolOverlays();
  (items || []).forEach(item => {
    if (!Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lng))) return;
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "map-poi-marker";
    marker.title = `${item.name || "주변 시설"}${item.address ? ` · ${item.address}` : ""}`;
    marker.setAttribute("aria-label", marker.title);
    marker.innerHTML = `<span>${item.category === "학교" ? "학" : item.category === "학원" ? "원" : item.category === "편의점" ? "편" : item.category === "병원" ? "병" : item.category === "약국" ? "약" : "주"}</span>`;
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      if (item.url) window.open(item.url, "_blank", "noopener,noreferrer");
    });
    const overlay = new kakao.maps.CustomOverlay({
      position: new kakao.maps.LatLng(Number(item.lat), Number(item.lng)),
      content: marker,
      xAnchor: 0.5,
      yAnchor: 1,
      zIndex: 30,
      clickable: true,
    });
    overlay.setMap(kakaoMap);
    overlay.__contentEl = marker;
    _mapToolOverlays.push(overlay);
  });
}

async function _loadPoi(tool){
  if (!kakaoMap || (tool !== "education" && tool !== "convenience")) return;
  const center = kakaoMap.getCenter();
  const centerKey = _poiCenterKey(center);
  if (!centerKey || _poiPendingCenterKey === centerKey) return;
  if (_poiRefreshTimer !== null){
    clearTimeout(_poiRefreshTimer);
    _poiRefreshTimer = null;
  }
  _poiScheduledCenterKey = null;
  if (_poiFetchController) _poiFetchController.abort();
  const sequence = ++_poiRequestSequence;
  _poiPendingCenterKey = centerKey;
  const controller = new AbortController();
  _poiFetchController = controller;
  const params = new URLSearchParams({
    type: tool,
    lat: String(center.getLat()),
    lng: String(center.getLng()),
    radius: "1500",
  });
  try {
    const response = await fetch(`/api/v1/m/6b4?${params.toString()}`, {
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (sequence !== _poiRequestSequence || _activeMapTool !== tool ||
        centerKey !== _poiCenterKey(kakaoMap.getCenter())) return;
    if (!response.ok || data.ok !== true){
      _clearMapToolOverlays();
      showFallbackToast(data.message || "주변정보를 불러오지 못했습니다.");
      return;
    }
    _poiDisplayedCenterKey = centerKey;
    _renderPoiResults(data.items);
    if (!data.items || data.items.length === 0) showFallbackToast("이 지도 중심 주변에는 표시할 시설이 없습니다.");
  } catch(e){
    if (e.name === "AbortError") return;
    if (sequence !== _poiRequestSequence || _activeMapTool !== tool ||
        centerKey !== _poiCenterKey(kakaoMap.getCenter())) return;
    _clearMapToolOverlays();
    showFallbackToast("주변정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
  } finally {
    if (sequence === _poiRequestSequence){
      _poiFetchController = null;
      _poiPendingCenterKey = null;
    }
  }
}

function _deactivateMapTool(){
  if (_poiRefreshTimer){
    clearTimeout(_poiRefreshTimer);
    _poiRefreshTimer = null;
  }
  _roadviewRequestSequence++;
  if (kakaoMap && kakao.maps && kakao.maps.MapTypeId &&
      kakao.maps.MapTypeId.ROADVIEW && kakaoMap.removeOverlayMapTypeId){
    kakaoMap.removeOverlayMapTypeId(kakao.maps.MapTypeId.ROADVIEW);
  }
  _setRoadviewMiniMapRoadviewLayer(false);
  _activeMapTool = null;
  _clearPoiResults();
  _clearMeasure();
  _closeRoadviewPanel();
  _setMapToolButtonState();
}

function _activateMapTool(tool){
  if (_activeMapTool === tool){
    _deactivateMapTool();
    return;
  }
  _deactivateMapTool();
  _activeMapTool = tool;
  _setMapToolButtonState();
  if (tool === "roadview"){
    if (kakaoMap && kakao.maps && kakao.maps.MapTypeId &&
        kakao.maps.MapTypeId.ROADVIEW && kakaoMap.addOverlayMapTypeId){
      kakaoMap.addOverlayMapTypeId(kakao.maps.MapTypeId.ROADVIEW);
    }
    _setRoadviewMiniMapRoadviewLayer(true);
    showFallbackToast("파란색 도로에서 원하는 지점을 클릭하면 로드뷰가 열립니다.");
  } else if (tool === "measure"){
    const panel = document.getElementById("measurePanel");
    if (panel) panel.hidden = false;
  } else {
    _loadPoi(tool);
  }
}

function _initMapToolControls(){
  const mapTypeButton = document.getElementById("mapTypeTool");
  const mapTypeState = document.getElementById("mapTypeState");
  if (mapTypeButton){
    mapTypeButton.addEventListener("click", () => {
      if (!kakaoMap || !kakao.maps.MapTypeId) return;
      _mapTypeIndex = (_mapTypeIndex + 1) % MAP_TYPE_STEPS.length;
      const step = MAP_TYPE_STEPS[_mapTypeIndex];
      const typeId = _mapTypeId(step.id);
      if (typeId) kakaoMap.setMapTypeId(typeId);
      if (mapTypeState) mapTypeState.textContent = step.label;
      mapTypeButton.setAttribute("aria-label", `지도전환: ${step.label}`);
    });
  }
  [["roadviewTool", "roadview"], ["measureTool", "measure"],
   ["educationTool", "education"], ["convenienceTool", "convenience"]]
    .forEach(([id, tool]) => {
      const button = document.getElementById(id);
      if (button) button.addEventListener("click", () => _activateMapTool(tool));
    });
  const closeButton = document.getElementById("roadviewClose");
  if (closeButton) closeButton.addEventListener("click", () => {
    if (_activeMapTool === "roadview") _deactivateMapTool();
    else _closeRoadviewPanel();
  });
  const resetButton = document.getElementById("measureReset");
  if (resetButton) resetButton.addEventListener("click", _clearMeasure);
}

function _bindMapToolMapEvents(){
  kakao.maps.event.addListener(kakaoMap, "click", event => {
    if (_activeMapTool === "roadview") _openRoadviewAt(event.latLng);
    else if (_activeMapTool === "measure") _addMeasurePoint(event.latLng);
  });
  kakao.maps.event.addListener(kakaoMap, "rightclick", () => {
    if (_activeMapTool === "measure" && _measurePoints.length > 1){
      _measureFinished = true;
      _renderMeasureLabel();
    }
  });
  kakao.maps.event.addListener(kakaoMap, "dblclick", () => {
    if (_activeMapTool === "measure" && _measurePoints.length > 1){
      _measureFinished = true;
      _renderMeasureLabel();
      showFallbackToast("거리 측정을 마쳤습니다. 초기화 후 다시 측정할 수 있습니다.");
    }
  });
}

// 새 레이어가 준비될 때까지 기존 CustomOverlay를 지도에 남겼다가 짧게 페이드아웃한다.
function _beginMapLayerSwap(){
  // 빠른 줌 변경으로 직전 렌더가 끝나지 않았어도, 더 오래된 레이어는 즉시 퇴장시킨다.
  _finishMapLayerSwap(_pendingFadeOutOverlays);
  const previousCustomOverlays = [
    ...mapOverlays,
    ...mapLabelData.map(d => d.overlay).filter(Boolean),
    ..._clusterOverlays,
  ];
  mapOverlays = [];
  mapLabelData = [];
  _clusterOverlays = [];
  _pendingFadeOutOverlays = previousCustomOverlays;
  return previousCustomOverlays;
}

function _fadeOutCustomOverlays(overlays){
  if (!overlays || overlays.length === 0) return;
  requestAnimationFrame(() => {
    overlays.forEach(overlay => {
      const el = overlay.__contentEl;
      if (el) {
        el.style.transition = "opacity .18s ease";
        el.style.opacity = "0";
      }
    });
  });
  setTimeout(() => overlays.forEach(overlay => overlay.setMap(null)), MAP_OVERLAY_FADE_MS);
}

function _finishMapLayerSwap(overlays){
  if (!overlays || overlays.length === 0) return;
  _pendingFadeOutOverlays = _pendingFadeOutOverlays.filter(
    overlay => !overlays.includes(overlay)
  );
  _fadeOutCustomOverlays(overlays);
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

// 현재 확대 레벨을 보고 1건 이상인 마커의 원형 숫자 배지를 표시/숨김한다.
// 0건 건물은 기존 작은 점 마커만 유지한다.
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
    if ((Number(d.b.total_count) || 0) < 1){
      if (d.overlay) d.overlay.setMap(null);
      return;
    }
    const inView = bounds ? bounds.contain(d.pos) : true;
    if (inView){
      if (!d.overlay){
        // 최초 줌인 시 1회만 DOM + CustomOverlay 생성
        d.el = _buildCircleBadgeEl(d.b);
        if (!d.el) return;
        syncMapLocationTargetElement(d.el, d.b.id);
        d.overlay = new kakao.maps.CustomOverlay({
          position: d.pos, content: d.el,
          xAnchor: 0.5, yAnchor: 1.0, zIndex: 20, // Kakao 기본 POI(~3)·마커(5)보다 위
          clickable: true,  // 모바일 탭 이벤트가 label DOM에 전달되도록
        });
        d.overlay.__contentEl = d.el;
      }
      d.overlay.setMap(kakaoMap);
    } else {
      // viewport 밖: 이미 표시 중인 경우만 숨김
      if (d.overlay) d.overlay.setMap(null);
    }
  });
}

// 마커 정보 내용 공용 빌더 — 호버 툴팁과 클릭 InfoWindow가 완전히 동일한
// 내용(건물명·용도·최근 실거래 + 관심저장 버튼 + "상세보기 →" 링크)을 쓰도록
// 한 곳에서 HTML을 만든다. 두 곳의 내용이 갈라지며 "이중 마커"처럼 느껴지던
// 문제를 없애기 위한 단일 소스.
function buildingInfoInnerHtml(b){
  const name = escapeHtml(b.building_name || "(건물명 미확인)");
  const nameSource = b.building_name_source === "lodging_report"
    ? `<span style="font-size:10.5px; font-weight:600; color:#386641;">(영업신고 기준${Number(b.building_name_candidate_count || 0) > 1 ? " · 규모 최대" : ""})</span>`
    : "";
  const typeKo = escapeHtml(lodgingLabelKo(b.lodging_type, b.building_status));
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
    ? `<div style="display:inline-flex; align-items:center; gap:3px; font-size:11px; color:#B4863F; background:#fffbf3; border:1px solid #f0ddb0; border-radius:6px; padding:2px 8px; margin-bottom:3px;">${Icons.heart(13)}<span>를 눌러 저장해보세요</span></div><br>`
    : "";
  const favBtn = canFav
    ? markerTipHtml + `<button type="button" data-name="${escapeHtml(b.building_name || "")}" data-address="${escapeHtml(favAddr)}" data-bid="${b.id != null ? b.id : ""}"
         onclick="return window.toggleFavFromInfo(this);"
         style="border:none; background:none; cursor:pointer; padding:0; font-size:12.5px; font-weight:700; color:${favActive ? "#B4863F" : "#8a94a0"};">
         <span style="display:inline-flex; align-items:center; gap:4px;">${Icons.heart(14, favActive)}<span>${favActive ? "관심저장됨" : "관심저장"}</span></span></button>`
    : "";
  const actionRow = (favBtn || detailLink)
    ? `<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:8px;">${favBtn}${detailLink}</div>`
    : "";

  return (
    `<div style="font-weight:700; font-size:13.5px; margin-bottom:2px;">${name} ${nameSource}</div>` +
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
  const myGen = ++_mapRenderGen;   // 이전 마커·클러스터 응답 및 addChunk 루프를 모두 폐기한다.
  if (_mapFetchController) _mapFetchController.abort();
  const emptyEl = document.getElementById("mapEmpty");

  const params = new URLSearchParams();
  ["building_id", "q", "si_do", "sgg_nm", "umd_nm", "lodging_type"].forEach(k => {
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

  // 네트워크 취소를 지원하지 않는 환경에서도 공용 세대 검사로 늦은 응답을 안전하게 폐기한다.
  const controller = new AbortController();
  _mapFetchController = controller;
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
  if (_mapRenderGen !== myGen) {
    controller.abort();  // 이미 응답 받았지만 결과를 버린다
    return;
  }

  // 기존 CustomOverlay는 새 배지가 생성될 때까지 남겨둔 뒤 짧게 페이드아웃한다.
  const previousCustomOverlays = _beginMapLayerSwap();
  const bounds = new kakao.maps.LatLngBounds();
  let placed = 0;

  // 유효 좌표만 필터링
  // 겹침 우선순위: 생활 > 관광 > 복합 > 일반 > 에어비앤비 > 한옥 > 농어촌민박 > 캠핑 > 준공전 > 미분류
  // Kakao Maps 캔버스는 나중에 추가된 마커가 위에 그려지므로
  // 우선순위 낮은 타입부터 먼저 추가해야 높은 타입이 위에 표시된다.
  const _DRAW_ORDER = {
    "미분류": 0, "준공전": 1,
    "캠핑": 2, "농어촌민박": 3, "한옥": 4, "에어비앤비": 5,
    "일반": 6, "복합": 7, "관광": 8, "생활": 9,
  };
  function _markerDrawOrder(b){
    if (!b.lodging_type){
      // lodging_type 없음 — building_status로 준공전/미분류 구분
      return (b.building_status === "허가" || b.building_status === "착공") ? 1 : 0;
    }
    if (b.lodging_type.includes("·")) return _DRAW_ORDER["복합"];
    return _DRAW_ORDER[b.lodging_type] ?? 0;
  }
  const validItems = items
    .filter(b => b.lat != null && b.lng != null)
    .sort((a, b) => _markerDrawOrder(a) - _markerDrawOrder(b));

  // 마커를 CHUNK_SIZE 단위로 나눠 setTimeout(0)으로 분산 생성 —
  // 한 번에 수천 개를 동기 삽입하면 메인 스레드가 블로킹돼 화면이 굳는다.
  // 숫자 배지는 가까운 줌 레벨에서만 lazy 생성한다.
  const CHUNK_SIZE = 300;
  let idx = 0;

  function addChunk(){
    if (_mapRenderGen !== myGen) return; // 더 새로운 지도 렌더 요청이 있음 — 이 루프 폐기
    const end = Math.min(idx + CHUNK_SIZE, validItems.length);
    for (; idx < end; idx++){
      const b = validItems[idx];
      const pos = new kakao.maps.LatLng(b.lat, b.lng);
      const totalCount = Math.max(0, Number(b.total_count) || 0);

      // 합계 0건은 기존 점 마커를 유지하고, 1건 이상은 원형 숫자 배지만 표시한다.
      if (totalCount === 0){
        const color = markerColor(b.lodging_type, b.building_status);
        // 점도 CustomOverlay로 만들어 다른 배지·클러스터와 동일하게 페이드아웃한다.
        const el = document.createElement("button");
        el.type = "button";
        el.title = b.building_name || "건물";
        el.setAttribute("aria-label", el.title);
        el.style.cssText =
          `width:14px;height:14px;padding:0;border:2px solid #fff;border-radius:50%;background:${color};` +
          "box-sizing:border-box;box-shadow:0 1px 3px rgba(0,0,0,.24);cursor:pointer;" +
          "pointer-events:auto;transition:opacity .18s ease;";
        syncMapLocationTargetElement(el, b.id);
        el.addEventListener("click", (event) => {
          event.stopPropagation();
          _openBuildingFromMap(b);
        });
        const overlay = new kakao.maps.CustomOverlay({
          position: pos, content: el, xAnchor: 0.5, yAnchor: 0.5,
          clickable: true, zIndex: 5,
        });
        overlay.__buildingId = b.id;
        overlay.__contentEl = el;
        overlay.setMap(kakaoMap);
        mapOverlays.push(overlay);
      } else {
        // 실제 DOM/오버레이는 updateMarkerLabels에서 가까운 줌 레벨에 lazy 생성
        mapLabelData.push({ b, pos, overlay: null, el: null });
      }
      bounds.extend(pos);
      placed++;
    }

    if (idx < validItems.length){
      setTimeout(addChunk, 0);
      return;
    }

    // 전체 완료 후 처리
    if (emptyEl) {
      if (placed === 0) {
        if (!filters.q) emptyEl.textContent = "이 지역은 아직 등록된 매물이 없어요";
        emptyEl.style.display = "flex";
      } else {
        emptyEl.style.display = "none";
      }
    }
    if (placed > 0 && opts.fit === true) {
      kakaoMap.setBounds(bounds);
      // 카카오맵은 단일 좌표에 setBounds를 하면 지나치게 넓은 레벨로 남는 특성이 있음.
      // 결과가 1~2건이면 명시적으로 레벨 3으로 확대해 건물이 화면에 꽉 차게 표시한다.
      if (placed <= 2) kakaoMap.setLevel(3);
    }
    updateMarkerLabels();
    applyMapLocationTarget();
    _finishMapLayerSwap(previousCustomOverlays);
    console.log(`[MAP] 마커 ${placed}개 표시 (필터: ${qs || "없음"})`);
    if (placed === 1 && filters.q && validItems[0]?.building_name) {
      const normalizeSearchText = (value) => String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
      const searchedName = normalizeSearchText(filters.q);
      const matchedName = normalizeSearchText(validItems[0].building_name);
      if (searchedName && matchedName && searchedName !== matchedName) {
        showFallbackToast(`정확히 일치하는 건물은 없어 '${String(filters.q).trim()}'을(를) 찾았습니다`);
      }
    }
    // 완료 콜백 — updateMapForZoom의 0건 폴백 판단에 사용
    if (opts.onComplete) opts.onComplete(placed);
  }

  addChunk();
}

// 현재 지도 줌 레벨로 클러스터 모드를 결정
function _clusterModeForLevel(lv){
  if (lv >= CLUSTER_SIDO_MIN_LEVEL) return "sido";
  if (lv >= CLUSTER_SGG_MIN_LEVEL)  return "sgg";
  if (lv >= CLUSTER_UMD_MIN_LEVEL)  return "umd";   // 읍면동 집계 배지 (lv 7)
  return "markers";
}

// 클러스터 배지(CustomOverlay) 렌더링
// clusterLevel: 'sido'|'sgg'|'umd', filters: mapFiltersFromState()
async function loadClusterOverlays(clusterLevel, filters = {}){
  if (!kakaoMap) return;
  const myGen = ++_mapRenderGen;  // 마커·다른 클러스터 요청을 포함해 이전 응답을 폐기한다.
  if (_mapFetchController) _mapFetchController.abort();

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

  const controller = new AbortController();
  _mapFetchController = controller;
  let items = [];
  try {
    const res  = await fetch(`/api/buildings-cluster?${params}`, { signal: controller.signal });
    const data = await res.json();
    items = data.items || [];
  } catch(e){
    if (e.name === "AbortError") return;
    console.error("[CLUSTER] 집계 로드 실패:", e);
    return;
  }

  // 응답 대기 중 줌·드래그·검색으로 더 새로운 렌더 요청이 발생했으면 무시한다.
  if (_mapRenderGen !== myGen) return;

  // 클러스터 모드에서도 0건이면 mapEmpty 표시, 있으면 숨김
  const _mapEmptyEl = document.getElementById("mapEmpty");
  if (_mapEmptyEl) {
    if (items.length === 0) {
      showMapEmptyBanner();
    } else {
      _mapEmptyEl.style.display = "none";
    }
  }

  // 새 클러스터 배지를 만든 뒤 이전 레이어를 페이드아웃한다.
  const previousCustomOverlays = _beginMapLayerSwap();

  // 클러스터 배지 색상 — LODGING_COLORS와 동일 (이중 관리 방지를 위해 참조)
  const BAR_COLORS = [
    { key: "생활",   color: LODGING_COLORS["생활"]   },
    { key: "관광",   color: LODGING_COLORS["관광"]   },
    { key: "일반",   color: LODGING_COLORS["일반"]   },
    { key: "에어비앤비", color: LODGING_COLORS["에어비앤비"] },
    { key: "농어촌민박", color: LODGING_COLORS["농어촌민박"] },
    { key: "캠핑",   color: LODGING_COLORS["캠핑"]   },
    { key: "한옥",   color: LODGING_COLORS["한옥"]   },
    { key: "복합",   color: LODGING_COLORS["복합"]   },
    { key: "준공전", color: LODGING_COLORS["준공전"] },
    { key: "미분류", color: LODGING_COLORS["미분류"] },
  ];

  // 클릭 시 드릴다운: 시도→시군구(9), 시군구→읍면동(7), 읍면동→개별마커(5)
  const drillLevel = clusterLevel === "sido" ? 9 : (clusterLevel === "sgg" ? 7 : 5);

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
      "min-width:52px;max-width:120px;transition:opacity .18s ease;";
    el.innerHTML =
      `<div style="font-size:11px;font-weight:700;color:#16202E;white-space:nowrap;` +
      `overflow:hidden;text-overflow:ellipsis;max-width:116px;">${escapeHtml(clusterLevel === "umd" ? item.name.trim().split(" ").pop() : item.name)}</div>` +
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
    // anchorLeft: true → xAnchor:1(배지 오른쪽 끝이 좌표에 고정 = 배지가 좌표 왼쪽에 표시)
    const anchorLeft = isSido && SIDO_ANCHOR_LEFT.has(item.name);
    if (isSido) {
      // 모바일: 좁은 화면에서 배지가 밀려나지 않도록 최소 간격만 적용
      // 데스크톱: 글자당 ~13px 기준으로 Kakao 지명 텍스트 너비만큼 여백 확보
      const nameLen = item.name ? item.name.length : 4;
      const gap = isMobileMapViewport() ? "6px" : Math.max(44, nameLen * 13 + 4) + "px";
      if (anchorLeft) {
        el.style.marginRight = gap;  // 배지가 좌표 왼쪽에 붙으므로 오른쪽 여백으로 지명 침범 방지
      } else {
        el.style.marginLeft = gap;
      }
    }
    const overlay = new kakao.maps.CustomOverlay({
      position: pos, content: el,
      xAnchor: isSido ? (anchorLeft ? 1 : 0) : 0.5,
      yAnchor: isSido ? 0.5 : 1.0,
      zIndex: 10,
    });
    overlay.setMap(kakaoMap);
    overlay.__contentEl = el;
    _clusterOverlays.push(overlay);
  });

  _finishMapLayerSwap(previousCustomOverlays);
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
  const forceMarkers = !!(
    (filters.q && filters.q.trim())
    || filters.building_id != null
  );
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

    // q 검색 0건 → umd 클러스터 폴백 콜백
    // "이 건물은 아직 지도에 없지만 이 동네엔 이만큼 등록돼 있다"는 최소 피드백 제공.
    // q를 제거하고 나머지 지역 필터(si_do/sgg_nm/umd_nm)만 유지해 umd 배지를 표시한다.
    const _markerOpts = { fit: opts.fit || forceMarkers, skipBounds: forceMarkers };
    if (forceMarkers){
      _markerOpts.onComplete = (placed) => {
        if (placed === 0){
          const fallback = Object.assign({}, filters);
          delete fallback.q;  // 검색어 제거 — 지역 필터만으로 umd 집계
          const hasRegionFilter = !!(fallback.si_do || fallback.sgg_nm || fallback.umd_nm);
          if (hasRegionFilter){
            _currentMapMode = "umd";
            loadClusterOverlays("umd", fallback);
            console.log("[MAP] q=0건 → umd 클러스터 폴백");
          } else {
            showMapEmptyBanner("검색 결과가 없습니다. 건물명을 다시 확인해주세요.");
            console.log("[MAP] 지역 필터 없는 q=0건 → 전국 클러스터 폴백 생략");
          }
        }
      };
    }
    await loadMapMarkers(filters, _markerOpts);
  } else {
    if (_currentMapMode !== mode || opts.force){
      _currentMapMode = mode;
      await loadClusterOverlays(mode, filters);
    }
    // 같은 클러스터 레벨 내에서 zoom만 바뀐 경우는 재로드 없음
  }
}

function initMapToolIcons(){
  if (!window.Icons) return;
  const toolIcons = {
    iconMapType: Icons.layers,
    iconRoadview: Icons.navigation,
    iconMeasure: Icons.ruler,
    iconEducation: Icons.graduationCap,
    iconConvenience: Icons.storeIcon,
  };
  Object.entries(toolIcons).forEach(([id, icon]) => {
    const element = document.getElementById(id);
    if (element) element.innerHTML = icon(15);
  });
}

async function initMap(){
  const container = document.getElementById("map");
  if (!container) return;

  initMapToolIcons();
  const dv = mapDefaultView();
  kakaoMap = new kakao.maps.Map(container, {
    center: new kakao.maps.LatLng(dv.center.lat, dv.center.lng),
    level: dv.level,
  });
  _initMapToolControls();
  _bindMapToolMapEvents();

  // 확대/축소(+/-) 버튼 — 휠/핀치줌이 불안정할 때를 위한 명시적 컨트롤.
  // 우측 하단(BOTTOMRIGHT)에 배치하되, 같은 자리의 범례박스(.map-legend)와
  // 겹치지 않도록 범례 높이만큼 bottom 오프셋을 JS로 계산해 위로 띄운다.
  // (우측 상단은 검색 토글 버튼 자리라 비워둔다)
  kakaoMap.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.BOTTOMRIGHT);
  liftZoomControlAboveLegend();
  window.addEventListener("resize", () => setTimeout(liftZoomControlAboveLegend, 150));

  // 지도 이동·줌 완료 시 마지막 위치를 localStorage에 저장 — 새로고침 후 복원에 사용
  // idle은 이동이 멈춘 뒤 발생한다. 주변정보 도구는 여기서 짧게 디바운스해
  // 빠른 드래그·확대/축소 중 발생하는 연속 이벤트를 한 번의 요청으로 합친다.
  kakao.maps.event.addListener(kakaoMap, "idle", () => {
    const c = kakaoMap.getCenter();
    localStorage.setItem("map_last_view", JSON.stringify({
      lat: c.getLat(), lng: c.getLng(), level: kakaoMap.getLevel(),
      savedAt: Date.now(),
    }));
    _schedulePoiRefresh();
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

// 줌 컨트롤을 지도 툴바 바로 아래에 붙이고 우측 하단 범례박스와의 겹침을 막는다.
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
  if (window.innerWidth <= 520){
    wrap.style.display = "none";
    return;
  }
  const legend = document.querySelector(".map-legend");
  const toolbar = document.getElementById("mapToolbar");
  const toolbarHeight = toolbar ? toolbar.offsetHeight : 0;
  // 툴바와 줌 컨트롤이 하나의 세로 라인으로 붙어야 하므로
  // 툴바 높이 + 최소 간격(8px)만 반영한다. 범례 높이는 이 위치 계산에 사용하지 않는다.
  let lift = toolbarHeight + 8;
  // 방어: 범례 높이가 비정상적으로 크게 계산돼도(레이아웃 깨짐 등)
  // 컨트롤이 지도 밖으로 밀려나지 않도록 상한을 둔다.
  const maxLift = Math.max(24, mapEl.offsetHeight - 120); // 지도 위쪽 120px는 항상 남긴다
  lift = Math.min(lift, Math.max(240, toolbarHeight + 120), maxLift);
  // 주의: wrap의 offsetParent가 높이 0인 요소일 수 있어(bottom 기준이 지도가 아님)
  // bottom 지정 시 화면 밖으로 밀려난다 → 지도 실좌표 기준으로 top을 직접 계산한다.
  const mapRect = mapEl.getBoundingClientRect();
  const parentRect = wrap.offsetParent ? wrap.offsetParent.getBoundingClientRect() : mapRect;
  const topPx = (mapRect.bottom - lift - wrap.offsetHeight) - parentRect.top;
  wrap.style.bottom = "auto";
  wrap.style.top = topPx + "px";
  const r = wrap.getBoundingClientRect();
  console.log(`[MAP] 줌 컨트롤을 툴바 아래로 ${lift}px 올림 — toolbar=${toolbarHeight}px, wrap rect: x=${Math.round(r.x)}, y=${Math.round(r.y)}, w=${Math.round(r.width)}, h=${Math.round(r.height)}, 화면(${window.innerWidth}x${window.innerHeight})`);
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
  btn.innerHTML = `<span style="display:inline-flex; align-items:center; gap:4px;">${Icons.heart(14, active)}<span>${active ? "관심저장됨" : "관심저장"}</span></span>`;
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

/* ===== 좌측 사이드 패널 (지도/검색/게시판과 독립) ===== */
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
  const dot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${markerColor(t.lodging_type, t.building_status)}; margin-right:5px; flex-shrink:0; vertical-align:middle;"></span>`;
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
    return;
  }
  box.innerHTML = items.map(t => renderSideTx(t)).join("");
}

async function loadSideFavorites(){
  const box = document.getElementById("sideFavList");
  if (!box) return;
  const allFavKeys = typeof getFavorites === "function" ? getFavorites() : [];
  if (!allFavKeys.length){
    box.innerHTML = `<div class="side-empty">저장된 관심물건이 없습니다.<br><span style="display:inline-flex;align-items:center;gap:4px;">${Icons.heart(14)}<span>를 눌러 추가하세요.</span></span></div>`;
    return;
  }

  const FAV_INITIAL = 5;
  const favKeys = allFavKeys.slice(0, FAV_INITIAL);
  const remainKeys = allFavKeys.slice(FAV_INITIAL); // 6번째~30번째

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

  // 6개 이상 저장돼 있으면 "더보기" 버튼 추가
  if (remainKeys.length > 0){
    const moreBtn = document.createElement("button");
    moreBtn.className = "side-more";
    moreBtn.textContent = `+ ${remainKeys.length}개 더보기`;
    moreBtn.addEventListener("click", async () => {
      moreBtn.disabled = true;
      moreBtn.textContent = "불러오는 중…";
      let moreItems = [];
      try {
        const res2 = await fetch(`/api/favorites?keys=${encodeURIComponent(remainKeys.join(","))}`);
        const data2 = await res2.json();
        moreItems = data2.items || [];
      } catch(e){ moreBtn.textContent = "오류 — 다시 시도"; moreBtn.disabled = false; return; }
      const byKey2 = {};
      moreItems.forEach(t => {
        const key = `${t.building_name}|${t.address}`;
        if (!(key in byKey2)) byKey2[key] = t;
      });
      const moreOrdered = remainKeys.map(k => byKey2[k]).filter(Boolean);
      const frag = document.createDocumentFragment();
      moreOrdered.forEach((t, i) => {
        const tmp = document.createElement("div");
        tmp.innerHTML = renderSideTx(t, ordered.length + i + 1);
        frag.appendChild(tmp.firstChild);
      });
      box.insertBefore(frag, moreBtn);
      moreBtn.remove();
    });
    box.appendChild(moreBtn);
  }
}

/* ===== 건물 상세: 좌측 패널 전환 ===== */
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
          `<div style="font-size:20px; font-weight:700; color:var(--brass-dark);">전국 ${d.rate}%</div>`;
      } else {
        regBox.textContent = "신고율 데이터를 불러오지 못했습니다.";
      }
    } catch(e){
      regBox.textContent = "신고율 데이터를 불러오지 못했습니다.";
    }
  }

  // sideAgentCount / sideOpConsign / sideOpHousekeeping / sideOpFinance 섹션은
  // 통합 파트너 배너로 대체되어 index.html에서 제거됨 — 관련 로직 삭제
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
      bg: "var(--brass-tint)", border: "#EAD9B8", icon: "🔎", iconSize: 14, pad: "8px 8px",
      title: "건물별 담당중개사를 모집하고 있습니다",
      desc: "건물별 담당 중개사무소를 모집합니다.",
      btnText: "담당중개사로 신청하기", href: "/partner", btnStyle: "",
    },
    consign: {
      bg: "#EEF6E6", border: "#CFE4B8", icon: "🏨", iconSize: 13, pad: "7px 8px",
      title: "위탁운영 지원업체를 찾고 있습니다",
      desc: "",
      btnText: "지원업체로 신청하기", href: "/partner",
      btnStyle: "background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8;",
    },
    housekeeping: {
      bg: "#EEF6E6", border: "#CFE4B8", icon: "🧹", iconSize: 13, pad: "7px 8px",
      title: "",
      desc: `<span style="font-weight:700;">청소 · 세탁 · 용품 · 소독 · 세무 · 인테리어</span>`,
      btnText: "지원업체로 신청하기", href: "/partner",
      btnStyle: "background:#EEF6E6; color:#4A7A18; border-color:#CFE4B8;",
    },
    finance: {
      bg: "var(--brass-tint)", border: "#EAD9B8", icon: "💰", iconSize: 13, pad: "7px 8px",
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
    ? `<a ${opts.linkId ? `id="${opts.linkId}" ` : ""}href="${href}" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:4px 10px; font-size:10.5px; text-decoration:none; ${k.btnStyle}">${btnText}</a>`
    : `<button class="side-more" style="width:auto; margin-top:0; padding:4px 10px; font-size:10.5px; ${k.btnStyle}">${btnText}</button>`;
  return `
    <div style="text-align:center; padding:${k.pad}; background:${k.bg}; border:1px dashed ${k.border}; border-radius:8px;">
      <div style="font-size:${k.iconSize}px; margin-bottom:3px;">${k.icon}</div>
      <div style="font-size:11px; font-weight:700; color:var(--ink); margin-bottom:3px;">${k.title}</div>
      ${k.desc ? `<div style="font-size:10px; color:var(--ink-soft); margin-bottom:5px; line-height:1.3;">${k.desc}</div>` : ""}
      ${btn}
    </div>`;
}

// ---- 파트너 모집 통합 배너 — B화면 상가정보 아래 + A화면 사이드 전용 ----
// 담당중개사·위탁운영·운영지원·금융 4개 개별 빈상태 박스를 하나로 통합
function partnerUnifiedBannerHTML(){
  return `
    <div style="text-align:center; padding:12px 10px; background:linear-gradient(135deg,var(--brass-tint,#FFF5E0) 0%,#EEF6E6 100%); border:1px dashed var(--brass,#B4863F); border-radius:10px;">
      <div style="font-size:14px; margin-bottom:4px;">🤝</div>
      <div style="font-size:12px; font-weight:800; color:var(--ink); margin-bottom:3px;">이 건물의 파트너가 되고 싶으신가요?</div>
      <div style="font-size:10.5px; color:var(--ink-soft); margin-bottom:8px; line-height:1.5;">중개사 · 위탁운영 · 운영지원업체 · 대출상담</div>
      <a href="/partner" class="side-more" style="display:inline-block; width:auto; margin-top:0; padding:5px 16px; font-size:11.5px; text-decoration:none; background:var(--brass,#B4863F); color:#fff; border-color:var(--brass,#B4863F);">파트너 등록하기 →</a>
    </div>`;
}

// 금융 섹션 빈 상태 — 통합 배너로 대체, 하위 호환용 스텁
function financeEmptyHTML(){
  return "";
}

// ── 최근 본 건물 (localStorage, 비로그인 포함) ──────────────────────────────
const HS_RECENT_KEY = "hs_recent_buildings";
const HS_RECENT_MAX = 5;

function trackRecentBuilding(id, name, addr){
  try {
    const normalizedId = Number(id);
    if (!Number.isInteger(normalizedId) || normalizedId <= 0) return;
    let list = JSON.parse(localStorage.getItem(HS_RECENT_KEY) || "[]");
    // 중복 제거 (같은 id가 있으면 맨 앞으로)
    list = Array.isArray(list) ? list.filter(b => Number(b && b.id) !== normalizedId) : [];
    list.unshift({ id: normalizedId, name, addr, viewed_at: Date.now() });
    if (list.length > HS_RECENT_MAX) list = list.slice(0, HS_RECENT_MAX);
    localStorage.setItem(HS_RECENT_KEY, JSON.stringify(list));
    renderRecentChips();
  } catch(e){ /* 스토리지 접근 실패 시 조용히 무시 */ }
}

function renderRecentChips(){
  const row = document.getElementById("recentRow");
  const container = document.getElementById("recentChips");
  if (!row || !container) return;
  let list = [];
  try { list = JSON.parse(localStorage.getItem(HS_RECENT_KEY) || "[]"); } catch(e){}
  list = Array.isArray(list)
    ? list
      .filter(b => Number.isInteger(Number(b && b.id)) && Number(b.id) > 0)
      .slice()
      .sort((a, b) => (Number(b.viewed_at) || 0) - (Number(a.viewed_at) || 0))
      .slice(0, HS_RECENT_MAX)
    : [];
  if (!list.length){ row.style.display = "none"; return; }
  row.style.display = "";
  container.innerHTML = list.map(b => {
    const label = escapeHtml(b.name || "(건물명 미확인)");
    return `<button type="button"
      class="recent-search-chip"
      onclick="openBuildingDetail(${Number(b.id)}); return false;"
      title="${label}">${label}</button>`;
  }).join("");
}

// ── 데이터랩: ① 전국숙박업통계 + 시장 신호 5종 ─────────────────────────────
let dataLabRequestSequence = 0;
let dataLabFetchController = null;
const DATA_LAB_CACHE_TTL_MS = 600000;
const DATA_LAB_CONSIGN_REFRESH_MS = 30000;
const dataLabResponseCache = new Map();
let dataLabActiveKey = null;
let dataLabConsignRefreshTimer = null;

function dataLabNum(value){
  return Number(value || 0).toLocaleString("ko-KR");
}

function dataLabArea(value){
  return value == null || !Number.isFinite(Number(value)) ? "-" : `${Number(value).toFixed(1)}㎡`;
}

function dataLabSimpleAddress(item){
  const shortAddress = [item.sgg_nm, item.umd_nm].filter(Boolean).join(" ");
  return escapeHtml(shortAddress || item.address || "-");
}

function dataLabTransactionMeta(item, date){
  const dateText = date ? ` · ${escapeHtml(date)}` : "";
  return `${dataLabSimpleAddress(item)}${dateText}`;
}

function dataLabBuildingButton(item){
  const name = escapeHtml(item.building_name || "건물명 미확인");
  const buildingId = Number(item.building_id);
  const lat = Number(item.lat);
  const lng = Number(item.lng);
  const hasCoordinates = Number.isFinite(lat) && Number.isFinite(lng);
  if (!Number.isInteger(buildingId) || buildingId <= 0 || !hasCoordinates) {
    return `<span class="datalab-building datalab-building-disabled" title="${name} — 지도 좌표 없음">${name}</span>`;
  }
  const selected = selectedDataLabBuilding && selectedDataLabBuilding.id === buildingId;
  return `<button type="button" class="datalab-building${selected ? " datalab-building-selected" : ""}" data-datalab-building="${buildingId}" data-datalab-lat="${lat}" data-datalab-lng="${lng}" aria-pressed="${selected}" title="지도에서 ${name} 위치 보기">${name}</button>`;
}

function moveDataLabBuildingToMap(button){
  if (!kakaoMap) return;
  const buildingId = Number(button.dataset.datalabBuilding);
  const lat = Number(button.dataset.datalabLat);
  const lng = Number(button.dataset.datalabLng);
  if (!Number.isInteger(buildingId) || buildingId <= 0 ||
      !Number.isFinite(lat) || !Number.isFinite(lng)) return;
  showDataLabBuildingHighlight({
    id: buildingId,
    name: button.textContent.trim() || "건물명 미확인",
    lat,
    lng,
  });
  const position = new kakao.maps.LatLng(lat, lng);
  kakaoMap.setCenter(position);
  kakaoMap.setLevel(3);
  updateMapForZoom(mapFiltersFromState(), { force: true });
}

function bindDataLabBuildingButtons(box){
  box.querySelectorAll("[data-datalab-building]").forEach(button => {
    button.addEventListener("click", () => {
      moveDataLabBuildingToMap(button);
      _syncDataLabBuildingSelection();
    });
  });
}

function dataLabRankList(items, makeMeta, makeValue){
  if (!items.length) return '<div class="side-empty">표시할 데이터가 없습니다.</div>';
  return `<div class="datalab-list">${items.map((item, index) => `
    <div class="datalab-list-item">
      <span class="datalab-rank">${index + 1}</span>
      <div style="min-width:0;">
        ${dataLabBuildingButton(item)}
        <div class="datalab-meta">${makeMeta(item)}</div>
      </div>
      <span class="datalab-value">${makeValue(item)}</span>
    </div>`).join("")}</div>`;
}

function renderDataLabLodging(data){
  const rows = Array.isArray(data.rows) ? data.rows : [];
  if (!rows.length) return '<div class="side-empty">전국 숙박업 통계가 없습니다.</div>';
  const roomRateTypes = new Set(["생활"]);
  const buildingCoverageTypes = new Set(["관광", "에어비앤비", "농어촌민박", "캠핑", "한옥", "복합"]);
  const rateTitle = row => {
    if (row.type === "일반") return "현재 영업신고업체 수 ÷ 일반 건물 수";
    if (roomRateTypes.has(row.type)) return "정상영업 신고객실수 ÷ 건축물대장 호실수";
    if (buildingCoverageTypes.has(row.type)) return `활성 신고가 매칭된 건물 수 ÷ ${row.type} 건물 수`;
    return "유형별 모집단에 맞춘 신고 커버리지";
  };
  const body = rows.map(row => {
    const campingTypes = row.camping_classification_breakdown || {};
    const campingMixedCount = Number(campingTypes.confirmed_mixed || 0) + Number(campingTypes.unknown || 0);
    const campingSubRows = row.type === "캠핑"
      ? [
          ["일반야영", campingTypes.general_only, row.camping_general_site_count],
          ["자동차야영", campingTypes.auto_only, row.camping_auto_site_count],
          ["글램핑", campingTypes.glamping_only, row.camping_glamping_site_count],
          ["카라반", campingTypes.caravan_only, row.camping_caravan_site_count],
          ["복합", campingMixedCount, null],
        ].map(([type, facilityCount, siteCount]) => `
          <tr class="datalab-sub-row">
            <td class="datalab-sub-name">${escapeHtml(type)}</td>
            <td>${dataLabNum(facilityCount)}</td>
            <td>${siteCount == null ? "-" : dataLabNum(siteCount)}</td>
            <td>-</td>
            <td>-</td>
            <td>-</td>
          </tr>`).join("")
      : "";
    const displayedBuildingCount = row.type === "캠핑"
      ? row.camping_facility_count
      : row.building_count;
    const displayedUnits = row.type === "캠핑"
      ? row.camping_site_count
      : row.units;
    const base = `
      <tr>
        <td>${escapeHtml(row.type)}</td>
        <td>${dataLabNum(displayedBuildingCount)}</td>
        <td>${dataLabNum(displayedUnits)}</td>
        <td>${dataLabNum(row.biz_count)}</td>
        <td>${dataLabNum(row.room_count)}</td>
        <td title="${rateTitle(row)}">${row.report_rate == null ? "-" : `${row.report_rate}%`}</td>
      </tr>`;
    const subRows = (row.sub_rows || []).map(sub => `
      <tr class="datalab-sub-row">
        <td class="datalab-sub-name">${escapeHtml(sub.type)}</td>
        <td>${dataLabNum(sub.building_count)}</td>
        <td>-</td>
        <td>${dataLabNum(sub.biz_count)}</td>
        <td>${dataLabNum(sub.room_count)}</td>
        <td>${sub.report_rate == null ? "-" : `${sub.report_rate}%`}</td>
      </tr>`).join("");
    return base + campingSubRows + subRows;
  }).join("");
  return `
    <div class="datalab-heading">
      <strong>① 전국숙박업통계</strong><span class="datalab-caption">현재수집 기준</span>
    </div>
    <div class="datalab-table-wrap">
      <table class="datalab-table">
        <thead><tr><th>구분</th><th>건물수(시설수)</th><th title="건축물대장 표제부 hoCnt 합계입니다. 생활 외 유형은 신고객실수와 직접 비교하지 않습니다.">호실수(사이트수)</th><th>신고업체</th><th>신고객실수(사이트수)</th><th title="생활은 객실 기준, 일반은 업체 기준, 관광·에어비앤비·농어촌민박·캠핑·한옥·복합은 건물 커버리지 기준입니다.">신고율</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function renderDataLabVolume(data){
  const items = Array.isArray(data.most_traded) ? data.most_traded : [];
  return `
    <div class="datalab-heading">
      <strong>② 🔥 거래량 TOP</strong><span class="datalab-caption">최근 7일 실거래</span>
    </div>
    ${dataLabRankList(
      items,
      item => dataLabTransactionMeta(item, item.latest_date),
      item => `${dataLabNum(item.deal_count)}건`
    )}`;
}

function renderDataLabChange(data){
  const direction = data.direction === "down" ? "down" : "up";
  const items = Array.isArray(data.items) ? data.items : [];
  const label = direction === "up" ? "상승" : "하락";
  return `
    <div class="datalab-heading">
      <strong>③ 📊 가격변동 TOP</strong><span class="datalab-caption">최근 30일 · 2건 이상</span>
    </div>
    <div class="datalab-toolbar">
      <span class="datalab-caption">${label}률 기준</span>
      <span class="datalab-toggle">
        <button type="button" data-datalab-direction="up" class="${direction === "up" ? "active" : ""}">상승</button>
        <button type="button" data-datalab-direction="down" class="${direction === "down" ? "active" : ""}">하락</button>
      </span>
    </div>
    ${dataLabRankList(
      items,
      item => `${dataLabTransactionMeta(item, item.latest_deal_date)} · ${dataLabArea(item.area_sqm)}`,
      item => `${item.change_percent > 0 ? "+" : ""}${item.change_percent}%`
    )}`;
}

function renderDataLabHighest(data){
  const order = data.order === "lowest" ? "lowest" : "highest";
  const items = Array.isArray(data.items) ? data.items : [];
  const label = order === "highest" ? "최고가" : "최저가";
  return `
    <div class="datalab-heading">
      <strong>④ 💰 ${label} 건물 TOP</strong><span class="datalab-caption">역대 ${label} 거래가</span>
    </div>
    <div class="datalab-toolbar">
      <span class="datalab-caption">${label} 기준</span>
      <span class="datalab-toggle">
        <button type="button" data-datalab-price-order="highest" class="${order === "highest" ? "active" : ""}">최고</button>
        <button type="button" data-datalab-price-order="lowest" class="${order === "lowest" ? "active" : ""}">최저</button>
      </span>
    </div>
    ${dataLabRankList(
      items,
      item => dataLabTransactionMeta(item, item.deal_date),
      item => `${dataLabNum(item.price)}만원`
    )}`;
}

function renderDataLabClosure(data){
  const items = Array.isArray(data.items) ? data.items : [];
  if (!items.length) {
    return '<div class="side-empty">표본 5건 이상인 지역 데이터가 없습니다.</div>';
  }
  return `
    <div class="datalab-heading">
      <strong>⑥ ⚫ 폐업 현황</strong><span class="datalab-caption">시군구 · 표본 5건 이상</span>
    </div>
    <div class="datalab-list">${items.map((item, index) => `
      <div class="datalab-list-item">
        <span class="datalab-rank">${index + 1}</span>
        <div style="min-width:0;">
          <span class="datalab-region">${escapeHtml(item.region)}</span>
          <div class="datalab-meta">전체 ${dataLabNum(item.total_count)}개 중 ${dataLabNum(item.closed_count)}개 폐업</div>
        </div>
        <span class="datalab-value">${item.closure_rate}%</span>
       </div>`).join("")}</div>`;
}

function renderDataLabConsign(data){
  const items = Array.isArray(data.items) ? data.items : [];
  const total = data && data.total && typeof data.total === "object" ? data.total : null;
  if (!items.length || !total) return '<div class="side-empty">영업신고현황 데이터가 없습니다.</div>';
  const partialBadge = data.is_partial === true
    ? '<span class="datalab-partial-badge">수집중</span>'
    : "";
  const renderRate = value => value == null
    ? "-"
    : `<strong class="datalab-consign-rate">${Number(value).toFixed(1)}%</strong>`;
  const renderRow = (item, label) => `
    <tr>
      <td>${escapeHtml(label)}</td>
      <td>${dataLabNum(item.building_cnt)}</td>
      <td>${dataLabNum(item.total_units)}</td>
      <td>${dataLabNum(item.active_biz_cnt)}</td>
      <td>${dataLabNum(item.active_room_cnt)}</td>
      <td>${renderRate(item.report_rate)}</td>
    </tr>`;
  return `
    <div class="datalab-heading">
      <div class="datalab-heading-main"><strong>⑤ 📋 생활숙박시설 영업신고현황</strong>${partialBadge}</div>
    </div>
    <div class="datalab-table-wrap">
      <table class="datalab-table datalab-consign-table">
        <thead><tr><th>시도</th><th>건물수</th><th>호실수</th><th>신고업체</th><th>신고호실</th><th>신고율</th></tr></thead>
        <tbody>${items.map(item => renderRow(item, item.sido || "-")).join("")}</tbody>
        <tfoot>${renderRow(total, "합계")}</tfoot>
      </table>
    </div>`;
}

function setDataLabActive(key){
  dataLabActiveKey = key;
  document.querySelectorAll("[data-datalab-key]").forEach(button => {
    const active = button.dataset.datalabKey === key;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (dataLabConsignRefreshTimer) {
    clearInterval(dataLabConsignRefreshTimer);
    dataLabConsignRefreshTimer = null;
  }
  if (key === "consign") {
    dataLabConsignRefreshTimer = setInterval(() => {
      if (document.visibilityState === "visible" && !dataLabFetchController) {
        // 수집 완료 뒤 서버 무효화는 브라우저 Map을 직접 비우지 못하므로,
        // 열린 탭의 30초 폴링은 공통 TTL을 우회해 새 stale 응답을 받아온다.
        loadDataLab("consign", "up", { background: true, forceRefresh: true });
      }
    }, DATA_LAB_CONSIGN_REFRESH_MS);
  }
}

function setDataLabTabLoading(key, loading, requestId){
  const button = document.querySelector(`[data-datalab-key="${key}"]`);
  if (!button) return;
  if (loading) {
    button.dataset.datalabLoadingRequest = String(requestId);
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    return;
  }
  if (
    requestId != null &&
    button.dataset.datalabLoadingRequest !== String(requestId)
  ) return;
  delete button.dataset.datalabLoadingRequest;
  button.classList.remove("is-loading");
  button.setAttribute("aria-busy", "false");
}

function dataLabLoadingHTML(){
  return `<div class="datalab-loading" role="status">
    <span class="datalab-spinner" aria-hidden="true"></span>
    <span>데이터를 불러오는 중입니다…</span>
    <div class="datalab-skeletons" aria-hidden="true"><i></i><i></i><i></i></div>
  </div>`;
}

function dataLabErrorHTML(){
  return `<div class="datalab-error">
    <span>데이터를 불러오지 못했습니다.</span>
    <button type="button" data-datalab-retry>다시 시도</button>
  </div>`;
}

function bindDataLabControls(content){
  bindDataLabBuildingButtons(content);
  content.querySelectorAll("[data-datalab-direction]").forEach(button => {
    button.addEventListener("click", () => loadDataLab("change", button.dataset.datalabDirection));
  });
  content.querySelectorAll("[data-datalab-price-order]").forEach(button => {
    button.addEventListener("click", () => loadDataLab("highest", button.dataset.datalabPriceOrder));
  });
}

async function loadDataLab(key, option = "up", {
  background = false,
  forceRefresh = false,
} = {}){
  const content = document.getElementById("dataLabContent");
  if (!content) return;
  const requestId = ++dataLabRequestSequence;
  setDataLabActive(key);
  const urls = {
    lodging: "/api/v1/d/3f7",
    volume: "/api/ranking",
    change: `/api/stats/price-change-top?direction=${encodeURIComponent(option)}`,
    highest: `/api/stats/highest-price-top?order=${encodeURIComponent(option === "lowest" ? "lowest" : "highest")}`,
    closure: "/api/stats/closure-rate-by-region",
    consign: "/api/stats/consign-by-sido",
  };
  const url = urls[key];
  if (!url) return;
  const cacheKey = `${key}:${option}`;
  const cached = dataLabResponseCache.get(cacheKey);
  // 모든 데이터랩 탭은 같은 브라우저 TTL을 사용한다. 다만 열린 영업신고
  // 탭의 30초 폴링은 forceRefresh로 서버 stale 재검증 결과를 받아온다.
  const cacheTtl = DATA_LAB_CACHE_TTL_MS;
  const renders = {
    lodging: renderDataLabLodging,
    volume: renderDataLabVolume,
    change: renderDataLabChange,
    highest: renderDataLabHighest,
    closure: renderDataLabClosure,
    consign: renderDataLabConsign,
  };
  if (!forceRefresh && cached && Date.now() - cached.ts < cacheTtl) {
    content.innerHTML = renders[key](cached.data);
    bindDataLabControls(content);
    return;
  }
  if (dataLabFetchController) dataLabFetchController.abort();
  const controller = new AbortController();
  dataLabFetchController = controller;
  setDataLabTabLoading(key, true, requestId);
  const contentIsEmpty = !content.textContent.trim();
  if (!background && contentIsEmpty) content.innerHTML = dataLabLoadingHTML();
  try {
    const response = await fetch(url, { signal: controller.signal });
    const data = await response.json();
    if (requestId !== dataLabRequestSequence) return;
    if (!response.ok || !data.ok) throw new Error("datalab request failed");
    dataLabResponseCache.set(cacheKey, { ts: Date.now(), data });
    content.innerHTML = renders[key](data);
    bindDataLabControls(content);
  } catch (error) {
    if (error.name === "AbortError") return;
    if (requestId !== dataLabRequestSequence) return;
    if (!background && contentIsEmpty) {
      content.innerHTML = dataLabErrorHTML();
      content.querySelector("[data-datalab-retry]")?.addEventListener("click", () => loadDataLab(key, option));
    }
    console.error("[데이터랩] 로드 실패:", error);
  } finally {
    if (dataLabFetchController === controller) {
      dataLabFetchController = null;
      setDataLabTabLoading(key, false, requestId);
    } else {
      setDataLabTabLoading(key, false, requestId);
    }
  }
}

function initDataLab(){
  const nav = document.getElementById("dataLabNav");
  if (!nav) return;
  nav.querySelectorAll("[data-datalab-key]").forEach(button => {
    button.addEventListener("click", () => loadDataLab(button.dataset.datalabKey));
  });
  loadDataLab("lodging");
}

function initDefaultSidePanel(){
  loadTrendChart();
  loadSideTx(5);
  initDataLab();
  renderRecentChips(); // 페이지 로드 시 최근 본 건물 칩 복원
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
function legacyOpenListingRequestModal(buildingId, buildingName){
  document.getElementById("listingReqOverlay")?.remove();
  const ov = document.createElement("div");
  ov.id = "listingReqOverlay";
  ov.style.cssText = "position:fixed; inset:0; background:rgba(22,32,46,.45); z-index:3000; display:flex; align-items:center; justify-content:center; padding:16px;";
  const FLD = "width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font-size:13.5px; font-family:inherit;";
  const DEFAULT_DEAL_MODE = "direct";
  ov.innerHTML = `
    <div style="background:#fff; border-radius:14px; width:100%; max-width:400px; padding:22px 20px; box-shadow:0 10px 40px rgba(0,0,0,.2); max-height:90vh; overflow-y:auto;" role="dialog" aria-modal="true">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
        <div style="font-size:16px; font-weight:800; color:var(--ink);">매물 내놓기</div>
        <button id="lrClose" style="background:none; border:none; font-size:20px; cursor:pointer; color:var(--ink-soft);" aria-label="닫기">×</button>
      </div>
      <div style="font-size:12.5px; color:var(--ink-soft); margin-bottom:14px;">${escapeHtml(buildingName)}</div>
      <div id="lrForm">
        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">의뢰인</div>
        <input id="lrName" type="text" readonly value="" placeholder="로그인 정보에서 자동 표시" style="${FLD} margin-bottom:12px; background:#F6F5F2; color:var(--ink-soft);" />

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">진행방식</div>
        <div style="display:flex; gap:6px; margin-bottom:10px;">
          <button type="button" id="lrModeDirect" class="side-more" style="flex:1; margin-top:0; padding:8px 0; background:var(--brass); color:#fff; border-color:var(--brass);">직거래</button>
          <button type="button" id="lrModeBroker" class="side-more" style="flex:1; margin-top:0; padding:8px 0;">중개사연결</button>
        </div>
        <div id="lrDirectNotice" style="font-size:11.5px; color:#7D4A00; background:#FFF7E6; border:1px solid #FFD898; border-radius:8px; padding:9px 11px; margin-bottom:12px; line-height:1.6;">
          <strong>직거래 공개 매물</strong>로 등록됩니다.<br>
          매물 내용과 채팅창이 건물 상세 페이지에 공개됩니다.
        </div>
        <div id="lrBrokerNotice" style="display:none; font-size:11.5px; color:var(--ink-soft); background:#F4F1EA; border-radius:8px; padding:9px 11px; margin-bottom:12px; line-height:1.6;">
          담당 중개사에게 배정되어 상담 연락을 드립니다.
        </div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">거래유형</div>
        <div id="lrDealTypes" style="display:flex; gap:6px; margin-bottom:12px;">
          ${["매매","전세","월세","단기임대"].map((t,i) => `<button type="button" data-dt="${t}" class="side-more" style="flex:1; margin-top:0; padding:8px 0; ${i===0 ? "background:var(--brass); color:#fff; border-color:var(--brass);" : ""}">${t}</button>`).join("")}
        </div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">전용면적 <span style="font-weight:400; color:var(--ink-soft);">(㎡, 선택)</span></div>
        <div id="lrAreaWrap" style="margin-bottom:12px;">
          <select id="lrAreaSelect" style="${FLD}">
            <option value="">불러오는 중…</option>
          </select>
          <input id="lrAreaSqm" type="number" min="1" max="9999" step="0.01" inputmode="decimal" placeholder="예) 46.28" style="${FLD} display:none; margin-top:6px;" />
        </div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">상세주소 <span style="font-weight:400; color:var(--ink-soft);">(선택 — 비공개)</span></div>
        <div style="display:flex; gap:6px; margin-bottom:4px;">
          <input id="lrDong" type="text" maxlength="20" placeholder="동" style="${FLD} flex:1;" />
          <input id="lrHo" type="text" maxlength="20" placeholder="호" style="${FLD} flex:1;" />
        </div>
        <div style="font-size:11px; color:var(--ink-soft); margin-bottom:12px; line-height:1.5;">동/호는 지도·매물목록에 공개되지 않으며, 추후 안전거래 확인 목적으로만 활용됩니다.</div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">등록자 정보</div>
        <select id="lrRegistrantType" style="${FLD} margin-bottom:12px;">
          <option value="owner">소유자 본인</option>
          <option value="agent">위임 대리인</option>
          <option value="other">기타</option>
        </select>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">희망가 <span style="font-weight:400; color:var(--ink-soft);">(선택)</span></div>
        <div id="lrPriceSale">
          <input id="lrSalePrice" type="number" min="1" max="1000000" inputmode="numeric" placeholder="매매가 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="lrPriceJeonse" style="display:none;">
          <input id="lrJeonseDeposit" type="number" min="1" max="1000000" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} margin-bottom:12px;" />
        </div>
        <div id="lrPriceWolse" style="display:none; gap:6px; margin-bottom:12px;">
          <input id="lrWolseDeposit" type="number" min="1" max="1000000" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} flex:1;" />
          <input id="lrWolseRent" type="number" min="1" max="1000000" inputmode="numeric" placeholder="월세 (만원)" style="${FLD} flex:1;" />
        </div>
        <div id="lrPriceShort" style="display:none;">
          <input id="lrShortPrice" type="text" maxlength="100" placeholder="예) 1박 8만원 / 주 단위 협의" style="${FLD} margin-bottom:12px;" />
        </div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">수익률 계산 <span style="font-weight:400; color:var(--ink-soft);">(선택, 참고용)</span></div>
        <div style="display:flex; gap:6px; margin-bottom:4px;">
          <input id="lrYieldDeposit" type="number" min="0" max="1000000" inputmode="numeric" placeholder="보증금 (만원)" style="${FLD} flex:1;" />
          <input id="lrYieldRent" type="number" min="1" max="100000" inputmode="numeric" placeholder="월세 (만원)" style="${FLD} flex:1;" />
        </div>
        <div id="lrYieldResult" style="font-size:12.5px; font-weight:700; color:var(--brass-dark,#7D4A00); min-height:18px; margin-bottom:2px;"></div>
        <div style="font-size:10.5px; color:var(--ink-soft); margin-bottom:12px; line-height:1.4;">관리비·공실률 미반영, 참고용 수치입니다. (월세×12 ÷ (매매가−보증금) × 100)</div>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">물건설명 <span style="font-weight:400; color:var(--ink-soft);">(선택, 최대 500자)</span></div>
        <textarea id="lrDesc" maxlength="500" rows="3" placeholder="역세권, 채광, 층수 등 특징을 간단히 적어주세요" style="${FLD} margin-bottom:12px; resize:vertical; min-height:64px;"></textarea>

        <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">사진 첨부 <span style="font-weight:400; color:var(--ink-soft);">(선택, 최대 5장 · 장당 5MB 이하)</span></div>
        <input id="lrPhotos" type="file" accept=".jpg,.jpeg,.png" multiple style="width:100%; font-size:12.5px; margin-bottom:4px; box-sizing:border-box;" />
        <div id="lrPhotosMsg" style="font-size:11.5px; color:var(--brick,#cc3300); min-height:14px; margin-bottom:4px;"></div>
        <div id="lrPhotosPreviews" style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px;"></div>

        <div id="lrPhoneSection">
          <div id="lrPhoneDirectWrap">
            <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">연락처 <span style="font-weight:400; color:var(--ink-soft);">(직거래 — 휴대폰 인증 필요)</span></div>
            <div id="lrPhoneVerified" style="display:none; margin-bottom:10px;">
              <div style="display:flex; align-items:center; gap:8px; padding:9px 11px; background:#F0FBF4; border:1px solid #B7E0C4; border-radius:8px;">
                <span id="lrPhoneVerifiedNum" style="font-size:14px; font-weight:700; color:var(--ink); flex:1;"></span>
                <span style="font-size:11.5px; color:#1a7a3c; font-weight:700; white-space:nowrap;">✓ 인증</span>
              </div>
              <button type="button" id="lrChangePhone" style="margin-top:5px; font-size:11.5px; color:var(--brass); background:none; border:none; cursor:pointer; padding:0; text-decoration:underline;">다른 번호로 변경</button>
            </div>
            <div id="lrPhoneInputWrap" style="margin-bottom:10px;">
              <input id="lrPhone" type="tel" maxlength="13" placeholder="010-1234-5678" style="${FLD} margin-bottom:6px;" />
              <div style="display:flex; gap:6px; margin-bottom:6px;">
                <input id="lrPhoneCode" type="text" inputmode="numeric" maxlength="6" placeholder="인증번호 6자리" style="${FLD} flex:1; min-width:90px; font-size:16px;" />
                <button type="button" id="lrSendCode" class="side-more" style="white-space:nowrap; margin-top:0; padding:8px 10px; flex-shrink:0; font-size:12.5px;">인증번호 받기</button>
              </div>
              <button type="button" id="lrVerifyCode" class="btn-search" style="width:100%; padding:9px; display:none; font-size:13px;">인증 확인</button>
            </div>
          </div>
          <div id="lrPhoneBrokerWrap" style="display:none;">
            <div style="font-size:12px; font-weight:700; color:var(--ink); margin-bottom:5px;">연락처</div>
            <input id="lrBrokerPhone" type="tel" maxlength="13" placeholder="010-1234-5678" style="${FLD} margin-bottom:10px;" />
          </div>
        </div>

        <div id="lrMsg" style="font-size:12px; min-height:16px; margin-top:4px;"></div>
        <button id="lrSubmit" class="btn-search" style="width:100%; padding:12px; margin-top:8px;">매물의뢰 접수하기</button>
        <div id="lrNoticeBox" style="font-size:11.5px; color:var(--ink-soft); line-height:1.7; margin-top:10px; padding:10px 12px; background:#F4F1EA; border-radius:8px;"></div>
      </div>
      <div id="lrDone" style="display:none; text-align:center; padding:18px 4px;">
        <div style="font-size:34px; margin-bottom:10px;">✅</div>
        <div id="lrDoneTitle" style="font-size:14.5px; font-weight:700; color:var(--ink); margin-bottom:6px;"></div>
        <div id="lrDoneDesc" style="font-size:12.5px; color:var(--ink-soft); line-height:1.6;"></div>
        <button id="lrDoneClose" class="side-more" style="width:auto; padding:8px 22px; margin-top:14px;">닫기</button>
      </div>
    </div>`;
  document.body.appendChild(ov);

  // —— 상태 변수
  let dealMode = DEFAULT_DEAL_MODE;  // 'direct' | 'broker'
  let dealType = "매매";
  let phoneVerified = false;
  let verifiedPhone = "";

  const PRICE_BOXES = { "매매": "lrPriceSale", "전세": "lrPriceJeonse", "월세": "lrPriceWolse", "단기임대": "lrPriceShort" };
  const _CAUTION = `<div style="font-weight:700; color:var(--ink); margin-bottom:5px; margin-top:10px;">[매물등록 유의사항]</div>` +
    `- 상세주소(동/호)는 공개되지 않으며, 추후 안전거래 확인(소유자 인증) 목적으로만 활용됩니다.<br>` +
    `- 동/호 정보가 정확하지 않으면 추후 안전거래 인증 절차에서 매물이 제외될 수 있습니다.<br>` +
    `- 이미 계약이 완료됐거나 존재하지 않는 매물을 등록하면 서비스 이용이 제한될 수 있습니다.`;
  const NOTICES = {
    direct: `<div style="font-weight:700; color:var(--ink); margin-bottom:6px;">[직거래 안내]</div>` +
      `-홈앤스테이는 중개행위에 관여하지 않으며 중개수수료를 받지 않습니다.<br>` +
      `-직거래 시 발생하는 법적 분쟁은 당사자 간 책임입니다. 고가 거래는 전문 중개사를 이용하시길 권장합니다.` +
      _CAUTION,
    broker: `<div style="font-weight:700; color:var(--ink); margin-bottom:6px;">[공지사항]</div>` +
      `-매물의뢰는 단지부동산, 지역부동산 순으로 자동으로 순차배정되며 배정된 부동산에서 중개상담차 전화를 연결할 수 있습니다.<br><br>` +
      `-홈앤스테이는 부동산중개사무소가 아니며 중개행위에 관여하지 않고, 중개수수료를 받지 않습니다.<br><br>` +
      `-"매물의뢰"는 매물내놓기 무료서비스이며, 중개의뢰는 배정된 중개사를 통하여 별도로 상담을 진행하여 주시기 바랍니다.`,
  };

  function setMsgColor(ok){ ov.querySelector("#lrMsg").style.color = ok ? "#1a7a3c" : "var(--brick)"; }
  function setMsg(text, ok = false){ setMsgColor(ok); ov.querySelector("#lrMsg").textContent = text; }

  function applyDealMode(mode){
    dealMode = mode;
    const isDirect = mode === "direct";
    // 진행방식 버튼 토글
    const btnD = ov.querySelector("#lrModeDirect"), btnB = ov.querySelector("#lrModeBroker");
    btnD.style.background = isDirect ? "var(--brass)" : ""; btnD.style.color = isDirect ? "#fff" : ""; btnD.style.borderColor = isDirect ? "var(--brass)" : "";
    btnB.style.background = !isDirect ? "var(--brass)" : ""; btnB.style.color = !isDirect ? "#fff" : ""; btnB.style.borderColor = !isDirect ? "var(--brass)" : "";
    // 공지 토글
    ov.querySelector("#lrDirectNotice").style.display = isDirect ? "block" : "none";
    ov.querySelector("#lrBrokerNotice").style.display = !isDirect ? "block" : "none";
    // 연락처 UI
    ov.querySelector("#lrPhoneDirectWrap").style.display = isDirect ? "block" : "none";
    ov.querySelector("#lrPhoneBrokerWrap").style.display = !isDirect ? "block" : "none";
    if (isDirect) {
      ov.querySelector("#lrPhoneVerified").style.display = phoneVerified ? "block" : "none";
      ov.querySelector("#lrPhoneInputWrap").style.display = phoneVerified ? "none" : "block";
    }
    ov.querySelector("#lrNoticeBox").innerHTML = NOTICES[mode];
  }

  function showPriceBox(){
    Object.entries(PRICE_BOXES).forEach(([dt, id]) => {
      const el = ov.querySelector("#" + id);
      el.style.display = (dt === dealType) ? (dt === "월세" ? "flex" : "block") : "none";
    });
  }

  // —— 로그인 정보 자동 채움 (이름 + 인증된 전화번호)
  fetch("/api/auth/me", { credentials: "same-origin" })
    .then((r) => r.json())
    .then((d) => {
      if (!d || !d.logged_in) return;
      if (d.name) ov.querySelector("#lrName").value = d.name;
      if (d.phone_verified && d.phone) {
        phoneVerified = true;
        verifiedPhone = d.phone;
        ov.querySelector("#lrPhoneVerifiedNum").textContent = d.phone;
        applyDealMode(dealMode);  // 인증 상태 반영
      }
    })
    .catch(() => {});

  // —— 전유부 API → 전용면적 콤보 채우기 (buildingId가 있을 때만)
  if (buildingId) {
    fetch(`/api/building/${buildingId}/area-types`, { credentials: "same-origin" })
      .then(r => r.json()).catch(() => ({}))
      .then(d => {
        const areaSelectEl = ov.querySelector("#lrAreaSelect");
        if (!areaSelectEl) return;
        const sqms = (d.items || []).map(it => it.sqm);
        if (sqms.length > 0) {
          areaSelectEl.innerHTML =
            sqms.map(v => `<option value="${v}">${v}㎡</option>`).join("") +
            `<option value="__manual__">직접입력</option>`;
        } else {
          // 전유부 데이터 없음 → 직접입력만
          areaSelectEl.innerHTML = `<option value="__manual__">직접입력</option>`;
        }
        // 직접입력 선택 시 수동 입력창 표시
        areaSelectEl.addEventListener("change", () => {
          const manualInput = ov.querySelector("#lrAreaSqm");
          if (!manualInput) return;
          if (areaSelectEl.value === "__manual__") {
            manualInput.style.display = "";
            manualInput.focus();
          } else {
            manualInput.style.display = "none";
          }
        });
      });
  } else {
    // 건물 없이 모달 열림 → 직접입력만
    const areaSelectEl = ov.querySelector("#lrAreaSelect");
    if (areaSelectEl) {
      areaSelectEl.innerHTML = `<option value="__manual__">직접입력</option>`;
      areaSelectEl.addEventListener("change", () => {
        const manualInput = ov.querySelector("#lrAreaSqm");
        if (manualInput) manualInput.style.display = areaSelectEl.value === "__manual__" ? "" : "none";
      });
    }
  }

  // 초기 렌더
  applyDealMode(DEFAULT_DEAL_MODE);
  showPriceBox();

  // 수익률 실시간 계산 (매매가, 보증금, 월세 입력 시 갱신)
  function _calcYield(){
    const price = parseFloat(ov.querySelector("#lrSalePrice")?.value) || 0;
    const dep   = parseFloat(ov.querySelector("#lrYieldDeposit")?.value) || 0;
    const rent  = parseFloat(ov.querySelector("#lrYieldRent")?.value) || 0;
    const disp  = ov.querySelector("#lrYieldResult");
    if (!disp) return;
    const denom = price - dep;
    disp.textContent = (denom > 0 && rent > 0)
      ? `수익률 ${((rent * 12) / denom * 100).toFixed(1)}%`
      : "";
  }
  ["lrSalePrice","lrYieldDeposit","lrYieldRent"].forEach(id => {
    ov.querySelector("#" + id)?.addEventListener("input", _calcYield);
  });

  // 사진 미리보기 & 유효성 검사
  ov.querySelector("#lrPhotos")?.addEventListener("change", function(){
    const prev = ov.querySelector("#lrPhotosPreviews");
    const msg  = ov.querySelector("#lrPhotosMsg");
    const files = Array.from(this.files || []);
    if (files.length > 5){
      if (msg) msg.textContent = "최대 5장까지 첨부 가능합니다.";
      this.value = ""; if (prev) prev.innerHTML = ""; return;
    }
    if (files.some(f => f.size > 5 * 1024 * 1024)){
      if (msg) msg.textContent = "각 파일은 5MB 이하여야 합니다.";
      this.value = ""; if (prev) prev.innerHTML = ""; return;
    }
    if (msg) msg.textContent = "";
    if (prev) prev.innerHTML = "";
    files.forEach(file => {
      const r = new FileReader();
      r.onload = (e) => {
        const img = document.createElement("img");
        img.src = e.target.result;
        img.style.cssText = "width:56px;height:56px;object-fit:cover;border-radius:6px;border:1px solid var(--line,#eee);";
        if (prev) prev.appendChild(img);
      };
      r.readAsDataURL(file);
    });
  });

  // —— 이벤트 바인딩
  ov.querySelector("#lrModeDirect").addEventListener("click", () => applyDealMode("direct"));
  ov.querySelector("#lrModeBroker").addEventListener("click", () => applyDealMode("broker"));

  ov.querySelectorAll("#lrDealTypes button").forEach((b) => {
    b.addEventListener("click", () => {
      dealType = b.dataset.dt;
      showPriceBox();
      ov.querySelectorAll("#lrDealTypes button").forEach((x) => {
        const on = x === b;
        x.style.background = on ? "var(--brass)" : ""; x.style.color = on ? "#fff" : ""; x.style.borderColor = on ? "var(--brass)" : "";
      });
    });
  });

  ov.querySelector("#lrChangePhone").addEventListener("click", () => {
    phoneVerified = false; verifiedPhone = "";
    ov.querySelector("#lrPhoneVerified").style.display = "none";
    ov.querySelector("#lrPhoneInputWrap").style.display = "block";
    ov.querySelector("#lrMsg").textContent = "";
  });

  // 인증번호 받기
  ov.querySelector("#lrSendCode").addEventListener("click", async () => {
    const phoneRaw = ov.querySelector("#lrPhone").value.trim();
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phoneRaw)){
      setMsg("휴대폰 번호 형식이 올바르지 않습니다. 예) 010-1234-5678"); return;
    }
    setMsg(""); const btn = ov.querySelector("#lrSendCode");
    btn.disabled = true; btn.textContent = "발송 중…";
    try {
      const res = await fetch("/api/auth/send-phone-code", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: phoneRaw }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.ok === false){ setMsg(d.message || "발송에 실패했습니다."); btn.disabled = false; btn.textContent = "인증번호 받기"; return; }
      ov.querySelector("#lrVerifyCode").style.display = "block";
      setMsg(d.sent ? "인증번호를 발송했습니다. (3분 이내 입력)" : `[개발환경] 인증번호: ${d.dev_code}`, true);
      btn.textContent = "재발송"; btn.disabled = false;
    } catch(e){
      setMsg("네트워크 오류가 발생했습니다."); btn.disabled = false; btn.textContent = "인증번호 받기";
    }
  });

  // 인증 확인
  ov.querySelector("#lrVerifyCode").addEventListener("click", async () => {
    const code = ov.querySelector("#lrPhoneCode").value.trim();
    if (!code){ setMsg("인증번호를 입력해주세요."); return; }
    setMsg(""); const btn = ov.querySelector("#lrVerifyCode");
    btn.disabled = true; btn.textContent = "확인 중…";
    try {
      const res = await fetch("/api/auth/verify-phone-code", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.ok === false){ setMsg(d.message || "인증에 실패했습니다."); btn.disabled = false; btn.textContent = "인증 확인"; return; }
      phoneVerified = true; verifiedPhone = d.phone;
      ov.querySelector("#lrPhoneVerifiedNum").textContent = d.phone;
      ov.querySelector("#lrPhoneVerified").style.display = "block";
      ov.querySelector("#lrPhoneInputWrap").style.display = "none";
      setMsg("✓ 휴대폰 인증이 완료됐습니다.", true);
    } catch(e){
      setMsg("네트워크 오류가 발생했습니다."); btn.disabled = false; btn.textContent = "인증 확인";
    }
  });

  const close = () => ov.remove();
  ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  ov.querySelector("#lrClose").addEventListener("click", close);
  ov.querySelector("#lrDoneClose").addEventListener("click", close);

  // —— 접수 제출
  ov.querySelector("#lrSubmit").addEventListener("click", async () => {
    setMsgColor(false);
    if (dealMode === "direct" && !phoneVerified){
      setMsg("직거래 매물은 휴대폰 인증이 필요합니다."); return;
    }
    let contactPhone = "";
    if (dealMode === "broker"){
      contactPhone = ov.querySelector("#lrBrokerPhone").value.trim();
      if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(contactPhone)){
        setMsg("연락처 형식이 올바르지 않습니다. 예) 010-1234-5678"); return;
      }
    }
    const _MAX_PRICE = 1_000_000; // 100억 만원 (만원 단위)
    let _priceOver = false;
    const numVal = (id) => {
      const v = parseInt(ov.querySelector("#" + id).value, 10);
      if (!Number.isFinite(v) || v <= 0) return null;
      if (v > _MAX_PRICE) { _priceOver = true; return null; }
      return v;
    };
    const fmt = (n) => n.toLocaleString("ko-KR");
    let priceKrw = null, monthlyRentKrw = null, desiredPrice = "";
    if (dealType === "매매"){ priceKrw = numVal("lrSalePrice"); if (priceKrw) desiredPrice = `매매가 ${fmt(priceKrw)}만원`; }
    else if (dealType === "전세"){ priceKrw = numVal("lrJeonseDeposit"); if (priceKrw) desiredPrice = `보증금 ${fmt(priceKrw)}만원`; }
    else if (dealType === "월세"){
      priceKrw = numVal("lrWolseDeposit"); monthlyRentKrw = numVal("lrWolseRent");
      const parts = []; if (priceKrw) parts.push(`보증금 ${fmt(priceKrw)}만원`); if (monthlyRentKrw) parts.push(`월세 ${fmt(monthlyRentKrw)}만원`); desiredPrice = parts.join("·");
    } else { desiredPrice = ov.querySelector("#lrShortPrice").value.trim(); }
    if (_priceOver){ setMsg("입력 가능한 최대 금액을 초과했습니다 (최대 100억 만원)."); return; }
    setMsg("");
    const btn = ov.querySelector("#lrSubmit"); btn.disabled = true; btn.textContent = "접수 중…";
    try {
      // 전용면적: 콤보 선택값 우선, "직접입력" 또는 수동입력창이 보이면 거기서 읽음
      const _areaSelectEl = ov.querySelector("#lrAreaSelect");
      const _areaManualEl = ov.querySelector("#lrAreaSqm");
      let _areaSqmRaw;
      if (_areaSelectEl && _areaSelectEl.value && _areaSelectEl.value !== "__manual__") {
        _areaSqmRaw = parseFloat(_areaSelectEl.value);
      } else {
        _areaSqmRaw = parseFloat(_areaManualEl ? _areaManualEl.value : "");
      }
      const areaSqm = Number.isFinite(_areaSqmRaw) && _areaSqmRaw > 0 ? _areaSqmRaw : null;
      const dong = ov.querySelector("#lrDong").value.trim().slice(0, 20) || null;
      const ho = ov.querySelector("#lrHo").value.trim().slice(0, 20) || null;
      const registrantType = ov.querySelector("#lrRegistrantType").value || "owner";
      const description = (ov.querySelector("#lrDesc")?.value || "").trim().slice(0, 500) || null;
      const depositKrw = numVal("lrYieldDeposit");
      // 수익률: 계산값 직접 전달 (서버도 검증)
      let yieldRate = null;
      {
        const price = priceKrw || 0;
        const dep   = depositKrw || 0;
        const rent  = monthlyRentKrw || numVal("lrYieldRent") || 0;
        const denom = price - dep;
        if (denom > 0 && rent > 0) yieldRate = parseFloat(((rent * 12) / denom * 100).toFixed(1));
      }
      if (_priceOver){ setMsg("입력 가능한 최대 금액을 초과했습니다 (최대 100억 만원)."); return; }
      const body = { master_building_id: buildingId, deal_type: dealType, deal_mode: dealMode, desired_price: desiredPrice, price_krw: priceKrw, monthly_rent_krw: monthlyRentKrw, area_sqm: areaSqm, dong, ho, registrant_type: registrantType, description, deposit_krw: depositKrw, yield_rate: yieldRate };
      if (contactPhone) body.contact_phone = contactPhone;
      const res = await fetch("/api/listing-requests", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await res.json().catch(() => ({}));
      if (res.status === 401){ close(); if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin(); return; }
      if (!res.ok || d.ok === false){ setMsg(d.message || "접수에 실패했습니다. 잠시 후 다시 시도해주세요."); btn.disabled = false; btn.textContent = "매물의뢰 접수하기"; return; }
      // 사진 업로드 (접수 성공 후 순차 처리, 실패해도 접수 자체는 유지)
      const reqId = d.id;
      if (reqId) {
        const photosEl = ov.querySelector("#lrPhotos");
        const photoFiles = photosEl ? Array.from(photosEl.files || []) : [];
        for (const file of photoFiles.slice(0, 5)) {
          try {
            const fd = new FormData(); fd.append("file", file);
            await fetch(`/api/listing-requests/${reqId}/photos`, { method:"POST", credentials:"same-origin", body: fd });
          } catch(e){ /* 사진 업로드 실패 무시 */ }
        }
      }
      ov.querySelector("#lrForm").style.display = "none";
      ov.querySelector("#lrDone").style.display = "block";
      if (dealMode === "direct"){
        ov.querySelector("#lrDoneTitle").textContent = "직거래 매물이 등록됐습니다";
        ov.querySelector("#lrDoneDesc").innerHTML = "건물 상세 페이지에 공개됩니다.<br/>마이페이지에서 확인·수정·철회할 수 있습니다.";
      } else {
        ov.querySelector("#lrDoneTitle").textContent = "매물의뢰가 접수됐습니다";
        ov.querySelector("#lrDoneDesc").innerHTML = "담당 중개사가 곧 연락드립니다.<br/>접수 현황은 마이페이지에서 확인할 수 있습니다.";
      }
      if (typeof gtag === "function") gtag("event", "generate_lead_listing");
    } catch(e){
      setMsg("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요."); btn.disabled = false; btn.textContent = "매물의뢰 접수하기";
    }
  });
}

// URL ?modal=listing 으로 직접 접근 시 매물의뢰 모달 자동 오픈
// (이메일 "매물내놓기 →" 버튼 → 홈 랜딩 후 자동 실행)
(function(){
  if (new URLSearchParams(location.search).get("modal") !== "listing") return;
  var _opened = false;
  function _open() {
    if (_opened) return;
    _opened = true;
    openListingRequestModal(null, "");
    history.replaceState({}, "", "/"); // 모달 열렸으면 파라미터 제거
  }
  // livingstay:auth 이벤트를 제거하지 않고 지속 감시.
  // 로그아웃→로그인 순서로 두 번 발생하므로 loggedIn=true 인 경우에만 오픈.
  window.addEventListener("livingstay:auth", function(e) {
    if (e.detail && e.detail.loggedIn) _open();
  });
  // 600ms 후 체크: 이미 로그인 상태이면 바로 열고, 아니면 로그인 모달 선행.
  setTimeout(function() {
    if (window.__livingstayLoggedIn) {
      _open();
    } else if (!_opened) {
      if (typeof window.livingstayOpenLogin === "function") window.livingstayOpenLogin();
      else location.href = "/?login=1";
    }
  }, 600);
})();

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
        <div id="brPhoneInputWrap" style="margin-bottom:6px;">
          <input id="brPhone" type="tel" maxlength="13" placeholder="010-1234-5678" style="${FLD} margin-bottom:6px;" />
          <div style="display:flex; gap:6px; margin-bottom:6px;">
            <input id="brPhoneCode" type="text" inputmode="numeric" maxlength="6" placeholder="인증번호 6자리" style="${FLD} flex:1; min-width:90px; font-size:16px;" />
            <button type="button" id="brSendCode" class="side-more" style="white-space:nowrap; margin-top:0; padding:8px 10px; flex-shrink:0; font-size:12.5px;">인증번호 받기</button>
          </div>
          <button type="button" id="brVerifyCode" class="btn-search" style="width:100%; padding:9px; display:none; font-size:13px;">인증 확인</button>
        </div>
        <div id="brPhoneVerified" style="display:none; margin-bottom:6px;">
          <div style="display:flex; align-items:center; gap:8px; padding:9px 11px; background:#F0FBF4; border:1px solid #B7E0C4; border-radius:8px;">
            <span id="brPhoneVerifiedNum" style="font-size:14px; font-weight:700; color:var(--ink); flex:1;"></span>
            <span style="font-size:11.5px; color:#1a7a3c; font-weight:700; white-space:nowrap;">✓ 인증</span>
          </div>
          <button type="button" id="brChangePhone" style="margin-top:5px; font-size:11.5px; color:var(--brass); background:none; border:none; cursor:pointer; padding:0; text-decoration:underline;">다른 번호로 변경</button>
        </div>
        <div id="brMsg" style="font-size:12px; color:var(--brick); min-height:16px; margin-top:6px;"></div>
        <button id="brSubmit" class="btn-search" disabled style="width:100%; padding:12px; margin-top:6px; background:#3B7DD8; border-color:#3B7DD8;">매수의뢰 접수하기</button>
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
    .then((d) => {
      if (!d || !d.logged_in) return;
      if (d.name) ov.querySelector("#brName").value = d.name;
      if (d.phone_verified && d.phone) {
        phoneVerified = true;
        verifiedPhone = d.phone;
        ov.querySelector("#brPhoneVerifiedNum").textContent = d.phone;
        ov.querySelector("#brPhoneInputWrap").style.display = "none";
        ov.querySelector("#brPhoneVerified").style.display = "block";
        ov.querySelector("#brSubmit").disabled = false;
      }
    })
    .catch(() => {});

  let dealType = "매매";
  let phoneVerified = false;
  let verifiedPhone = "";
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

  ov.querySelector("#brChangePhone").addEventListener("click", () => {
    phoneVerified = false;
    verifiedPhone = "";
    ov.querySelector("#brPhoneVerified").style.display = "none";
    ov.querySelector("#brPhoneInputWrap").style.display = "block";
    ov.querySelector("#brPhoneCode").value = "";
    ov.querySelector("#brVerifyCode").style.display = "none";
    ov.querySelector("#brSendCode").disabled = false;
    ov.querySelector("#brSendCode").textContent = "인증번호 받기";
    ov.querySelector("#brSubmit").disabled = true;
    ov.querySelector("#brMsg").textContent = "";
  });

  ov.querySelector("#brSendCode").addEventListener("click", async () => {
    const phoneRaw = ov.querySelector("#brPhone").value.trim();
    const msg = ov.querySelector("#brMsg");
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phoneRaw)){
      msg.textContent = "휴대폰 번호 형식이 올바르지 않습니다. 예) 010-1234-5678";
      return;
    }
    const btn = ov.querySelector("#brSendCode");
    msg.style.color = "var(--brick)";
    msg.textContent = "";
    btn.disabled = true;
    btn.textContent = "발송 중…";
    try {
      const res = await fetch("/api/auth/send-phone-code", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: phoneRaw }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.ok === false){
        msg.textContent = d.message || "발송에 실패했습니다.";
        btn.disabled = false;
        btn.textContent = "인증번호 받기";
        return;
      }
      ov.querySelector("#brVerifyCode").style.display = "block";
      msg.style.color = "#1a7a3c";
      msg.textContent = d.sent ? "인증번호를 발송했습니다. (3분 이내 입력)" : `[개발환경] 인증번호: ${d.dev_code}`;
      btn.textContent = "재발송";
      btn.disabled = false;
    } catch(e){
      msg.style.color = "var(--brick)";
      msg.textContent = "네트워크 오류가 발생했습니다.";
      btn.disabled = false;
      btn.textContent = "인증번호 받기";
    }
  });

  ov.querySelector("#brVerifyCode").addEventListener("click", async () => {
    const code = ov.querySelector("#brPhoneCode").value.trim();
    const msg = ov.querySelector("#brMsg");
    if (!code){ msg.textContent = "인증번호를 입력해주세요."; return; }
    const btn = ov.querySelector("#brVerifyCode");
    btn.disabled = true;
    btn.textContent = "확인 중…";
    try {
      const res = await fetch("/api/auth/verify-phone-code", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.ok === false){
        msg.textContent = d.message || "인증에 실패했습니다.";
        btn.disabled = false;
        btn.textContent = "인증 확인";
        return;
      }
      phoneVerified = true;
      verifiedPhone = d.phone;
      ov.querySelector("#brPhoneVerifiedNum").textContent = d.phone;
      ov.querySelector("#brPhoneInputWrap").style.display = "none";
      ov.querySelector("#brPhoneVerified").style.display = "block";
      ov.querySelector("#brSubmit").disabled = false;
      msg.style.color = "#1a7a3c";
      msg.textContent = "✓ 휴대폰 인증이 완료됐습니다.";
    } catch(e){
      msg.textContent = "네트워크 오류가 발생했습니다.";
      btn.disabled = false;
      btn.textContent = "인증 확인";
    }
  });

  ov.querySelector("#brSubmit").addEventListener("click", async () => {
    const msg = ov.querySelector("#brMsg");
    if (!phoneVerified){
      msg.textContent = "휴대폰 인증이 필요합니다.";
      return;
    }
    const phone = verifiedPhone;
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

function detailBadgeLabel(v, subtype, buildingStatus){
  return window.LodgingTypes.badge(v, subtype, buildingStatus);
}

function buildingPhotoSliderHtml(){
  return `<div id="bldPhotoWrap" class="bld-photo-wrap" style="display:none;"></div>`;
}

function renderPhotoSlider(photos){
  const wrap = document.getElementById("bldPhotoWrap");
  if (!wrap) return;
  const usablePhotos = (Array.isArray(photos) ? photos : [])
    .filter(photo => photo && typeof photo.url === "string" && photo.url.trim());
  if (!usablePhotos.length){
    wrap.innerHTML = "";
    wrap.style.display = "none";
    wrap.classList.remove("has-streetview");
    return;
  }
  wrap.classList.toggle(
    "has-streetview",
    usablePhotos.some(photo => photo.source === "streetview")
  );
  const slides = usablePhotos.map(photo => `
    <div class="bld-photo-slide">
      <img class="${photo.source === "streetview" ? "bld-photo-streetview" : ""}"
           src="${escapeHtml(photo.url.trim())}" alt="건물사진" loading="lazy"
           onerror="handleBuildingPhotoError(this)">
      ${photo.can_delete && photo.id ? `
        <button type="button" class="bld-photo-delete"
                data-building-photo-delete="${escapeHtml(String(photo.id))}"
                aria-label="이 사진 삭제" title="이 사진 삭제">🗑</button>` : ""}
    </div>`
  ).join("");
  const arrowsHidden = usablePhotos.length === 1 ? ` style="display:none;"` : "";
  wrap.innerHTML = `
    <div class="bld-photo-track" id="photoTrack">${slides}</div>
    <button type="button" class="photo-prev" aria-label="이전 사진"${arrowsHidden}>&#8249;</button>
    <button type="button" class="photo-next" aria-label="다음 사진"${arrowsHidden}>&#8250;</button>
    <span class="photo-counter" id="photoCounter">1 / ${usablePhotos.length}</span>`;
  wrap.style.display = "";
  initBuildingPhotoSlider(usablePhotos.length);
  wrap.querySelectorAll("[data-building-photo-delete]").forEach(button => {
    button.addEventListener("click", async event => {
      event.preventDefault();
      event.stopPropagation();
      if (!_activePhotoBuildingId || !window.confirm("이 건물 사진을 삭제하시겠습니까?")) return;
      const photoId = button.dataset.buildingPhotoDelete;
      button.disabled = true;
      try {
        const response = await fetch(
          `/api/building/${encodeURIComponent(_activePhotoBuildingId)}/photos/${encodeURIComponent(photoId)}`,
          {method: "DELETE", credentials: "same-origin"}
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
          throw new Error(data.message || "사진을 삭제하지 못했습니다.");
        }
        renderPhotoSlider(usablePhotos.filter(photo => String(photo.id) !== String(photoId)));
      } catch (error) {
        button.disabled = false;
        window.alert(error.message || "사진 삭제 중 오류가 발생했습니다.");
      }
    });
  });
}

function handleBuildingPhotoError(image){
  const slide = image?.closest(".bld-photo-slide");
  const wrap = image?.closest(".bld-photo-wrap");
  if (slide) slide.remove();
  const remaining = wrap?.querySelectorAll(".bld-photo-slide") || [];
  if (!wrap || !remaining.length) {
    if (wrap) {
      wrap.innerHTML = "";
      wrap.style.display = "none";
    }
    return;
  }
  const track = wrap.querySelector(".bld-photo-track");
  if (track) track.style.transform = "translateX(0)";
  const counter = wrap.querySelector(".photo-counter");
  if (counter) counter.textContent = `1 / ${remaining.length}`;
  wrap.querySelectorAll(".photo-prev, .photo-next").forEach(button => {
    button.style.display = remaining.length > 1 ? "" : "none";
  });
}

function initBuildingPhotoSlider(photoCount){
  if (!photoCount || photoCount < 2) return;
  const wrap = document.querySelector("#bHeaderCard .bld-photo-wrap");
  const track = document.getElementById("photoTrack");
  const counter = document.getElementById("photoCounter");
  const prev = wrap && wrap.querySelector(".photo-prev");
  const next = wrap && wrap.querySelector(".photo-next");
  if (!wrap || !track || !counter || !prev || !next) return;

  let current = 0;
  const update = () => {
    track.style.transform = `translateX(-${current * 100}%)`;
    counter.textContent = `${current + 1} / ${photoCount}`;
  };
  const move = (delta) => {
    current = (current + delta + photoCount) % photoCount;
    update();
  };
  prev.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));

  let touchStartX = null;
  wrap.addEventListener("touchstart", (event) => {
    touchStartX = event.changedTouches[0]?.clientX ?? null;
  }, { passive: true });
  wrap.addEventListener("touchend", (event) => {
    if (touchStartX == null) return;
    const endX = event.changedTouches[0]?.clientX ?? touchStartX;
    const distance = endX - touchStartX;
    touchStartX = null;
    if (Math.abs(distance) >= 40) move(distance < 0 ? 1 : -1);
  }, { passive: true });
}

let _activePhotoBuildingId = null;
const TOUR_API_BROWSER_BASE = "https://apis.data.go.kr/B551011/KorService2";
const BUILDING_PHOTO_LOCAL_CACHE_VERSION = 1;
const BUILDING_PHOTO_LOCAL_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function normalizeTourAddress(address){
  let text = String(address || "").trim().replace(/\s+/g, " ");
  const aliases = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "제주특별자치도": "제주"
  };
  Object.entries(aliases).forEach(([from, to]) => { text = text.replaceAll(from, to); });
  return text.replace(/\([^)]*\)/g, " ").replace(/[^0-9A-Za-z가-힣]/g, "");
}

function tourAddressSimilarity(left, right){
  const a = normalizeTourAddress(left);
  const b = normalizeTourAddress(right);
  if (!a || !b) return 0;
  const aRoad = a.match(/[0-9A-Za-z가-힣]+(?:대로|로|길)/)?.[0];
  const bRoad = b.match(/[0-9A-Za-z가-힣]+(?:대로|로|길)/)?.[0];
  if (aRoad && bRoad && aRoad !== bRoad) return 0;
  const prev = Array.from({length: b.length + 1}, (_, index) => index);
  for (let i = 1; i <= a.length; i += 1){
    let left = prev[0];
    prev[0] = i;
    for (let j = 1; j <= b.length; j += 1){
      const above = prev[j];
      prev[j] = Math.min(
        prev[j] + 1,
        prev[j - 1] + 1,
        left + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
      left = above;
    }
  }
  return 1 - prev[b.length] / Math.max(a.length, b.length);
}

function extractTourItems(data){
  const item = data?.response?.body?.items?.item;
  if (Array.isArray(item)) return item;
  if (item && typeof item === "object") return [item];
  return [];
}

function assertTourApiSuccess(data){
  const header = data?.response?.header || {};
  const code = String(header.resultCode || "").trim();
  if (code && !["0000", "000"].includes(code)){
    throw new Error(`TourAPI ${code}: ${header.resultMsg || "응답 오류"}`);
  }
}

async function tourApiGet(path, params){
  const apiKey = String(
    document.querySelector('meta[name="livingstay-tour-api-service-key"]')?.content || ""
  ).trim();
  if (!apiKey) throw new Error("TourAPI key unavailable");
  const url = new URL(`${TOUR_API_BROWSER_BASE}/${path}`);
  Object.entries({
    serviceKey: apiKey,
    MobileOS: "ETC",
    MobileApp: "homenstay",
    _type: "json",
    ...params
  }).forEach(([key, value]) => url.searchParams.set(key, String(value)));
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url.toString(), {
      mode: "cors",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`TourAPI HTTP ${response.status}`);
    const data = await response.json();
    assertTourApiSuccess(data);
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchTourApiPhotos(buildingName, roadAddress, prewarmed){
  let matchedItem = null;
  let contentId = String(prewarmed?.content_id || "").trim();
  if (!contentId) {
    const searchData = await tourApiGet("searchKeyword2", {
      arrange: "A", numOfRows: 10, pageNo: 1,
      keyword: buildingName, contentTypeId: 32
    });
    const matches = extractTourItems(searchData)
      .map(item => ({
        score: tourAddressSimilarity(item.addr1 || item.addr || "", roadAddress),
        item
      }))
      .filter(candidate => candidate.score >= 0.70)
      .sort((left, right) => right.score - left.score);
    matchedItem = matches[0]?.item;
    contentId = matchedItem?.contentid || matchedItem?.contentId;
  }
  if (!contentId) return [];

  const imageData = await tourApiGet("detailImage2", {
    contentId, numOfRows: 100, pageNo: 1, imageYN: "Y", subImageYN: "Y"
  });
  const representative = matchedItem?.firstimage
    || matchedItem?.firstImage
    || matchedItem?.firstimage2
    || matchedItem?.firstImage2;
  const candidates = [];
  const addPhoto = (url, photoType, isPrimary) => {
    const normalized = String(url || "").trim().replace(/^http:\/\//i, "https://");
    if (!normalized || !/^https:\/\//i.test(normalized)) return;
    if (!candidates.some(photo => photo.url === normalized)){
      candidates.push({url: normalized, photo_type: photoType || "exterior", is_primary: isPrimary});
    }
  };
  addPhoto(representative, "exterior", true);
  extractTourItems(imageData).forEach((image, index) => {
    const name = String(image.imgname || "").toLowerCase();
    const photoType = name.includes("객실") || name.includes("room")
      ? "room"
      : (name.includes("로비") || name.includes("입구") || name.includes("lobby")
        ? "lobby" : "exterior");
    addPhoto(image.originimgurl || image.originImgUrl, photoType, !representative && index === 0);
  });
  if (!candidates.length && prewarmed?.photo_available === true) {
    const commonData = await tourApiGet("detailCommon2", {
      contentId, defaultYN: "Y", firstImageYN: "Y", addrinfoYN: "N",
      mapinfoYN: "N", overviewYN: "N"
    });
    const common = extractTourItems(commonData)[0] || {};
    addPhoto(
      common.firstimage || common.firstImage || common.firstimage2 || common.firstImage2,
      "exterior",
      true
    );
  }
  return candidates.slice(0, 20);
}

function buildingPhotoLocalCacheKey(buildingId){
  return `livingstay:building-photos:v${BUILDING_PHOTO_LOCAL_CACHE_VERSION}:${buildingId}`;
}

function readLocalBuildingPhotos(buildingId, buildingName, roadAddress){
  try {
    const cached = JSON.parse(localStorage.getItem(buildingPhotoLocalCacheKey(buildingId)) || "null");
    const identityMatches = cached
      && cached.building_name === String(buildingName || "")
      && cached.road_address === String(roadAddress || "");
    if (!identityMatches || !Number.isFinite(cached.checked_at)
        || Date.now() - cached.checked_at > BUILDING_PHOTO_LOCAL_TTL_MS){
      localStorage.removeItem(buildingPhotoLocalCacheKey(buildingId));
      return null;
    }
    return {
      status: cached.status === "success" ? "success" : "no_match",
      photos: Array.isArray(cached.photos) ? cached.photos : []
    };
  } catch(e) {
    return null;
  }
}

function writeLocalBuildingPhotos(buildingId, buildingName, roadAddress, photos){
  try {
    localStorage.setItem(buildingPhotoLocalCacheKey(buildingId), JSON.stringify({
      building_name: String(buildingName || ""),
      road_address: String(roadAddress || ""),
      checked_at: Date.now(),
      status: photos.length ? "success" : "no_match",
      photos
    }));
  } catch(e) {
    // 저장 공간 부족·차단 시에도 현재 화면의 사진 표시는 유지한다.
  }
}

function streetViewFallbackPhoto(buildingId, lat, lng){
  if (lat == null || lng == null || String(lat).trim() === "" || String(lng).trim() === "") return [];
  if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return [];
  return [{
    url: `/api/building-photo/${encodeURIComponent(buildingId)}/streetview?view=building-v6`,
    source: "streetview",
    photo_type: "exterior"
  }];
}

function tryShowStreetView(cached, fallbackBuildingId){
  const buildingId = cached?.building_id ?? fallbackBuildingId;
  const photos = streetViewFallbackPhoto(buildingId, cached?.lat, cached?.lng);
  if (!photos.length) return false;
  // Google Maps 키는 서버 프록시가 보관한다. 브라우저에는 사진 프록시 URL만 노출한다.
  renderPhotoSlider(photos);
  return true;
}

async function savePhotosToServer(buildingId, photos){
  const response = await fetch(
    `/api/building/${encodeURIComponent(buildingId)}/photos/tourapi`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({photos}),
    },
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.message || `TourAPI 사진 캐시 저장 실패 (${response.status})`);
  }
  return data;
}

async function loadOnDemandBuildingPhotos(buildingId, initialPhotos, building){
  _activePhotoBuildingId = buildingId;
  const requestToken = _buildingDetailRequestToken;
  const isCurrentPhotoRequest = () =>
    _activePhotoBuildingId === buildingId && _isActiveBuilding(buildingId, requestToken);
  const initial = Array.isArray(initialPhotos) ? initialPhotos : [];

  try {
    const response = await fetch(`/api/building/${encodeURIComponent(buildingId)}/photos`);
    const data = await response.json().catch(() => ({}));
    if (!isCurrentPhotoRequest()) return;
    const photos = response.ok && data.ok && Array.isArray(data.photos) ? data.photos : [];
    if (photos.length > 0) {
      renderPhotoSlider(photos);
      return;
    }
    const gocampingInitial = initial.filter(photo => photo?.source === "gocamping");
    if (gocampingInitial.length > 0) renderPhotoSlider(gocampingInitial);

    const buildingName = data.building_name || building?.building_name || "";
    const roadAddress = data.road_address || building?.road_address || "";
    const prewarmed = data.tourapi_prewarm || null;
    const cached = {
      ...data,
      building_id: buildingId,
      building_name: buildingName,
      road_address: roadAddress,
      lat: data.lat ?? building?.lat,
      lng: data.lng ?? building?.lng,
    };

    // 최근 TourAPI no_match로 서버가 허용한 건물에만 Street View를 표시한다.
    // 좌표만 보고 먼저 표시하면 프록시의 404 JSON이 깨진 이미지로 노출된다.
    const svShown = gocampingInitial.length === 0 && data.streetview_available === true
      && tryShowStreetView(cached, buildingId);

    const local = gocampingInitial.length
      ? null
      : readLocalBuildingPhotos(buildingId, buildingName, roadAddress);
    if (local && local.photos.length > 0) {
      renderPhotoSlider(local.photos);
      return;
    }
    if (local && !prewarmed?.content_id) {
      // 예전 브라우저 캐시에만 no_match가 남은 경우 서버에도 결과를 기록해야
      // Street View 프록시의 허용 조건이 열린다.
      if (!svShown) {
        try {
          const saved = await savePhotosToServer(buildingId, []);
          if (!isCurrentPhotoRequest()) return;
          if (saved.streetview_available === true) {
            tryShowStreetView(cached, buildingId);
          } else {
            renderPhotoSlider([]);
          }
        } catch (error) {
          if (isCurrentPhotoRequest()) renderPhotoSlider([]);
        }
      }
      return;
    }

    // TourAPI는 Street View를 막지 않도록 백그라운드에서 실행한다.
    if (!buildingName) {
      if (!svShown) renderPhotoSlider([]);
      return;
    }

    fetchTourApiPhotos(buildingName, roadAddress, prewarmed)
      .then(async clientPhotos => {
        writeLocalBuildingPhotos(buildingId, buildingName, roadAddress, clientPhotos);
        let saved;
        try {
          saved = await savePhotosToServer(buildingId, clientPhotos);
        } catch (error) {
          // 공용 캐시 저장이 실패해도 현재 방문자의 TourAPI 결과는 표시한다.
          console.warn("[building-photos] TourAPI 서버 캐시 저장 실패", error);
        }
        if (!isCurrentPhotoRequest()) return;
        if (!clientPhotos.length) {
          if (saved?.streetview_available === true) {
            tryShowStreetView(cached, buildingId);
          } else if (!svShown && !gocampingInitial.length) {
            renderPhotoSlider([]);
          }
          return;
        }
        // TourAPI 매칭 성공 시에만 Street View를 교체한다.
        renderPhotoSlider(clientPhotos);
      })
      .catch(() => {
        // TourAPI 실패 시 이미 표시한 고캠핑 대표 이미지나 Street View를 유지한다.
      });
  } catch(e) {
    if (!isCurrentPhotoRequest()) return;
    // 서버가 fallback 가능 여부를 확인하지 못했으면 Street View를 추측해 표시하지 않는다.
    if (initial.length > 0) renderPhotoSlider(initial);
    else renderPhotoSlider([]);
  }
}

function _campingValues(value){
  return String(value || "")
    .split(/[,/]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function _renderCampingSection(b){
  const card = document.getElementById("bCampCard");
  const body = document.getElementById("bCampBody");
  if (!card || !body) return;
  if (b.lodging_type !== "캠핑") {
    card.style.display = "none";
    body.innerHTML = "";
    return;
  }

  const camp = b.camping || {};
  const sites = [
    ["일반 야영", camp.general_site_count ?? b.camping_general_site_count, "🏕️"],
    ["오토 캠핑", camp.auto_site_count ?? b.camping_auto_site_count, "🚙"],
    ["글램핑", camp.glamping_site_count ?? b.camping_glamping_site_count, "⛺"],
    ["카라반", camp.caravan_site_count ?? b.camping_caravan_site_count, "🚐"],
  ].filter(([, count]) => Number(count) > 0);
  const amenities = _campingValues(camp.amenities ?? b.camping_sbrs);
  const seasons = _campingValues(camp.operating_seasons ?? b.camping_oper_pd);
  const chips = [
    ..._campingValues(camp.location_types ?? b.camping_lct_cl),
    ..._campingValues(camp.theme_types ?? b.camping_thema),
    camp.animal_policy ?? b.camping_animal,
  ].filter(Boolean);
  const facts = [
    ["화장실", camp.toilet_count ?? b.camping_toilet_co, "개동"],
    ["샤워실", camp.shower_count ?? b.camping_swrm_co, "개"],
    ["개수대", camp.sink_count ?? b.camping_wtrpl_co, "개"],
    ["전체면적", camp.facility_area ?? b.camping_area, "㎡"],
  ].filter(([, value]) => value != null && value !== "" && Number(value) > 0);
  const reservationUrl = _publicHttpUrl(camp.reservation_url ?? b.camping_resve_url);
  const hasContent = sites.length || amenities.length || seasons.length
    || chips.length || facts.length || reservationUrl;
  if (!hasContent) {
    card.style.display = "none";
    body.innerHTML = "";
    return;
  }

  body.innerHTML = `
    ${chips.length ? `<div class="camp-chips">${chips.map(item =>
      `<span>${escapeHtml(String(item))}</span>`).join("")}</div>` : ""}
    ${sites.length ? `
      <div class="camp-section-label">사이트 구성</div>
      <div class="camp-site-grid">${sites.map(([label, count, icon]) => `
        <div class="camp-site-item">
          <span class="camp-site-icon" aria-hidden="true">${icon}</span>
          <span><b>${Number(count).toLocaleString("ko-KR")}</b> 사이트<br>
            <small>${escapeHtml(label)}</small></span>
        </div>`).join("")}
      </div>` : ""}
    ${amenities.length ? `
      <div class="camp-section-label">편의시설</div>
      <div class="camp-amenities">${amenities.map(item =>
        `<span>✓ ${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    ${facts.length ? `
      <div class="camp-section-label">시설 정보</div>
      <div class="camp-facts">${facts.map(([label, value, unit]) => `
        <div><small>${label}</small><b>${Number(value).toLocaleString("ko-KR")}${unit}</b></div>`
      ).join("")}</div>` : ""}
    ${seasons.length ? `
      <div class="camp-section-label">운영 기간</div>
      <div class="camp-chips camp-seasons">${seasons.map(item =>
        `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    ${reservationUrl ? `
      <a class="camp-reservation" href="${escapeHtml(String(reservationUrl))}"
         target="_blank" rel="noopener noreferrer">캠핑장 예약 페이지 열기 ↗</a>` : ""}
  `;
  card.style.display = "";
}

const STRUCTURE_A_TYPES = ["생활", "관광", "일반"];
const STRUCTURE_B_TYPES = ["에어비앤비", "캠핑", "농어촌민박", "한옥"];
let _buildingDetailRequestToken = 0;
let _buildingTrendRequestSeq = 0;
let _buildingTxRequestSeq = 0;

function _publicHttpUrl(value){
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch(e) {
    return null;
  }
}

function _isActiveBuilding(id, requestToken){
  return window.__openBuildingId === Number(id)
    && _buildingDetailRequestToken === requestToken;
}

function _bookingTarget(b){
  const operators = Array.isArray(b.lodging_operators) ? b.lodging_operators : [];
  const firstValid = field => {
    for (const operator of operators) {
      const url = _publicHttpUrl(operator?.[field]);
      if (url) return url;
    }
    return null;
  };
  const campingUrl = _publicHttpUrl(b.camping?.reservation_url ?? b.camping_resve_url);
  const url = firstValid("booking_url")
    || firstValid("airbnb_url")
    || firstValid("gocamping_url")
    || campingUrl
    || _publicHttpUrl(b.booking_url);
  if (!url) return null;
  const host = new URL(url).hostname.toLowerCase();
  const platform = host.includes("airbnb") ? "에어비앤비"
    : host.includes("yanolja") ? "야놀자"
    : host.includes("yeogi") ? "여기어때"
    : host.includes("booking.com") ? "부킹닷컴"
    : host.includes("gocamping") ? "고캠핑"
    : "외부 예약";
  return { url, platform };
}

function _reservationBar(b, includeConnection = true){
  const target = _bookingTarget(b);
  if (!target) {
    return includeConnection ? `
      <div class="b-reservation-bar is-empty" role="group" aria-label="예약 및 운영자 연결">
        <div><strong>예약 링크 미연결</strong><span>운영자라면 예약 사이트를 직접 연결할 수 있습니다.</span></div>
        <a class="b-connect-btn" href="/lodging-operator/manage">운영자이신가요?</a>
      </div>` : "";
  }
  return `<div class="b-reservation-bar" role="group" aria-label="예약">
    <div><strong>${escapeHtml(target.platform)}</strong><span>예약 가능한 외부 페이지로 이동합니다.</span></div>
    <a class="b-reserve-btn" href="${escapeHtml(target.url)}" target="_blank" rel="noopener noreferrer">예약 페이지 열기</a>
  </div>`;
}

function _setupBuildingPanels(type){
  const isB = STRUCTURE_B_TYPES.includes(type);
  const ids = {
    operations: ["bReservationCard", "bAdminCard", "bCampCard", "bLodgingOperatorCard"],
    property: [
      "bAreaFilterCard", "bTrendCard", "bTimelineCard", "bTxCard",
      "bListingsCard", "bBldgInfoCard", "bAgentCard", "bStoresCard", "bPartnerBannerCard",
    ],
  };
  const opPanel = document.getElementById("bOperationsPanel");
  const propPanel = document.getElementById("bPropertyPanel");
  if (!isB || !opPanel || !propPanel) return;
  ids.operations.forEach(id => { const el = document.getElementById(id); if (el) opPanel.appendChild(el); });
  ids.property.forEach(id => { const el = document.getElementById(id); if (el) propPanel.appendChild(el); });
  ["bOperatorSupportCard", "bFinanceCard"].forEach(id => {
    const el = document.getElementById(id); if (el) propPanel.appendChild(el);
  });
  const tabBar = document.getElementById("bInlineTypeTabs");
  const tabs = tabBar ? tabBar.querySelectorAll(".b-detail-tab") : [];
  const activateTab = tab => {
    tabs.forEach(t => {
      const active = t === tab;
      t.classList.toggle("active", active);
      t.setAttribute("aria-selected", active ? "true" : "false");
      t.tabIndex = active ? 0 : -1;
    });
    const showOps = tab.dataset.panel === "operations";
    opPanel.hidden = !showOps; propPanel.hidden = showOps;
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    });
  });
  const first = tabBar?.querySelector('.b-detail-tab[data-panel="operations"]');
  if (first) activateTab(first);
}

function buildingPanelSkeleton(){
  return `
    <section class="side-card b-panel-topbar">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
        <button id="btnBackToList" class="side-more" style="margin-top:0; text-align:left; width:auto; white-space:nowrap; font-size:12px; padding:6px 10px;">← 전체목록</button>
        <button id="btnListingRequest" class="side-more" style="margin-top:0; width:auto; padding:6px 10px; background:var(--brass); color:#fff; border-color:var(--brass); font-weight:700; white-space:nowrap; font-size:12px;">매물내놓기</button>
        <button id="btnBuyRequest" class="side-more" style="display:inline-flex; margin-top:0; width:auto; padding:6px 10px; background:#3B7DD8; color:#fff; border-color:#3B7DD8; font-weight:700; white-space:nowrap; font-size:12px;">매수의뢰</button>
      </div>
    </section>

    <section class="side-card" id="bHeaderCard">
      <div class="side-empty">불러오는 중…</div>
    </section>
    <section id="bOperationsPanel" class="b-detail-panel" role="tabpanel" aria-labelledby="bTabOperations" hidden></section>
    <section id="bPropertyPanel" class="b-detail-panel" role="tabpanel" aria-labelledby="bTabProperty" hidden></section>

    <section class="side-card" id="bAreaFilterCard" style="padding:10px 14px;">
      <div style="display:flex; align-items:center; gap:8px;">
        <label for="bAreaFilter" style="font-size:12px; color:var(--ink-soft); white-space:nowrap; font-weight:600;">전용면적 타입</label>
        <select id="bAreaFilter" style="flex:1; font-size:12.5px; border:1px solid var(--line); border-radius:6px; padding:4px 8px; background:#fff; color:var(--ink); cursor:pointer;">
          <option value="">전체</option>
        </select>
      </div>
    </section>

    <section class="side-card" id="bTrendCard">
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

    <section class="side-card" id="bTxCard">
      <div class="side-card-title">실거래목록 <span class="side-sub" id="bTxTotalLabel"></span></div>
      <div id="bTxTableWrap" style="overflow-x:auto;"><div class="side-empty">불러오는 중…</div></div>
      <div id="bTxMoreWrap" style="display:none; text-align:center; margin-top:12px;">
        <button id="bTxMore" class="side-more" style="width:auto; padding:7px 18px; margin-top:0;">더보기</button>
      </div>
      <div style="text-align:center; margin-top:8px;">
        <a id="bTxAllLink" class="side-more" style="display:none; width:auto; padding:7px 18px; margin-top:0; text-decoration:none;" href="/transactions">이 건물 전체 실거래 보기 →</a>
      </div>
    </section>

    <section class="side-card" id="bCampCard" style="display:none;">
      <div class="side-card-title">캠핑장 안내 <span class="side-sub">고캠핑</span></div>
      <div id="bCampBody"></div>
    </section>

    <section class="side-card" id="bListingsCard" style="display:none;">
      <div class="side-card-title">직거래 매물</div>
      <div id="bListingsBody"></div>
    </section>

    <section class="side-card" id="bAgentCard" style="display:none;">
      <div class="side-card-title">담당중개사</div>
      <div id="bAgentBox"></div>
    </section>
    <section class="side-card" id="bLodgingOperatorCard" style="display:none;">
      <div class="side-card-title">시설 운영 파트너</div><div id="bLodgingOperatorBox"></div>
    </section>
    <section class="side-card" id="bReservationCard" style="display:none;"></section>
    <section class="side-card" id="bOperatorSupportCard" style="display:none;">
      <div class="side-card-title">운영지원 파트너</div><div id="bOperatorBox"></div>
    </section>
    <section class="side-card" id="bFinanceCard" style="display:none;">
      <div class="side-card-title">금융 파트너</div><div id="bFinanceBox"></div>
    </section>

    <section class="side-card" id="bAdminCard">
      <div class="side-card-title">행정 <span class="side-sub">숙박업영업신고율</span></div>
      <div class="side-empty">불러오는 중…</div>
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
    </section>

    <section class="side-card" id="bPartnerBannerCard">
      ${partnerUnifiedBannerHTML()}
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
function _renderDetailCards(b, buildingId){
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
  const unitStatsHtml = (() => {
    const stats = Array.isArray(b.unit_area_stats) ? b.unit_area_stats : [];
    if (!stats.length) return "";
    const items = stats.map(s => `${s.area_sqm}㎡ ${s.ho_cnt}실`).join("&emsp;");
    return `<div style="margin-top:8px; padding-top:8px; border-top:1px solid var(--line);">
      <div style="font-size:11px; color:var(--ink-soft); font-weight:600; margin-bottom:4px;">평형별 호실수</div>
      <div style="font-size:12.5px; color:var(--ink); line-height:1.8;">${items}</div>
    </div>`;
  })();
  bldgInfoCard.innerHTML = `
    <div class="side-card-title">건축정보 <span class="side-sub">${isPreC ? "건축인허가" : "표제부"}</span>${hint}</div>
    <div class="b-bldg-grid">${cells}</div>${unitStatsHtml}`;

  // 최근 본 건물 localStorage 기록 (로그인 불필요)
  const bName = b.building_name || "(건물명 미확인)";
  trackRecentBuilding(buildingId, bName, b.road_address || b.jibun_address || b.address || "");

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
          _renderDetailCards(fresh, buildingId);
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
  const requestToken = _buildingDetailRequestToken;
  let b;
  try {
    const res = await fetch("/api/building/" + id);
    if (!res.ok) throw new Error(res.status);
    b = await res.json();
  } catch(e){
    if (!_isActiveBuilding(id, requestToken)) return;
    headerCard.innerHTML = `<div class="side-empty">건물 정보를 불러오지 못했습니다.</div>`;
    return;
  }
  if (!_isActiveBuilding(id, requestToken)) return;


  const isPreCompletion = b.building_status && b.building_status !== "완공";
  const hasType = !!(b.lodging_type && b.lodging_type !== "mixed_use_excluded");
  const typeBadge = hasType
    ? `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:${markerColor(b.lodging_type, b.building_status)}; padding:2px 9px; border-radius:6px; vertical-align:middle;">${escapeHtml(detailBadgeLabel(b.lodging_type, b.lodging_subtype, b.building_status))}</span>`
    : "";
  const preBadge = isPreCompletion
    ? `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:#9AA5B1; padding:2px 9px; border-radius:6px; vertical-align:middle; margin-left:${hasType ? "5px" : "0"};">🏗 준공예정 ${b.completion_expected_date ? escapeHtml(String(b.completion_expected_date)) : "미정"}</span>`
    : "";
  const badge = hasType || isPreCompletion
    ? `${typeBadge}${preBadge}`
    : `<span style="display:inline-block; font-size:10.5px; font-weight:700; color:#fff; background:${LODGING_COLORS["미분류"]}; padding:2px 9px; border-radius:6px; vertical-align:middle;">미분류</span>`;
  const units = b.units != null ? Number(b.units).toLocaleString('ko-KR') + "실" : "-";
  // 영업신고 호수·신고율은 lodging_registry 비폐업 객실수 합계만 사용한다.
  // master_buildings의 과거 biz_units 스냅샷은 계산 경로에서 제외한다.
  const lodgingRoomTotal = b.lodging_room_total != null
    ? Number(b.lodging_room_total) : null;
  const bizUnits = lodgingRoomTotal != null ? lodgingRoomTotal.toLocaleString('ko-KR') + "실" : "-";
  // 신고율: 서버가 같은 실시간 집계로 계산한 값을 우선 사용한다.
  const unitsNum = b.units != null ? Number(b.units) : null;
  let headerRate = "-";
  if (b.lodging_type !== "일반" && b.lodging_report_rate != null) {
    headerRate = Number(Number(b.lodging_report_rate).toFixed(1)).toLocaleString('ko-KR') + "%";
  } else if (b.lodging_type !== "일반" && lodgingRoomTotal != null && unitsNum && unitsNum > 0) {
    headerRate = Number((lodgingRoomTotal * 100 / unitsNum).toFixed(1)).toLocaleString('ko-KR') + "%";
  }
  const bName = b.display_building_name || b.building_name || "(건물명 미확인)";
  const lodgingNameTag = b.building_name_report_display
    ? `<span title="건축물대장 명칭이 확인되지 않아 현재 활성 영업신고 중 객실 수가 가장 많은 사업장명을 대표로 표시합니다." style="font-size:11px; font-weight:600; color:#386641; background:#edf7ee; border:1px solid #b9dec0; border-radius:10px; padding:2px 8px; white-space:nowrap;">영업신고(최다) 기준</span>`
    : "";
  const namePendingNeedsReview = b.building_name_needs_review != null
    ? Boolean(b.building_name_needs_review)
    : Boolean(
        (b.name_pending || b.building_name_source === "lodging_report")
        && !b.building_name_report_display
      );
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
  const safeBuildingBookingUrl = _publicHttpUrl(b.booking_url);
  const bookingBadge = safeBuildingBookingUrl
    ? `<a href="${escapeHtml(safeBuildingBookingUrl)}" target="_blank" rel="noopener noreferrer"
        style="display:inline-block;font-size:12px;font-weight:700;color:#1a7a3c;
        background:#E6F4EA;border:1px solid #B7E0C4;border-radius:5px;padding:2px 8px;
        text-decoration:none;">✓ OTA 등록확인</a>`
    : `<span style="font-size:12px;color:var(--ink-soft);">미확인</span>`;

  // 관심저장/실거래알림은 좌측 목록과 동일한 키(building_name|address)를 사용. address가
  // 없는(=거래이력 없는) 건물은 두 버튼을 비활성화한다.
  // 실거래 지번주소(b.address)가 있으면 그대로(좌측 목록과 키 일치), 없으면 마스터
  // 도로명주소(b.road_address)로 폴백 → 거래이력 없어도 주소만 있으면 버튼 활성화.
  const favAddr = (b.address != null && b.address !== "") ? b.address : (b.road_address || "");
  const favItem = { building_name: b.building_name, address: favAddr, building_id: b.building_id };
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
  const buildingPhotos = Array.isArray(b.photos) ? b.photos : [];

  headerCard.innerHTML = `
    ${buildingPhotoSliderHtml()}
    ${STRUCTURE_A_TYPES.includes(b.lodging_type) ? _reservationBar(b) : ""}
    ${STRUCTURE_B_TYPES.includes(b.lodging_type) ? `<div id="bInlineTypeTabs" class="b-inline-tabs" role="tablist" aria-label="건물 상세 정보">
      <button type="button" id="bTabOperations" class="b-detail-tab active" data-panel="operations" role="tab" aria-controls="bOperationsPanel" aria-selected="true" tabindex="0">운영정보</button>
      <button type="button" id="bTabProperty" class="b-detail-tab" data-panel="property" role="tab" aria-controls="bPropertyPanel" aria-selected="false" tabindex="-1">부동산정보</button>
    </div>` : ""}
    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px;">
      <h1 style="font-size:17px; font-weight:700; color:var(--ink); margin:0;">${escapeHtml(bName)}</h1>
      ${namePendingNeedsReview ? '<span style="font-size:11px; font-weight:600; color:#8a6d1f; background:#fdf6e3; border:1px solid #e8d9a0; border-radius:10px; padding:2px 8px; white-space:nowrap;">정식명칭 확인중</span>' : ""}
      ${lodgingNameTag}
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
    ${namePendingNeedsReview && b.sgg_cd && b.umd_nm && b.jibun ? `
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
    <button type="button" id="bSignalBtn" class="b-signal-btn" title="숙박알리미" data-enabled="false"
      style="width:100%;display:flex;flex-direction:column;gap:2px;padding:8px 12px;border-radius:8px;margin-bottom:6px;border:1px solid var(--brass,#B4863F);cursor:pointer;text-align:left;background:none;">
      <span class="b-signal-label" style="font-size:12px;font-weight:800;color:var(--brass-dark,#8A6812);">🔔 숙박알리미 받기</span>
      <span style="font-size:10px;color:var(--ink-soft);line-height:1.6;">
        실거래 · 급매 · 신규매물 · 영업신고변동<br>
        관심자증가 · 주변 신규등록·폐업
      </span>
    </button>
    <div class="b-actions" style="display:flex;gap:6px;">
      <button type="button" id="bFavBtn" class="b-icon-btn" title="관심저장">${Icons.heart(14)}<span class="b-icon-label">관심저장</span></button>
      <button type="button" id="bMapBtn" class="b-icon-btn" title="지도위치">${Icons.navigation(14)}<span class="b-icon-label">지도위치</span></button>
      <button type="button" id="bShareBtn" class="b-icon-btn" title="공유">${Icons.share(14)}<span class="b-icon-label">공유</span></button>
    </div>
    ${canFav ? `<div id="bFavHint" style="font-size:11.5px;color:var(--ink-soft);margin:2px 0 8px;text-align:center;">저장하면 새 실거래를 이메일로 알려드립니다</div>` : ""}`;
  renderPhotoSlider(buildingPhotos);
  _setupBuildingPanels(b.lodging_type);
  const reservationCard = document.getElementById("bReservationCard");
  if (reservationCard) {
    if (STRUCTURE_B_TYPES.includes(b.lodging_type)) {
      reservationCard.innerHTML = _reservationBar(b);
      reservationCard.style.display = "";
    } else {
      reservationCard.style.display = "none";
    }
  }
  loadOnDemandBuildingPhotos(id, buildingPhotos, b);

  // 직거래 공개 매물 카드 — 카드형 리스트, 정렬/NEW뱃지/찜/설명/사진
  const listingsCard = document.getElementById("bListingsCard");
  const listingsBody = document.getElementById("bListingsBody");
  if (listingsCard && listingsBody) {
    const allListings = Array.isArray(b.direct_listings) ? b.direct_listings : [];
    let _lsSort = "latest";
    let _urgentOnly = false;
    const _isUrgentListing = (listing) => !!(listing && listing.urgent_tier === "urgent");
    const _trackedWholeListingViews = new Set();
      const _liveWholeListingViews = new Set();
      let _wholeViewerRefreshTimer = null;
      const _refreshWholeViewerCounts = async () => {
        const ids = [..._liveWholeListingViews];
        if (!ids.length) return;
        try {
          const query = ids.map(id => `listing_ids=${encodeURIComponent(id)}`).join("&");
          const response = await fetch(`/api/listings/views?${query}`, {credentials:"same-origin"});
          const data = await response.json().catch(() => ({}));
          if (!response.ok || !data.ok) return;
          (data.items || []).forEach(item => {
            listingsBody.querySelectorAll(`[data-listing-id="${item.id}"] .b-whole-viewers`).forEach(el => {
              el.textContent = `최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명`;
            });
            document.querySelectorAll(`[data-listing-viewer-count="${item.id}"]`).forEach(el => {
              el.textContent = `최근 열람 ${Number(item.viewer_count || 0).toLocaleString()}명`;
            });
          });
        } catch (error) {}
      };
      const _startWholeViewerRefresh = () => {
        if (_wholeViewerRefreshTimer) return;
        _wholeViewerRefreshTimer = setInterval(_refreshWholeViewerCounts, 15000);
      };
    let _wholeLocationContext = null;
      const _dealTypeColors = { "매매":"#C85A36", "전세":"#378ADD", "월세":"#639922", "단기임대":"#8B6BB1", "통임대":"#5A7FA6", "운영권양도":"#8B6BB1", "위탁운영":"#557A5B" };
     function _dealTypeBadge(raw){
       const label = raw || "-";
       const color = _dealTypeColors[label] || "#7B8794";
       return `<span style="display:inline-block;min-width:35px;padding:2px 5px;margin-right:4px;border-radius:5px;color:#fff;background:${color};font-size:10px;line-height:1.25;font-weight:800;text-align:center;vertical-align:middle;white-space:nowrap;">${escapeHtml(label)}</span>`;
     }
      function _businessStayPriceText(lr, formatNumber){
        if (lr.room_price_min != null && lr.room_price_max != null) {
          return `장기임대 가능 · ${formatNumber(lr.room_price_min)}~${formatNumber(lr.room_price_max)}만원/월`;
        }
        return "현재 문의 가능 여부는 채팅으로 확인해주세요";
      }
      function _listingPriceText(lr, formatNumber){
        if (lr.is_whole_listing || lr.transaction_target === "whole") {
          if (lr.deal_type === "매매") return lr.price_krw != null ? `매매가 ${formatNumber(lr.price_krw)}만원` : "매매 조건 협의";
          const deposit = lr.price_krw != null ? `보증금 ${formatNumber(lr.price_krw)}만원` : "조건 협의";
          return lr.monthly_rent_krw != null ? `${deposit} / 월 ${formatNumber(lr.monthly_rent_krw)}만원` : deposit;
        }
        if (lr.is_business_listing) return _businessStayPriceText(lr, formatNumber);
        return lr.deal_type === "월세" && lr.price_krw_max == null
          ? `보${formatNumber(lr.price_krw)}/${formatNumber(lr.monthly_rent_krw)}만`
          : (lr.price_krw
            ? `${formatNumber(lr.price_krw)}${lr.price_krw_max != null ? " ~ " + formatNumber(lr.price_krw_max) : ""}만원`
            : "-");
       }
       function _operationStatusText(lr){
         if (!(lr.is_whole_listing || lr.transaction_target === "whole") || !lr.operation_status) return "";
         const icon = lr.operation_status === "영업중" ? "🟢" : (lr.operation_status === "휴업" ? "🟡" : "⚫");
         const closedDate = lr.operation_status === "폐업" && (lr.closed_at || lr.closed_date)
           ? `(${escapeHtml(lr.closed_at || lr.closed_date)})` : "";
         return `영업상태: ${icon}${escapeHtml(lr.operation_status)}${closedDate}`;
       }
       function _operationStatusMarkup(lr){
         const text = _operationStatusText(lr);
         if (!text) return "";
         const color = lr.operation_status === "폐업" ? "#222" : (lr.operation_status === "휴업" ? "#A06D18" : "#4A7A18");
         return `<div style="font-size:12px;color:${color};font-weight:700;margin-bottom:7px;">${text}</div>`;
       }
       function _permitBadgeMarkup(lr){
         if (!lr || !lr.permit_number_masked) return "";
         return `<span title="인증된 숙박업 신고번호의 일부를 마스킹해 표시합니다." style="display:inline-block;margin-left:5px;padding:1px 5px;border-radius:4px;background:#EDF6EC;color:#356212;font-size:10px;font-weight:800;vertical-align:middle;white-space:nowrap;">신고 ${escapeHtml(lr.permit_number_masked)}</span>`;
       }
       function _operationRatioMarkup(lr){
         const badges = [];
         if (lr && lr.short_stay_ratio != null) badges.push(`대실 ${Number(lr.short_stay_ratio).toLocaleString()}%`);
         if (lr && lr.ota_revenue_ratio != null) badges.push(`OTA ${Number(lr.ota_revenue_ratio).toLocaleString()}%`);
         return badges.map(label => `<span style="display:inline-block;margin:0 4px 7px 0;padding:2px 5px;border-radius:4px;background:#EEF5FF;color:#275B88;font-size:10px;font-weight:800;">${escapeHtml(label)}</span>`).join("");
       }
       function _urgentBadgeMarkup(lr){
         if (!lr || lr.urgent_tier !== "urgent") return "";
         const urgentTitle = lr.is_urgent
           ? "판매자가 급매로 등록한 매물"
           : "최신 실거래가보다 낮은 매물";
         return `<span class="urgent-tier-badge" title="${urgentTitle}"
           style="display:inline-block;padding:2px 7px;border-radius:4px;
                  background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;
                  letter-spacing:0.3px;">급매</span>`;
       }
      function _openDirectListingCard(lr){
        if (typeof window.openListingDetailModal === "function") {
          const shareListing = async () => {
            const shareOrigin = (window.LIVINGSTAY_PUBLIC_BASE_URL || location.origin).replace(/\/+$/, "");
            const shareUrl = new URL(`/building/${encodeURIComponent(b.building_id)}`, shareOrigin);
            shareUrl.searchParams.set("listing", String(lr.id));
            const shareData = {title: `${bName} 직거래 매물 | 홈앤스테이`, text: `${bName} 직거래 매물`, url: shareUrl.toString()};
            if (navigator.share) {
              try {
                await navigator.share(shareData);
                return;
              } catch (e) {
                if (e && e.name === "AbortError") return;
              }
            }
            try {
              if (navigator.clipboard) {
                await navigator.clipboard.writeText(shareData.url);
                return;
              }
            } catch (e) {}
            prompt("아래 매물 링크를 복사하세요:", shareData.url);
          };
          window.openListingDetailModal(lr, {
            onChat: () => _openListingChat(lr.id),
            onShare: shareListing,
          });
          return;
        }
       document.getElementById("directListingCardOverlay")?.remove();
        const previousFocus = document.activeElement;
       const photos = Array.isArray(lr.photos) ? lr.photos.filter(Boolean) : [];
       const formatNumber = (v) => v != null ? Number(v).toLocaleString() : "-";
        let photoIndex = 0;
        const photoGallery = photos[0]
          ? `<div style="position:relative;background:#f6f4f0;">
              <img id="directListingCardImage" src="${escapeHtml(photos[0])}" alt="매물 사진 1" style="width:100%;height:220px;object-fit:cover;display:block;" onerror="this.style.display='none';">
              ${photos.length > 1 ? `<button type="button" id="directListingPhotoPrev" aria-label="이전 사진" style="position:absolute;left:10px;top:calc(50% - 17px);width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.5);color:#fff;font-size:21px;line-height:1;cursor:pointer;">‹</button>
              <button type="button" id="directListingPhotoNext" aria-label="다음 사진" style="position:absolute;right:10px;top:calc(50% - 17px);width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.5);color:#fff;font-size:21px;line-height:1;cursor:pointer;">›</button>
              <span id="directListingPhotoCount" style="position:absolute;right:12px;bottom:10px;padding:4px 8px;border-radius:999px;background:rgba(0,0,0,.62);color:#fff;font-size:11px;font-weight:700;">1 / ${photos.length}</span>
              <div id="directListingPhotoThumbs" style="position:absolute;left:10px;bottom:9px;display:flex;gap:5px;max-width:calc(100% - 86px);overflow:auto;">${photos.map((src, index) => `<button type="button" data-photo-index="${index}" aria-label="사진 ${index + 1} 보기" style="width:34px;height:27px;padding:0;flex:0 0 auto;border:${index === 0 ? "2px solid #fff" : "1px solid rgba(255,255,255,.72)"};border-radius:4px;overflow:hidden;background:#fff;cursor:pointer;"><img src="${escapeHtml(src)}" alt="" style="width:100%;height:100%;object-fit:cover;display:block;"></button>`).join("")}</div>` : ""}
            </div>`
          : `<div style="height:220px;background:var(--brass-tint,#FFF5E0);display:flex;align-items:center;justify-content:center;">${Icons.home(56)}</div>`;
        const isWholeListing = lr.is_whole_listing || lr.transaction_target === "whole";
        const sqm = !isWholeListing && lr.area_sqm ? `${parseFloat(lr.area_sqm).toFixed(1)}㎡` : "";
        const listingMeta = [
          lr.listing_number ? escapeHtml(lr.listing_number) : "",
          lr.listing_date ? `최근 수정 ${escapeHtml(lr.listing_date)}` : ""
        ].filter(Boolean).join(" · ");
         const priceText = _listingPriceText(lr, formatNumber);
       const yieldText = lr.yield_rate != null ? `수익률 ${parseFloat(lr.yield_rate).toFixed(1)}% (참고용)` : "";
        const wholeRoomPriceText = isWholeListing && lr.price_krw != null
          && Number(lr.room_count) > 0 && Number(lr.price_krw) > 0
          ? `객실당 ${formatNumber(Math.round(Number(lr.price_krw) / Number(lr.room_count)))}만원` : "";
        const roomText = isWholeListing
          ? [lr.room_count != null && Number(lr.room_count) > 0 ? `총 ${formatNumber(lr.room_count)}실` : "", wholeRoomPriceText]
            .filter(Boolean).join(" · ")
          : (!lr.is_business_listing && lr.room_count != null && Number(lr.room_count) > 0
            ? `총 ${formatNumber(lr.room_count)}실` : "");
        const statusMarkup = _operationStatusMarkup(lr);
        const desc = lr.description ? escapeHtml(lr.description) : "";
        const hasApproximateLocation = !!lr.is_limited_listing
          && Number.isFinite(Number(lr.approx_lat))
          && Number.isFinite(Number(lr.approx_lng));
        const approximateLocationButton = hasApproximateLocation
          ? `<button type="button" id="directListingApproxLocation" style="display:inline-block;margin:0 0 12px;padding:7px 9px;border:1px solid #378ADD;border-radius:7px;background:#F3F8FD;color:#275B88;font:700 12px inherit;cursor:pointer;">◎ 반경 500m 위치 보기</button>`
          : "";
       const ov = document.createElement("div");
       ov.id = "directListingCardOverlay";
       ov.style.cssText = "position:fixed;inset:0;z-index:4500;background:rgba(22,32,46,.5);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";
         const listingIcons = window.LivingstayListingIcons;
         const likeCount = lr.like_count || 0;
         const listingActionsMarkup = `<div style="display:flex;justify-content:flex-end;gap:7px;">
           <button type="button" id="directListingCardLike" class="listing-like-btn${lr.liked ? " is-liked" : ""}" aria-label="매물 찜" title="찜">${listingIcons.heart(!!lr.liked)}<span class="like-cnt">${likeCount}</span></button>
            <button type="button" id="directListingCardChat" class="listing-chat-btn" aria-label="매물 채팅" title="채팅">${listingIcons.chat()}</button>
            <button type="button" id="directListingCardShare" class="listing-share-btn" aria-label="매물 공유" title="매물 공유">${listingIcons.share()}</button>
         </div>`;
        ov.innerHTML = `<div id="directListingCardDialog" role="dialog" aria-modal="true" aria-label="직거래 매물 상세" tabindex="-1" style="width:min(100%,420px);max-height:88vh;overflow:auto;background:#fff;border-radius:16px;box-shadow:0 10px 36px rgba(0,0,0,.25);">
          <div style="position:relative;">${photoGallery}<button type="button" id="directListingCardClose" aria-label="닫기" style="position:absolute;top:10px;right:10px;width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:22px;line-height:1;cursor:pointer;">×</button></div>
          <div style="padding:16px 18px 18px;">
             ${listingMeta ? `<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:-4px 0 8px;font-size:11px;color:var(--ink-soft);"><span style="padding:2px 6px;border-radius:4px;background:var(--brass-tint,#FFF5E0);border:1px solid var(--brass,#B4863F);color:var(--brass-dark,#7D4A00);font-weight:800;">${lr.listing_number ? escapeHtml(lr.listing_number) : ""}</span>${lr.listing_date ? `<span>최근 수정 ${escapeHtml(lr.listing_date)}</span>` : ""}</div>` : ""}
            <div style="font-size:16px;font-weight:800;color:var(--ink);margin-bottom:7px;">${isWholeListing ? '<span style="display:inline-block;margin-right:5px;padding:2px 6px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;">건물전체</span>' : ""}${_dealTypeBadge(lr.deal_type)}${sqm ? ` · ${sqm}` : ""}</div>
           <div style="font-size:20px;font-weight:800;color:var(--ink);margin-bottom:7px;">${escapeHtml(priceText)}</div>
             ${roomText ? `<div style="font-size:12px;color:var(--ink-soft);font-weight:700;margin-bottom:7px;">${escapeHtml(roomText)}</div>` : ""}
             ${statusMarkup}
              ${_operationRatioMarkup(lr)}
              ${_permitBadgeMarkup(lr)}
           ${yieldText ? `<div style="font-size:12px;color:var(--brass-dark,#7D4A00);font-weight:700;margin-bottom:7px;">${escapeHtml(yieldText)}</div>` : ""}
            ${desc ? `<div style="font-size:13px;color:var(--ink-soft);line-height:1.6;white-space:pre-line;margin-bottom:12px;">${desc}</div>` : ""}
             ${approximateLocationButton}
             ${isWholeListing ? `<button type="button" class="listing-checklist-open" id="directListingChecklistOpen">숙박업소 거래 체크리스트 열어보기</button>` : ""}
             ${listingActionsMarkup}
         </div>
       </div>`;
       document.body.appendChild(ov);
        const dialog = ov.querySelector("#directListingCardDialog");
        const close = () => {
          document.removeEventListener("keydown", handleCardKeydown);
          ov.remove();
          if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
        };
        const handleCardKeydown = (event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            close();
            return;
          }
          if (event.key !== "Tab") return;
          const focusable = Array.prototype.slice.call(dialog.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )).filter((element) => element.offsetParent !== null);
          if (!focusable.length) {
            event.preventDefault();
            dialog.focus();
            return;
          }
          const first = focusable[0], last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        };
        document.addEventListener("keydown", handleCardKeydown);
       ov.querySelector("#directListingCardClose").addEventListener("click", close);
         ov.querySelector("#directListingApproxLocation")?.addEventListener("click", (event) => {
           event.stopPropagation();
           if (typeof window.openApproximateLocationMap === "function") {
             window.openApproximateLocationMap(Number(lr.approx_lat), Number(lr.approx_lng), event.currentTarget);
           }
         });
         ov.querySelector("#directListingChecklistOpen")?.addEventListener("click", () => {
           window.LivingstayListingChecklist?.open(lr.id);
         });
        ov.querySelector("#directListingCardChat").addEventListener("click", () => { close(); _openListingChat(lr.id); });
        if (photos.length > 1) {
          const image = ov.querySelector("#directListingCardImage");
          const count = ov.querySelector("#directListingPhotoCount");
          const thumbs = ov.querySelectorAll("[data-photo-index]");
          const showPhoto = (index) => {
            photoIndex = (index + photos.length) % photos.length;
            image.src = photos[photoIndex];
            image.alt = `매물 사진 ${photoIndex + 1}`;
            count.textContent = `${photoIndex + 1} / ${photos.length}`;
            thumbs.forEach((thumb, thumbIndex) => {
              thumb.style.border = thumbIndex === photoIndex ? "2px solid #fff" : "1px solid rgba(255,255,255,.72)";
            });
          };
          ov.querySelector("#directListingPhotoPrev").addEventListener("click", () => showPhoto(photoIndex - 1));
          ov.querySelector("#directListingPhotoNext").addEventListener("click", () => showPhoto(photoIndex + 1));
          thumbs.forEach((thumb) => thumb.addEventListener("click", () => showPhoto(parseInt(thumb.dataset.photoIndex, 10))));
        }
        ov.querySelector("#directListingCardShare").addEventListener("click", async () => {
          const shareOrigin = (window.LIVINGSTAY_PUBLIC_BASE_URL || location.origin).replace(/\/+$/, "");
          const shareUrl = new URL(`/building/${encodeURIComponent(b.building_id)}`, shareOrigin);
          shareUrl.searchParams.set("listing", String(lr.id));
          const url = shareUrl.toString();
          const shareData = {title: `${bName} 직거래 매물 | 홈앤스테이`, text: `${bName} 직거래 매물`, url: url};
          if (navigator.share) {
            try {
              await navigator.share(shareData);
              return;
            } catch (e) {
              // 사용자가 공유창을 닫은 경우만 조용히 종료한다.
              // 그 밖의 오류는 아래 링크 복사로 이어져 공유가 불발되지 않게 한다.
              if (e && e.name === "AbortError") return;
            }
          }
          try {
            if (navigator.clipboard) {
              await navigator.clipboard.writeText(url);
              const button = ov.querySelector("#directListingCardShare");
              const originalMarkup = button.innerHTML;
              button.innerHTML = `<span style="font-size:11px;font-weight:700;white-space:nowrap;">복사됨</span>`;
              setTimeout(() => { if (button.isConnected) button.innerHTML = originalMarkup; }, 1400);
              return;
            }
          } catch (e) { /* 아래 복사 안내로 진행 */ }
          prompt("아래 매물 링크를 복사하세요:", url);
        });
        ov.querySelector("#directListingCardLike").addEventListener("click", async (event) => {
          const button = event.currentTarget;
          try {
            const response = await fetch(`/api/listing-requests/${lr.id}/like`, {method:"POST", credentials:"same-origin"});
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.ok) return;
            button.classList.toggle("is-liked", !!data.liked);
            button.innerHTML = `${listingIcons.heart(!!data.liked)}<span class="like-cnt">${data.like_count}</span>`;
          } catch (error) {}
        });
       ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
        requestAnimationFrame(() => ov.querySelector("#directListingCardClose").focus());
     }

    function _renderListings(listings){
      if (!listings.length && !_urgentOnly){ listingsCard.style.display = "none"; return; }
      listingsCard.style.display = "";
      const _fmtN = (v) => v != null ? Number(v).toLocaleString() : "-";
      const now = Date.now();
      const THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000;

      const _sortBtns = [["latest","최신순"],["price","가격순"],["yield","수익률순"]].map(([v,l])=>
        `<button type="button" data-lsort="${v}" style="font-size:11px;padding:3px 9px;border-radius:12px;border:1px solid ${_lsSort===v?"var(--brass,#B4863F)":"var(--line,#ddd)"};background:${_lsSort===v?"var(--brass-tint,#FFF5E0)":"#fff"};color:${_lsSort===v?"var(--brass-dark,#7D4A00)":"var(--ink-soft)"};cursor:pointer;margin-right:4px;">${l}</button>`
      ).join("");
      const _urgentOnlyBtn = `<button type="button" id="lsUrgentFilter"
        style="font-size:11px;padding:3px 9px;border-radius:12px;
          border:1px solid ${_urgentOnly?"var(--brass,#B4863F)":"var(--line,#ddd)"};
          background:${_urgentOnly?"#FFF0EC":"#fff"};
          color:${_urgentOnly?"var(--brass-dark,#7D4A00)":"var(--ink-soft)"};
          cursor:pointer;margin-left:2px;font-weight:${_urgentOnly?700:400};">
        급매</button>`;
      const sortBar = _sortBtns + _urgentOnlyBtn;
      function _lodgingBadge(raw, subtype){
        const label = window.LodgingTypes.badge(raw, subtype);
        return `<span style="display:inline-block;margin-right:5px;padding:1px 6px;border-radius:4px;background:${window.LodgingTypes.color(raw)};color:#fff;font-size:10px;font-weight:700;vertical-align:middle;white-space:nowrap;">${escapeHtml(label)}</span>`;
      }
      function _wholeListingCard(lr, lrId, photoHtml, photoCount, dt){
         const hasApproximateLocation = !!lr.is_limited_listing
           && Number.isFinite(Number(lr.approx_lat))
           && Number.isFinite(Number(lr.approx_lng));
         const approximateLocationButton = hasApproximateLocation
           ? `<button type="button" class="b-approx-location-btn" data-lat="${Number(lr.approx_lat)}" data-lng="${Number(lr.approx_lng)}" style="display:inline-block;margin:5px 0 0;padding:7px 9px;border:1px solid #378ADD;border-radius:7px;background:#F3F8FD;color:#275B88;font:700 12px inherit;cursor:pointer;">◎ 반경 500m 위치 보기</button>`
           : "";
        const price = Number(lr.price_krw || 0);
        const loan = Number(lr.succession_loan_krw || 0);
        const keyMoney = Number(lr.key_money_krw || 0);
        const financeVisible = !!lr.financial_details_visible;
        const acquisition = price > 0 && financeVisible
          ? price - loan + keyMoney + (price * 0.061) : null;
        const isRecentClosure = lr.operation_status === "폐업" && lr.closed_at
          && Date.now() - new Date(lr.closed_at).getTime() <= 90 * 24 * 60 * 60 * 1000;
        const wholeRoomPriceText = lr.price_krw != null && Number(lr.room_count) > 0
          && Number(lr.price_krw) > 0
          ? `객실당 ${_fmtN(Math.round(Number(lr.price_krw) / Number(lr.room_count)))}만원` : "";
        const metrics = [
          lr.room_count != null && Number(lr.room_count) > 0
            ? `객실 ${_fmtN(lr.room_count)}실${wholeRoomPriceText ? ` · ${wholeRoomPriceText}` : ""}`
            : "객실 정보 없음",
          b.tot_pkng_cnt != null ? `주차 ${_fmtN(b.tot_pkng_cnt)}대` : "주차 정보 없음",
          b.plat_area != null ? `대지 ${(Number(b.plat_area) / 3.305785).toFixed(1)}평` : "대지 정보 없음",
          b.tot_area != null ? `연면적 ${(Number(b.tot_area) / 3.305785).toFixed(1)}평` : "연면적 정보 없음",
        ];
        const finance = financeVisible
          ? `실인수가 ${acquisition != null ? _fmtN(Math.round(acquisition)) + "만원" : "-"} · 융자 ${lr.has_succession_loan ? _fmtN(loan) + "만원" : "없음"} · 권리금 ${lr.has_key_money ? _fmtN(keyMoney) + "만원" : "없음"}`
          : `실인수가 🔒 로그인하고 보기 · 융자${lr.has_succession_loan ? " 🔒 로그인하고 보기" : " 없음"} · 권리금${lr.has_key_money ? " 🔒 로그인하고 보기" : " 없음"}`;
        const revenue = lr.has_monthly_revenue
          ? (financeVisible ? `월 매출 ${_fmtN(lr.monthly_revenue_krw)}만원` : "월 매출 🔒 로그인하고 보기")
          : "";
        const nearby = (_wholeLocationContext || {}).nearby_lodgings || {};
        const nearbyTotal = Number(nearby["일반"] || 0) + Number(nearby["관광"] || 0)
          + Number(nearby["복합"] || 0) + Number(nearby["생활"] || 0);
        const subway = (_wholeLocationContext || {}).subway;
        const stationName = subway && (subway.station_name || subway.name);
        const locationText = _wholeLocationContext
          ? `경쟁업소 ${_fmtN(nearbyTotal)}곳${stationName && subway.walk_minutes != null ? ` · ${stationName}까지 도보 약 ${_fmtN(subway.walk_minutes)}분` : ""}`
          : "입지정보 불러오는 중…";
        const badges = [
          _urgentBadgeMarkup(lr),
          isRecentClosure ? '<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:#E5E5E5;color:#222;font-size:10px;font-weight:800;">최근 폐업</span>' : "",
           lr.has_monthly_revenue ? '<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:#E7F2FC;color:#275B88;font-size:10px;font-weight:800;">매출정보 있음</span>' : "",
           _operationRatioMarkup(lr)
        ].filter(Boolean).join(" ");
        return `<div class="b-listing-card b-whole-listing-card" data-listing-id="${lrId}" style="border-color:var(--brass,#B4863F);">
          <div class="b-listing-info listing-card-trigger" role="button" tabindex="0" data-lrid="${lrId}" aria-label="건물전체 매물 카드로 보기">
             <div class="b-listing-l1">${_lodgingBadge(lr.lodging_type || b.lodging_type, lr.lodging_subtype || b.lodging_subtype)}<span style="display:inline-block;margin-right:5px;padding:1px 6px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;">건물전체</span>${dt}${escapeHtml(bName)}${_permitBadgeMarkup(lr)}${_operationStatusHtml(lr)}</div>
             <div class="b-listing-l2">${escapeHtml(_listingPriceText(lr, _fmtN))}</div>
            <div style="font-size:12px;font-weight:700;color:var(--brass-dark,#7D4A00);margin:4px 0;">${escapeHtml(finance)}${revenue ? ` · ${escapeHtml(revenue)}` : ""}</div>
            <div style="font-size:11.5px;color:var(--ink-soft);line-height:1.55;">${escapeHtml(metrics[0])} · ${escapeHtml(metrics[1])}<br>${escapeHtml(metrics[2])} · ${escapeHtml(metrics[3])}</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin:5px 0;">${badges}</div>
            <div class="b-whole-location" style="font-size:11px;color:var(--ink-soft);">${escapeHtml(locationText)}</div>
             ${approximateLocationButton}
            <div class="b-whole-viewers" style="font-size:11px;font-weight:700;color:#356212;margin-top:3px;">최근 열람 ${_fmtN(lr.viewer_count || 0)}명</div>
            <div style="border-top:1px solid var(--line,#ddd);margin-top:6px;padding-top:6px;color:var(--ink-soft);font-size:10.5px;line-height:1.45;">※ 실제 인수금은 거래금액·승계융자·권리금·부대비용 기준의 참고값입니다.</div>
            <div class="b-listing-l4">
              ${lr.listing_number ? `<span class="b-listing-number">${escapeHtml(lr.listing_number)}</span>` : ""}
              <span>${escapeHtml(lr.listing_date || "")}</span>
              <span class="b-listing-actions">
                <button type="button" class="listing-like-btn${lr.liked ? " is-liked" : ""}" data-lrid="${lrId}" title="찜">${window.LivingstayListingIcons.heart(!!lr.liked)}<span class="like-cnt">${lr.like_count || 0}</span></button>
                <button type="button" class="listing-chat-btn" data-lrid="${lrId}" title="문의하기">${window.LivingstayListingIcons.chat()}</button>
                <button type="button" class="listing-share-btn" data-lrid="${lrId}" title="링크 공유">${window.LivingstayListingIcons.share()}</button>
              </span>
            </div>
          </div>
          <button type="button" class="b-listing-photo-btn listing-photo-btn" data-lrid="${lrId}" aria-label="건물전체 매물 카드로 보기">${photoHtml}${window.LivingstayListingIcons.photoCount(photoCount)}</button>
        </div>`;
      }

      const cards = listings.map((lr) => {
        const lrId = lr.id;
        const isNew = lr.listing_date && ((now - new Date(lr.listing_date + "T00:00:00").getTime()) < THREE_DAYS_MS);
        const newBadge = isNew ? `<span style="display:inline-block;font-size:9px;font-weight:800;color:#fff;background:#E03333;border-radius:3px;padding:1px 4px;margin-left:4px;vertical-align:middle;">NEW</span>` : "";
        const dt = _dealTypeBadge(lr.deal_type);
        const isWholeListing = lr.is_whole_listing || lr.transaction_target === "whole";
        const sqm = !isWholeListing && lr.area_sqm ? parseFloat(lr.area_sqm).toFixed(1) + "㎡" : "";
        const priceText = _listingPriceText(lr, _fmtN);
        const floorValue = lr.floor ?? lr.floor_no ?? lr.floor_number;
        const floorText = floorValue != null && String(floorValue).trim() ? String(floorValue).trim() + "층" : "";
        const roomText = !isWholeListing && !lr.is_business_listing && lr.room_count != null && Number(lr.room_count) > 0
          ? `총 ${_fmtN(lr.room_count)}실` : "";
        const yieldText = lr.yield_rate != null ? `수익률 ${parseFloat(lr.yield_rate).toFixed(1)}%` : "";
        const statusText = _operationStatusText(lr);
        const desc = lr.description ? lr.description.slice(0, 50) + (lr.description.length > 50 ? "…" : "") : "";
        const detailText = [sqm, floorText, roomText, yieldText, statusText, desc].filter(Boolean).join(" · ") || "-";
        const likeCount = lr.like_count || 0;
        const photos = Array.isArray(lr.photos) ? lr.photos.filter(Boolean) : [];
        const photoSrc = photos[0] ? escapeHtml(photos[0]) : null;
        const photoHtml = photoSrc
          ? `<img src="${photoSrc}" alt="매물 사진" onerror="this.parentElement.innerHTML=window.Icons.home(40)">`
          : Icons.home(40);
        if (isWholeListing) {
          return _wholeListingCard(lr, lrId, photoHtml, photos.length, dt);
        }
        return `<div class="b-listing-card" data-listing-id="${lrId}">
          <div class="b-listing-info listing-card-trigger" role="button" tabindex="0" data-lrid="${lrId}" aria-label="매물 카드로 보기">
            <div class="b-listing-l1">${_lodgingBadge(lr.lodging_type || b.lodging_type, lr.lodging_subtype || b.lodging_subtype)}${isWholeListing ? '<span style="display:inline-block;margin-right:5px;padding:1px 6px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;">건물전체</span>' : ""}${escapeHtml(bName)}${newBadge}${_permitBadgeMarkup(lr)}</div>
            <div class="b-listing-l2">${dt}${escapeHtml(priceText)}</div>
            <div class="b-listing-l3" title="${escapeHtml(detailText)}">${escapeHtml(detailText)}${_operationRatioMarkup(lr)}</div>
            <div class="b-listing-l4">
              ${lr.listing_number ? `<span class="b-listing-number">${escapeHtml(lr.listing_number)}</span>` : ""}
              <span>${escapeHtml(lr.listing_date || "")}</span>
              <span class="b-listing-actions">
                <button type="button" class="listing-like-btn${lr.liked ? " is-liked" : ""}" data-lrid="${lrId}" title="찜">${window.LivingstayListingIcons.heart(!!lr.liked)}<span class="like-cnt">${likeCount}</span></button>
                <button type="button" class="listing-chat-btn" data-lrid="${lrId}" title="문의하기">${window.LivingstayListingIcons.chat()}</button>
                <button type="button" class="listing-share-btn" data-lrid="${lrId}" title="링크 공유">${window.LivingstayListingIcons.share()}</button>
              </span>
            </div>
          </div>
          <button type="button" class="b-listing-photo-btn listing-photo-btn" data-lrid="${lrId}" aria-label="매물 카드로 보기">${photoHtml}${window.LivingstayListingIcons.photoCount(photos.length)}</button>
        </div>`;
      }).join("");

      const emptyMessage = !listings.length
        ? `<div style="padding:12px 4px;color:var(--ink-soft);font-size:12px;">현재 급매 매물이 없습니다.</div>`
        : cards;
      listingsBody.innerHTML = `<div style="margin-bottom:8px;">${sortBar}</div><div>${emptyMessage}</div><div style="font-size:11px;color:var(--ink-soft);line-height:1.6;margin-top:6px;">직거래 시 계약 전 등기부등본 확인을 권장합니다.</div>`;
      const wholeListingIds = listings
        .filter(lr => (lr.is_whole_listing || lr.transaction_target === "whole")
          && !_trackedWholeListingViews.has(lr.id))
        .map(lr => lr.id);
      if (wholeListingIds.length) {
        wholeListingIds.forEach(id => _trackedWholeListingViews.add(id));
            wholeListingIds.forEach(id => _liveWholeListingViews.add(id));
            _startWholeViewerRefresh();
        fetch("/api/listings/views", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ listing_ids: wholeListingIds }),
        })
          .then(res => res.json().then(data => ({ ok: res.ok, data })))
          .then(({ ok, data }) => {
            if (!ok || !data.ok) throw new Error("view record failed");
            (data.items || []).forEach(item => {
              listingsBody.querySelectorAll(`[data-listing-id="${item.id}"]`).forEach(card => {
                const count = card.querySelector(".b-whole-viewers");
                if (count) count.textContent = `최근 열람 ${_fmtN(item.viewer_count || 0)}명`;
              });
            });
            _refreshWholeViewerCounts();
          })
          .catch(() => wholeListingIds.forEach(id => _trackedWholeListingViews.delete(id)));
      }

      listingsBody.querySelectorAll("[data-lsort]").forEach(btn => {
        btn.addEventListener("click", () => {
          _lsSort = btn.dataset.lsort;
          let sorted = _urgentOnly
            ? allListings.filter(_isUrgentListing)
            : [...allListings];
          if (_lsSort === "price") sorted.sort((a,b)=>(
            (a.is_business_listing ? a.room_price_min : a.price_krw) || 0
          ) - (
            (b.is_business_listing ? b.room_price_min : b.price_krw) || 0
          ));
          else if (_lsSort === "yield") sorted.sort((a,b)=>(b.yield_rate||0)-(a.yield_rate||0));
          else sorted.sort((a,b)=>new Date(b.listing_date)-new Date(a.listing_date));
          _renderListings(sorted);
        });
      });
      // 급매 필터 버튼
      const urgentFilterBtn = listingsBody.querySelector("#lsUrgentFilter");
      if (urgentFilterBtn) {
        urgentFilterBtn.addEventListener("click", () => {
          _urgentOnly = !_urgentOnly;
          const base = _urgentOnly
            ? allListings.filter(_isUrgentListing)
            : [...allListings];
          _renderListings(base);
        });
      }
      // listing card click: 모바일에서 액션 버튼 외 카드 전체를 공용 listing modal로 연다.
      listingsBody.querySelectorAll(".b-listing-card").forEach(card => {
        card.addEventListener("click", (e) => {
          if (window.innerWidth > 520) return;
          if (e.target.closest(".b-listing-actions button")) return;
          const lr = listings.find(item => String(item.id) === String(card.dataset.listingId));
          if (lr) _openDirectListingCard(lr);
        });
      });
      listingsBody.querySelectorAll(".listing-photo-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
          if (window.innerWidth <= 520) return;
          e.stopPropagation();
          const lr = listings.find(item => String(item.id) === String(btn.dataset.lrid));
          if (lr) _openDirectListingCard(lr);
        });
      });
      listingsBody.querySelectorAll(".listing-card-trigger").forEach(trigger => {
        const openRow = () => {
          const lr = listings.find(item => String(item.id) === String(trigger.dataset.lrid));
          if (lr) _openDirectListingCard(lr);
        };
        trigger.addEventListener("click", () => {
          if (window.innerWidth <= 520) return;
          openRow();
        });
       listingsBody.querySelectorAll(".b-approx-location-btn").forEach(btn => {
         btn.addEventListener("click", (event) => {
           event.stopPropagation();
           if (typeof window.openApproximateLocationMap === "function") {
             window.openApproximateLocationMap(Number(btn.dataset.lat), Number(btn.dataset.lng), btn);
           }
         });
       });
        trigger.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openRow();
          }
        });
      });
      listingsBody.querySelectorAll(".listing-chat-btn").forEach(btn => {
        btn.addEventListener("click", (e) => { e.stopPropagation(); _openListingChat(parseInt(btn.dataset.lrid, 10)); });
      });
      listingsBody.querySelectorAll(".listing-share-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const shareOrigin = (window.LIVINGSTAY_PUBLIC_BASE_URL || location.origin).replace(/\/+$/, "");
          const shareUrl = new URL(`/building/${encodeURIComponent(b.building_id)}`, shareOrigin);
          shareUrl.searchParams.set("listing", String(btn.dataset.lrid));
          const url = shareUrl.toString();
          const shareData = { title: `${bName} 직거래 매물 | 홈앤스테이`, text: `${bName} 직거래 매물`, url };
          try {
            if (navigator.share) {
              await navigator.share(shareData);
              return;
            }
            if (navigator.clipboard) {
              await navigator.clipboard.writeText(url);
              const previous = btn.textContent;
              btn.textContent = "✓";
              setTimeout(() => { if (btn.isConnected) btn.textContent = previous; }, 1400);
              return;
            }
          } catch (err) {
            if (err && err.name === "AbortError") return;
          }
          prompt("아래 매물 링크를 복사하세요:", url);
        });
      });
      listingsBody.querySelectorAll(".listing-like-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const lrid = parseInt(btn.dataset.lrid, 10);
          try {
            const res = await fetch(`/api/listing-requests/${lrid}/like`, {method:"POST",credentials:"same-origin"});
            const d = await res.json().catch(()=>({}));
            if (res.ok && d.ok){
              btn.classList.toggle("is-liked", !!d.liked);
              const cnt = btn.querySelector(".like-cnt");
              if (cnt) cnt.textContent = d.like_count;
              const oldIcon = btn.querySelector(".listing-icon");
              if (oldIcon) oldIcon.replaceWith(document.createRange().createContextualFragment(window.LivingstayListingIcons.heart(!!d.liked)));
            }
          } catch(e){}
        });
      });
    }
    _renderListings(allListings);
    if (allListings.some(lr => lr.is_whole_listing || lr.transaction_target === "whole") && b.building_id) {
      fetch(`/api/building/${encodeURIComponent(b.building_id)}/whole-listing-context`, {credentials:"same-origin"})
        .then(res => res.json().then(data => ({ok: res.ok, data})))
        .then(({ok, data}) => {
          if (!ok || !data.ok) throw new Error("location context failed");
          _wholeLocationContext = data;
          _renderListings(allListings);
        })
        .catch(() => {
          _wholeLocationContext = {nearby_lodgings: {}, subway: null};
          _renderListings(allListings);
        });
    }

    // ?listing=ID 로 진입 시 해당 매물 카드로 자동 스크롤 + 2초 하이라이트
    const _targetListing = new URLSearchParams(location.search).get("listing");
    if (_targetListing) {
      requestAnimationFrame(() => {
        const el = listingsCard && listingsCard.querySelector(`[data-listing-id="${_targetListing}"]`);
        const targetListing = allListings.find(item => String(item.id) === String(_targetListing));
        if (el && targetListing) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.style.background = "var(--brass-tint, #FFF5E0)";
          setTimeout(() => { el.style.background = ""; }, 2000);
          _openDirectListingCard(targetListing);
        }
      });
    }
  }

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

  // 헤더 액션 버튼 배선 — 관심저장/숙박알리미 통합 알림/공유
  const signalBtn = document.getElementById("bSignalBtn");
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
  let detailFavorite = null;
  let detailSignalEnabled = false;
  async function loadDetailFavorite(){
    if (!window.__livingstayLoggedIn) return null;
    try {
      const res = await fetch("/api/favorites/mine", { credentials: "same-origin" });
      const data = await res.json();
      const items = data.items || [];
      return items.find(item =>
        (item.master_building_id != null && Number(item.master_building_id) === Number(b.building_id)) ||
        (`${item.building_name}|${item.address}` === favKeyStr)
      ) || null;
    } catch(e){ return null; }
  }
  function syncSignalBtn(){
    if (!signalBtn) return;
    signalBtn.dataset.enabled = detailSignalEnabled ? "true" : "false";
    signalBtn.classList.toggle("on", detailSignalEnabled);
    signalBtn.style.background = detailSignalEnabled ? "#FFF8EE" : "none";
    const label = signalBtn.querySelector(".b-signal-label");
    if (label) label.textContent = detailSignalEnabled ? "🔔 숙박알리미 켜짐" : "🔔 숙박알리미 받기";
  }
  // 헤더 알림 새로고침(refreshAlertsUI) 시 현재 열린 B패널도 최신 상태를 반영한다.
  window.__syncOpenAlertBtn = function(){
    if (canFav) loadDetailFavorite().then(item => {
      detailFavorite = item;
      detailSignalEnabled = !!(item && item.urgent_alert_enabled &&
        item.new_listing_alert_enabled && item.permit_change_alert_enabled &&
        item.favorite_increase_alert_enabled && item.nearby_change_alert_enabled);
      syncSignalBtn();
    });
  };
  if (canFav){
    window.__syncOpenFavBtn = syncFavBtn;
    syncFavBtn();
    loadDetailFavorite().then(item => {
      detailFavorite = item;
      detailSignalEnabled = !!(item && item.urgent_alert_enabled &&
        item.new_listing_alert_enabled && item.permit_change_alert_enabled &&
        item.favorite_increase_alert_enabled && item.nearby_change_alert_enabled);
      syncSignalBtn();
    });
    favBtn.addEventListener("click", () => {
      const wasFav = isFav(favItem);
      const ok = toggleFav(favItem);
      if (ok !== false) {
        syncFavBtn();
        if (wasFav) {
          // 관심단지를 해제하면 통합 알림도 함께 사용할 수 없으므로 화면 상태를 즉시 초기화한다.
          detailFavorite = null;
          detailSignalEnabled = false;
          syncSignalBtn();
        }
      }
    });
    signalBtn.addEventListener("click", async () => {
      if (window.__livingstayAccountType && window.__livingstayAccountType !== "user"){
        alert("숙박알리미는 일반회원 전용 기능입니다."); return;
      }
      if (!window.__livingstayLoggedIn){ promptLogin("로그인하고 숙박알리미를 받아보세요."); return; }
      if (signalBtn.disabled) return;
      const wasOn = detailSignalEnabled;
      signalBtn.disabled = true;
      try {
        let favorite = detailFavorite || await loadDetailFavorite();
        if (!favorite && !wasOn){
          const addRes = await fetch("/api/favorites/mine", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(favItem)
          });
          const addData = await addRes.json().catch(() => ({}));
          if (!addRes.ok || !addData.ok) throw new Error(addData.message || "favorite");
          favorite = await loadDetailFavorite();
        }
        if (!favorite || !favorite.favorite_id) throw new Error("favorite");
        const res = await fetch("/api/favorites/mine/signal-alert", {
          method: wasOn ? "DELETE" : "PUT", credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ favorite_id: favorite.favorite_id, building_id: b.building_id })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) throw new Error(data.message || "signal");
        detailSignalEnabled = !wasOn;
        detailFavorite = Object.assign({}, favorite, {
          urgent_alert_enabled: detailSignalEnabled,
          new_listing_alert_enabled: detailSignalEnabled,
          permit_change_alert_enabled: detailSignalEnabled,
          favorite_increase_alert_enabled: detailSignalEnabled,
          nearby_change_alert_enabled: detailSignalEnabled
        });
        if (detailSignalEnabled) addFavoriteFirst(favKeyStr);
        else serverFavKeys.delete(favKeyStr);
        syncSignalBtn(); syncFavBtn();
      } catch(e) {
        alert(e.message || "숙박알리미 설정에 실패했습니다. 잠시 후 다시 시도해주세요.");
      } finally {
        signalBtn.disabled = false;
      }
    });
  } else {
    [favBtn, signalBtn].forEach(btn => {
      btn.disabled = true;
      btn.classList.add("disabled");
      btn.title = "주소 정보가 있는 건물만 이용할 수 있습니다";
    });
  }
  shareBtn.addEventListener("click", async () => {
    const url = location.href;
    const shareData = { title: `${bName} | 숙박시설은 홈앤스테이`, url };
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
  const mapLocBtn = document.getElementById("bMapBtn");
  if (mapLocBtn){
    mapLocBtn.addEventListener("click", () => {
      if (!kakaoMap || b.lat == null || b.lng == null) return;
      const targetBuildingId = Number(b.building_id ?? id);
      if (!Number.isInteger(targetBuildingId) || targetBuildingId <= 0) return;
      const closeDetailOnMobile = window.matchMedia("(max-width: 980px)").matches;
      if (closeDetailOnMobile){
        history.pushState({}, "", "/");
        if (typeof gtag === "function") gtag("event", "page_view", { page_path: "/" });
        restoreDefaultPanel();
        closeMapSearchbar();
      }
      setMapLocationTarget(targetBuildingId);
      // level 3 = 개별마커 모드(_clusterModeForLevel 기준), 클러스터 단계 생략
      kakaoMap.setLevel(3);
      kakaoMap.setCenter(new kakao.maps.LatLng(b.lat, b.lng));
      // 지도위치 이동은 특정 건물 하나만 조회하지 않는다. 기존 검색어만
      // 제외하고 현재 지역·숙박유형 필터의 전체 포인트를 다시 표시해야
      // 주변 포인트가 사라지지 않는다.
      const locationMapFilters = Object.assign({}, mapFiltersFromState());
      delete locationMapFilters.q;
      Promise.resolve(updateMapForZoom(locationMapFilters, { force: true })).then(
        applyMapLocationTarget,
        (error) => {
          console.error("[MAP] 선택 건물 마커 재조회 실패:", error);
        },
      );
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

  const lodgings = Array.isArray(b.lodgings) ? b.lodgings : [];
  if (isPreCompletion) {
    adminCard.innerHTML = STRUCTURE_B_TYPES.includes(b.lodging_type) ? `
      <div class="side-card-title">영업신고 <span class="side-sub">행정운영</span></div>
      <div style="font-size:12.5px;color:var(--ink);">
        영업 중 ${lodgings.length.toLocaleString("ko-KR")}개 사업장 신고 완료
      </div>` : `
      <div class="side-card-title">행정운영 <span class="side-sub">숙박업영업신고</span></div>
      <div class="side-empty">준공 전입니다. 사용승인 후 영업신고 정보가 표시됩니다.</div>
    `;

    // 타임라인은 _renderDetailCards()가 담당 (폴링 갱신과 공유)
  } else {
    // [2] 행정운영 표 — 확인된 영업신고 데이터(영업/정상만) 기반.
    //     일반숙박은 건축물대장 호실수와 객실수가 비교 대상이 아니므로 절대 객실수만 표시한다.
    const roomTotal = Number(b.lodging_room_total || 0);
    const usesAbsoluteRoomMetric = b.lodging_metric === "room_count";
    let rateDisplay;
    const _adminUnits = b.units != null ? Number(b.units) : 0;
    if (usesAbsoluteRoomMetric) {
      rateDisplay = `${roomTotal.toLocaleString('ko-KR')}실 (현재 영업중 ${lodgings.length}개 사업장)`;
    } else if (b.lodging_report_rate != null){
      rateDisplay = Number(Number(b.lodging_report_rate).toFixed(1)).toLocaleString('ko-KR') + "%";
    } else if (roomTotal > 0 && _adminUnits > 0){
      // lodging_room_total(정상영업 신고객실수)로 즉석 계산 — 헤더 신고율과 동일 소스
      rateDisplay = Number((roomTotal * 100 / _adminUnits).toFixed(1)).toLocaleString('ko-KR') + "%";
    } else if (_adminUnits > 0 && lodgings.length === 0){
      rateDisplay = "0%";
    } else {
      rateDisplay = "확인 불가";
    }
    const reportedRooms = roomTotal > 0 ? roomTotal.toLocaleString('ko-KR') + "실" : "-";
    const notReported = (!usesAbsoluteRoomMetric && b.units != null && Number(b.units) > 0)
      ? Math.max(Number(b.units) - roomTotal, 0).toLocaleString('ko-KR') + "실"
      : "-";
    // 영업신고 업종 → 상세페이지 용도 뱃지 매핑
    function _hygieneBadge(hygiene) {
      const MAP = {
        "숙박업(생활)":         ["생숙", "#378ADD", "#fff"],
        "생활숙박업":           ["생숙", "#378ADD", "#fff"],
        "생활숙박시설":         ["생숙", "#378ADD", "#fff"],
        "관광숙박업":           ["관광", LODGING_COLORS["관광"], "#fff"],
        "관광호텔업":           ["관광", LODGING_COLORS["관광"], "#fff"],
        "휴양콘도미니엄업":       ["관광", LODGING_COLORS["관광"], "#fff"],
        "가족호텔업":            ["관광", LODGING_COLORS["관광"], "#fff"],
        "소형호텔업":            ["관광", LODGING_COLORS["관광"], "#fff"],
        "한국전통호텔업":         ["관광", LODGING_COLORS["관광"], "#fff"],
        "의료관광호텔업":         ["관광", LODGING_COLORS["관광"], "#fff"],
        "일반숙박업":            ["일반", "#D46BA3", "#fff"],
        "숙박업(일반)":           ["일반", "#D46BA3", "#fff"],
        "일반호텔":              ["일반", "#D46BA3", "#fff"],
        "여관업":                ["일반", "#D46BA3", "#fff"],
        "여인숙업":              ["일반", "#D46BA3", "#fff"],
        "외국인관광도시민박업":     ["에어비앤비", "#FF5A5F", "#fff"],
        "농어촌민박업":           ["농어촌민박", "#8BC34A", "#333"],
        "야영장업":              ["캠핑", "#795548", "#fff"],
        "일반야영장업":           ["캠핑", "#795548", "#fff"],
        "한옥체험업":            ["한옥", "#FF8F00", "#fff"],
      };
      const found = MAP[String(hygiene || "").trim()] || ["기타", "#999", "#fff"];
      return `<span style="display:inline-block;font-size:10px;font-weight:700;line-height:1.25;
                            padding:1px 6px;border-radius:10px;white-space:nowrap;margin-right:4px;
                            background:${found[1]};color:${found[2]};">${found[0]}</span>`;
    }

    // 영업신고 사업장 목록 — 서버가 이미 등록운영업체(priority 순) → 미등록(랜덤)으로 정렬해서 내려줌
    const lodgingRows = lodgings.map((l) => {
      const badge = _hygieneBadge(l.hygiene_type);
      const representativeTag = l.building_name_representative
        ? `<span title="건물 대표 명칭으로 표시 중인 최다 객실 영업신고" style="font-size:10px;font-weight:700;color:#386641;white-space:nowrap;margin-right:4px;">(최다)</span>`
        : "";
      const name = l.registered && l.operator_slug
        ? `<a href="/operator/${encodeURIComponent(l.operator_slug)}?building_id=${b.building_id}&building_name=${encodeURIComponent(b.building_name||"")}" style="display:inline-block; font-size:12.5px; font-weight:700; color:#fff; background:var(--brass-dark); border-radius:5px; padding:2px 8px; text-decoration:none;">${escapeHtml(l.biz_name)}</a>`
        : escapeHtml(l.biz_name);
      const rooms = (l.room_count != null && Number(l.room_count) > 0)
        ? Number(l.room_count).toLocaleString('ko-KR') + "실" : "-";
      return `<tr>
        <td style="text-align:left;vertical-align:middle;padding:3px 0;">${badge}${representativeTag}${name}</td>
        <td style="white-space:nowrap;vertical-align:middle;padding:3px 0;">${rooms}</td>
      </tr>`;
    }).join("");
    const lodgingListHtml = lodgings.length
      ? `<div style="font-size:12px; font-weight:700; color:var(--ink-soft); margin:10px 0 4px;">영업 중 신고업소 ${lodgings.length}곳</div>
         <table class="b-info-table" style="margin-bottom:12px;">
           <thead><tr><th style="text-align:left;">영업상호명</th><th style="white-space:nowrap;">객실수</th></tr></thead>
           <tbody>${lodgingRows}</tbody>
         </table>`
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
          ${usesAbsoluteRoomMetric
            ? `<tr><th>정상영업 신고객실수</th><td>${rateDisplay}</td></tr>`
            : `<tr><th>신고율</th><td>${rateDisplay}</td></tr>
               <tr><th>호실수</th><td>${units}</td></tr>
               <tr><th>신고</th><td>${reportedRooms}</td></tr>
               <tr><th>미신고</th><td>${notReported}</td></tr>`}
          <tr><th>담당부처</th><td>${deptCell}</td></tr>
          <tr><th>연락처</th><td>${phoneCell}</td></tr>
        </tbody>
      </table>
      ${lodgingListHtml}
      ${(Array.isArray(b.booking_urls) && b.booking_urls.length > 0) ? (() => {
        const btns = b.booking_urls
          .map(bu => ({...bu, safe_url: _publicHttpUrl(bu.url)}))
          .filter(bu => bu.safe_url)
          .map(bu =>
          `<a href="${escapeHtml(bu.safe_url)}" target="_blank" rel="noopener noreferrer"
              style="display:inline-block; font-size:12.5px; font-weight:700; color:#fff;
                     background:#1a7a3c; border-radius:6px; padding:4px 12px;
                     text-decoration:none; white-space:nowrap; margin:3px 0;">${escapeHtml(bu.platform)}</a>`
        ).join(" ");
        return `<div style="font-size:12px; font-weight:700; color:var(--ink-soft); margin:6px 0 5px;">OTA 예약 링크</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px;">${btns}</div>`;
      })() : ""}
      ${STRUCTURE_A_TYPES.includes(b.lodging_type) ? `<a href="https://jnjclub.co.kr/" target="_blank" rel="noopener noreferrer" style="display:block; margin-top:0;" title="숙박업등록·위탁운영 무료 상담 신청">
        <img src="/static/banner_biz_report.png" alt="우수부동산서비스인증 — 숙박업등록·위탁운영 의뢰하기, 무료 상담 신청" style="display:block; width:100%; height:auto; border-radius:10px;" />
      </a>` : ""}`;
  }

  const lodgingOperatorTypes = ["캠핑", "에어비앤비", "농어촌민박", "한옥", "생활"];
  const showTransactions = STRUCTURE_A_TYPES.includes(b.lodging_type)
    || STRUCTURE_B_TYPES.includes(b.lodging_type);
  ["bAreaFilterCard", "bTrendCard", "bTxCard"].forEach(cardId => {
    const card = document.getElementById(cardId);
    if (card) card.style.display = showTransactions ? "" : "none";
  });
  _renderCampingSection(b);
  renderBuildingLodgingOperators(b.lodging_operators || [], b.lodging_type);
  renderBuildingAgents(showTransactions ? (b.agents || (b.agent ? [b.agent] : [])) : [], b.more_agents || [], id, bName, b.building_status);

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
  _renderDetailCards(b, id);
  if (!b.detail_fetched_at
      && b.sgg_cd && b.umd_nm && b.jibun) {
    _startDetailPoll(id);
  }

  return b.building_status || "완공";
}

// 상거래정보 카드 — /api/building/<id>/nearby-stores 로 이 건물(지번)의
// 상가업소를 업종별 요약 + 층별 목록으로 그린다. 최대 15개 먼저 보여주고 "더보기".
async function loadBuildingStores(buildingId){
  const requestToken = _buildingDetailRequestToken;
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
    if (!_isActiveBuilding(buildingId, requestToken)) return;
    if (!data.pending) break;
    if (_poll < 4) await new Promise(r => setTimeout(r, 4000));
    if (!_isActiveBuilding(buildingId, requestToken)) return;
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

// 운영지원업체 카드 — 단지뱃지를 우선하고 지역뱃지로 보충한 모든 지원 업종을 표시한다.
function renderBuildingOperators(operatorByCategory, buildingId, buildingName){
  const box = document.getElementById("bOperatorBox");
  const card = document.getElementById("bOperatorSupportCard");
  if (!box) return;
  const all = Array.isArray(operatorByCategory) ? operatorByCategory : [];
  const items = all.filter(it => it && it.company_name);
  if (!items.length){ box.innerHTML = ""; if (card) card.style.display = "none"; return; }
  if (card) card.style.display = "";

  const applyHref = `/apply/operator?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}`;
  box.innerHTML = items.map(it => {
    const categoryLabel = it.category === "위탁운영" ? "위탁" : (it.category || "운영지원");
    const badge = it.tier === "premium" ? Icons.compass(14) : Icons.mapPin(14);
    const nameEl = it.tier === "premium" && it.subdomain_slug
      ? `<a href="/operator/${encodeURIComponent(it.subdomain_slug)}?building_id=${buildingId}&building_name=${encodeURIComponent(buildingName||"")}" style="font-size:13px; font-weight:700; color:var(--ink); text-decoration:none;">${escapeHtml(it.company_name)}</a>`
      : `<span style="font-size:13px; font-weight:600; color:var(--ink);">${escapeHtml(it.company_name)}</span>`;
    return `<div data-operator-category="${escapeHtml(categoryLabel)}" style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 2px; border-bottom:1px solid var(--line,#eee);">
      <span style="font-size:11.5px; color:var(--ink-soft); width:52px; flex-shrink:0; display:inline-flex; align-items:center; gap:3px;">${badge}<span>${escapeHtml(categoryLabel)}</span></span>
      <span style="flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${nameEl}</span>
      ${it.phone ? `<a href="tel:${escapeHtml(it.phone)}" style="font-size:16px; text-decoration:none;" onclick="event.stopPropagation();">📞</a>` : ""}
    </div>`;
  }).join("");
}

// 금융/대출상담 카드 — 지역매칭 상담사 전원 골드 스타일로 바로 노출
function renderBuildingLoanConsultants(consultants, buildingId, buildingName, buildingStatus){
  const box = document.getElementById("bFinanceBox");
  const card = document.getElementById("bFinanceCard");
  if (!box) return;
  const isPreCompletion = buildingStatus && buildingStatus !== "완공";
  const items = Array.isArray(consultants) ? consultants : [];
  const applyHref = `/apply/loan?building_id=${buildingId != null ? encodeURIComponent(buildingId) : ""}&building_name=${encodeURIComponent(buildingName || "")}`;

  if (!items.length){ box.innerHTML = ""; if (card) card.style.display = "none"; return; }
  if (card) card.style.display = "";

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
        <a href="sms:${escapeHtml(c.phone)}" style="font-size:18px;text-decoration:none;display:inline-flex;" onclick="event.stopPropagation();" aria-label="문자">${Icons.messageCircle(17)}</a>
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
  const agentCard = document.getElementById("bAgentCard");
  if (list.length){
    if (agentCard) agentCard.style.display = "";
    // 최대 3명 카드 스택 — 기존 단일 카드 스타일을 세로로 나열 (서버가 priority_score DESC, RANDOM()으로 최대 3명 반환)
    box.innerHTML = list.map((agent) => {
      // 프로필 사진(photo_src)이 없으면 건물 아이콘을 원형 썸네일에 표시한다.
      const avatar = agent.photo_src
        ? `<img src="${escapeHtml(agent.photo_src)}" alt="담당중개사 사진" style="width:44px; height:44px; border-radius:50%; object-fit:cover; border:1px solid var(--line); flex-shrink:0;" onerror="this.outerHTML='<div style=&quot;width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center;&quot;>'+window.Icons.building(18)+'</div>'">`
        : `<div style="width:40px; height:40px; border-radius:50%; background:var(--brass-tint); color:var(--brass-dark); display:flex; align-items:center; justify-content:center;">${Icons.building(18)}</div>`;
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
        ${hasBadge ? `<span style="position:absolute; bottom:0; left:50%; transform:translateX(-50%); display:inline-flex; align-items:center; gap:2px; font-size:9.5px; font-weight:700; color:#fff; background:var(--brass-dark); padding:2px 7px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.3); white-space:nowrap;">${Icons.compass(11)}<span>단지</span></span>` : ""}
        ${isRegion ? `<span style="position:absolute; bottom:0; left:50%; transform:translateX(-50%); display:inline-flex; align-items:center; gap:2px; font-size:9.5px; font-weight:700; color:#fff; background:#9AA5B1; padding:2px 7px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.3); white-space:nowrap;">${Icons.mapPin(11)}<span>지역담당</span></span>` : ""}
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
              <a href="sms:${escapeHtml(agent.phone)}" style="font-size:12px; color:var(--brass-dark); text-decoration:none; display:inline-flex; align-items:center; gap:3px;" onclick="event.stopPropagation();">${Icons.messageCircle(13)}<span>문자</span></a>
            </div>` : ""}
            ${agent.office_phone ? `<div style="font-size:12.5px; color:var(--ink-soft); margin-top:2px;">☎️ ${escapeHtml(window.formatPhone ? formatPhone(agent.office_phone) : agent.office_phone)}</div>` : ""}
          </div>
        </div>
      </div>`;
    }).join("");
  } else {
    // 배정된 중개사 없으면 카드 자체를 숨김 (통합 파트너 배너에서 안내)
    if (agentCard) agentCard.style.display = "none";
    box.innerHTML = "";
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

async function loadBuildingTrend(id, buildingStatus, areaFilter=""){
  const requestToken = _buildingDetailRequestToken;
  const requestSeq = ++_buildingTrendRequestSeq;
  const isCurrent = () =>
    _isActiveBuilding(id, requestToken) && _buildingTrendRequestSeq === requestSeq;
  if (!isCurrent()) return;
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
    const qs = areaFilter ? `&area_sqm=${encodeURIComponent(areaFilter)}` : "";
    const res = await fetch("/api/monthly-trend?building_id=" + id + qs);
    const data = await res.json();
    items = data.items || [];
    granularity = data.granularity || "month";
  } catch(e){ console.error("[상세] 추세 로드 실패:", e); return; }
  if (!isCurrent()) return;

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

async function loadBuildingTx(id, buildingStatus, areaFilter=""){
  const requestToken = _buildingDetailRequestToken;
  const requestSeq = ++_buildingTxRequestSeq;
  const isCurrent = () =>
    _isActiveBuilding(id, requestToken) && _buildingTxRequestSeq === requestSeq;
  if (!isCurrent()) return;
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
  const areaQs = areaFilter ? `&area_sqm=${encodeURIComponent(areaFilter)}` : "";
  let items = [];
  let txTotal = 0;
  const shown = bTxShown;
  try {
    const size = Math.min(shown, 200);
    let page = 1;
    while (true){
      const res = await fetch(`/api/transactions?building_id=${id}&page=${page}&size=${size}&with_total=1${areaQs}`);
      const data = await res.json();
      if (!isCurrent()) return;
      txTotal = data.total || 0;
      const batch = data.items || [];
      items = items.concat(batch);
      if (items.length >= shown || items.length >= txTotal || batch.length < size) break;
      page++;
    }
  } catch(e){
    if (!isCurrent()) return;
    wrap.innerHTML = `<div class="side-empty">실거래 목록을 불러오지 못했습니다.</div>`;
    return;
  }
  if (!isCurrent()) return;
  bTxTotal = txTotal;
  items = items.slice(0, shown);
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

function renderBuildingLodgingOperators(items, lodgingType){
  const card = document.getElementById("bLodgingOperatorCard");
  const box = document.getElementById("bLodgingOperatorBox");
  if (!card || !box) return;
  const typeMap = { "에어비앤비":"airbnb", "캠핑":"camping", "농어촌민박":"rural", "한옥":"hanok", "생활":"living" };
  if (!typeMap[lodgingType]) { card.style.display = "none"; return; }
  card.style.display = "";
  const labels = {airbnb:"에어비앤비 호스트",camping:"캠핑 운영파트너",rural:"농어촌민박 운영자",hanok:"한옥 운영자",living:"생숙 운영자"};
  const safeUrl = value => { try { const url = new URL(value); return ["http:","https:"].includes(url.protocol) ? url.href : null; } catch(e) { return null; } };
  if (!items.length) {
    box.innerHTML = `<div class="side-empty">이 시설 운영자이신가요?<br><a href="/apply/lodging-operator?type=${typeMap[lodgingType]}">운영 파트너 등록하기</a></div>`;
    return;
  }
  box.innerHTML = items.map(op => {
    const url = safeUrl(op.booking_url) || safeUrl(op.airbnb_url) || safeUrl(op.gocamping_url);
    const action = op.booking_url ? "자체 예약 페이지" : op.airbnb_url ? "에어비앤비에서 보기" : "고캠핑에서 예약";
    return `<div style="padding:10px 0;border-bottom:1px solid var(--line)">${op.photo_src ? `<img src="${escapeHtml(op.photo_src)}" alt="" style="width:44px;height:44px;object-fit:cover;border-radius:8px;float:right">` : ""}<b>${escapeHtml(labels[op.lodging_op_type] || "숙박 운영자")}</b><div>${escapeHtml(op.biz_name || "")}</div>${op.intro_text ? `<div style="font-size:12px;color:var(--ink-soft)">${escapeHtml(op.intro_text)}</div>` : ""}<div style="margin-top:6px;display:flex;gap:10px">${op.phone ? `<a href="tel:${escapeHtml(op.phone)}">전화</a><a href="sms:${escapeHtml(op.phone)}">문자</a>` : ""}${url ? `<a target="_blank" rel="noopener noreferrer" href="${escapeHtml(url)}">${action}</a>` : ""}</div></div>`;
  }).join("");
}

// 좌측 패널을 건물 상세로 교체하고 데이터를 채운다.
function renderBuildingPanel(id){
  const panel = document.querySelector(".side-panel");
  if (!panel) return;
  window.__openBuildingId = Number(id);
  _buildingDetailRequestToken += 1;
  clearMapLocationTarget();
  _cancelDetailPoll(); // 이전 건물의 폴링이 살아있으면 즉시 중단
  if (sideTrendChart){ sideTrendChart.destroy(); sideTrendChart = null; }
  if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }

  panel.innerHTML = buildingPanelSkeleton();
  panel.scrollTop = 0;
  panel.classList.remove("panel-collapsed");
  panel.classList.add("open"); // 모바일에서도 상세가 보이도록 패널을 펼친다
  if (typeof window.livingstaySetPanelToggle === "function") {
    window.livingstaySetPanelToggle(true);
  }

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

  // 전용면적 타입 필터 — 변경 시 trend/tx 재로드
  const bAreaFilterEl = document.getElementById("bAreaFilter");
  let _bAreaFilter = "";
  if (bAreaFilterEl){
    bAreaFilterEl.addEventListener("change", () => {
      _bAreaFilter = bAreaFilterEl.value;
      loadBuildingTrend(id, null, _bAreaFilter);
      loadBuildingTx(id, null, _bAreaFilter);
    });
  }

  // 4개 카드를 동시에 시작 — 헤더 응답을 기다리지 않음(B-2 병렬화)
  loadBuildingStores(id);
  loadBuildingTrend(id, null);   // null = 완공 가정으로 즉시 API 시작
  loadBuildingTx(id, null);      // 동일
  const requestToken = _buildingDetailRequestToken;
  loadBuildingHeader(id).then(status => {
    if (!_isActiveBuilding(id, requestToken)) return;
    // 헤더 응답 후 준공전이면 trend/tx를 status 기준으로 덮어씀
    if (status && status !== "완공") {
      loadBuildingTrend(id, status, _bAreaFilter);
      loadBuildingTx(id, status, _bAreaFilter);
    }
    // 전용면적 필터 드롭다운 옵션 채우기 (unit_area_sqms 우선, 없으면 건너뜀)
    if (bAreaFilterEl){
      const _fillAreaFilter = (items) => {
        if (!_isActiveBuilding(id, requestToken)) return;
        if (items.length > 0){
          const prevVal = bAreaFilterEl.value;
          bAreaFilterEl.innerHTML = `<option value="">전체</option>` +
            items.map(it => {
              const label = it.ho_cnt != null ? `${it.sqm}㎡ (${it.ho_cnt}실)` : `${it.sqm}㎡`;
              return `<option value="${it.sqm}">${label}</option>`;
            }).join("");
          if (prevVal) bAreaFilterEl.value = prevVal; // 선택 값 유지
        } else {
          // 전유부 + 실거래 모두 없으면 섹션 숨김
          const sec = bAreaFilterEl.closest("section");
          if (sec) sec.style.display = "none";
        }
      };
      fetch("/api/building/" + id + "/area-types")
        .then(r => r.json()).catch(() => ({}))
        .then(d => {
          if (!_isActiveBuilding(id, requestToken)) return;
          const items = d.items || [];
          _fillAreaFilter(items);
          // ho_cnt가 전부 null이면 백그라운드 populate 중 → 8초 후 재시도
          const allNull = items.length > 0 && items.every(it => it.ho_cnt == null);
          if (allNull){
            setTimeout(() => {
              fetch("/api/building/" + id + "/area-types")
                .then(r => r.json()).catch(() => ({}))
                .then(d2 => {
                  if (!_isActiveBuilding(id, requestToken)) return;
                  const items2 = d2.items || [];
                  if (items2.some(it => it.ho_cnt != null)) _fillAreaFilter(items2);
                });
            }, 8000);
          }
        });
    }
  });
}

// 기본(홈) 좌측 패널로 되돌린다.
function restoreDefaultPanel(){
  const panel = document.querySelector(".side-panel");
  if (!panel) return;
  window.__openBuildingId = null;
  _buildingDetailRequestToken += 1;
  clearMapLocationTarget();
  closeFavOverflowPopover();
  if (buildingDetailChart){ buildingDetailChart.destroy(); buildingDetailChart = null; }
  if (sideTrendChart){ sideTrendChart.destroy(); sideTrendChart = null; }
  panel.classList.remove("panel-collapsed");
  panel.classList.remove("open");
  panel.innerHTML = DEFAULT_SIDE_PANEL_HTML;
  if (typeof window.livingstaySetPanelToggle === "function") {
    const compact = window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
    window.livingstaySetPanelToggle(!compact);
  }
  initDefaultSidePanel();
}

// InfoWindow "상세보기 →" 클릭 → 페이지 이동 없이 패널 전환 + URL만 교체
window.openBuildingDetail = function(id){
  closeFavOverflowPopover();
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
      const bldStr = d.count.toLocaleString("ko-KR") + "개";
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

// 검색창 바로 아래 데이터 규모 지표 — 값은 매 로드마다 서버 집계에서 갱신한다.
async function loadPlatformStats(){
  const platformStats = document.getElementById("platformStats");
  if (!platformStats) return;
  const statKeys = ["building_count", "biz_count", "transaction_count", "listing_count"];
  const statEls = statKeys.map(key =>
    platformStats.querySelector(`[data-platform-stat="${key}"]`)
  );
  if (!statEls.length) return;
  try {
    const res = await fetch("/api/stats/platform-summary", { credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error("platform summary failed");
    const values = statKeys.map(key => data[key]);
    if (values.some(value => !Number.isInteger(value) || value < 0)) {
      throw new Error("invalid platform summary values");
    }
    statEls.forEach((el, index) => {
      if (el) el.textContent = values[index].toLocaleString("ko-KR");
    });
  } catch (e) {
    statEls.forEach(el => { if (el) el.textContent = "—"; });
    console.error("[홈] 데이터 규모 지표 로드 실패:", e);
  }
}

// 최초 로드: 기본 패널 초기화 후, URL이 /building/<id>면 자동으로 상세를 연다.
initDefaultSidePanel();
loadBuildingCountLabel();
(function(){
  const m = location.pathname.match(/^\/building\/(\d+)/);
  if (m) renderBuildingPanel(Number(m[1]));
})();
