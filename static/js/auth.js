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
    } else {
      titleEl.textContent = "로그인";
      nameField.style.display = "none";
      submitBtn.textContent = "로그인";
      switchText.textContent = "아직 회원이 아니신가요?";
      switchLink.textContent = "회원가입";
      passwordInput.setAttribute("autocomplete", "current-password");
    }
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

  function refreshMe() {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.logged_in) renderLoggedIn(d);
        else renderLoggedOut();
      })
      .catch(function () { renderLoggedOut(); });
  }

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

    var url = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
    var body = mode === "signup"
      ? { email: email, password: password, name: name }
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
      .finally(function () { submitBtn.disabled = false; });
  }

  // 카카오 로그인 실패 시 홈으로 ?login_error=1 붙여 돌아옴 → 안내 후 URL 정리
  function checkLoginError() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get("login_error")) {
        params.delete("login_error");
        var qs = params.toString();
        var clean = window.location.pathname + (qs ? "?" + qs : "");
        window.history.replaceState({}, "", clean);
        openModal();
        showError("카카오 로그인에 실패했습니다. 다시 시도해주세요.");
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
