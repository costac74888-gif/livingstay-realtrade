(function(){
  "use strict";
  var list=document.getElementById("reviewList");
  function esc(value){return String(value==null?"":value).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function money(value){return value===null||value===undefined||value===""?"미기재":Number(value).toLocaleString("ko-KR")+"만원";}
  function brokerValue(item,key){return (item.broker&&item.broker[key])||item[key]||"";}
  function rightsRows(item){
    var info=item.business_rights_info||{};
    if(typeof info==="string"){try{info=JSON.parse(info);}catch(e){info={};}}
    var labels={facility_name:"영업장명",maintenance_fee_krw:"관리비 (만원)",lease_term:"임대차 기간",
      lease_transfer_possible:"임대차 승계",furniture_included:"시설·집기 포함",furniture_details:"시설·집기 상세",
      staff_transfer:"직원 승계",ota_transfer:"예약·OTA 인계",takeover_conditions:"인수 조건",
      adr_krw:"ADR (만원)",occ:"점유율 (%)",revpar_krw:"RevPAR (만원)",rating:"평점",
      review_count:"리뷰 수",permit_status:"인허가 상태",permit_industry:"신고 업종",
      permit_certificate:"영업신고증",permit_notes:"승계 참고사항"};
    return Object.keys(labels).filter(function(key){return info[key]!==null&&info[key]!==undefined&&info[key]!=="";})
      .map(function(key){var value=info[key];if(typeof value==="boolean")value=value?"가능":"불가";
        if(/_krw$/.test(key))value=money(value);return '<div class="review-fact"><span>'+esc(labels[key])+'</span><b>'+esc(value)+'</b></div>';}).join("");
  }
  function amountFacts(item){
    return [
      ["희망가 / 보증금",item.price_krw],["월 임대료",item.monthly_rent_krw],["권리금",item.key_money_krw]
    ].filter(function(row){return row[1]!==null&&row[1]!==undefined;})
      .map(function(row){return '<div class="review-fact"><span>'+esc(row[0])+'</span><b>'+esc(money(row[1]))+'</b></div>';}).join("");
  }
  function operatingFacts(item){
    return [
      ["최근 12개월 매출",item.annual_revenue_krw],["월평균 매출",item.monthly_revenue_krw],
      ["대실 비율",item.short_stay_ratio],["OTA 매출 비중",item.ota_revenue_ratio],
      ["운영상태",item.operation_status],["객실 수",item.room_count]
    ].filter(function(row){return row[1]!==null&&row[1]!==undefined&&row[1]!=="";})
      .map(function(row){var value=/_매출$/.test(row[0])?money(row[1]):row[1];
        if(row[0]==="객실 수")value=Number(value).toLocaleString("ko-KR")+"실";
        if(row[0].includes("비율"))value=value+"%";
        return '<div class="review-fact"><span>'+esc(row[0])+'</span><b>'+esc(value)+'</b></div>';}).join("");
  }
  function photoMarkup(item){
    var photos=Array.isArray(item.photos)?item.photos:[];
    if(!photos.length&&item.photo_url)photos=[{url:item.photo_url}];
    return photos.length?'<div class="review-photos" aria-label="등록된 매물 사진">'+photos.map(function(photo){
      var url=typeof photo==="string"?photo:photo&&photo.url;
      return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener"><img src="'+esc(url)+'" alt="등록 매물 사진"></a>':"";
    }).join("")+'</div>':'<p class="review-muted">등록된 매물 사진이 없습니다.</p>';
  }
  function load(){
    list.className="review-state"; list.textContent="검수 대기 매물을 불러오는 중입니다.";
    fetch("/api/admin/broker-listings",{credentials:"same-origin"}).then(function(r){return r.json().then(function(d){if(!r.ok||!d.ok)throw new Error(d.message||"검수 목록을 불러오지 못했습니다.");return d;});}).then(function(data){
      var items=data.items||[];
      if(!items.length){list.innerHTML="현재 검수 대기 중인 중개 매물이 없습니다.";return;}
      list.className="";
      list.innerHTML=items.map(function(item){
        var publication=item.publication_status||"pending";
        var publicationName={pending:"검수 대기",approved:"게시 승인",rejected:"게시 반려"}[publication]||publication;
        var propertyFacts=[
          ["거래유형",item.deal_type],["등록대상",item.transaction_target==="business_rights"?"영업권 양도":item.transaction_target==="whole"?"건물 전체":"개별 호실"],
          ["주소",item.road_address||item.address||""],["등록일",item.created_at||item.listing_date||""]
        ].filter(function(row){return row[1]!==null&&row[1]!==undefined&&row[1]!=="";})
          .map(function(row){return '<div class="review-fact"><span>'+esc(row[0])+'</span><b>'+esc(row[1])+'</b></div>';}).join("");
        var officeFacts=[
          ["중개사무소",brokerValue(item,"office_name")],["개업공인중개사",brokerValue(item,"owner_name")],
          ["등록번호",brokerValue(item,"reg_number")],["사무소 소재지",brokerValue(item,"office_address")],
          ["사무소 연락처",brokerValue(item,"office_phone")||brokerValue(item,"phone")],
          ["등록 담당자",brokerValue(item,"registered_by")],["중개사 등록일",brokerValue(item,"created_at")]
        ].map(function(row){return '<div class="review-fact"><span>'+esc(row[0])+'</span><b>'+esc(row[1]||"미기재")+'</b></div>';}).join("");
        var operating=operatingFacts(item)+rightsRows(item);
        return '<article class="review-card" data-id="'+esc(item.id)+'" data-review-version="'+esc(item.review_version||"")+'">'+
          '<div class="review-card-head"><div><h2>'+esc(item.building_name||item.business_rights_info&&item.business_rights_info.facility_name||"검수 대상 매물")+'</h2>'+
          '<div class="review-meta">매물번호 '+esc(item.listing_number||item.id)+' · 수정 버전 '+esc(item.review_version||"없음")+'</div></div>'+
          '<span class="review-status review-status-'+esc(publication)+'">현재 상태 · '+esc(publicationName)+'</span></div>'+
          (item.publication_reason?'<div class="review-reason"><b>최근 검수 의견</b> '+esc(item.publication_reason)+'</div>':"")+
          '<section class="review-section"><h3>매물정보 · 거래 조건</h3><div class="review-facts">'+propertyFacts+amountFacts(item)+'</div>'+
          (item.description?'<p class="review-description">'+esc(item.description)+'</p>':"")+'</section>'+
          '<section class="review-section"><h3>운영정보 · 영업권 양도</h3><div class="review-facts">'+(operating||'<span class="review-muted">입력된 운영정보가 없습니다.</span>')+'</div></section>'+
          '<section class="review-section"><h3>중개사 표시·광고 정보</h3><div class="review-facts">'+officeFacts+'</div></section>'+
          '<section class="review-section"><h3>사진·영상</h3>'+photoMarkup(item)+'</section>'+
          '<div class="review-actions"><textarea aria-label="검수 사유" placeholder="승인 의견 (선택) · 반려 시 필수"></textarea><button type="button" data-decision="approved">승인 게시</button><button type="button" class="reject" data-decision="rejected">반려</button></div>'+
          '<div class="review-feedback" aria-live="polite"></div></article>';
      }).join("");
      list.querySelectorAll("button[data-decision]").forEach(function(button){button.addEventListener("click",function(){
        var card=button.closest(".review-card"), feedback=card.querySelector(".review-feedback"), reason=card.querySelector("textarea").value.trim();
        if(button.dataset.decision==="rejected"&&!reason){feedback.textContent="반려 사유를 입력해 주세요.";return;}
        card.querySelectorAll("button").forEach(function(b){b.disabled=true;});
        fetch("/api/admin/broker-listings/"+encodeURIComponent(card.dataset.id)+"/review",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision:button.dataset.decision,reason:reason,review_version:card.dataset.reviewVersion})}).then(function(r){return r.json().then(function(d){if(!r.ok||!d.ok){var error=new Error(d.message||"처리하지 못했습니다.");error.status=r.status;throw error;}return d;});}).then(function(){card.remove();if(!list.querySelector(".review-card")){list.className="review-state";list.textContent="현재 검수 대기 중인 중개 매물이 없습니다.";}}).catch(function(error){feedback.textContent=error.status===409?"매물이 수정되어 검수 버전이 만료되었습니다. 최신 정보를 다시 불러옵니다.":error.message;card.querySelectorAll("button").forEach(function(b){b.disabled=false;});if(error.status===409)setTimeout(load,900);});
      });});
    }).catch(function(error){list.className="review-state";list.innerHTML=esc(error.message)+' <button type="button" id="reviewRetry">다시 시도</button>';document.getElementById("reviewRetry").addEventListener("click",load);});
  }
  document.getElementById("reviewReload").addEventListener("click",load);load();
})();
