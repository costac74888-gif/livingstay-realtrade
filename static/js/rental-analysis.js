(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var buildingSequence = 0;
  var loadedBuildingId = "";
  var marketPriceManuallyEdited = false;
  var automaticMarketPrice = null;
  var areaLookupTimer = null;
  var taxManuallyEdited = false;
  var loadedBuilding = null;
  var rentalBenchmark = null;
  var rentalBenchmarkItems = [];
  var benchmarkSource = "";
  var benchmarkNotice = "";
  var ids = [
    "rentalUnitArea", "rentalPurchasePrice", "rentalMarketPrice", "rentalDeposit", "rentalMonthlyRent",
    "rentalVacancyMonths", "rentalVacancyRate", "rentalAcquisitionTax", "rentalBrokerFee", "rentalPropertyTax",
    "rentalManagementCost", "rentalOtherCost", "rentalLoanAmount",
    "rentalLoanRate", "rentalLoanYears",
  ];
  function n(id) {
    var value = $(id).value;
    if (id === "rentalUnitArea") value = value.replace(/\s*㎡\s*$/, "").trim();
    return value === "" || !Number.isFinite(Number(value)) ? 0 : Number(value);
  }
  function escapeHtml(value) {
    var node = document.createElement("div");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }
  function monthLabel(value) {
    var match = String(value || "").match(/^(\d{4})-(\d{2})-\d{2}$/);
    return match ? match[1] + "년 " + Number(match[2]) + "월" : String(value || "");
  }
  function quarterLabel(value) {
    var match = String(value || "").match(/^(\d{4})-(\d{2})-\d{2}$/);
    return match ? match[1] + "년 " + (Math.floor((Number(match[2]) - 1) / 3) + 1) + "분기" : String(value || "");
  }
  function money(value, digits) {
    return Number(value || 0).toLocaleString("ko-KR", {
      maximumFractionDigits: digits == null ? 0 : digits,
    }) + "만원";
  }
  function percent(value) {
    return Number.isFinite(value) ? value.toFixed(2) + "%" : "계산 불가";
  }
  var resultHelp = {
    "대출 후 월 순현금": "대출을 갚고 매달 남는 돈",
    "자기자본 수익률": "내가 실제 넣은 돈 대비 연간 수익",
    "비용 반영 순수익률": "공실·운영비를 뺀 실제 수익률",
    "표면수익률": "비용을 빼기 전 단순 임대수익률",
    "현재 실거래 기준 수익률": "주변 실거래 가격으로 다시 계산한 수익률",
    "월 대출 상환액": "매달 갚아야 할 원금과 이자",
    "DSCR": "임대수익으로 대출을 갚을 수 있는 정도",
    "연간 보유비용": "1년간 드는 세금·관리비·수선비",
  };
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
    return '<article class="analysis-card rental-result ' + (style || "") + '"><small><b>'
      + label + '</b><em>' + (resultHelp[label] || "") + '</em></small><strong>'
      + value + '</strong><span>' + note + "</span></article>";
  }
  function benchmarkMonths() {
    if (!rentalBenchmark) return null;
    if (Number.isFinite(Number(rentalBenchmark))) return Number(rentalBenchmark);
    var values = [rentalBenchmark.vacancy_months, rentalBenchmark.average_vacancy_months,
      rentalBenchmark.avg_vacancy_months, rentalBenchmark.r_one_vacancy_months];
    for (var i = 0; i < values.length; i++) if (Number.isFinite(Number(values[i]))) return Number(values[i]);
    var rate = rentalBenchmark.vacancy_rate || rentalBenchmark.average_vacancy_rate;
    return Number.isFinite(Number(rate)) ? Number(rate) * 12 / 100 : null;
  }
  function renderPositioning(yieldValue, months, userEntered) {
    var box = $("rentalPositioning");
    if (!box) return;
    var benchmarkYield = rentalBenchmark && Number(rentalBenchmark.income_yield);
    var benchmarkVacancy = rentalBenchmark && Number(rentalBenchmark.vacancy_rate);
    if (!Number.isFinite(yieldValue) || !Number.isFinite(months)
        || !Number.isFinite(benchmarkYield) || !Number.isFinite(benchmarkVacancy)) {
      box.className = "analysis-card rental-positioning pending";
      box.innerHTML = '<div class="positioning-copy"><span class="eyebrow">MARKET POSITION</span><h3>시장가 기준 순소득수익률 × 공실안정성</h3><p>시장가 수익률과 최근 1년 공실 기준을 함께 확인합니다.</p></div><div class="positioning-pending">판정 보류 · 현재 시장가와 R-ONE 기준자료가 모두 확인되어야 위치를 판정할 수 있습니다.</div>';
      return;
    }
    var vacancyRate = months / 12 * 100;
    var stable = 100 - vacancyRate;
    var benchmarkStable = 100 - benchmarkVacancy;
    var yieldSpan = Math.max(2, Math.abs(benchmarkYield) * 0.8);
    var stableSpan = Math.max(12, benchmarkVacancy * 1.5);
    var x = Math.max(8, Math.min(92, 50 + (yieldValue - benchmarkYield) / yieldSpan * 42));
    var y = Math.max(8, Math.min(92, 50 - (stable - benchmarkStable) / stableSpan * 42));
    var highYield = yieldValue >= benchmarkYield;
    var highStable = stable >= benchmarkStable;
    var verdict = !userEntered
      ? (highYield ? "시장 대비 고수익 후보" : "수익개선 검토")
      : highYield && highStable ? "고수익·안정형"
        : highYield ? "고수익·위험형" : highStable ? "안정·저수익형" : "수익개선 필요형";
    var source = userEntered
      ? "공실 기준: 사용자 입력 · 수익률 비교: " + benchmarkSource
      : "공실 기준: 소규모 상가 전국 전체 평균 · 수익률 비교: " + benchmarkSource;
    var comparison = "오피스텔 평균 수익률 " + benchmarkYield.toFixed(2) + "% · 적용 공실률 "
      + benchmarkVacancy.toFixed(1) + "%";
    var peerDots = rentalBenchmarkItems.map(function (item) {
      var itemYield = Number(item.income_yield);
      var itemStable = Number(item.stability_score);
      if (!Number.isFinite(itemYield) || !Number.isFinite(itemStable)) return "";
      var left = Math.max(4, Math.min(96, 50 + (itemYield - benchmarkYield) / yieldSpan * 42));
      var top = Math.max(4, Math.min(96, 50 - (itemStable - benchmarkStable) / stableSpan * 42));
      return '<i class="positioning-peer" style="left:' + left + '%;top:' + top
        + '%" title="' + escapeHtml(item.region_name || "비교지역") + '"></i>';
    }).join("");
    box.className = "analysis-card rental-positioning";
    box.innerHTML = '<div class="positioning-copy"><span class="eyebrow">MARKET POSITION</span><h3>시장가 기준 순소득수익률 × 공실안정성</h3><p>현재 실거래 기준가로 환산한 순소득수익률과 1년 공실 데이터를 오피스텔 수익률 기준선과 비교합니다.</p><strong class="positioning-verdict">' + escapeHtml(verdict) + '</strong><div class="positioning-source">' + escapeHtml(source) + '<br>' + escapeHtml(comparison) + '<br>' + escapeHtml(benchmarkNotice) + '</div></div><div><div class="positioning-map"><span class="positioning-quadrant pq-tl">안정·저수익형</span><span class="positioning-quadrant pq-tr">고수익·안정형</span><span class="positioning-quadrant pq-bl">수익개선 필요형</span><span class="positioning-quadrant pq-br">고수익·위험형</span><span class="positioning-axis x">시장가 기준 순소득수익률 →</span><span class="positioning-axis y">공실안정성</span>' + peerDots + '<i class="positioning-dot" style="left:' + x + '%;top:' + y + '%"></i></div><div class="positioning-legend"><span>R-ONE 비교지역</span><strong>공실 ' + months.toFixed(1) + '개월 · 순소득 ' + yieldValue.toFixed(2) + '%</strong><span>' + (userEntered ? "사용자 입력" : "전국 전체 평균") + '</span></div></div>';
  }
  async function loadRentalBenchmark(id, seq) {
    rentalBenchmark = null; rentalBenchmarkItems = []; benchmarkSource = ""; benchmarkNotice = "";
    if (!id) return;
    try {
      var response = await fetch("/api/analysis/rental-benchmark?building_id=" + encodeURIComponent(id)
        + "&property_type=officetel", { credentials: "same-origin" });
      var payload = response.ok ? await response.json() : null;
      if (seq !== buildingSequence || String(id) !== loadedBuildingId) return;
      var candidate = payload && payload.available !== false && (payload.benchmark || payload);
      rentalBenchmark = candidate != null && (typeof candidate === "object" || typeof candidate === "number") ? candidate : null;
      rentalBenchmarkItems = payload && Array.isArray(payload.items) ? payload.items : [];
      var source = payload && (payload.source || candidate && candidate.source);
      benchmarkSource = typeof source === "string" ? source : source && (source.provider + " 오피스텔" + (candidate && candidate.period ? " · " + monthLabel(candidate.period) : "")) || "";
      benchmarkNotice = source && source.notice || "";
      var months = benchmarkMonths();
      $("rentalVacancyMonthsHint").textContent = months == null
        ? "전국 전체 공실 평균을 확인할 수 없어 사용자 입력을 기다립니다."
        : "소규모 상가 전국 전체 평균 " + months.toFixed(1) + "개월"
          + (candidate && candidate.vacancy_period ? " (" + quarterLabel(candidate.vacancy_period) + ")" : "")
          + " · 직접 입력 시 사용자 값 우선";
      calculate();
    } catch (ignore) {
      if (seq !== buildingSequence || String(id) !== loadedBuildingId) return;
      rentalBenchmark = null;
      $("rentalVacancyMonthsHint").textContent = "R-ONE 평균을 불러오지 못했습니다. 직접 입력할 수 있습니다.";
      calculate();
    }
  }
  function calculate() {
    var purchase = n("rentalPurchasePrice");
    var market = n("rentalMarketPrice");
    var deposit = n("rentalDeposit");
    var rent = n("rentalMonthlyRent");
    var enteredMonths = $("rentalVacancyMonths").value.trim() === "" ? null : n("rentalVacancyMonths");
    var resolvedMonths = enteredMonths != null ? Math.min(12, Math.max(0, enteredMonths)) : benchmarkMonths();
    $("rentalVacancyRate").value = resolvedMonths == null ? "" : (resolvedMonths / 12 * 100).toFixed(1);
    $("rentalVacancyRateHint").textContent = resolvedMonths == null
      ? "공실 개월을 입력하거나 전국 전체 평균을 불러와야 합니다."
      : enteredMonths != null ? "사용자 입력 공실기간에서 자동계산" : "R-ONE 소규모 상가 전국 전체 평균 적용";
    var vacancy = resolvedMonths == null ? 0 : resolvedMonths / 12;
    var acquisitionTax = n("rentalAcquisitionTax");
    var brokerFee = n("rentalBrokerFee");
    var acquisition = acquisitionTax + brokerFee;
    var tax = n("rentalPropertyTax");
    var costs = tax + n("rentalManagementCost") + n("rentalOtherCost");
    var loan = n("rentalLoanAmount");
    if (resolvedMonths == null) {
      $("rentalResults").innerHTML = '<div class="rental-calculation-warning"><b>공실 기준이 필요합니다</b><span>최근 1년 공실 개월을 입력하거나 R-ONE 전국 전체 평균이 연결되어야 수익률을 계산합니다.</span></div>';
      renderPositioning(NaN, null, false);
      window.__rentalAnalysisResult = {
        purchasePrice: purchase, vacancyMonths: null, vacancyRate: null,
        vacancySource: "unavailable", benchmark: null, ready: false,
      };
      return;
    }
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
      (resolvedMonths == null ? '<div class="rental-calculation-warning"><b>공실 기준 미반영 임시 계산</b><span>최근 1년 공실 개월을 입력하거나 R-ONE 전국 전체 평균이 연결되면 결과가 자동으로 갱신됩니다.</span></div>' : "")
      + card("대출 후 월 순현금", money(cashFlow / 12, 1), "순영업소득에서 월 원리금 차감", "primary")
      + card("자기자본 수익률", percent(cashReturn), "실투자금 " + money(invested), cashReturn < 0 ? "warning" : "")
      + card("비용 반영 순수익률", percent(netYield), "순영업소득 " + money(noi) + "/년")
      + card("표면수익률", percent(grossYield), "공실·비용 차감 전")
      + card("현재 실거래 기준 수익률", market ? percent(marketYield) : "기준가 입력 필요", market ? "현재 기준가 " + money(market) : "최근 실거래 자동연결 예정")
      + card("월 대출 상환액", money(debt.monthly, 1), $("rentalLoanMethod").selectedOptions[0].text)
      + card("DSCR", dscr == null ? "대출 없음" : dscr.toFixed(2) + "배", dscr == null ? "대출상환 부담 없음" : (dscr >= 1.2 ? "임대수익 상환여력 양호" : "상환여력 주의"), dscr != null && dscr < 1.2 ? "warning" : "")
       + card("연간 보유비용", money(costs), "보유세·관리비·수선비 합계");
    renderPositioning(market > 0 ? marketYield : NaN, resolvedMonths, enteredMonths != null);
    window.__rentalAnalysisResult = {
      purchasePrice: purchase, annualRent: annualRent, noi: noi, invested: invested,
      debtService: debt.annual, cashFlow: cashFlow, grossYield: grossYield,
      netYield: netYield, cashReturn: cashReturn, dscr: dscr,
      marketYield: marketYield, vacancyMonths: resolvedMonths,
      vacancyRate: resolvedMonths == null ? null : resolvedMonths / 12 * 100,
      vacancySource: enteredMonths != null ? "user" : rentalBenchmark ? "rone" : "unavailable",
      benchmark: rentalBenchmark,
      ready: true,
    };
    if (loadedBuildingId) window.livingstayAnalysisReportActions(
      $("rentalReportActions"), loadedBuildingId,
      loadedBuilding && (loadedBuilding.display_building_name || loadedBuilding.building_name)
    );
  }
  function updateEstimatedTax() {
    if (taxManuallyEdited) return;
    var estimated = estimateTax(n("rentalPurchasePrice"));
    $("rentalPropertyTax").value = estimated ? String(estimated) : "";
    $("rentalTaxHint").textContent = estimated
      ? "비주거용 추정 과세표준·부가세목 적용: 연 " + money(estimated, 1)
      : "매입가 입력 시 자동 추정되며 직접 수정할 수 있습니다.";
  }
  function updateAcquisitionCosts() {
    var purchasePrice = n("rentalPurchasePrice");
    $("rentalAcquisitionTax").value = purchasePrice
      ? String(Math.round(purchasePrice * 0.046 * 10) / 10) : "";
    $("rentalBrokerFee").value = purchasePrice
      ? String(Math.round(purchasePrice * 0.009 * 10) / 10) : "";
  }
  function setMarketStatus(message, mode) {
    $("rentalMarketPriceHint").textContent = message;
    $("rentalMarketPrice").dataset.valueSource = mode || "";
  }
  function clearMarketEvidence() {
    $("rentalMarketEvidence").classList.add("hidden");
    $("rentalMarketEvidence").open = false;
    $("rentalMarketEvidenceList").replaceChildren();
  }
  function renderMarketEvidence(result) {
    var transactions = Array.isArray(result.transactions) ? result.transactions : [];
    if (transactions.length !== Number(result.sample_count)) {
      clearMarketEvidence();
      return false;
    }
    var evidence = $("rentalMarketEvidence");
    var list = $("rentalMarketEvidenceList");
    list.replaceChildren();
    transactions.forEach(function (transaction) {
      var row = document.createElement("div");
      row.className = "rental-market-evidence-row";
      var badge = document.createElement("span");
      badge.className = "area-match " + (transaction.area_match === "exact" ? "exact" : "similar");
      badge.textContent = transaction.area_match === "exact" ? "동일 면적" : "유사 면적";
      var date = document.createElement("time");
      date.textContent = String(transaction.deal_date || "").replace(/-/g, ".");
      var area = document.createElement("span");
      area.textContent = Number(transaction.area_sqm).toLocaleString("ko-KR") + "㎡";
      var price = document.createElement("strong");
      price.textContent = money(transaction.price);
      row.append(badge, date, area, price);
      list.appendChild(row);
    });
    $("rentalMarketEvidenceSummary").textContent = "기준가 산정 거래 " + transactions.length + "건 보기";
    evidence.classList.remove("hidden");
    return true;
  }
  async function loadMarketPrice(id, seq) {
    var area = n("rentalUnitArea");
    if (!id || !area) {
      clearMarketEvidence();
      automaticMarketPrice = null;
      if (!marketPriceManuallyEdited) $("rentalMarketPrice").value = "";
      $("rentalMarketPrice").placeholder = "호실 면적을 먼저 선택";
      setMarketStatus("호실 전용면적을 선택하거나 입력하면 최근 실거래 중앙값을 조회합니다.", "");
      calculate();
      return;
    }
    $("rentalMarketPrice").placeholder = "최근 실거래 조회 중";
    clearMarketEvidence();
    setMarketStatus("선택 면적의 최근 36개월 매매 실거래를 확인하고 있습니다.", "loading");
    try {
      var response = await fetch("/api/analysis/rental-market-price?building_id="
        + encodeURIComponent(id) + "&area_sqm=" + encodeURIComponent(area), { credentials: "same-origin" });
      var result = await response.json();
      if (seq !== buildingSequence || String(area) !== String(n("rentalUnitArea"))) return;
      if (!response.ok || !result.ok) {
        clearMarketEvidence();
        automaticMarketPrice = null;
        if (!marketPriceManuallyEdited) $("rentalMarketPrice").value = "";
        $("rentalMarketPrice").placeholder = "직접 입력";
        setMarketStatus(result.reason || "실거래 자료가 부족해 자동 기준가를 계산할 수 없습니다.", "unavailable");
        calculate();
        return;
      }
      if (!renderMarketEvidence(result)) {
        automaticMarketPrice = null;
        if (!marketPriceManuallyEdited) $("rentalMarketPrice").value = "";
        $("rentalMarketPrice").placeholder = "직접 입력";
        setMarketStatus("실거래 계산 표본과 근거 목록이 일치하지 않아 자동 기준가를 제공하지 않습니다.", "error");
        calculate();
        return;
      }
      automaticMarketPrice = Number(result.median_price);
      if (!marketPriceManuallyEdited) {
        $("rentalMarketPrice").value = String(automaticMarketPrice);
        calculate();
      }
      var range = result.area_range || {};
      var details = [
        result.match_type === "exact" ? "동일 면적" : "유사 면적",
        "중앙값 " + money(automaticMarketPrice),
        String(result.latest_deal_date || "").replace(/-/g, ".") + " 기준",
        "표본 " + result.sample_count + "건",
      ];
      if (result.match_type === "similar" && Number(range.min) > 0 && Number(range.max) > 0) {
        details.push(Number(range.min).toLocaleString("ko-KR") + "~"
          + Number(range.max).toLocaleString("ko-KR") + "㎡");
      }
      setMarketStatus(details.join(" · ")
        + (marketPriceManuallyEdited ? " · 사용자 수정값 사용 중" : " · 자동값 사용 중"),
        marketPriceManuallyEdited ? "manual" : "automatic");
    } catch (ignore) {
      if (seq === buildingSequence) {
        clearMarketEvidence();
        automaticMarketPrice = null;
        if (!marketPriceManuallyEdited) $("rentalMarketPrice").value = "";
        $("rentalMarketPrice").placeholder = "직접 입력";
        setMarketStatus("최근 실거래를 불러오지 못했습니다. 직접 입력할 수 있습니다.", "error");
        calculate();
      }
    }
  }
  async function loadBuilding() {
    var id = new URLSearchParams(location.search).get("building_id");
    var seq = ++buildingSequence;
    if (!id) {
      loadedBuildingId = "";
      loadedBuilding = null;
      rentalBenchmark = null;
      rentalBenchmarkItems = [];
      benchmarkSource = "";
      benchmarkNotice = "";
      window.__rentalAnalysisBuilding = null;
      $("rentalReportActions").classList.add("hidden");
      $("rentalReportActions").replaceChildren();
      marketPriceManuallyEdited = false;
      automaticMarketPrice = null;
      clearMarketEvidence();
      $("rentalBuildingName").textContent = "분석할 건물을 선택해 주세요";
      $("rentalUnitArea").value = "";
      $("rentalUnitAreaOptions").innerHTML = "";
      $("rentalMarketPrice").value = "";
      $("rentalMarketPrice").placeholder = "호실 면적을 먼저 선택";
      $("rentalVacancyMonthsHint").textContent = "건물을 선택하면 R-ONE 전국 전체 공실 평균을 확인합니다.";
      $("rentalUnitAreaHint").textContent = "건물을 선택하면 확인된 호실 면적을 불러옵니다.";
      setMarketStatus("건물과 호실 면적을 선택하면 최근 실거래 중앙값을 불러옵니다.", "");
      calculate();
      return;
    }
    if (loadedBuildingId !== String(id)) {
      loadedBuildingId = String(id);
      marketPriceManuallyEdited = false;
      automaticMarketPrice = null;
      clearMarketEvidence();
      $("rentalUnitArea").value = "";
      $("rentalMarketPrice").value = "";
      $("rentalMarketPrice").placeholder = "호실 면적을 먼저 선택";
      setMarketStatus("호실 면적 목록을 확인하고 있습니다.", "loading");
    }
    try {
      var responses = await Promise.all([
        fetch("/api/building/" + encodeURIComponent(id), { credentials: "same-origin" }),
        fetch("/api/building/" + encodeURIComponent(id) + "/area-types", { credentials: "same-origin" }),
      ]);
      var data = responses[0].ok ? await responses[0].json() : null;
      var areas = responses[1].ok ? await responses[1].json() : null;
      if (seq !== buildingSequence) return;
      if (data) {
        loadedBuilding = data;
        window.__rentalAnalysisBuilding = data;
        $("rentalBuildingName").textContent = data.display_building_name || data.building_name || "선택 건물";
        if (window.setAnalysisBuildingStatus) {
          window.setAnalysisBuildingStatus(data.display_building_name || data.building_name || "선택 건물");
        }
      }
      await loadRentalBenchmark(id, seq);
      if (seq !== buildingSequence) return;
      var items = areas && Array.isArray(areas.items) ? areas.items : [];
      $("rentalUnitAreaOptions").innerHTML = items.map(function (item) {
        var sqm = Number(item.sqm);
        return '<option value="' + sqm.toLocaleString("ko-KR") + '㎡"></option>';
      }).join("");
      if (items.length) {
        $("rentalUnitAreaHint").textContent = "확인된 면적 " + items.length + "개 중 선택하거나 직접 입력할 수 있습니다.";
        await loadMarketPrice(id, seq);
      } else {
        $("rentalUnitAreaHint").textContent = "확인된 호실 면적이 없어 직접 입력해 주세요.";
        setMarketStatus("호실 전용면적을 직접 입력하면 최근 실거래를 조회합니다.", "unavailable");
      }
    } catch (ignore) {
      if (seq === buildingSequence) {
        $("rentalMarketPrice").placeholder = "직접 입력";
        $("rentalMarketPriceHint").textContent = "최근 실거래를 불러오지 못했습니다. 직접 입력할 수 있습니다.";
      }
    }
  }
  ids.forEach(function (id) {
    $(id).addEventListener("input", function () {
      if (id === "rentalPropertyTax") taxManuallyEdited = true;
      if (id === "rentalMarketPrice") {
        marketPriceManuallyEdited = true;
        if ($(id).value) {
          setMarketStatus(automaticMarketPrice
            ? "사용자 수정값 사용 중 · 자동 중앙값 " + money(automaticMarketPrice)
            : "사용자가 직접 입력한 실거래 기준가입니다.", "manual");
        }
      }
      if (id === "rentalUnitArea") {
        marketPriceManuallyEdited = false;
        automaticMarketPrice = null;
        clearTimeout(areaLookupTimer);
        areaLookupTimer = setTimeout(function () {
          loadMarketPrice(loadedBuildingId, buildingSequence);
        }, 250);
      }
      if (id === "rentalPurchasePrice") {
        updateAcquisitionCosts();
        updateEstimatedTax();
      }
      calculate();
    });
  });
  $("rentalLoanMethod").addEventListener("change", calculate);
  $("rentalCalculate").addEventListener("click", calculate);
  $("rentalReset").addEventListener("click", function () {
    taxManuallyEdited = false;
    marketPriceManuallyEdited = false;
    automaticMarketPrice = null;
    clearMarketEvidence();
    clearTimeout(areaLookupTimer);
    ids.forEach(function (id) { $(id).value = ""; });
    $("rentalVacancyMonths").value = "";
    $("rentalVacancyRate").value = "";
    $("rentalManagementCost").value = "0";
    $("rentalOtherCost").value = "0";
    $("rentalLoanAmount").value = "0";
    $("rentalLoanRate").value = "4.5";
    $("rentalLoanYears").value = "20";
    $("rentalLoanMethod").value = "interest";
    $("rentalUnitAreaHint").textContent = loadedBuildingId
      ? "면적을 다시 선택하거나 입력해 주세요." : "건물을 선택하면 확인된 호실 면적을 불러옵니다.";
    setMarketStatus("호실 전용면적을 선택하거나 입력하면 최근 실거래 중앙값을 조회합니다.", "");
    $("rentalResults").innerHTML = '<article class="analysis-card rental-empty"><strong>임대조건을 입력해 주세요</strong><span>매입가·보증금·월세를 입력하면 대출과 비용을 반영한 수익률을 계산합니다.</span></article>';
  });
  window.addEventListener("livingstay:analysis-reset", function () {
    $("rentalReset").click();
  });
  window.loadRentalAnalysis = loadBuilding;
  loadBuilding();
}());