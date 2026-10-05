(function(){
  "use strict";
  const esc=v=>String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt=v=>v==null||v===""?"—":esc(v);
  const money=v=>`${Number(v||0).toLocaleString("ko-KR")}원`;
  const dates=v=>{if(!v)return"—";const d=new Date(v);return Number.isNaN(d.getTime())?fmt(v):new Intl.DateTimeFormat("ko-KR",{dateStyle:"medium",timeStyle:"short"}).format(d)};
  const statusText={pending:"입금 대기",approved:"승인",rejected:"반려",revoked:"이용 취소",received:"접수",investigating:"확인 중",reported:"보고 완료"};
  let page=1,status="pending",checkPage=1,checkStatus="",checkMeta={},checks=[],selectedCheck=null,seq=0;
  async function api(url,options){const r=await fetch(url,Object.assign({credentials:"same-origin",cache:"no-store",headers:{}},options||{}));if(r.status===401){location.href="/admin/login";throw new Error("관리자 로그인 후 다시 시도해 주세요.")}const d=await r.json().catch(()=>({}));if(!r.ok||d.ok!==true)throw new Error(d.message||"요청을 처리하지 못했습니다.");return d}
  function css(){if(document.getElementById("am-style"))return;const l=document.createElement("link");l.id="am-style";l.rel="stylesheet";l.href="/static/css/admin-membership.css";document.head.append(l)}
  function activate(){
    css();document.querySelectorAll(".admin-menu-item").forEach(b=>b.classList.toggle("is-active",b.dataset.menu==="admin-membership"));
    const grid=document.getElementById("grid");if(!grid)return;
    grid.innerHTML=`<div class="am-page"><header class="am-head"><div><span>HOME &amp; STAY · MEMBER DESK</span><h2>멤버십 운영</h2><p>수동 송금 승인과 월간 확인 보고서를 관리합니다.</p></div><button class="am-button am-light" id="amReload">새로고침</button></header>
      <div class="am-price-note"><strong>정액 월 29,000원</strong><span>승인 버튼은 실제 송금 29,000원 입금 확인 후에만 사용하세요. 승인은 결제 신청만으로 자동 처리되지 않습니다.</span></div>
      <section class="am-card"><div class="am-card-head"><div><h3>멤버십 신청</h3><p>신청 시점의 입금 계좌 스냅샷을 확인하세요.</p></div><select id="amStatus" aria-label="결제 신청 상태"><option value="pending">입금 대기</option><option value="approved">승인</option><option value="rejected">반려</option><option value="revoked">이용 취소</option></select></div><div id="amPayments"><div class="am-loading">신청을 불러오는 중입니다.</div></div></section>
      <section class="am-card"><div class="am-card-head"><div><h3>월간 확인 이력</h3><p>전체 신청 · 결과와 보고서를 편집할 수 있습니다.</p></div><select id="amCheckStatus" aria-label="확인 진행 상태"><option value="">전체 진행 상태</option><option value="received">접수</option><option value="investigating">확인 중</option><option value="reported">보고 완료</option></select><span class="am-count" id="amCheckCount"></span></div><div id="amChecks"><div class="am-loading">확인 신청을 불러오는 중입니다.</div></div></section>
      <section id="amEditor"></section></div>`;
    grid.querySelector("#amStatus").value=status;
    grid.querySelector("#amStatus").addEventListener("change",e=>{status=e.target.value;page=1;loadAll()});
    grid.querySelector("#amCheckStatus").value=checkStatus;
    grid.querySelector("#amCheckStatus").addEventListener("change",e=>{checkStatus=e.target.value;checkPage=1;loadAll()});
    grid.querySelector("#amReload").addEventListener("click",loadAll);
    loadAll();
  }
  window.showAdminMembership=activate;
  if(location.hash==="#admin-membership")activate();
  async function loadAll(){const current=++seq;await loadPayments(current)}
  async function loadPayments(current=seq){
    const host=document.getElementById("amPayments");if(!host)return;host.innerHTML='<div class="am-loading">신청을 불러오는 중입니다.</div>';
    try{const d=await api(`/api/admin/membership/requests?page=${page}&status=${encodeURIComponent(status)}&check_page=${checkPage}&check_status=${encodeURIComponent(checkStatus)}`);if(current!==seq||!host.isConnected)return;checks=Array.isArray(d.checks)?d.checks:[];checkMeta=d;renderPayments(d);renderChecks(checks)}
    catch(e){host.innerHTML=`<div class="am-error">${esc(e.message)} <button class="am-button am-light" data-retry>다시 시도</button></div>`;host.querySelector("[data-retry]")?.addEventListener("click",()=>loadPayments())}
  }
  function renderPayments(d){
    const host=document.getElementById("amPayments");if(!host)return;const rows=Array.isArray(d.payments)?d.payments:[];
    if(!rows.length){host.innerHTML='<div class="am-empty">해당 상태의 신청이 없습니다.</div>';return}
    host.innerHTML=`<div class="am-grid-list">${rows.map(p=>`<article class="am-request"><header><div><span class="am-kicker">${esc(p.request_no||"REQUEST")}</span><h4>${fmt(p.member_name)} <small>${fmt(p.email)}</small></h4></div><b class="am-state">${esc(statusText[p.status]||p.status)}</b></header>
      <div class="am-payment-data"><div><small>입금자명</small><strong>${fmt(p.depositor_name)}</strong></div><div><small>금액</small><strong>${money(p.amount)}</strong></div><div><small>접수</small><strong>${dates(p.created_at)}</strong></div></div>
      <div class="am-snapshot"><b>신청 당시 계좌 스냅샷</b><span>${fmt(p.bank?.bank_name)} ${fmt(p.bank?.bank_account)}</span><span>예금주 ${fmt(p.bank?.bank_holder)}</span></div>
      ${p.admin_note?`<p class="am-note">${esc(p.admin_note)}</p>`:""}
      <div class="am-actions">${p.status==="pending"?`<button class="am-button am-approve" data-payment-action="approved" data-id="${esc(p.id)}">송금 확인 후 승인</button><button class="am-button am-light" data-payment-action="rejected" data-id="${esc(p.id)}">반려</button>`:""}
      ${p.status==="approved"?`<button class="am-button am-danger" data-payment-action="revoked" data-id="${esc(p.id)}">이용 취소</button>`:""}</div></article>`).join("")}</div>
      <div class="am-pagination"><button class="am-button am-light" data-page="-1" ${Number(d.page||1)<=1?"disabled":""}>이전</button><span>${Number(d.page||1)} · 총 ${Number(d.total||0).toLocaleString("ko-KR")}건</span><button class="am-button am-light" data-page="1" ${Number(d.page||1)>=Math.max(1,Math.ceil(Number(d.total||0)/Number(d.page_size||30)))?"disabled":""}>다음</button></div>`;
    host.querySelectorAll("[data-payment-action]").forEach(b=>b.addEventListener("click",()=>changePayment(b.dataset.id,b.dataset.paymentAction)));
    host.querySelectorAll("[data-page]").forEach(b=>b.addEventListener("click",()=>{page+=Number(b.dataset.page);loadPayments()}));
  }
  async function changePayment(id,next){
    let note="";
    if(next==="approved"&&!confirm("은행 거래 내역에서 이 신청자의 실제 29,000원 송금을 확인했습니까? 확인한 경우에만 승인되며 승인 후 한 달 이용 기간이 시작됩니다."))return;
    if(next==="revoked"&&!confirm("멤버십 이용을 취소할까요? 은행 환불은 자동으로 진행되지 않습니다. 별도로 환불 처리한 뒤 기록해 주세요."))return;
    if(next!=="approved"){note=prompt(next==="revoked"?"이용 취소 사유 (환불은 별도 처리)":"반려 사유 또는 관리자 메모","")??null;if(note===null)return}
    try{await api(`/api/admin/membership/payments/${encodeURIComponent(id)}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:next,note})});await loadAll()}catch(e){alert(e.message||"상태를 변경하지 못했습니다.")}
  }
  function renderChecks(rows){
      const host=document.getElementById("amChecks");if(!host)return;document.getElementById("amCheckCount").textContent=`전체 ${Number(checkMeta.checks_total||0)}건`;
    if(!rows.length){host.innerHTML='<div class="am-empty">최근 확인 신청이 없습니다.</div>';return}
    host.innerHTML=`<div class="am-table-wrap"><table class="am-table"><thead><tr><th>접수 / 번호</th><th>회원</th><th>대상 물건</th><th>상태</th><th>결과 보고서</th><th></th></tr></thead><tbody>${rows.map(c=>`<tr><td>${dates(c.created_at)}<br><b>${fmt(c.request_no)}</b></td><td>${fmt(c.member_name)}<br>${fmt(c.email)}</td><td>${fmt(c.title)}<br>${fmt(c.address)}</td><td><span class="am-state">${esc(statusText[c.status]||c.status)}</span></td><td>${c.report?esc(String(c.report).slice(0,110)):"보고서 미작성"}</td><td><button type="button" class="am-text-button" data-check-id="${esc(c.id)}">열기 · 편집</button></td></tr>`).join("")}</tbody></table></div>
      <div class="am-pagination"><button class="am-button am-light" data-check-page="-1" ${checkPage<=1?"disabled":""}>이전</button><span>${checkPage} / ${Math.max(1,Math.ceil(Number(checkMeta.checks_total||0)/30))}</span><button class="am-button am-light" data-check-page="1" ${checkPage>=Math.max(1,Math.ceil(Number(checkMeta.checks_total||0)/30))?"disabled":""}>다음</button></div>`;
    host.querySelectorAll("[data-check-id]").forEach(b=>b.addEventListener("click",()=>showCheckEditor(rows.find(c=>String(c.id)===b.dataset.checkId))));
    host.querySelectorAll("[data-check-page]").forEach(b=>b.addEventListener("click",()=>{checkPage+=Number(b.dataset.checkPage);loadAll()}));
  }
  function showCheckEditor(item){
    if(!item)return;selectedCheck=item;const host=document.getElementById("amEditor");
    const select=(key,label)=>`<label class="am-field">${label}<select name="${key}"><option value="need_check" ${item[key]==="need_check"?"selected":""}>미확인 / 자료 대기</option><option value="ok" ${item[key]==="ok"?"selected":""}>확인 완료</option><option value="issue" ${item[key]==="issue"?"selected":""}>확인사항 있음</option></select></label>`;
    host.innerHTML=`<section class="am-card am-editor"><div class="am-card-head"><div><h3>확인 결과 편집</h3><p>${fmt(item.member_name)} · ${fmt(item.title)} · ${fmt(item.request_no)}</p></div><button class="am-button am-light" type="button" data-editor-close>닫기</button></div>
      <p class="am-note">회원 요청사항: ${esc(item.memo||"없음")}</p>
      <form id="amCheckForm" class="am-editor-form"><div class="am-result-grid">${select("business_report","영업신고")}${select("operation_succession","위탁운영 승계")}${select("fee_arrears","관리비 체납")}</div>
      <label class="am-field">보고서<textarea name="report" rows="7" maxlength="10000">${esc(item.report||"")}</textarea></label>
      <label class="am-field">진행 상태<select name="status"><option value="received" ${item.status==="received"?"selected":""}>접수</option><option value="investigating" ${item.status==="investigating"?"selected":""}>확인 중</option><option value="reported" ${item.status==="reported"?"selected":""}>보고 완료</option></select></label>
      <p class="am-form-message" role="status"></p><button class="am-button am-approve" type="submit">결과 저장</button></form></section>`;
    host.querySelector("[data-editor-close]").addEventListener("click",()=>{host.innerHTML=""});
    host.querySelector("#amCheckForm").addEventListener("submit",saveCheck);
    host.scrollIntoView({behavior:"smooth",block:"start"});
  }
  async function saveCheck(event){
    event.preventDefault();const form=event.currentTarget,item=selectedCheck,button=form.querySelector("[type=submit]"),msg=form.querySelector(".am-form-message");button.disabled=true;msg.textContent="저장 중입니다.";
    const payload={status:form.elements.status.value,business_report:form.elements.business_report.value,operation_succession:form.elements.operation_succession.value,fee_arrears:form.elements.fee_arrears.value,report:form.elements.report.value.trim()};
    try{await api(`/api/admin/membership/checks/${encodeURIComponent(item.id)}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});msg.textContent="저장했습니다.";await loadAll();const updated=checks.find(c=>String(c.id)===String(item.id));if(updated)showCheckEditor(updated)}catch(e){msg.textContent=e.message||"저장하지 못했습니다.";button.disabled=false}
  }
})();