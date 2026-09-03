
/* 전체 메뉴 페이지 — 상태 표시는 auth.js가 쏘는 livingstay:auth 이벤트를 단일 소스로 사용.
   로그인 버튼은 헤더의 #authLoginBtn(로그인 모달), 로그아웃은 헤더의 로그아웃과 동일 API 사용. */
(function(){
  function renderState(loggedIn, user){
    var nameEl = document.getElementById("menuUserName");
    var emailEl = document.getElementById("menuUserEmail");
    var loginBtn = document.getElementById("menuLoginBtn");
    var mypage = document.getElementById("menuMypageLink");
    var logoutWrap = document.getElementById("menuLogoutWrap");
    if (loggedIn && user) {
      nameEl.textContent = (user.name || "회원") + "님";
      emailEl.textContent = user.email || "";
      loginBtn.style.display = "none";
      mypage.style.display = "flex";
      logoutWrap.style.display = "block";
    } else {
      nameEl.textContent = "게스트";
      emailEl.textContent = "로그인하고 관심단지를 저장해보세요.";
      loginBtn.style.display = "block";
      mypage.style.display = "none";
      logoutWrap.style.display = "none";
    }
  }
  window.addEventListener("livingstay:auth", function(e){
    renderState(e.detail && e.detail.loggedIn, e.detail && e.detail.user);
  });

  document.getElementById("menuLoginBtn").addEventListener("click", function(){
    // auth.js가 헤더에 그려둔 로그인 버튼을 눌러 기존 로그인 모달을 그대로 연다.
    var btn = document.getElementById("authLoginBtn");
    if (btn) btn.click();
  });
  document.getElementById("menuLogoutBtn").addEventListener("click", function(){
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" })
      .then(function(){ if (window.livingstayRefreshAuth) window.livingstayRefreshAuth(); renderState(false, null); })
      .catch(function(){ if (window.livingstayRefreshAuth) window.livingstayRefreshAuth(); });
  });

  // 회사소개 모달 (index.html과 동일 동작)
  var companyModal = document.getElementById("companyModal");
  var companyLink = document.getElementById("menuCompanyLink");
  var companyClose = document.getElementById("companyModalClose");
  function openCompanyModal(e){ if (e) e.preventDefault(); companyModal.style.display = "flex"; }
  function closeCompanyModal(){ companyModal.style.display = "none"; }
  companyLink.addEventListener("click", openCompanyModal);
  companyClose.addEventListener("click", closeCompanyModal);
  companyModal.addEventListener("click", function(e){ if (e.target === companyModal) closeCompanyModal(); });
  document.addEventListener("keydown", function(e){ if (e.key === "Escape") closeCompanyModal(); });
})();
