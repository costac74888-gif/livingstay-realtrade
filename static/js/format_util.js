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

  window.formatPhone = formatPhone;
  window.formatBizRegNumber = formatBizRegNumber;
})();
