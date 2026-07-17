/* auth.js — 일반 회원 로그인/회원가입 (이메일 + 카카오)
 * 지도/검색/필터/건물상세 로직이 있는 main.js는 절대 건드리지 않고,
 * 헤더의 #authArea 와 로그인 모달(#authModal)만 독립적으로 제어한다.
 */
(function () {
  "use strict";

  var authArea = document.getElementById("authArea");
  var modal = document.getElementById("authModal");
  if (!authArea || !modal) return;

  var form = document.getElementById("authForm");
  var titleEl = document.getElementById("authModalTitle");
  var errorEl = document.getElementById("authError");
  var nameField = document.getElementById("authNameField");
  var nameInput = document.getElementById("authName");
  var emailInput = document.getElementById("authEmail");
  var passwordInput = document.getElementById("authPassword");
  var submitBtn = document.getElementById("authSubmit");
  var switchText = document.getElementById("authSwitchText");
  var switchLink = document.getElementById("authSwitchLink");
  var closeBtn = document.getElementById("authModalClose");

  var mode = "login"; // "login" | "signup"

  // ---- 회원가입 동의 체크박스 (header.js 가 마크업 주입) ----
  var consentBox = document.getElementById("authConsent");
  var agreeAll = document.getElementById("agreeAll");
  var agreeAge14 = document.getElementById("agreeAge14");
  var agreeTerms = document.getElementById("agreeTerms");
  var agreePrivacy = document.getElementById("agreePrivacy");
  var agreeMarketing = document.getElementById("agreeMarketing");
  var privacyToggle = document.getElementById("privacyToggle");
  var privacyDetail = document.getElementById("privacyDetail");

  function requiredAgreed() {
    return !!(agreeAge14 && agreeAge14.checked && agreeTerms.checked && agreePrivacy.checked);
  }
  // 가입 모드에서는 필수 3개(만14세·이용약관·개인정보) 모두 체크해야 가입하기 활성화.
  function updateSubmitState() {
    if (!submitBtn) return;
    submitBtn.disabled = (mode === "signup") && !requiredAgreed();
  }
  function syncAgreeAll() {
    if (agreeAll) {
      agreeAll.checked = requiredAgreed() && !!(agreeMarketing && agreeMarketing.checked);
    }
    updateSubmitState();
  }
  if (consentBox) {
    if (agreeAll) agreeAll.addEventListener("change", function () {
      var v = agreeAll.checked;
      agreeAge14.checked = v; agreeTerms.checked = v; agreePrivacy.checked = v;
      if (agreeMarketing) agreeMarketing.checked = v;
      updateSubmitState();
    });
    [agreeAge14, agreeTerms, agreePrivacy, agreeMarketing].forEach(function (el) {
      if (el) el.addEventListener("change", syncAgreeAll);
    });
    // 체크박스 라벨 안의 링크(/terms 등) 클릭 시 체크 토글 없이 새 탭만 열리도록.
    consentBox.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function (ev) { ev.stopPropagation(); });
    });
    if (privacyToggle && privacyDetail) {
      privacyToggle.addEventListener("click", function () {
        var open = privacyDetail.style.display !== "none";
        privacyDetail.style.display = open ? "none" : "block";
        privacyToggle.textContent = open ? "펼치기 ▾" : "접기 ▴";
        privacyToggle.setAttribute("aria-expanded", open ? "false" : "true");
      });
    }
  }
  function resetConsent() {
    if (!consentBox) return;
    [agreeAll, agreeAge14, agreeTerms, agreePrivacy, agreeMarketing].forEach(function (el) {
      if (el) el.checked = false;
    });
    if (privacyDetail) privacyDetail.style.display = "none";
    if (privacyToggle) { privacyToggle.textContent = "펼치기 ▾"; privacyToggle.setAttribute("aria-expanded", "false"); }
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = "block";
  }
  function clearError() {
    errorEl.textContent = "";
    errorEl.style.display = "none";
  }

  function setMode(next) {
    mode = next;
    clearError();
    if (mode === "signup") {
      titleEl.textContent = "회원가입";
      nameField.style.display = "";
      submitBtn.textContent = "가입하기";
      switchText.textContent = "이미 회원이신가요?";
      switchLink.textContent = "로그인";
      passwordInput.setAttribute("autocomplete", "new-password");
      if (consentBox) consentBox.style.display = "";
      resetConsent();
    } else {
      titleEl.textContent = "로그인";
      nameField.style.display = "none";
      submitBtn.textContent = "로그인";
      switchText.textContent = "아직 회원이 아니신가요?";
      switchLink.textContent = "회원가입";
      passwordInput.setAttribute("autocomplete", "current-password");
      if (consentBox) consentBox.style.display = "none";
    }
    updateSubmitState();
  }

  function openModal() {
    clearError();
    setMode("login");
    modal.style.display = "flex";
    setTimeout(function () { emailInput.focus(); }, 50);
  }
  function closeModal() {
    modal.style.display = "none";
    form.reset();
  }

  function renderLoggedIn(user) {
    authArea.innerHTML =
      '<span class="auth-username">' + escapeHtml(user.name || "회원") + '님</span>' +
      '<button type="button" class="auth-btn auth-btn-ghost" id="authLogoutBtn">로그아웃</button>';
    var logoutBtn = document.getElementById("authLogoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", doLogout);
  }

  function renderLoggedOut() {
    authArea.innerHTML =
      '<button type="button" class="auth-btn auth-btn-solid" id="authLoginBtn">로그인</button>';
    var loginBtn = document.getElementById("authLoginBtn");
    if (loginBtn) loginBtn.addEventListener("click", openModal);
  }

  // localStorage 관심단지(favKey 배열)를 서버로 이관 → 응답(합쳐진 최종 목록)으로 localStorage 재동기화.
  // migrate 는 없는 것만 채우므로(중복 스킵) 여러 번 호출돼도 안전하지만,
  // 브라우저 세션당 1회만(로그인 직후) 돌도록 sessionStorage 플래그로 가드한다.
  function syncFavorites() {
    var keys = [];
    try { keys = JSON.parse(localStorage.getItem("livingstay_favorites") || "[]"); } catch (e) { keys = []; }
    if (!Array.isArray(keys)) keys = [];
    fetch("/api/favorites/migrate", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: keys })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && Array.isArray(d.keys)) {
          try { localStorage.setItem("livingstay_favorites", JSON.stringify(d.keys)); } catch (e) {}
          if (typeof window.refreshFavoritesUI === "function") window.refreshFavoritesUI();
        }
      })
      .catch(function () { /* 이관 실패해도 로컬 관심단지는 그대로 → 무시 */ });
  }

  // 실거래 알림 구독도 동일하게 이관: 비로그인 때 localStorage(livingstay_alerts)에 담아둔
  // 구독 키를 서버로 옮기고, 이후엔 서버가 소스오브트루스가 된다(로컬은 정리).
  function syncAlerts() {
    var keys = [];
    try { keys = JSON.parse(localStorage.getItem("livingstay_alerts") || "[]"); } catch (e) { keys = []; }
    if (!Array.isArray(keys)) keys = [];
    fetch("/api/alerts/migrate", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: keys })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) {
          // 서버가 소스오브트루스 → 로컬 알림구독 캐시는 비운다(중복 이관 방지).
          try { localStorage.removeItem("livingstay_alerts"); } catch (e) {}
          if (typeof window.refreshAlertsUI === "function") window.refreshAlertsUI();
        }
      })
      .catch(function () { /* 이관 실패해도 무시 */ });
  }

  // 로그인 상태가 바뀔 때마다 페이지에 알린다(예: 마이페이지 본문 동기화).
  // 헤더 밖의 UI가 헤더 auth 상태를 소스오브트루스로 삼도록 하는 용도 — 헤더만 쓰는
  // 페이지에서는 아무도 구독하지 않으므로 부작용이 없다.
  function emitAuthChange(loggedIn, user) {
    try {
      window.dispatchEvent(new CustomEvent("livingstay:auth", {
        detail: { loggedIn: !!loggedIn, user: user || null }
      }));
    } catch (e) { /* CustomEvent 미지원 → 무시 */ }
  }

  function refreshMe() {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.logged_in) {
          window.__livingstayLoggedIn = true;
          renderLoggedIn(d);
          // 로그인 직후(이 세션 첫 확인) 1회만 관심단지 이관.
          var migrated;
          try { migrated = sessionStorage.getItem("livingstay_fav_migrated"); } catch (e) { migrated = "1"; }
          if (migrated !== "1") {
            try { sessionStorage.setItem("livingstay_fav_migrated", "1"); } catch (e) {}
            syncFavorites();
            syncAlerts();
          } else if (typeof window.refreshAlertsUI === "function") {
            // 이미 이관은 끝난 세션 → 알림구독 목록만 다시 로드해 B패널 버튼 상태 반영.
            window.refreshAlertsUI();
          }
          if (typeof window.startNotifPolling === "function") window.startNotifPolling();
          emitAuthChange(true, d);
        } else {
          window.__livingstayLoggedIn = false;
          try { sessionStorage.removeItem("livingstay_fav_migrated"); } catch (e) {}
          if (typeof window.stopNotifPolling === "function") window.stopNotifPolling();
          renderLoggedOut();
          emitAuthChange(false, null);
        }
      })
      .catch(function () { window.__livingstayLoggedIn = false; renderLoggedOut(); emitAuthChange(false, null); });
  }

  // 헤더 밖 페이지(마이페이지 등)에서 로그아웃/로그인 후 헤더+상태를 다시 맞추도록 노출.
  window.livingstayRefreshAuth = refreshMe;

  function doLogout() {
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" })
      .then(function () { refreshMe(); })
      .catch(function () { refreshMe(); });
  }

  function submit(e) {
    e.preventDefault();
    clearError();
    var email = (emailInput.value || "").trim();
    var password = passwordInput.value || "";
    var name = (nameInput.value || "").trim();

    if (!email || !password) {
      showError("이메일과 비밀번호를 입력해주세요.");
      return;
    }
    if (mode === "signup" && !name) {
      showError("이름을 입력해주세요.");
      return;
    }
    if (mode === "signup" && !requiredAgreed()) {
      showError("필수 약관에 모두 동의해주세요.");
      return;
    }

    var url = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
    var body = mode === "signup"
      ? { email: email, password: password, name: name,
          age14: !!(agreeAge14 && agreeAge14.checked),
          terms: !!(agreeTerms && agreeTerms.checked),
          privacy: !!(agreePrivacy && agreePrivacy.checked),
          marketing: !!(agreeMarketing && agreeMarketing.checked) }
      : { email: email, password: password };

    submitBtn.disabled = true;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (res.ok && res.data && res.data.ok) {
          closeModal();
          refreshMe();
        } else {
          showError((res.data && res.data.message) || "요청을 처리하지 못했습니다.");
        }
      })
      .catch(function () { showError("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요."); })
      .finally(function () { updateSubmitState(); });
  }

  // 카카오 로그인 실패 시 홈으로 ?login_error=1 붙여 돌아옴 → 안내 후 URL 정리
  // 마이페이지 등에서 ?login=1 로 들어오면 로그인 모달을 자동으로 연다.
  function checkLoginError() {
    try {
      var params = new URLSearchParams(window.location.search);
      var hadLoginError = !!params.get("login_error");
      var wantLogin = !!params.get("login");
      if (hadLoginError || wantLogin) {
        params.delete("login_error");
        params.delete("login");
        var qs = params.toString();
        var clean = window.location.pathname + (qs ? "?" + qs : "");
        window.history.replaceState({}, "", clean);
        openModal();
        if (hadLoginError) showError("카카오 로그인에 실패했습니다. 다시 시도해주세요.");
      }
    } catch (err) { /* URLSearchParams 미지원 등 → 무시 */ }
  }

  switchLink.addEventListener("click", function (e) {
    e.preventDefault();
    setMode(mode === "login" ? "signup" : "login");
  });
  closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.style.display !== "none") closeModal();
  });
  form.addEventListener("submit", submit);

  refreshMe();
  checkLoginError();
})();
