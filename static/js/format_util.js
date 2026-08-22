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

  window.formatPhone = formatPhone;
  window.formatBizRegNumber = formatBizRegNumber;
  window.formatLicenseNumber = formatLicenseNumber;
  window.formatLrPrice = formatLrPrice;
  window.autoHyphenPhone = autoHyphenPhone;
  window.autoHyphenBizReg = autoHyphenBizReg;
  window.autoHyphenLicense = autoHyphenLicense;
})();
