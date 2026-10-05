(function () {
  "use strict";
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const money = value => value == null || value === "" || !Number.isFinite(Number(value)) ? "확인 필요" : `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
  const date = value => {
    if (!value) return "일정 확인 필요";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? esc(value) : new Intl.DateTimeFormat("ko-KR",{year:"numeric",month:"long",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(parsed);
  };
  async function jsonRequest(url, options) {
    const response = await fetch(url, Object.assign({credentials:"same-origin"}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok !== true) {
      const error = new Error(data.message || "요청을 처리하지 못했습니다.");
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }
  const rowFact = (label, value) => `<div class="survey-fact"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  const statusLabel = value => {
    const raw = String(value || "");
    return ({
      scheduled:"입찰예정",bidding:"입찰중",failed:"유찰",sold:"낙찰",canceled:"취소",closed:"종료"
    })[raw.toLowerCase()] || (/[\u3131-\uD79D]/.test(raw) ? raw : "상태 확인 필요");
  };
  const finite = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const uuid = () => {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (window.crypto && typeof window.crypto.getRandomValues === "function") window.crypto.getRandomValues(bytes);
    else for (let index=0;index<bytes.length;index++) bytes[index]=Math.floor(Math.random()*256);
    bytes[6]=(bytes[6]&0x0f)|0x40;bytes[8]=(bytes[8]&0x3f)|0x80;
    const hex=Array.from(bytes,byte=>byte.toString(16).padStart(2,"0")).join("");
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  };
  const displayArea = item => finite(item.area_m2) && Number(item.area_m2) > 0
    ? `${Number(item.area_m2).toLocaleString("ko-KR",{maximumFractionDigits:2})}㎡${item.unit_label ? ` · ${item.unit_label}` : ""}`
    : "확인 필요";
  const membershipRequired = data => Boolean(data && data.membership_access && data.membership_access.required === true);
  const membershipInfoUrl = data => {
    const candidate = data && data.membership_access && data.membership_access.info_url;
    return typeof candidate === "string" && candidate.startsWith("/") && !candidate.startsWith("//")
      ? candidate : "/membership";
  };
  function renderMembershipNotice(target, data) {
    if (!target) return;
    target.innerHTML = `<section class="survey-membership-notice" role="status">
      <span class="survey-kicker">MEMBERSHIP ACCESS</span>
      <h2>멤버십 준비 중</h2>
      <p>현황조사 정보와 신청 기능은 멤버십 서비스 준비 후 이용하실 수 있습니다.</p>
      <a href="${esc(membershipInfoUrl(data))}">멤버십 안내</a>
    </section>`;
  }

  function renderDetail(slot, id, item, links, comparison, checklist, availability, analysisNotice) {
    const matched = Boolean(item.master_building_id);
    const analysis = matched ? (Array.isArray(links) ? links : []).map(link => {
      let href = "";
      try { const u = new URL(link.url, location.origin); if (u.protocol === "https:" || u.protocol === "http:") href = u.href; } catch (_) {}
      return href ? `<a class="survey-analysis-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer"><span>${esc(link.label || "투자분석")}</span><span aria-hidden="true">↗</span></a>` : "";
    }).join("") : "";
    const checklistItems = [
      ["영업신고 현황","business_report"],
      ["위탁운영 승계 여부","operation_succession"],
      ["관리비 체납 여부","fee_arrears"]
    ];
    const checklistByKey = Object.fromEntries((Array.isArray(checklist) ? checklist : []).map(entry=>[entry.key,entry.description]));
    const checkItems = checklistItems.map(([label,key]) =>
      `<article class="survey-check-item"><div class="survey-check-top"><strong>${esc(label)}</strong><span class="survey-check-state">확인필요</span></div><p>현황조사 신청 시 확인</p>${checklistByKey[key] ? `<p class="survey-check-detail">${esc(checklistByKey[key])}</p>` : ""}</article>`
    ).join("");
    const canApply = availability && availability.can_apply === true;
    const availabilityText = availability && availability.reason || "";
    const facts = [
      rowFact("공매 물건", item.title || "제목 확인 필요"),
      rowFact("주소", item.address || "주소 확인 필요"),
      rowFact("최저입찰가", money(item.min_bid_price)),
      ...(finite(item.min_bid_price) && Number(item.min_bid_price) > 0 && finite(item.area_m2) && Number(item.area_m2) > 0
        ? [rowFact("최저입찰가/평", money(Math.round(Number(item.min_bid_price) / Number(item.area_m2) * 3.3058)))]
        : []),
      rowFact("면적", displayArea(item)),
      rowFact("입찰 마감", date(item.bid_end_at)),
      rowFact("물건 상태", statusLabel(item.status))
    ].join("");
    slot.innerHTML = `<section class="survey-block" aria-labelledby="surveyAnalysisTitle">
      <header class="survey-head"><h2 id="surveyAnalysisTitle">투자분석</h2></header>
      <div class="survey-body"><div class="survey-source-facts">${facts}</div>
      ${matched ? (analysis ? `<div class="survey-analysis-links">${analysis}</div>` : "") : `<div class="survey-unavailable">건물 매칭 전이라 분석을 제공하지 않습니다.</div>`}
      ${matched && analysisNotice ? `<p class="survey-analysis-notice">${esc(analysisNotice)}</p>` : ""}
      ${matched && comparison && comparison.text ? `<div class="survey-comparison">${esc(comparison.text)}</div>` : ""}
      <h3 class="survey-checklist-heading">생활형숙박시설 체크리스트</h3>
      <div class="survey-checklist">${checkItems}</div>
      ${canApply ? `<button class="survey-apply" type="button" data-open-auction-survey="${esc(id)}">현황조사 신청</button>` : `<button class="survey-apply" type="button" disabled>현황조사 신청</button>${availabilityText ? `<p class="survey-copy">${esc(availabilityText)}</p>` : ""}`}
      </div></section>`;
    slot.querySelector("[data-open-auction-survey]")?.addEventListener("click",()=>window.openAuctionSurvey(id));
    if (matched) loadMarketReference(item).then(reference => {
      if (!reference || !slot.isConnected) return;
      const body = slot.querySelector(".survey-body");
      const referenceNode = document.createElement("p");
      referenceNode.className = "survey-market-reference";
      referenceNode.textContent = reference;
      const heading = slot.querySelector(".survey-analysis-links");
      if (heading) heading.after(referenceNode);
      else body.insertBefore(referenceNode, body.querySelector(".survey-checklist-heading"));
    });
  }

  async function loadMarketReference(item) {
    const buildingId = String(item.master_building_id == null ? "" : item.master_building_id);
    const area = Number(item.area_m2);
    if (!/^\d+$/.test(buildingId) || !finite(item.area_m2) || !Number.isFinite(area) || area <= 0 || area > 10000) return "";
    try {
      const params = new URLSearchParams({building_id:buildingId,area_sqm:String(area)});
      const response = await fetch(`/api/analysis/rental-market-price?${params}`,{credentials:"same-origin"});
      const data = await response.json().catch(()=>({}));
      const sampleCount = Number(data.sample_count);
      const medianManwon = Number(data.median_price);
      const verifiedArea = Number(data.area_sqm);
      const periodMonths = Number(data.period_months);
      if (!response.ok || data.ok !== true || !Number.isFinite(sampleCount) || sampleCount <= 0 ||
          !Number.isFinite(medianManwon) || medianManwon <= 0 || !Number.isFinite(verifiedArea) || verifiedArea <= 0 ||
          !Number.isFinite(periodMonths) || periodMonths <= 0) return "";
      const cohort = data.match_type === "exact" ? "동일 면적" : data.match_type === "similar" ? "동일·유사 면적" : "";
      if (!cohort) return "";
      const medianWon = Math.round(medianManwon * 10000);
      const perPyeong = Math.round(medianWon / verifiedArea * 3.3058);
      return `동일 건물 매매 실거래 참고 · 최근 ${periodMonths}개월 ${cohort} ${sampleCount.toLocaleString("ko-KR")}건 · 중앙값 ${money(medianWon)} (${verifiedArea.toLocaleString("ko-KR",{maximumFractionDigits:2})}㎡ 기준 ${money(perPyeong)}/평)`;
    } catch (_) { return ""; }
  }

  async function loadAuctionInfo(id) {
    return jsonRequest(`/api/auctions/${encodeURIComponent(id)}/survey-info`);
  }

  const detailMounts = new WeakMap();
  window.mountAuctionSurveyDetail = async function(slot,id) {
    if(!slot||!id)return;
    const sequence=(detailMounts.get(slot)||0)+1;detailMounts.set(slot,sequence);
    slot.innerHTML=`<section class="survey-block"><div class="survey-loading" role="status">투자분석과 현황조사 정보를 확인 중입니다.</div></section>`;
    try {
      const data=await loadAuctionInfo(id);
      if(detailMounts.get(slot)!==sequence||!slot.isConnected)return;
      if(membershipRequired(data)){
        renderMembershipNotice(slot,data);
        return;
      }
      if(!data.item)throw new Error("공매 정보를 찾을 수 없습니다.");
      const item=data.item;if(item.id==null)item.id=id;
      renderDetail(slot,id,item,data.analysis_links,data.comparison,data.checklist,data.availability,data.analysis_notice);
    } catch(error) {
      if(detailMounts.get(slot)!==sequence||!slot.isConnected)return;
      if(error.data && error.data.code === "MEMBERSHIP_PREPARING"){
        renderMembershipNotice(slot,error.data);
        return;
      }
      slot.innerHTML=`<section class="survey-block"><div class="survey-error" role="alert">${esc(error.message||"현황조사 정보를 불러오지 못했습니다.")}<button type="button" data-survey-retry>다시 불러오기</button></div></section>`;
      slot.querySelector("[data-survey-retry]")?.addEventListener("click",()=>window.mountAuctionSurveyDetail(slot,id));
    }
  };

  let surveyDrawerSequence=0;
  window.openAuctionSurvey = async function(id) {
    if(!id)return;
    const sequence=++surveyDrawerSequence;
    let drawer=document.getElementById("auctionSurveyDrawer");
    if(!drawer){
      drawer=document.createElement("div");
      drawer.id="auctionSurveyDrawer";
      drawer.className="survey-drawer";
      drawer.hidden=true;
      drawer.innerHTML=`<div class="survey-drawer-backdrop" data-survey-close></div><section class="survey-drawer-panel" role="dialog" aria-modal="true" aria-labelledby="auctionSurveyDrawerTitle"><header class="survey-drawer-header"><div><span class="survey-kicker">PROPERTY DUE DILIGENCE</span><h2 id="auctionSurveyDrawerTitle">현황조사 신청</h2></div><button type="button" class="survey-drawer-close" data-survey-close aria-label="신청창 닫기">×</button></header><div class="survey-drawer-content" id="auctionSurveyDrawerContent"></div></section>`;
      document.body.append(drawer);
      drawer.addEventListener("click",event=>{if(event.target.closest("[data-survey-close]"))closeSurveyDrawer();});
      drawer.addEventListener("keydown",event=>{
        if(event.key==="Escape"){event.preventDefault();closeSurveyDrawer();return;}
        if(event.key!=="Tab")return;
        const focusable=[...drawer.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter(node=>node.offsetParent!==null);
        if(!focusable.length){event.preventDefault();return;}
        const first=focusable[0],last=focusable[focusable.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      });
    }
    drawer._returnFocus=document.activeElement;
    drawer.hidden=false;document.body.classList.add("survey-drawer-open");
    const panel=drawer.querySelector(".survey-drawer-panel");
    panel.querySelector(".survey-drawer-close").focus();
    const content=drawer.querySelector("#auctionSurveyDrawerContent");
    content.innerHTML='<div class="survey-loading" role="status">조사 범위와 신청 조건을 확인 중입니다.</div>';
    try {
      const auction=await loadAuctionInfo(id);
      if(sequence!==surveyDrawerSequence||drawer.hidden)return;
      if(membershipRequired(auction)){
        renderMembershipNotice(content,auction);
        return;
      }
      const configData=await jsonRequest("/api/survey/config");
      if(sequence!==surveyDrawerSequence||drawer.hidden)return;
      const item=auction.item||{},config=configData.config||auction.config||{};
      if(!auction.availability||auction.availability.can_apply!==true)throw new Error(auction.availability?.reason||"현재 현황조사 신청이 불가능합니다.");
      renderApplication(content,id,item,config,auction.checklist);
      panel.querySelector(".survey-drawer-header h2").focus?.();
    } catch(error) {
      if(sequence!==surveyDrawerSequence||drawer.hidden)return;
      if(error.data && error.data.code === "MEMBERSHIP_PREPARING"){
        renderMembershipNotice(content,error.data);
        return;
      }
      content.innerHTML=`<div class="survey-error" role="alert"><strong>${esc(error.message||"신청 정보를 불러오지 못했습니다.")}</strong><p>잠시 후 다시 시도해 주세요.</p><button type="button" data-drawer-retry>다시 불러오기</button></div>`;
      content.querySelector("[data-drawer-retry]")?.addEventListener("click",()=>window.openAuctionSurvey(id));
    }
  };
  function closeSurveyDrawer() {
    const drawer=document.getElementById("auctionSurveyDrawer");
    if(!drawer||drawer.hidden)return;
    drawer.hidden=true;document.body.classList.remove("survey-drawer-open");
    drawer._returnFocus?.focus?.();
  }

  function renderApplication(app, id, item, config, checklist) {
    const infoBlock = `<div class="survey-source-facts">${rowFact("공매 물건",item.title || "제목 확인 필요")}${rowFact("주소",item.address || "주소 확인 필요")}${rowFact("최저입찰가",money(item.min_bid_price))}${rowFact("면적",displayArea(item))}${rowFact("입찰 마감",date(item.bid_end_at))}${rowFact("물건 상태",statusLabel(item.status))}</div>`;
    const checklistByKey = Object.fromEntries((Array.isArray(checklist) ? checklist : []).map(entry=>[entry.key,entry.description]));
    const items = [
      ["영업신고 현황","business_report"],
      ["위탁운영 승계 여부","operation_succession"],
      ["관리비 체납 여부","fee_arrears"]
    ].map(([title,key]) => `<div class="survey-report-item"><strong>${esc(title)}</strong><span>${esc(checklistByKey[key]||"조사 신청 시 확인")}</span></div>`).join("");
    app.innerHTML = `<button class="survey-back" type="button" data-survey-close>← 공매정보로 돌아가기</button>
      <h1 class="survey-page-title">현황조사 신청</h1><p class="survey-page-intro">제공기관과 조사 범위를 확인한 뒤 신청 정보를 작성해 주세요.</p>
      <section class="survey-card"><h2>조사 대상 공매</h2><div class="survey-card-content">${infoBlock}</div></section>
      <section class="survey-card"><h2>조사 범위</h2><div class="survey-card-content"><div class="survey-report-items">${items}</div>
      <div class="survey-provider-note"><p><b>서비스 설명</b><br>${esc(config.service_description || "")}</p>
<p><b>보고서 설명</b><br>${esc(config.report_description || "")}</p>
<p>${esc(config.provider_notice || "")}</p>
<p>제공기관: ${esc(config.provider_name || "")}<br>${config.business_registration ? `통신판매업 신고번호: ${esc(config.business_registration)}<br>` : ""}보고서 제공 기준: 입금 확인 후 ${esc(config.report_business_days ?? "")}영업일 이내.</p></div></div></section>
      <form id="surveyRequestForm" novalidate>
        <section class="survey-card"><h2>조사 방식 및 금액</h2><div class="survey-card-content">
          <div class="survey-type-options">
            <label class="survey-type-option"><input type="radio" name="survey_type" value="basic" checked><span><b>기본 조사(서류·전화 확인)</b><small>${money(config.effective_base_fee)}</small></span></label>
            <label class="survey-type-option"><input type="radio" name="survey_type" value="visit"><span><b>현장 방문 포함</b><small>기본 조사 + 방문 추가 ${money(config.visit_fee)}</small></span></label>
          </div>
          <div class="survey-total"><span class="survey-total-label">신청 예상 금액${config.vat_label ? ` · ${esc(config.vat_label)}` : ""}</span><span><small id="surveyRegularPrice" class="survey-total-was"></small><strong id="surveyTotalPrice" class="survey-total-price"></strong></span></div>
          <p class="survey-copy" id="surveyFeeNote"></p>
          <div class="survey-provider-note">신청 마감: 입찰마감일 ${esc(config.cutoff_days)}일 전까지<br>
입금 기한: 접수 후 ${esc(config.payment_hours)}시간 · 기한 내 미입금 시 자동취소<br>
입금 계좌: ${esc(config.bank_name)} ${esc(config.bank_account)}<br>예금주: ${esc(config.bank_holder)}</div>
        </div></section>
        <section class="survey-card"><h2>신청자 정보</h2><div class="survey-card-content"><div class="survey-form-grid">
          <div class="survey-field"><label for="surveyApplicant">신청자 이름 *</label><input id="surveyApplicant" name="applicant_name" autocomplete="name" required maxlength="100"></div>
          <div class="survey-field"><label for="surveyPhone">연락처 *</label><input id="surveyPhone" name="phone" type="tel" autocomplete="tel" required maxlength="40"></div>
          <div class="survey-field"><label for="surveyEmail">이메일 (선택)</label><input id="surveyEmail" name="email" type="email" autocomplete="email" maxlength="254"></div>
          <div class="survey-field"><label for="surveyDepositor">입금자명 *</label><input id="surveyDepositor" name="depositor_name" required maxlength="100"></div>
          <div class="survey-field is-wide"><label for="surveyMemo">조사 관련 전달사항 (선택)</label><textarea id="surveyMemo" name="memo" maxlength="2000"></textarea></div>
        </div></div></section>
        <section class="survey-card"><h2>확인 및 동의</h2><div class="survey-card-content"><div class="survey-agreements">
          <label class="survey-agreement"><input type="checkbox" name="agree_terms" required><span><a href="/terms/survey" target="_blank" rel="noopener">공매 조사 약관</a>을 확인하고 동의합니다. *</span></label>
          <label class="survey-agreement"><input type="checkbox" name="agree_refund" required><span>환불 기준을 확인하고 동의합니다. *<br>${esc(config.refund_policy || "")}</span></label>
          <label class="survey-agreement"><input type="checkbox" name="agree_privacy" required><span>개인정보 처리 내용을 확인하고 동의합니다. *<br>${esc(config.privacy_policy || "")}</span></label>
        </div></div></section>
        <p class="survey-form-message" id="surveyFormMessage" role="alert"></p>
        <button class="survey-submit" id="surveySubmit" type="submit">조사 신청 접수</button>
      </form>`;
    const form = app.querySelector("#surveyRequestForm");
    const feeNote = app.querySelector("#surveyFeeNote");
    const requestToken = uuid();
    const baseRaw = config.effective_base_fee ?? config.base_fee;
    const regularRaw = config.base_fee;
    const visitRaw = config.visit_fee;
    const validFee = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
    const base = validFee(baseRaw) ? Number(baseRaw) : null;
    const regularBase = validFee(regularRaw) ? Number(regularRaw) : null;
    const visit = validFee(visitRaw) ? Number(visitRaw) : null;
    const quoteValid = base !== null && visit !== null;
    const promosActive = config.promo_enabled === true && config.promo_active === true;
    const selected = () => form.elements.survey_type.value;
    const refreshAmount = () => {
      const isVisit = selected() === "visit";
      const total = quoteValid ? base + (isVisit ? visit : 0) : null;
      const regular = regularBase !== null && visit !== null ? regularBase + (isVisit ? visit : 0) : null;
      app.querySelector("#surveyTotalPrice").textContent = money(total);
      app.querySelector("#surveyRegularPrice").textContent = promosActive && regular !== null && total !== null && regular > total ? money(regular) : "";
      feeNote.textContent = config.promo_end_date && promosActive ? `프로모션 종료일: ${config.promo_end_date}까지 (한국시간)` : "";
    };
    form.querySelectorAll('[name="survey_type"]').forEach(input => input.addEventListener("change",refreshAmount));
    refreshAmount();
    if (!quoteValid) {
      app.querySelector("#surveySubmit").disabled = true;
      app.querySelector("#surveyFormMessage").textContent = "조사 금액 설정을 확인할 수 없어 신청을 진행할 수 없습니다.";
    }
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const message = app.querySelector("#surveyFormMessage");
      const submit = app.querySelector("#surveySubmit");
      message.textContent = "";
      if (!quoteValid) { message.textContent = "조사 금액 설정을 확인할 수 없어 신청을 진행할 수 없습니다."; return; }
      if (!form.reportValidity()) return;
      if (!form.elements.agree_terms.checked || !form.elements.agree_refund.checked || !form.elements.agree_privacy.checked) {
        message.textContent = "필수 동의 항목을 모두 확인해 주세요."; return;
      }
      submit.disabled = true; submit.textContent = "신청 내용을 확인하고 있습니다.";
      const body = {
        applicant_name:form.elements.applicant_name.value.trim(),
        phone:form.elements.phone.value.trim(),
        email:form.elements.email.value.trim(),
        memo:form.elements.memo.value.trim(),
        depositor_name:form.elements.depositor_name.value.trim(),
        survey_type:selected(),
        agree_terms:form.elements.agree_terms.checked,
        agree_refund:form.elements.agree_refund.checked,
        agree_privacy:form.elements.agree_privacy.checked,
        config_version:config.version,
        request_token:requestToken
      };
      try {
        const response = await fetch(`/api/auctions/${encodeURIComponent(id)}/survey-requests`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
        const data = await response.json().catch(()=>({}));
        if(response.status===403&&data.code==="MEMBERSHIP_PREPARING"){
          renderMembershipNotice(app,data);
          return;
        }
        if (response.status === 409) {
          const fresh = await jsonRequest("/api/survey/config");
          const updated = fresh.config || {};
          const auctionFresh = await loadAuctionInfo(id).catch(()=>null);
          renderApplication(app,id,auctionFresh?.item || item,updated,auctionFresh?.checklist || checklist);
          const notice = document.createElement("p");
          notice.className = "survey-form-message";
          notice.setAttribute("role","alert");
          notice.textContent = "조사 조건이 변경되어 최신 금액과 약관을 다시 확인해야 합니다. 동의 항목을 다시 체크한 뒤 신청해 주세요.";
          app.querySelector("#surveyRequestForm").before(notice);
          return;
        }
        if (![200, 201].includes(response.status) || data.ok !== true || !data.receipt) throw new Error(data.message || "신청 접수에 실패했습니다.");
        renderReceipt(app,data.receipt);
      } catch (error) {
        message.textContent = error.message || "네트워크 오류가 발생했습니다. 같은 신청을 다시 확인해 주세요.";
        submit.disabled = false; submit.textContent = "조사 신청 접수";
      }
    });
  }
  function renderReceipt(app, receipt) {
    const account = [receipt.bank_name,receipt.bank_account,receipt.bank_holder].filter(Boolean).join(" ");
    app.innerHTML = `<button class="survey-back" type="button" data-survey-close>← 공매정보로 돌아가기</button><section class="survey-receipt" aria-live="polite">
      <div class="survey-kicker">REQUEST RECEIVED</div><h2>조사 신청이 접수되었습니다.</h2>
      <p>입금 확인 후 조사 절차가 진행됩니다. 신청 번호와 결제 기한을 확인해 주세요.</p>
      <div class="survey-receipt-no">${esc(receipt.request_no || "접수번호 확인 필요")}</div>
      <div class="survey-payment"><div>조사비용 <strong>${money(receipt.total_fee)}</strong></div><div>입금 기한 <strong>${date(receipt.payment_deadline)}</strong></div><div>입금 계좌 <strong>${esc(account || "계좌 정보 확인 필요")}</strong></div></div>
      <button type="button" class="survey-copy-account" id="copySurveyAccount">계좌 정보 복사</button>
      </section>`;
    app.querySelector("#copySurveyAccount").addEventListener("click", async event => {
      try {
        await navigator.clipboard.writeText(account);
        event.currentTarget.textContent = "계좌 정보를 복사했습니다.";
      } catch (_) { event.currentTarget.textContent = account || "계좌 정보를 복사할 수 없습니다."; }
    });
  }
  function initTerms() {
    const body = document.getElementById("surveyTermsBody");
    if (!body) return;
    fetch("/api/legal/survey_terms",{credentials:"same-origin"}).then(async response => {
      const data = await response.json().catch(()=>({}));
      if (!response.ok || data.ok !== true || !data.content) throw new Error("공매 조사 약관을 불러오지 못했습니다.");
      body.innerHTML = data.content;
      if (data.updated_at) document.getElementById("surveyTermsUpdated").textContent = `최종 개정일 ${data.updated_at}`;
    }).catch(() => { body.textContent = "약관을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."; });
  }
  initTerms();
})();