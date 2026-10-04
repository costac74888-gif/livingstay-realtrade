(function () {
  "use strict";
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const fmt = value => value == null || value === "" ? "—" : esc(value);
  const numberText = value => value == null || value === "" ? "—" : Number(value).toLocaleString("ko-KR");
  const statusNames = {received:"접수",paid:"입금확인",investigating:"조사중",reported:"보고완료",canceled:"취소",refunded:"환불"};
  const statusKeys = Object.keys(statusNames);
  const settingsFields = [
    {key:"base_fee",label:"기본 조사 금액",type:"number",required:true},
    {key:"visit_fee",label:"현장 방문 추가 금액",type:"number",required:true},
    {key:"promo_base_fee",label:"프로모션 기본 금액",type:"number"},
    {key:"promo_enabled",label:"프로모션 사용",type:"checkbox"},
    {key:"promo_end_date",label:"프로모션 종료일",type:"date"},
    {key:"bank_name",label:"은행명",required:true},
    {key:"bank_account",label:"계좌번호",required:true},
    {key:"bank_holder",label:"예금주",required:true},
    {key:"report_business_days",label:"보고서 제공 영업일",type:"number",required:true},
    {key:"cutoff_days",label:"신청 마감 기준일",type:"number",required:true},
    {key:"payment_hours",label:"입금 기한 시간",type:"number",required:true},
    {key:"provider_name",label:"조사 제공기관",required:true},
    {key:"business_registration",label:"통신판매업 신고번호",required:true},
    {key:"vat_label",label:"부가세 표기",required:true},
    {key:"service_description",label:"서비스 설명",type:"textarea",required:true},
    {key:"provider_notice",label:"제공기관 안내",type:"textarea",required:true},
    {key:"report_description",label:"보고서 안내",type:"textarea",required:true},
    {key:"refund_policy",label:"환불 기준",type:"textarea",required:true},
    {key:"privacy_policy",label:"개인정보 안내",type:"textarea",required:true}
  ];
  const checkFields = [
    {key:"business_report",label:"사업·건물 관련 사실 확인"},
    {key:"operation_succession",label:"운영 승계 관련 확인"},
    {key:"fee_arrears",label:"공과금·관리비 등 체납 확인"}
  ];
  let activeTab = "requests";
  let settingsSnapshot = null;
  let listState = {status:"",q:"",page:1,pageSize:20,transitions:{}};
  let currentRequest = null;

  const css = document.createElement("style");
  css.textContent = `
  .as-page{--as-ink:#202522;--as-muted:#758078;--as-line:#e4e7e2;--as-paper:#fffefa;--as-green:#476454;color:var(--as-ink);padding:0 0 40px}
  .as-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin:0 0 13px}.as-head h2{margin:0;font-size:22px;letter-spacing:-.05em}.as-head p{margin:4px 0 0;color:var(--as-muted);font-size:11px}
  .as-tabs{display:flex;gap:4px;padding:4px;background:#f0f1ec;border-radius:6px;margin:12px 0}.as-tab{border:0;background:transparent;padding:7px 12px;border-radius:4px;color:#687269;font:700 11px inherit;cursor:pointer}.as-tab.is-active{background:#fff;color:#29342e;box-shadow:0 1px 3px #1d27320d}
  .as-card{background:var(--as-paper);border:1px solid var(--as-line);border-radius:8px;margin:10px 0;overflow:hidden}.as-card-head{padding:12px 14px;border-bottom:1px solid var(--as-line);display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.as-card-head h3{margin:0;font-size:13px}.as-card-body{padding:13px 14px}
  .as-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.as-field{display:flex;flex-direction:column;gap:5px;min-width:0}.as-field label{font-size:10.5px;font-weight:800;color:#5d675e}.as-field input,.as-field textarea,.as-field select{box-sizing:border-box;width:100%;min-height:35px;padding:8px 9px;border:1px solid #dfe3dd;border-radius:4px;background:#fff;color:var(--as-ink);font:12px "Noto Sans KR",sans-serif}.as-field textarea{min-height:74px;resize:vertical}.as-field input:focus,.as-field textarea:focus{outline:2px solid #dce5dc;border-color:#687c6b}.as-wide{grid-column:1/-1}
  .as-toggle{display:flex;align-items:center;gap:8px;min-height:35px;font-size:11px;font-weight:700}.as-toggle input{accent-color:#476454}
  .as-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}.as-btn{border:1px solid #cfd7ce;border-radius:4px;background:#fff;color:#304033;padding:8px 11px;font:700 11px "Noto Sans KR",sans-serif;cursor:pointer}.as-btn-primary{background:#29342e;border-color:#29342e;color:white}.as-btn:disabled{opacity:.5;cursor:wait}.as-msg{font-size:11px;color:#526254;min-height:17px}
  .as-history{display:grid;gap:7px}.as-history-row{padding:9px 10px;background:#f4f5f1;border-left:2px solid #9ca99b;font-size:10.5px;line-height:1.55;overflow-wrap:anywhere}.as-history-row b{color:#476454}.as-note{color:var(--as-muted);font-size:10px}
  .as-filters{display:grid;grid-template-columns:170px minmax(160px,1fr) auto;gap:7px;margin-bottom:10px}.as-input,.as-select{box-sizing:border-box;height:35px;width:100%;border:1px solid #dfe3dd;border-radius:4px;background:#fff;padding:0 9px;color:#202522;font:12px "Noto Sans KR",sans-serif}
  .as-table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--as-line);border-radius:5px}.as-table{width:100%;min-width:1020px;border-collapse:collapse;font-size:10.5px}.as-table th{background:#f0eee7;text-align:left;padding:8px;border-bottom:1px solid #ddd7c9;white-space:nowrap}.as-table td{padding:8px;border-bottom:1px solid #edf0eb;vertical-align:top;line-height:1.45}.as-table tr:last-child td{border-bottom:0}.as-table button{border:0;background:none;color:#34483b;text-decoration:underline;font:700 10.5px "Noto Sans KR",sans-serif;cursor:pointer}.as-status{display:inline-block;padding:3px 6px;background:#edf1eb;color:#445848;font-weight:800;white-space:nowrap}
  .as-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.as-detail{padding:8px;border:1px solid #e7e9e3;min-width:0}.as-detail span{display:block;color:#788178;font-size:9px;margin-bottom:3px}.as-detail strong{font-size:11px;overflow-wrap:anywhere;white-space:pre-line}.as-pagination{display:flex;justify-content:center;align-items:center;gap:8px;padding:12px}.as-empty,.as-load-error{padding:22px;text-align:center;color:#6f7a70;font-size:11px}.as-load-error{color:#984e42}
  @media(max-width:600px){.as-fields,.as-detail-grid{grid-template-columns:1fr}.as-wide{grid-column:auto}.as-filters{grid-template-columns:1fr 1fr}.as-filters .as-search{grid-column:1/-1}.as-head h2{font-size:19px}.as-card-body{padding:11px}}
  `;
  document.head.appendChild(css);

  async function api(url, options) {
    const response = await fetch(url,Object.assign({credentials:"same-origin"},options||{}));
    if (response.status === 401) { location.href="/admin/login"; throw new Error("관리자 로그인 후 다시 시도해 주세요."); }
    const data = await response.json().catch(()=>({}));
    if (!response.ok || data.ok !== true) {
      const error = new Error(data.message || "요청을 처리하지 못했습니다.");
      error.status = response.status; error.data = data; throw error;
    }
    return data;
  }
  function activateSurvey() {
    document.querySelectorAll(".admin-menu-item").forEach(button=>button.classList.toggle("is-active",button.dataset.menu==="admin-survey"));
    const grid=document.getElementById("grid");
    if (!grid) return;
    grid.innerHTML=`<div class="as-page"><header class="as-head"><div><h2>공매 현황조사</h2><p>금액·신청조건과 접수 이후의 조사 진행을 관리합니다.</p></div></header>
      <nav class="as-tabs" aria-label="공매 조사 관리"><button type="button" class="as-tab ${activeTab==="requests"?"is-active":""}" data-as-tab="requests">신청 관리</button><button type="button" class="as-tab ${activeTab==="settings"?"is-active":""}" data-as-tab="settings">요금·계좌 설정</button></nav>
      <div id="asContent"><div class="as-empty">화면을 불러오는 중입니다.</div></div></div>`;
    grid.querySelectorAll("[data-as-tab]").forEach(button=>button.addEventListener("click",()=>{activeTab=button.dataset.asTab;activateSurvey();}));
    if (activeTab==="settings") loadSettings(); else loadRequests();
  }
  window.showAdminSurvey = activateSurvey;
  if (location.hash==="#admin-survey") activateSurvey();

  function inputField(field,value) {
    const id=`as-${field.key}`;
    if(field.type==="checkbox") return `<div class="as-field"><label>${esc(field.label)}</label><label class="as-toggle"><input id="${id}" data-setting="${esc(field.key)}" type="checkbox" ${value===true?"checked":""}> 사용</label></div>`;
    const type=field.type==="number"?"number":field.type==="date"?"date":"text";
    const val=field.type==="date"&&value?String(value).slice(0,10):value??"";
    return `<div class="as-field"><label for="${id}">${esc(field.label)}${field.required?" *":""}</label><input id="${id}" data-setting="${esc(field.key)}" type="${type}" value="${esc(val)}" ${field.type==="number"?'step="1" min="0"':""} ${field.required?"required":""}></div>`;
  }
  function areaField(field,value) {
    return `<div class="as-field as-wide"><label for="as-${field.key}">${esc(field.label)}${field.required?" *":""}</label><textarea id="as-${field.key}" data-setting="${esc(field.key)}" ${field.required?"required":""}>${esc(value??"")}</textarea></div>`;
  }
  async function loadSettings() {
    const host=document.getElementById("asContent");if(!host)return;
    host.innerHTML='<div class="as-empty">조사 설정을 불러오는 중입니다.</div>';
    try{
      const data=await api("/api/admin/survey/settings");
      settingsSnapshot=data.settings||{};
      const fields=settingsFields.map(field=>field.type==="textarea"?areaField(field,settingsSnapshot[field.key]):inputField(field,settingsSnapshot[field.key])).join("");
      const checklist=checkFields.map(field=>`<div class="as-field as-wide"><label for="as-check-${field.key}">${esc(field.label)}</label><textarea id="as-check-${field.key}" data-checklist="${field.key}" required>${esc((settingsSnapshot.checklist_descriptions||{})[field.key]||"")}</textarea></div>`).join("");
      const history=(data.history||[]).slice(0,10).map(entry=>`<div class="as-history-row"><b>${fmt(entry.changed_by)}</b> · ${fmt(entry.created_at)}<br><span>변경 전: ${esc(JSON.stringify(entry.before??{}))}</span><br><span>변경 후: ${esc(JSON.stringify(entry.after??{}))}</span></div>`).join("")||'<div class="as-note">아직 설정 변경 이력이 없습니다.</div>';
      host.innerHTML=`<section class="as-card"><div class="as-card-head"><h3>요금·계좌 설정</h3><span class="as-note">* 필수 설정</span></div><div class="as-card-body"><form id="asSettingsForm"><div class="as-fields">${fields}
        <div class="as-field as-wide"><label>확인 목록 안내 문구</label></div>${checklist}</div>
        <p class="as-note">조사 요금은 1,000원 단위 입력을 권장합니다.</p>
        <div class="as-actions"><button class="as-btn as-btn-primary" type="submit" id="asSaveSettings">설정 저장</button><span class="as-msg" id="asSettingsMsg" role="status"></span></div>
      </form></div></section>
      <section class="as-card"><div class="as-card-head"><h3>최근 설정 변경</h3><span class="as-note">최근 10건</span></div><div class="as-card-body"><div class="as-history">${history}</div></div></section>
      <section class="as-card"><div class="as-card-head"><h3>공개 약관</h3><a href="/terms/survey" target="_blank" rel="noopener">공매 조사 약관 보기</a></div><div class="as-card-body as-note">약관 본문은 약관 관리의 ‘공매 조사 약관’ 탭에서 편집할 수 있습니다.</div></section>`;
      host.querySelector("#asSettingsForm").addEventListener("submit",saveSettings);
    }catch(error){host.innerHTML=`<div class="as-load-error" role="alert">${esc(error.message)} <button type="button" class="as-btn" data-as-retry>다시 불러오기</button></div>`;host.querySelector("[data-as-retry]")?.addEventListener("click",loadSettings);}
  }
  async function saveSettings(event) {
    event.preventDefault();
    const form=event.currentTarget,msg=document.getElementById("asSettingsMsg"),button=document.getElementById("asSaveSettings");
    const payload=Object.assign({},settingsSnapshot||{});
    let invalid=null;
    form.querySelectorAll("[data-setting]").forEach(input=>{
      const key=input.dataset.setting;
      if(input.type==="checkbox") payload[key]=input.checked;
      else if(input.type==="number") {
        if(input.value.trim()===""){if(input.required)invalid=input;payload[key]=null;}
        else payload[key]=Number(input.value);
      } else {
        const value=input.value.trim();
        if(input.required&&!value)invalid=input;
        payload[key]=value;
      }
    });
    payload.checklist_descriptions=Object.assign({},payload.checklist_descriptions||{});
    form.querySelectorAll("[data-checklist]").forEach(input=>{if(!input.value.trim())invalid=input;payload.checklist_descriptions[input.dataset.checklist]=input.value.trim();});
    if(invalid){invalid.focus();msg.textContent="필수 설정을 모두 입력해 주세요.";return;}
    button.disabled=true;msg.textContent="저장 중…";
    try{
      await api("/api/admin/survey/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      msg.textContent="저장했습니다. 공개 신청 조건에 반영됩니다.";
      await loadSettings();
    }catch(error){msg.textContent=error.message||"설정을 저장하지 못했습니다.";button.disabled=false;}
  }
  async function loadRequests() {
    const host=document.getElementById("asContent");if(!host)return;
    host.innerHTML=`<section class="as-card"><div class="as-card-head"><h3>현황조사 신청</h3></div><div class="as-card-body"><div class="as-filters">
      <select class="as-select" id="asStatusFilter" aria-label="상태">${'<option value="">전체 상태</option>'+statusKeys.map(key=>`<option value="${key}" ${listState.status===key?"selected":""}>${statusNames[key]}</option>`).join("")}</select>
      <input class="as-input as-search" id="asRequestSearch" type="search" placeholder="신청번호·공매명·이름 검색" value="${esc(listState.q)}">
      <button type="button" class="as-btn as-btn-primary" id="asSearchRequests">검색</button></div>
      <div id="asRequestResults"><div class="as-empty">신청 목록을 불러오는 중입니다.</div></div></div></section>
      <section id="asRequestDetail"></section>`;
    const search=()=>{listState.status=host.querySelector("#asStatusFilter").value;listState.q=host.querySelector("#asRequestSearch").value.trim();listState.page=1;fetchRequestRows();};
    host.querySelector("#asSearchRequests").addEventListener("click",search);
    host.querySelector("#asRequestSearch").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();search();}});
    host.querySelector("#asStatusFilter").addEventListener("change",search);
    fetchRequestRows();
  }
  async function fetchRequestRows() {
    const results=document.getElementById("asRequestResults");if(!results)return;
    results.innerHTML='<div class="as-empty">신청 목록을 불러오는 중입니다.</div>';
    const params=new URLSearchParams({page:String(listState.page)});
    if(listState.status)params.set("status",listState.status);if(listState.q)params.set("q",listState.q);
    try{
      const data=await api(`/api/admin/survey/requests?${params}`);
      listState.transitions=data.transitions||{};
      const rows=Array.isArray(data.items)?data.items:[];
      if(!rows.length){results.innerHTML='<div class="as-empty">조건에 맞는 신청이 없습니다.</div>';return;}
      results.innerHTML=`<div class="as-table-wrap"><table class="as-table"><thead><tr><th>신청번호·접수일</th><th>공매</th><th>신청자·연락처</th><th>조사 방식</th><th>금액</th><th>상태</th><th>입금 기한</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr>
        <td><strong>${fmt(row.request_no)}</strong><br>${fmt(row.created_at)}</td><td>${fmt(row.auction_title)}</td>
        <td>${fmt(row.applicant_name)}<br>${fmt(row.phone)}${row.email?`<br>${esc(row.email)}`:""}</td>
        <td>${row.survey_type==="visit"?"현장 방문":"서류 중심"}<br>입금자 ${fmt(row.depositor_name)}</td>
        <td>${numberText(row.total_fee)}원<br><span class="as-note">기본 ${numberText(row.base_fee)} · 방문 ${numberText(row.visit_fee)}</span></td>
        <td><span class="as-status">${esc(statusNames[row.status]||row.status||"상태 미확인")}</span></td><td>${fmt(row.payment_deadline)}</td>
        <td><button type="button" data-request-id="${esc(row.id)}">상세·진행 관리</button></td></tr>`).join("")}</tbody></table></div>
        <div class="as-pagination"><button type="button" class="as-btn" id="asPrevPage" ${Number(data.page||1)<=1?"disabled":""}>이전</button><span>${Number(data.page||1)} / ${Math.max(1,Math.ceil(Number(data.total||0)/Number(data.page_size||20)))}</span><button type="button" class="as-btn" id="asNextPage" ${Number(data.page||1)>=Math.max(1,Math.ceil(Number(data.total||0)/Number(data.page_size||20)))?"disabled":""}>다음</button><span class="as-note">총 ${Number(data.total||0).toLocaleString("ko-KR")}건</span></div>`;
      results.querySelectorAll("[data-request-id]").forEach(button=>button.addEventListener("click",()=>loadRequestDetail(button.dataset.requestId)));
      results.querySelector("#asPrevPage")?.addEventListener("click",()=>{listState.page--;fetchRequestRows();});
      results.querySelector("#asNextPage")?.addEventListener("click",()=>{listState.page++;fetchRequestRows();});
    }catch(error){results.innerHTML=`<div class="as-load-error" role="alert">${esc(error.message)} <button type="button" class="as-btn" data-as-retry>다시 불러오기</button></div>`;results.querySelector("[data-as-retry]")?.addEventListener("click",fetchRequestRows);}
  }
  async function loadRequestDetail(id) {
    const host=document.getElementById("asRequestDetail");if(!host)return;
    host.innerHTML='<div class="as-empty">신청 상세와 이력을 불러오는 중입니다.</div>';
    try{
      const data=await api(`/api/admin/survey/requests/${encodeURIComponent(id)}`);
      const item=data.item||{};currentRequest=item;
      const allowed=listState.transitions[item.status]||data.transitions?.[item.status]||[];
      const transitionList=Array.isArray(allowed)?allowed:Array.isArray(allowed.allowed)?allowed.allowed:[];
      const history=(data.history||[]).map(entry=>`<div class="as-history-row"><b>${esc(statusNames[entry.from_status]||entry.from_status||"신청")} → ${esc(statusNames[entry.to_status]||entry.to_status||"")}</b> · ${fmt(entry.created_at)} · ${fmt(entry.changed_by)}${entry.note?`<br>${esc(entry.note)}`:""}</div>`).join("")||'<div class="as-note">진행 이력이 없습니다.</div>';
      const fields=[["신청 번호",item.request_no],["접수 시각",item.created_at],["공매 물건",item.auction_title],["신청자",item.applicant_name],["연락처",item.phone],["이메일",item.email],["입금자",item.depositor_name],["조사 방식",item.survey_type==="visit"?"현장 방문":"서류 중심"],["기본 조사 금액",numberText(item.base_fee)+"원"],["방문 추가 금액",numberText(item.visit_fee)+"원"],["합계",numberText(item.total_fee)+"원"],["입금 기한",item.payment_deadline],["신청 메모",item.memo],["관리자 메모",item.admin_memo]].map(([label,value])=>`<div class="as-detail"><span>${esc(label)}</span><strong>${fmt(value)}</strong></div>`).join("");
      host.innerHTML=`<section class="as-card"><div class="as-card-head"><h3>신청 상세 · ${fmt(item.request_no)}</h3><span class="as-status">${esc(statusNames[item.status]||item.status||"")}</span></div>
        <div class="as-card-body"><div class="as-detail-grid">${fields}</div>
        <div class="as-card" style="margin-top:12px"><div class="as-card-head"><h3>진행 상태 변경</h3></div><div class="as-card-body">
          <form id="asStatusForm"><div class="as-fields"><div class="as-field"><label for="asNextStatus">다음 상태</label><select id="asNextStatus" class="as-select" ${transitionList.length?"":"disabled"}>${transitionList.map(status=>`<option value="${esc(status)}">${esc(statusNames[status]||status)}</option>`).join("")}</select></div>
          <div class="as-field"><label for="asStatusNote">변경 메모</label><input id="asStatusNote" type="text" maxlength="1000" placeholder="변경 사유 또는 작업 메모"></div></div>
          <div class="as-actions"><button class="as-btn as-btn-primary" type="submit" ${transitionList.length?"":"disabled"}>상태 변경</button><span class="as-msg" id="asStatusMsg" role="status">${transitionList.length?"":"현재 상태에서 허용된 변경이 없습니다."}</span></div></form>
        </div></div>
        <div class="as-card"><div class="as-card-head"><h3>상태 변경 이력</h3></div><div class="as-card-body"><div class="as-history">${history}</div></div></div></div></section>`;
      host.querySelector("#asStatusForm")?.addEventListener("submit",event=>changeStatus(event,item.id));
    }catch(error){host.innerHTML=`<div class="as-load-error" role="alert">${esc(error.message)} <button type="button" class="as-btn" data-as-retry>다시 불러오기</button></div>`;host.querySelector("[data-as-retry]")?.addEventListener("click",()=>loadRequestDetail(id));}
  }
  async function changeStatus(event,id) {
    event.preventDefault();
    const form=event.currentTarget,button=form.querySelector('button[type="submit"]'),msg=form.querySelector("#asStatusMsg");
    const status=form.querySelector("#asNextStatus").value;
    if(!status)return;
    button.disabled=true;msg.textContent="상태를 저장 중입니다.";
    try{
      await api(`/api/admin/survey/requests/${encodeURIComponent(id)}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status,note:form.querySelector("#asStatusNote").value.trim()})});
      await fetchRequestRows();await loadRequestDetail(id);
    }catch(error){msg.textContent=error.message||"상태를 변경하지 못했습니다.";button.disabled=false;}
  }
})();