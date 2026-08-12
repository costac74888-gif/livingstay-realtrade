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
    '<img class="brand-mark-img" src="/static/home_stay_share.png" alt="HOME &amp; STAY">' +
    '<div class="brand-text"><div class="name">홈앤스테이</div></div>';
  var brandHtml = inplace
    ? '<div class="brand" id="brandHome" title="홈으로 (전체 보기)" style="cursor:pointer;">' + brandInner + '</div>'
    : '<a class="brand" id="brandHome" href="/" title="홈으로" style="text-decoration:none;">' + brandInner + '</a>';

  // ---- 헤더 본문 (로고 + 페이지타이틀 + 알림 드롭다운 + 메뉴 + 로그인영역) ----
  // 벨(🔔)은 자주 쓰므로 모바일에서도 항상 노출. 나머지 메뉴(실거래목록/공지/마이페이지/로그인)는
  // 좁은 화면에서 햄버거(☰) 드롭다운(.header-menu)으로 접는다.
  // (지도 '목록' 토글 버튼은 헤더가 아니라 index.html의 지도 위 플로팅 버튼(#btnTogglePanel) —
  //  아래에서 존재할 때만 클릭 핸들러를 바인딩한다.)
  host.innerHTML =
    brandHtml +
    '<div class="page-title">' + esc(title) + '</div>' +
    '<div class="header-actions">' +
      '<button type="button" class="hnav-btn" id="myPriceBtn">🏨 <span class="hnav-label">내건물시세</span></button>' +
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
      // 파트너등록 CTA — 로그인 여부와 무관하게 항상 노출. 모바일(≤520px)에서는
      // 햄버거 → /menu 안에 동일 항목이 있으므로 헤더에서는 숨긴다(CSS .partner-cta).
      '<a class="partner-cta" href="/partner">🤝 파트너등록</a>' +
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
            '<div class="auth-pw-wrap">' +
              '<input type="password" id="authPassword" placeholder="비밀번호 (8자 이상)" autocomplete="current-password" required />' +
              '<button type="button" class="auth-pw-toggle" id="authPwToggle" aria-label="비밀번호 표시" aria-pressed="false" title="비밀번호 표시">👁</button>' +
            '</div>' +
          '</div>' +
          '<label class="auth-remember" id="authRememberRow">' +
            '<input type="checkbox" id="authRemember" /> 로그인 상태 유지 (31일)' +
          '</label>' +
          '<div class="auth-consent" id="authConsent" style="display:none;">' +
            '<div style="background:#fffbf3; border:1px solid #f0ddb0; border-radius:8px; padding:9px 12px; margin-bottom:10px; font-size:12.5px; color:#8a5e1a; line-height:1.55;">' +
              '🎁 회원가입하면 관심단지를 등록하고, 새 실거래가 등록될 때마다 무료로 알림을 받아볼 수 있어요' +
            '</div>' +
            '<label class="auth-consent-row auth-consent-all">' +
              '<input type="checkbox" id="agreeAll" /> <b>전체 동의</b>' +
            '</label>' +
            '<div class="auth-consent-sep"></div>' +
            '<label class="auth-consent-row">' +
              '<input type="checkbox" id="agreeAge14" class="agree-required" /> <span class="agree-tag">[필수]</span> 만 14세 이상입니다' +
            '</label>' +
            '<label class="auth-consent-row">' +
              '<input type="checkbox" id="agreeTerms" class="agree-required" /> <span class="agree-tag">[필수]</span> <a href="/terms" target="_blank" rel="noopener">이용약관</a> 동의' +
            '</label>' +
            '<div class="auth-consent-row auth-consent-privacy">' +
              '<label>' +
                '<input type="checkbox" id="agreePrivacy" class="agree-required" /> <span class="agree-tag">[필수]</span> 개인정보 수집·이용 동의' +
              '</label>' +
              '<button type="button" class="auth-consent-toggle" id="privacyToggle" aria-expanded="false" aria-controls="privacyDetail">펼치기 ▾</button>' +
            '</div>' +
            '<div class="auth-consent-detail" id="privacyDetail" style="display:none;">' +
              '수집항목: 이메일, 비밀번호(암호화 저장), 이름<br/>' +
              '수집목적: 회원 가입 및 본인 확인, 서비스 이용(관심단지 저장·실거래알림 등) 제공<br/>' +
              '보유·이용기간: 회원 탈퇴 시까지(탈퇴 후 관계법령에 따라 필요한 경우 별도 보관)<br/>' +
              '동의 거부 권리 및 불이익: 위 동의는 회원가입을 위한 필수 항목으로, 동의하지 않으실 경우 회원가입이 제한됩니다.<br/>' +
              '<a href="/privacy" target="_blank" rel="noopener">개인정보처리방침 전문</a>' +
            '</div>' +
            '<label class="auth-consent-row">' +
              '<input type="checkbox" id="agreeMarketing" /> <span class="agree-tag agree-tag-opt">[선택]</span> 마케팅 정보(이메일) 수신 동의' +
            '</label>' +
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
        '<div class="auth-partner-link" style="margin-top:14px; padding-top:12px; border-top:1px solid var(--line, #e5e8ec); text-align:center;">' +
          '<a href="/partner" style="font-size:12.5px; color:var(--ink-soft, #6b7684); text-decoration:none;">중개사・운영지원업체이신가요? <b style="color:var(--brass, #B4863F);">파트너 등록 안내 →</b></a>' +
        '</div>' +
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

  // ---- (지도 페이지) '목록' 토글(지도 위 플로팅) — .side-panel 열고닫기 (레이아웃 전용) ----
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
      // 모바일 폭(520px 이하 — 햄버거가 보이는 구간)에서는 드롭다운 대신 전체 메뉴 페이지로 이동.
      // 데스크톱 폭에서는 기존 드롭다운 동작 그대로 유지(변경 없음).
      if (window.matchMedia && window.matchMedia("(max-width: 520px)").matches) {
        window.location.href = "/menu";
        return;
      }
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

  // ── "내건물시세" 버튼 — 다른 페이지에서 클릭 시 메인으로 이동 ──────────
  var myPriceBtn = document.getElementById("myPriceBtn");
  if (myPriceBtn){
    myPriceBtn.addEventListener("click", function(){
      // index.html에선 오버레이 IIFE가 직접 처리(delegated listener)
      // 다른 페이지에서는 메인으로 이동하면서 강제 오픈 파라미터 전달
      if (!document.getElementById("welcomeOverlay")){
        location.href = "/?openMyPrice=1";
      }
    });
  }

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

  // ---- 사이트 팝업/상단배너 (관리자 "팝업관리"에서 등록) ----
  // 서버(/api/popups/active)가 기간·기기·로그인대상을 걸러 1건만 주고,
  // scope(home_only)와 닫기 기록(세션/오늘하루)은 여기서 판단한다.
  function todayStr() {
    var d = new Date();
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }

  function popupDismissed(p) {
    try {
      if (sessionStorage.getItem("popupClosed_" + p.id) === "1") return true;
      if (localStorage.getItem("popupHideDay_" + p.id) === todayStr()) return true;
    } catch (e) { /* 스토리지 차단 환경이면 그냥 보여준다 */ }
    return false;
  }

  function buildPopupImage(p) {
    var img = document.createElement("img");
    img.src = p.image_url;
    img.alt = "안내";
    img.style.cssText = "display:block; width:100%; height:auto;";
    if (!p.link_url) return img;
    var a = document.createElement("a");
    a.href = p.link_url;
    if (p.open_new_tab) { a.target = "_blank"; a.rel = "noopener"; }
    a.appendChild(img);
    return a;
  }

  function dismissBtn(label, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.style.cssText = "background:none; border:none; cursor:pointer; font-size:13px; color:#fff; padding:6px 10px;";
    b.addEventListener("click", onClick);
    return b;
  }

  function showSitePopup(p) {
    var overlay = document.createElement("div");
    overlay.id = "sitePopupOverlay";
    overlay.style.cssText =
      "position:fixed; inset:0; z-index:10050; background:rgba(0,0,0,0.45);" +
      "display:flex; align-items:center; justify-content:center; padding:16px;";
    var box = document.createElement("div");
    box.style.cssText =
      "width:" + p.width_px + "px; max-width:92vw; max-height:88vh; overflow:auto;" +
      "background:#fff; border-radius:8px; box-shadow:0 12px 40px rgba(0,0,0,0.35);";
    box.appendChild(buildPopupImage(p));
    var bar = document.createElement("div");
    bar.style.cssText = "display:flex; justify-content:flex-end; gap:4px; background:#16202E;";
    function remove(hideToday) {
      try {
        if (hideToday) localStorage.setItem("popupHideDay_" + p.id, todayStr());
        else sessionStorage.setItem("popupClosed_" + p.id, "1");
      } catch (e) {}
      overlay.remove();
    }
    if (p.close_mode === "hide_today") {
      bar.appendChild(dismissBtn("오늘 하루 안 보기", function () { remove(true); }));
    }
    bar.appendChild(dismissBtn("닫기 ✕", function () { remove(false); }));
    box.appendChild(bar);
    overlay.appendChild(box);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) remove(false); });
    document.body.appendChild(overlay);
  }

  function showSiteBanner(p) {
    var bar = document.createElement("div");
    bar.id = "siteTopBanner";
    bar.style.cssText =
      "position:relative; z-index:10040; background:#16202E; display:flex;" +
      "align-items:center; justify-content:center; gap:8px; padding:0;";
    var inner = document.createElement("div");
    inner.style.cssText = "width:" + p.width_px + "px; max-width:100%;";
    inner.appendChild(buildPopupImage(p));
    bar.appendChild(inner);
    var btns = document.createElement("div");
    btns.style.cssText = "position:absolute; right:8px; top:50%; transform:translateY(-50%); display:flex; gap:2px;" +
      "background:rgba(22,32,46,0.7); border-radius:6px;";
    function remove(hideToday) {
      try {
        if (hideToday) localStorage.setItem("popupHideDay_" + p.id, todayStr());
        else sessionStorage.setItem("popupClosed_" + p.id, "1");
      } catch (e) {}
      bar.remove();
      setHeaderH();
    }
    if (p.close_mode === "hide_today") {
      btns.appendChild(dismissBtn("오늘 하루 안 보기", function () { remove(true); }));
    }
    btns.appendChild(dismissBtn("✕", function () { remove(false); }));
    bar.appendChild(btns);
    document.body.insertBefore(bar, document.body.firstChild);
  }

  fetch("/api/popups/active", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var p = d && d.popup;
      if (!p || !p.image_url) return;
      if (p.scope === "home_only" && location.pathname !== "/") return;
      if (popupDismissed(p)) return;
      if (p.display_type === "top_banner") showSiteBanner(p);
      else showSitePopup(p);
    })
    .catch(function () { /* 팝업은 부가 기능 — 실패해도 페이지에 영향 없음 */ });

  // ---- 오류신고 플로팅 버튼 (관리자 페이지 제외) ----
  (function () {
    // /admin 경로는 제외
    if (location.pathname.startsWith("/admin")) return;

    // 플로팅 버튼 삽입
    var btn = document.createElement("button");
    btn.id = "bugReportBtn";
    btn.title = "오류신고";
    btn.textContent = "🐛";
    btn.style.cssText =
      "position:fixed;right:20px;bottom:20px;z-index:9999;" +
      "width:48px;height:48px;border-radius:50%;border:none;" +
      "background:var(--brass,#C9A227);color:#fff;" +
      "font-size:22px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.25);" +
      "display:flex;align-items:center;justify-content:center;";
    document.body.appendChild(btn);

    // 모달 마크업
    var modal = document.createElement("div");
    modal.id = "bugReportModal";
    modal.style.cssText =
      "display:none;position:fixed;inset:0;z-index:10000;" +
      "background:rgba(0,0,0,.45);align-items:center;justify-content:center;";
    modal.innerHTML = [
      '<div style="background:#fff;border-radius:14px;width:min(92vw,460px);',
             'padding:24px 24px 20px;box-shadow:0 8px 32px rgba(0,0,0,.22);',
             'font-family:inherit;max-height:90vh;overflow-y:auto;">',
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">',
          '<strong style="font-size:16px;">🐛 오류 신고</strong>',
          '<button id="bugReportClose" style="background:none;border:none;font-size:20px;cursor:pointer;color:#888;line-height:1;">✕</button>',
        '</div>',
        '<div id="bugReportResult" style="display:none;padding:16px;background:#E6F4EA;border-radius:8px;color:#1a7a3c;font-size:14px;text-align:center;margin-bottom:12px;"></div>',
        '<form id="bugReportForm">',
          '<label style="display:block;font-size:13px;font-weight:600;margin-bottom:4px;">무엇이 잘못됐나요? <span style="color:#c00;">*</span></label>',
          '<textarea id="brDescription" rows="4" placeholder="화면이 깨짐, 버튼이 안 눌림, 로그인이 안 됨 등…"',
            ' style="width:100%;box-sizing:border-box;border:1px solid #ddd;border-radius:8px;',
            'padding:10px;font-size:14px;resize:vertical;font-family:inherit;" required></textarea>',
          '<label style="display:block;font-size:13px;font-weight:600;margin:12px 0 6px;">심각도</label>',
          '<div style="display:flex;gap:8px;flex-wrap:wrap;">',
            '<label style="flex:1;min-width:100px;cursor:pointer;border:1.5px solid #ddd;border-radius:8px;',
              'padding:8px 10px;font-size:13px;text-align:center;transition:border-color .15s;">',
              '<input type="radio" name="brSeverity" value="blocking" style="display:none;">',
              '🚫 사용이 안 돼요</label>',
            '<label style="flex:1;min-width:100px;cursor:pointer;border:1.5px solid var(--brass,#C9A227);border-radius:8px;',
              'padding:8px 10px;font-size:13px;text-align:center;transition:border-color .15s;background:#FDF8EE;">',
              '<input type="radio" name="brSeverity" value="annoying" checked style="display:none;">',
              '😕 불편해요</label>',
            '<label style="flex:1;min-width:100px;cursor:pointer;border:1.5px solid #ddd;border-radius:8px;',
              'padding:8px 10px;font-size:13px;text-align:center;transition:border-color .15s;">',
              '<input type="radio" name="brSeverity" value="minor" style="display:none;">',
              '🔹 사소한 문제예요</label>',
          '</div>',
          '<label style="display:block;font-size:13px;font-weight:600;margin:12px 0 4px;">스크린샷 <span style="font-size:12px;color:#888;">(선택, jpg/png)</span></label>',
          '<input id="brScreenshot" type="file" accept=".jpg,.jpeg,.png" style="font-size:13px;">',
          '<div id="brScreenshotStatus" style="font-size:12px;color:#888;margin-top:4px;"></div>',
          '<button type="submit" id="brSubmitBtn"',
            ' style="margin-top:18px;width:100%;padding:11px;background:var(--brass,#C9A227);',
            'color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;">',
            '신고하기</button>',
        '</form>',
      '</div>'
    ].join("");
    document.body.appendChild(modal);

    // 심각도 라디오 선택 시 테두리 갱신
    var severityLabels = modal.querySelectorAll("label[style*='cursor:pointer']");
    modal.querySelectorAll("input[name='brSeverity']").forEach(function (radio, i) {
      radio.addEventListener("change", function () {
        severityLabels.forEach(function (lbl) {
          lbl.style.borderColor = "#ddd";
          lbl.style.background  = "";
        });
        if (radio.checked) {
          severityLabels[i].style.borderColor = "var(--brass,#C9A227)";
          severityLabels[i].style.background  = "#FDF8EE";
        }
      });
    });

    function openModal() {
      modal.style.display = "flex";
      document.getElementById("brDescription").focus();
    }
    function closeModal() {
      modal.style.display = "none";
      document.getElementById("bugReportForm").reset();
      document.getElementById("bugReportResult").style.display = "none";
      document.getElementById("brScreenshotStatus").textContent = "";
      _brScreenshotKey = null;
      // 심각도 선택 초기화
      severityLabels.forEach(function (lbl, i) {
        lbl.style.borderColor = i === 1 ? "var(--brass,#C9A227)" : "#ddd";
        lbl.style.background  = i === 1 ? "#FDF8EE" : "";
      });
    }

    btn.addEventListener("click", function () {
      if (!window.__livingstayLoggedIn) {
        if (typeof window.livingstayOpenLogin === "function") {
          window.livingstayOpenLogin("오류신고는 로그인 후 이용할 수 있습니다.");
        }
        return;
      }
      openModal();
    });
    document.getElementById("bugReportClose").addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });

    // 스크린샷 업로드
    var _brScreenshotKey = null;
    document.getElementById("brScreenshot").addEventListener("change", function (e) {
      var file = e.target.files && e.target.files[0];
      var statusEl = document.getElementById("brScreenshotStatus");
      if (!file) { _brScreenshotKey = null; statusEl.textContent = ""; return; }
      statusEl.textContent = "업로드 중…";
      var fd = new FormData();
      fd.append("file", file);
      fetch("/api/bug-reports/upload-screenshot", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) {
            _brScreenshotKey = d.key;
            statusEl.style.color = "#1a7a3c";
            statusEl.textContent = "✓ 첨부 완료";
          } else {
            _brScreenshotKey = null;
            statusEl.style.color = "#c00";
            statusEl.textContent = "✕ 업로드 실패: " + (d.message || "");
          }
        })
        .catch(function () {
          _brScreenshotKey = null;
          statusEl.style.color = "#c00";
          statusEl.textContent = "✕ 업로드 실패";
        });
    });

    // 폼 제출
    document.getElementById("bugReportForm").addEventListener("submit", function (e) {
      e.preventDefault();
      var desc = (document.getElementById("brDescription").value || "").trim();
      if (!desc) { alert("신고 내용을 입력해주세요."); return; }
      var severity = "annoying";
      modal.querySelectorAll("input[name='brSeverity']").forEach(function (r) {
        if (r.checked) severity = r.value;
      });
      var payload = {
        description:    desc,
        severity:       severity,
        page_url:       location.href,
        user_agent:     navigator.userAgent,
        screenshot_key: _brScreenshotKey || undefined,
      };
      var submitBtn = document.getElementById("brSubmitBtn");
      submitBtn.disabled = true;
      submitBtn.textContent = "신고 중…";
      fetch("/api/bug-reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var resultEl = document.getElementById("bugReportResult");
          resultEl.textContent = d.message || (d.ok ? "접수되었습니다!" : "오류가 발생했습니다.");
          resultEl.style.display = "block";
          resultEl.style.background = d.ok ? "#E6F4EA" : "#FBEAEA";
          resultEl.style.color = d.ok ? "#1a7a3c" : "#B23A3A";
          if (d.ok) {
            document.getElementById("bugReportForm").style.display = "none";
            setTimeout(closeModal, 2500);
          }
        })
        .catch(function () {
          var resultEl = document.getElementById("bugReportResult");
          resultEl.textContent = "제출 중 오류가 발생했습니다.";
          resultEl.style.display = "block";
          resultEl.style.background = "#FBEAEA";
          resultEl.style.color = "#B23A3A";
        })
        .finally(function () {
          submitBtn.disabled = false;
          submitBtn.textContent = "신고하기";
        });
    });
  })();
})();
