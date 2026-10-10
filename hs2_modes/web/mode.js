(function () {
  "use strict";

  var API = "/hs2/api/mode";
  var state = {
    profile: null,
    csrf: "",
    loading: false,
    submitting: false,
    requestId: 0,
    controller: null,
    selectedContext: null
  };

  var el = {
    badge: document.getElementById("sessionBadge"),
    feedback: document.getElementById("feedback"),
    emailAuthPanel: document.getElementById("emailAuthPanel"),
    emailAuthTitle: document.getElementById("emailAuthTitle"),
    emailAuthCopy: document.getElementById("emailAuthCopy"),
    signedOut: document.getElementById("signedOutPanel"),
    signedIn: document.getElementById("signedInPanel"),
    unavailable: document.getElementById("unavailablePanel"),
    unavailableCopy: document.getElementById("unavailableCopy"),
    loginForm: document.getElementById("emailLoginForm"),
    loginEmail: document.getElementById("loginEmail"),
    loginPassword: document.getElementById("loginPassword"),
    loginButton: document.getElementById("emailLoginButton"),
    memberName: document.getElementById("memberName"),
    currentModeMark: document.getElementById("currentModeMark"),
    currentModeName: document.getElementById("currentModeName"),
    currentBusiness: document.getElementById("currentBusinessName"),
    consumerButton: document.getElementById("consumerModeButton"),
    operatorButton: document.getElementById("operatorModeButton"),
    businessSection: document.getElementById("businessSection"),
    businessCount: document.getElementById("businessCount"),
    businessUnavailable: document.getElementById("businessUnavailable"),
    businessList: document.getElementById("businessList"),
    modeHint: document.getElementById("modeHint"),
    logoutButton: document.getElementById("logoutButton"),
    retryButton: document.getElementById("retryButton")
  };

  function setFeedback(message, tone) {
    el.feedback.textContent = message || "";
    el.feedback.hidden = !message;
    el.feedback.dataset.tone = tone || "error";
  }

  function setBadge(label, status) {
    el.badge.textContent = label;
    el.badge.dataset.state = status;
  }

  function setBusy(busy) {
    state.submitting = busy;
    document.body.classList.toggle("is-busy", busy);
    el.loginButton.disabled = busy || !state.profile || !state.profile.email_entry;
    el.logoutButton.disabled = busy;
    el.consumerButton.disabled = busy;
    el.operatorButton.disabled = busy || !state.profile || !hasContexts();
    Array.prototype.forEach.call(el.businessList.querySelectorAll("button"), function (button) {
      button.disabled = busy;
    });
  }

  function hasContexts() {
    return !!(state.profile && Array.isArray(state.profile.contexts) && state.profile.contexts.length);
  }

  function activeBusiness() {
    var contexts = state.profile && Array.isArray(state.profile.contexts) ? state.profile.contexts : [];
    for (var i = 0; i < contexts.length; i += 1) {
      if (String(contexts[i].id) === String(state.profile.context_id)) return contexts[i];
    }
    return null;
  }

  function roleLabel(role) {
    var labels = {
      operator: "숙박 운영자",
      lodging_operator: "숙박 운영자",
      agent: "중개사",
      operations_support: "운영지원업체",
      partner: "사업자"
    };
    var key = String(role || "").toLowerCase();
    return labels[key] || (role ? String(role) : "승인된 사업장");
  }

  function renderBusinesses() {
    var contexts = state.profile && Array.isArray(state.profile.contexts) ? state.profile.contexts : [];
    el.businessList.replaceChildren();
    el.businessCount.textContent = contexts.length ? contexts.length + "개 승인됨" : "0개 승인됨";
    el.businessUnavailable.hidden = contexts.length > 0;
    el.businessList.hidden = contexts.length === 0;
    contexts.forEach(function (context, index) {
      var button = document.createElement("button");
      var copy = document.createElement("span");
      var name = document.createElement("span");
      var role = document.createElement("span");
      var symbol = document.createElement("span");
      var status = document.createElement("span");
      var active = state.profile.mode === "operator" &&
        String(context.id) === String(state.profile.context_id);
      button.type = "button";
      button.className = "business-choice";
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.dataset.contextId = String(context.id == null ? "" : context.id);
      symbol.className = "business-symbol";
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = String(index + 1).padStart(2, "0");
      copy.className = "business-copy";
      name.className = "business-name";
      name.textContent = context.business_name || "이름이 등록되지 않은 사업장";
      role.className = "business-role";
      role.textContent = roleLabel(context.role);
      status.className = "business-status";
      status.textContent = active ? "현재 이용 중" : "승인됨";
      copy.appendChild(name);
      copy.appendChild(role);
      button.appendChild(symbol);
      button.appendChild(copy);
      button.appendChild(status);
      button.addEventListener("click", function () {
        if (state.submitting || active) return;
        state.selectedContext = context.id;
        requestMode("operator", context.id);
      });
      el.businessList.appendChild(button);
    });
  }

  function renderProfile(data) {
    state.profile = data;
    state.csrf = typeof data.csrf_token === "string" ? data.csrf_token : "";
    el.unavailable.hidden = true;
    el.signedOut.hidden = !!data.logged_in;
    el.signedIn.hidden = !data.logged_in;
    setFeedback("", "");

    if (!data.logged_in) {
      setBadge("로그아웃 상태", "signed-out");
      setBusy(false);
      el.loginButton.disabled = !data.email_entry || !state.csrf;
      el.emailAuthPanel.hidden = !data.email_entry;
      el.emailAuthTitle.textContent = "승인된 사업자 로그인";
      el.emailAuthCopy.textContent = "사업자용 이메일 계정으로 로그인합니다. 이메일만으로 다른 계정이나 사업장을 연결하지 않습니다.";
      return;
    }

    setBadge("로그인됨", "signed-in");
    el.emailAuthPanel.hidden = !data.email_entry || data.email_authenticated === true;
    el.emailAuthTitle.textContent = "사업자 이메일 재확인";
    el.emailAuthCopy.textContent = "사업자 모드로 전환하려면 이메일과 비밀번호를 다시 확인해 주세요. 확인이 끝나면 승인된 사업장을 선택할 수 있습니다.";
    el.memberName.textContent = data.name || "회원";
    var business = activeBusiness();
    var isOperator = data.mode === "operator";
    el.currentModeMark.dataset.mode = isOperator ? "operator" : "consumer";
    el.currentModeName.textContent = isOperator ? "사업자 이용" : "일반회원 이용";
    el.currentBusiness.textContent = isOperator && business ? business.business_name || roleLabel(business.role) : "";
    el.consumerButton.setAttribute("aria-pressed", isOperator ? "false" : "true");
    el.operatorButton.setAttribute("aria-pressed", isOperator ? "true" : "false");
    el.operatorButton.disabled = !hasContexts();
    el.businessSection.hidden = false;
    el.businessUnavailable.hidden = hasContexts();
    if (isOperator && !business) {
      el.currentBusiness.textContent = "사업장 정보를 확인할 수 없습니다";
      el.modeHint.textContent = "현재 사업자 모드의 컨텍스트를 확인할 수 없습니다. 다른 사업장 승인이 있는지 확인하거나 일반회원 모드로 전환하세요.";
      el.businessSection.hidden = false;
      el.businessCount.textContent = "컨텍스트 미확인";
      el.businessList.hidden = true;
      el.businessUnavailable.hidden = false;
    } else {
      el.modeHint.textContent = isOperator
        ? "선택한 승인 사업장으로 이용 중입니다. 다른 이용 범위로 바꾸면 계정 세션의 모드가 변경됩니다."
        : "사업자 전환은 승인된 사업장으로만 가능합니다. 전환하면 해당 컨텍스트가 계정 세션에 적용됩니다.";
      renderBusinesses();
    }
    setBusy(false);
  }

  function showUnavailable(message) {
    el.signedIn.hidden = true;
    el.signedOut.hidden = true;
    el.unavailable.hidden = false;
    el.unavailableCopy.textContent = message || "모드 확인 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    setBadge("연결 불가", "error");
    el.loginButton.disabled = true;
  }

  function fetchProfile() {
    var requestId = ++state.requestId;
    if (state.controller) state.controller.abort();
    state.controller = typeof AbortController === "function" ? new AbortController() : null;
    state.loading = true;
    setBadge("확인 중", "loading");
    el.signedIn.hidden = true;
    el.signedOut.hidden = true;
    el.unavailable.hidden = true;
    if (state.controller) el.retryButton.disabled = true;
    fetch(API, {
      method: "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      signal: state.controller ? state.controller.signal : undefined
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data || data.ok !== true) throw new Error(data && data.message || "모드 정보를 확인할 수 없습니다.");
        return data;
      });
    }).then(function (data) {
      if (requestId !== state.requestId) return;
      renderProfile(data);
    }).catch(function (error) {
      if (requestId !== state.requestId || error.name === "AbortError") return;
      showUnavailable(error.message === "Failed to fetch"
        ? "모드 확인 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        : error.message);
    }).finally(function () {
      if (requestId !== state.requestId) return;
      state.loading = false;
      el.retryButton.disabled = false;
    });
  }

  function postJson(url, payload) {
    if (!state.csrf) return Promise.reject(new Error("보안 토큰을 확인할 수 없습니다. 먼저 계정 정보를 다시 불러와 주세요."));
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-HS2-CSRF": state.csrf
      },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data || data.ok !== true) {
          throw new Error(data && data.message || "요청을 처리하지 못했습니다.");
        }
        return data;
      });
    });
  }

  function requestMode(mode, contextId) {
    if (state.submitting || !state.profile || !state.profile.logged_in) return;
    if (mode === "operator" && state.profile.email_authenticated !== true) {
      setFeedback("사업자 모드로 전환하기 전에 사업자 이메일을 다시 확인해 주세요.", "error");
      el.emailAuthPanel.hidden = false;
      el.emailAuthPanel.scrollIntoView({ behavior: "smooth", block: "center" });
      el.loginEmail.focus({ preventScroll: true });
      return;
    }
    if (mode === "operator" && !hasContexts()) {
      setFeedback("승인된 사업장 컨텍스트가 확인되지 않아 사업자 모드로 전환할 수 없습니다.", "error");
      return;
    }
    if (mode === state.profile.mode &&
        (mode !== "operator" || String(contextId) === String(state.profile.context_id))) return;

    setBusy(true);
    setFeedback("", "");
    var payload = mode === "operator"
      ? { mode: "operator", context_id: contextId }
      : { mode: "consumer" };
    postJson(API, payload).then(function () {
      setFeedback(mode === "operator"
        ? "선택한 사업장으로 전환했습니다. 현재 이용 범위를 다시 확인해 주세요."
        : "일반회원 모드로 전환했습니다.", "success");
      fetchProfile();
    }).catch(function (error) {
      setBusy(false);
      setFeedback(error.message || "모드 전환에 실패했습니다. 현재 이용 범위는 변경되지 않았습니다.", "error");
    });
  }

  el.loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (state.submitting || !state.profile || !state.profile.email_entry) return;
    var email = el.loginEmail.value.trim();
    var password = el.loginPassword.value;
    if (!email || !password) {
      setFeedback("이메일과 비밀번호를 모두 입력해 주세요.", "error");
      return;
    }
    setBusy(true);
    setBadge("인증 중", "loading");
    setFeedback("사업자 계정을 확인하고 있습니다.", "info");
    postJson("/hs2/api/email-login", { email: email, password: password }).then(function () {
      el.loginPassword.value = "";
      el.loginEmail.value = "";
      setFeedback("로그인되었습니다. 현재 계정과 이용 범위를 확인하고 있습니다.", "success");
      fetchProfile();
    }).catch(function (error) {
      el.loginPassword.value = "";
      setBusy(false);
      setBadge("로그아웃 상태", "signed-out");
      setFeedback(error.message || "로그인할 수 없습니다. 승인된 사업자 계정인지 확인해 주세요.", "error");
    });
  });

  el.consumerButton.addEventListener("click", function () { requestMode("consumer"); });
  el.operatorButton.addEventListener("click", function () {
    var contexts = state.profile && state.profile.contexts;
    if (!Array.isArray(contexts) || !contexts.length) {
      setFeedback("사용 가능한 승인 사업장이 없습니다. 사업자 접근 승인 상태를 확인해 주세요.", "error");
      el.businessSection.hidden = false;
      el.businessUnavailable.hidden = false;
      el.businessList.hidden = true;
      return;
    }
    if (state.profile.email_authenticated !== true) {
      setFeedback("사업자 모드로 전환하기 전에 사업자 이메일을 다시 확인해 주세요.", "error");
      el.emailAuthPanel.hidden = false;
      el.emailAuthPanel.scrollIntoView({ behavior: "smooth", block: "center" });
      el.loginEmail.focus({ preventScroll: true });
      return;
    }
    el.businessSection.hidden = false;
    renderBusinesses();
    el.businessSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
    var firstChoice = el.businessList.querySelector("button:not([aria-pressed='true'])");
    if (firstChoice) firstChoice.focus({ preventScroll: true });
  });
  el.logoutButton.addEventListener("click", function () {
    if (state.submitting || !state.profile || !state.profile.logged_in) return;
    setBusy(true);
    setFeedback("로그아웃하고 있습니다.", "info");
    postJson("/hs2/api/logout", {}).then(function () {
      state.profile = null;
      state.csrf = "";
      el.loginEmail.value = "";
      el.loginPassword.value = "";
      fetchProfile();
    }).catch(function (error) {
      setBusy(false);
      setFeedback(error.message || "로그아웃하지 못했습니다. 다시 시도해 주세요.", "error");
    });
  });
  el.retryButton.addEventListener("click", function () {
    setFeedback("", "");
    fetchProfile();
  });
  fetchProfile();
})();
