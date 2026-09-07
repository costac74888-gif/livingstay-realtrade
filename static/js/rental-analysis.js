(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var buildingSequence = 0;
  var taxManuallyEdited = false;
  var ids = [
    "rentalPurchasePrice", "rentalMarketPrice", "rentalDeposit", "rentalMonthlyRent",
    "rentalVacancyRate", "rentalAcquisitionCost", "rentalPropertyTax",
    "rentalManagementCost", "rentalOtherCost", "rentalLoanAmount",
    "rentalLoanRate", "rentalLoanYears",
  ];
  function n(id) {
    var value = $(id).value;
    return value === "" || !Number.isFinite(Number(value)) ? 0 : Number(value);
  }
  function money(value, digits) {
    return Number(value || 0).toLocaleString("ko-KR", {
      maximumFractionDigits: digits == null ? 0 : digits,
    }) + "만원";
  }
  function percent(value) {
    return Number.isFinite(value) ? value.toFixed(2) + "%" : "계산 불가";
  }
  function estimateTax(purchasePrice) {
    if (!purchasePrice) return 0;
    var estimatedTaxBase = purchasePrice * 0.6;
    var propertyTax = estimatedTaxBase * 0.0025;
    var urbanAreaTax = estimatedTaxBase * 0.0014;
    var educationTax = propertyTax * 0.2;
    return Math.round((propertyTax + urbanAreaTax + educationTax) * 10) / 10;
  }
  function annualDebtService(amount, annualRate, years, method) {
    if (amount <= 0) return { annual: 0, monthly: 0, firstPrincipal: 0 };
    var months = Math.max(1, years * 12);
    var rate = annualRate / 100 / 12;
    if (method === "interest") {
      return { annual: amount * annualRate / 100, monthly: amount * rate, firstPrincipal: 0 };
    }
    if (method === "principal") {
      var principal = amount / months;
      return {
        annual: (principal + amount * rate) * 12,
        monthly: principal + amount * rate,
        firstPrincipal: principal,
      };
    }
    var monthly = rate > 0
      ? amount * rate * Math.pow(1 + rate, months) / (Math.pow(1 + rate, months) - 1)
      : amount / months;
    return { annual: monthly * 12, monthly: monthly, firstPrincipal: Math.max(0, monthly - amount * rate) };
  }
  function card(label, value, note, style) {
    return '<article class="analysis-card rental-result ' + (style || "") + '"><small>'
      + label + '</small><strong>' + value + '</strong><span>' + note + "</span></article>";
  }
  function calculate() {
    var purchase = n("rentalPurchasePrice");
    var market = n("rentalMarketPrice");
    var deposit = n("rentalDeposit");
    var rent = n("rentalMonthlyRent");
    var vacancy = Math.min(100, Math.max(0, n("rentalVacancyRate"))) / 100;
    var acquisition = n("rentalAcquisitionCost");
    var tax = n("rentalPropertyTax");
    var costs = tax + n("rentalManagementCost") + n("rentalOtherCost");
    var loan = n("rentalLoanAmount");
    var debt = annualDebtService(
      loan, n("rentalLoanRate"), Math.max(1, n("rentalLoanYears")),
      $("rentalLoanMethod").value
    );
    var annualRent = rent * 12;
    var effectiveRent = annualRent * (1 - vacancy);
    var noi = effectiveRent - costs;
    var invested = purchase + acquisition - deposit - loan;
    var cashFlow = noi - debt.annual;
    var grossYield = purchase > 0 ? annualRent / purchase * 100 : NaN;
    var netYield = purchase > 0 ? noi / purchase * 100 : NaN;
    var cashReturn = invested > 0 ? cashFlow / invested * 100 : NaN;
    var marketYield = market > 0 ? noi / market * 100 : NaN;
    var dscr = debt.annual > 0 ? noi / debt.annual : null;
    $("rentalResults").innerHTML =
      card("대출 후 월 순현금", money(cashFlow / 12, 1), "순영업소득에서 월 원리금 차감", "primary")
      + card("자기자본 수익률", percent(cashReturn), "실투자금 " + money(invested), cashReturn < 0 ? "warning" : "")
      + card("비용 반영 순수익률", percent(netYield), "순영업소득 " + money(noi) + "/년")
      + card("표면수익률", percent(grossYield), "공실·비용 차감 전")
      + card("현재 실거래 기준 수익률", market ? percent(marketYield) : "기준가 입력 필요", market ? "현재 기준가 " + money(market) : "최근 실거래 자동연결 예정")
      + card("월 대출 상환액", money(debt.monthly, 1), $("rentalLoanMethod").selectedOptions[0].text)
      + card("DSCR", dscr == null ? "대출 없음" : dscr.toFixed(2) + "배", dscr == null ? "대출상환 부담 없음" : (dscr >= 1.2 ? "임대수익 상환여력 양호" : "상환여력 주의"), dscr != null && dscr < 1.2 ? "warning" : "")
      + card("연간 보유비용", money(costs), "보유세·관리비·수선비 합계");
    window.__rentalAnalysisResult = {
      purchasePrice: purchase, annualRent: annualRent, noi: noi, invested: invested,
      debtService: debt.annual, cashFlow: cashFlow, grossYield: grossYield,
      netYield: netYield, cashReturn: cashReturn, dscr: dscr,
    };
  }
  function updateEstimatedTax() {
    if (taxManuallyEdited) return;
    var estimated = estimateTax(n("rentalPurchasePrice"));
    $("rentalPropertyTax").value = estimated ? String(estimated) : "";
    $("rentalTaxHint").textContent = estimated
      ? "비주거용 추정 과세표준·부가세목 적용: 연 " + money(estimated, 1)
      : "매입가 입력 시 자동 추정되며 직접 수정할 수 있습니다.";
  }
  async function loadBuilding() {
    var id = new URLSearchParams(location.search).get("building_id");
    var seq = ++buildingSequence;
    if (!id) {
      $("rentalBuildingName").textContent = "분석할 건물을 선택해 주세요";
      $("rentalBuildingAddress").textContent = "생활숙박시설·장기임대 호실의 보증금과 월세 수익을 계산합니다.";
      return;
    }
    try {
      var response = await fetch("/api/building/" + encodeURIComponent(id), { credentials: "same-origin" });
      var data = response.ok ? await response.json() : null;
      if (seq !== buildingSequence || !data) return;
      $("rentalBuildingName").textContent = data.display_building_name || data.building_name || "선택 건물";
      $("rentalBuildingAddress").textContent = data.road_address || data.jibun_address || "주소 미확인";
    } catch (ignore) {}
  }
  ids.forEach(function (id) {
    $(id).addEventListener("input", function () {
      if (id === "rentalPropertyTax") taxManuallyEdited = true;
      if (id === "rentalPurchasePrice") updateEstimatedTax();
      calculate();
    });
  });
  $("rentalLoanMethod").addEventListener("change", calculate);
  $("rentalCalculate").addEventListener("click", calculate);
  $("rentalReset").addEventListener("click", function () {
    taxManuallyEdited = false;
    ids.forEach(function (id) { $(id).value = ""; });
    $("rentalVacancyRate").value = "5";
    $("rentalManagementCost").value = "0";
    $("rentalOtherCost").value = "0";
    $("rentalLoanAmount").value = "0";
    $("rentalLoanRate").value = "4.5";
    $("rentalLoanYears").value = "20";
    $("rentalLoanMethod").value = "interest";
    $("rentalResults").innerHTML = '<article class="analysis-card rental-empty"><strong>임대조건을 입력해 주세요</strong><span>매입가·보증금·월세를 입력하면 대출과 비용을 반영한 수익률을 계산합니다.</span></article>';
  });
  window.loadRentalAnalysis = loadBuilding;
  loadBuilding();
}());