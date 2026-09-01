(function () {
  "use strict";

  var MAX_PHOTOS = 10;
  var MAX_PHOTO_BYTES = 10 * 1024 * 1024;
  var DEAL_TYPES = ["매매", "전세", "월세", "단기임대"];
  var WHOLE_DEAL_TYPES = ["매매", "통임대", "운영권양도", "위탁운영"];
  var WHOLE_DESCRIPTION_TEMPLATE = "■ 매물 개요\n- 건물 전체 거래 매물입니다.\n- 매매·임대·운영 조건은 협의 가능합니다.\n\n" +
    "■ 건물 정보\n- 대지면적:\n- 연면적:\n- 층수:\n- 사용승인일:\n- 용도지역:\n- 주차:\n- 승강기:\n- 구조:\n\n" +
    "■ 운영 현황\n- 월평균 매출:\n- 연매출:\n- 운영상태:\n- 리모델링:\n\n" +
    "■ 거래 조건\n- 거래방식:\n- 권리금:\n- 급매 여부:\n\n" +
    "■ 매도 사유\n- \n\n" +
    "■ 인수인계 조건\n- 희망 인수인계 시기:\n- 직원 고용승계:\n- 시설·집기 포함 여부:\n\n" +
    "■ 기타 안내\n- 상세 조건은 상담을 통해 안내드립니다.";
  var WHOLE_ACQUISITION_COST_RATE = 0.061;
  var REGISTRANT_TYPES = [
    {value: "owner", label: "소유자 또는 대리인"},
    {value: "building_owner", label: "건물주 또는 대리인"},
    {value: "business", label: "사업주(숙박업대표) 또는 대리인"}
  ];
  var LEGACY_REGISTRANT_LABELS = {agent: "기존 등록자유형: 중개사", other: "기존 등록자유형: 기타 관계자"};
  var DRAFT_REGISTRANT_LABELS = {
    owner: "소유자 등록",
    building_owner: "건물주 등록",
    business: "사업주 등록",
    agent: "중개사 등록",
    other: "기타 관계자 등록"
  };

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

  function priceText(dealType, price, rent, priceMax) {
    var range = price
      ? (priceMax ? price + "만원 ~ " + priceMax + "만원" : price + "만원")
      : "";
    if (dealType === "매매") return range ? "매매가 " + range : "";
    if (dealType === "전세") return range ? "전세 " + range : "";
    if (dealType === "월세" && priceMax) return "월세 " + range;
    if (dealType === "단기임대" && price) return "단기임대 " + range;
    if (dealType === "월세") return price || rent ? "보증금 " + (price || 0) + "만원 / 월세 " + (rent || 0) + "만원" : "";
    return "";
  }

  function photoArray(value) {
    return Array.isArray(value) ? value.filter(function (p) {
      return p && p.id != null && p.url;
    }) : [];
  }

  function uploadPhoto(listingId, file, isPublic) {
    var form = new FormData();
    form.append("file", file, file.name);
    form.append("is_public", isPublic ? "true" : "false");
    return fetch("/api/listing-requests/" + listingId + "/photos", {
      method: "POST", credentials: "same-origin", body: form
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok || !data.ok) throw new Error(data.message || "사진 업로드에 실패했습니다.");
        return data;
      });
    });
  }

  function validRegistrantType(value) {
    var allowed = REGISTRANT_TYPES.map(function (item) { return item.value; });
    return allowed.indexOf(value) >= 0 || Object.prototype.hasOwnProperty.call(LEGACY_REGISTRANT_LABELS, value);
  }

  function draftRegistrantLabel(value) {
    return DRAFT_REGISTRANT_LABELS[value] || "등록자유형 미상";
  }

  function draftDealLabel(value) {
    return DEAL_TYPES.indexOf(value) >= 0 ? value : "거래유형 미상";
  }

  function registrantOptions(selectedValue) {
    var html = REGISTRANT_TYPES.map(function (item) {
      return '<option value="' + item.value + '">' + item.label + '</option>';
    }).join("");
    if (Object.prototype.hasOwnProperty.call(LEGACY_REGISTRANT_LABELS, selectedValue)) {
      html += '<option value="' + selectedValue + '" hidden>' + LEGACY_REGISTRANT_LABELS[selectedValue] + '</option>';
    }
    return html;
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

    var presetDealType = options.presetDealType;
    var presetRegistrantType = options.presetRegistrantType;
    var transactionTarget = (prefill.transaction_target || prefill.listing_target) === "whole" ? "whole" : "unit";
    var dealType = presetDealType || prefill.deal_type || "매매";
    if ((transactionTarget === "whole" ? WHOLE_DEAL_TYPES : DEAL_TYPES).indexOf(dealType) < 0) dealType = "매매";
    var dealMode = prefill.deal_mode || "direct";
    if (dealMode !== "broker") dealMode = "direct";
    var photoItems = photoArray(prefill.photos || prefill.existing_photos).map(function (photo) {
      return { kind: "existing", photo: photo, isPublic: photo.is_public !== false };
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
        '<div id="lrBusinessVerifyGate" style="display:none;padding:28px 18px 24px;">' +
          '<div style="font-size:17px;font-weight:800;color:var(--ink,#16202e);">사업주 영업신고번호 확인</div>' +
          '<p id="lrBusinessVerifyHelp" style="margin:8px 0 18px;color:var(--ink-soft,#6b7684);font-size:13px;line-height:1.55;">이 건물에 등록된 대표 숙박업 영업신고번호를 확인해주세요.<br>하이픈과 공백은 입력하지 않아도 됩니다.</p>' +
          '<div id="lrBusinessVerifyLoading" style="font-size:13px;color:var(--ink-soft,#6b7684);">인증 상태를 확인하고 있습니다.</div>' +
          '<div id="lrBusinessVerifyFields" style="display:none;"><input id="lrBusinessPermitNumber" type="text" inputmode="numeric" autocomplete="off" placeholder="영업신고번호" style="' + inputStyle() + '">' +
          '<button type="button" id="lrBusinessVerifySubmit" style="width:100%;margin-top:8px;border:0;border-radius:8px;padding:11px;background:#4A7A18;color:#fff;font:700 13px inherit;cursor:pointer;">신고번호 확인</button>' +
          '<div id="lrBusinessVerifyMessage" aria-live="polite" style="display:none;margin-top:9px;font-size:12.5px;"></div></div>' +
        '</div>' +
        '<form id="lrForm" style="padding:16px 18px 20px;">' +
          '<section id="lrModeSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">진행 방식</div>' +
          '<div style="display:flex;gap:8px;"><button type="button" class="lr-mode" data-mode="direct" style="flex:1;padding:9px;border-radius:8px;border:1px solid #4A7A18;background:' + (dealMode === "direct" ? "#4A7A18" : "#fff") + ';color:' + (dealMode === "direct" ? "#fff" : "#4A7A18") + ';font:700 13px inherit;cursor:pointer;">직거래</button>' +
          '<button type="button" class="lr-mode" data-mode="broker" style="flex:1;padding:9px;border-radius:8px;border:1px solid var(--brass,#b4863f);background:' + (dealMode === "broker" ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (dealMode === "broker" ? "#fff" : "var(--brass,#b4863f)") + ';font:700 13px inherit;cursor:pointer;">중개사 연결</button></div>' +
          '<div id="lrModeHelp" style="font-size:11.5px;color:var(--ink-soft);margin-top:6px;"></div></section>' +
            '<section id="lrTargetSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">STEP 2 · 거래대상</div>' +
            '<div style="display:flex;gap:8px;"><button type="button" class="lr-target" data-target="unit" style="flex:1;padding:9px;border-radius:8px;border:1px solid #4A7A18;background:' + (transactionTarget === "unit" ? "#4A7A18" : "#fff") + ';color:' + (transactionTarget === "unit" ? "#fff" : "#4A7A18") + ';font:700 13px inherit;cursor:pointer;">개별호실</button>' +
            '<button type="button" class="lr-target" data-target="whole" style="flex:1;padding:9px;border-radius:8px;border:1px solid var(--brass,#b4863f);background:' + (transactionTarget === "whole" ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (transactionTarget === "whole" ? "#fff" : "var(--brass,#b4863f)") + ';font:700 13px inherit;cursor:pointer;">건물전체</button></div>' +
            '<div id="lrTargetHelp" style="font-size:11.5px;color:var(--ink-soft);margin-top:6px;"></div></section>' +
            '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">STEP 3 · 등록자유형</div>' +
            '<select id="lrRegistrantType" style="' + inputStyle() + '">' + registrantOptions(presetRegistrantType || prefill.registrant_type) + '</select></section>' +
           '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">STEP 4 · 거래 방식</div>' +
           '<div id="lrUnitDealButtons" style="display:' + (transactionTarget === "unit" ? "flex" : "none") + ';gap:6px;flex-wrap:wrap;">' + DEAL_TYPES.map(function (dt) {
            return '<button type="button" class="lr-deal" data-type="' + dt + '" style="padding:7px 11px;border-radius:7px;border:1px solid ' + (dt === dealType ? "var(--brass,#b4863f)" : "var(--line,#e2ddd8)") + ';background:' + (dt === dealType ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (dt === dealType ? "#fff" : "var(--ink,#16202e)") + ';font:700 12.5px inherit;cursor:pointer;">' + dt + '</button>';
           }).join("") + '</div><div id="lrWholeDealButtons" style="display:' + (transactionTarget === "whole" ? "flex" : "none") + ';gap:6px;flex-wrap:wrap;">' + WHOLE_DEAL_TYPES.map(function (dt) {
             return '<button type="button" class="lr-deal" data-type="' + dt + '" style="padding:7px 11px;border-radius:7px;border:1px solid ' + (dt === dealType ? "var(--brass,#b4863f)" : "var(--line,#e2ddd8)") + ';background:' + (dt === dealType ? "var(--brass,#b4863f)" : "#fff") + ';color:' + (dt === dealType ? "#fff" : "var(--ink,#16202e)") + ';font:700 12.5px inherit;cursor:pointer;">' + dt + '</button>';
           }).join("") + '</div></section>' +
            '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">매물 정보</div>' +
           '<div id="lrPriceSale" class="lr-field"><label class="lr-field-label" for="lrSalePrice">매매가<span id="lrUnitUrgentSlot"></span></label><input id="lrSalePrice" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div>' +
           '<div id="lrPriceJeonse" class="lr-field"><label class="lr-field-label" for="lrJeonseDeposit">전세 보증금</label><input id="lrJeonseDeposit" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div>' +
           '<div id="lrPriceWolse" class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrWolseDeposit">보증금</label><input id="lrWolseDeposit" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrWolseRent">월세</label><input id="lrWolseRent" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.monthly_rent_krw || "") + '" style="' + inputStyle() + '"></div></div>' +
            '<div id="lrPriceWolseBusiness" class="lr-field-row" style="display:none;"><div class="lr-field"><label class="lr-field-label" for="lrWolsePriceMin">월 최저가</label><input id="lrWolsePriceMin" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrWolsePriceMax">월 최고가</label><input id="lrWolsePriceMax" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw_max || "") + '" style="' + inputStyle() + '"></div></div>' +
            '<div id="lrShortTerm" class="lr-field"><label class="lr-field-label" for="lrDesiredPrice">희망 조건</label><input id="lrDesiredPrice" maxlength="100" placeholder="선택" value="' + esc(prefill.desired_price || "") + '" style="' + inputStyle() + '"></div>' +
             '<div id="lrShortTermBusiness" class="lr-field-row" style="display:none;"><div class="lr-field"><label class="lr-field-label" for="lrShortPriceMin">최저가</label><input id="lrShortPriceMin" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw || "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrShortPriceMax">최고가</label><input id="lrShortPriceMax" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.price_krw_max || "") + '" style="' + inputStyle() + '"></div></div>' +
              '<div id="lrWholeSale" class="lr-whole-terms" style="display:none;"><div class="lr-field"><label class="lr-field-label" for="lrWholeSalePrice">매매가<span id="lrWholeUrgentSlot"></span></label><input id="lrWholeSalePrice" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "매매" ? prefill.price_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrSaleKeyMoney">권리금</label><input id="lrSaleKeyMoney" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "매매" ? prefill.key_money_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrSaleLoan">승계융자</label><input id="lrSaleLoan" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "매매" ? prefill.succession_loan_krw || "" : "") + '" style="' + inputStyle() + '"></div></div></div>' +
             '<div id="lrWholeLease" class="lr-whole-terms" style="display:none;"><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrWholeLeaseDeposit">보증금</label><input id="lrWholeLeaseDeposit" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "통임대" ? prefill.price_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrWholeLeaseRent">월세</label><input id="lrWholeLeaseRent" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "통임대" ? prefill.monthly_rent_krw || "" : "") + '" style="' + inputStyle() + '"></div></div><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrLeaseKeyMoney">권리금</label><input id="lrLeaseKeyMoney" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "통임대" ? prefill.key_money_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrLeaseLoan">승계융자</label><input id="lrLeaseLoan" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "통임대" ? prefill.succession_loan_krw || "" : "") + '" style="' + inputStyle() + '"></div></div></div>' +
             '<div id="lrWholeTransfer" class="lr-whole-terms" style="display:none;"><div class="lr-field"><label class="lr-field-label" for="lrWholeTransferPrice">양도금</label><input id="lrWholeTransferPrice" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "운영권양도" ? prefill.price_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrTransferKeyMoney">권리금</label><input id="lrTransferKeyMoney" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "운영권양도" ? prefill.key_money_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrTransferLoan">승계융자</label><input id="lrTransferLoan" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "운영권양도" ? prefill.succession_loan_krw || "" : "") + '" style="' + inputStyle() + '"></div></div></div>' +
             '<div id="lrWholeConsign" class="lr-whole-terms" style="display:none;"><div class="lr-field"><label class="lr-field-label" for="lrWholeConsignDeposit">보증금</label><input id="lrWholeConsignDeposit" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "위탁운영" ? prefill.price_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrConsignKeyMoney">권리금</label><input id="lrConsignKeyMoney" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "위탁운영" ? prefill.key_money_krw || "" : "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrConsignLoan">승계융자</label><input id="lrConsignLoan" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(dealType === "위탁운영" ? prefill.succession_loan_krw || "" : "") + '" style="' + inputStyle() + '"></div></div></div><div id="lrWholeFinanceSummary" style="display:none;margin-top:8px;"><div id="lrRealTakeover" style="padding:10px 11px;border-radius:8px;background:#fff7ea;color:var(--brass,#b4863f);font-size:12px;font-weight:700;">실인수가 계산</div><div style="margin-top:5px;font-size:11px;color:var(--ink-soft);">거래금액 - 승계융자 + 권리금 + 예상 부대비용 6.1%의 참고값이며 저장되지 않습니다.</div></div></section>' +
             '<section id="lrUnitDetailSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">상세 정보 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div>' +
            '<div style="display:flex;gap:7px;margin-bottom:7px;"><div style="flex:1;"><div id="lrAreaOwnerWrap"><select id="lrArea" style="' + inputStyle() + '"><option value="">전용면적 선택</option></select><input id="lrAreaManual" type="number" min="0" step="0.01" inputmode="decimal" placeholder="전용면적 직접 입력 ㎡" style="' + inputStyle("display:none;margin-top:6px;") + '"></div><div id="lrAreaBusinessWrap" style="display:none;"><input id="lrAreaBusiness" type="number" min="0" step="0.01" inputmode="decimal" placeholder="평균 전용면적(㎡) 예: 18" value="' + esc(prefill.area_sqm || "") + '" style="' + inputStyle() + '"></div></div><input id="lrDong" maxlength="20" placeholder="동" value="' + esc(prefill.dong || "") + '" style="' + inputStyle("flex:.55;") + '"><input id="lrHo" maxlength="20" placeholder="호" value="' + esc(prefill.ho || "") + '" style="' + inputStyle("flex:.55;") + '"></div>' +
           '</section>' +
            '<section id="lrRoomCountSection" style="display:none;margin-bottom:17px;"><div class="lr-field"><label class="lr-field-label" for="lrRoomCount">총 객실수</label><input id="lrRoomCount" type="number" min="1" max="100000" step="1" inputmode="numeric" placeholder="직접 입력 가능" value="' + esc(prefill.room_count || "") + '" style="' + inputStyle() + '"></div><div id="lrRoomCountHelp" style="display:none;margin-top:6px;font-size:11.5px;color:var(--ink-soft);"></div></section>' +
          '<section id="lrYieldSection" style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">예상 수익률 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div>' +
          '<div style="display:flex;gap:7px;"><input id="lrYieldDeposit" type="number" min="1" inputmode="numeric" placeholder="보증금 (만원)" value="' + esc(prefill.deposit_krw || "") + '" style="' + inputStyle("flex:1;") + '"><input id="lrYieldRent" type="number" min="1" inputmode="numeric" placeholder="월 임대료 (만원)" value="' + esc(prefill.yield_rent_krw || "") + '" style="' + inputStyle("flex:1;") + '"></div><div id="lrYieldResult" style="font-size:11.5px;color:var(--brass,#b4863f);margin-top:6px;"></div></section>' +
             '<section id="lrWholeOperationSection" style="display:none;margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">STEP 5 · 운영정보</div><div class="lr-field-row"><div class="lr-field"><label class="lr-field-label" for="lrMonthlyRevenue">월평균매출</label><input id="lrMonthlyRevenue" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.monthly_revenue_krw || "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrAnnualRevenue">연매출</label><input id="lrAnnualRevenue" type="number" min="1" inputmode="numeric" placeholder="만원" value="' + esc(prefill.annual_revenue_krw || "") + '" style="' + inputStyle() + '"></div></div><div class="lr-field-row" style="margin-top:7px;"><div class="lr-field"><label class="lr-field-label" for="lrShortStayRatio">대실 비율</label><input id="lrShortStayRatio" type="number" min="0" max="100" step="0.1" inputmode="decimal" placeholder="선택 · %" value="' + esc(prefill.short_stay_ratio || "") + '" style="' + inputStyle() + '"></div><div class="lr-field"><label class="lr-field-label" for="lrOtaRevenueRatio">OTA 매출 비중</label><input id="lrOtaRevenueRatio" type="number" min="0" max="100" step="0.1" inputmode="decimal" placeholder="선택 · %" value="' + esc(prefill.ota_revenue_ratio || "") + '" style="' + inputStyle() + '"></div></div><div class="lr-field-row" style="margin-top:7px;"><div class="lr-field"><label class="lr-field-label" for="lrOperationStatus">운영상태</label><select id="lrOperationStatus" style="' + inputStyle() + '"><option value="">선택</option><option value="영업중">영업중</option><option value="휴업">휴업</option><option value="폐업">폐업</option></select></div><div class="lr-field"><label class="lr-field-label" for="lrClosedAt">폐업일</label><input id="lrClosedAt" type="date" value="' + esc(prefill.closed_at || "") + '" style="' + inputStyle("display:none;") + '"></div></div><div class="lr-field" style="margin-top:7px;"><label class="lr-field-label" for="lrRemodelingInfo">리모델링 정보</label><textarea id="lrRemodelingInfo" maxlength="500" rows="2" placeholder="시기·범위·비용 등" style="' + inputStyle("resize:vertical;") + '">' + esc(prefill.remodeling_info || "") + '</textarea></div><div style="margin-top:8px;font-size:12px;"><label>공개범위 <select id="lrDisclosureScope" style="margin-left:4px;border:1px solid var(--line);border-radius:5px;padding:4px;"><option value="limited">제한공개</option><option value="public">전체공개</option></select></label></div><div id="lrDisclosureHelp" style="margin-top:6px;font-size:11.5px;color:var(--ink-soft);line-height:1.5;"></div></section>' +
              '<span id="lrUrgentSection" style="display:none;align-items:center;margin-left:10px;white-space:nowrap;font-size:12px;font-weight:400;color:var(--ink-soft);vertical-align:middle;">' +
              '<label for="lrUrgentSale" style="display:inline-flex;align-items:center;gap:3px;cursor:pointer;"><input id="lrUrgentSale" type="checkbox"' + (prefill.is_urgent ? " checked" : "") + ' style="width:15px;height:15px;margin:0;accent-color:var(--brass,#B4863F);"><span>급매</span></label>' +
              '</span>' +
           '<section id="lrWholeBuildingSection" style="display:none;margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">STEP 6 · 건물정보</div><div id="lrWholeBuildingInfo" style="padding:10px;border:1px solid var(--line);border-radius:8px;background:#fcfbf9;font-size:12px;color:var(--ink-soft);">건물 정보를 불러오는 중…</div><a href="/contact" style="display:inline-block;margin-top:7px;font-size:11.5px;color:var(--brass,#b4863f);">건물정보 수정 요청하기</a></section>' +
           '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">매물 설명 <span style="font-weight:400;color:var(--ink-soft);">선택</span></div><textarea id="lrDescription" maxlength="500" rows="4" aria-describedby="lrDescriptionHint" placeholder="매물의 장점, 입주 가능일 등을 적어주세요." style="' + inputStyle("resize:vertical;line-height:1.5;") + '">' + esc(prefill.description || "") + '</textarea><div id="lrDescriptionHint" style="margin-top:5px;font-size:11px;color:var(--ink-soft);">Enter 키를 누르면 다음 줄에 작성할 수 있습니다.</div></section>' +
           '<section style="margin-bottom:17px;"><div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">사진 <span style="font-weight:400;color:var(--ink-soft);">최대 10장 · JPG/PNG · 장당 5MB · 첫 사진이 대표사진</span></div>' +
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
    var phoneGate = $("#lrPhoneVerifyGate"), businessGate = $("#lrBusinessVerifyGate"), gateTimer = null;
    var initialRegistrantType = validRegistrantType(presetRegistrantType)
      ? presetRegistrantType
      : (validRegistrantType(prefill.registrant_type) ? prefill.registrant_type : "owner");
    $("#lrRegistrantType").value = initialRegistrantType;
    $("#lrOperationStatus").value = prefill.operation_status || "";
    $("#lrDisclosureScope").value = prefill.disclosure_scope === "public" ? "public" : "limited";
    var areaTypesLoaded = false;
    var lodgingSummaryLoaded = false;
    var wholeContextLoaded = false;
    var wholeBuildingInfo = {};

    function isWholeListing() {
      return transactionTarget === "whole";
    }

    var WHOLE_TERM_FIELDS = {
      "매매": {section: "#lrWholeSale", price: "#lrWholeSalePrice", rent: null, keyMoney: "#lrSaleKeyMoney", loan: "#lrSaleLoan"},
      "통임대": {section: "#lrWholeLease", price: "#lrWholeLeaseDeposit", rent: "#lrWholeLeaseRent", keyMoney: "#lrLeaseKeyMoney", loan: "#lrLeaseLoan"},
      "운영권양도": {section: "#lrWholeTransfer", price: "#lrWholeTransferPrice", rent: null, keyMoney: "#lrTransferKeyMoney", loan: "#lrTransferLoan"},
      "위탁운영": {section: "#lrWholeConsign", price: "#lrWholeConsignDeposit", rent: null, keyMoney: "#lrConsignKeyMoney", loan: "#lrConsignLoan"}
    };

    function wholeTermsForCurrentDeal() {
      return WHOLE_TERM_FIELDS[dealType] || WHOLE_TERM_FIELDS["매매"];
    }

    function wholeTermValue(name) {
      var fields = wholeTermsForCurrentDeal();
      return fields[name] ? numValue($(fields[name])) : null;
    }

    function setWholeTermValues(values) {
      var fields = wholeTermsForCurrentDeal();
      ["price", "rent", "keyMoney", "loan"].forEach(function (name) {
        if (fields[name] && values[name] != null) $(fields[name]).value = values[name];
      });
    }

    function wholeTermsDraftData() {
      var result = {};
      Object.keys(WHOLE_TERM_FIELDS).forEach(function (wholeDealType) {
        var fields = WHOLE_TERM_FIELDS[wholeDealType];
        result[wholeDealType] = {
          price: fields.price ? $(fields.price).value || "" : "",
          rent: fields.rent ? $(fields.rent).value || "" : "",
          keyMoney: fields.keyMoney ? $(fields.keyMoney).value || "" : "",
          loan: fields.loan ? $(fields.loan).value || "" : ""
        };
      });
      return result;
    }

    function applyWholeTermsDraftData(values) {
      if (!values || typeof values !== "object") return;
      Object.keys(WHOLE_TERM_FIELDS).forEach(function (wholeDealType) {
        var fields = WHOLE_TERM_FIELDS[wholeDealType];
        var terms = values[wholeDealType] || {};
        ["price", "rent", "keyMoney", "loan"].forEach(function (name) {
          if (fields[name] && terms[name] != null) $(fields[name]).value = terms[name];
        });
      });
    }

    function formatBuildingInfoValue(key, value) {
      if (value == null || value === "") return "정보 없음";
      if (key === "site_area_sqm" || key === "total_area_sqm") return Number(value).toLocaleString() + "㎡";
      if (key === "above_ground_floors" || key === "below_ground_floors") return Number(value).toLocaleString() + "층";
      if (key === "parking_spaces") return Number(value).toLocaleString() + "대";
      if (key === "elevators") return Number(value).toLocaleString() + "대";
      return String(value);
    }

    function renderWholeBuildingInfo(info, nearby, subway) {
      wholeBuildingInfo = info || {};
      var labels = {
        site_area_sqm: "대지면적", total_area_sqm: "연면적", above_ground_floors: "지상층수",
        below_ground_floors: "지하층수", approval_date: "사용승인일", zoning: "용도지역",
        parking_spaces: "주차", elevators: "승강기", structure: "구조"
      };
      var saved = prefill.building_info_overrides || {};
        var html = Object.keys(labels).map(function (key) {
        var value = wholeBuildingInfo[key];
          if (key === "zoning" && (value == null || value === "")) return "";
        if (value != null && value !== "") {
          return '<div style="display:flex;justify-content:space-between;gap:10px;padding:3px 0;"><span>' + labels[key] + '</span><b style="color:var(--ink);text-align:right;">' + esc(formatBuildingInfoValue(key, value)) + '</b></div>';
        }
        return '<label style="display:flex;align-items:center;gap:8px;padding:3px 0;"><span style="min-width:76px;">' + labels[key] + '</span><input data-building-info-key="' + key + '" value="' + esc(saved[key] || "") + '" placeholder="정보 없음 · 직접 입력" style="' + inputStyle("padding:6px 8px;font-size:11.5px;") + '"></label>';
      }).join("");
      if (nearby) {
        var nearbyTotal = Number(nearby["일반"] || 0) + Number(nearby["관광"] || 0) + Number(nearby["복합"] || 0) + Number(nearby["생활"] || 0);
        html += '<div style="border-top:1px solid var(--line);margin-top:8px;padding-top:8px;color:var(--ink);">반경 500m 내 동종 숙박시설 ' + nearbyTotal.toLocaleString() + '곳 · 일반 ' + Number(nearby["일반"] || 0).toLocaleString() + ' · 관광 ' + Number(nearby["관광"] || 0).toLocaleString() + ' · 복합 ' + Number(nearby["복합"] || 0).toLocaleString() + ' · 생활 ' + Number(nearby["생활"] || 0).toLocaleString() + '</div>';
      }
      var stationName = subway && (subway.station_name || subway.name);
      if (stationName && subway.walk_minutes != null) {
        html += '<div style="margin-top:4px;color:var(--ink);">' + esc(stationName) + '까지 도보 약 ' + esc(subway.walk_minutes) + '분</div>';
      }
      $("#lrWholeBuildingInfo").innerHTML = html || "건물 정보가 없습니다.";
    }

    function loadWholeListingContext() {
      if (!buildingId || wholeContextLoaded) return;
      wholeContextLoaded = true;
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/whole-listing-context", {credentials: "same-origin"})
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.ok) throw new Error("건물 정보를 불러오지 못했습니다.");
          renderWholeBuildingInfo((data.building || {}).info || {}, data.nearby_lodgings, data.subway);
          if (data.suggested_room_count != null) {
            var roomInput = $("#lrRoomCount");
            if (!roomInput.value) roomInput.value = String(data.suggested_room_count);
            var roomHelp = $("#lrRoomCountHelp");
            roomHelp.textContent = "영업신고 기준 " + Number(data.suggested_room_count).toLocaleString() + "실을 입력했습니다. 실제와 다르면 수정해주세요.";
            roomHelp.style.display = "block";
          }
        })
        .catch(function () {
          $("#lrWholeBuildingInfo").textContent = "건물 정보를 불러오지 못했습니다. 직접 입력 항목은 저장할 수 있습니다.";
        });
    }

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

    function loadAreaTypes() {
      if (!buildingId || areaTypesLoaded) return;
      areaTypesLoaded = true;
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/area-types", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) { populateAreaTypes(data.items || []); })
        .catch(function () { populateAreaTypes([]); });
    }

    function loadLodgingSummary() {
      if (!buildingId || lodgingSummaryLoaded) return;
      lodgingSummaryLoaded = true;
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/lodging-summary", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.ok || data.room_count == null) return;
          var roomInput = $("#lrRoomCount");
          if (!roomInput.value) roomInput.value = String(data.room_count);
          var help = $("#lrRoomCountHelp");
          help.textContent = Number(data.room_count).toLocaleString() + "실로 신고되어 있습니다. 다르면 수정해주세요.";
          help.style.display = "block";
        })
        .catch(function () {
          // 자동 채움 실패는 직접 입력을 막지 않는다.
        });
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
      updateUrgentVisibility();
    }
    function updateUrgentVisibility() {
      var eligible = dealMode === "direct" && dealType === "매매";
      var section = $("#lrUrgentSection");
      var checkbox = $("#lrUrgentSale");
      var target = isWholeListing() ? $("#lrWholeUrgentSlot") : $("#lrUnitUrgentSlot");
      if (target && checkbox && section.parentElement !== target) target.appendChild(section);
      section.style.display = eligible ? "inline-flex" : "none";
      checkbox.disabled = !eligible;
      section.setAttribute("aria-disabled", eligible ? "false" : "true");
    }
    function updateTransactionTarget() {
      var whole = isWholeListing();
      Array.prototype.forEach.call(overlay.querySelectorAll(".lr-target"), function (button) {
        var active = button.getAttribute("data-target") === transactionTarget;
        var isUnit = button.getAttribute("data-target") === "unit";
        button.style.background = active ? (isUnit ? "#4A7A18" : "var(--brass,#b4863f)") : "#fff";
        button.style.color = active ? "#fff" : (isUnit ? "#4A7A18" : "var(--brass,#b4863f)");
      });
      $("#lrTargetHelp").textContent = whole
        ? "건물 전체의 매매·통임대·운영권양도·위탁운영 조건을 입력합니다."
        : "기존 호실 단위 매물 등록 흐름으로 진행합니다.";
      $("#lrUnitDealButtons").style.display = whole ? "none" : "flex";
      $("#lrWholeDealButtons").style.display = whole ? "flex" : "none";
       $("#lrWholeOperationSection").style.display = whole ? "block" : "none";
      $("#lrWholeBuildingSection").style.display = whole ? "block" : "none";
       $("#lrRoomCountSection").style.display = whole || $("#lrRegistrantType").value === "business" ? "block" : "none";
      updateDisclosureHelp();
      if (whole) {
        if (!isEdit && !($("#lrDescription").value || "").trim()) $("#lrDescription").value = WHOLE_DESCRIPTION_TEMPLATE;
        loadWholeListingContext();
      }
      updateRegistrantTypeFlag();
      updateDealType();
      updateUrgentVisibility();
    }
    function updateDisclosureHelp() {
      var help = $("#lrDisclosureHelp");
      if (!help) return;
      help.textContent = $("#lrDisclosureScope").value === "public"
        ? "전체공개: 건물명·매물 조건·공개로 선택한 사진이 목록과 건물 상세에 표시됩니다."
        : "제한공개: 지역·조건과 직접 작성한 매물 설명이 공개됩니다. 건물명·상세지번·사진은 공개 목록에 표시되지 않으며, 언제든 마이페이지에서 전체공개로 변경할 수 있습니다.";
    }
    function updateDealType() {
      var isBusiness = $("#lrRegistrantType").value === "business";
      var whole = isWholeListing();
      Array.prototype.forEach.call(overlay.querySelectorAll(".lr-deal"), function (button) {
        var active = button.getAttribute("data-type") === dealType;
        button.style.background = active ? "var(--brass,#b4863f)" : "#fff";
        button.style.color = active ? "#fff" : "var(--ink,#16202e)";
        button.style.borderColor = active ? "var(--brass,#b4863f)" : "var(--line,#e2ddd8)";
      });
      $("#lrPriceSale").style.display = dealType === "매매" && !isBusiness && !whole ? "block" : "none";
      $("#lrPriceJeonse").style.display = dealType === "전세" && !isBusiness && !whole ? "block" : "none";
      $("#lrPriceWolse").style.display = dealType === "월세" && !isBusiness && !whole ? "flex" : "none";
      $("#lrPriceWolseBusiness").style.display = dealType === "월세" && isBusiness && !whole ? "flex" : "none";
      $("#lrShortTerm").style.display = dealType === "단기임대" && !isBusiness && !whole ? "block" : "none";
      $("#lrShortTermBusiness").style.display = dealType === "단기임대" && isBusiness && !whole ? "flex" : "none";
       Object.keys(WHOLE_TERM_FIELDS).forEach(function (wholeDealType) {
         $(WHOLE_TERM_FIELDS[wholeDealType].section).style.display = whole && dealType === wholeDealType ? "block" : "none";
       });
       $("#lrWholeFinanceSummary").style.display = whole ? "block" : "none";
      $("#lrUnitDetailSection").style.display = whole ? "none" : "block";
      $("#lrYieldSection").style.display = !whole && dealType === "매매" ? "block" : "none";
      updateUrgentVisibility();
      updateYield();
      updateRealTakeover();
    }
    function updateYield() {
      var price = numValue($("#lrSalePrice"));
      var deposit = numValue($("#lrYieldDeposit")) || 0, rent = numValue($("#lrYieldRent"));
      $("#lrYieldResult").textContent = dealType === "매매" && price && rent
        ? "예상 수익률 약 " + ((rent * 12 / Math.max(price - deposit, 1)) * 100).toFixed(1) + "%" : "";
    }
    function updateRealTakeover() {
       var price = wholeTermValue("price");
       var loan = wholeTermValue("loan") || 0;
       var keyMoney = wholeTermValue("keyMoney") || 0;
      var output = $("#lrRealTakeover");
       if (!isWholeListing() || !price) {
        output.textContent = "실인수가 계산";
        return;
      }
       var realTakeover = price - loan + keyMoney + (price * WHOLE_ACQUISITION_COST_RATE);
      output.textContent = "예상 실인수가 약 " + Math.round(realTakeover).toLocaleString() + "만원";
    }
    function collectBuildingInfoOverrides() {
      var values = {};
      Array.prototype.forEach.call(overlay.querySelectorAll("[data-building-info-key]"), function (input) {
        var value = (input.value || "").trim();
        if (value) values[input.getAttribute("data-building-info-key")] = value;
      });
      return values;
    }
    function saveDraft() {
      if (!draftKey || !form || form.style.display === "none") return;
      try {
        var isBusiness = $("#lrRegistrantType").value === "business";
        var whole = isWholeListing();
        var draftPrice = whole ? (wholeTermValue("price") || "")
          : (dealType === "월세" && isBusiness ? $("#lrWolsePriceMin").value
          : (dealType === "단기임대" && isBusiness ? $("#lrShortPriceMin").value
            : (dealType === "전세" ? $("#lrJeonseDeposit").value
              : (dealType === "월세" ? $("#lrWolseDeposit").value : $("#lrSalePrice").value))));
        var draftPriceMax = dealType === "월세" && isBusiness ? $("#lrWolsePriceMax").value
          : (dealType === "단기임대" && isBusiness ? $("#lrShortPriceMax").value : "");
        localStorage.setItem(draftKey, JSON.stringify({
          saved_at: Date.now(),
          data: {
            deal_type: dealType,
             transaction_target: transactionTarget,
            deal_mode: dealMode,
            price_krw: draftPrice || "",
            price_krw_max: draftPriceMax || "",
             monthly_rent_krw: whole ? (wholeTermValue("rent") || "") : ($("#lrWolseRent").value || ""),
            desired_price: $("#lrDesiredPrice").value || "",
            area_sqm: isBusiness
              ? ($("#lrAreaBusiness").value || "")
              : ($("#lrArea").value === "__manual__" ? ($("#lrAreaManual").value || "") : ($("#lrArea").value || "")),
             room_count: (whole || isBusiness) ? ($("#lrRoomCount").value || "") : "",
            dong: $("#lrDong").value || "",
            ho: $("#lrHo").value || "",
            registrant_type: $("#lrRegistrantType").value || "owner",
            deposit_krw: $("#lrYieldDeposit").value || "",
            yield_rent_krw: $("#lrYieldRent").value || "",
             description: $("#lrDescription").value || "",
              succession_loan_krw: whole ? (wholeTermValue("loan") || "") : "",
              key_money_krw: whole ? (wholeTermValue("keyMoney") || "") : "",
              whole_terms: whole ? wholeTermsDraftData() : {},
             monthly_revenue_krw: $("#lrMonthlyRevenue").value || "",
             annual_revenue_krw: $("#lrAnnualRevenue").value || "",
              short_stay_ratio: $("#lrShortStayRatio").value || "",
              ota_revenue_ratio: $("#lrOtaRevenueRatio").value || "",
             operation_status: $("#lrOperationStatus").value || "",
             closed_at: $("#lrClosedAt").value || "",
             remodeling_info: $("#lrRemodelingInfo").value || "",
             is_urgent: $("#lrUrgentSale").checked,
             disclosure_scope: $("#lrDisclosureScope").value || "limited",
             building_info_overrides: collectBuildingInfoOverrides()
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
      transactionTarget = draft.transaction_target === "whole" ? "whole" : "unit";
       if (!presetDealType) {
         dealType = (transactionTarget === "whole" ? WHOLE_DEAL_TYPES : DEAL_TYPES).indexOf(draft.deal_type) >= 0 ? draft.deal_type : dealType;
       }
      dealMode = draft.deal_mode === "broker" ? "broker" : "direct";
      $("#lrSalePrice").value = draft.price_krw || "";
      $("#lrJeonseDeposit").value = draft.price_krw || "";
      $("#lrWolseDeposit").value = draft.price_krw || "";
      $("#lrWolseRent").value = draft.monthly_rent_krw || "";
      $("#lrDesiredPrice").value = draft.desired_price || "";
       $("#lrWolsePriceMin").value = draft.price_krw || "";
       $("#lrWolsePriceMax").value = draft.price_krw_max || "";
       $("#lrShortPriceMin").value = draft.price_krw || "";
       $("#lrShortPriceMax").value = draft.price_krw_max || "";
        applyWholeTermsDraftData(draft.whole_terms);
        setWholeTermValues({
          price: draft.price_krw || "",
          rent: draft.monthly_rent_krw || "",
          loan: draft.succession_loan_krw || "",
          keyMoney: draft.key_money_krw || ""
        });
       $("#lrMonthlyRevenue").value = draft.monthly_revenue_krw || "";
       $("#lrAnnualRevenue").value = draft.annual_revenue_krw || "";
        $("#lrShortStayRatio").value = draft.short_stay_ratio || "";
        $("#lrOtaRevenueRatio").value = draft.ota_revenue_ratio || "";
       $("#lrOperationStatus").value = draft.operation_status || "";
       $("#lrClosedAt").value = draft.closed_at || "";
       $("#lrRemodelingInfo").value = draft.remodeling_info || "";
       $("#lrUrgentSale").checked = !!draft.is_urgent;
       $("#lrDisclosureScope").value = draft.disclosure_scope === "public" ? "public" : "limited";
       $("#lrRoomCount").value = draft.room_count || "";
      $("#lrDong").value = draft.dong || "";
      $("#lrHo").value = draft.ho || "";
       if (!presetRegistrantType && validRegistrantType(draft.registrant_type)) {
         $("#lrRegistrantType").value = draft.registrant_type;
       }
      $("#lrYieldDeposit").value = draft.deposit_krw || "";
      $("#lrYieldRent").value = draft.yield_rent_krw || "";
      $("#lrDescription").value = draft.description || "";
      var areaSelect = $("#lrArea"), areaManual = $("#lrAreaManual");
      if (draft.area_sqm) {
         $("#lrAreaBusiness").value = draft.area_sqm;
        var hasArea = Array.prototype.some.call(areaSelect.options, function (option) {
          return option.value === String(draft.area_sqm);
        });
        areaSelect.value = hasArea ? String(draft.area_sqm) : "__manual__";
        areaManual.value = hasArea ? "" : draft.area_sqm;
        areaManual.style.display = hasArea ? "none" : "block";
      }
      updateMode();
       updateTransactionTarget();
      updateDealType();
       updateRegistrantTypeFlag();
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
        var draftInfo = savedDraft.data;
        var draftSummary = draftRegistrantLabel(draftInfo.registrant_type) + ", " + draftDealLabel(draftInfo.deal_type);
        if (confirm("이 건물에 이전에 작성 중이던 매물 정보(" + draftSummary + ")가 있습니다.\n확인을 누르면 불러오고, 취소를 누르면 새로 작성합니다.")) {
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
    Array.prototype.forEach.call(overlay.querySelectorAll(".lr-target"), function (button) {
      button.addEventListener("click", function () {
        var nextTarget = button.getAttribute("data-target");
        if (nextTarget === transactionTarget) return;
        transactionTarget = nextTarget;
        dealType = transactionTarget === "whole"
          ? (WHOLE_DEAL_TYPES.indexOf(dealType) >= 0 ? dealType : "매매")
          : (DEAL_TYPES.indexOf(dealType) >= 0 ? dealType : "매매");
        updateTransactionTarget();
        saveDraft();
        if ($("#lrRegistrantType").value === "business" && transactionTarget === "whole") {
          checkBusinessVerification();
        } else {
          showListingForm();
        }
      });
    });
    Array.prototype.forEach.call(overlay.querySelectorAll(".lr-deal"), function (button) {
      button.addEventListener("click", function () {
        if ((transactionTarget === "whole" ? WHOLE_DEAL_TYPES : DEAL_TYPES).indexOf(button.getAttribute("data-type")) < 0) return;
        dealType = button.getAttribute("data-type"); updateDealType(); saveDraft();
      });
    });
    function updateRegistrantTypeFlag() {
      var registrantType = $("#lrRegistrantType").value || "owner";
      var isBusiness = registrantType === "business";
      var whole = isWholeListing();
      form.dataset.registrantType = registrantType;
      $("#lrAreaOwnerWrap").style.display = !whole && !isBusiness ? "block" : "none";
      $("#lrAreaBusinessWrap").style.display = !whole && isBusiness ? "block" : "none";
       $("#lrRoomCountSection").style.display = whole || isBusiness ? "block" : "none";
      if (!whole && isBusiness) loadLodgingSummary();
      else if (!whole) loadAreaTypes();
      updateDealType();
    }
    $("#lrRegistrantType").addEventListener("change", function () {
      updateRegistrantTypeFlag();
      saveDraft();
      if (this.value === "business" && transactionTarget === "whole") {
        checkBusinessVerification();
      } else {
        showListingForm();
      }
    });
    function updateClosedAt() {
      $("#lrClosedAt").style.display = $("#lrOperationStatus").value === "폐업" ? "block" : "none";
      if ($("#lrOperationStatus").value !== "폐업") $("#lrClosedAt").value = "";
    }
    $("#lrOperationStatus").addEventListener("change", function () { updateClosedAt(); saveDraft(); });
    $("#lrDisclosureScope").addEventListener("change", function () { updateDisclosureHelp(); saveDraft(); });
    ["#lrSalePrice", "#lrJeonseDeposit", "#lrWolseDeposit", "#lrWolseRent",
      "#lrWolsePriceMin", "#lrWolsePriceMax", "#lrShortPriceMin", "#lrShortPriceMax",
      "#lrDesiredPrice", "#lrArea", "#lrAreaManual", "#lrAreaBusiness", "#lrRoomCount",
      "#lrDong", "#lrHo", "#lrRegistrantType", "#lrYieldDeposit", "#lrYieldRent",
      "#lrDescription", "#lrWholeSalePrice", "#lrSaleKeyMoney", "#lrSaleLoan",
      "#lrWholeLeaseDeposit", "#lrWholeLeaseRent", "#lrLeaseKeyMoney", "#lrLeaseLoan",
      "#lrWholeTransferPrice", "#lrTransferKeyMoney", "#lrTransferLoan",
      "#lrWholeConsignDeposit", "#lrConsignKeyMoney", "#lrConsignLoan",
      "#lrMonthlyRevenue", "#lrAnnualRevenue",
      "#lrShortStayRatio", "#lrOtaRevenueRatio",
      "#lrClosedAt", "#lrRemodelingInfo", "#lrUrgentSale", "#lrDisclosureScope"].forEach(function (selector) {
      $(selector).addEventListener("input", updateYield);
      $(selector).addEventListener("input", updateRealTakeover);
      $(selector).addEventListener("input", saveDraft);
      $(selector).addEventListener("change", saveDraft);
    });
    // 모바일 키보드나 상위 폼 이벤트와 무관하게 Enter는 항상 설명의 다음 줄을 만든다.
    $("#lrDescription").addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      var start = this.selectionStart;
      var end = this.selectionEnd;
      var nextValue = this.value.slice(0, start) + "\n" + this.value.slice(end);
      if (this.maxLength > 0 && nextValue.length > this.maxLength) return;
      this.value = nextValue;
      this.selectionStart = this.selectionEnd = start + 1;
      this.dispatchEvent(new Event("input", {bubbles: true}));
    });
    if (isEdit) $("#lrModeSection").style.display = "none";
    updateMode();
    updateClosedAt();
    updateTransactionTarget();
    if (isEdit && $("#lrRegistrantType").value === "business"
        && transactionTarget === "whole") checkBusinessVerification();
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
      businessGate.style.display = "none";
      $("#lrGateLoading").style.display = "none";
      $("#lrGateFields").style.display = "block";
      $("#lrGatePhone").focus();
    }
    function showListingForm() {
      $("#lrAuthLoading").style.display = "none";
      phoneGate.style.display = "none";
      businessGate.style.display = "none";
      form.style.display = "block";
      if (draftRestored) {
        setMessage("이전에 작성 중이던 내용을 불러왔습니다.");
        draftRestored = false;
      }
    }
    function setBusinessVerifyMessage(text, ok) {
      var verifyMessage = $("#lrBusinessVerifyMessage");
      verifyMessage.textContent = text || "";
      verifyMessage.style.color = ok ? "#28733f" : "#b42318";
      verifyMessage.style.display = text ? "block" : "none";
    }
    function showBusinessGate() {
      $("#lrAuthLoading").style.display = "none";
      form.style.display = "none";
      phoneGate.style.display = "none";
      businessGate.style.display = "block";
    }
    function checkBusinessVerification() {
      if ($("#lrRegistrantType").value !== "business"
          || transactionTarget !== "whole") {
        showListingForm();
        return;
      }
      if (!buildingId) {
        showBusinessGate();
        $("#lrBusinessVerifyLoading").style.display = "none";
        $("#lrBusinessVerifyFields").style.display = "none";
        setBusinessVerifyMessage("건물을 선택한 뒤 사업주 매물을 등록할 수 있습니다.");
        return;
      }
      $("#lrAuthLoading").style.display = "block";
      form.style.display = "none";
      phoneGate.style.display = "none";
      businessGate.style.display = "none";
      $("#lrBusinessVerifyFields").style.display = "none";
      setBusinessVerifyMessage("");
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/business-verification", {
        credentials: "same-origin"
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) { return {ok: r.ok, data: data}; });
      }).then(function (result) {
        if (!result.ok || !result.data.ok) throw new Error(result.data.message || "사업주 인증 상태를 확인하지 못했습니다.");
        if (result.data.verified || !result.data.matched) {
          showListingForm();
          return;
        }
        showBusinessGate();
        $("#lrBusinessVerifyLoading").style.display = "none";
        $("#lrBusinessVerifyFields").style.display = result.data.permit_available ? "block" : "none";
        $("#lrBusinessVerifyHelp").textContent = (result.data.business_name
          ? result.data.business_name + "의 " : "") + "영업신고번호를 입력해주세요. 하이픈과 공백은 입력하지 않아도 됩니다.";
        if (result.data.permit_available) $("#lrBusinessPermitNumber").focus();
        else setBusinessVerifyMessage("이 건물의 영업신고번호를 확인할 수 없습니다. 관리자에게 문의해주세요.");
      }).catch(function (error) {
        showBusinessGate();
        $("#lrBusinessVerifyLoading").style.display = "none";
        $("#lrBusinessVerifyFields").style.display = "none";
        setBusinessVerifyMessage(error.message || "인증 상태를 확인하지 못했습니다. 잠시 후 다시 시도해주세요.");
      });
    }
    $("#lrBusinessVerifySubmit").addEventListener("click", function () {
      var button = this;
      var permitNumber = ($("#lrBusinessPermitNumber").value || "").replace(/\D/g, "");
      if (!permitNumber) {
        setBusinessVerifyMessage("영업신고번호를 입력해주세요.");
        return;
      }
      setBusinessVerifyMessage("");
      button.disabled = true;
      button.textContent = "확인 중…";
      fetch("/api/building/" + encodeURIComponent(buildingId) + "/business-verification", {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({permit_number: permitNumber})
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) { return {ok: r.ok, data: data}; });
      }).then(function (result) {
        if (!result.ok || !result.data.ok) throw new Error(result.data.message || "영업신고번호 확인에 실패했습니다.");
        showListingForm();
      }).catch(function (error) {
        button.disabled = false;
        button.textContent = "신고번호 확인";
        setBusinessVerifyMessage(error.message || "네트워크 오류가 발생했습니다.");
      });
    });
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
          if ($("#lrRegistrantType").value === "business"
              && transactionTarget === "whole") checkBusinessVerification();
          else showListingForm();
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
          if (user && user.phone) {
            var savedDigits = String(user.phone).replace(/\D/g, "").slice(0, 11);
            $("#lrGatePhone").value = savedDigits.length > 7
              ? savedDigits.slice(0, 3) + "-" + savedDigits.slice(3, 7) + "-" + savedDigits.slice(7)
              : (savedDigits.length > 3 ? savedDigits.slice(0, 3) + "-" + savedDigits.slice(3) : savedDigits);
          }
          if (user && user.phone_verified && user.phone) {
            restoreDraftForUser(draftUser);
            if ($("#lrRegistrantType").value === "business"
                && transactionTarget === "whole") checkBusinessVerification();
            else showListingForm();
            return;
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
    function photoPublicFor(items) {
      var values = {};
      (items || photoItems).forEach(function (item) {
        if (item.kind === "existing" && item.photo && item.photo.id != null) {
          values[String(item.photo.id)] = item.isPublic !== false;
        }
      });
      return values;
    }

    function savePhotoOrder(listingId, items) {
      var photoIds = photoIdsFor(items || photoItems);
      if (!photoIds.length || photoIds.some(function (id) { return id == null; })) return Promise.resolve();
      return fetch("/api/listing-requests/" + listingId + "/photos/order", {
        method: "PUT", credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({photo_ids: photoIds, photo_public: photoPublicFor(items || photoItems)})
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
        card.style.cssText = "position:relative;width:82px;height:123px;";
        card.innerHTML =
          '<img src="' + esc(photoUrl) + '" alt="' + photoAlt + '" style="width:82px;height:76px;object-fit:cover;border-radius:7px;border:1px solid #eee;">' +
          (index === 0
            ? '<span style="position:absolute;left:3px;top:3px;padding:2px 4px;border-radius:4px;background:var(--brass,#b4863f);color:#fff;font-size:9px;font-weight:800;">대표</span>'
            : '<button type="button" class="lr-photo-cover" aria-label="대표사진으로 지정" style="position:absolute;left:3px;top:3px;border:0;border-radius:4px;padding:3px 4px;background:rgba(22,32,46,.78);color:#fff;font-size:9px;font-weight:700;cursor:pointer;">대표로</button>') +
          '<button type="button" class="lr-photo-remove" aria-label="사진 삭제" style="position:absolute;right:-4px;top:-5px;width:21px;height:21px;border:0;border-radius:50%;background:#333;color:#fff;cursor:pointer;line-height:18px;">×</button>' +
          '<label style="display:block;margin-top:3px;font-size:10px;color:var(--ink-soft);white-space:nowrap;"><input type="checkbox" class="lr-photo-public"' + (item.isPublic !== false ? " checked" : "") + '> 사진 공개</label>' +
          '<div style="display:flex;gap:3px;margin-top:3px;">' +
            '<button type="button" class="lr-photo-prev" aria-label="사진 앞으로 이동" ' + (index === 0 ? "disabled" : "") + ' style="flex:1;border:1px solid var(--line,#ddd);border-radius:4px;background:#fff;padding:2px 0;font-size:11px;cursor:' + (index === 0 ? "default" : "pointer") + ';">←</button>' +
            '<button type="button" class="lr-photo-next" aria-label="사진 뒤로 이동" ' + (index === photoItems.length - 1 ? "disabled" : "") + ' style="flex:1;border:1px solid var(--line,#ddd);border-radius:4px;background:#fff;padding:2px 0;font-size:11px;cursor:' + (index === photoItems.length - 1 ? "default" : "pointer") + ';">→</button>' +
          '</div>';
        var cover = card.querySelector(".lr-photo-cover");
        if (cover) cover.addEventListener("click", function () { movePhoto(index, 0); });
        card.querySelector(".lr-photo-remove").addEventListener("click", function () {
          removePhoto(index);
        });
        card.querySelector(".lr-photo-public").addEventListener("change", function () {
          item.isPublic = this.checked;
          if (item.kind === "existing") persistPhotoOrder();
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
        else if (file.size > MAX_PHOTO_BYTES) errors.push(file.name + ": 10MB 이하만 가능합니다.");
        else if (photoItems.length >= MAX_PHOTOS) errors.push("사진은 최대 " + MAX_PHOTOS + "장까지 첨부할 수 있습니다.");
        else photoItems.push({
          kind: "pending", file: file, previewUrl: URL.createObjectURL(file),
          isPublic: !isWholeListing() || $("#lrDisclosureScope").value === "public"
        });
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
      var isBusiness = $("#lrRegistrantType").value === "business";
      var isWhole = isWholeListing();
      var price = null, priceMax = null, rent = null;
      if (isWhole) {
        price = wholeTermValue("price");
        rent = wholeTermValue("rent");
      } else if (dealType === "매매") {
        price = numValue($("#lrSalePrice"));
      }
      if (dealType === "전세") {
        price = numValue($("#lrJeonseDeposit"));
      }
      if (dealType === "월세") {
        if (isBusiness) {
          price = numValue($("#lrWolsePriceMin"));
          priceMax = numValue($("#lrWolsePriceMax"));
        } else {
          price = numValue($("#lrWolseDeposit"));
          rent = numValue($("#lrWolseRent"));
        }
      }
      if (dealType === "단기임대" && isBusiness) {
        price = numValue($("#lrShortPriceMin"));
        priceMax = numValue($("#lrShortPriceMax"));
      }
      var body = {
        deal_type: dealType,
        transaction_target: transactionTarget,
        desired_price: !isWhole && dealType === "단기임대"
          ? (($("#lrDesiredPrice").value || "").trim() || priceText(dealType, price, rent, priceMax))
          : priceText(dealType, price, rent, priceMax),
        price_krw: price, price_krw_max: priceMax, monthly_rent_krw: rent,
        area_sqm: isWhole ? "" : (isBusiness
          ? ($("#lrAreaBusiness").value || "").trim()
          : ($("#lrArea").value === "__manual__" ? ($("#lrAreaManual").value || "").trim() : ($("#lrArea").value || "").trim())),
        room_count: (isWhole || isBusiness) ? numValue($("#lrRoomCount")) : null,
        dong: isWhole ? "" : ($("#lrDong").value || "").trim(), ho: isWhole ? "" : ($("#lrHo").value || "").trim(),
        registrant_type: $("#lrRegistrantType").value, description: ($("#lrDescription").value || "").trim(),
        deposit_krw: !isWhole && dealType === "매매" ? numValue($("#lrYieldDeposit")) : null,
        yield_rent_krw: !isWhole && dealType === "매매" ? numValue($("#lrYieldRent")) : null,
        succession_loan_krw: isWhole ? wholeTermValue("loan") : null,
        key_money_krw: isWhole ? wholeTermValue("keyMoney") : null,
        monthly_revenue_krw: isWhole ? numValue($("#lrMonthlyRevenue")) : null,
        annual_revenue_krw: isWhole ? numValue($("#lrAnnualRevenue")) : null,
        short_stay_ratio: isWhole ? ($("#lrShortStayRatio").value || "").trim() : "",
        ota_revenue_ratio: isWhole ? ($("#lrOtaRevenueRatio").value || "").trim() : "",
        operation_status: isWhole ? $("#lrOperationStatus").value : "",
        closed_at: isWhole ? $("#lrClosedAt").value : "",
        remodeling_info: isWhole ? ($("#lrRemodelingInfo").value || "").trim() : "",
        is_urgent: dealMode === "direct" && dealType === "매매" && $("#lrUrgentSale").checked,
        disclosure_scope: isWhole ? $("#lrDisclosureScope").value : "",
        building_info_overrides: isWhole ? collectBuildingInfoOverrides() : {}
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
            return uploadPhoto(listingId, item.file, item.isPublic !== false).then(function (data) {
              if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
              item.kind = "existing";
              item.photo = {id: data.id, url: data.src, is_public: data.is_public};
              item.isPublic = data.is_public !== false;
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

  function openApproximateLocationMap(lat, lng, returnFocus) {
    var old = document.getElementById("ls-listing-location-map");
    if (old) {
      var oldClose = old.querySelector("[data-approx-map-close]");
      if (oldClose) oldClose.click();
      else old.remove();
    }

    var mapOverlay = document.createElement("div");
    mapOverlay.id = "ls-listing-location-map";
    mapOverlay.style.cssText = "position:fixed;inset:0;z-index:4700;background:rgba(22,32,46,.58);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";
    mapOverlay.innerHTML =
      '<div role="dialog" aria-modal="true" aria-labelledby="lsApproxMapTitle" tabindex="-1" style="width:min(100%,620px);background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,.3);">' +
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:15px 16px;border-bottom:1px solid var(--line,#e2ddd8);">' +
          '<div><div id="lsApproxMapTitle" style="font-size:17px;font-weight:800;color:var(--ink,#16202e);">대략적인 위치</div>' +
          '<div style="margin-top:4px;color:var(--ink-soft,#6b7684);font-size:12px;line-height:1.5;">파란 원은 중심 기준 반경 500m이며 정확한 건물 위치가 아닙니다.</div></div>' +
          '<button type="button" data-approx-map-close aria-label="지도 닫기" style="flex:0 0 auto;width:34px;height:34px;border:0;border-radius:50%;background:#6B7280;color:#fff;font-size:22px;line-height:1;cursor:pointer;">×</button>' +
        '</div>' +
        '<div data-approx-map-canvas style="height:min(62vh,480px);min-height:320px;background:#eef3f8;"></div>' +
        '<div style="padding:10px 16px;color:#275B88;background:#F3F8FD;font-size:11.5px;font-weight:700;text-align:center;">정확한 주소와 위치 핀은 제한공개 정책에 따라 표시하지 않습니다.</div>' +
      '</div>';
    document.body.appendChild(mapOverlay);

    var dialog = mapOverlay.querySelector('[role="dialog"]');
    var close = function () {
      document.removeEventListener("keydown", onKeydown);
      mapOverlay.remove();
      if (returnFocus && typeof returnFocus.focus === "function") returnFocus.focus();
    };
    var onKeydown = function (event) {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        var focusables = Array.from(
          dialog.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
        );
        if (!focusables.length) {
          event.preventDefault();
          dialog.focus();
          return;
        }
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeydown);
    mapOverlay.addEventListener("click", function (event) {
      if (event.target === mapOverlay) close();
    });
    mapOverlay.querySelector("[data-approx-map-close]").addEventListener("click", close);

    var canvas = mapOverlay.querySelector("[data-approx-map-canvas]");
    var renderMap = function () {
      if (!mapOverlay.isConnected) return;
      try {
        var center = new kakao.maps.LatLng(lat, lng);
        var map = new kakao.maps.Map(canvas, {center:center, level:4});
        new kakao.maps.Circle({
          center:center,
          radius:500,
          strokeWeight:3,
          strokeColor:"#378ADD",
          strokeOpacity:0.95,
          strokeStyle:"solid",
          fillColor:"#378ADD",
          fillOpacity:0.18
        }).setMap(map);
      } catch (error) {
        canvas.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#6b7684;font-size:13px;">지도를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>';
      }
    };
    if (window.kakao && kakao.maps && typeof kakao.maps.load === "function") {
      kakao.maps.load(renderMap);
    } else {
      canvas.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#6b7684;font-size:13px;">지도를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>';
    }
    requestAnimationFrame(function () { dialog.focus(); });
  }
  window.openApproximateLocationMap = openApproximateLocationMap;

  // 직거래 목록과 건물 상세 화면에서 공용으로 사용하는 읽기 전용 매물 상세 팝업.
  // 등록/수정 모달(openListingRequestModal)과 분리해, 어느 화면에서도 같은 상세
  // 정보·사진·액션을 제공한다.
  window.openListingDetailModal = function (listing, options) {
    options = options || {};
    if (!listing) return;

    var old = document.getElementById("ls-listing-modal");
    if (old) old.remove();

    var previousFocus = document.activeElement;
    var photos = (Array.isArray(listing.photos) ? listing.photos : []).map(function (photo) {
      return typeof photo === "string" ? photo : (photo && photo.url);
    }).filter(Boolean);
    if (!photos.length && listing.photo_url) photos = [listing.photo_url];

    var isWhole = listing.is_whole_listing || listing.transaction_target === "whole";
    var formatNumber = function (value) {
      return value != null && value !== "" ? Number(value).toLocaleString("ko-KR") : "-";
    };
    var priceText;
    if (isWhole) {
      var deposit = listing.price_krw != null ? "보증금 " + formatNumber(listing.price_krw) + "만원" : "조건 협의";
      priceText = listing.deal_type === "매매"
        ? (listing.price_krw != null ? "매매가 " + formatNumber(listing.price_krw) + "만원" : "매매 조건 협의")
        : (listing.monthly_rent_krw != null ? deposit + " / 월 " + formatNumber(listing.monthly_rent_krw) + "만원" : deposit);
    } else if (listing.is_business_listing) {
      priceText = listing.room_price_min != null && listing.room_price_max != null
        ? "장기임대 가능 · " + formatNumber(listing.room_price_min) + "~" + formatNumber(listing.room_price_max) + "만원/월"
        : "현재 문의 가능 여부는 채팅으로 확인해주세요";
    } else if (listing.deal_type === "월세" && listing.price_krw_max == null) {
      priceText = "보" + formatNumber(listing.price_krw) + "/" + formatNumber(listing.monthly_rent_krw) + "만";
    } else {
      priceText = listing.price_krw != null
        ? formatNumber(listing.price_krw) + (listing.price_krw_max != null ? " ~ " + formatNumber(listing.price_krw_max) : "") + "만원"
        : "-";
    }

    var lodging = window.LodgingTypes.badge(listing.lodging_type, listing.lodging_subtype);
    var lodgingColor = window.LodgingTypes.color(listing.lodging_type);
    var dealColors = {"매매":"#C85A36","전세":"#378ADD","월세":"#639922","단기임대":"#8B6BB1","통임대":"#5A7FA6","운영권양도":"#8B6BB1","위탁운영":"#557A5B"};
    var areaText = !isWhole && listing.area_sqm ? Number(listing.area_sqm).toFixed(1) + "㎡" : "";
    var roomText = listing.room_count != null && Number(listing.room_count) > 0
      ? (isWhole ? "총 " : "") + formatNumber(listing.room_count) + "실" : "";
    var yieldText = listing.yield_rate != null ? "수익률 " + Number(listing.yield_rate).toFixed(1) + "%" : "";
    var meta = [listing.listing_number, listing.listing_date ? "최근 수정 " + listing.listing_date : ""].filter(Boolean).join(" · ");
    var detail = [areaText, roomText, yieldText].filter(Boolean).join(" · ");
    var isLimitedLocation = isWhole && listing.location_precision === "approximate";
    var locationLat = Number(isLimitedLocation ? listing.approx_lat : listing.lat);
    var locationLng = Number(isLimitedLocation ? listing.approx_lng : listing.lng);
    var hasMapLocation = isWhole && Number.isFinite(locationLat) && Number.isFinite(locationLng);
    var mapLocationLabel = isLimitedLocation
      ? (listing.approx_location_label || "대략적인 위치")
      : "정확한 위치";
    var mapLocationAction = hasMapLocation
      ? '<div style="margin:10px 0 0;"><button type="button" data-listing-detail-map style="border:1px solid ' + (isLimitedLocation ? "#378ADD" : "var(--brass,#B4863F)") + ';border-radius:7px;background:' + (isLimitedLocation ? "#F3F8FD" : "#fffaf2") + ';color:' + (isLimitedLocation ? "#275B88" : "var(--brass-dark,#7D4A00)") + ';padding:7px 9px;font:700 12px inherit;cursor:pointer;">' + (isLimitedLocation ? "◎ 반경 500m 위치 보기" : "📍 지도에서 " + esc(mapLocationLabel) + " 보기") + '</button>' +
        (isLimitedLocation ? '<div style="margin-top:5px;color:var(--ink-soft);font-size:11px;line-height:1.45;">제한공개 매물은 정확한 핀 대신 대략적인 중심의 반경 500m 파란 원만 표시합니다.</div>' : "") +
        '</div>'
      : "";
    var description = listing.description ? esc(listing.description) : "";
    var rawDescription = String(listing.description || "").trim();
    var descriptionIsLong = rawDescription.length > 180 || rawDescription.split(/\r?\n/).length > 5;
    var descriptionMarkup = description
      ? '<div style="margin:12px 0;padding:11px 12px;border:1px solid #D7E4F2;border-radius:8px;background:#F7FAFD;color:#34475A;font-size:13px;line-height:1.65;">' +
          '<div style="margin-bottom:5px;color:#275B88;font-size:11px;font-weight:800;">매물 설명</div>' +
          '<div data-listing-description-text style="white-space:pre-wrap;overflow-wrap:anywhere;' +
            (descriptionIsLong ? 'display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:6;overflow:hidden;' : '') + '">' + description + '</div>' +
          (descriptionIsLong ? '<button type="button" data-listing-description-toggle aria-expanded="false" style="display:block;margin:7px 0 0 auto;padding:2px 0;border:0;background:transparent;color:#275B88;font:700 11.5px inherit;cursor:pointer;">설명 전체보기</button>' : '') +
        '</div>'
      : "";
    var detailGroup = function (title, rows) {
      rows = rows.filter(function (row) { return row && row[1] !== null && row[1] !== undefined && row[1] !== ""; });
      if (!rows.length) return "";
      return '<section style="padding:11px 12px;border:1px solid var(--line,#e2ddd8);border-radius:9px;background:#fcfbf9;">' +
        '<div style="margin-bottom:7px;color:var(--ink-soft,#6b7684);font-size:11px;font-weight:800;">' + esc(title) + '</div>' +
        rows.map(function (row) {
          return '<div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0;font-size:12.5px;line-height:1.5;">' +
            '<span style="color:var(--ink-soft,#6b7684);">' + esc(row[0]) + '</span><b style="color:var(--ink,#16202e);text-align:right;overflow-wrap:anywhere;">' + esc(row[1]) + '</b></div>';
        }).join("") + '</section>';
    };
    var formatMoney = function (value) { return formatNumber(value) + "만원"; };
    var financeVisible = !!listing.financial_details_visible;
    var acquisitionValue = financeVisible && listing.price_krw != null
      ? Number(listing.price_krw) - Number(listing.succession_loan_krw || 0) +
        Number(listing.key_money_krw || 0) + Number(listing.price_krw) * 0.061
      : null;
    var wholeDetailsMarkup = isWhole
      ? '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0;" data-listing-detail-groups>' +
          detailGroup("거래 조건", [
            [listing.deal_type === "매매" ? "매매가" : "보증금·양도금", listing.price_krw != null ? formatMoney(listing.price_krw) : "조건 협의"],
            ["월세", listing.monthly_rent_krw != null ? formatMoney(listing.monthly_rent_krw) : ""]
          ]) +
          detailGroup("금융 · 인수", financeVisible ? [
            ["실인수가", acquisitionValue != null ? formatMoney(Math.round(acquisitionValue)) : "-"],
            ["승계융자", listing.succession_loan_krw != null ? formatMoney(listing.succession_loan_krw) : "없음"],
            ["권리금", listing.key_money_krw != null ? formatMoney(listing.key_money_krw) : "없음"]
          ] : [["상세 금융정보", "로그인 후 확인"]]) +
          detailGroup("운영 · 매출", [
            ["월평균매출", listing.has_monthly_revenue ? (financeVisible ? formatMoney(listing.monthly_revenue_krw) : "로그인 후 확인") : ""],
            ["연매출", listing.annual_revenue_krw != null ? (financeVisible ? formatMoney(listing.annual_revenue_krw) : "로그인 후 확인") : ""],
            ["대실 비율", listing.short_stay_ratio != null ? formatNumber(listing.short_stay_ratio) + "%" : ""],
            ["OTA 매출 비중", listing.ota_revenue_ratio != null ? formatNumber(listing.ota_revenue_ratio) + "%" : ""],
            ["운영상태", listing.operation_status || ""],
            ["폐업일", listing.closed_at || ""]
          ]) +
          detailGroup("시설 · 건물", [
            ["객실", listing.room_count != null ? formatNumber(listing.room_count) + "실" : ""],
            ["주차", listing.parking_count != null ? formatNumber(listing.parking_count) + "대" : ""],
            ["대지면적", listing.land_area_pyeong != null ? Number(listing.land_area_pyeong).toFixed(1) + "평" : ""],
            ["연면적", listing.gross_area_pyeong != null ? Number(listing.gross_area_pyeong).toFixed(1) + "평" : ""]
          ]) +
          detailGroup("설명 · 공개 상태", [
            ["리모델링", listing.remodeling_info || ""],
            ["공개범위", listing.is_limited_listing ? "제한공개" : "전체공개"],
            ["영업신고 인증", listing.permit_number_masked || ""]
          ]) +
        '</div>' +
        (listing.is_limited_listing ? '<div style="margin:0 0 12px;padding:9px 11px;border-radius:8px;background:#F3F8FD;color:#275B88;font-size:11.5px;line-height:1.55;">건물명·정확한 주소·사진은 보호됩니다. 상세 조건은 채팅으로 확인해 주세요.</div>' : "")
      : "";
    var viewerCountMarkup = isWhole
      ? '<div data-listing-viewer-count="' + esc(listing.id) + '" style="margin:3px 0 0;color:#356212;font-size:11px;font-weight:700;">최근 열람 ' + formatNumber(listing.viewer_count || 0) + '명</div>'
      : "";
    var photoIndex = 0;
    var icons = window.LivingstayListingIcons;
    if (!icons) return;

    var overlay = document.createElement("div");
    overlay.id = "ls-listing-modal";
    overlay.style.cssText = "position:fixed;inset:0;z-index:4500;background:rgba(22,32,46,.5);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";
    var gallery = photos[0]
      ? '<div style="position:relative;background:#f6f4f0;">' +
        '<img id="lsListingDetailImage" src="' + esc(photos[0]) + '" alt="매물 사진 1" style="width:100%;height:220px;object-fit:cover;display:block;" onerror="this.style.display=\'none\';">' +
        (photos.length > 1
          ? '<button type="button" data-listing-photo-prev aria-label="이전 사진" style="position:absolute;left:10px;top:calc(50% - 17px);width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.5);color:#fff;font-size:21px;cursor:pointer;">‹</button>' +
            '<button type="button" data-listing-photo-next aria-label="다음 사진" style="position:absolute;right:10px;top:calc(50% - 17px);width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.5);color:#fff;font-size:21px;cursor:pointer;">›</button>' +
            '<span id="lsListingDetailCount" style="position:absolute;right:12px;bottom:10px;padding:4px 8px;border-radius:999px;background:rgba(0,0,0,.62);color:#fff;font-size:11px;font-weight:700;">1 / ' + photos.length + '</span>'
          : "") +
        '</div>'
      : '<div style="height:220px;background:var(--brass-tint,#FFF5E0);display:flex;align-items:center;justify-content:center;font-size:56px;">🏠</div>';
    var urgentBadge = listing.urgent_tier === "urgent"
      ? '<span title="' + (listing.is_urgent ? "판매자가 급매로 등록한 매물" : "최신 실거래가보다 낮은 매물") + '" style="display:inline-block;margin-left:5px;padding:2px 7px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;font-weight:800;">급매</span>'
      : "";

    overlay.innerHTML =
      '<div role="dialog" aria-modal="true" aria-label="직거래 매물 상세" tabindex="-1" style="width:min(100%,420px);max-height:88vh;overflow:auto;background:#fff;border-radius:16px;box-shadow:0 10px 36px rgba(0,0,0,.25);">' +
        '<div style="position:relative;">' + gallery +
          '<button type="button" data-listing-detail-close aria-label="닫기" style="position:absolute;top:10px;right:10px;width:34px;height:34px;border:0;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:22px;cursor:pointer;">×</button>' +
        '</div>' +
        '<div style="padding:16px 18px 18px;">' +
          (meta ? '<div style="font-size:11px;color:var(--ink-soft);margin:-4px 0 8px;">' + esc(meta) + '</div>' : "") +
          '<div style="font-size:12px;font-weight:800;color:var(--ink);margin-bottom:7px;">' +
            '<span style="display:inline-block;margin-right:5px;padding:2px 6px;border-radius:4px;background:' + lodgingColor + ';color:#fff;font-size:10px;">' + esc(lodging) + '</span>' +
            (isWhole ? '<span style="display:inline-block;margin-right:5px;padding:2px 6px;border-radius:4px;background:var(--brass,#B4863F);color:#fff;font-size:10px;">건물전체</span>' : "") +
            '<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:' + (dealColors[listing.deal_type] || "#7B8794") + ';color:#fff;font-size:10px;">' + esc(listing.deal_type || "-") + '</span>' +
             urgentBadge +
            (areaText ? ' · ' + esc(areaText) : "") +
          '</div>' +
          '<div style="font-size:20px;font-weight:800;color:var(--ink);margin-bottom:7px;">' + esc(priceText) + '</div>' +
          (detail ? '<div style="font-size:12px;color:var(--ink-soft);font-weight:700;margin-bottom:7px;">' + esc(detail) + '</div>' : "") +
          wholeDetailsMarkup +
          viewerCountMarkup +
          mapLocationAction +
          descriptionMarkup +
          '<div style="display:flex;justify-content:flex-end;gap:7px;">' +
            '<button type="button" data-listing-detail-like class="listing-like-btn' + (listing.liked ? " is-liked" : "") + '" title="찜">' + icons.heart(!!listing.liked) + '<span class="like-cnt">' + (listing.like_count || 0) + '</span></button>' +
            '<button type="button" data-listing-detail-chat class="listing-chat-btn" title="채팅">' + icons.chat() + '</button>' +
            '<button type="button" data-listing-detail-share class="listing-share-btn" title="매물 공유">' + icons.share() + '</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var dialog = overlay.querySelector('[role="dialog"]');
    var close = function () {
      document.removeEventListener("keydown", onKeydown);
      overlay.remove();
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    };
    var onKeydown = function (event) {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeydown);
    overlay.addEventListener("click", function (event) { if (event.target === overlay) close(); });
    overlay.querySelector("[data-listing-detail-close]").addEventListener("click", close);
    overlay.querySelector("[data-listing-detail-chat]").addEventListener("click", function () {
      close();
      if (typeof options.onChat === "function") options.onChat(listing);
    });
    overlay.querySelector("[data-listing-detail-share]").addEventListener("click", function () {
      if (typeof options.onShare === "function") options.onShare(listing);
    });
    var mapButton = overlay.querySelector("[data-listing-detail-map]");
    if (mapButton) {
      mapButton.addEventListener("click", function () {
        if (isLimitedLocation) {
          openApproximateLocationMap(locationLat, locationLng, mapButton);
          return;
        }
        var label = isLimitedLocation ? "대략적인 위치" : (listing.building_name || "매물 위치");
        var mapUrl = "https://map.kakao.com/link/map/" + encodeURIComponent(label) + "," +
          encodeURIComponent(locationLat) + "," + encodeURIComponent(locationLng);
        window.open(mapUrl, "_blank", "noopener,noreferrer");
      });
    }
    var descriptionToggle = overlay.querySelector("[data-listing-description-toggle]");
    if (descriptionToggle) {
      descriptionToggle.addEventListener("click", function () {
        var text = overlay.querySelector("[data-listing-description-text]");
        var expanding = descriptionToggle.getAttribute("aria-expanded") !== "true";
        descriptionToggle.setAttribute("aria-expanded", expanding ? "true" : "false");
        if (text) {
          text.style.display = expanding ? "block" : "-webkit-box";
          text.style.webkitLineClamp = expanding ? "unset" : "6";
          text.style.overflow = expanding ? "visible" : "hidden";
        }
        descriptionToggle.textContent = expanding ? "설명 접기" : "설명 전체보기";
      });
    }
    overlay.querySelector("[data-listing-detail-like]").addEventListener("click", function (event) {
      var button = event.currentTarget;
      fetch("/api/listing-requests/" + encodeURIComponent(listing.id) + "/like", {method:"POST", credentials:"same-origin"})
        .then(function (res) { return res.json().then(function (data) { return {ok:res.ok, data:data}; }); })
        .then(function (result) {
          if (!result.ok || !result.data.ok) return;
          listing.liked = !!result.data.liked;
          listing.like_count = result.data.like_count;
          button.classList.toggle("is-liked", listing.liked);
          button.innerHTML = icons.heart(listing.liked) + '<span class="like-cnt">' + listing.like_count + '</span>';
          if (typeof options.onLike === "function") options.onLike(listing);
        }).catch(function () {});
    });
    if (photos.length > 1) {
      var image = overlay.querySelector("#lsListingDetailImage");
      var count = overlay.querySelector("#lsListingDetailCount");
      var showPhoto = function (index) {
        photoIndex = (index + photos.length) % photos.length;
        image.src = photos[photoIndex];
        image.alt = "매물 사진 " + (photoIndex + 1);
        count.textContent = (photoIndex + 1) + " / " + photos.length;
      };
      overlay.querySelector("[data-listing-photo-prev]").addEventListener("click", function () { showPhoto(photoIndex - 1); });
      overlay.querySelector("[data-listing-photo-next]").addEventListener("click", function () { showPhoto(photoIndex + 1); });
    }
    requestAnimationFrame(function () { overlay.querySelector("[data-listing-detail-close]").focus(); });
  };
})();