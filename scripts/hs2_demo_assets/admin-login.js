(() => {
  "use strict";
  const form = document.getElementById("admin-login-form");
  if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const feedback = document.getElementById("admin-login-feedback");
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const response = await fetch("/hs2/admin/login", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify(Object.fromEntries(new FormData(form)))
      });
      const data = await response.json();
      form.elements.password.value = "";
      if (!response.ok || !data.ok) {
        feedback.textContent = data.code === "ADMIN_ACCOUNT_NOT_CONFIGURED"
          ? "개발 관리자 계정이 설정되지 않았습니다. 운영 계정이나 가상 역할로 우회하지 않습니다."
          : data.code === "LOGIN_RATE_LIMIT" ? "잠시 후 다시 시도해 주세요." : "계정과 비밀번호를 확인해 주세요.";
        return;
      }
      location.assign("/hs2/admin/");
    } catch (_) {
      feedback.textContent = "로그인을 완료하지 못했습니다. 다시 시도해 주세요.";
    } finally { button.disabled = false; }
  });
})();
