(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LivingstayChat = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function containsKoreanMobileNumber(text) {
    return /(?:^|[^\d])01[016789][\s-]?\d{3,4}[\s-]?\d{4}(?!\d)/.test(text || "");
  }

  function shouldShowGreeting(messages) {
    return Array.isArray(messages) && messages.length === 0;
  }

  function fillQuickReply(inputEl, text) {
    inputEl.value = text;
    inputEl.focus();
  }

  function showSafetyNoticeForMessage(text, noticeEl) {
    if (!noticeEl || !containsKoreanMobileNumber(text)) return false;
    noticeEl.textContent = "개인정보 보호 안내: 연락처 공유보다 앱 안에서 대화를 이어가세요. 송금·계약 전에는 상대방과 매물 정보를 다시 확인해 사기 피해를 예방하세요.";
    noticeEl.style.display = "block";
    return true;
  }

  function isLatestMessageLoad(activeRoomToken, requestRoomToken, requestSequence, latestSequence, modalConnected) {
    return Boolean(
      modalConnected &&
      activeRoomToken === requestRoomToken &&
      requestSequence === latestSequence
    );
  }

  function openPhoneVerificationModal(listingRequestId, retryChatStart) {
    document.getElementById("chatPhoneVerifyOverlay")?.remove();
    var ov = document.createElement("div");
    ov.id = "chatPhoneVerifyOverlay";
    ov.style.cssText = "position:fixed; inset:0; background:rgba(22,32,46,.45); z-index:4100; display:flex; align-items:center; justify-content:center; padding:16px;";
    var fieldStyle = "width:100%; box-sizing:border-box; border:1px solid var(--line); border-radius:8px; padding:10px 12px; font:14px inherit;";
    ov.innerHTML =
      '<div role="dialog" aria-modal="true" aria-labelledby="chatPhoneVerifyTitle" style="width:100%; max-width:380px; background:#fff; border-radius:14px; padding:22px 20px; box-shadow:0 10px 40px rgba(0,0,0,.2);">' +
        '<div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">' +
          '<strong id="chatPhoneVerifyTitle" style="font-size:16px; color:var(--ink);">휴대폰 인증이 필요해요</strong>' +
          '<button type="button" id="chatPhoneVerifyClose" aria-label="닫기" style="border:0; background:none; font-size:22px; color:var(--ink-soft); cursor:pointer;">×</button>' +
        '</div>' +
        '<p style="font-size:13px; color:var(--ink-soft); line-height:1.6; margin:9px 0 16px;">안전한 직거래를 위해 휴대폰 인증 후 채팅을 시작할 수 있어요. 인증이 끝나면 이 매물 채팅으로 바로 연결됩니다.</p>' +
        '<input id="chatPhoneNumber" type="tel" maxlength="13" inputmode="tel" placeholder="010-1234-5678" style="' + fieldStyle + '" />' +
        '<div style="display:flex; gap:6px; margin-top:7px;">' +
          '<input id="chatPhoneCode" type="text" maxlength="6" inputmode="numeric" placeholder="인증번호 6자리" style="' + fieldStyle + ' flex:1;" />' +
          '<button type="button" id="chatPhoneSendCode" style="border:1px solid var(--brass,#B4863F); background:#fff; color:var(--brass,#B4863F); border-radius:8px; padding:0 10px; white-space:nowrap; font:12.5px inherit; cursor:pointer;">인증번호 받기</button>' +
        '</div>' +
        '<button type="button" id="chatPhoneVerifyCode" style="width:100%; margin-top:8px; border:0; border-radius:8px; padding:10px; background:var(--brass,#B4863F); color:#fff; font:600 14px inherit; cursor:pointer;">인증하고 채팅 시작</button>' +
        '<div id="chatPhoneVerifyMsg" role="status" style="min-height:18px; margin-top:9px; font-size:12px;"></div>' +
      '</div>';
    document.body.appendChild(ov);

    var messageEl = ov.querySelector("#chatPhoneVerifyMsg");
    function setMessage(message, ok) {
      messageEl.textContent = message;
      messageEl.style.color = ok ? "#1a7a3c" : "var(--brick,#c33)";
    }
    function close() { ov.remove(); }
    ov.querySelector("#chatPhoneVerifyClose").addEventListener("click", close);
    ov.addEventListener("click", function (event) { if (event.target === ov) close(); });

    ov.querySelector("#chatPhoneSendCode").addEventListener("click", async function () {
      var phone = ov.querySelector("#chatPhoneNumber").value.trim();
      if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) {
        setMessage("휴대폰 번호 형식을 확인해주세요. 예) 010-1234-5678");
        return;
      }
      var button = ov.querySelector("#chatPhoneSendCode");
      button.disabled = true;
      button.textContent = "발송 중…";
      setMessage("");
      try {
        var response = await fetch("/api/auth/send-phone-code", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: phone }),
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.ok === false) {
          setMessage(data.message || "인증번호 발송에 실패했습니다.");
        } else {
          setMessage("인증번호를 발송했습니다. 3분 이내에 입력해주세요.", true);
        }
      } catch (error) {
        setMessage("네트워크 오류가 발생했습니다.");
      } finally {
        button.disabled = false;
        button.textContent = "재발송";
      }
    });

    ov.querySelector("#chatPhoneVerifyCode").addEventListener("click", async function () {
      var code = ov.querySelector("#chatPhoneCode").value.trim();
      if (!code) {
        setMessage("인증번호를 입력해주세요.");
        return;
      }
      var button = ov.querySelector("#chatPhoneVerifyCode");
      button.disabled = true;
      button.textContent = "확인 중…";
      setMessage("");
      try {
        var response = await fetch("/api/auth/verify-phone-code", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: code }),
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.ok === false) {
          setMessage(data.message || "인증에 실패했습니다.");
          return;
        }
        close();
        await retryChatStart();
      } catch (error) {
        setMessage("네트워크 오류가 발생했습니다.");
      } finally {
        if (document.body.contains(ov)) {
          button.disabled = false;
          button.textContent = "인증하고 채팅 시작";
        }
      }
    });
    setTimeout(function () { ov.querySelector("#chatPhoneNumber")?.focus(); }, 0);
  }

  async function startListingChat(listingRequestId, onRoomReady, options) {
    options = options || {};
    try {
      var response = await fetch("/api/chat/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ listing_request_id: listingRequestId }),
      });
      if (response.status === 401) {
        if (typeof window !== "undefined" && typeof window.livingstayOpenLogin === "function") {
          window.livingstayOpenLogin();
        } else if (typeof window !== "undefined") {
          window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
        }
        return;
      }
      var data = await response.json().catch(function () { return {}; });
      if (response.ok && data.ok) {
        if (typeof onRoomReady === "function") await onRoomReady(data.room_id);
        else if (typeof window !== "undefined" && typeof window.openChatModal === "function") window.openChatModal(data.room_id);
        return data.room_id;
      }
      if (response.status === 403 && data.code === "PHONE_VERIFICATION_REQUIRED") {
        var verificationOpener = options.openPhoneVerification || openPhoneVerificationModal;
        return await verificationOpener(listingRequestId, function () {
          return startListingChat(listingRequestId, onRoomReady, options);
        });
      }
      if (typeof alert === "function") {
        alert(data.message || data.error || "채팅방 생성에 실패했습니다. 잠시 후 다시 시도해주세요.");
      }
    } catch (error) {
      if (typeof alert === "function") alert("오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    }
  }

  return {
    containsKoreanMobileNumber: containsKoreanMobileNumber,
    shouldShowGreeting: shouldShowGreeting,
    fillQuickReply: fillQuickReply,
    showSafetyNoticeForMessage: showSafetyNoticeForMessage,
    isLatestMessageLoad: isLatestMessageLoad,
    openPhoneVerificationModal: openPhoneVerificationModal,
    startListingChat: startListingChat,
  };
});