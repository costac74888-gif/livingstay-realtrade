(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const safeImageUrl = value => {
    if (!value || typeof value !== "string") return "";
    try {
      const url = new URL(value, location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) { return ""; }
  };
  const money = value => {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "확인 필요";
    const n = Math.round(Number(value));
    if (n >= 100000000) {
      return `${(Math.round(n / 10000000) / 10).toLocaleString("ko-KR",{maximumFractionDigits:1})}억`;
    }
    return `${Math.round(n / 10000).toLocaleString("ko-KR")}만원`;
  };
  const areaText = value => {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "면적 미확인";
    const sqm = Number(value), pyeong = Math.round(sqm / 3.3058);
    return `${sqm.toLocaleString("ko-KR",{maximumFractionDigits:1})}㎡ · ${pyeong}평`;
  };
  const dateText = value => {
    if (!value) return "일정 미정";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return esc(value);
    return new Intl.DateTimeFormat("ko-KR",{month:"numeric",day:"numeric"}).format(d);
  };
  const dday = value => {
    if (!value) return "일정 미정";
    const date = new Date(value), today = new Date();
    if (Number.isNaN(date.getTime())) return "일정 미정";
    date.setHours(0,0,0,0); today.setHours(0,0,0,0);
    const days = Math.ceil((date - today) / 86400000);
    return days < 0 ? "마감" : days === 0 ? "오늘 마감" : `D-${days}`;
  };
  const STATUS = {scheduled:"입찰예정",bidding:"입찰중",failed:"유찰",sold:"낙찰",canceled:"취소",closed:"종료"};
  const SOURCE = {listing:"매물사진",auction:"공매·온비드",tourapi:"호텔·TourAPI",gocamping:"캠핑·고캠핑",google_streetview:"거리뷰·구글",streetview:"거리뷰·구글",operator:"운영자 등록"};
  const kindClass = value => `kind-${String(value || "기타").replace(/[^가-힣A-Za-z0-9_-]/g,"")}`;

  function initList() {
    const results = $("auctionResults");
    if (!results) return;
    const state = {region:"",category:"",kind:"",status:"",sort:"deadline",page:1};
    const sortLabels = {deadline:"마감 임박순",discount:"할인율순",new:"신규순",ratio_asc:"최저가율 낮은순",ratio_desc:"최저가율 높은순",failed_asc:"유찰 횟수 적은순",failed_desc:"유찰 횟수 많은순"};
    const statusLabels = {bidding:"입찰중",scheduled:"입찰예정",failed:"유찰",sold:"낙찰",canceled:"취소",closed:"종료"};
    let regionTree = {};
    let fetchSequence = 0;
    const fetchPage = async () => {
      const sequence = ++fetchSequence;
      const submitted = {...state};
      results.innerHTML = '<div class="auction-loading" role="status" aria-label="불러오는 중"><i></i><i></i><i></i></div>';
      $("auctionPagination").replaceChildren();
      const params = new URLSearchParams({page:String(submitted.page),sort:submitted.sort});
      Object.entries({region:submitted.region,category:submitted.category,kind:submitted.kind,status:submitted.status}).forEach(([k,v])=>{if(v!==""&&v!=null)params.set(k,String(v));});
      try {
        const response = await fetch(`/api/auctions?${params}`, {credentials:"same-origin"});
        const data = await response.json().catch(()=>({}));
        if (sequence !== fetchSequence) return;
        if (!response.ok || data.ok !== true) throw new Error(data.message || "공매 목록을 불러오지 못했습니다.");
        $("auctionTotal").textContent = Number(data.total || 0).toLocaleString("ko-KR");
        if (!Array.isArray(data.items) || !data.items.length) {
          results.innerHTML = '<div class="auction-empty"><strong>조건에 맞는 숙박시설 공매가 없습니다.</strong><span>조건을 넓혀 보세요.</span></div>';
        } else {
          results.innerHTML = data.items.map(cardHtml).join("");
        }
        renderPages(Number(data.page || submitted.page), Number(data.pages || 1));
        $("auctionFilterSummary").textContent = [
          submitted.region || "전국", submitted.category || "모든 숙박 용도", submitted.kind || "모든 공매 종류",
          submitted.status ? statusLabels[submitted.status] : "모든 진행 상태", sortLabels[submitted.sort]
        ].join(" · ");
      } catch (error) {
        if (sequence !== fetchSequence) return;
        results.innerHTML = `<div class="auction-error" role="alert"><strong>${esc(error.message || "네트워크 오류가 발생했습니다.")}</strong><button type="button" id="auctionRetry">다시 불러오기</button></div>`;
        $("auctionRetry")?.addEventListener("click",fetchPage);
      }
    };
    function cardHtml(item) {
      const href = `/auctions/${encodeURIComponent(item.id)}`;
      const image = safeImageUrl(item.thumbnail_url);
      const status = STATUS[item.status] || "상태 확인";
      const place = item.address_road || item.address_jibun || "주소 확인 중";
      const title = [item.title || item.usage_name || item.lodging_category || "숙박시설 공매",item.unit_label].filter(Boolean).join(" · ");
      const remaining = item.bid_end_at ? dday(item.bid_end_at) : dateText(item.bid_start_at);
      const source = SOURCE[item.photo_source] || (item.photo_source ? esc(item.photo_source) : "공매 사진");
      return `<a class="auction-card" href="${href}">
        <div class="auction-card-photo">${image ? `<img src="${esc(image)}" alt="" loading="lazy" onerror="this.remove()">` : ""}<span class="auction-card-placeholder">사진 ${image ? "" : "없음"}</span>${image ? `<span class="auction-photo-source">${source}</span>` : ""}</div>
        <div class="auction-card-info">
          <div class="auction-card-badges"><span class="auction-kind ${kindClass(item.sale_kind)}">${esc(item.sale_kind || "기타")}</span><span class="auction-status status-${esc(item.status || "closed")}">${status}</span></div>
          <h3 class="auction-card-title">${esc(title)}</h3><div class="auction-card-address">${esc(place)}</div>
          <div class="auction-card-tags"><span>${esc(item.lodging_category || item.usage_name || "숙박시설")}</span><span>${esc(areaText(item.area_m2))}</span></div>
          <div class="auction-price-row"><span class="auction-price-label">최저입찰가</span><strong class="auction-price">${esc(money(item.min_bid_price))}</strong><span class="auction-ratio">${item.min_bid_ratio == null ? "율 확인 필요" : `${Number(item.min_bid_ratio).toLocaleString("ko-KR",{maximumFractionDigits:1})}%`}</span></div>
          <div class="auction-card-bottom"><span>감정가 <strong>${esc(money(item.appraisal_price))}</strong></span><span>${esc(remaining)} · 유찰 ${Number(item.failed_count || 0)}회</span></div>
        </div></a>`;
    }
    function renderPages(current,total) {
      const nav = $("auctionPagination");
      if (total <= 1) return;
      const first = Math.max(1,Math.floor((current-1)/5)*5+1), last=Math.min(total,first+4);
      let html = `<button class="auction-page-button" type="button" data-page="${Math.max(1,first-1)}" aria-label="이전 페이지" ${first===1?"disabled":""}>‹</button>`;
      for(let p=first;p<=last;p++) html+=`<button class="auction-page-button ${p===current?"is-active":""}" type="button" data-page="${p}" ${p===current?'aria-current="page"':""}>${p}</button>`;
      html+=`<button class="auction-page-button" type="button" data-page="${Math.min(total,last+1)}" aria-label="다음 페이지" ${last===total?"disabled":""}>›</button>`;
      nav.innerHTML=html;
      nav.querySelectorAll("[data-page]").forEach(button=>button.addEventListener("click",()=>{state.page=Number(button.dataset.page);fetchPage();window.scrollTo({top:0,behavior:"smooth"});}));
    }
    const sido=$("auctionSido"), sgg=$("auctionSgg");
    fetch("/api/regions",{credentials:"same-origin"}).then(r=>r.json()).then(data=>{
      const tree=data?.regions&&typeof data.regions==="object"&&!Array.isArray(data.regions)?data.regions:data;
      regionTree=tree&&typeof tree==="object"&&!Array.isArray(tree)?tree:{};
      sido.innerHTML='<option value="">전체</option>'+Object.keys(regionTree).sort().map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join("");
    }).catch(()=>{regionTree={};});
    sido.addEventListener("change",()=>{const children=regionTree[sido.value]?.sgg||{};sgg.innerHTML='<option value="">전체</option>'+Object.keys(children).sort().map(name=>{const label=name.startsWith(`${sido.value} `)?name.slice(sido.value.length).trim():name;return `<option value="${esc(name)}">${esc(label)}</option>`;}).join("");});
    document.querySelectorAll("[data-category]").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll("[data-category]").forEach(b=>b.classList.toggle("is-active",b===button));state.category=button.dataset.category;}));
    const applyVisibleFilters=()=>{state.region=sgg.value||sido.value;state.category=document.querySelector("[data-category].is-active")?.dataset.category||"";state.kind=$("auctionKind").value;state.status=$("auctionStatus").value;};
    const syncSortControls=()=>{ $("auctionSort").value=state.sort;document.querySelectorAll(".auction-sort-option").forEach(button=>{const active=button.dataset.sort===state.sort;button.classList.toggle("is-active",active);button.setAttribute("aria-pressed",String(active));});};
    const selectSort=sort=>{state.sort=sort;state.page=1;syncSortControls();fetchPage();};
    $("auctionSearch").addEventListener("click",()=>{applyVisibleFilters();state.page=1;fetchPage();});
    $("auctionSort").addEventListener("change",event=>{applyVisibleFilters();selectSort(event.target.value);});
    document.querySelectorAll(".auction-sort-option").forEach(button=>button.addEventListener("click",()=>{applyVisibleFilters();selectSort(button.dataset.sort);}));
    $("auctionReset").addEventListener("click",()=>{sido.value="";sgg.innerHTML='<option value="">전체</option>'; $("auctionKind").value="";$("auctionStatus").value="";document.querySelector('[data-category=""]').click();state.region="";state.kind="";state.status="";state.sort="deadline";state.page=1;syncSortControls();fetchPage();});
    fetchPage();
  }

  function initDetail() {
    const root=$("auctionDetailRoot");
    if(!root)return;
    const match=location.pathname.match(/^\/auctions\/([^/]+)/);
    if(!match){root.innerHTML='<div class="auction-error">공매 번호를 확인할 수 없습니다.</div>';return;}
    const id=decodeURIComponent(match[1]);
    let photos=[],lightIndex=0;
    const lightbox=$("auctionLightbox");
    const showLightbox=index=>{if(!photos.length)return;lightIndex=(index+photos.length)%photos.length;const img=lightbox.querySelector("img");img.dataset.photoUrl=safeImageUrl(photos[lightIndex].url);img.src=img.dataset.photoUrl;img.alt=`공매 사진 ${lightIndex+1}`;lightbox.querySelector(".lightbox-count").textContent=`${lightIndex+1} / ${photos.length}`;lightbox.hidden=false;document.body.style.overflow="hidden";};
    const closeLightbox=()=>{lightbox.hidden=true;document.body.style.overflow="";};
    function discardPhoto(url){
      const index=photos.findIndex(photo=>safeImageUrl(photo.url)===url);
      if(index<0)return;
      photos.splice(index,1);
      lightIndex=photos.length?Math.min(lightIndex,photos.length-1):0;
      renderGallery(root.querySelector("#auctionGalleryMount"));
    }
    function renderGallery(host){
      if(!host)return;
      if(!photos.length){host.innerHTML='<div class="auction-no-photos">사진 없음</div>';return;}
      host.innerHTML=`<div class="auction-gallery"><div class="auction-gallery-track">${photos.map((photo,index)=>`<div class="auction-gallery-slide"><img src="${esc(safeImageUrl(photo.url))}" alt="공매 및 건물 사진 ${index+1}" loading="${index<2?"eager":"lazy"}" data-gallery-index="${index}" data-photo-url="${esc(safeImageUrl(photo.url))}"><span class="auction-photo-source">${SOURCE[photo.source]||(photo.source?esc(photo.source):"건물 사진")}</span></div>`).join("")}</div><span class="auction-gallery-counter">1 / ${photos.length}</span></div>`;
      const track=host.querySelector(".auction-gallery-track"),counter=host.querySelector(".auction-gallery-counter");
      track.querySelectorAll("[data-gallery-index]").forEach(img=>{
        img.addEventListener("click",()=>showLightbox(Number(img.dataset.galleryIndex)));
        img.addEventListener("error",()=>discardPhoto(img.dataset.photoUrl),{once:true});
      });
      track.addEventListener("scroll",()=>{
        if(!counter)return;
        const slides=[...track.querySelectorAll(".auction-gallery-slide")];
        if(!slides.length)return;
        let nearest=0,distance=Infinity;
        slides.forEach((slide,index)=>{const current=Math.abs(slide.offsetLeft-track.offsetLeft-track.scrollLeft);if(current<distance){distance=current;nearest=index;}});
        counter.textContent=`${nearest+1} / ${photos.length}`;
      },{passive:true});
    }
    lightbox.querySelector("img").addEventListener("error",()=>{const url=lightbox.querySelector("img").dataset.photoUrl;closeLightbox();if(url)discardPhoto(url);});
    lightbox.querySelector(".lightbox-close").addEventListener("click",closeLightbox);
    lightbox.querySelector(".lightbox-prev").addEventListener("click",()=>showLightbox(lightIndex-1));
    lightbox.querySelector(".lightbox-next").addEventListener("click",()=>showLightbox(lightIndex+1));
    lightbox.addEventListener("click",e=>{if(e.target===lightbox)closeLightbox();});
    document.addEventListener("keydown",e=>{if(lightbox.hidden)return;if(e.key==="Escape")closeLightbox();if(e.key==="ArrowLeft")showLightbox(lightIndex-1);if(e.key==="ArrowRight")showLightbox(lightIndex+1);});
    (async()=>{
      try{
        const response=await fetch(`/api/auctions/${encodeURIComponent(id)}`,{credentials:"same-origin"});
        const data=await response.json().catch(()=>({}));
        if(!response.ok||data.ok!==true||!data.item)throw new Error(data.message||"공매 정보를 불러오지 못했습니다.");
        const item=data.item, building=item.master_building_id?data.building:null;
        let buildingPhotos=[];
        if(item.master_building_id){
          try{const photoRes=await fetch(`/api/building/${encodeURIComponent(item.master_building_id)}/auctions`,{credentials:"same-origin"});const photoData=await photoRes.json().catch(()=>({}));if(photoRes.ok&&photoData.ok)buildingPhotos=Array.isArray(photoData.photos)?photoData.photos:[];}catch(_){}
        }
        const priority={listing:0,auction:1,tourapi:2,gocamping:3,google_streetview:4,streetview:4,operator:5};
        const combined=[...(buildingPhotos||[]),...(data.photos||[])].filter(p=>p&&safeImageUrl(p.url)).sort((a,b)=>(priority[a.source]??6)-(priority[b.source]??6)||Number(a.sort_order||0)-Number(b.sort_order||0));
        const unique=new Set();photos=combined.filter(photo=>{const url=safeImageUrl(photo.url);if(unique.has(url))return false;unique.add(url);return true;});
        const status=STATUS[item.status]||"상태 확인";
        const title=building?.building_name||item.title||item.usage_name||item.lodging_category||"숙박시설 공매";
        const addr=item.address_road||item.address_jibun||building?.road_address||building?.jibun_address||"주소 확인 중";
        const category=item.lodging_category||item.usage_name||"숙박시설";
        const rounds=Array.isArray(data.rounds)?data.rounds:[];
        const gallery=photos.length?`<div class="auction-gallery"><div class="auction-gallery-track">${photos.map((p,index)=>`<div class="auction-gallery-slide"><img src="${esc(safeImageUrl(p.url))}" alt="공매 및 건물 사진 ${index+1}" loading="${index<2?"eager":"lazy"}" data-gallery-index="${index}" onerror="this.closest('.auction-gallery-slide').remove()"><span class="auction-photo-source">${SOURCE[p.source]||"건물 사진"}</span></div>`).join("")}</div><span class="auction-gallery-counter">1 / ${photos.length}</span></div>`:'<div class="auction-no-photos">사진 없음</div>';
        const roundsHtml=rounds.length?`<div class="auction-timeline"><h3>회차별 최저가</h3>${rounds.map(round=>`<div class="auction-round ${round.is_current?"is-current":""}"><b>${Number(round.round_no)||"-"}회차${round.is_current?" · 현재":round.is_upcoming?" · 예정":""}</b><span>${round.result_at?`개찰 ${dateText(round.result_at)}`:`${dateText(round.bid_start_at)} – ${dateText(round.bid_end_at)}`} · ${esc(round.result|| (round.is_current?"진행 회차":"결과 확인"))}</span><strong>${esc(money(round.min_bid_price))}</strong></div>`).join("")}</div>`:"";
        const detailUrl=safeImageUrl(item.detail_url);
        root.innerHTML=`<div id="auctionGalleryMount"></div><section class="auction-detail-title-block"><div class="auction-card-badges"><span class="auction-kind ${kindClass(item.sale_kind)}">${esc(item.sale_kind||"기타")}</span><span class="auction-status status-${esc(item.status||"closed")}">${status}</span></div><h1>${esc(title)}</h1><div class="auction-detail-sub">${esc(addr)} · ${esc(category)} · ${esc(areaText(item.area_m2))}${item.unit_label?` · ${esc(item.unit_label)}`:""}</div></section>
          <section class="auction-info-card"><div class="auction-section-title"><span>01</span> 공매 일반정보</div><div class="auction-info-grid">${info("감정가",money(item.appraisal_price),true)}${info("최저입찰가",`${money(item.min_bid_price)}${item.min_bid_ratio==null?"":` (${Number(item.min_bid_ratio).toLocaleString("ko-KR",{maximumFractionDigits:1})}%)`}`,true)}${info("입찰기간",`${dateText(item.bid_start_at)} – ${dateText(item.bid_end_at)}`)}${info("회차 · 유찰",`${item.round_no||"-"}회차 · ${Number(item.failed_count||0)}회`)}${info("처분방식",item.disposal_method||"정보 없음")}${info("공고기관",item.notice_org||"정보 없음")}</div>${roundsHtml}${detailUrl?`<a class="auction-onbid" href="${esc(detailUrl)}" target="_blank" rel="noopener noreferrer">온비드 원문 공고 보기 ↗</a>`:"<div class='auction-onbid' aria-disabled='true'>온비드 원문 링크가 제공되지 않았습니다</div>"}</section>
          <section id="auctionAnalysisSlot"></section><button type="button" class="auction-favorite" id="auctionFavorite">관심 등록 · 알림</button>
          ${!building?'<div class="auction-building-empty">연결된 건물 정보가 없습니다. 이 공매는 관심단지로 등록할 수 없습니다.</div>':""}
          <p class="auction-disclaimer">공매 정보 출처: 한국자산관리공사 온비드(공공데이터포털). 입찰 전 온비드 원문 공고와 권리관계를 반드시 확인하세요. 홈앤스테이는 입찰을 대행하거나 결과를 보장하지 않습니다.</p>`;
        renderGallery(root.querySelector("#auctionGalleryMount"));
        const syncWatchButton=async()=>{
          if(!building||!window.__livingstayLoggedIn)return;
          try{
            const response=await fetch(`/api/building/${encodeURIComponent(building.id)}/auction-watch`,{credentials:"same-origin"});
            const watched=await response.json();
            if(response.ok&&watched.ok){
              $("auctionFavorite").dataset.watchEnabled=watched.enabled?"true":"false";
              $("auctionFavorite").textContent=watched.enabled?"공매 알림 해제":"관심 등록 · 알림";
            }
          }catch(_){}
        };
        void syncWatchButton();
        window.addEventListener("livingstay:auth",syncWatchButton);
        $("auctionFavorite").addEventListener("click",async event=>{
          const button=event.currentTarget;
          if(!building){window.alert("매칭된 건물 정보가 없어 관심단지 등록을 할 수 없습니다.");return;}
          if(window.__livingstayAccountType&&window.__livingstayAccountType!=="user"){window.alert("관심저장은 일반회원 전용 기능입니다.");return;}
          if(!window.__livingstayLoggedIn){if(typeof window.livingstayOpenLogin==="function")window.livingstayOpenLogin();else location.href="/?login=1";return;}
          button.disabled=true;
          try{
            if(button.dataset.watchEnabled==="true"){
              const response=await fetch(`/api/building/${encodeURIComponent(building.id)}/auction-watch`,{method:"DELETE",credentials:"same-origin"});
              const result=await response.json();
              if(!response.ok||!result.ok)throw new Error(result.message||"알림 해제 실패");
              button.dataset.watchEnabled="false";button.textContent="관심 등록 · 알림";button.classList.remove("is-saved");button.disabled=false;
              return;
            }
            const payload={building_name:building.building_name||item.title||item.usage_name||"숙박시설",address:building.road_address||building.jibun_address||item.address_road||item.address_jibun||"",building_id:building.id||item.master_building_id};
            if(!payload.address)throw new Error("매칭 건물의 주소를 확인할 수 없어 관심단지로 저장하지 못했습니다.");
            const save=await fetch("/api/favorites/mine",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
            const result=await save.json().catch(()=>({}));
            if(!save.ok||!result.ok)throw new Error(result.message||"관심단지 등록에 실패했습니다.");
            const watch=await fetch(`/api/building/${encodeURIComponent(payload.building_id)}/auction-watch`,{method:"POST",credentials:"same-origin"});
            const watched=await watch.json().catch(()=>({}));
            if(!watch.ok||!watched.ok)throw new Error("관심단지는 저장했지만 공매 알림 설정에 실패했습니다. 다시 시도해 주세요.");
            button.dataset.watchEnabled="true";button.textContent="공매 알림 해제";button.classList.add("is-saved");button.disabled=false;
          }catch(error){window.alert(error.message||"관심단지 등록에 실패했습니다.");button.disabled=false;}
        });
      }catch(error){root.innerHTML=`<div class="auction-error" role="alert"><strong>${esc(error.message||"공매 상세를 불러오지 못했습니다.")}</strong><button id="auctionDetailRetry" type="button">다시 불러오기</button></div>`;$("auctionDetailRetry")?.addEventListener("click",()=>location.reload());}
    })();
    function info(label,value,isPrice=false){return `<div class="auction-info-item"><span class="auction-info-label">${esc(label)}</span><div class="auction-info-value ${isPrice?"price":""}">${esc(value)}</div></div>`;}
  }
  initList();initDetail();
})();