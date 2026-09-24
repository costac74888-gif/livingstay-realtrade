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
  var positionChart = null;
  var positionMode = "net";
  var rafId = 0;
  var vacancyAssumed = true;
  var sliderInputs = {};
  var sliderBounds = Object.create(null);
  var sliderBasePrice = null;
  var rentCenterBase = null;
  var rentCenterEdited = false;
  var invalidRentalInputs = Object.create(null);
  var lastValidRentalInputs = Object.create(null);
  var sliderChangeTimer = 0;
  var sliderChangeField = "";
  var lastCalculated = null;
  var loadingSharedValues = false;
  var sharedFieldParams = {
    r_unit_area: "rentalUnitArea", r_purchase: "rentalPurchasePrice", r_deposit: "rentalDeposit",
    r_rent: "rentalMonthlyRent", r_vacancy: "rentalVacancyMonths", r_loan: "rentalLoanAmount",
    r_rate: "rentalLoanRate", r_years: "rentalLoanYears", r_method: "rentalLoanMethod",
    r_management: "rentalManagementCost", r_other: "rentalOtherCost",
  };
  var sharedValuesRestored = false;
  var invalidRentalUrlFields = Object.create(null);
  var ids = [
    "rentalUnitArea", "rentalPurchasePrice", "rentalMarketPrice", "rentalDeposit", "rentalMonthlyRent",
    "rentalVacancyMonths", "rentalVacancyRate", "rentalAcquisitionTax", "rentalBrokerFee", "rentalPropertyTax",
    "rentalManagementCost", "rentalOtherCost", "rentalLoanAmount", "rentalBasisTotal",
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
    "월 순현금흐름": "이자 차감 후 매달 남는 금액",
    "실투자금": "매입가·취득비용에서 보증금과 대출을 뺀 금액",
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
  function formatInputValue(field, value) {
    if (value === "" || value == null || !Number.isFinite(Number(value))) return "입력";
    if (field === "rentalVacancyMonths") return Number(value).toLocaleString("ko-KR", {
      maximumFractionDigits: 1,
    }) + "개월";
    return window.analysisSliderUtils.formatMan(Number(value));
  }
  function rentalHardKind(field) {
    return ({
      rentalPurchasePrice: "purchase",
      rentalDeposit: "deposit",
      rentalMonthlyRent: "rent",
      rentalVacancyMonths: "vacancy",
      rentalLoanAmount: "loan",
    })[field] || "";
  }
  function clampRentalValue(field, value) {
    var kind = rentalHardKind(field);
    return kind ? window.analysisSliderUtils.clampHard(kind, value,
      field === "rentalLoanAmount" ? n("rentalPurchasePrice") : undefined) : Number(value);
  }
  function setRentalInputError(field, message) {
    var error = document.querySelector('[data-rental-input-error="' + field + '"]');
    if (!error) return;
    error.textContent = message || "";
    error.hidden = !message;
  }
  function rentalLimitText(field, value) {
    if (field === "rentalVacancyMonths") {
      return Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "개월";
    }
    if (value >= 10000 && value % 10000 === 0) return (value / 10000).toLocaleString("ko-KR") + "억";
    return Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "만";
  }
  function updateRentalLimitLabels(bounds) {
    Object.keys(bounds).forEach(function (field) {
      var node = document.querySelector('[data-rental-limits="' + field + '"]');
      var rangeBounds = bounds[field];
      if (!node) return;
      var edges = node.querySelectorAll("span");
      if (!rangeBounds) {
        if (edges[0]) edges[0].textContent = "—";
        if (edges[1]) edges[1].textContent = "—";
        return;
      }
      if (edges[0]) edges[0].textContent = rentalLimitText(field, rangeBounds.min);
      if (edges[1]) edges[1].textContent = rentalLimitText(field, rangeBounds.max);
    });
  }
  function cleanInvalidRentalParams(keys) {
    if (!keys.length) return;
    var params = new URLSearchParams(location.search);
    keys.forEach(function (key) { params.delete(key); });
    var suffix = params.toString();
    history.replaceState(history.state, "", location.pathname + (suffix ? "?" + suffix : "") + location.hash);
  }
  function warnInvalidRentalParam(key, value) {
    console.warn("[slider] 비정상 값 무시:", key, value);
  }
  function purchaseBounds() {
    var utils = window.analysisSliderUtils;
    var market = utils.clampHard("purchase", n("rentalMarketPrice"));
    var current = utils.clampHard("purchase", n("rentalPurchasePrice"));
    sliderBasePrice = market != null ? market : current;
    var safeBase = sliderBasePrice;
    if (safeBase == null) return null;
    var bounds = utils.purchaseBounds(safeBase);
    bounds.min = Math.max(utils.HARD_CAPS.purchase[0], Math.floor(bounds.min / 1000) * 1000);
    bounds.max = utils.HARD_CAPS.purchase[1];
    bounds.step = 1000;
    return bounds;
  }
  function rentCenter() {
    var rent = n("rentalMonthlyRent");
    var utils = window.analysisSliderUtils;
    if (rent > 0) return utils.clampHard("rent", rent);
    var market = utils.clampHard("purchase", n("rentalMarketPrice"));
    var purchase = utils.clampHard("purchase", n("rentalPurchasePrice"));
    if (purchase == null) purchase = sliderBasePrice || market;
    var yieldRate = rentalBenchmark && Number(rentalBenchmark.income_yield);
    if (purchase > 0 && Number.isFinite(yieldRate) && yieldRate > 0) {
      return utils.clampHard("rent", purchase * yieldRate / 100 / 12);
    }
    var base = market || sliderBasePrice || purchase;
    return base > 0 ? utils.clampHard("rent", base * 0.005) : null;
  }
  function applyInvalidRentalUrlDefaults() {
    var utils = window.analysisSliderUtils;
    var seeded = false;
    if (invalidRentalUrlFields.rentalPurchasePrice && n("rentalPurchasePrice") <= 0) {
      var market = utils.clampHard("purchase", n("rentalMarketPrice"));
      if (market != null) {
        $("rentalPurchasePrice").value = String(market);
        lastValidRentalInputs.rentalPurchasePrice = market;
        updateAcquisitionCosts();
        updateEstimatedTax();
        delete invalidRentalUrlFields.rentalPurchasePrice;
        seeded = true;
      }
    }
    if (invalidRentalUrlFields.rentalMonthlyRent && n("rentalMonthlyRent") <= 0) {
      var rent = utils.clampHard("rent", rentCenter());
      if (rent == null) {
        var marketBase = utils.clampHard("purchase", n("rentalMarketPrice"));
        rent = marketBase == null ? null : utils.clampHard("rent", marketBase * 0.005);
      }
      if (rent != null) {
        $("rentalMonthlyRent").value = String(rent);
        lastValidRentalInputs.rentalMonthlyRent = rent;
        delete invalidRentalUrlFields.rentalMonthlyRent;
        seeded = true;
      }
    }
    if (seeded) resetRentCenterBase();
  }
  function resetRentCenterBase() {
    var utils = window.analysisSliderUtils;
    var next = utils.clampHard("rent", rentCenter());
    rentCenterBase = next;
    rentCenterEdited = false;
  }
  function rentalSliderConfiguration() {
    var utils = window.analysisSliderUtils;
    if (!utils) throw new Error("공통 슬라이더 설정을 불러오지 못했습니다.");
    var purchase = purchaseBounds();
    var purchaseValue = n("rentalPurchasePrice");
    var depositMax = utils.HARD_CAPS.deposit[1];
    var rent = rentCenterBase == null ? null : utils.rentBounds(rentCenterBase);
    if (rent) {
      rent.min = Math.max(utils.HARD_CAPS.rent[0], rent.min);
      rent.max = utils.HARD_CAPS.rent[1];
      rent.step = 1;
    }
    return {
      rentalPurchasePrice: purchase,
      rentalLoanAmount: purchase && purchaseValue > 0 ? {
        min: 0,
        max: loanMaximum(),
        step: 1000,
      } : null,
      rentalDeposit: purchase && purchaseValue > 0 ? {
        min: 0, max: depositMax, step: 100,
      } : null,
      rentalMonthlyRent: rent,
      rentalVacancyMonths: { min: 0, max: 12, step: 1 },
    };
  }
  function loanMaximum() {
    var purchase = n("rentalPurchasePrice");
    return Math.max(0, Math.min(purchase, 400000));
  }
  function syncSliderBounds(expandField, skipField) {
    var utils = window.analysisSliderUtils;
    if (!utils) throw new Error("공통 슬라이더 설정을 불러오지 못했습니다.");
    ["rentalPurchasePrice", "rentalDeposit", "rentalMonthlyRent",
      "rentalVacancyMonths", "rentalLoanAmount"].forEach(function (field) {
      var value = $(field).value;
      if (value !== "" && clampRentalValue(field, value) == null) {
        var corrected = field === "rentalLoanAmount" && n("rentalPurchasePrice") > 0
          ? Math.min(Number(value), loanMaximum())
          : lastValidRentalInputs[field];
        $(field).value = corrected == null ? "" : String(corrected);
        if (corrected != null) lastValidRentalInputs[field] = corrected;
      } else if (value !== "") {
        lastValidRentalInputs[field] = clampRentalValue(field, value);
      }
    });
    var bounds = rentalSliderConfiguration();
    if (expandField && bounds[expandField]) {
      bounds[expandField] = utils.includeValue(bounds[expandField], n(expandField));
    }
    sliderBounds = bounds;
    Object.keys(bounds).forEach(function (field) {
      var range = sliderInputs[field];
      if (!range || field === skipField) return;
      var rangeBounds = bounds[field];
      range.disabled = !rangeBounds;
      if (!rangeBounds) {
        range.min = "0"; range.max = "0"; range.step = "1"; range.value = "0";
        return;
      }
      range.min = String(rangeBounds.min);
      range.max = String(rangeBounds.max);
      range.step = String(rangeBounds.step);
      var amount = n(field);
      range.value = String(amount > 0 || field === "rentalVacancyMonths"
        ? utils.nearest(amount, rangeBounds) : rangeBounds.min);
    });
    var loanCap = loanMaximum();
    if (n("rentalLoanAmount") > loanCap) $("rentalLoanAmount").value = String(loanCap);
    Object.keys(bounds).forEach(function (field) {
      var button = document.querySelector('[data-rental-value="' + field + '"]');
      if (button) button.textContent = formatInputValue(field, $(field).value);
    });
    updateRentalLimitLabels(bounds);
    var buyHeading = document.querySelector("#rentalSliders .rental-buy-heading");
    if (buyHeading) buyHeading.textContent = "매수 조건 (대출금리 연 " + formatInputValue("rate", n("rentalLoanRate")).replace("만원", "%")
      + ", " + $("rentalLoanMethod").selectedOptions[0].text + ")";
  }
  function updateRentalUrl() {
    if (window.__analysisShareToken) return;
    var params = new URLSearchParams(location.search);
    params.set("mode", "rental");
    Object.keys(sharedFieldParams).forEach(function (key) {
      var field = sharedFieldParams[key], value = $(field).value;
      if (value == null || value === "") params.delete(key);
      else params.set(key, value);
    });
    params.set("r_yieldmode", positionMode);
    [["buy", n("rentalPurchasePrice")], ["rent", n("rentalMonthlyRent")]]
      .forEach(function (entry) {
        if (entry[1] > 0) params.set(entry[0], String(entry[1]));
        else params.delete(entry[0]);
      });
    history.replaceState({}, "", "/analysis" + (params.toString() ? "?" + params.toString() : ""));
  }
  function cancelRentalSliderChange() {
    clearTimeout(sliderChangeTimer);
    sliderChangeTimer = 0;
    sliderChangeField = "";
  }
  function queueRentalSliderChange(field, directEntry) {
    cancelRentalSliderChange();
    sliderChangeField = field;
    var queuedLoadSequence = buildingSequence;
    var queuedBuildingId = loadedBuildingId;
    sliderChangeTimer = setTimeout(function () {
      sliderChangeTimer = 0;
      var activeBuildingId = new URLSearchParams(location.search).get("building_id") || "";
      if (queuedLoadSequence !== buildingSequence
        || queuedBuildingId !== loadedBuildingId
        || queuedBuildingId !== activeBuildingId
        || sliderChangeField !== field) {
        sliderChangeField = "";
        return;
      }
      var changedField = field;
      sliderChangeField = "";
      var dependentChange = changedField === "rentalPurchasePrice" || changedField === "rentalDeposit";
      if (dependentChange) {
        var cap = loanMaximum();
        if (n("rentalLoanAmount") > cap) {
          $("rentalLoanAmount").value = String(cap);
          updateRentalUrl();
        }
      }
      if (!directEntry && dependentChange) syncSliderBounds(null, changedField);
      updateRentalUrl();
      scheduleCalculate();
    }, 300);
  }
  function makeSliderRow(field, label, step) {
    var units = {
      rentalPurchasePrice: "천만원 단위",
      rentalLoanAmount: "천만원 단위 · 절대 상한 40억",
      rentalDeposit: "백만원 단위",
      rentalMonthlyRent: "만원 단위",
      rentalVacancyMonths: "1개월 단위",
    };
    return '<div class="rental-slider-row" data-rental-row="' + field + '"><div class="rental-slider-head"><label for="rentalSlider' + field.slice(6) + '">' + label + '</label>'
      + '<span><button type="button" class="rental-value-button slider-value" data-rental-value="' + field + '" data-value-for="' + field + '" aria-label="' + label + ' 직접 입력">' + formatInputValue(field, $(field).value) + '</button>'
      + (field === "rentalVacancyMonths" ? '<i class="rental-assumption-badge" data-vacancy-assumption>가정값</i>' : '')
      + '</span></div><input class="rental-range" type="range" id="rentalSlider' + field.slice(6) + '" data-rental-slider="' + field + '" min="0" max="100" step="' + step + '" value="0" aria-label="' + label + '">'
      + '<span class="rental-range-limits" data-rental-limits="' + field + '"><span>—</span><small>' + units[field] + '</small><span>—</span></span>'
      + '<span class="rental-slider-input-error" data-rental-input-error="' + field + '" role="alert" hidden></span></div>';
  }
  function setupRentalSliders() {
    var host = $("rentalSliders");
    if (!host) return;
    host.innerHTML = '<div class="rental-panel-title"><div><span class="eyebrow">SCENARIO BUILDER</span><h3>조건을 조정해 수익을 확인하세요</h3></div></div>'
      + '<section class="rental-slider-group"><h3 class="rental-buy-heading">매수 조건</h3><div class="rental-slider-list">'
      + makeSliderRow("rentalPurchasePrice", "매수가", 1000)
      + makeSliderRow("rentalLoanAmount", "대출금 (매수가 이내)", 1000)
      + '</div></section><section class="rental-slider-group"><h3>임대 조건</h3><div class="rental-slider-list">'
      + makeSliderRow("rentalDeposit", "보증금", 100)
      + makeSliderRow("rentalMonthlyRent", "월세", 1)
      + makeSliderRow("rentalVacancyMonths", "공실", 1)
      + '</div></section><p class="rental-slider-hint">값을 눌러 직접 입력할 수 있습니다. 슬라이더는 가장 가까운 단위에, 계산은 입력한 정확한 값에 맞춥니다.</p>';
    host.querySelectorAll("[data-rental-slider]").forEach(function (range) {
      sliderInputs[range.dataset.rentalSlider] = range;
    });
    host.addEventListener("input", function (event) {
      var range = event.target.closest("[data-rental-slider]");
      if (!range) return;
      var field = range.dataset.rentalSlider;
      delete invalidRentalUrlFields[field];
      var safeValue = clampRentalValue(field, range.value);
      if (safeValue == null) {
        range.value = $(field).value || range.min;
        setRentalInputError(field, field === "rentalMonthlyRent"
          ? "월세는 1~1,000만원 범위로 입력하세요" : "입력값이 허용 범위를 벗어났습니다.");
        return;
      }
      range.value = String(safeValue);
      lastValidRentalInputs[field] = safeValue;
      invalidRentalInputs[field] = false;
      rentCenterEdited = true;
      setRentalInputError(field, "");
      if (field === "rentalVacancyMonths") vacancyAssumed = false;
      $(field).value = String(safeValue);
      var valueButton = document.querySelector('[data-rental-value="' + field + '"]');
      if (valueButton) valueButton.textContent = formatInputValue(field, safeValue);
      if (field === "rentalPurchasePrice") {
        updateAcquisitionCosts();
        updateEstimatedTax();
      }
      scheduleCalculate();
    });
    host.addEventListener("change", function (event) {
      var range = event.target.closest("[data-rental-slider]");
      if (!range) return;
      queueRentalSliderChange(range.dataset.rentalSlider, false);
    });
    host.addEventListener("click", function (event) {
      var button = event.target.closest("[data-rental-value]");
      if (!button) return;
      var field = button.dataset.rentalValue;
      if (button.querySelector("input")) return;
      var hardKind = rentalHardKind(field);
      var hardBounds = hardKind && window.analysisSliderUtils.HARD_CAPS[hardKind];
      var input = document.createElement("input");
      input.type = "number";
      input.step = field === "rentalVacancyMonths" ? "0.5" : "1";
      input.min = hardKind === "loan" ? "0" : hardBounds ? String(hardBounds[0]) : "0";
      input.max = hardKind === "loan" ? String(loanMaximum())
        : hardBounds ? String(hardBounds[1]) : "";
      input.value = $(field).value;
      input.setAttribute("aria-label", field === "rentalVacancyMonths" ? "연간 공실 개월" : "금액(만원)");
      setRentalInputError(field, "");
      button.textContent = "";
      button.appendChild(input);
      input.focus();
      input.select();
      var commit = function () {
        if (!button.contains(input)) return;
        delete invalidRentalUrlFields[field];
        var raw = input.value.trim();
        var parsed = raw === "" ? null : clampRentalValue(field, raw);
        if (raw !== "" && Number.isFinite(Number(raw)) && parsed == null) {
          setRentalInputError(field, field === "rentalMonthlyRent"
            ? "월세는 1~1,000만원 범위로 입력하세요" : "입력값이 허용 범위를 벗어났습니다.");
          button.textContent = formatInputValue(field, $(field).value);
          return;
        }
        if (parsed == null) setRentalInputError(field, "");
        if (parsed != null) {
          setRentalInputError(field, "");
          $(field).value = String(parsed);
          lastValidRentalInputs[field] = parsed;
          invalidRentalInputs[field] = false;
          if (field === "rentalMonthlyRent") {
            resetRentCenterBase();
          }
          rentCenterEdited = true;
          if (field === "rentalVacancyMonths") vacancyAssumed = false;
          if (field === "rentalPurchasePrice") {
            updateAcquisitionCosts();
            updateEstimatedTax();
          }
          var cap = loanMaximum();
          if (n("rentalLoanAmount") > cap) $("rentalLoanAmount").value = String(cap);
          syncSliderBounds(field);
          scheduleCalculate();
          queueRentalSliderChange(field, true);
          return;
        }
        syncSliderBounds();
        scheduleCalculate();
      };
      input.addEventListener("blur", commit, { once: true });
      input.addEventListener("keydown", function (keyEvent) {
        if (keyEvent.key === "Enter") { keyEvent.preventDefault(); input.blur(); }
        if (keyEvent.key === "Escape") { input.value = $(field).value; input.blur(); }
      });
    });
    syncSliderBounds();
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
  function vacancyTransform(months, averageMonths) {
    if (months <= averageMonths) return averageMonths > 0 ? 0.5 * months / averageMonths : 0;
    return averageMonths < 6 ? 0.5 + 0.5 * (months - averageMonths) / (6 - averageMonths) : 1;
  }
  function vacancyInverse(position, averageMonths) {
    if (position <= 0.5) return averageMonths > 0 ? 2 * position * averageMonths : 0;
    return averageMonths < 6 ? averageMonths + 2 * (position - 0.5) * (6 - averageMonths) : 6;
  }
  function benchmarkIncomeYield() {
    var national = rentalBenchmarkItems.find(function (item) {
      return item.region_level === "national" || String(item.region_code) === "00";
    });
    var candidate = national || (rentalBenchmark &&
      (rentalBenchmark.region_level === "national" || String(rentalBenchmark.region_code) === "00")
      ? rentalBenchmark : null);
    var value = candidate && Number(candidate.income_yield);
    return candidate && Number.isFinite(value) ? value : NaN;
  }
  function benchmarkName() {
    var national = rentalBenchmarkItems.some(function (item) {
      return item.region_level === "national" || String(item.region_code) === "00";
    }) || rentalBenchmark && (rentalBenchmark.region_level === "national" || String(rentalBenchmark.region_code) === "00");
    return national ? "전국 평균" : (rentalBenchmark && rentalBenchmark.region_name || "선택 지역") + " R-ONE 기준";
  }
  function normalizedRegionCode(value) {
    var code = String(value || "").trim();
    if (code.length >= 2 && /^\d+$/.test(code)) return ({ "51": "42", "52": "45" })[code.slice(0, 2)] || code.slice(0, 2);
    return "";
  }
  function selectedProvinceCode() {
    return normalizedRegionCode(loadedBuilding && (loadedBuilding.sgg_cd || loadedBuilding.region_code));
  }
  function selectedProvinceName() {
    var building = loadedBuilding || {};
    var text = [building.sido_nm, building.province_name, building.road_address, building.jibun_address, building.sgg_text]
      .filter(Boolean).join(" ");
    var names = [
      ["서울", /서울/], ["부산", /부산/], ["대구", /대구/], ["인천", /인천/],
      ["광주", /광주/], ["대전", /대전/], ["울산", /울산/], ["세종", /세종/],
      ["경기", /경기/], ["강원", /강원/], ["충북", /충청북|충북/], ["충남", /충청남|충남/],
      ["전북", /전북|전라북/], ["전남", /전라남|전남/], ["경북", /경상북|경북/],
      ["경남", /경상남|경남/], ["제주", /제주/],
    ];
    var found = names.find(function (entry) { return entry[1].test(text); });
    return found ? found[0] : "";
  }
  function selectedModeValue(result) {
    return positionMode === "equity" ? result.cashReturn : result.netYield;
  }
  function rentalQuadrantLabel(result, benchmarkYield, benchmarkMonths) {
    if (!result || result.vacancySource === "unavailable") return "조건 입력 대기";
    if (!Number.isFinite(benchmarkYield) || !Number.isFinite(benchmarkMonths)
        || !Number.isFinite(selectedModeValue(result))) return "판정 보류 · 비교 기준 자료 없음";
    if (result.vacancySource === "rone") return "판정 보류 · 공실 가정값 사용 중";
    var highReturn = selectedModeValue(result) >= benchmarkYield;
    var stable = result.vacancyMonths <= benchmarkMonths;
    if (highReturn && stable) return "고수익·안정";
    if (highReturn) return "고수익·위험";
    if (stable) return "안정·저수익";
    return "수익개선 필요";
  }
  function drawRentalQuadrants(chart) {
    var area = chart.chartArea;
    if (!area) return;
    var ctx = chart.ctx;
    var midX = chart.scales.x.getPixelForValue(benchmarkIncomeYield());
    var midY = chart.scales.y.getPixelForValue(0.5);
    ctx.save();
    ctx.fillStyle = "rgba(70,145,129,.035)";
    ctx.fillRect(area.left, area.top, midX - area.left, midY - area.top);
    ctx.fillStyle = "rgba(47,135,111,.065)";
    ctx.fillRect(midX, area.top, area.right - midX, midY - area.top);
    ctx.fillStyle = "rgba(132,147,164,.035)";
    ctx.fillRect(area.left, midY, midX - area.left, area.bottom - midY);
    ctx.fillStyle = "rgba(226,147,103,.055)";
    ctx.fillRect(midX, midY, area.right - midX, area.bottom - midY);
    ctx.strokeStyle = "rgba(71,92,109,.58)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(midX, area.top); ctx.lineTo(midX, area.bottom);
    ctx.moveTo(area.left, midY); ctx.lineTo(area.right, midY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = "600 10px 'Noto Sans KR', sans-serif";
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(36,57,73,.68)";
    ctx.fillText("안정·저수익", area.left + 8, area.top + 7);
    ctx.textAlign = "right";
    ctx.fillText("고수익·안정", area.right - 8, area.top + 7);
    ctx.textBaseline = "bottom";
    ctx.textAlign = "left";
    ctx.fillText("수익개선 필요", area.left + 8, area.bottom - 7);
    ctx.textAlign = "right";
    ctx.fillText("고수익·위험", area.right - 8, area.bottom - 7);
    ctx.restore();
  }
  function rentalChartPlugins() {
    var quadrant = { id: "rentalQuadrants", beforeDraw: drawRentalQuadrants };
    var selectedLabel = {
      id: "rentalPointLabels",
      beforeDatasetsDraw: function (chart) {
        var selected = chart.data.datasets.find(function (set) { return set.key === "selected"; });
        if (!selected || !selected.data.length) return;
        var element = chart.getDatasetMeta(chart.data.datasets.indexOf(selected)).data[0];
        if (!element) return;
        var ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.arc(element.x, element.y, 20, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(235,104,52,.18)";
        ctx.fill();
        ctx.restore();
      },
      afterDatasetsDraw: function (chart) {
        var ctx = chart.ctx;
        var used = [];
        var overlaps = function (a, b) { return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; };
        var drawBadge = function (element, text, foreground, background, border, font, force) {
          ctx.font = font;
          var w = Math.ceil(ctx.measureText(text).width) + 14;
          var h = 24;
          var area = chart.chartArea;
          var candidates = [
            { x: element.x + 11, y: element.y - h - 5 },
            { x: element.x - w - 11, y: element.y - h - 5 },
            { x: element.x + 11, y: element.y + 5 },
            { x: element.x - w - 11, y: element.y + 5 },
          ].map(function (box) {
            return { x: Math.max(area.left + 2, Math.min(area.right - w - 2, box.x)), y: Math.max(area.top + 2, Math.min(area.bottom - h - 2, box.y)), w: w, h: h };
          });
          var box = candidates.find(function (candidate) { return !used.some(function (prior) { return overlaps(candidate, prior); }); });
          if (!box && !force) return null;
          if (!box) box = candidates[0];
          used.push(box);
          ctx.save();
          ctx.font = font;
          ctx.textBaseline = "middle";
          ctx.fillStyle = background;
          ctx.strokeStyle = border;
          ctx.lineWidth = 1;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(box.x, box.y, box.w, box.h, 8);
          else ctx.rect(box.x, box.y, box.w, box.h);
          ctx.fill(); ctx.stroke();
          ctx.fillStyle = foreground;
          ctx.textAlign = "center";
          ctx.fillText(text, box.x + box.w / 2, box.y + box.h / 2);
          ctx.restore();
          return box;
        };
        var selectedSet = chart.data.datasets.find(function (set) { return set.key === "selected"; });
        var selectedIndex = selectedSet && chart.data.datasets.indexOf(selectedSet);
        var selectedElement = selectedSet && selectedSet.data.length
          ? chart.getDatasetMeta(selectedIndex).data[0] : null;
        var reservedSelectedBox = null;
        if (selectedElement) {
          var selectedPoint = selectedSet.data[0];
          if (selectedPoint.offscale) {
            ctx.font = "800 11px 'Noto Sans KR', sans-serif";
            var offText = (selectedPoint.direction === "right" ? "▶ " : "◀ ") + percent(selectedPoint.actualX);
            var offWidth = ctx.measureText(offText).width + 15;
            reservedSelectedBox = {
              x: selectedPoint.direction === "right" ? chart.chartArea.right - offWidth - 3 : chart.chartArea.left + 3,
              y: Math.max(chart.chartArea.top + 3, Math.min(chart.chartArea.bottom - 25, selectedElement.y - 30)),
              w: offWidth, h: 22,
            };
          } else {
            ctx.font = "800 13px 'Noto Sans KR', sans-serif";
            var ownWidth = Math.ceil(ctx.measureText("내 호실").width) + 14;
            reservedSelectedBox = {
              x: Math.max(chart.chartArea.left + 2, Math.min(chart.chartArea.right - ownWidth - 2, selectedElement.x + 11)),
              y: Math.max(chart.chartArea.top + 2, Math.min(chart.chartArea.bottom - 26, selectedElement.y - 29)),
              w: ownWidth, h: 24,
            };
          }
          used.push(reservedSelectedBox);
        }
        chart.data.datasets.forEach(function (set, index) {
          if (set.key === "selected") return;
          var meta = chart.getDatasetMeta(index);
          set.data.forEach(function (point, pointIndex) {
            var element = meta.data[pointIndex];
            if (!element || !point.badge) return;
            drawBadge(element, point.badge, set.key === "national" ? "#18508a" : "#3C3489",
              set.key === "national" ? "#edf5ff" : "#EEEDFE", set.key === "national" ? "#2a78d6" : "#b8b4ef",
              "700 10px 'Noto Sans KR', sans-serif", false);
          });
        });
        if (selectedSet && selectedSet.data.length) {
          var element = selectedElement;
          if (element) {
            var point = selectedSet.data[0];
            if (reservedSelectedBox) used.splice(used.indexOf(reservedSelectedBox), 1);
            if (point.offscale) {
              var area = chart.chartArea;
              var ctx2 = chart.ctx;
              ctx2.save();
              ctx2.font = "800 11px 'Noto Sans KR', sans-serif";
              var text = (point.direction === "right" ? "▶ " : "◀ ") + percent(point.actualX);
              var width = ctx2.measureText(text).width + 15;
              var x = point.direction === "right" ? area.right - width - 3 : area.left + 3;
              var y = Math.max(area.top + 3, Math.min(area.bottom - 25, element.y - 30));
              used.push({ x: x, y: y, w: width, h: 22 });
              ctx2.fillStyle = "#fff2eb"; ctx2.strokeStyle = "#eb6834";
              ctx2.beginPath();
              if (ctx2.roundRect) ctx2.roundRect(x, y, width, 22, 7); else ctx2.rect(x, y, width, 22);
              ctx2.fill(); ctx2.stroke();
              ctx2.fillStyle = "#a64119"; ctx2.textBaseline = "middle"; ctx2.textAlign = "center";
              ctx2.fillText(text, x + width / 2, y + 11);
              ctx2.restore();
            } else {
              drawBadge(element, "내 호실", "#873714", "#fff4ec", "#eb6834", "800 13px 'Noto Sans KR', sans-serif", true);
            }
            element.draw(chart.ctx, chart.chartArea);
          }
        }
      },
    };
    return [quadrant, selectedLabel];
  }
  function regionVacancyMonths(item, averageMonths) {
    // This endpoint does not collect province-level small-retail vacancy.
    // Every province currently carries the nationwide substitute, regardless
    // of whether its numeric value happens to differ from another row.
    return { months: averageMonths, hollow: true };
  }
  function chartPoint(item, averageMonths, badge) {
    var vacancy = regionVacancyMonths(item, averageMonths);
    return {
      x: Number(item.income_yield), y: vacancyTransform(vacancy.months, averageMonths),
      label: String(item.region_name || "지역 평균"), badge: badge || String(item.region_name || "지역") + " " + Number(item.income_yield).toFixed(1) + "%",
      hollow: vacancy.hollow, months: vacancy.months, item: item,
    };
  }
  function buildRentalDatasets(result) {
    var averageYield = benchmarkIncomeYield();
    var averageMonths = benchmarkMonths();
    var datasets = [];
    var national = rentalBenchmarkItems.find(function (item) { return item.region_level === "national" || String(item.region_code) === "00"; });
    if (!national && rentalBenchmark && (rentalBenchmark.region_level === "national" || String(rentalBenchmark.region_code) === "00")) national = rentalBenchmark;
    if (national && Number.isFinite(averageYield) && Number.isFinite(averageMonths)) {
      var nationalPoint = chartPoint(national, averageMonths, "전국 " + averageYield.toFixed(2) + "%");
      nationalPoint.x = averageYield;
      nationalPoint.y = vacancyTransform(averageMonths, averageMonths);
      nationalPoint.months = averageMonths;
      datasets.push({
        key: "national", label: "전국 평균", data: [nationalPoint], order: 1,
        pointRadius: 9, pointHoverRadius: 10, pointStyle: "rectRot", pointBackgroundColor: "#2a78d6",
        pointBorderColor: "#fff", pointBorderWidth: 2,
      });
    }
    var provinceCode = selectedProvinceCode();
    var provinceName = selectedProvinceName();
    var provinceData = rentalBenchmarkItems.filter(function (item) {
      return item.region_level !== "national" && String(item.region_code) !== "00"
        && Number.isFinite(Number(item.income_yield));
    }).map(function (item) {
      var point = chartPoint(item, averageMonths);
      point.selectedProvince = provinceCode && normalizedRegionCode(item.region_code) === provinceCode
        || provinceName && String(item.region_name || "").indexOf(provinceName) >= 0;
      point.badge = point.label + " " + Number(item.income_yield).toFixed(1) + "%";
      return point;
    });
    if (provinceData.length) datasets.push({
      key: "province", label: "지역 평균", data: provinceData, order: 2,
      pointRadius: function (context) { return context.raw.selectedProvince ? 9 : 7; },
      pointHoverRadius: function (context) { return context.raw.selectedProvince ? 11 : 9; },
      pointStyle: "circle",
      pointBackgroundColor: function (context) { return context.raw.hollow ? "#fff" : "#7F77DD"; },
      pointBorderColor: function (context) { return context.raw.hollow ? "#7F77DD"
        : context.raw.selectedProvince ? "#403b8d" : "#fff"; },
      pointBorderWidth: function (context) { return context.raw.selectedProvince ? 3 : 2; },
    });
    var selectedYield = selectedModeValue(result);
    if (Number.isFinite(selectedYield) && Number.isFinite(result.vacancyMonths)) {
      var xMin = averageYield - 10;
      var xMax = averageYield + 10;
      var offscale = selectedYield < xMin || selectedYield > xMax;
      var clipped = Math.max(xMin + 0.18, Math.min(xMax - 0.18, selectedYield));
      datasets.push({
        key: "selected", label: "내 호실", order: 0,
        data: [{
          x: clipped, actualX: selectedYield, y: vacancyTransform(result.vacancyMonths, averageMonths),
          actualMonths: result.vacancyMonths, offscale: offscale,
          direction: selectedYield > xMax ? "right" : "left",
        }],
        pointRadius: 13, pointHoverRadius: 15,
        pointStyle: function (context) {
          return context.raw.offscale ? "triangle" : "circle";
        },
        pointRotation: function (context) {
          return context.raw.offscale && context.raw.direction === "right" ? 90
            : context.raw.offscale ? -90 : 0;
        },
        pointBackgroundColor: "#eb6834", pointBorderColor: "#fff", pointBorderWidth: 3,
      });
    }
    return datasets;
  }
  function renderPositioning(result) {
    var box = $("rentalPositioning");
    var canvas = $("rentalPositionChart");
    if (!box || !canvas || typeof Chart === "undefined") return;
    var averageYield = benchmarkIncomeYield();
    var averageMonths = benchmarkMonths();
    var ready = Number.isFinite(averageYield) && Number.isFinite(averageMonths);
    Array.prototype.forEach.call(box.querySelectorAll(".positioning-quadrant"), function (label) {
      label.classList.add("hidden");
    });
    var pending = box.querySelector(".positioning-pending");
    if (pending) pending.classList.toggle("hidden", ready);
    var equityNote = box.querySelector("[data-rental-equity-note]");
    if (!equityNote) {
      equityNote = document.createElement("p");
      equityNote.className = "rental-equity-note hidden";
      equityNote.dataset.rentalEquityNote = "true";
      equityNote.textContent = "비교점은 대출 없는 공공통계 수익률입니다. 내 호실만 대출 효과가 반영된 위치입니다.";
      box.appendChild(equityNote);
    }
    var toggleButtons = box.querySelectorAll("[data-mode]");
    Array.prototype.forEach.call(toggleButtons, function (button) {
      var active = button.dataset.mode === positionMode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      if (!button.dataset.rentalModeBound) {
        button.dataset.rentalModeBound = "true";
        button.addEventListener("click", function () {
          positionMode = button.dataset.mode === "equity" ? "equity" : "net";
          renderPositioning(lastCalculated);
          if (lastCalculated) {
            renderSensitivity(lastCalculated);
            renderVerdict(lastCalculated);
          }
        });
      }
    });
    var note = box.querySelector("[data-rental-equity-note]");
    if (note) note.classList.toggle("hidden", positionMode !== "equity");
    var benchmarkNode = box.querySelector("[data-rental-benchmark-legend]");
    if (benchmarkNode) benchmarkNode.textContent = ready
      ? benchmarkName() + " · " + benchmarkSource + (rentalBenchmark && rentalBenchmark.period ? " · " + monthLabel(rentalBenchmark.period) : "")
      : "R-ONE 수익률 자료를 불러오지 못했습니다.";
    var regionLegend = box.querySelector("[data-rental-region-legend]");
    if (regionLegend) regionLegend.textContent = "지역 평균 · " + benchmarkSource
      + (rentalBenchmark && rentalBenchmark.period ? " · " + monthLabel(rentalBenchmark.period) : "") + " · 개별 호실 사례 아님";
    var legend = box.querySelector(".rental-chart-legend");
    if (!legend) {
      legend = document.createElement("div");
      legend.className = "rental-chart-legend";
      box.appendChild(legend);
    }
    var period = rentalBenchmark && rentalBenchmark.period ? " · " + monthLabel(rentalBenchmark.period) : "";
    legend.innerHTML = '<span class="legend-own">내 호실</span><span class="legend-national">'
      + escapeHtml(benchmarkName()) + ' (' + escapeHtml(benchmarkSource || "R-ONE") + escapeHtml(period) + ')</span>'
      + '<span class="legend-province">지역 평균 (R-ONE' + escapeHtml(period) + ') · 개별 호실 사례 아님</span>';
    if (!ready) {
      if (positionChart) { positionChart.destroy(); positionChart = null; }
      return;
    }
    var xMin = averageYield - 10;
    var xMax = averageYield + 10;
    var datasets = buildRentalDatasets(result || {});
    var axisTicks = [];
    for (var x = Math.ceil(xMin / 2) * 2; x <= xMax; x += 2) axisTicks.push(x);
    if (!axisTicks.some(function (value) { return Math.abs(value - averageYield) < 0.01; })) axisTicks.push(averageYield);
    axisTicks.sort(function (a, b) { return a - b; });
    var options = {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "nearest", intersect: true },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function () { return ""; },
            label: function (context) {
              var raw = context.raw;
              var set = context.dataset;
              if (set.key === "selected") return "내 호실 · " + percent(raw.actualX) + " · 연간 공실 " + raw.actualMonths.toFixed(1) + "개월";
              var vacancyNote = raw.hollow ? "공실: 전국 대체값" : "공실: " + raw.months.toFixed(1) + "개월";
              return (set.key === "national" ? "전국 평균" : raw.label) + " · " + percent(raw.x) + " · " + vacancyNote;
            },
          },
        },
      },
      scales: {
        x: {
          type: "linear", min: xMin, max: xMax,
          title: { display: true, text: positionMode === "equity" ? "자기자본 수익률 (%)" : "순수익률 (대출 전, %)", font: { family: "'Noto Sans KR', sans-serif" } },
          afterBuildTicks: function (scale) {
            scale.ticks = axisTicks.map(function (value) { return { value: value }; });
          },
          ticks: {
            font: { family: "'Noto Sans KR', sans-serif" },
            callback: function (value) {
              var tick = axisTicks.find(function (item) { return Math.abs(item - Number(value)) < 0.001; });
              if (tick == null) return "";
            return Math.abs(tick - averageYield) < 0.001 ? "기준 " + tick.toFixed(2) : tick.toFixed(0);
            },
          },
        },
        y: {
          type: "linear", min: 0, max: 1, reverse: true,
          afterBuildTicks: function (scale) {
            scale.ticks = [0, 1, 2, 3, 4, 5, 6].map(function (months) {
              return { value: vacancyTransform(months, averageMonths) };
            });
          },
          title: { display: true, text: "← 공실 적음 · 연간 공실 개월 (평균 기준 상하 구간 척도)", font: { family: "'Noto Sans KR', sans-serif" } },
          ticks: {
            font: { family: "'Noto Sans KR', sans-serif" },
            callback: function (value) {
              var months = vacancyInverse(Number(value), averageMonths);
              var nearest = Math.round(months);
              return Math.abs(months - nearest) < 0.02 ? nearest + "개월" : "";
            },
          },
        },
      },
    };
    if (!positionChart || positionChart.canvas !== canvas) {
      if (positionChart) positionChart.destroy();
      positionChart = new Chart(canvas, { type: "scatter", data: { datasets: datasets }, options: options, plugins: rentalChartPlugins() });
    } else {
      positionChart.data.datasets = datasets;
      positionChart.options = options;
      positionChart.update("none");
    }
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
      if (!rentCenterEdited) resetRentCenterBase();
      syncSliderBounds();
      calculate();
    } catch (ignore) {
      if (seq !== buildingSequence || String(id) !== loadedBuildingId) return;
      rentalBenchmark = null;
      $("rentalVacancyMonthsHint").textContent = "R-ONE 평균을 불러오지 못했습니다. 직접 입력할 수 있습니다.";
      if (!rentCenterEdited) resetRentCenterBase();
      syncSliderBounds();
      calculate();
    }
  }
  function calculate() {
    scheduleCalculate();
  }
  function scheduleCalculate() {
    if (rafId) return;
    rafId = window.requestAnimationFrame(function () {
      rafId = 0;
      calculateNow();
    });
  }
  function sensitivityYield(rent, vacancyMonths, result) {
    var annualRent = rent * 12;
    var noi = annualRent * (1 - vacancyMonths / 12) - result.costs;
    if (positionMode === "equity") {
      return result.invested > 0 ? (noi - result.annualInterest) / result.invested * 100 : NaN;
    }
    return result.returnBasis > 0 ? noi / result.returnBasis * 100 : NaN;
  }
  function renderSensitivity(result) {
    var host = $("rentalSensitivity");
    if (!host) return;
    var rent = n("rentalMonthlyRent");
    var utils = window.analysisSliderUtils;
    var center = rent > 0 ? rent : rentCenter();
    if (!(center > 0)) {
      host.innerHTML = "<h3>월세 × 공실 민감도</h3><p>월세 비교 기준이 없어 민감도 표를 표시할 수 없습니다.</p>";
      return;
    }
    var rentStep = sliderBounds.rentalMonthlyRent && sliderBounds.rentalMonthlyRent.step || 1;
    var interval = Math.max(rentStep, utils.niceStep(center * 0.1));
    var columns = Array.from({ length: 7 }, function (_, index) {
      return { amount: center + (index - 3) * interval, current: rent > 0 && index === 3 };
    });
    var currentVacancy = Number.isFinite(Number(result.vacancyMonths))
      ? Number(result.vacancyMonths) : 0;
    var boundedVacancy = Math.max(0, Math.min(6, currentVacancy));
    var vacancyRows = [];
    for (var offset = -3; offset <= 3; offset += 1) {
      var vacancy = offset === 0 ? boundedVacancy : Number((boundedVacancy + offset).toFixed(10));
      if (vacancy < 0 || vacancy > 6) continue;
      if (!vacancyRows.some(function (value) { return Math.abs(value - vacancy) < 0.000000001; })) {
        vacancyRows.push(vacancy);
      }
    }
    var clippedBelow = boundedVacancy - 3 < 0;
    var clippedAbove = boundedVacancy + 3 > 6;
    if (clippedBelow && !vacancyRows.some(function (value) { return value === 0; })) vacancyRows.push(0);
    if (vacancyRows.length < 7 && clippedAbove
      && !vacancyRows.some(function (value) { return value === 6; })) vacancyRows.push(6);
    while (vacancyRows.length < 7) {
      var preferHigh = clippedBelow && !clippedAbove;
      var next = preferHigh ? Math.max.apply(null, vacancyRows) + 1 : Math.min.apply(null, vacancyRows) - 1;
      if (next < 0 || next > 6) {
        next = preferHigh ? Math.min.apply(null, vacancyRows) - 1 : Math.max.apply(null, vacancyRows) + 1;
      }
      if (next < 0 || next > 6) break;
      vacancyRows.push(next);
    }
    vacancyRows.sort(function (a, b) { return a - b; });
    var currentRow = rent > 0 && currentVacancy >= 0 && currentVacancy <= 6
      ? vacancyRows.findIndex(function (value) { return Math.abs(value - currentVacancy) < 0.000000001; })
      : -1;
    var averageYield = benchmarkIncomeYield();
    var rows = vacancyRows.map(function (months, rowIndex) {
      var selectedRow = Math.abs(months - currentVacancy) < 0.000000001;
      return '<tr><th scope="row"' + (rowIndex === currentRow ? ' class="selected-row"' : "") + '>'
        + String(months) + '개월</th>' + columns.map(function (column) {
            var selected = rowIndex === currentRow && column.current;
            var scenarioRent = column.current && rent > 0 ? rent : column.amount;
            var scenarioVacancy = selectedRow ? currentVacancy : months;
            var value = sensitivityYield(scenarioRent, scenarioVacancy, result || {});
        var color = !Number.isFinite(value) ? "unavailable" : value >= averageYield ? "above"
          : value >= 3 ? "middle" : "below";
        var tooltip = "월세 " + scenarioRent.toLocaleString("ko-KR") + "만원 · 공실 "
          + scenarioVacancy.toLocaleString("ko-KR") + "개월 기준 "
          + (Number.isFinite(value) ? value.toFixed(1) + "%" : "계산불가");
        return '<td class="' + color + (column.current ? " current-column" : "")
          + (selected ? " selected" : "") + '"'
          + (selected ? ' aria-current="true"' : "")
        + ' title="' + escapeHtml(tooltip) + '">'
          + (Number.isFinite(value) ? value.toFixed(2) + "%" : "-") + "</td>";
      }).join("") + "</tr>";
    });
    host.innerHTML = '<div class="rental-sensitivity-head"><h3>월세 × 공실 민감도 (' +
      '매수가 ' + money(result.purchasePrice) + ' · 대출 ' + money(result.loan) + ' · 보증금 ' + money(result.deposit)
      + ' 반영, ' + (positionMode === "equity" ? "자기자본 수익률" : "순수익률") + ')</h3></div>'
      + '<div class="rental-sensitivity-scroll"><table class="rental-sensitivity-table"><thead><tr><th>공실 \\ 월세</th>'
      + columns.map(function (column) {
        return '<th' + (column.current ? ' class="selected-column"' : "") + '>'
          + column.amount.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + "만원</th>";
      }).join("") + '</tr></thead><tbody>' + rows.join("") + '</tbody></table></div>'
      + '<div class="rental-sensitivity-legend"><span><i class="above"></i>전국 평균 이상</span>'
      + '<span><i class="middle"></i>3% 이상 ~ 전국 평균 미만</span><span><i class="below"></i>3% 미만</span>'
      + '<span><i class="unavailable"></i>계산 불가</span></div>';
  }
  function renderVerdict(result) {
    var host = $("rentalVerdict");
    if (!host) return;
    var averageYield = benchmarkIncomeYield();
    var averageMonths = benchmarkMonths();
    var modeYield = selectedModeValue(result);
    var title = rentalQuadrantLabel(result, averageYield, averageMonths);
    var explanation = result.vacancySource === "rone"
      ? "공실은 R-ONE 소규모 상가 전국 대체값을 사용 중입니다. 최근 1년 실제 공실을 입력하면 판정을 표시합니다."
      : "현재 조건 기준 " + (positionMode === "equity" ? "자기자본 수익률 " : "순수익률 ")
        + percent(modeYield) + " · 공실 " + result.vacancyMonths.toFixed(1) + "개월";
    host.innerHTML = '<strong>' + escapeHtml(title) + '</strong><span>' + escapeHtml(explanation) + '</span>';
  }
  function renderCoreMetrics(result) {
    var host = $("rentalCoreMetrics");
    if (!host) return;
    var grid = host.querySelector(".metric-grid") || host;
    var averageYield = benchmarkIncomeYield();
    var returnClass = function (value) {
      return !Number.isFinite(value) ? "" : value < 3 ? "danger" : value >= averageYield ? "success" : "";
    };
    grid.innerHTML = card("순수익률(대출 전)", percent(result.netYield), "NOI ÷ (매입가 + 취득부대 − 보증금)", returnClass(result.netYield))
      + card("자기자본 수익률", percent(result.cashReturn), "이자 차감 후 현금흐름 ÷ 실투자금", returnClass(result.cashReturn))
      + card("월 순현금흐름", money(result.cashFlow / 12, 1), "NOI에서 연 대출이자를 차감", result.cashFlow < 0 ? "danger" : "")
      + card("실투자금", result.invested > 0 ? money(result.invested) : "계산불가", "매입가 + 취득부대 − 보증금 − 대출금", result.invested <= 0 ? "danger" : "");
  }
  function renderExtraMetrics(result) {
    var host = $("rentalExtraMetrics");
    if (!host) return;
    var cards = [
      card("표면수익률", percent(result.grossYield), "공실·비용 차감 전"),
      card("현재 실거래 기준 수익률", Number.isFinite(result.marketYield) ? percent(result.marketYield) : "기준가 입력 필요",
        Number.isFinite(result.marketYield) ? "현재 기준가 " + money(result.marketPrice) : "최근 실거래 자동연결 예정"),
      card("비용 반영 순수익률", percent(result.netYield), "대출 전 NOI 기준 순수익률"),
      card("연간 보유비용", money(result.costs), "보유세·관리비·수선비 합계"),
    ];
    if (result.loan > 0) {
      cards.push(card("월 대출 상환액", money(result.debtMonthly, 1), $("rentalLoanMethod").selectedOptions[0].text));
      cards.push(card("DSCR", result.dscr == null ? "계산불가" : result.dscr.toFixed(2) + "배",
        result.dscr == null ? "연간 대출상환액 계산 불가" : (result.dscr >= 1.2 ? "임대수익 상환여력 양호" : "상환여력 주의"),
        result.dscr != null && result.dscr < 1.2 ? "danger" : ""));
    }
    host.innerHTML = cards.join("");
  }
  function calculateNow() {
    syncSliderBounds();
    var purchase = n("rentalPurchasePrice");
    var market = n("rentalMarketPrice");
    var deposit = n("rentalDeposit");
    var rent = n("rentalMonthlyRent");
    var enteredMonths = $("rentalVacancyMonths").value.trim() === "" ? null : n("rentalVacancyMonths");
    var resolvedMonths = enteredMonths != null ? Math.min(6, Math.max(0, enteredMonths)) : benchmarkMonths();
    if (enteredMonths == null && resolvedMonths != null) {
      $("rentalVacancyMonths").value = String(Math.max(0, Math.min(6, Math.round(resolvedMonths))));
      resolvedMonths = Number($("rentalVacancyMonths").value);
    }
    var assumptionBadge = document.querySelector("[data-vacancy-assumption]");
    if (assumptionBadge) assumptionBadge.classList.toggle("hidden", !vacancyAssumed);
    $("rentalVacancyRate").value = resolvedMonths == null ? "" : (resolvedMonths / 12 * 100).toFixed(1);
    $("rentalVacancyRateHint").textContent = resolvedMonths == null
      ? "공실 개월을 입력하거나 전국 전체 평균을 불러와야 합니다."
      : vacancyAssumed ? "R-ONE 전국 대체 공실률 가정값 적용" : "사용자 입력 공실기간에서 자동계산";
    var vacancy = resolvedMonths == null ? 0 : resolvedMonths / 12;
    var acquisitionTax = n("rentalAcquisitionTax");
    var brokerFee = n("rentalBrokerFee");
    var acquisition = acquisitionTax + brokerFee;
    var tax = n("rentalPropertyTax");
    var costs = tax + n("rentalManagementCost") + n("rentalOtherCost");
    var basisTotal = costs;
    if ($("rentalBasisTotal")) $("rentalBasisTotal").value = basisTotal ? money(basisTotal, 1).replace("만원", "") : "";
    var loan = n("rentalLoanAmount");
    if (resolvedMonths == null) {
      $("rentalResults").innerHTML = '<div class="rental-calculation-warning"><b>공실 기준이 필요합니다</b><span>최근 1년 공실 개월을 입력하거나 R-ONE 전국 전체 평균이 연결되어야 수익률을 계산합니다.</span></div>';
      var metricGrid = $("rentalCoreMetrics").querySelector(".metric-grid");
      if (metricGrid) metricGrid.innerHTML = [
        "순수익률(대출 전)", "자기자본 수익률", "월 순현금흐름", "실투자금"
      ].map(function (label) { return card(label, "계산불가", "공실 기준 확인 필요"); }).join("");
      $("rentalExtraMetrics").innerHTML = "";
      $("rentalSensitivity").innerHTML = '<h3>월세 × 공실 민감도</h3><p>공실 기준을 입력하거나 R-ONE 자료를 불러온 뒤 표시합니다.</p>';
      var waiting = { vacancyMonths: 0, vacancySource: "unavailable", cashReturn: NaN, netYield: NaN };
      lastCalculated = waiting;
      renderPositioning(waiting);
      renderVerdict(waiting);
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
    var returnBasis = purchase + acquisition - deposit;
    var annualInterest = loan * n("rentalLoanRate") / 100;
    var cashFlow = noi - annualInterest;
    var grossYield = purchase > 0 ? annualRent / purchase * 100 : NaN;
    var netYield = returnBasis > 0 ? noi / returnBasis * 100 : NaN;
    var cashReturn = invested > 0 ? cashFlow / invested * 100 : NaN;
    var marketYield = market > 0 ? noi / market * 100 : NaN;
    var dscr = debt.annual > 0 ? noi / debt.annual : null;
    $("rentalResults").innerHTML =
      card("대출 후 월 순현금", money(cashFlow / 12, 1), "순영업소득에서 연 대출이자 차감", "primary")
      + card("자기자본 수익률", invested > 0 ? percent(cashReturn) : "계산불가", "실투자금 " + money(invested), invested <= 0 || cashReturn < 0 ? "danger" : "")
      + card("비용 반영 순수익률", percent(netYield), "NOI " + money(noi) + " ÷ 투자기준금액 " + money(returnBasis))
      + card("실투자금", invested > 0 ? money(invested) : "계산불가", "매입가 + 취득부대 − 보증금 − 대출금")
      + card("표면수익률", percent(grossYield), "공실·비용 차감 전")
      + card("현재 실거래 기준 수익률", market ? percent(marketYield) : "기준가 입력 필요", market ? "현재 기준가 " + money(market) : "최근 실거래 자동연결 예정")
      + (loan > 0 ? card("월 대출 상환액", money(debt.monthly, 1), $("rentalLoanMethod").selectedOptions[0].text) : "")
      + (loan > 0 ? card("DSCR", dscr == null ? "계산불가" : dscr.toFixed(2) + "배", dscr == null ? "연간 대출상환액 계산 불가" : (dscr >= 1.2 ? "임대수익 상환여력 양호" : "상환여력 주의"), dscr != null && dscr < 1.2 ? "danger" : "") : "")
       + card("연간 보유비용", money(costs), "보유세·관리비·수선비 합계");
    var source = vacancyAssumed && rentalBenchmark ? "rone" : "user";
    lastCalculated = {
      purchasePrice: purchase, annualRent: annualRent, noi: noi, invested: invested,
      debtService: debt.annual, debtMonthly: debt.monthly, annualInterest: annualInterest, cashFlow: cashFlow, grossYield: grossYield,
      netYield: netYield, cashReturn: cashReturn, dscr: dscr,
      returnBasis: returnBasis, costs: costs, loan: loan, deposit: deposit, marketPrice: market,
      marketYield: marketYield, vacancyMonths: resolvedMonths,
      vacancyRate: resolvedMonths == null ? null : resolvedMonths / 12 * 100,
      vacancySource: source,
      benchmark: rentalBenchmark,
      ready: true,
    };
    renderCoreMetrics(lastCalculated);
    renderExtraMetrics(lastCalculated);
    renderPositioning(lastCalculated);
    renderSensitivity(lastCalculated);
    renderVerdict(lastCalculated);
    window.__rentalAnalysisResult = lastCalculated;
    if (loadedBuildingId) window.livingstayAnalysisReportActions(
      $("rentalReportActions"), loadedBuildingId,
       loadedBuilding && (loadedBuilding.display_building_name || loadedBuilding.building_name),
       loadedBuilding && (loadedBuilding.road_address || loadedBuilding.jibun_address)
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
  function updateMethodologyFormula() {
    var formula = document.querySelector("#rentalAnalysis .methodology .formula");
    if (!formula) return;
    formula.innerHTML = "순영업소득(NOI) = 연 월세 − 공실손실 − 재산세·관리비·기타비용<br>"
      + "순수익률(대출 전) = NOI ÷ (매입가 + 취득 부대비용 − 보증금)<br>"
      + "실투자금 = 매입가 + 취득 부대비용 − 보증금 − 대출금<br>"
      + "자기자본 수익률 = (NOI − 연 대출이자) ÷ 실투자금<br>"
      + "DSCR = 순영업소득 ÷ 연간 대출 원리금";
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
      sliderBasePrice = null;
      syncSliderBounds();
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
        sliderBasePrice = null;
        if (!rentCenterEdited) resetRentCenterBase();
        syncSliderBounds();
        calculate();
        return;
      }
      if (!renderMarketEvidence(result)) {
        automaticMarketPrice = null;
        if (!marketPriceManuallyEdited) $("rentalMarketPrice").value = "";
        $("rentalMarketPrice").placeholder = "직접 입력";
        setMarketStatus("실거래 계산 표본과 근거 목록이 일치하지 않아 자동 기준가를 제공하지 않습니다.", "error");
        sliderBasePrice = null;
        if (!rentCenterEdited) resetRentCenterBase();
        syncSliderBounds();
        calculate();
        return;
      }
      automaticMarketPrice = Number(result.median_price);
      if (!marketPriceManuallyEdited) {
        $("rentalMarketPrice").value = String(automaticMarketPrice);
      }
      sliderBasePrice = null;
      applyInvalidRentalUrlDefaults();
      if (!rentCenterEdited) resetRentCenterBase();
      syncSliderBounds();
      calculate();
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
        sliderBasePrice = null;
        if (!rentCenterEdited) resetRentCenterBase();
        syncSliderBounds();
        calculate();
      }
    }
  }
  function restoreSharedRentalValues() {
    if (sharedValuesRestored) return;
    var params = new URLSearchParams(location.search);
    var hasRentalValues = Object.keys(sharedFieldParams).some(function (key) { return params.has(key); })
      || params.has("r_yieldmode") || params.has("buy") || params.has("rent");
    if (!hasRentalValues) return;
    sharedValuesRestored = true;
    loadingSharedValues = true;
    var invalidKeys = [];
    var invalidFields = Object.create(null);
    Object.keys(sharedFieldParams).forEach(function (key) {
      if (!params.has(key)) return;
      var field = sharedFieldParams[key];
      var value = params.get(key);
      if (field === "rentalLoanMethod") {
        if (["interest", "equal", "principal"].indexOf(value) >= 0) $(field).value = value;
        return;
      }
      if (field === "rentalUnitArea") {
        if (/^\d+(?:\.\d+)?$/.test(value)) $(field).value = value;
        return;
      }
      if (field === "rentalVacancyMonths" && value === "") {
        $("rentalVacancyMonths").value = "";
        vacancyAssumed = true;
        return;
      }
      var kind = rentalHardKind(field);
      var normalized = kind ? window.analysisSliderUtils.clampHard(kind, value,
        field === "rentalLoanAmount" ? n("rentalPurchasePrice") : undefined)
        : Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null;
      if (normalized == null) {
        invalidKeys.push(key);
        invalidFields[field] = true;
        invalidRentalUrlFields[field] = true;
        warnInvalidRentalParam(key, value);
        return;
      }
      $(field).value = String(normalized);
      if (kind) lastValidRentalInputs[field] = normalized;
    });
    [["buy", "rentalPurchasePrice", "r_purchase"], ["rent", "rentalMonthlyRent", "r_rent"]]
      .forEach(function (entry) {
        var key = entry[0];
        if (!params.has(key)) return;
        var value = params.get(key);
        var valid = window.analysisSliderUtils.clampHard(
          entry[1] === "rentalPurchasePrice" ? "purchase" : "rent", value);
        if (valid == null) {
          invalidKeys.push(key);
          invalidRentalUrlFields[entry[1]] = true;
          if (!invalidFields[entry[1]]) warnInvalidRentalParam(key, value);
        }
      });
    var mode = params.get("r_yieldmode");
    if (mode === "equity" || mode === "net") positionMode = mode;
    loadingSharedValues = false;
    if (n("rentalPurchasePrice") > 0) {
      updateAcquisitionCosts();
      updateEstimatedTax();
    }
    if (n("rentalVacancyMonths") > 0 || params.has("r_vacancy") && params.get("r_vacancy") !== "") {
      vacancyAssumed = false;
    }
    cleanInvalidRentalParams(invalidKeys);
    resetRentCenterBase();
    syncSliderBounds();
  }
  async function loadBuilding() {
    var id = new URLSearchParams(location.search).get("building_id");
    var seq = ++buildingSequence;
    cancelRentalSliderChange();
    if (!id) {
      rentCenterBase = null;
      rentCenterEdited = false;
      loadedBuildingId = "";
      loadedBuilding = null;
      sliderBasePrice = null;
      sliderBounds = Object.create(null);
      if (window.livingstayRenderAnalysisBuildingIdentity) window.livingstayRenderAnalysisBuildingIdentity($("rentalBuildingIdentity"), null);
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
      syncSliderBounds();
      calculate();
      return;
    }
    if (loadedBuildingId !== String(id)) {
      loadedBuildingId = String(id);
      marketPriceManuallyEdited = false;
      automaticMarketPrice = null;
      sliderBasePrice = null;
      sliderBounds = Object.create(null);
      clearMarketEvidence();
      $("rentalUnitArea").value = "";
      $("rentalMarketPrice").value = "";
      $("rentalMarketPrice").placeholder = "호실 면적을 먼저 선택";
      setMarketStatus("호실 면적 목록을 확인하고 있습니다.", "loading");
    }
    restoreSharedRentalValues();
    resetRentCenterBase();
    try {
      var responses = await Promise.all([
        fetch("/api/building/" + encodeURIComponent(id), { credentials: "same-origin" }),
        fetch("/api/building/" + encodeURIComponent(id) + "/area-types", { credentials: "same-origin" }),
      ]);
      var data = responses[0].ok ? await responses[0].json() : null;
      var areas = responses[1].ok ? await responses[1].json() : null;
      if (seq !== buildingSequence) return;
      if (data) {
        data.building_id = data.building_id || data.id || Number(id);
        loadedBuilding = data;
        window.__rentalAnalysisBuilding = data;
        $("rentalBuildingName").textContent = data.display_building_name || data.building_name || "선택 건물";
        if (window.livingstayRenderAnalysisBuildingIdentity) window.livingstayRenderAnalysisBuildingIdentity($("rentalBuildingIdentity"), data);
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
        sliderBasePrice = null;
        syncSliderBounds();
      }
    } catch (ignore) {
      if (seq === buildingSequence) {
        $("rentalMarketPrice").placeholder = "직접 입력";
        $("rentalMarketPriceHint").textContent = "최근 실거래를 불러오지 못했습니다. 직접 입력할 수 있습니다.";
      }
    }
  }
  setupRentalSliders();
  ids.forEach(function (id) {
    $(id).addEventListener("input", function () {
      var hardKind = rentalHardKind(id);
      if (hardKind) {
        delete invalidRentalUrlFields[id];
        var safeValue = clampRentalValue(id, $(id).value);
        if (safeValue == null) {
          invalidRentalInputs[id] = true;
          $(id).value = lastValidRentalInputs[id] == null ? "" : String(lastValidRentalInputs[id]);
          setRentalInputError(id, id === "rentalMonthlyRent"
            ? "월세는 1~1,000만원 범위로 입력하세요"
            : "입력값이 허용 범위를 벗어났습니다.");
          return;
        }
        $(id).value = String(safeValue);
        lastValidRentalInputs[id] = safeValue;
        invalidRentalInputs[id] = false;
        rentCenterEdited = true;
        setRentalInputError(id, "");
      }
      if (id === "rentalVacancyMonths" && !loadingSharedValues) vacancyAssumed = false;
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
        $("rentalMarketPrice").value = "";
        sliderBasePrice = null;
        syncSliderBounds();
        clearTimeout(areaLookupTimer);
        areaLookupTimer = setTimeout(function () {
          loadMarketPrice(loadedBuildingId, buildingSequence);
        }, 300);
      }
      if (id === "rentalPurchasePrice") {
        updateAcquisitionCosts();
        updateEstimatedTax();
      }
      var valueButton = document.querySelector('[data-rental-value="' + id + '"]');
      if (valueButton) valueButton.textContent = formatInputValue(id, $(id).value);
      calculate();
    });
    $(id).addEventListener("change", function () {
      if (invalidRentalInputs[id]) {
        invalidRentalInputs[id] = false;
        return;
      }
      if (id === "rentalUnitArea") {
        resetRentCenterBase();
        syncSliderBounds();
        queueRentalSliderChange(id, true);
        return;
      }
      if (id === "rentalMarketPrice") {
        sliderBasePrice = null;
        syncSliderBounds();
        return;
      }
      if (["rentalPurchasePrice", "rentalLoanAmount", "rentalDeposit",
        "rentalMonthlyRent", "rentalVacancyMonths"].indexOf(id) >= 0) {
        syncSliderBounds(id);
        queueRentalSliderChange(id, true);
      }
    });
  });
  $("rentalLoanMethod").addEventListener("change", calculate);
  $("rentalReset").addEventListener("click", function () {
    taxManuallyEdited = false;
    marketPriceManuallyEdited = false;
    automaticMarketPrice = null;
    clearMarketEvidence();
    clearTimeout(areaLookupTimer);
    cancelRentalSliderChange();
    sliderBasePrice = null;
    rentCenterBase = null;
    rentCenterEdited = false;
    ids.forEach(function (id) { $(id).value = ""; });
    lastValidRentalInputs = Object.create(null);
    invalidRentalUrlFields = Object.create(null);
    $("rentalVacancyMonths").value = "";
    resetRentCenterBase();
    vacancyAssumed = true;
    positionMode = "net";
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
    syncSliderBounds();
    calculate();
    queueRentalSliderChange("rentalPurchasePrice", true);
  });
  window.addEventListener("livingstay:analysis-reset", function () {
    $("rentalReset").click();
  });
  updateMethodologyFormula();
  window.loadRentalAnalysis = loadBuilding;
  loadBuilding();
}());