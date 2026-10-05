(function(){
  "use strict";
  const host=document.getElementById("membershipApp");
  const assetStamp=document.currentScript?.src||"membership";
  const esc=v=>String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const date=v=>{if(!v)return "—";const d=new Date(v);return Number.isNaN(d.getTime())?esc(v):new Intl.DateTimeFormat("ko-KR",{year:"numeric",month:"long",day:"numeric"}).format(d)};
  const money=v=>Number(v||0).toLocaleString("ko-KR")+"원";
  function uuid(){if(crypto.randomUUID)return crypto.randomUUID();return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c==="x"?r:(r&3|8)).toString(16)})}
  async function api(url,options){const res=await fetch(url,Object.assign({credentials:"same-origin",cache:"no-store",headers:{}},options||{}));const data=await res.json().catch(()=>({}));if(!res.ok||data.ok!==true){const e=new Error(data.message||"요청을 처리하지 못했습니다.");e.status=res.status;e.data=data;throw e}return data}
  let snapshot=null,loadingSeq=0;
  const statusText={pending:"입금 확인 대기",approved:"승인 완료",rejected:"반려",canceled:"취소",revoked:"이용 취소",active:"이용 중",inactive:"미가입"};
  const resultLabel={need_check:"확인 대기",ok:"확인 완료",issue:"확인사항 있음"};
  function renderError(error,retry){host.innerHTML=`<div class="membership-error" role="alert">${esc(error.message||"정보를 불러오지 못했습니다.")}<div class="member-actions"><button class="membership-btn secondary" type="button" data-retry>다시 시도</button></div></div>`;host.querySelector("[data-retry]")?.addEventListener("click",retry)}
  async function load(){
    if(!host)return;const seq=++loadingSeq;host.innerHTML='<div class="membership-loading"><span></span> 멤버십 정보를 확인하고 있습니다.</div>';
    try{const data=await api("/api/membership/me");if(seq!==loadingSeq)return;snapshot=data;render(data)}
    catch(error){if(seq===loadingSeq)renderError(error,load)}
  }
  function bankMarkup(bank){if(!bank)return "";return `<div class="bank-box"><strong>입금 계좌 · 은행 송금</strong>${esc(bank.bank_name)} ${esc(bank.bank_account)}<br>예금주 ${esc(bank.bank_holder)}<br><b>입금 금액 ${money(29000)}</b></div>`}
  function paymentMarkup(payment,bank){
    if(!payment)return "";
    return `<article class="member-row"><div class="member-row-head"><div><h3>신청 번호 ${esc(payment.request_no||"확인 중")}</h3><p>${esc(statusText[payment.status]||payment.status)} · 접수 ${date(payment.created_at)}</p></div>${payment.status==="pending"?`<button class="membership-btn danger" type="button" data-cancel-payment="${esc(payment.id)}">신청 취소</button>`:""}</div>
      <p>입금자명 ${esc(payment.depositor_name||"—")} · ${money(payment.amount||29000)}</p>${bankMarkup(payment.bank||bank)}
      ${payment.status==="approved"?'<p class="membership-footnote">관리자가 입금 내역을 확인했습니다. 최초 이용은 승인 시 시작하며, 조기 갱신은 기존 이용기간 뒤에 이어집니다.</p>':""}
      ${payment.admin_note?`<div class="member-report">${esc(payment.admin_note)}</div>`:""}</article>`;
  }
  function checkMarkup(item){
    const results=[["영업신고",item.business_report],["위탁운영",item.operation_succession],["관리비",item.fee_arrears]];
    const result=results.map(([label,value])=>`<div class="member-result ${value==="issue"?"is-issue":""}"><b>${esc(label)}</b>${esc(value==="need_check"&&item.status==="reported"?"미확인":resultLabel[value]||"확인 대기")}</div>`).join("");
    return `<article class="member-row"><div class="member-row-head"><div><h3>${esc(item.title||"확인 대상")} · ${esc(item.status==="reported"?"보고 완료":item.status==="investigating"?"확인 중":"접수")}</h3><p>${esc(item.address||"")} · ${date(item.created_at)}</p></div></div><div class="member-report-grid">${result}</div>${item.report?`<div class="member-report">${esc(item.report)}</div>`:'<p>확인 결과가 등록되면 이곳에서 보고서를 볼 수 있습니다.</p>'}</article>`
  }
  function render(data){
    if(!data.logged_in){host.innerHTML=`<section class="membership-card guest-card"><span class="member-state is-inactive">회원 전용</span><h2>로그인 후 멤버십을 신청하세요.</h2><p>월 29,000원 · 수동 계좌이체로 신청하며 입금 확인 후 관리자가 이용을 승인합니다. 자동 결제는 진행되지 않습니다.</p><div class="member-actions"><button class="membership-btn" type="button" data-login>로그인</button></div></section>`;host.querySelector("[data-login]").addEventListener("click",()=>window.livingstayOpenLogin?.());return}
    const active=data.status==="active",pending=(data.payments||[]).find(p=>p.status==="pending"),latest=(data.payments||[])[0];
    const period=data.period;
    const renew=active?"다음 달 이용 신청":"멤버십 이용 신청";
    const paymentForm=pending?"":!data.bank?`<p class="membership-error">${esc(data.bank_error||"입금 계좌가 설정되지 않았습니다. 관리자에게 문의해 주세요.")}</p>`:`<form class="membership-form" id="membershipPayForm"><div class="membership-field"><label for="memberDepositor">입금자명</label><input id="memberDepositor" name="depositor_name" required maxlength="100" autocomplete="name" placeholder="실제 송금에 사용할 이름"></div><label class="membership-consent"><input type="checkbox" name="agree_terms" required><span>월 이용료 29,000원, 입금 확인 후 1개월 이용에 동의합니다. 월 1개 동일 물건에 세 항목을 각 1회 자료·전화로 확인하며, 미사용 횟수는 이월되지 않고 현장 방문은 제공하지 않습니다. 자동 결제가 아니며 신청만으로 활성화되지 않습니다.</span></label><p id="membershipPayMessage" class="membership-message" role="alert"></p><button class="membership-btn" type="submit">신청 후 계좌 확인</button></form>`;
    const latestPayment=pending||latest;
    const reportItems=(data.checks||[]).length?(data.checks||[]).map(checkMarkup).join(""):'<div class="membership-empty">아직 확인 신청이나 보고서가 없습니다. 이용 가능 기간에 원하는 건물을 선택해 신청할 수 있습니다.</div>';
    host.innerHTML=`<div class="membership-dashboard">
      <div class="member-summary">
        <section class="membership-card"><span class="member-state ${active?"":pending?"is-pending":"is-inactive"}">${active?"이용 중":pending?"입금 확인 대기":"이용권 없음"}</span><h2>${active?"멤버십이 활성화되어 있습니다":pending?"신청이 접수되었습니다":"이용을 시작해 보세요"}</h2>
          ${active?`<p class="member-metric">${Number(data.remaining||0)}<small> / 월 1건 남음</small></p><p>이번 이용 기간 ${date(period?.starts_at)} – ${date(period?.ends_at)}</p><p>결제 완료 이용권 만료 ${date(data.paid_through||period?.ends_at)}</p><p>공식 영업·운영 기록 무제한 열람 · 매월 물건 1곳의 세 가지 확인 포함</p>`:`<p>공식 영업·운영 기록 무제한 열람과 매월 물건 한 곳에 대한 세 가지 확인이 포함됩니다.</p>`}
          <div class="member-plan-meta"><span>월 이용료 <b>${money(29000)}</b></span><span>결제 방식 <b>은행 송금</b></span><span>현장 방문 미포함</span></div>
          ${!pending?paymentForm:""}</section>
        <section class="membership-card"><span class="section-kicker">MEMBERSHIP PAYMENT</span><h2>${pending?"신청 내역":"최근 신청"}</h2>${latestPayment?paymentMarkup(latestPayment,data.bank):'<p>아직 결제 신청이 없습니다.</p>'}
          ${!pending?`<div class="member-actions"><button class="membership-btn ${active?"secondary":""}" type="button" data-renew>${renew}</button></div>`:""}
          <p class="membership-footnote">송금 확인은 관리자가 직접 처리합니다. 신청만으로 이용 기간이 시작되지 않습니다.${active?" 갱신은 현재 기간 다음에 이어지며 자동 결제되지 않습니다.":""}</p></section>
      </div>
      <section class="membership-card"><div class="member-row-head"><div><span class="section-kicker">MONTHLY CHECK</span><h2>확인 신청 및 보고서</h2></div>${active&&Number(data.remaining)>0?'<span class="member-state">신청 가능</span>':""}</div><p>${active?"이번 이용 기간 남은 확인 횟수: "+Number(data.remaining||0)+" / 1":"확인 신청은 활성 이용 기간에 가능합니다."}</p><p>지도에서 건물의 운영정보 → ‘이번 달 포함 확인 신청’을 선택하거나 공매 현황조사 탭에서 신청하세요.</p><a href="/">지도에서 건물 선택</a><div class="membership-list">${reportItems}</div></section></div>`;
    host.querySelector("#membershipPayForm")?.addEventListener("submit",submitPayment);
    host.querySelector("[data-renew]")?.addEventListener("click",()=>host.querySelector("#memberDepositor")?.focus());
    host.querySelector("[data-cancel-payment]")?.addEventListener("click",cancelPayment);
  }
  async function submitPayment(event){
    event.preventDefault();const form=event.currentTarget,button=form.querySelector("button[type=submit]"),message=form.querySelector(".membership-message");
    if(!form.reportValidity())return;button.disabled=true;message.textContent="신청을 접수하고 있습니다.";
    // Keep this token for retries of this exact form until a successful receipt.
    const token=form.dataset.requestToken||(form.dataset.requestToken=uuid());
    try{await api("/api/membership/payments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({depositor_name:form.elements.depositor_name.value.trim(),request_token:token,agree_terms:form.elements.agree_terms.checked})});await load()}
    catch(error){message.textContent=error.message||"신청을 접수하지 못했습니다.";button.disabled=false}
  }
  async function cancelPayment(event){const button=event.currentTarget,id=button.dataset.cancelPayment;if(!confirm("입금 대기 중인 멤버십 신청을 취소할까요?"))return;button.disabled=true;try{await api(`/api/membership/payments/${encodeURIComponent(id)}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});await load()}catch(error){alert(error.message||"취소하지 못했습니다.");button.disabled=false}}
  function closeDialog(dialog){dialog?.remove();document.body.classList.remove("membership-dialog-open")}
  function openCheckDialog(property){
    if(!property||(!property.building_id&&!property.auction_id))return;
    if(!document.querySelector('link[href*="/css/membership.css"]')){const link=document.createElement("link");link.rel="stylesheet";link.href="/static/css/membership.css?v="+encodeURIComponent(assetStamp);document.head.append(link)}
    let dialog=document.querySelector(".membership-dialog-backdrop");
    if(dialog)closeDialog(dialog);
    dialog=document.createElement("div");dialog.className="membership-dialog-backdrop";
    dialog.innerHTML=`<section class="membership-dialog" role="dialog" aria-modal="true" aria-labelledby="memberCheckTitle"><div class="membership-dialog-head"><div><span class="section-kicker">INCLUDED DUE DILIGENCE</span><h2 id="memberCheckTitle">월간 확인 신청</h2></div><button class="membership-dialog-close" type="button" aria-label="닫기">×</button></div><div class="membership-dialog-body"><div class="membership-loading"><span></span>이용 가능 여부를 확인하고 있습니다.</div></div></section>`;
    document.body.append(dialog);document.body.classList.add("membership-dialog-open");
    const body=dialog.querySelector(".membership-dialog-body"),close=()=>closeDialog(dialog);
    dialog.addEventListener("click",e=>{if(e.target===dialog||e.target.closest(".membership-dialog-close"))close()});
    dialog.addEventListener("keydown",e=>{if(e.key==="Escape")close()});
    const requestToken=uuid();
    (async()=>{try{
      const data=await api("/api/membership/me");
      if(!data.logged_in){body.innerHTML=`<div class="membership-empty">신청하려면 로그인해 주세요.</div>`;return}
      if(data.status!=="active"){location.href="/membership";return}
      if(Number(data.remaining)<1){body.innerHTML=`<div class="membership-empty">이번 달 확인 횟수를 모두 사용했습니다. 사용하지 않은 횟수는 다음 달로 이월되지 않습니다.</div>`;return}
      const idLabel=property.title||property.address||"선택한 물건";
      body.innerHTML=`<p>${esc(idLabel)}에 대해 영업신고·위탁운영·관리비를 함께 확인합니다. 월 1건이며 자료·전화 확인으로 진행합니다.</p><form class="membership-form" id="memberCheckForm"><div class="membership-field"><label for="memberCheckMemo">전달 메모 (선택)</label><textarea id="memberCheckMemo" name="memo" maxlength="2000" placeholder="확인 시 참고할 사항"></textarea></div><label class="membership-consent"><input type="checkbox" name="agree_terms" required><span>선택한 물건 한 곳에 세 항목을 묶어 신청하며, 현장 방문은 포함되지 않는 점을 확인했습니다.</span></label><p class="membership-message" role="alert"></p><button class="membership-btn" type="submit">포함 확인 신청</button></form>`;
      body.querySelector("#memberCheckForm").addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget,button=form.querySelector("button"),msg=form.querySelector(".membership-message");if(!form.reportValidity())return;button.disabled=true;msg.textContent="신청을 접수하고 있습니다.";const payload={request_token:requestToken,memo:form.elements.memo.value.trim(),agree_terms:form.elements.agree_terms.checked};if(property.building_id)payload.building_id=Number(property.building_id);else payload.auction_id=Number(property.auction_id);try{await api("/api/membership/checks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});close();if(location.pathname==="/membership")load();else alert("월간 확인 신청을 접수했습니다. 보고서는 멤버십 내역에서 확인할 수 있습니다.")}catch(error){msg.textContent=error.message||"신청하지 못했습니다.";button.disabled=false}});
    }catch(error){body.innerHTML=`<div class="membership-error">${esc(error.message)}<button class="membership-btn secondary" type="button" data-dialog-retry>다시 시도</button></div>`;body.querySelector("[data-dialog-retry]")?.addEventListener("click",()=>{close();openCheckDialog(property)})}})();
  }
  window.openMembershipCheck=openCheckDialog;
  window.addEventListener("livingstay:auth",()=>{closeDialog(document.querySelector(".membership-dialog-backdrop"));if(host){snapshot=null;host.innerHTML='<div class="membership-loading"><span></span> 계정 상태를 갱신하고 있습니다.</div>';load()}});
  if(host)load();
})();