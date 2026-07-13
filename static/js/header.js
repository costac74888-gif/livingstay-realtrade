/* header.js — 전 페이지 공용 헤더(로고 + 페이지타이틀 + 알림 드롭다운 + 로그인영역)를
 * 한 곳에서 렌더링한다. 각 페이지는 <header id="siteHeader"></header> 빈 껍데기와
 * (선택) window.PAGE_TITLE 만 두면 되고, 실제 마크업/알림 로직은 여기서 주입한다.
 *
 * 설정값(페이지에서 header.js 로드 전에 지정):
 *   window.PAGE_TITLE          : 헤더 가운데 페이지 제목 (미지정 시 빈 문자열)
 *   window.HEADER_BRAND_INPLACE: true 면 로고를 링크가 아닌 버튼(div)로 렌더 →
 *                                 index.html에서 main.js resetToHome이 제자리 초기화.
 *                                 (미지정/false: 로고 클릭 시 "/"로 이동)
 *
 * auth.js 는 이 파일이 만든 #authArea, #authModal 을 제어하므로 반드시 header.js
 * 이후에 로드되어야 한다. index.html에서는 main.js(#brandHome 참조)보다도 먼저 로드한다.
 */
(function () {
  "use strict";

  var host = document.getElementById("siteHeader");
  if (!host) return;

  var title = (typeof window.PAGE_TITLE === "string") ? window.PAGE_TITLE : "";
  var inplace = !!window.HEADER_BRAND_INPLACE;

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---- 로고(브랜드) : index는 제자리초기화 버튼, 그 외 페이지는 홈 링크 ----
  var brandInner =
    '<img class="brand-mark-img" src="/static/home_stay_logo.png" alt="HOME &amp; STAY">' +
    '<div class="brand-text"><div class="name">홈앤스테이</div></div>';
  var brandHtml = inplace
    ? '<div class="brand" id="brandHome" title="홈으로 (전체 보기)" style="cursor:pointer;">' + brandInner + '</div>'
    : '<a class="brand" id="brandHome" href="/" title="홈으로" style="text-decoration:none;">' + brandInner + '</a>';

  // ---- (지도 페이지 전용) 좌측 '목록' 토글 버튼 — window.HEADER_LEFT_TOGGLE=true 일 때만 ----
  // index.html의 좌측 패널(.side-panel)을 열고닫는다. 모바일에서 지도 위 플로팅 버튼이
  // 지도 컨트롤과 겹치는 문제를 피하려 헤더 좌측(로고 옆)으로 옮긴 것.
  var listToggleHtml = window.HEADER_LEFT_TOGGLE
    ? '<button type="button" class="header-list-toggle" id="btnTogglePanel" aria-label="목록 열기">☰ <span class="htoggle-label">목록</span></button>'
    : '';

  // ---- 헤더 본문 (로고 + 페이지타이틀 + 알림 드롭다운 + 메뉴 + 로그인영역) ----
  // 벨(🔔)은 자주 쓰므로 모바일에서도 항상 노출. 나머지 메뉴(실거래목록/공지/마이페이지/로그인)는
  // 좁은 화면에서 햄버거(☰) 드롭다운(.header-menu)으로 접는다.
  host.innerHTML =
    listToggleHtml +
    brandHtml +
    '<div class="page-title">' + esc(title) + '</div>' +
    '<div class="header-actions">' +
      '<div class="hnav-dropdown" id="alertMenu">' +
        '<button type="button" class="hnav-btn" id="alertMenuBtn" aria-haspopup="true" aria-expanded="false">🔔 <span class="hnav-label">알림</span><span class="notif-badge" id="notifBadge" hidden>0</span> ▾</button>' +
        '<div class="hnav-panel hnav-panel-notif" id="alertMenuPanel" role="menu">' +
          '<div class="notif-head">' +
            '<span class="hnav-panel-title">알림</span>' +
            '<button type="button" class="notif-readall" id="notifReadAll">모두 읽음</button>' +
          '</div>' +
          '<div class="notif-list" id="notifList">' +
            '<div class="notif-empty">로그인하면 관심건물의 새 실거래 알림을 받아볼 수 있어요.</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<button type="button" class="hamburger-btn" id="hamburgerBtn" aria-label="메뉴" aria-haspopup="true" aria-expanded="false">☰</button>' +
      '<div class="header-menu" id="headerMenu">' +
        '<nav class="header-nav">' +
          '<a class="hnav-btn" href="/transactions">📊 <span class="hnav-label">실거래목록</span></a>' +
          '<a class="hnav-btn" href="/notices">📢 <span class="hnav-label">공지사항</span></a>' +
          '<a class="hnav-btn" href="/mypage">👤 <span class="hnav-label">마이페이지</span></a>' +
        '</nav>' +
        '<div class="auth-area" id="authArea"><!-- auth.js가 로그인/로그아웃 상태를 채움 --></div>' +
      '</div>' +
    '</div>';

  // ---- 로그인/회원가입 모달 (auth.js가 제어) — 없을 때만 body에 주입(중복 방지) ----
  if (!document.getElementById("authModal")) {
    var modal = document.createElement("div");
    modal.className = "auth-modal-backdrop";
    modal.id = "authModal";
    modal.style.display = "none";
    modal.innerHTML =
      '<div class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="authModalTitle">' +
        '<button class="auth-modal-close" id="authModalClose" aria-label="닫기">&times;</button>' +
        '<div class="auth-brand">HOME &amp; STAY</div>' +
        '<h2 class="auth-modal-title" id="authModalTitle">로그인</h2>' +
        '<div class="auth-error" id="authError" style="display:none;"></div>' +
        '<form id="authForm" autocomplete="on">' +
          '<div class="auth-field" id="authNameField" style="display:none;">' +
            '<label for="authName">이름</label>' +
            '<input type="text" id="authName" placeholder="이름 또는 닉네임" autocomplete="name" />' +
          '</div>' +
          '<div class="auth-field">' +
            '<label for="authEmail">이메일</label>' +
            '<input type="email" id="authEmail" placeholder="you@example.com" autocomplete="email" required />' +
          '</div>' +
          '<div class="auth-field">' +
            '<label for="authPassword">비밀번호</label>' +
            '<input type="password" id="authPassword" placeholder="비밀번호 (8자 이상)" autocomplete="current-password" required />' +
          '</div>' +
          '<button type="submit" class="auth-submit" id="authSubmit">로그인</button>' +
        '</form>' +
        '<div class="auth-switch">' +
          '<span id="authSwitchText">아직 회원이 아니신가요?</span>' +
          '<a href="#" id="authSwitchLink">회원가입</a>' +
        '</div>' +
        '<div class="auth-divider"><span>또는</span></div>' +
        '<a href="/auth/kakao/start" class="auth-kakao" id="authKakaoBtn">' +
          '<span class="auth-kakao-icon">💬</span> 카카오로 3초 로그인' +
        '</a>' +
      '</div>';
    document.body.appendChild(modal);
  }

  // ---- 헤더 높이를 CSS 변수(--header-h)로 반영 (지도 등 레이아웃 계산용) ----
  function setHeaderH() {
    var h = document.querySelector("header");
    if (h) document.documentElement.style.setProperty("--header-h", h.offsetHeight + "px");
  }
  setHeaderH();
  window.addEventListener("resize", setHeaderH);
  window.addEventListener("load", setHeaderH);

  // ---- (지도 페이지) 좌측 '목록' 토글 — .side-panel 열고닫기 (레이아웃 전용) ----
  var listToggleBtn = document.getElementById("btnTogglePanel");
  if (listToggleBtn) {
    listToggleBtn.addEventListener("click", function () {
      var panel = document.querySelector(".side-panel");
      if (!panel) return;
      var open = panel.classList.toggle("open");
      listToggleBtn.innerHTML = open
        ? '✕ <span class="htoggle-label">닫기</span>'
        : '☰ <span class="htoggle-label">목록</span>';
    });
  }

  // ---- 모바일 햄버거 메뉴 토글 (실거래목록/공지/마이페이지/로그인 묶음) ----
  var hamburgerBtn = document.getElementById("hamburgerBtn");
  var headerMenu = document.getElementById("headerMenu");
  if (hamburgerBtn && headerMenu) {
    hamburgerBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = headerMenu.classList.toggle("open");
      hamburgerBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!headerMenu.contains(e.target) && e.target !== hamburgerBtn) {
        headerMenu.classList.remove("open");
        hamburgerBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  // ---- 알림함(헤더 벨) — 로그인 상태에서만 안읽은 개수 뱃지 + 최근 알림 드롭다운 ----
  var alertMenu = document.getElementById("alertMenu");
  var alertMenuBtn = document.getElementById("alertMenuBtn");
  var notifBadge = document.getElementById("notifBadge");
  var notifList = document.getElementById("notifList");
  var notifReadAll = document.getElementById("notifReadAll");
  var notifPollTimer = null;

  function notifTimeAgo(iso) {
    if (!iso) return "";
    var t = new Date(iso.replace(" ", "T"));
    if (isNaN(t)) return "";
    var s = Math.floor((Date.now() - t.getTime()) / 1000);
    if (s < 60) return "방금 전";
    if (s < 3600) return Math.floor(s / 60) + "분 전";
    if (s < 86400) return Math.floor(s / 3600) + "시간 전";
    if (s < 604800) return Math.floor(s / 86400) + "일 전";
    return (t.getMonth() + 1) + "월 " + t.getDate() + "일";
  }
  function renderNotifBadge(n) {
    if (!notifBadge) return;
    if (n > 0) { notifBadge.textContent = n > 99 ? "99+" : String(n); notifBadge.hidden = false; }
    else { notifBadge.hidden = true; }
  }
  function refreshUnreadCount() {
    if (!window.__livingstayLoggedIn) { renderNotifBadge(0); return; }
    fetch("/api/notifications/unread-count", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.ok) renderNotifBadge(d.count); })
      .catch(function () {});
  }
  function loadNotifList() {
    if (!window.__livingstayLoggedIn) {
      notifList.innerHTML = '<div class="notif-empty">로그인하면 관심건물의 새 실거래 알림을 받아볼 수 있어요.</div>';
      return;
    }
    notifList.innerHTML = '<div class="notif-empty">불러오는 중…</div>';
    fetch("/api/notifications/mine", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) { notifList.innerHTML = '<div class="notif-empty">알림을 불러오지 못했습니다.</div>'; return; }
        var items = d.items || [];
        if (!items.length) { notifList.innerHTML = '<div class="notif-empty">받은 알림이 없습니다.</div>'; return; }
        notifList.innerHTML = items.map(function (it) {
          var cls = "notif-item" + (it.is_read ? "" : " unread");
          return '<div class="' + cls + '" data-id="' + it.id + '" data-bid="' + (it.building_id != null ? it.building_id : "") + '">' +
                   '<div class="notif-title">' + esc(it.title) + '</div>' +
                   (it.body ? '<div class="notif-body">' + esc(it.body) + '</div>' : '') +
                   '<div class="notif-time">' + notifTimeAgo(it.created_at) + '</div>' +
                 '</div>';
        }).join("");
      })
      .catch(function () { notifList.innerHTML = '<div class="notif-empty">알림을 불러오지 못했습니다.</div>'; });
  }

  // 폴링(1분 간격) — auth.js가 로그인/로그아웃 시점에 start/stop 호출.
  window.startNotifPolling = function () {
    refreshUnreadCount();
    if (notifPollTimer) return;
    notifPollTimer = setInterval(refreshUnreadCount, 60000);
  };
  window.stopNotifPolling = function () {
    if (notifPollTimer) { clearInterval(notifPollTimer); notifPollTimer = null; }
    renderNotifBadge(0);
  };

  if (alertMenu && alertMenuBtn) {
    alertMenuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = alertMenu.classList.toggle("open");
      alertMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) loadNotifList();   // 열 때마다 최신 목록 로드
    });
    document.addEventListener("click", function (e) {
      if (!alertMenu.contains(e.target)) {
        alertMenu.classList.remove("open");
        alertMenuBtn.setAttribute("aria-expanded", "false");
      }
    });
    // 항목 클릭 → 읽음 처리 후 해당 건물 상세로 이동.
    notifList.addEventListener("click", function (e) {
      var item = e.target.closest(".notif-item");
      if (!item) return;
      var id = item.getAttribute("data-id");
      var bid = item.getAttribute("data-bid");
      fetch("/api/notifications/mine/read", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: parseInt(id, 10) })
      }).then(function () {
        item.classList.remove("unread");
        refreshUnreadCount();
        if (bid) location.href = "/building/" + bid;
      }).catch(function () { if (bid) location.href = "/building/" + bid; });
    });
    if (notifReadAll) {
      notifReadAll.addEventListener("click", function (e) {
        e.stopPropagation();
        fetch("/api/notifications/mine/read-all", { method: "POST", credentials: "same-origin" })
          .then(function () { loadNotifList(); refreshUnreadCount(); })
          .catch(function () {});
      });
    }
  }
})();
