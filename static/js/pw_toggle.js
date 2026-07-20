// 비밀번호 눈표시(보이기/숨기기) 토글 — 사이트 공용.
// 페이지의 모든 input[type=password]를 .auth-pw-wrap으로 감싸고 👁 버튼을 붙인다.
// (auth.js가 관리하는 로그인 모달 입력창처럼 이미 .auth-pw-wrap 안에 있는 것은 건너뜀)
(function () {
  "use strict";

  function enhance(input) {
    if (input.dataset.pwToggleDone) return;
    if (input.closest(".auth-pw-wrap")) { input.dataset.pwToggleDone = "1"; return; }
    input.dataset.pwToggleDone = "1";

    var wrap = document.createElement("div");
    wrap.className = "auth-pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "auth-pw-toggle";
    btn.tabIndex = -1;
    wrap.appendChild(btn);

    function setVisible(visible) {
      input.type = visible ? "text" : "password";
      btn.textContent = visible ? "🙈" : "👁";
      btn.setAttribute("aria-pressed", visible ? "true" : "false");
      var label = visible ? "비밀번호 숨기기" : "비밀번호 표시";
      btn.setAttribute("aria-label", label);
      btn.title = label;
    }
    setVisible(false);
    btn.addEventListener("click", function () {
      setVisible(input.type === "password");
      input.focus();
    });
  }

  function scan(root) {
    (root.querySelectorAll ? root.querySelectorAll('input[type="password"]') : []).forEach(enhance);
  }

  function init() {
    scan(document);
    // 동적으로 추가되는 입력창(마이페이지 비밀번호 변경 폼 등)도 자동 적용
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches('input[type="password"]')) enhance(n);
          else scan(n);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
