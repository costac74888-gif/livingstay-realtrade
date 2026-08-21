(function () {
  "use strict";

  var MAX_PHOTOS = 5;
  var MAX_PHOTO_BYTES = 5 * 1024 * 1024;
  var DEAL_TYPES = ["매매", "전세", "월세", "단기임대"];

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function numValue(el) {
    var n = parseInt(el && el.value, 10);
    return isFinite(n) && n > 0 ? n : null;
  }

  function inputStyle(extra) {
    return "width:100%;box-sizing:border-box;padding:10px 11px;border:1px solid var(--line,#e2ddd8);" +
      "border-radius:8px;font:13px inherit;background:#fff;" + (extra || "");
  }

  function priceText(dealType, price, rent) {
    if (dealType === "매매") return price ? "매매가 " + price + "만원" : "";
    if (dealType === "전세") return price ? "전세 " + price + "만원" : "";
    if (dealType === "월세") return price || rent ? "보증금 " + (price || 0) + "만원 / 월세 " + (rent || 0) + "만원" : "";
    return "";
  }

  function photoArray(value) {
    return Array.isArray(value) ? value.filter(function (p) {
      return p && p.id != null && p.url;
    }) : [];
  }

  function uploadPhoto(listingId, file) {
    var form = new FormData();
    form.append("file", file, file.name);
    return fetch("/api/listing-requests/" + listingId + "/photos", {
      method: "POST", credentials: "same-origin", body: form
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok || !data.ok) throw new Error(data.message || "사진 업로드에 실패했습니다.");
        return data;
      });
    });
  }

  window.openListingRequestModal = function (buildingId, buildingName, options) {
    options = options || {};
    var prefill = options.prefill || options;
    var editId = options.editId || prefill.editId || null;
    var isEdit = !!editId;
    var draftKey = null;
    var draftRestored = false;
    var draftUser = null;
    var DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
    var old = document.getElementById("listingRequestOverlay");
    if (old) old.remove();

    var dealType = prefill.deal_type || "매매";
    if (DEAL_TYPES.indexOf(dealType) < 0) dealType = "매매";
    var dealMode = prefill.deal_mode || "direct";
    if (dealMode !== "broker") dealMode = "direct";
    var photoItems = photoArray(prefill.photos || prefill.existing_photos).map(function (photo) {
      return { kind: "existing", photo: photo };
    });
    var confirmedPhotoItems = photoItems.slice();
    var photoOrderSaveChain = Promise.resolve();
    var photoOrderVersion = 0;
    var overlay = document.createElement("div");
    overlay.id = "listingRequestOverlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:4100;background:rgba(22,32,46,.52);display:flex;align-items:center;justify-content:center;padding:14px;";

    overlay.innerHTML =
      '<div role="dialog" aria-modal="true" aria-labelledby="lrTitle" style="width:100%;max-width:520px;max-height:calc(100vh - 28px);overflow:auto;background:#fff;border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.28);">' +
        '<div style="position:sticky;top:0;z-index:1;background:#fff;padding:18px 18px 12px;border-bottom:1px solid var(--line,#eee);display:flex;align-items:flex-start;justify-content:space-between;gap:12px;">' +
          '<div><div id="lrTitle" style="font-size:17px;font-weight:800;color:var(--ink,#16202e);">' + (isEdit ? "매물의뢰 수정" : "매물 내놓기") + '</div>' +
          '<div style="font-size:12px;color:var(--ink-soft,#6b7684);margin-top:4px;">' + esc(buildingName || "") + '</div></div>' +
          '<button type="button" id="lrClose" aria-label="닫기" style="border:0;background:transparent;color:#6b7684;font-size:25px;line-height:1;cursor:pointer;">×</button>' +
        '</div>' +
        '<div id="lrAuthLoading" style="display:none;padding:34px 18px;text-align:center;color:var(--ink-soft,#6b7684);font-size:13px;">매물 등록을 준비하고 있습니다.</div>' +
        '<div id="lrPhoneVerifyGate" style="display:none;padding:28px 18px 24px;">' +
          '<div style="font-size:17px;font-weight:800;color:var(--ink,#16202e);">휴대폰 인증</div>' +
          '<p style="margin:8px 0 18px;color:var(--ink-soft,#6b7684);font-size:13px;line-height:1.55;">매물 등록은 휴대폰 인증이 필요합니다.<br>인증된 계정 전화번호만 매물 연락처로 사용됩니다.</p>' +
          '<div id="lrGateLoading" style="font-size:13px;color:var(--ink-soft,#6b7684);">인증 상태를 확인하고 있습니다.</div>' +
          '<div id="lrGateFields" style="display:none;"><input id="lrGatePhone" type="tel" inputmode="tel" autocomplete="tel" placeholder="010-1234-5678" style="' + inputStyle() + '">' +
          '<button type="button" id="lrGateSendCode" style="width:100%;margin-top:8px;border:0;border-radius:8px;padding:11px;background:var(--brass,#b4863f);color:#fff;font:700 13px inherit;cursor:pointer;">인증번호 받기</button>' +
          '<div id="lrGateCodeWrap" style="display:none;margin-top:12px;"><div style="display:flex;gap:7px;"><input id="lrGateCode" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="인증번호 6자리" style="' + inputStyle("flex:1;") + '"><button type="button" id="lrGateVerify" style="white-space:nowrap;border:0;border-radius:8px;padding:10px 13px;background:#4A7A18;color:#fff;font:700 13px inherit;cursor:pointer;">확인</button></div></div>' +
          '<div id="lrGateMessage" aria-live="polite" style="display:none;margin-top:9px;font-size:12.5px;"></div></div>' +
        '</div>' +
        '<form id="lrForm" style="padding:16px 18px 20px;">' +
          '<section id="lrModeSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">진행 방식</div>' +
          '<div style="display:flex;gap:8px;"><button type="button" class="lr-mode" data-mode="direct" style="flex:1;padding:9px;border-radius:8px;border:1px solid #4A7A18;background:' + (dealMode === "direct" ? "#4A7A18" : "#fff") + ';color:' + (dealMode === "direct" ? "#fff" : "#4A7A18") + ';font:700 13px inherit;cursor:pointer;">직거래</button>' +
          '<button type="button" class="lr-mode" data-mode="broker" style="flex:1;padding:9px;border-radius:8px;border:1px solid var(--brass,#b4863f);background:' + (dealMode === "broker" ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (dealMode === "broker" ? "#fff" : "var(--brass,#b4863f)") + ';font:700 13px inherit;cursor:pointer;">중개사 연결</button></div>' +
          '<div id="lrModeHelp" style="font-size:11.5px;color:var(--ink-soft);margin-top:6px;"></div></section>' +
          '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">거래 유형</div>' +
          '<div id="lrDealButtons" style="display:flex;gap:6px;flex-wrap:wrap;">' + DEAL_TYPES.map(function (dt) {
            return '<button type="button" class="lr-deal" data-type="' + dt + '" style="padding:7px 11px;border-radius:7px;border:1px solid ' + (dt === dealType ? "var(--brass,#b4863f)" : "var(--line,#e2ddd8)") + ';background:' + (dt === dealType ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (dt === dealType ? "#fff" : "var(--ink,#16202e)") + ';font:700 12.5px inherit;cursor:pointer;">' + dt + '</button>';
          }).join("") + '</div></section>' +
          '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">매물 정보</div>' +
          '<div id="lrPriceSale"><input id="lrSalePrice" type="number" min="1" inputmode="numeric" placeholder="매매가 (만원)" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div>' +
          '<div id="lrPriceJeonse"><input id="lrJeonseDeposit" type="number" min="1" inputmode="numeric" placeholder="전세 보증금 (만원)" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div>' +
          '<div id="lrPriceWolse" style="display:flex;gap:7px;"><input id="lrWolseDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle("flex:1;") + '"><input id="lrWolseRent" type="number" min="1" inputmode="numeric" placeholder="월세 (만원)" value="' + esc(prefill.monthly_rent_krw || "") + '" style="' + inputStyle("flex:1;") + '"></div>' +
          '<div id="lrShortTerm"><input id="lrDesiredPrice" maxlength="100" placeholder="희망 조건 (선택)" value="' + esc(prefill.desired_price || "") + '" style="' + inputStyle() + '"></div></section>' +
           '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">상세 정보 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div>' +
           '<div style="display:flex;gap:7px;margin-bottom:7px;"><div style="flex:1;"><select id="lrArea" style="' + inputStyle() + '"><option value="">전용면적 선택</option></select><input id="lrAreaManual" type="number" min="0" step="0.01" inputmode="decimal" placeholder="전용면적 직접 입력 ㎡" style="' + inputStyle("display:none;margin-top:6px;") + '"></div><input id="lrDong" maxlength="20" placeholder="동" value="' + esc(prefill.dong || "") + '" style="' + inputStyle("flex:.55;") + '"><input id="lrHo" maxlength="20" placeholder="호" value="' + esc(prefill.ho || "") + '" style="' + inputStyle("flex:.55;") + '"></div>' +
          '<select id="lrRegistrantType" style="' + inputStyle() + '"><option value="owner">소유자</option><option value="agent">중개사</option><option value="other">기타 관계자</option></select></section>' +
          '<section id="lrYieldSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">예상 수익률 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div>' +
          '<div style="display:flex;gap:7px;"><input id="lrYieldDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" value="' + esc(prefill.deposit_krw || "") + '" style="' + inputStyle("flex:1;") + '"><input id="lrYieldRent" type="number" min="1" inputmode="numeric" placeholder="월 임대료 (만원)" value="' + esc(prefill.yield_rent_krw || "") + '" style="' + inputStyle("flex:1;") + '"></div><div id="lrYieldResult" style="font-size:11.5px;color:var(--brass,#b4863f);margin-top:6px;"></div></section>' +
          '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">매물 설명 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div><textarea id="lrDescription" maxlength="500" rows="4" placeholder="매물의 장점, 입주 가능일 등을 적어주세요." style="' + inputStyle("resize:vertical;line-height:1.5;") + '">' + esc(prefill.description || "") + '</textarea></section>' +
          '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">사진 <span style="font-weight:400;color:var(--ink-soft);">최대 5장 · JPG/PNG · 장당 5MB · 첫 사진이 대표사진</span></div>' +
          '<input id="lrPhotoInput" type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" multiple style="display:none">' +
          '<div id="lrDropZone" tabindex="0" role="button" style="border:1.5px dashed var(--brass,#b4863f);border-radius:9px;padding:16px 10px;text-align:center;color:var(--brass,#b4863f);font-size:12.5px;cursor:pointer;background:#fffaf2;">사진을 끌어 놓거나 클릭해서 선택</div>' +
          '<div id="lrPhotoGrid" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:9px;"></div></section>' +
          '<div id="lrMessage" aria-live="polite" style="display:none;margin-bottom:10px;font-size:12.5px;color:#b42318;"></div>' +
          '<button id="lrSubmit" type="submit" style="width:100%;border:0;border-radius:9px;padding:13px;background:var(--brass,#b4863f);color:#fff;font:800 14px inherit;cursor:pointer;">' + (isEdit ? "저장" : "매물의뢰 접수하기") + '</button>' +
        '</form><div id="lrDone" style="display:none;text-align:center;padding:46px 20px;color:var(--ink);"><div style="font-size:18px;font-weight:800;">' + (isEdit ? "변경 내용을 저장했습니다" : "매물의뢰가 접수됐습니다") + '</div><div style="font-size:13px;color:var(--ink-soft);margin-top:8px;">' + (isEdit ? "최신 정보로 매물이 업데이트됩니다." : "등록 후에도 마이페이지에서 수정할 수 있습니다.") + '</div></div>' +
      '</div>';
    document.body.appendChild(overlay);

    var $ = function (selector) { return overlay.querySelector(selector); };
    var form = $("#lrForm"), message = $("#lrMessage"), submit = $("#lrSubmit");
    var phoneGate = $("#lrPhoneVerifyGate"), gateTimer = null;
    $("#lrRegistrantType").value = ["owner", "agent", "other"].indexOf(prefill.registrant_type) >= 0 ? prefill.registrant_type : "owner";

    function populateAreaTypes(items) {
      var areaSelect = $("#lrArea");
      var areaManual = $("#lrAreaManual");
      if (!areaSelect || !areaManual) return;
      var savedArea = prefill.area_sqm == null ? "" : String(prefill.area_sqm);
      var validItems = (Array.isArray(items) ? items : []).filter(function (item) {
        return item && item.sqm != null && isFinite(Number(item.sqm)) && Number(item.sqm) > 0;
      });
      areaSelect.innerHTML = '<option value="">전용면적 선택</option>' +
        validItems.map(function (item) {
          var value = String(item.sqm);
          var label = value + "㎡" + (item.ho_cnt != null ? " (" + item.ho_cnt + "실)" : "");
          return '<option value="' + esc(value) + '">' + esc(label) + '</option>';
        }).join("") +
        '<option value="__manual__">직접 입력</option>';
      var matchingArea = savedArea && validItems.find(function (item) {
        return Number(item.sqm) === Number(savedArea);
      });
      if (matchingArea) {
        areaSelect.value = String(matchingArea.sqm);
      } else if (savedArea) {
        areaSelect.value = "__manual__";
        areaManual.value = savedArea;
      }
      areaManual.style.display = areaSelect.value === "__manual__" ? "block" : "none";
    }
    $("#lrArea").addEventListener("change", function () {
      $("#lrAreaManual").style.display = this.value === "__manual__" ? "block" : "none";
      if (this.value !== "__manual__") $("#lrAreaManual").value = "";
    });
    if (buildingId) {
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/area-types", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) { populateAreaTypes(data.items || []); })
        .catch(function () { populateAreaTypes([]); });
    } else {
      populateAreaTypes([]);
    }

    function close() {
      if (gateTimer) clearInterval(gateTimer);
      overlay.remove();
    }
    $("#lrClose").addEventListener("click", close);
    overlay.addEventListener("click", function (event) { if (event.target === overlay) close(); });

    function setMessage(text) {
      message.textContent = text || "";
      message.style.display = text ? "block" : "none";
    }
    function updateMode() {
      Array.prototype.forEach.call(overlay.querySelectorAll(".lr-mode"), function (button) {
        var active = button.getAttribute("data-mode") === dealMode;
        button.style.background = active ? (dealMode === "direct" ? "#4A7A18" : "var(--brass,#b4863f)") : "#fff";
        button.style.color = active ? "#fff" : (button.getAttribute("data-mode") === "direct" ? "#4A7A18" : "var(--brass,#b4863f)");
      });
      $("#lrModeHelp").textContent = dealMode === "direct" ? "인증된 휴대폰 번호로 구매자와 직접 연락합니다." : "조건에 맞는 담당 중개사에게 연결합니다.";
    }
    function updateDealType() {
      Array.prototype.forEach.call(overlay.querySelectorAll(".lr-deal"), function (button) {
        var active = button.getAttribute("data-type") === dealType;
        button.style.background = active ? "var(--brass,#b4863f)" : "#fff";
        button.style.color = active ? "#fff" : "var(--ink,#16202e)";
        button.style.borderColor = active ? "var(--brass,#b4863f)" : "var(--line,#e2ddd8)";
      });
      $("#lrPriceSale").style.display = dealType === "매매" ? "block" : "none";
      $("#lrPriceJeonse").style.display = dealType === "전세" ? "block" : "none";
      $("#lrPriceWolse").style.display = dealType === "월세" ? "flex" : "none";
      $("#lrShortTerm").style.display = dealType === "단기임대" ? "block" : "none";
      $("#lrYieldSection").style.display = dealType === "매매" ? "block" : "none";
      updateYield();
    }
    function updateYield() {
      var price = numValue($("#lrSalePrice")), deposit = numValue($("#lrYieldDeposit")) || 0, rent = numValue($("#lrYieldRent"));
      $("#lrYieldResult").textContent = dealType === "매매" && price && rent
        ? "예상 수익률 약 " + ((rent * 12 / Math.max(price - deposit, 1)) * 100).toFixed(1) + "%" : "";
    }
    function saveDraft() {
      if (!draftKey || !form || form.style.display === "none") return;
      try {
        var draftPrice = dealType === "전세" ? $("#lrJeonseDeposit").value :
          (dealType === "월세" ? $("#lrWolseDeposit").value : $("#lrSalePrice").value);
        localStorage.setItem(draftKey, JSON.stringify({
          saved_at: Date.now(),
          data: {
            deal_type: dealType,
            deal_mode: dealMode,
            price_krw: draftPrice || "",
            monthly_rent_krw: $("#lrWolseRent").value || "",
            desired_price: $("#lrDesiredPrice").value || "",
            area_sqm: $("#lrArea").value === "__manual__" ? ($("#lrAreaManual").value || "") : ($("#lrArea").value || ""),
            dong: $("#lrDong").value || "",
            ho: $("#lrHo").value || "",
            registrant_type: $("#lrRegistrantType").value || "owner",
            deposit_krw: $("#lrYieldDeposit").value || "",
            yield_rent_krw: $("#lrYieldRent").value || "",
            description: $("#lrDescription").value || ""
          }
        }));
      } catch (e) {}
    }
    function clearDraft() {
      if (!draftKey) return;
      try { localStorage.removeItem(draftKey); } catch (e) {}
    }
    function applyDraft(draft) {
      prefill = Object.assign({}, prefill, draft);
      dealType = DEAL_TYPES.indexOf(draft.deal_type) >= 0 ? draft.deal_type : dealType;
      dealMode = draft.deal_mode === "broker" ? "broker" : "direct";
      $("#lrSalePrice").value = draft.price_krw || "";
      $("#lrJeonseDeposit").value = draft.price_krw || "";
      $("#lrWolseDeposit").value = draft.price_krw || "";
      $("#lrWolseRent").value = draft.monthly_rent_krw || "";
      $("#lrDesiredPrice").value = draft.desired_price || "";
      $("#lrDong").value = draft.dong || "";
      $("#lrHo").value = draft.ho || "";
      $("#lrRegistrantType").value = ["owner", "agent", "other"].indexOf(draft.registrant_type) >= 0 ? draft.registrant_type : "owner";
      $("#lrYieldDeposit").value = draft.deposit_krw || "";
      $("#lrYieldRent").value = draft.yield_rent_krw || "";
      $("#lrDescription").value = draft.description || "";
      var areaSelect = $("#lrArea"), areaManual = $("#lrAreaManual");
      if (draft.area_sqm) {
        var hasArea = Array.prototype.some.call(areaSelect.options, function (option) {
          return option.value === String(draft.area_sqm);
        });
        areaSelect.value = hasArea ? String(draft.area_sqm) : "__manual__";
        areaManual.value = hasArea ? "" : draft.area_sqm;
        areaManual.style.display = hasArea ? "none" : "block";
      }
      updateMode();
      updateDealType();
    }
    function restoreDraftForUser(user) {
      if (isEdit || !buildingId || !user || !user.id) return;
      draftKey = "livingstay:listing-draft:" + String(user.id) + ":" + String(buildingId);
      try {
        var savedDraft = JSON.parse(localStorage.getItem(draftKey) || "null");
        if (!savedDraft || !savedDraft.data || typeof savedDraft.data !== "object") return;
        if (!savedDraft.saved_at || Date.now() - Number(savedDraft.saved_at) > DRAFT_MAX_AGE_MS) {
          localStorage.removeItem(draftKey);
          return;
        }
        if (confirm("이 건물에 이전에 작성 중이던 매물 정보가 있습니다.\n확인을 누르면 불러오고, 취소를 누르면 새로 작성합니다.")) {
          applyDraft(savedDraft.data);
          draftRestored = true;
        } else {
          localStorage.removeItem(draftKey);
        }
      } catch (e) {}
    }
    Array.prototype.forEach.call(overlay.querySelectorAll(".lr-mode"), function (button) {
      button.addEventListener("click", function () { dealMode = button.getAttribute("data-mode"); updateMode(); saveDraft(); });
    });
    Array.prototype.forEach.call(overlay.querySelectorAll(".lr-deal"), function (button) {
      button.addEventListener("click", function () { dealType = button.getAttribute("data-type"); updateDealType(); saveDraft(); });
    });
    ["#lrSalePrice", "#lrJeonseDeposit", "#lrWolseDeposit", "#lrWolseRent", "#lrDesiredPrice",
      "#lrArea", "#lrAreaManual", "#lrDong", "#lrHo", "#lrRegistrantType", "#lrYieldDeposit",
      "#lrYieldRent", "#lrDescription"].forEach(function (selector) {
      $(selector).addEventListener("input", updateYield);
      $(selector).addEventListener("input", saveDraft);
      $(selector).addEventListener("change", saveDraft);
    });
    if (isEdit) $("#lrModeSection").style.display = "none";
    updateMode();
    updateDealType();
    if (draftRestored) {
      setTimeout(function () { setMessage("이전에 작성 중이던 내용을 불러왔습니다."); }, 0);
    }

    function setGateMessage(text, ok) {
      var gateMessage = $("#lrGateMessage");
      gateMessage.textContent = text || "";
      gateMessage.style.color = ok ? "#28733f" : "#b42318";
      gateMessage.style.display = text ? "block" : "none";
    }
    function showPhoneGate() {
      $("#lrAuthLoading").style.display = "none";
      form.style.display = "none";
      phoneGate.style.display = "block";
      $("#lrGateLoading").style.display = "none";
      $("#lrGateFields").style.display = "block";
      $("#lrGatePhone").focus();
    }
    function showListingForm() {
      $("#lrAuthLoading").style.display = "none";
      phoneGate.style.display = "none";
      form.style.display = "block";
      if (draftRestored) {
        setMessage("이전에 작성 중이던 내용을 불러왔습니다.");
        draftRestored = false;
      }
    }
    function startResendCountdown() {
      var button = $("#lrGateSendCode"), remaining = 60;
      if (gateTimer) clearInterval(gateTimer);
      button.disabled = true;
      button.textContent = "재전송 (" + remaining + "초)";
      gateTimer = setInterval(function () {
        remaining -= 1;
        if (remaining <= 0) {
          clearInterval(gateTimer);
          gateTimer = null;
          button.disabled = false;
          button.textContent = "인증번호 재발송";
          return;
        }
        button.textContent = "재전송 (" + remaining + "초)";
      }, 1000);
    }
    function formatGatePhone() {
      var field = $("#lrGatePhone"), digits = field.value.replace(/\D/g, "").slice(0, 11);
      field.value = digits.length > 7 ? digits.slice(0, 3) + "-" + digits.slice(3, 7) + "-" + digits.slice(7) :
        (digits.length > 3 ? digits.slice(0, 3) + "-" + digits.slice(3) : digits);
    }
    if (!isEdit) {
      form.style.display = "none";
      $("#lrAuthLoading").style.display = "block";
      $("#lrGatePhone").addEventListener("input", formatGatePhone);
      $("#lrGateSendCode").addEventListener("click", function () {
        var button = this, phone = ($("#lrGatePhone").value || "").trim();
        if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) {
          setGateMessage("휴대폰 번호 형식이 올바르지 않습니다. 예) 010-1234-5678");
          return;
        }
        setGateMessage("");
        button.disabled = true;
        button.textContent = "발송 중…";
        fetch("/api/auth/send-phone-code", {
          method: "POST", credentials: "same-origin",
          headers: {"Content-Type": "application/json"}, body: JSON.stringify({phone: phone})
        }).then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (data) { return {ok: r.ok, data: data}; });
        }).then(function (result) {
          if (!result.ok || !result.data.ok) throw new Error(result.data.message || "인증번호 발송에 실패했습니다.");
          $("#lrGateCodeWrap").style.display = "block";
          setGateMessage("인증번호를 발송했습니다. 3분 이내에 입력해주세요.", true);
          startResendCountdown();
          $("#lrGateCode").focus();
        }).catch(function (error) {
          button.disabled = false;
          button.textContent = "인증번호 받기";
          setGateMessage(error.message || "네트워크 오류가 발생했습니다.");
        });
      });
      $("#lrGateVerify").addEventListener("click", function () {
        var button = this, code = ($("#lrGateCode").value || "").trim();
        if (!/^\d{6}$/.test(code)) {
          setGateMessage("인증번호 6자리를 입력해주세요.");
          return;
        }
        setGateMessage("");
        button.disabled = true;
        button.textContent = "확인 중…";
        fetch("/api/auth/verify-phone-code", {
          method: "POST", credentials: "same-origin",
          headers: {"Content-Type": "application/json"}, body: JSON.stringify({code: code})
        }).then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (data) { return {ok: r.ok, data: data}; });
        }).then(function (result) {
          if (!result.ok || !result.data.ok) throw new Error(result.data.message || "휴대폰 인증에 실패했습니다.");
          if (gateTimer) clearInterval(gateTimer);
          gateTimer = null;
          if (typeof window.livingstayRefreshAuth === "function") window.livingstayRefreshAuth();
          window.dispatchEvent(new CustomEvent("livingstay:auth"));
          restoreDraftForUser(draftUser);
          showListingForm();
        }).catch(function (error) {
          button.disabled = false;
          button.textContent = "확인";
          setGateMessage(error.message || "네트워크 오류가 발생했습니다.");
        });
      });
      fetch("/api/auth/me", {credentials: "same-origin"})
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (user) {
          draftUser = user && user.logged_in ? user : null;
          // 새 매물 등록은 매번 휴대폰 인증 화면을 먼저 거친다.
          // 기존 인증 번호가 있으면 재입력을 줄이기 위해 번호만 채워 둔다.
          if (user && user.phone) {
            var savedDigits = String(user.phone).replace(/\D/g, "").slice(0, 11);
            $("#lrGatePhone").value = savedDigits.length > 7
              ? savedDigits.slice(0, 3) + "-" + savedDigits.slice(3, 7) + "-" + savedDigits.slice(7)
              : (savedDigits.length > 3 ? savedDigits.slice(0, 3) + "-" + savedDigits.slice(3) : savedDigits);
          }
          if (user && user.phone_verified && user.phone) {
            setGateMessage("매물 등록 전 휴대폰 인증을 한 번 더 진행해주세요.", true);
          }
          showPhoneGate();
        })
        .catch(showPhoneGate);
    }

    function photoIdsFor(items) {
      return items.map(function (item) {
        return item.kind === "existing" ? item.photo.id : null;
      });
    }

    function savePhotoOrder(listingId, items) {
      var photoIds = photoIdsFor(items || photoItems);
      if (!photoIds.length || photoIds.some(function (id) { return id == null; })) return Promise.resolve();
      return fetch("/api/listing-requests/" + listingId + "/photos/order", {
        method: "PUT", credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({photo_ids: photoIds})
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok || !data.ok) throw new Error(data.message || "사진 순서를 저장하지 못했습니다.");
        });
      });
    }

    function persistPhotoOrder() {
      if (!isEdit) return;
      var snapshot = photoItems.slice();
      if (photoIdsFor(snapshot).some(function (id) { return id == null; })) return;
      var version = ++photoOrderVersion;
      photoOrderSaveChain = photoOrderSaveChain.catch(function () {
        // 이전 저장 실패는 사용자에게 이미 알렸고, 최신 순서 저장은 계속 시도한다.
      }).then(function () {
        return savePhotoOrder(editId, snapshot);
      }).then(function () {
        confirmedPhotoItems = snapshot.slice();
      }).catch(function (error) {
        if (version !== photoOrderVersion) return;
        var confirmedExistingItems = confirmedPhotoItems.filter(function (item) {
          return item.kind === "existing";
        });
        var existingIndex = 0;
        // 서버에 이미 있던 사진만 마지막 저장 순서로 되돌리고, 그 사이 새로 고른
        // 로컬 사진은 현재 위치에 그대로 둬서 업로드 대상이 사라지지 않게 한다.
        photoItems = photoItems.map(function (item) {
          return item.kind === "existing" ? confirmedExistingItems[existingIndex++] : item;
        }).filter(Boolean);
        renderPhotos();
        setMessage((error.message || "사진 순서를 저장하지 못했습니다.") + " 마지막으로 저장된 순서로 되돌렸습니다.");
      });
    }

    function movePhoto(from, to) {
      if (to < 0 || to >= photoItems.length || from === to) return;
      var item = photoItems.splice(from, 1)[0];
      photoItems.splice(to, 0, item);
      renderPhotos();
      persistPhotoOrder();
    }

    function removePhoto(index) {
      var item = photoItems[index];
      if (!item) return;
      if (item.kind !== "existing") {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
        photoItems.splice(index, 1);
        renderPhotos();
        return;
      }
      if (!isEdit || !confirm("이 사진을 삭제할까요?")) return;
      fetch("/api/listing-requests/" + editId + "/photos/" + item.photo.id, {
        method: "DELETE", credentials: "same-origin"
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok || !data.ok) throw new Error(data.message || "삭제하지 못했습니다.");
        });
      }).then(function () {
        photoItems.splice(index, 1);
        confirmedPhotoItems = photoItems.slice();
        renderPhotos();
      }).catch(function (error) {
        setMessage(error.message || "사진 삭제에 실패했습니다.");
      });
    }

    function renderPhotos() {
      var grid = $("#lrPhotoGrid");
      grid.innerHTML = "";
      photoItems.forEach(function (item, index) {
        var card = document.createElement("div");
        var photoUrl = item.kind === "existing" ? item.photo.url : item.previewUrl;
        var photoAlt = item.kind === "existing" ? "기존 매물 사진" : "새 사진 미리보기";
        card.style.cssText = "position:relative;width:82px;height:104px;";
        card.innerHTML =
          '<img src="' + esc(photoUrl) + '" alt="' + photoAlt + '" style="width:82px;height:76px;object-fit:cover;border-radius:7px;border:1px solid #eee;">' +
          (index === 0
            ? '<span style="position:absolute;left:3px;top:3px;padding:2px 4px;border-radius:4px;background:var(--brass,#b4863f);color:#fff;font-size:9px;font-weight:800;">대표</span>'
            : '<button type="button" class="lr-photo-cover" aria-label="대표사진으로 지정" style="position:absolute;left:3px;top:3px;border:0;border-radius:4px;padding:3px 4px;background:rgba(22,32,46,.78);color:#fff;font-size:9px;font-weight:700;cursor:pointer;">대표로</button>') +
          '<button type="button" class="lr-photo-remove" aria-label="사진 삭제" style="position:absolute;right:-4px;top:-5px;width:21px;height:21px;border:0;border-radius:50%;background:#333;color:#fff;cursor:pointer;line-height:18px;">×</button>' +
          '<div style="display:flex;gap:3px;margin-top:4px;">' +
            '<button type="button" class="lr-photo-prev" aria-label="사진 앞으로 이동" ' + (index === 0 ? "disabled" : "") + ' style="flex:1;border:1px solid var(--line,#ddd);border-radius:4px;background:#fff;padding:2px 0;font-size:11px;cursor:' + (index === 0 ? "default" : "pointer") + ';">←</button>' +
            '<button type="button" class="lr-photo-next" aria-label="사진 뒤로 이동" ' + (index === photoItems.length - 1 ? "disabled" : "") + ' style="flex:1;border:1px solid var(--line,#ddd);border-radius:4px;background:#fff;padding:2px 0;font-size:11px;cursor:' + (index === photoItems.length - 1 ? "default" : "pointer") + ';">→</button>' +
          '</div>';
        var cover = card.querySelector(".lr-photo-cover");
        if (cover) cover.addEventListener("click", function () { movePhoto(index, 0); });
        card.querySelector(".lr-photo-remove").addEventListener("click", function () {
          removePhoto(index);
        });
        card.querySelector(".lr-photo-prev").addEventListener("click", function () { movePhoto(index, index - 1); });
        card.querySelector(".lr-photo-next").addEventListener("click", function () { movePhoto(index, index + 1); });
        grid.appendChild(card);
      });
    }
    function addPhotos(files) {
      var candidates = Array.prototype.slice.call(files || []);
      var errors = [];
      candidates.forEach(function (file) {
        var ext = (file.name.split(".").pop() || "").toLowerCase();
        if (["jpg", "jpeg", "png"].indexOf(ext) < 0) errors.push(file.name + ": JPG 또는 PNG만 가능합니다.");
        else if (file.size > MAX_PHOTO_BYTES) errors.push(file.name + ": 5MB 이하만 가능합니다.");
        else if (photoItems.length >= MAX_PHOTOS) errors.push("사진은 최대 " + MAX_PHOTOS + "장까지 첨부할 수 있습니다.");
        else photoItems.push({kind: "pending", file: file, previewUrl: URL.createObjectURL(file)});
      });
      $("#lrPhotoInput").value = "";
      renderPhotos();
      setMessage(errors.join(" "));
    }
    $("#lrDropZone").addEventListener("click", function () { $("#lrPhotoInput").click(); });
    $("#lrDropZone").addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#lrPhotoInput").click(); } });
    $("#lrPhotoInput").addEventListener("change", function () { addPhotos(this.files); });
    ["dragenter", "dragover"].forEach(function (eventName) {
      $("#lrDropZone").addEventListener(eventName, function (event) { event.preventDefault(); this.style.background = "#fff3df"; });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      $("#lrDropZone").addEventListener(eventName, function (event) { event.preventDefault(); this.style.background = "#fffaf2"; });
    });
    $("#lrDropZone").addEventListener("drop", function (event) { addPhotos(event.dataTransfer.files); });
    renderPhotos();

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      setMessage("");
      var price = null, rent = null;
      if (dealType === "매매") price = numValue($("#lrSalePrice"));
      if (dealType === "전세") price = numValue($("#lrJeonseDeposit"));
      if (dealType === "월세") { price = numValue($("#lrWolseDeposit")); rent = numValue($("#lrWolseRent")); }
      var body = {
        deal_type: dealType, desired_price: dealType === "단기임대" ? ($("#lrDesiredPrice").value || "").trim() : priceText(dealType, price, rent),
        price_krw: price, monthly_rent_krw: rent, area_sqm: ($("#lrArea").value === "__manual__" ? ($("#lrAreaManual").value || "").trim() : ($("#lrArea").value || "").trim()),
        dong: ($("#lrDong").value || "").trim(), ho: ($("#lrHo").value || "").trim(),
        registrant_type: $("#lrRegistrantType").value, description: ($("#lrDescription").value || "").trim(),
        deposit_krw: numValue($("#lrYieldDeposit")), yield_rent_krw: numValue($("#lrYieldRent"))
      };
      if (!isEdit) { body.master_building_id = parseInt(buildingId, 10); body.deal_mode = dealMode; }
      submit.disabled = true; submit.textContent = "처리 중…";
      var savedListingId = null;
      fetch(isEdit ? "/api/listing-requests/" + editId : "/api/listing-requests", {
        method: isEdit ? "PUT" : "POST", credentials: "same-origin",
        headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) { return {ok:r.ok, data:data}; });
      }).then(function (result) {
        if (!result.ok || !result.data.ok) throw new Error(result.data.message || "저장에 실패했습니다.");
        var listingId = isEdit ? editId : result.data.id;
        savedListingId = listingId;
        return photoItems.reduce(function (chain, item) {
          if (item.kind !== "pending") return chain;
          return chain.then(function () {
            return uploadPhoto(listingId, item.file).then(function (data) {
              if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
              item.kind = "existing";
              item.photo = {id: data.id, url: data.src};
              delete item.file;
              delete item.previewUrl;
            });
          });
        }, Promise.resolve()).then(function () {
          return savePhotoOrder(listingId);
        });
      }).then(function () {
        clearDraft();
        form.style.display = "none"; $("#lrDone").style.display = "block";
        if (typeof options.onSuccess === "function") options.onSuccess();
      }).catch(function (error) {
        if (savedListingId) {
          clearDraft();
          form.style.display = "none";
          $("#lrDone").innerHTML = '<div style="font-size:18px;font-weight:800;">매물 정보는 저장했습니다</div><div style="font-size:13px;color:var(--ink-soft);margin-top:8px;">일부 사진은 업로드하지 못했습니다. 마이페이지에서 다시 수정해 주세요.</div>';
          $("#lrDone").style.display = "block";
          if (typeof options.onSuccess === "function") options.onSuccess();
          return;
        }
        submit.disabled = false; submit.textContent = isEdit ? "저장" : "매물의뢰 접수하기";
        setMessage(error.message || "네트워크 오류가 발생했습니다.");
      });
    });
  };
})();