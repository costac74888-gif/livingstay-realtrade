(function () {
  "use strict";

  var path = window.location.pathname.replace(/\/+$/, "");
  var roles = {
    "/operator/login": "operator",
    "/loan-consultant/login": "loan_consultant",
    "/lodging-operator/login": "lodging_operator",
    "/partner/login": "partner"
  };
  var role = roles[path] || "partner";
  var titles = {
    operator: "운영지원업체 로그인",
    loan_consultant: "대출상담사 로그인",
    lodging_operator: "숙박 운영자 로그인",
    partner: "파트너 통합 로그인"
  };
  var fallbacks = {
    operator: "/operator/dashboard",
    loan_consultant: "/loan-consultant/dashboard",
    lodging_operator: "/lodging-operator/manage",
    partner: "/mypage"
  };
  var title = document.getElementById("partnerLoginTitle");
  if (title) title.textContent = titles[role];
  var form = document.getElementById("loginForm");
  var msg = document.getElementById("loginMsg");
  var btn = document.getElementById("loginBtn");
  var picker = document.getElementById("contextPicker");
  var remember = document.getElementById("rememberLogin");
  var emailInput = document.querySelector("#loginForm input[autocomplete='username']");
  var passwordInput = document.querySelector("#loginForm input[autocomplete='current-password']");
  if (!form || !msg || !btn || !picker || !emailInput || !passwordInput) return;
  var busy = false;

  function showMessage(text) {
    msg.textContent = text || "";
    msg.hidden = !text;
  }

  function safeRedirect(pathValue) {
    if (typeof pathValue !== "string" || !pathValue) return fallbacks[role];
    try {
      var parsed = new URL(pathValue, window.location.origin);
      if (parsed.origin === window.location.origin) {
        return parsed.pathname + parsed.search + parsed.hash;
      }
    } catch (error) {}
    return fallbacks[role];
  }

  function showContexts(contexts) {
    picker.textContent = "";
    picker.hidden = false;
    var prompt = document.createElement("p");
    prompt.className = "admin-login-sub";
    prompt.textContent = "접속할 역할 또는 사업장을 선택하세요.";
    picker.appendChild(prompt);

    var select = document.createElement("select");
    select.className = "admin-input";
    select.id = "contextChoice";
    select.setAttribute("aria-label", "접속할 역할과 사업장");
    contexts.forEach(function (context) {
      var option = document.createElement("option");
      option.value = String(context.id);
      var roleLabels = {agent:"중개사",operator:"운영지원업체",
        loan_consultant:"대출상담사",lodging_operator:"숙박운영자"};
      var roleLabel = context.label || context.role_label || roleLabels[context.role] || "파트너";
      var business = context.business_name || context.office_name || context.company_name || context.building_name || context.name || "";
      option.textContent = (roleLabel ? roleLabel + (business ? " · " : "") : "") + business ||
        "파트너 사업장";
      select.appendChild(option);
    });
    picker.appendChild(select);

    var chooseButton = document.createElement("button");
    chooseButton.type = "button";
    chooseButton.className = "admin-btn admin-btn-primary";
    chooseButton.textContent = "선택한 역할로 접속";
    chooseButton.addEventListener("click", async function () {
      if (busy || !select.value) return;
      busy = true;
      chooseButton.disabled = true;
      select.disabled = true;
      showMessage("");
      try {
        var response = await fetch("/api/auth/context", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ context_id: select.value })
        });
        var result = await response.json().catch(function () { return {}; });
        if (!response.ok || !result.ok) {
          throw new Error(result.message || "역할 선택에 실패했습니다. 다시 시도해주세요.");
        }
        window.location.href = safeRedirect(result.redirect);
      } catch (error) {
        showMessage(error.message || "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
        busy = false;
        chooseButton.disabled = false;
        select.disabled = false;
      }
    });
    picker.appendChild(chooseButton);
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (busy) return;
    var email = emailInput.value.trim();
    var password = passwordInput.value;
    showMessage("");
    picker.hidden = true;
    picker.textContent = "";
    busy = true;
    btn.disabled = true;
    btn.textContent = "확인 중…";
    try {
      var response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
          password: password,
          remember: !!(remember && remember.checked),
          role: role
        })
      });
      var result = await response.json().catch(function () { return {}; });
      if (response.ok && result.ok && result.select_context && Array.isArray(result.contexts) && result.contexts.length) {
        showContexts(result.contexts);
        showMessage("로그인되었습니다. 접속할 역할 또는 사업장을 선택해주세요.");
        busy = false;
        return;
      }
      if (response.ok && result.ok) {
        window.location.href = safeRedirect(result.redirect);
        return;
      }
      var code = String(result.code || result.error || "").toLowerCase();
      var fallback = code.indexOf("pending") !== -1
        ? "승인 대기 중입니다. 승인 완료 후 로그인할 수 있습니다."
        : code.indexOf("link") !== -1
          ? "연결된 사업장이나 파트너 역할이 없습니다. 등록 상태를 확인해주세요."
          : "로그인에 실패했습니다. 이메일과 계정 상태를 확인해주세요.";
      showMessage(result.message || fallback);
    } catch (error) {
      showMessage("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      busy = false;
      btn.disabled = false;
      btn.textContent = "로그인";
    }
  });
})();
