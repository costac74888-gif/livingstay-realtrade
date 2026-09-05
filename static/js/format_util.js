// 공용 표시 포맷 유틸 — 전화번호/사업자등록번호는 DB에 숫자만 저장되므로
// 화면에 보여줄 때 이 함수들로 하이픈 포함 형식으로 재포맷한다.
(function(){
  function digitsOnly(s){ return String(s || "").replace(/\D/g, ""); }

  // 전화번호: 02 지역번호(9~10자리)와 휴대폰/일반(10~11자리) 처리. 실패 시 원문 반환.
  function formatPhone(p){
    const d = digitsOnly(p);
    if (!d) return p || "";
    if (d.startsWith("02")){
      if (d.length === 9)  return d.slice(0,2) + "-" + d.slice(2,5) + "-" + d.slice(5);
      if (d.length === 10) return d.slice(0,2) + "-" + d.slice(2,6) + "-" + d.slice(6);
    }
    if (d.length === 10) return d.slice(0,3) + "-" + d.slice(3,6) + "-" + d.slice(6);
    if (d.length === 11) return d.slice(0,3) + "-" + d.slice(3,7) + "-" + d.slice(7);
    return p || "";
  }

  // 사업자등록번호: 10자리 → 000-00-00000. 실패 시 원문 반환.
  function formatBizRegNumber(b){
    const d = digitsOnly(b);
    if (d.length === 10) return d.slice(0,3) + "-" + d.slice(3,5) + "-" + d.slice(5);
    return b || "";
  }

  // 대출모집인 등록번호: 10자리 → 00-00000000. 실패 시 원문 반환.
  function formatLicenseNumber(v) {
    const d = digitsOnly(v);
    if (d.length === 10) return d.slice(0, 2) + "-" + d.slice(2);
    return v || "";
  }

  // ---- 입력창 자동 하이픈 (UX 전용 — 저장/전송 시엔 서버·JS에서 숫자만 추출) ----

  function autoHyphenPhone(el) {
    el.addEventListener("input", function () {
      var d = this.value.replace(/\D/g, "").slice(0, 11);
      var f = d;
      if (d.startsWith("02")) {
        if (d.length > 5) f = d.slice(0,2)+"-"+d.slice(2,6)+"-"+d.slice(6);
        else if (d.length > 2) f = d.slice(0,2)+"-"+d.slice(2);
      } else {
        if (d.length > 7) f = d.slice(0,3)+"-"+d.slice(3,7)+"-"+d.slice(7);
        else if (d.length > 3) f = d.slice(0,3)+"-"+d.slice(3);
      }
      this.value = f;
    });
  }

  function autoHyphenBizReg(el) {
    el.addEventListener("input", function () {
      var d = this.value.replace(/\D/g, "").slice(0, 10);
      var f = d;
      if (d.length > 5) f = d.slice(0,3)+"-"+d.slice(3,5)+"-"+d.slice(5);
      else if (d.length > 3) f = d.slice(0,3)+"-"+d.slice(3);
      this.value = f;
    });
  }

  function autoHyphenLicense(el) {
    el.addEventListener("input", function () {
      var d = this.value.replace(/\D/g, "").slice(0, 10);
      this.value = d.length > 2 ? d.slice(0,2)+"-"+d.slice(2) : d;
    });
  }

  // 거래유형별 희망가 포맷 (만원 단위)
  // 매매/전세: '10,000' | 월세: '보5,000/50' | 없으면 '-'
  function formatLrPrice(deal_type, price_krw, monthly_rent_krw, price_krw_max) {
    var fmt = function(v){ return v != null ? Number(v).toLocaleString() : "-"; };
    if (deal_type === "매매" || deal_type === "전세") {
      return price_krw_max != null ? fmt(price_krw) + " ~ " + fmt(price_krw_max) : fmt(price_krw);
    }
    if (deal_type === "월세") {
      return price_krw_max != null ? fmt(price_krw) + " ~ " + fmt(price_krw_max) : "보" + fmt(price_krw) + "/" + fmt(monthly_rent_krw);
    }
    if (deal_type === "단기임대") return price_krw != null ? fmt(price_krw) + (price_krw_max != null ? " ~ " + fmt(price_krw_max) : "") : "-";
    return "-";
  }

  // 법정 숙박분류 공용 표시 규칙. 화면별 중복 색상/약칭이 서로 달라지지 않게
  // 모든 공개·파트너·관리자 화면에서 이 객체를 사용한다.
  var lodgingTypeOrder = [
    "생활", "관광", "일반", "에어비앤비", "농어촌민박",
    "캠핑", "한옥", "복합", "준공전", "미분류"
  ];
  var lodgingTypeColors = {
    "생활": "#378ADD",
    "관광": "#14B8A6",
    "일반": "#D46BA3",
    "에어비앤비": "#FF5A5F",
    "농어촌민박": "#8BC34A",
    "캠핑": "#795548",
    "한옥": "#FF8F00",
    "복합": "#B39DDB",
    "준공전": "#E53935",
    "미분류": "#9AA5B1"
  };
  var lodgingTypeLabels = {
    "생활": "생활숙박시설",
    "관광": "관광숙박",
    "일반": "일반숙박",
    "에어비앤비": "에어비앤비",
    "농어촌민박": "농어촌민박",
    "캠핑": "캠핑·야영",
    "한옥": "한옥",
    "복합": "복합",
    "준공전": "미준공(분양중)",
    "미분류": "미분류"
  };
  var lodgingTypeBadges = Object.assign({}, lodgingTypeLabels, { "생활": "생숙" });

  function normalizeLodgingType(value, buildingStatus) {
    var raw = String(value || "").trim();
    if (raw.indexOf("·") >= 0 || raw === "복합") return "복합";
    // 과거 화면/API 값은 관광 법정분류로만 표시해 새 체계와 섞이지 않게 한다.
    if (raw === "호텔" || raw === "콘도") return "관광";
    if (lodgingTypeColors[raw]) return raw;
    if (!raw && (buildingStatus === "허가" || buildingStatus === "착공")) return "준공전";
    return "미분류";
  }

  function lodgingTypeColor(value, buildingStatus) {
    return lodgingTypeColors[normalizeLodgingType(value, buildingStatus)];
  }

  function lodgingTypeLabel(value, buildingStatus) {
    return lodgingTypeLabels[normalizeLodgingType(value, buildingStatus)];
  }

  function lodgingTypeBadge(value, subtype, buildingStatus) {
    var label = lodgingTypeBadges[normalizeLodgingType(value, buildingStatus)];
    return subtype ? label + "(" + subtype + ")" : label;
  }

  window.formatPhone = formatPhone;
  window.formatBizRegNumber = formatBizRegNumber;
  window.formatLicenseNumber = formatLicenseNumber;
  window.formatLrPrice = formatLrPrice;
  window.autoHyphenPhone = autoHyphenPhone;
  window.autoHyphenBizReg = autoHyphenBizReg;
  window.autoHyphenLicense = autoHyphenLicense;
  window.LodgingTypes = Object.freeze({
    order: Object.freeze(lodgingTypeOrder.slice()),
    colors: Object.freeze(Object.assign({}, lodgingTypeColors)),
    labels: Object.freeze(Object.assign({}, lodgingTypeLabels)),
    normalize: normalizeLodgingType,
    color: lodgingTypeColor,
    label: lodgingTypeLabel,
    badge: lodgingTypeBadge
  });
})();
