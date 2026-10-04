(function(){
  "use strict";
  const generations=new WeakMap();
  const esc=value=>String(value==null?"":value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const safeUrl=value=>{try{const url=new URL(value,location.origin);return ["http:","https:"].includes(url.protocol)?url.href:"";}catch(_){return "";}};
  const money=value=>value==null||value===""||!Number.isFinite(Number(value))?"확인 필요":Number(value)>=100000000?`${(Number(value)/100000000).toLocaleString("ko-KR",{maximumFractionDigits:2})}억 원`:`${Math.round(Number(value)/10000).toLocaleString("ko-KR")}만 원`;
  const date=value=>{if(!value)return "일정 미정";const parsed=new Date(value);return Number.isNaN(parsed.getTime())?esc(value):new Intl.DateTimeFormat("ko-KR",{year:"numeric",month:"numeric",day:"numeric"}).format(parsed);};
  const statusText=value=>({bidding:"입찰중",scheduled:"입찰예정",failed:"유찰",sold:"낙찰",canceled:"취소",closed:"종료"})[value]||"상태 확인";
  const sourceText=value=>({listing:"매물사진",auction:"공매·온비드",tourapi:"호텔·TourAPI",gocamping:"캠핑·고캠핑",google_streetview:"거리뷰·구글",streetview:"거리뷰·구글",operator:"운영자 등록"})[value]||"건물 사진";
  const valid= (host,seq,isCurrent)=>generations.get(host)===seq&&(!isCurrent||isCurrent());
  window.auctionListReturnUrl=function(){
    const candidate=new URLSearchParams(location.search).get("auction_list")||document.referrer;
    try{
      const url=new URL(candidate,location.origin);
      return url.origin===location.origin&&url.pathname==="/auctions"&&!url.username&&!url.password
        ?url.pathname+url.search:null;
    }catch(_){return null;}
  };
  window.returnFromAuctionDetail=function(){
    const list=window.auctionListReturnUrl();
    if(list){location.assign(list);return;}
    if(history.length>1){history.back();return;}
    location.assign("/auctions");
  };
  function ensureBackButton(){
    const header=document.getElementById("bHeaderCard")||document.querySelector(".auction-panel-unmatched-heading");
    if(!header)return;
    let button=header.querySelector("[data-auction-panel-back],#auctionBackToMap");
    if(!button){button=document.createElement("button");button.type="button";header.prepend(button);}
    button.className="auction-panel-back";
    button.dataset.auctionPanelBack="";
    button.textContent=window.auctionListReturnUrl()?"← 공매목록으로":"← 이전 화면";
    button.onclick=window.returnFromAuctionDetail;
  }
  window.renderUnmatchedAuctionDetail=function(host,item){
    if(!host||!item)return;
    const facts=[
      ["소재지",item.address_road||item.address_jibun],
      ["용도",item.usage_name||item.lodging_category],
      ["관리번호",item.management_no],
      ["대지면적",formatArea(item.land_area_m2)],
      ["건물면적",formatArea(item.building_area_m2)]
    ];
    host.innerHTML=`<section class="side-card auction-panel-unmatched-heading"><button type="button" id="auctionBackToMap" class="side-more">← 지도로</button><h2>${esc(item.title||item.usage_name||"공매 물건 상세")}</h2><p>${esc(item.address_road||item.address_jibun||"소재지 확인 필요")}</p><p class="auction-panel-unmatched">공매 정보에 매칭된 건물 정보가 없습니다. 실제 건물의 존재 여부는 확인되지 않았습니다.</p></section><div class="b-inline-tabs auction-panel-unmatched-tabs" role="tablist" aria-label="공매 물건 상세 정보"><button type="button" class="b-detail-tab" id="bTabProperty" data-panel="property" role="tab" aria-controls="bPropertyPanel" aria-selected="false" tabindex="-1">부동산정보</button><button type="button" class="b-detail-tab" id="bTabOperations" data-panel="operations" role="tab" aria-controls="bOperationsPanel" aria-selected="false" tabindex="-1">운영정보</button><button type="button" class="b-detail-tab active" id="bTabAuctions" data-panel="auctions" role="tab" aria-controls="bAuctionPanel" aria-selected="true" tabindex="0">공매정보</button></div><section id="bPropertyPanel" class="b-detail-panel" role="tabpanel" aria-labelledby="bTabProperty" hidden><section class="auction-panel-section"><div class="auction-panel-section-title"><span>01</span><h3>공매 자료에 확인된 부동산 정보</h3></div><dl class="auction-panel-facts">${facts.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value||"자료에 없음")}</dd></div>`).join("")}</dl></section><p class="auction-panel-unmatched">건축물대장과 실거래 자료는 연결되어 있지 않습니다. 공매 자료에 없는 정보는 확인된 사실로 표시하지 않습니다.</p></section><section id="bOperationsPanel" class="b-detail-panel" role="tabpanel" aria-labelledby="bTabOperations" hidden><section class="auction-panel-section"><div class="auction-panel-section-title"><span>02</span><h3>운영정보</h3></div><div class="auction-panel-content"><p class="auction-panel-unmatched">운영정보를 확인할 수 없습니다. 이 화면에 연결된 영업신고 자료가 없으며, 이는 미신고 또는 폐업을 의미하지 않습니다.</p></div></section></section><section id="bAuctionPanel" class="b-detail-panel" role="tabpanel" aria-labelledby="bTabAuctions"></section>`;
    ensureBackButton();
    const tabs=Array.from(host.querySelectorAll('[role="tab"]'));
    const panels={property:host.querySelector("#bPropertyPanel"),operations:host.querySelector("#bOperationsPanel"),auctions:host.querySelector("#bAuctionPanel")};
    const activate=tab=>{
      const selected=tab.dataset.panel;
      tabs.forEach(candidate=>{
        const active=candidate===tab;
        candidate.classList.toggle("active",active);
        candidate.setAttribute("aria-selected",String(active));
        candidate.tabIndex=active?0:-1;
      });
      Object.entries(panels).forEach(([name,panel])=>{if(panel)panel.hidden=name!==selected;});
    };
    tabs.forEach(tab=>{
      tab.addEventListener("click",()=>activate(tab));
      tab.addEventListener("keydown",event=>{
        if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
        event.preventDefault();
        const index=tabs.indexOf(tab);
        const next=event.key==="Home"?0:event.key==="End"?tabs.length-1:(index+(event.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;
        tabs[next]?.focus();
        if(tabs[next])activate(tabs[next]);
      });
    });
    activate(host.querySelector('#bTabAuctions'));
  };
  function formatArea(value){
    if(value==null||value===""||!Number.isFinite(Number(value)))return "";
    return `${Number(value).toLocaleString("ko-KR",{maximumFractionDigits:2})}㎡`;
  }
  window.renderAuctionPanel=async function(host,items,options){
    if(!host)return;
    const opts=options||{}, list=(Array.isArray(items)?items:[]).filter(Boolean);
    const seq=(generations.get(host)||0)+1;generations.set(host,seq);
    if(!list.length){host.innerHTML='<div class="auction-panel-empty">연결된 공매 정보가 없습니다.</div>';return;}
    const ordered=[...list].sort((a,b)=>activeRank(a)-activeRank(b));
    let selected=ordered.find(item=>String(item.id)===String(opts.selectedId))||ordered[0];
    const choose=async item=>{
      selected=item;
      if(typeof opts.onSelect==="function"){try{await opts.onSelect(item);}catch(_){}}
      if(!valid(host,seq,opts.isCurrent))return;
      await render();
    };
    const render=async()=>{
      if(!valid(host,seq,opts.isCurrent))return;
      const currentId=String(selected.id);
      host.innerHTML=`<section class="auction-panel" data-auction-panel><header class="auction-panel-heading"><div><span class="auction-panel-kicker">PUBLIC AUCTION EVIDENCE</span><h2>공매정보</h2></div>${ordered.length>1?`<label class="auction-panel-picker"><span>공매 물건 선택</span><select data-auction-select aria-label="공매 물건 선택">${ordered.map(item=>`<option value="${esc(item.id)}" ${String(item.id)===currentId?"selected":""}>${activeRank(item)===0?"진행 우선 · ":""}${esc(item.title||item.usage_name||item.lodging_category||`공매 ${item.id}`)}${item.round_no?` · ${esc(item.round_no)}회차`:""}</option>`).join("")}</select></label>`:""}</header><div class="auction-panel-content"><div class="auction-panel-loading" role="status"><i></i><span>온비드 상세와 건물 증빙을 불러오는 중</span></div></div></section>`;
      host.querySelector("[data-auction-select]")?.addEventListener("change",event=>{const next=ordered.find(item=>String(item.id)===event.target.value);if(next)void choose(next);});
      try{
        const response=await fetch(`/api/auctions/${encodeURIComponent(selected.id)}`,{credentials:"same-origin"});
        const data=await response.json().catch(()=>({}));
        if(!response.ok||data.ok!==true||!data.item)throw new Error(data.message||"공매 정보를 불러오지 못했습니다.");
        let building=data.building||null, buildingPhotos=[];
        if(data.item.master_building_id){
          try{const photoResponse=await fetch(`/api/building/${encodeURIComponent(data.item.master_building_id)}/auctions`,{credentials:"same-origin"});const photoData=await photoResponse.json().catch(()=>({}));if(photoResponse.ok&&photoData.ok)buildingPhotos=Array.isArray(photoData.photos)?photoData.photos:[];}catch(_){}
        }
        if(!valid(host,seq,opts.isCurrent)||String(selected.id)!==currentId)return;
        const item=data.item;building=building||data.building||null;
        if(building)ensureBackButton();
        const priority={listing:0,auction:1,tourapi:2,gocamping:3,google_streetview:4,streetview:4,operator:5};
        const allPhotos=[...(buildingPhotos||[]),...(data.photos||[])].filter(photo=>photo&&safeUrl(photo.url)).sort((a,b)=>(priority[a.source]??6)-(priority[b.source]??6)||Number(a.sort_order||0)-Number(b.sort_order||0));
        const seen=new Set(),photos=allPhotos.filter(photo=>{const src=safeUrl(photo.url);if(seen.has(src))return false;seen.add(src);return true;});
        const title=building?.building_name||item.title||item.usage_name||item.lodging_category||"숙박시설 공매";
        const address=item.address_road||item.address_jibun||building?.road_address||building?.jibun_address||"주소 확인 중";
        const category=item.lodging_category||item.usage_name||"숙박시설";
        const gallery=photos.length?`<div class="auction-panel-gallery"><div class="auction-panel-gallery-track">${photos.map((photo,index)=>`<figure class="auction-panel-photo"><img src="${esc(safeUrl(photo.url))}" alt="${esc(title)} 사진 ${index+1}" loading="${index<2?"eager":"lazy"}" data-photo-index="${index}"><figcaption>${esc(sourceText(photo.source))}</figcaption></figure>`).join("")}</div><span class="auction-panel-photo-count">1 / ${photos.length}</span></div>`:'<div class="auction-panel-no-photo">등록된 사진이 없습니다</div>';
        const rounds=Array.isArray(data.rounds)?data.rounds:[];
        const roundsHtml=rounds.length?`<div class="auction-panel-rounds"><h3>회차별 최저가</h3>${rounds.map(round=>`<div class="auction-panel-round ${round.is_current?"is-current":""}"><b>${Number(round.round_no)||"—"}회차${round.is_current?" · 현재":round.is_upcoming?" · 예정":""}</b><span>${round.result_at?`개찰 ${date(round.result_at)}`:`${date(round.bid_start_at)} – ${date(round.bid_end_at)}`} · ${esc(round.result||(round.is_current?"진행 회차":"결과 확인"))}</span><strong>${esc(money(round.min_bid_price))}</strong></div>`).join("")}</div>`:"";
        const link=safeUrl(item.detail_url);
        const placeFacts=[[ "용도",category ],["상태",statusText(item.status)],["소재지",address],["면적",item.area_m2?`${Number(item.area_m2).toLocaleString("ko-KR",{maximumFractionDigits:1})}㎡ · ${Math.round(Number(item.area_m2)/3.3058)}평`:"확인 필요"],["감정가",money(item.appraisal_price)],["최저입찰가",`${money(item.min_bid_price)}${item.min_bid_ratio==null?"":` · ${Number(item.min_bid_ratio).toLocaleString("ko-KR",{maximumFractionDigits:1})}%`}`],["입찰기간",`${date(item.bid_start_at)} – ${date(item.bid_end_at)}`],["회차 · 유찰",`${item.round_no||"—"}회차 · ${Number(item.failed_count||0)}회`],["처분방식",item.disposal_method||"정보 없음"],["공고기관",item.notice_org||"정보 없음"]];
        const content=host.querySelector(".auction-panel-content");
        content.innerHTML=`${gallery}<section class="auction-panel-section auction-panel-general"><div class="auction-panel-section-title"><span>01</span><h3>공매 일반정보</h3></div><div class="auction-panel-title"><div><span class="auction-status status-${esc(item.status||"unknown")}">${esc(statusText(item.status))}</span><h4>${esc(title)}</h4><p>${esc(address)} · ${esc(category)}</p></div></div><dl class="auction-panel-facts">${placeFacts.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>${roundsHtml}${link?`<a class="auction-panel-onbid" href="${esc(link)}" target="_blank" rel="noopener noreferrer">온비드 원문 공고 보기 <span aria-hidden="true">↗</span></a>`:'<div class="auction-panel-onbid is-disabled" aria-disabled="true">온비드 원문 링크가 제공되지 않았습니다</div>'}</section><section class="auction-panel-survey-section" aria-label="투자분석 및 현황조사"><div data-auction-survey-slot></div></section><button type="button" class="auction-panel-favorite" data-auction-favorite>관심 등록 · 알림</button>${!building?'<p class="auction-panel-unmatched">연결된 건물 정보가 없습니다. 공매 정보와 제공기관 원문을 기준으로 확인해 주세요.</p>':""}<p class="auction-panel-disclaimer">공매 정보 출처: 한국자산관리공사 온비드. 입찰 전 원문 공고와 권리관계를 반드시 확인하세요. 홈앤스테이는 입찰을 대행하거나 결과를 보장하지 않습니다.</p><div class="auction-panel-lightbox" hidden role="dialog" aria-modal="true" aria-label="공매 사진 크게 보기"><button type="button" data-lightbox-close aria-label="닫기">×</button><button type="button" data-lightbox-prev aria-label="이전 사진">‹</button><img alt=""><button type="button" data-lightbox-next aria-label="다음 사진">›</button><span data-lightbox-count></span></div>`;
        // 탭을 바꿔도 사진은 상세 상단에 유지한다.
        const header=document.getElementById("bHeaderCard")||document.querySelector(".auction-panel-unmatched-heading");
        if(header){
          let photoHeader=header.querySelector("#auctionDetailPhotoHeader");
          if(!photoHeader){
            photoHeader=document.createElement("div");photoHeader.id="auctionDetailPhotoHeader";
            const back=header.querySelector("[data-auction-panel-back]");
            if(back)back.after(photoHeader);else header.prepend(photoHeader);
          }
          // 기존 관심저장·공유·뒤로가기의 실제 버튼과 이벤트를 보존한다.
          const actions=Array.from(header.querySelectorAll(".bld-photo-actions"));
          photoHeader.replaceChildren();
          const picture=content.querySelector(".auction-panel-gallery,.auction-panel-no-photo");
          const lightbox=content.querySelector(".auction-panel-lightbox");
          if(picture)photoHeader.appendChild(picture);
          if(lightbox)photoHeader.appendChild(lightbox);
          actions.forEach(action=>photoHeader.appendChild(action));
          const originalPhotos=header.querySelector(".bld-photo-shell");
          if(originalPhotos)originalPhotos.hidden=true;
          bindGallery(photoHeader,photos);
        }else bindGallery(content,photos);
        bindFavorite(content,item,building);
        if(typeof window.mountAuctionSurveyDetail==="function")window.mountAuctionSurveyDetail(content.querySelector("[data-auction-survey-slot]"),item.id);
      }catch(error){
        if(!valid(host,seq,opts.isCurrent)||String(selected.id)!==currentId)return;
        const content=host.querySelector(".auction-panel-content");
        if(content)content.innerHTML=`<div class="auction-panel-error" role="alert"><strong>${esc(error.message||"상세 정보를 불러오지 못했습니다.")}</strong><button type="button" data-panel-retry>다시 시도</button></div>`;
        host.querySelector("[data-panel-retry]")?.addEventListener("click",()=>void render());
      }
    };
    await render();
  };
  function activeRank(item){return ["bidding","scheduled","failed"].includes(String(item.status||"").toLowerCase())?0:1;}
  function bindGallery(host,photos){
    let box=host.querySelector(".auction-panel-lightbox");if(!box||!photos.length)return;
    // Native dialog enters the browser top layer, above the map/header stacking contexts.
    if(box.localName!=="dialog"){
      const dialog=document.createElement("dialog");
      Array.from(box.attributes).forEach(attribute=>dialog.setAttribute(attribute.name,attribute.value));
      dialog.append(...box.childNodes);box.replaceWith(dialog);box=dialog;
    }
    let index=0,previousFocus=null;
    const show=next=>{index=(next+photos.length)%photos.length;const image=box.querySelector("img");image.src=safeUrl(photos[index].url);image.alt=`공매 사진 ${index+1}`;box.querySelector("[data-lightbox-count]").textContent=`${index+1} / ${photos.length}`;};
    const close=()=>{if(box.open)box.close();box.hidden=true;if(previousFocus?.isConnected)previousFocus.focus();};
    host.querySelectorAll("[data-photo-index]").forEach(image=>image.addEventListener("click",()=>{previousFocus=image;show(Number(image.dataset.photoIndex));box.hidden=false;box.showModal();box.querySelector("[data-lightbox-close]").focus();}));
    box.addEventListener("cancel",event=>{event.preventDefault();close();});
    box.querySelector("[data-lightbox-close]").addEventListener("click",close);
    box.querySelector("[data-lightbox-prev]").addEventListener("click",()=>show(index-1));
    box.querySelector("[data-lightbox-next]").addEventListener("click",()=>show(index+1));
    box.addEventListener("click",event=>{if(event.target===box)close();});
    box.addEventListener("keydown",event=>{if(event.key==="Escape")close();if(event.key==="ArrowLeft")show(index-1);if(event.key==="ArrowRight")show(index+1);});
  }
  async function bindFavorite(host,item,building){
    const button=host.querySelector("[data-auction-favorite]");if(!button)return;
    if(!building){button.disabled=true;button.title="매칭된 건물 정보가 없어 관심 알림을 설정할 수 없습니다.";return;}
    const buildingId=building.id||item.master_building_id;
    const sync=async()=>{if(!window.__livingstayLoggedIn)return;try{const response=await fetch(`/api/building/${encodeURIComponent(buildingId)}/auction-watch`,{credentials:"same-origin"});const data=await response.json();if(response.ok&&data.ok){button.dataset.watchEnabled=String(Boolean(data.enabled));button.textContent=data.enabled?"공매 알림 해제":"관심 등록 · 알림";button.classList.toggle("is-saved",Boolean(data.enabled));}}catch(_){}};
    void sync();window.addEventListener("livingstay:auth",sync);
    button.addEventListener("click",async()=>{
      if(window.__livingstayAccountType&&window.__livingstayAccountType!=="user"){window.alert("관심저장은 일반회원 전용 기능입니다.");return;}
      if(!window.__livingstayLoggedIn){if(typeof window.livingstayOpenLogin==="function")window.livingstayOpenLogin();else location.href="/?login=1";return;}
      button.disabled=true;
      try{
        if(button.dataset.watchEnabled==="true"){
          const response=await fetch(`/api/building/${encodeURIComponent(buildingId)}/auction-watch`,{method:"DELETE",credentials:"same-origin"}),data=await response.json();
          if(!response.ok||!data.ok)throw new Error(data.message||"알림 해제에 실패했습니다.");
          button.dataset.watchEnabled="false";button.textContent="관심 등록 · 알림";button.classList.remove("is-saved");
        }else{
          const payload={building_name:building.building_name||item.title||item.usage_name||"숙박시설",address:building.road_address||building.jibun_address||item.address_road||item.address_jibun||"",building_id:buildingId};
          if(!payload.address)throw new Error("건물 주소를 확인할 수 없습니다.");
          const save=await fetch("/api/favorites/mine",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}),result=await save.json().catch(()=>({}));
          if(!save.ok||!result.ok)throw new Error(result.message||"관심단지 등록에 실패했습니다.");
          const watch=await fetch(`/api/building/${encodeURIComponent(buildingId)}/auction-watch`,{method:"POST",credentials:"same-origin"}),watched=await watch.json().catch(()=>({}));
          if(!watch.ok||!watched.ok)throw new Error("관심단지는 저장했지만 공매 알림 설정에 실패했습니다.");
          button.dataset.watchEnabled="true";button.textContent="공매 알림 해제";button.classList.add("is-saved");
        }
      }catch(error){window.alert(error.message||"요청에 실패했습니다.");}
      button.disabled=false;
    });
  }
})();