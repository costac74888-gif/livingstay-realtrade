(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const money = value => {
    if(value==null||value===""||!Number.isFinite(Number(value)))return "—";
    const n=Number(value);
    if(n>=100000000)return `${(n/100000000).toLocaleString("ko-KR",{maximumFractionDigits:2})}억`;
    return `${Math.round(n/10000).toLocaleString("ko-KR")}만`;
  };
  const pyeong = value => Number.isFinite(Number(value))&&Number(value)>0?`${Math.round(Number(value)/3.3058).toLocaleString("ko-KR")}평`:"—";
  const statusName = status => ({bidding:"진행",scheduled:"예정",failed:"유찰"})[status]||({sold:"낙찰",canceled:"취소",closed:"종료"})[status]||"확인";
  const formatDate = value => {
    if(!value)return "일정 미정";
    const date=new Date(value);
    return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat("ko-KR",{month:"numeric",day:"numeric"}).format(date);
  };
  function initList(){
    const body=$("auctionResults"); if(!body)return;
    body.addEventListener("click",event=>{
      if(event.target.closest("a,button"))return;
      const row=event.target.closest("[data-auction-href]");
      if(row)location.href=row.dataset.auctionHref;
    });
    const state={region:"",category:"",status:"",sort:"deadline",page:1,pageSize:10};
    const pairs={deadline:["deadline","deadline_desc"],appraisal:["appraisal_asc","appraisal_desc"],price:["price_asc","price_desc"],failed:["failed_asc","failed_desc"],status:["status_asc","status_desc"],category:["category_asc","category_desc"],address:["address_asc","address_desc"],area:["area_asc","area_desc"]};
    let regionTree={},sequence=0;
    const fetchPage=async()=>{
      const seq=++sequence,submitted={...state};
      body.innerHTML='<tr><td colspan="9"><div class="auction-loading" role="status">목록을 불러오는 중</div></td></tr>';
      $("auctionPagination").replaceChildren();
      const params=new URLSearchParams({page:String(submitted.page),page_size:String(submitted.pageSize),sort:submitted.sort});
      for(const [key,value] of Object.entries({region:submitted.region,category:submitted.category,status:submitted.status}))if(value)params.set(key,value);
      try{
        const response=await fetch(`/api/auctions?${params}`,{credentials:"same-origin"});
        const data=await response.json().catch(()=>({}));
        if(seq!==sequence)return;
        if(!response.ok||data.ok!==true)throw new Error(data.message||"공매 목록을 불러오지 못했습니다.");
        $("auctionTotal").textContent=Number(data.total||0).toLocaleString("ko-KR");
        $("auctionLastUpdated").textContent=data.last_success_at?formatUpdate(data.last_success_at):"마지막 성공 갱신 시각 확인 불가";
        body.innerHTML=Array.isArray(data.items)&&data.items.length?data.items.map(rowHtml).join(""):'<tr><td colspan="9"><div class="auction-empty"><strong>조건에 맞는 공매가 없습니다.</strong><span>필터를 조정해 다시 찾아보세요.</span></div></td></tr>';
        renderPages(Number(data.page||submitted.page),Number(data.pages||1));
      }catch(error){
        if(seq!==sequence)return;
        body.innerHTML=`<tr><td colspan="9"><div class="auction-error" role="alert"><strong>${esc(error.message||"네트워크 오류가 발생했습니다.")}</strong><button type="button" id="auctionRetry">다시 불러오기</button></div></td></tr>`;
        $("auctionRetry")?.addEventListener("click",fetchPage);
      }
    };
    function rowHtml(item){
      const building=item.master_building_id||item.building_id||item.building?.id;
      const query=new URLSearchParams(building?{building:String(building),tab:"auction",auction:String(item.id)}:{auction:String(item.id)});
      const href=`/?${query.toString()}`;
      const category=item.lodging_category||item.usage_name||"숙박시설";
      const address=item.address_road||item.address_jibun||item.address||"주소 확인 중";
      const ratio=item.min_bid_ratio==null?"":` <small>(${Number(item.min_bid_ratio).toLocaleString("ko-KR",{maximumFractionDigits:1})}%)</small>`;
      return `<tr class="auction-row" data-auction-href="${esc(href)}"><td><a class="auction-row-link" href="${esc(href)}"><span class="auction-status status-${esc(item.status||"unknown")}">${esc(statusName(item.status))}</span></a></td>
        <td class="auction-mobile-combined"><a class="auction-row-link" href="${esc(href)}"><strong>${esc(category)}</strong><span>${esc(address)}</span></a></td>
        <td><a class="auction-row-link auction-category" href="${esc(href)}">${esc(category)}</a></td>
        <td class="auction-address"><a class="auction-row-link" href="${esc(href)}" title="${esc(address)}">${esc(address)}</a></td>
        <td class="col-area"><a class="auction-row-link" href="${esc(href)}">${esc(pyeong(item.area_m2))}</a></td>
        <td class="col-appraisal"><a class="auction-row-link" href="${esc(href)}">${esc(money(item.appraisal_price))}</a></td>
        <td><a class="auction-row-link auction-min-price" href="${esc(href)}">${esc(money(item.min_bid_price))}${ratio}</a></td>
        <td class="col-failed"><a class="auction-row-link" href="${esc(href)}">${Number(item.failed_count||0)}회</a></td>
        <td><a class="auction-row-link auction-deadline" href="${esc(href)}">${esc(formatDate(item.bid_end_at))}</a></td></tr>`;
    }
    function formatUpdate(value){
      const date=new Date(value);if(Number.isNaN(date.getTime()))return esc(value);
      return new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(date);
    }
    function renderPages(current,total){
      const nav=$("auctionPagination");if(total<=1)return;
      const start=Math.max(1,Math.floor((current-1)/5)*5+1),end=Math.min(total,start+4);
      let html=`<button type="button" data-page="${Math.max(1,start-1)}" aria-label="이전 페이지" ${start===1?"disabled":""}>‹</button>`;
      for(let page=start;page<=end;page++)html+=`<button type="button" data-page="${page}" class="${page===current?"is-active":""}" ${page===current?'aria-current="page"':""}>${page}</button>`;
      html+=`<button type="button" data-page="${Math.min(total,end+1)}" aria-label="다음 페이지" ${end===total?"disabled":""}>›</button>`;
      nav.innerHTML=html;nav.querySelectorAll("[data-page]").forEach(button=>button.addEventListener("click",()=>{state.page=Number(button.dataset.page);fetchPage();window.scrollTo({top:0,behavior:"smooth"});}));
    }
    const sido=$("auctionSido"),sgg=$("auctionSgg"),category=$("auctionCategory"),status=$("auctionStatus");
    fetch("/api/regions",{credentials:"same-origin"}).then(r=>r.json()).then(data=>{
      const tree=data?.regions&&typeof data.regions==="object"&&!Array.isArray(data.regions)?data.regions:data;
      regionTree=tree&&typeof tree==="object"&&!Array.isArray(tree)?tree:{};
      sido.innerHTML='<option value="">전체 시·도</option>'+Object.keys(regionTree).sort().map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join("");
    }).catch(()=>{regionTree={};});
    const apply=()=>{state.region=sgg.value||sido.value;state.category=category.value;state.status=status.value;state.page=1;fetchPage();};
    sido.addEventListener("change",()=>{const children=regionTree[sido.value]?.sgg||{};sgg.innerHTML='<option value="">전체 시·군·구</option>'+Object.keys(children).sort().map(name=>{const label=name.startsWith(`${sido.value} `)?name.slice(sido.value.length).trim():name;return `<option value="${esc(name)}">${esc(label)}</option>`;}).join("");apply();});
    [sgg,category,status].forEach(select=>select.addEventListener("change",apply));
    document.querySelectorAll(".auction-order-button").forEach(button=>button.addEventListener("click",()=>{
      const choices=pairs[button.dataset.sortKey];if(!choices)return;
      state.sort=choices.includes(state.sort)?(state.sort===choices[0]?choices[1]:choices[0]):choices[0];
      document.querySelectorAll(".auction-order-button").forEach(other=>{const active=other===button;other.classList.toggle("is-active",active);other.setAttribute("aria-pressed",String(active));other.querySelector(".auction-order-arrow").textContent=active?(state.sort===choices[0]?"↑":"↓"):"";});
      state.page=1;fetchPage();
    }));
    $("auctionPageSize").addEventListener("change",event=>{state.pageSize=Number(event.target.value);state.page=1;fetchPage();});
    $("auctionReset").addEventListener("click",()=>{sido.value="";sgg.innerHTML='<option value="">전체 시·군·구</option>';category.value="";status.value="";state.sort="deadline";state.pageSize=10;$("auctionPageSize").value="10";document.querySelectorAll(".auction-order-button").forEach(button=>{const active=button.dataset.sortKey==="deadline";button.classList.toggle("is-active",active);button.setAttribute("aria-pressed",String(active));button.querySelector(".auction-order-arrow").textContent=active?"↑":"";});apply();});
    fetchPage();
  }
  initList();
})();