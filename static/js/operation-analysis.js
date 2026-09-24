(function () {
  "use strict";
  var uploadedOccupancyBasis = null;

  var building = null;
  var benchmarks = [];
  var region = "";
  var subregion = "";
  var loadSequence = 0;
  var benchmarkLoadError = "";
  var animationFrame = 0;
  var initializedBuildingId = "";
  var scenarioSeeded = false;
  var uploadSequence = 0;
  var assumed = { adr: true, occ: true, opexRatio: true, mgmtFeeRatio: true, purchasePrice: true, compareRent: true };
  var purchasePriceBase = null;
  var uploadedMonthlyDayBasis = null;
  var uploadedMonthPeriod = null;
  var compareRentSource = null;
  var roneRentStatus = "";
  var roneBenchmarksByBuilding = Object.create(null);
  var roneRequestsByBuilding = Object.create(null);
  var crossRentSync = false;
  var rentalRentUserChanged = false;
  var sliderBounds = Object.create(null);
  var activeSliderField = "";
  var sliderCommitTimer = 0;
  var sliderCommitGeneration = 0;
  var pendingSliderFields = Object.create(null);
  var sliderUtils = window.analysisSliderUtils;
  var labels = {
    adr: ["operationAdr", "ADR", "원", 5000], occ: ["operationOcc", "OCC", "%", 1],
    opexRatio: ["operationOpexRatio", "운영경비율", "%", 1],
    mgmtFeeRatio: ["operationMgmtFeeRatio", "위탁수수료율", "%", 1],
    purchasePrice: ["operationPurchasePrice", "호실 매입가", "만원", 500],
    compareRent: ["operationCompareRent", "비교 월세", "만원", 5],
  };
  var originalOperationQuery = new URLSearchParams(location.search);
  var originalOperationBuildingId = originalOperationQuery.get("building_id") || "";
  var activeBuildingId = originalOperationBuildingId;

  function $(id) { return document.getElementById(id); }
  function number(value) {
    return value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
  }
  function format(value, digits) {
    var parsed = number(value);
    return parsed == null ? "—" : parsed.toLocaleString("ko-KR", {
      maximumFractionDigits: digits == null ? 1 : digits,
    });
  }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }
  function buildingId() {
    return new URLSearchParams(location.search).get("building_id") || "";
  }
  function average(key) {
    var values = benchmarks.map(function (item) { return number(item[key]); })
      .filter(function (value) { return value != null; });
    return values.length
      ? values.reduce(function (sum, value) { return sum + value; }, 0) / values.length
      : null;
  }
  function regionalBaseline() {
    var exact = benchmarks.find(function (item) {
      return String(item.region || "").replace(/\s+/g, "") === String(subregion || "").replace(/\s+/g, "");
    });
    return {
      adr: exact ? number(exact.adr) : average("adr"),
      occ: exact ? number(exact.occ) : average("occ"),
      exact: !!exact,
    };
  }
  function operationName() {
    var input = $("operationBusinessName");
    var value = input && input.value.trim();
    return value || building && (building.display_building_name || building.building_name)
      || "선택 숙박시설";
  }
  function selectedLodging() {
    var lodgings = building && Array.isArray(building.lodgings) ? building.lodgings : [];
    var index = Number($("operationLodging").value);
    return Number.isInteger(index) && index >= 0 ? lodgings[index] : null;
  }
  function selectedRooms() {
    return number($("operationRoomCountInput").value);
  }
  function settings() {
    var config = window.operationAnalysisSettings;
    if (config && Number.isFinite(config.DEFAULT_OPEX_RATIO)
      && Number.isFinite(config.DEFAULT_MGMT_FEE_RATIO)
      && Number.isFinite(config.MONTH_DAYS_FALLBACK) && config.MONTH_DAYS_FALLBACK > 0) return config;
    var message = "운영 분석 설정 모듈을 불러오지 못했습니다. 페이지를 새로고침하거나 관리자에게 문의해 주세요.";
    var host = $("operationSliders");
    if (host) host.innerHTML = '<p class="operation-settings-error" role="alert">' + message + "</p>";
    return null;
  }
  function ensureOperationInputs() {
    [
      ["operationOpexRatio", "hidden"], ["operationMgmtFeeRatio", "hidden"],
      ["operationPurchasePrice", "hidden"], ["operationCompareRent", "hidden"],
    ].forEach(function (entry) {
      if (!$(entry[0])) {
        var input = document.createElement("input");
        input.type = entry[1]; input.id = entry[0];
        $("operationInputs").appendChild(input);
      }
    });
  }
  function value(field) { return number($(labels[field][0]).value); }
  function roundTo(valueToRound, step) { return Math.round(valueToRound / step) * step; }
  function setAssumption(field, isAssumed) {
    assumed[field] = !!isAssumed;
    var row = document.querySelector('[data-operation-row="' + field + '"]');
    var badge = row && row.querySelector("[data-operation-assumption]");
    if (badge) {
      badge.classList.toggle("hidden", !assumed[field]);
      badge.textContent = field === "adr" || field === "occ" ? "가정값(지역 평균)"
        : field === "compareRent" && compareRentSource ? "가정값(R-ONE 수익률)" : "가정값";
    }
  }
  function sharedRentValue() {
    if (!rentalScenarioMatchesBuilding()) return null;
    var rent = number(document.getElementById("rentalMonthlyRent") && document.getElementById("rentalMonthlyRent").value);
    return rent != null && rent > 0 ? { value: rent, assumed: false } : null;
  }
  function sharedPurchaseValue() {
    if (!rentalScenarioMatchesBuilding()) return null;
    var purchase = number(document.getElementById("rentalPurchasePrice") && document.getElementById("rentalPurchasePrice").value);
    if (purchase != null && purchase > 0) return { value: purchase, assumed: false };
    var market = number(document.getElementById("rentalMarketPrice") && document.getElementById("rentalMarketPrice").value);
    return market != null && market > 0 ? { value: market, assumed: true } : null;
  }
  function roneSourceLabel(source) {
    var benchmark = source.benchmark || {};
    var name = String(benchmark.region_name || "R-ONE 공개지역");
    var period = String(benchmark.period || "기준기간 미확인");
    var type = String(benchmark.property_type_name || "오피스텔");
    var provider = source.source && (source.source.provider || source.source.name)
      ? String(source.source.provider || source.source.name) : "한국부동산원 R-ONE";
    var proxy = source.source && source.source.is_exact_asset_type === false;
    return "비교 월세 가정 출처: " + provider + " · " + name + " · " + period + " · " + type
      + " 수익률 " + format(benchmark.income_yield, 2) + "%."
      + (proxy ? " 생활숙박시설 정확 유형 자료가 없어 오피스텔 수익률을 대체 기준으로 사용했습니다." : "");
  }
  function applyRoneBreakEvenRent(source) {
    if (!source || !assumed.compareRent || !buildingId() || !value("purchasePrice")) return;
    var incomeYield = source.benchmark.income_yield;
    var rent = roundTo(value("purchasePrice") * incomeYield / 100 / 12, 5);
    if (!Number.isFinite(rent) || rent <= 0) {
      roneRentStatus = "매입가·R-ONE 수익률로 양수 비교 월세를 계산할 수 없습니다. 비교 월세를 직접 입력해 주세요.";
      syncSliderPositions();
      return;
    }
    setInput("compareRent", rent);
    compareRentSource = {
      incomeYield: incomeYield,
      text: roneSourceLabel(source),
    };
    roneRentStatus = compareRentSource.text;
    setAssumption("compareRent", true);
    syncSliderPositions();
    crossRent();
    updateOperationUrl("compareRent");
    scheduleRender();
  }
  function applyRentYieldFallback(reason) {
    if (!assumed.compareRent || value("compareRent") != null) return;
    var basis = currentPurchaseBasis();
    if (basis == null || basis <= 0) return;
    setInput("compareRent", basis * 0.005);
    compareRentSource = null;
    roneRentStatus = (reason ? reason + " " : "")
      + "검증된 R-ONE 수익률을 사용할 수 없어 기준 매입가의 0.5% 월 수익률을 비교 월세 가정값으로 적용했습니다.";
    setAssumption("compareRent", true);
    syncSliderPositions();
    crossRent();
    updateOperationUrl("compareRent");
    scheduleRender();
  }
  function ensureRoneCompareRent(sequence) {
    var id = buildingId(), purchase = value("purchasePrice");
    if (!id || !assumed.compareRent) return;
    if (compareRentSource && Number.isFinite(compareRentSource.incomeYield)) {
      if (purchase != null && purchase > 0) {
        var adjustedRent = roundTo(purchase * compareRentSource.incomeYield / 100 / 12, 5);
        if (adjustedRent > 0 && adjustedRent !== value("compareRent")) {
          setInput("compareRent", adjustedRent);
          roneRentStatus = compareRentSource.text;
          syncSliderPositions();
          crossRent();
          updateOperationUrl("compareRent");
          scheduleRender();
        }
      }
      return;
    }
    if (value("compareRent") != null || purchase == null || purchase <= 0) return;
    if (roneBenchmarksByBuilding[id]) {
      applyRoneBreakEvenRent(roneBenchmarksByBuilding[id]);
      return;
    }
    roneRentStatus = "R-ONE 오피스텔 수익률을 확인해 비교 월세를 계산합니다.";
    syncSliderPositions();
    var request = roneRequestsByBuilding[id];
    if (!request) {
      request = fetch("/api/analysis/rental-benchmark?building_id=" + encodeURIComponent(id),
        { credentials: "same-origin" })
        .then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        }).catch(function () { return { ok: false, error: "R-ONE 임대수익률 자료 요청에 실패했습니다." }; })
        .then(function (result) {
          delete roneRequestsByBuilding[id];
          var payload = result.payload || {};
          var benchmark = payload.benchmark || {};
          var source = payload.source || {};
          var valid = result.ok && payload.ok === true && payload.available === true
            && source && Number.isFinite(benchmark.income_yield) && benchmark.income_yield > 0
            && String(benchmark.region_name || "").trim() !== ""
            && String(benchmark.period || "").trim() !== ""
            && String(benchmark.property_type_name || "").trim() !== "";
          if (valid) roneBenchmarksByBuilding[id] = payload;
          return valid ? { payload: payload } : { error: payload.reason || payload.message
            || "검증된 R-ONE 임대수익률 자료를 사용할 수 없습니다." };
        });
      roneRequestsByBuilding[id] = request;
    }
    request.then(function (result) {
      if (sequence !== loadSequence || id !== buildingId() || !assumed.compareRent
        || activeSliderField === "purchasePrice") return;
      if (value("compareRent") != null && !compareRentSource) return;
      var currentPurchase = value("purchasePrice");
      if (currentPurchase == null || currentPurchase <= 0) return;
      if (result.payload) {
        applyRoneBreakEvenRent(result.payload);
      } else {
        applyRentYieldFallback(result.error || "검증된 R-ONE 임대수익률 자료를 사용할 수 없습니다.");
        if (value("compareRent") == null) {
          roneRentStatus = result.error || "검증된 R-ONE 임대수익률 자료를 사용할 수 없습니다.";
          syncSliderPositions();
        }
      }
    });
  }
  function syncRentSource() {
    var note = $("operationRoneRentSource");
    if (!note) return;
    var text = compareRentSource ? compareRentSource.text : roneRentStatus;
    if (!text && value("purchasePrice") == null) {
      text = "호실 매입가가 확인되면 R-ONE 수익률 기준 비교 월세를 산출합니다.";
    }
    note.textContent = text || "";
    note.classList.toggle("hidden", !text);
  }
  function setInput(field, nextValue) {
    if (!$(labels[field][0])) return;
    $(labels[field][0]).value = nextValue == null ? "" : String(nextValue);
  }
  function rentalScenarioMatchesBuilding() {
    var rentalBuilding = window.__rentalAnalysisBuilding;
    if (!rentalBuilding || !buildingId()) return false;
    var rentalId = rentalBuilding.building_id != null ? rentalBuilding.building_id : rentalBuilding.id;
    return rentalId != null && String(rentalId) === buildingId();
  }
  function syncUrlForBuildingChange(id) {
    var operationKeys = ["adr", "occ", "opex_ratio", "mgmt_fee", "buy", "rent"];
    var rentalKeys = ["r_unit_area", "r_purchase", "r_deposit", "r_rent", "r_vacancy",
      "r_loan", "r_rate", "r_years", "r_method", "r_management", "r_other", "r_yieldmode"];
    var params = new URLSearchParams(location.search);
    operationKeys.concat(rentalKeys).forEach(function (key) { params.delete(key); });
    if (id) params.set("building_id", id);
    else params.delete("building_id");
    if (originalOperationBuildingId === id) {
      operationKeys.concat(rentalKeys).forEach(function (key) {
        if (originalOperationQuery.has(key)) params.set(key, originalOperationQuery.get(key));
      });
    }
    history.replaceState({}, "", "/analysis" + (params.toString() ? "?" + params.toString() : ""));
  }
  function resetOperationScenarioForBuildingChange(id) {
    uploadSequence += 1;
    sliderCommitGeneration += 1;
    window.clearTimeout(sliderCommitTimer);
    sliderCommitTimer = 0;
    pendingSliderFields = Object.create(null);
    activeSliderField = "";
    ensureOperationInputs();
    building = null;
    benchmarks = [];
    region = "";
    subregion = "";
    benchmarkLoadError = "";
    window.__operationBenchmarkSource = "";
    window.__operationAnalysisBuilding = null;
    window.__operationAnalysisState = { ready: false, buildingId: id, error: "building changed" };
    window.__operationChartLayout = { ready: false };
    ["adr", "occ", "opexRatio", "mgmtFeeRatio", "purchasePrice", "compareRent"].forEach(function (field) {
      setInput(field, "");
    });
    assumed = { adr: true, occ: true, opexRatio: true, mgmtFeeRatio: true, purchasePrice: true, compareRent: true };
    purchasePriceBase = null;
    compareRentSource = null;
    roneRentStatus = "";
    uploadedOccupancyBasis = null;
    uploadedMonthlyDayBasis = null;
    uploadedMonthPeriod = null;
    rentalRentUserChanged = false;
    window.__operationRentalRentGenerated = null;
    initializedBuildingId = "";
    scenarioSeeded = false;
    var config = settings();
    if (config) {
      setInput("opexRatio", config.DEFAULT_OPEX_RATIO);
      setInput("mgmtFeeRatio", config.DEFAULT_MGMT_FEE_RATIO);
    }
    if ($("operationFiles")) {
      $("operationFiles").value = "";
      $("operationFiles").disabled = false;
    }
    if ($("operationFileStatus")) $("operationFileStatus").textContent = "PDF·엑셀·CSV·이미지를 올리면 ADR·OCC·기간이 자동 반영됩니다.";
    if ($("operationLodging")) $("operationLodging").innerHTML = '<option value="">건물 운영자료 불러오는 중…</option>';
    if ($("operationBusinessName")) $("operationBusinessName").value = "";
    if ($("operationRoomCountInput")) $("operationRoomCountInput").value = "";
    if (window.livingstayRenderAnalysisBuildingIdentity) {
      window.livingstayRenderAnalysisBuildingIdentity($("operationBuildingIdentity"), null);
    }
    renderRoomCount();
    setupOperationSliders();
    if (config) syncOperationSliders();
    syncUrlForBuildingChange(id);
    renderChart();
  }
  function seedScenario() {
    ensureOperationInputs();
    var config = settings();
    if (!config) return;
    var baseline = regionalBaseline();
    var isNewBuilding = initializedBuildingId !== buildingId();
    var params = originalOperationBuildingId === buildingId()
      ? originalOperationQuery : new URLSearchParams();
    var signedOperationScenario = ["adr", "occ", "opex_ratio", "mgmt_fee", "buy", "rent"].some(function (key) {
      return params.has(key);
    });
    if (isNewBuilding) {
      if (assumed.compareRent && compareRentSource) {
        setInput("compareRent", "");
        compareRentSource = null;
      }
      roneRentStatus = "";
      var purchaseSource = !signedOperationScenario && !window.__analysisShareToken
        && rentalScenarioMatchesBuilding()
        ? sharedPurchaseValue() : null;
      if (purchaseSource && (purchasePriceBase == null || assumed.purchasePrice)) {
        purchasePriceBase = purchaseSource.value;
      } else if (!purchaseSource && assumed.purchasePrice) {
        purchasePriceBase = null;
      }
      if (baseline.adr != null && (value("adr") == null || assumed.adr)) {
        setInput("adr", roundTo(baseline.adr, 5000)); setAssumption("adr", true);
      }
      if (baseline.occ != null && (value("occ") == null || assumed.occ)) {
        setInput("occ", roundTo(baseline.occ, 1)); setAssumption("occ", true);
      }
      initializedBuildingId = buildingId();
    }
    if (!scenarioSeeded && signedOperationScenario) {
      ["adr", "occ", "opex_ratio", "mgmt_fee", "buy", "rent"].forEach(function (key) {
        if (!params.has(key)) return;
        var field = ({ adr: "adr", occ: "occ", opex_ratio: "opexRatio", mgmt_fee: "mgmtFeeRatio", buy: "purchasePrice", rent: "compareRent" })[key];
        var parsed = Number(params.get(key));
        var bounds = {
          adr: [50000, 1000000], occ: [0, 100], opexRatio: [10, 60],
          mgmtFeeRatio: [0, 50], purchasePrice: [100, 1000000], compareRent: [5, 1000],
        }[field];
        if (Number.isFinite(parsed) && parsed >= bounds[0] && parsed <= bounds[1]) {
          setInput(field, parsed); setAssumption(field, false);
          if (field === "compareRent") { compareRentSource = null; roneRentStatus = ""; }
          if (field === "purchasePrice" && purchasePriceBase == null) purchasePriceBase = parsed;
        }
      });
      scenarioSeeded = true;
    } else if (!scenarioSeeded) {
      scenarioSeeded = true;
      if ((!window.__analysisShareToken || signedOperationScenario) && rentalScenarioMatchesBuilding()) {
        var purchase = sharedPurchaseValue(), rent = sharedRentValue();
        if (purchase && (value("purchasePrice") == null || assumed.purchasePrice)) {
          setInput("purchasePrice", purchase.value); setAssumption("purchasePrice", purchase.assumed);
        }
        if (rent && (value("compareRent") == null || assumed.compareRent)) {
          setInput("compareRent", rent.value); setAssumption("compareRent", false);
        }
      }
    }
    if (value("opexRatio") == null) setInput("opexRatio", config.DEFAULT_OPEX_RATIO);
    if (value("mgmtFeeRatio") == null) setInput("mgmtFeeRatio", config.DEFAULT_MGMT_FEE_RATIO);
    syncOperationSliders();
    ensureRoneCompareRent(loadSequence);
  }
  function fieldMin(field) {
    var bounds = sliderBounds[field];
    return bounds ? bounds.min : 0;
  }
  function fieldMax(field) {
    var bounds = sliderBounds[field];
    return bounds ? bounds.max : 0;
  }
  function currentPurchaseBasis() {
    var market = number(document.getElementById("rentalMarketPrice")
      && document.getElementById("rentalMarketPrice").value);
    if (market != null && market > 0) return market;
    if (purchasePriceBase != null && purchasePriceBase > 0) return purchasePriceBase;
    var source = sharedPurchaseValue();
    if (source && source.value > 0) {
      purchasePriceBase = source.value;
      return purchasePriceBase;
    }
    return null;
  }
  function computeSliderBounds() {
    if (!sliderUtils) throw new Error("공통 슬라이더 설정을 불러오지 못했습니다.");
    var baseline = regionalBaseline();
    var bounds = Object.create(null);
    if (baseline.adr != null && baseline.adr > 0) {
      var adrUnit = sliderUtils.niceStep(baseline.adr / 100);
      var adrMin = Math.max(0, Math.round(baseline.adr * 0.4 / adrUnit) * adrUnit);
      var adrMax = baseline.adr * 2;
      bounds.adr = {
        min: adrMin, max: Math.max(adrMax, adrMin + 1),
        step: sliderUtils.niceStep((adrMax - adrMin) / 60),
      };
    } else {
      bounds.adr = { min: 50000, max: 300000, step: 5000 };
    }
    bounds.occ = { min: 20, max: 100, step: 1 };
    bounds.opexRatio = { min: 10, max: 60, step: 1 };
    bounds.mgmtFeeRatio = { min: 0, max: 50, step: 1 };

    var purchaseBasis = currentPurchaseBasis();
    if (purchaseBasis != null) {
      bounds.purchasePrice = sliderUtils.purchaseBounds(purchaseBasis);
      bounds.purchasePrice = sliderUtils.includeValue(bounds.purchasePrice, value("purchasePrice"));
    } else {
      bounds.purchasePrice = null;
    }

    var compareCenter = value("compareRent");
    var sharedRent = sharedRentValue();
    if (!(compareCenter > 0) && sharedRent) compareCenter = sharedRent.value;
    if (!(compareCenter > 0) && purchaseBasis != null) compareCenter = purchaseBasis * 0.005;
    bounds.compareRent = compareCenter > 0 ? sliderUtils.rentBounds(compareCenter) : null;
    if (bounds.compareRent) bounds.compareRent = sliderUtils.includeValue(bounds.compareRent, value("compareRent"));

    ["adr", "occ", "opexRatio", "mgmtFeeRatio"].forEach(function (field) {
      bounds[field] = sliderUtils.includeValue(bounds[field], value(field));
    });
    sliderBounds = bounds;
  }
  function displayValue(field) {
    var valueNow = value(field);
    if (field === "purchasePrice" && !sliderBounds.purchasePrice) return "입력 필요";
    if (valueNow == null) return "입력 필요";
    if ((field === "purchasePrice" || field === "compareRent") && sliderUtils) {
      return sliderUtils.formatMan(valueNow, 0);
    }
    return format(valueNow, field === "occ" ? 2 : 0) + labels[field][2];
  }
  function sliderMarkup(field) {
    var meta = labels[field], input = $(meta[0]), current = number(input.value);
    var computedBounds = sliderBounds[field];
    var bounds = computedBounds || { min: 0, max: 0, step: 1 };
    var initial = current == null ? bounds.min
      : Math.max(bounds.min, Math.min(bounds.max,
        bounds.min + Math.round((current - bounds.min) / bounds.step) * bounds.step));
    return '<div class="operation-slider-row" data-operation-row="' + field + '"><div class="operation-slider-head"><label for="operationSlider_' + field + '">' + meta[1] + '</label><span>'
      + '<button class="operation-value-button" type="button" data-operation-value="' + field + '">' + displayValue(field) + '</button>'
      + '<i data-operation-assumption' + (assumed[field] ? "" : ' class="hidden"') + '>' + (field === "adr" || field === "occ" ? "가정값(지역 평균)" : "가정값") + "</i>"
      + '</span></div><input id="operationSlider_' + field + '" type="range" data-operation-slider="' + field + '" min="' + bounds.min + '" max="' + bounds.max + '" step="' + bounds.step + '" value="' + initial + '" aria-label="' + meta[1] + '"'
      + (((field === "purchasePrice" || field === "compareRent") && !computedBounds) ? " disabled" : "") + "></div>";
  }
  function syncOperationSliders() {
    var host = $("operationSliders");
    if (!host) return;
    computeSliderBounds();
    var dayBasis = monthlyDayBasis();
    var baseline = regionalBaseline();
    var operationGroupTitle = "운영 조건";
    if (baseline.adr != null && baseline.occ != null) {
      operationGroupTitle += " · " + (subregion || region || "지역")
        + (baseline.exact ? " 전체등급" : " 시군구 평균")
        + " ADR " + format(baseline.adr, 0) + "원 · OCC " + format(baseline.occ, 1) + "%";
    }
    var groups = [
      [operationGroupTitle, ["adr", "occ"]],
      ["비용 조건", ["opexRatio", "mgmtFeeRatio"]],
      ["비교 조건", ["purchasePrice", "compareRent"]],
    ];
    var costTooltip = "위탁운영 계약서·월 정산서의 운영경비와 수수료율을 입력하세요. 기본값은 공개된 수도권 생숙 정산 사례(2021년 보도, 운영경비 매출의 26.65%, 매출이익 대비 위탁수수료 30%)를 참고한 가정값이며, 실제 비율은 건물·운영사·계약 구조에 따라 다릅니다.";
    host.innerHTML = groups.map(function (group) {
      var costGroup = group[0] === "비용 조건";
      return '<section class="operation-slider-group"><h3' + (costGroup
        ? ' title="' + escapeHtml(costTooltip) + '"' : "") + '>' + escapeHtml(group[0])
        + (costGroup ? ' <button class="operation-cost-info" type="button" title="' + escapeHtml(costTooltip)
          + '" aria-label="' + escapeHtml(costTooltip) + '">ⓘ</button>' : "")
        + '</h3><div class="operation-slider-list">'
        + group[1].map(sliderMarkup).join("") + '</div></section>';
    }).join("") + '<p class="operation-slider-hint">값을 눌러 직접 입력할 수 있습니다. 월 산정 일수 '
      + format(dayBasis.days, 1) + "일 · " + escapeHtml(dayBasis.source) + ".</p>"
      + '<p class="operation-rent-source hidden" id="operationRoneRentSource"></p>'
      + '<p class="operation-cost-share" id="operationCostShare"></p>';
    var costShare = $("operationCostShare");
    if (costShare && value("opexRatio") != null && value("mgmtFeeRatio") != null) {
      var owner = (1 - value("opexRatio") / 100) * (1 - value("mgmtFeeRatio") / 100) * 100;
      costShare.textContent = "실질 공제율 " + (100 - owner).toFixed(1) + "% · 소유주 몫 " + owner.toFixed(1) + "%";
    }
    syncSliderPositions();
  }
  function updateSliderLabel(field) {
    var button = document.querySelector('[data-operation-value="' + field + '"]');
    if (button && !button.querySelector("input")) button.textContent = displayValue(field);
  }
  function updateSliderAssumptionBadge(field) {
    var badge = document.querySelector('[data-operation-row="' + field + '"] [data-operation-assumption]');
    if (badge) {
      badge.classList.toggle("hidden", !assumed[field]);
      badge.textContent = field === "adr" || field === "occ" ? "가정값(지역 평균)"
        : field === "compareRent" && compareRentSource ? "가정값(R-ONE 수익률)" : "가정값";
    }
  }
  function syncSliderPositions(options) {
    options = options || {};
    if (options.recompute !== false) computeSliderBounds();
    document.querySelectorAll("[data-operation-slider]").forEach(function (range) {
      var field = range.dataset.operationSlider, current = value(field);
      var bounds = sliderBounds[field];
      if (bounds && field !== activeSliderField) {
        range.min = String(bounds.min);
        range.max = String(bounds.max);
        range.step = String(bounds.step);
        range.disabled = false;
        range.value = String(current == null ? bounds.min : sliderUtils.nearest(current, bounds));
      } else if (!bounds && (field === "purchasePrice" || field === "compareRent")) {
        range.min = "0"; range.max = "0"; range.step = "1"; range.value = "0"; range.disabled = true;
      }
      updateSliderLabel(field);
      updateSliderAssumptionBadge(field);
    });
    var costShare = $("operationCostShare");
    if (costShare && value("opexRatio") != null && value("mgmtFeeRatio") != null) {
      var owner = (1 - value("opexRatio") / 100) * (1 - value("mgmtFeeRatio") / 100) * 100;
      costShare.textContent = "실질 공제율 " + (100 - owner).toFixed(1) + "% · 소유주 몫 " + owner.toFixed(1) + "%";
    }
    syncRentSource();
  }
  function scheduleRender() {
    if (animationFrame) return;
    animationFrame = window.requestAnimationFrame(function () { animationFrame = 0; renderChart(); });
  }
  function scheduleSliderCommit(field) {
    activeSliderField = "";
    if (field) pendingSliderFields[field] = true;
    window.clearTimeout(sliderCommitTimer);
    var generation = ++sliderCommitGeneration;
    var committedBuildingId = buildingId();
    var committedLoadSequence = loadSequence;
    sliderCommitTimer = window.setTimeout(function () {
      if (generation !== sliderCommitGeneration || committedBuildingId !== buildingId()
        || committedLoadSequence !== loadSequence) return;
      sliderCommitTimer = 0;
      var changedFields = Object.keys(pendingSliderFields);
      pendingSliderFields = Object.create(null);
      syncSliderPositions({ recompute: true });
      if (generation !== sliderCommitGeneration || committedBuildingId !== buildingId()
        || committedLoadSequence !== loadSequence) return;
      if (changedFields.indexOf("purchasePrice") >= 0 || changedFields.indexOf("compareRent") >= 0) crossRent();
      if (generation !== sliderCommitGeneration || committedBuildingId !== buildingId()
        || committedLoadSequence !== loadSequence) return;
      updateOperationUrl(changedFields);
      if (changedFields.indexOf("purchasePrice") >= 0) ensureRoneCompareRent(loadSequence);
      scheduleRender();
    }, 300);
  }
  function crossRent() {
    var purchase = value("purchasePrice"), rent = value("compareRent");
    var purchaseInput = document.getElementById("rentalPurchasePrice");
    var rentInput = document.getElementById("rentalMonthlyRent");
    crossRentSync = true;
    try {
      [["purchase", purchase, purchaseInput], ["rent", rent, rentInput]].forEach(function (entry) {
        if (!entry[2] || entry[1] == null) return;
        if (Number(entry[2].value) === entry[1]) return;
        entry[2].value = String(entry[1]);
        entry[2].dispatchEvent(new Event("input", { bubbles: true }));
        entry[2].dispatchEvent(new Event("change", { bubbles: true }));
      });
    } finally {
      crossRentSync = false;
    }
    if (rent != null && assumed.compareRent && compareRentSource) {
      window.__operationRentalRentGenerated = { buildingId: buildingId(), value: rent };
    } else {
      window.__operationRentalRentGenerated = null;
    }
  }
  function updateOperationUrl(changedFields) {
    var params = new URLSearchParams(location.search);
    params.set("mode", "operation");
    if (buildingId()) params.set("building_id", buildingId());
    var fieldParams = {
      adr: "adr", occ: "occ", opexRatio: "opex_ratio", mgmtFeeRatio: "mgmt_fee",
      purchasePrice: "buy", compareRent: "rent",
    };
    (Array.isArray(changedFields) ? changedFields : [changedFields]).filter(Boolean).forEach(function (field) {
      var key = fieldParams[field];
      var current = value(field);
      if (current == null) params.delete(key);
      else params.set(key, String(current));
    });
    history.replaceState({}, "", "/analysis?" + params.toString());
  }
  function bindOperationShare() {
    var button = document.querySelector('#operationReportActions [data-report-action="share"]');
    if (!button || button.dataset.operationShareBound) return;
    button.dataset.operationShareBound = "true";
    button.onclick = async function () {
      try {
        var url;
        if (window.__analysisShareToken) {
          url = new URL(location.href);
        } else {
          var response = await fetch("/api/analysis/share-link", {
            method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ building_id: Number(buildingId()), mode: "operation" }),
          });
          var payload = await response.json().catch(function () { return {}; });
          if (!response.ok || !payload.path) throw Error(payload.message || "분석 링크를 만들지 못했습니다.");
          url = new URL(payload.path, location.origin);
          if (url.origin !== location.origin) throw Error("분석 공유 링크의 주소가 올바르지 않습니다.");
        }
        var state = window.__operationAnalysisState || {};
        [["adr", state.adr], ["occ", state.occ], ["opex_ratio", state.opexRatio],
          ["mgmt_fee", state.mgmtFeeRatio], ["buy", state.purchasePrice], ["rent", state.compareRent]]
          .forEach(function (entry) {
            if (entry[1] != null) url.searchParams.set(entry[0], String(entry[1]));
          });
        var data = { title: operationName() + "_" + new Date().toLocaleDateString("sv-SE"),
          text: operationName() + " 운영분석 결과를 확인해보세요.", url: url.toString() };
        if (navigator.share) await navigator.share(data);
        else if (navigator.clipboard) await navigator.clipboard.writeText(data.url).then(function () { alert("분석 링크를 복사했습니다."); });
      } catch (error) {
        if (!error || error.name !== "AbortError") alert(error && error.message || "공유하지 못했습니다.");
      }
    };
  }

  function applyDerivedOcc() {
    if (!uploadedOccupancyBasis) return null;
    var rooms = selectedRooms();
    var sold = number(uploadedOccupancyBasis.soldRooms);
    var days = number(uploadedOccupancyBasis.days);
    var occ = rooms && sold != null && days
      ? Math.round(sold / (rooms * days) * 10000) / 100
      : null;
    if (occ == null || occ < 0 || occ > 100) {
      $("operationOcc").value = "";
      return null;
    }
    $("operationOcc").value = occ;
    return occ;
  }
  function officialRooms() {
    var lodging = selectedLodging();
    return lodging ? number(lodging.room_count) : building && (number(building.lodging_room_total)
      || number(building.building_name_representative_room_count));
  }
  function setModeClass() {
    var operation = new URLSearchParams(location.search).get("mode") === "operation"
      || $("operationTab").getAttribute("aria-selected") === "true";
    document.querySelector(".analysis-shell").classList.toggle("operation-mode", operation);
  }
  function setBuildingStatus(name, ready) {
    if (ready && window.setAnalysisBuildingStatus) window.setAnalysisBuildingStatus(name);
  }
  function renderLodgingOptions() {
    var lodgings = building && Array.isArray(building.lodgings) ? building.lodgings : [];
    if (!lodgings.length) {
      $("operationLodging").innerHTML = '<option value="">영업신고 업소 확인 불가</option>';
    } else {
      $("operationLodging").innerHTML = lodgings.map(function (item, index) {
        var rooms = number(item.room_count);
        return '<option value="' + index + '">' + escapeHtml(item.biz_name || "업소명 미확인")
          + " · " + (rooms == null ? "객실 수 미상" : format(rooms, 0) + "실") + "</option>";
      }).join("");
      $("operationLodging").value = "0";
    }
    renderRoomCount();
  }
  function renderRoomCount() {
    var rooms = officialRooms();
    $("operationRoomCount").textContent = rooms == null ? "신고 객실 수 확인 불가" : format(rooms, 0) + "실";
    $("operationRoomCountInput").value = rooms == null ? "" : String(rooms);
  }
  function grade(adr, occ) {
    var baseline = regionalBaseline();
    var baseAdr = baseline.adr;
    var baseOcc = baseline.occ;
    if (baseAdr == null || baseOcc == null) return "비교자료 부족";
    return adr >= baseAdr
      ? (occ >= baseOcc ? "프리미엄 우수운영" : "가격조정 필요")
      : (occ >= baseOcc ? "고가동·저단가형" : "운영개선 필요");
  }
  function renderTop() {
    var list = benchmarks.slice().sort(function (a, b) {
      return (number(b.revpar) || 0) - (number(a.revpar) || 0);
    }).slice(0, 5);
    $("operationTopTitle").textContent = (region ? region + " " : "") + "시군구 숙박 운영지표 TOP 5";
    $("operationTopRows").innerHTML = list.length ? list.map(function (item, index) {
      return "<tr><td>" + (index + 1) + "</td><td><b>" + escapeHtml(item.region) + "</b></td><td>"
        + format(item.adr, 0) + "원</td><td>" + format(item.occ, 1) + "%</td><td>"
        + format(item.revpar, 0) + "원</td><td>" + format(item.foreign, 1)
        + '%</td><td><span class="recommendation-status">' + escapeHtml(grade(item.adr, item.occ))
        + "</span></td></tr>";
    }).join("") : '<tr><td colspan="7">해당 시도의 공개 운영지표가 없습니다.</td></tr>';
  }
  function renderEvidence(baseAdr, baseOcc) {
    $("operationRegionBaseline").textContent = subregion || (region ? region + " 시군구" : "—");
    $("operationAdrBaseline").textContent = baseAdr == null ? "—" : format(baseAdr, 0) + "원";
    $("operationOccBaseline").textContent = baseOcc == null ? "—" : format(baseOcc, 1) + "%";
    $("operationSampleBaseline").textContent = format(benchmarks.length, 0) + "개 시군구";
    var baseline = regionalBaseline();
    var sourceNote = document.querySelector("#operationAnalysis .operation-benchmark-note");
    if (sourceNote) {
      var source = window.__operationBenchmarkSource || "";
      sourceNote.textContent = benchmarkLoadError ? benchmarkLoadError
        : (source ? source + "의 호텔업 운영 통계입니다. " : "2024년 공공 호텔업 통계입니다. ")
          + "호텔 ADR·OCC 비교값은 생활숙박시설 위탁운영의 실제 정산 실적과 같지 않으며, 참고 비교기준으로만 사용합니다.";
    }
    $("operationMethodRegion").textContent = subregion
      ? subregion + "의 2024년 전체등급 운영지표 ADR·OCC를 사분면 중앙 기준선으로 사용합니다."
      : region
        ? region + " 내 " + benchmarks.length
          + "개 시군구의 운영지표 평균을 사분면 기준선으로 사용합니다."
      : "선택 건물의 주소로 비교지역을 자동 산정합니다.";
    var method = document.querySelector("#operationAnalysis .methodology");
    var formula = method && method.querySelector(".formula");
    if (formula && !method.textContent.includes("실질 공제율")) {
      formula.innerHTML += "<br>매출이익 = 매출 × (1 − 운영경비율)<br>"
        + "호실 월 순수익 = 매출이익 × (1 − 위탁수수료율)<br>"
        + "실질 공제율 = 1 − (1 − 운영경비율) × (1 − 위탁수수료율)<br>"
        + "호실 월 매출 = ADR × OCC × 월 일수<br>연 수익률 = 호실 월 순수익 × 12 ÷ 호실 매입가";
      formula.dataset.costFormula = "true";
    }
    if (method && !method.textContent.includes("위탁운영 계약서")) {
      var disclaimer = document.createElement("p");
      disclaimer.className = "operation-cost-disclaimer";
      disclaimer.textContent = "운영경비·위탁수수료 기본값은 참고용 가정값입니다. 실제 정산은 위탁운영 계약서와 월 정산서를 기준으로 하며, 계약 구조(정액·매출연동·이익배분)에 따라 다릅니다. 월 일수 원자료가 확인되지 않아 30.4일을 적용했습니다.";
      method.appendChild(disclaimer);
    }
    var lodgings = building && Array.isArray(building.lodgings) ? building.lodgings : [];
    var cards = [
      ["연결 영업신고", lodgings.length + "곳", "선택 건물의 정상 영업 업소"],
      ["비교지역", subregion || region || "—", "건물 주소에서 자동 산정"],
      ["지역 평균 ADR", baseAdr == null ? "—" : format(baseAdr, 0) + "원",
        baseline.exact ? subregion + " 전체등급" : "시군구 평균"],
      ["지역 평균 OCC", baseOcc == null ? "—" : format(baseOcc, 1) + "%",
        baseline.exact ? subregion + " 전체등급" : "시군구 평균"],
    ];
    $("operationSummary").innerHTML = cards.map(function (card) {
      return '<article class="analysis-card summary-tile"><div class="summary-label">'
        + escapeHtml(card[0]) + '</div><div class="summary-value">' + escapeHtml(card[1])
        + '</div><div class="summary-note">' + escapeHtml(card[2]) + "</div></article>";
    }).join("");
  }
  function renderDetail(selected) {
    if (!selected) {
      $("operationDetail").innerHTML = '<div class="detail-empty"><div><strong>운영자료를 입력해 주세요</strong>ADR과 OCC를 입력하면 운영분석 결과가 표시됩니다.</div></div>'
        + (building ? '<div class="analysis-report-common-actions operation-empty-actions" id="operationReportActions"></div>' : "");
      if (building) window.livingstayAnalysisReportActions(
        $("operationReportActions"), buildingId(), operationName(),
        building && (building.road_address || building.jibun_address)
      );
      return;
    }
    var lodging = selectedLodging();
    var name = operationName();
    var address = building && (building.road_address || building.jibun_address) || "주소 미확인";
    var rooms = selectedRooms();
    $("operationDetail").innerHTML = '<div class="detail-building-head"><div><h2 class="detail-name">'
      + escapeHtml(name) + '</h2><div class="detail-address">' + escapeHtml(address)
      + '</div></div><span class="detail-status">' + escapeHtml(building && building.lodging_type || "숙박시설")
      + '</span></div><div class="detail-tags"><span class="pill">신고 객실 '
      + (rooms == null ? "확인 불가" : format(rooms, 0) + "실")
      + '</span><span class="pill sample">2024 공공통계 비교</span></div>'
      + '<section class="detail-analysis"><small>선택 숙박시설 운영 진단</small><b>'
      + escapeHtml(grade(selected.adr, selected.occ)) + '</b></section><div class="detail-metrics">'
      + '<div class="detail-metric"><small>ADR</small><strong>' + format(selected.adr, 0) + '원</strong></div>'
      + '<div class="detail-metric"><small>OCC</small><strong>' + format(selected.occ, 1) + '%</strong></div>'
      + '<div class="detail-metric"><small>RevPAR</small><strong>' + format(selected.revpar, 0) + '원</strong></div>'
      + '<div class="detail-metric"><small>자료 처리</small><strong>자동분석</strong></div></div>'
      + '<div class="detail-disclaimer">영업신고 객실 수와 사용자가 올린 자기자료를 결합한 참고 분석이며 세무·회계 검증이나 감정평가를 대신하지 않습니다.</div>'
      + '<div class="analysis-report-common-actions" id="operationReportActions"></div>';
    window.livingstayAnalysisReportActions(
      $("operationReportActions"), buildingId(), name,
      building && (building.road_address || building.jibun_address)
    );
  }
  function monthRevenue(adr, occ, days, opex, fee) {
    if ([adr, occ, days, opex, fee].some(function (value) { return value == null; })) return null;
    return adr * occ / 100 * days * (1 - opex / 100) * (1 - fee / 100);
  }
  function calendarMonth(start, end) {
    var startMatch = String(start || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    var endMatch = String(end || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!startMatch || !endMatch) return null;
    var startYear = Number(startMatch[1]), startMonth = Number(startMatch[2]), startDay = Number(startMatch[3]);
    var endYear = Number(endMatch[1]), endMonth = Number(endMatch[2]), endDay = Number(endMatch[3]);
    var lastDay = new Date(Date.UTC(startYear, startMonth, 0)).getUTCDate();
    if (startMonth < 1 || startMonth > 12 || startDay !== 1
      || endYear !== startYear || endMonth !== startMonth || endDay !== lastDay) return null;
    return { year: startYear, month: startMonth, days: lastDay };
  }
  function setUploadedMonthBasis(result) {
    var start = result && result.period_start, end = result && result.period_end;
    var fullMonth = calendarMonth(start, end);
    var periodDays = number(result && result.occupancy_days);
    uploadedMonthPeriod = start || end ? {
      start: start || "", end: end || "", fullMonth: !!fullMonth,
      dayCountMismatch: !!(fullMonth && periodDays != null && periodDays !== fullMonth.days),
    } : null;
    uploadedMonthlyDayBasis = null;
    if (!fullMonth) return;
    uploadedMonthlyDayBasis = {
      days: fullMonth.days,
      source: "업로드된 전체 월 기간 " + String(start).slice(0, 7) + "의 달력 일수"
        + (periodDays === fullMonth.days ? " (occupancy_days 확인)" : " (기간 시작일·종료일 기준)"),
    };
    if (uploadedMonthPeriod.dayCountMismatch) uploadedMonthlyDayBasis = null;
  }
  function monthlyDayBasis() {
    if (uploadedMonthlyDayBasis) {
      return { days: uploadedMonthlyDayBasis.days, source: uploadedMonthlyDayBasis.source };
    }
    var config = settings();
    if (!config) return { days: null, source: "운영 분석 설정을 불러올 수 없습니다." };
    if (uploadedMonthPeriod) {
      return {
        days: config.MONTH_DAYS_FALLBACK,
        source: uploadedMonthPeriod.dayCountMismatch
          ? "업로드한 전체 월 날짜와 occupancy_days가 일치하지 않아 " + config.MONTH_DAYS_FALLBACK + "일 공통 기준을 적용합니다."
          : "업로드 기간 " + (uploadedMonthPeriod.start || "—") + "~"
            + (uploadedMonthPeriod.end || "—") + "은 전체 한 달이 아니어서 월 기준 일수로 사용하지 않았습니다. "
            + config.MONTH_DAYS_FALLBACK + "일 공통 기준을 적용합니다.",
      };
    }
    return {
      days: config.MONTH_DAYS_FALLBACK,
      source: "월 전체 기간 정의가 없어 " + config.MONTH_DAYS_FALLBACK + "일 공통 기준을 적용합니다.",
    };
  }
  function moneyMan(value) {
    return value == null || !Number.isFinite(value) ? "계산 불가"
      : (value / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "만원";
  }
  function renderCoreMetrics(state) {
    var host = $("operationCoreMetrics");
    if (!host) return;
    var rows = [
      ["RevPAR", state.revpar == null ? "계산 불가" : format(state.revpar, 0) + "원", "ADR × OCC"],
      ["호실 월 매출", state.monthlyRevenue == null ? "계산 불가" : moneyMan(state.monthlyRevenue),
        format(state.monthlyDays, 1) + "일 기준 · " + state.monthlyDaysSource],
      ["호실 월 순수익", state.monthlyNet == null ? "계산 불가" : moneyMan(state.monthlyNet),
        "경비 " + moneyMan(state.monthlyRevenue == null ? null : state.monthlyRevenue * state.opexRatio / 100)
          + " 차감 후 수수료 차감", "net"],
      ["월세 대비", state.monthlyNet == null || state.compareRent == null ? "비교 기준 필요"
        : ((state.monthlyNet / 10000 - state.compareRent >= 0 ? "+" : "")
          + (state.monthlyNet / 10000 - state.compareRent).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "만원"),
        state.monthlyNet == null || state.compareRent == null ? "비교 월세 입력 필요"
          : state.monthlyNet / 10000 >= state.compareRent ? "숙박위탁이 유리 · 클릭해 월세 분석" : "장기임대가 유리 · 클릭해 월세 분석",
        "rent"],
      ["연 수익률", state.annualYield == null ? "매입가 입력 필요" : state.annualYield.toFixed(2) + "%", "월 순수익 × 12 ÷ 호실 매입가"],
    ];
    host.innerHTML = rows.map(function (row, index) {
      var cls = row[3] === "net" ? " owner-net" : row[3] === "rent"
        ? (state.monthlyNet != null && state.compareRent != null && state.monthlyNet / 10000 >= state.compareRent ? " success" : " danger")
        : "";
      return '<article class="analysis-card operation-metric' + cls + '"'
        + (row[3] === "rent" ? ' data-operation-rent-link tabindex="0" role="link"' : "") + '><small>' + row[0]
        + '</small><strong>' + row[1] + '</strong><span>' + row[2] + '</span>'
        + (row[3] === "net" && state.monthlyRevenue != null
          ? '<em class="operation-cost-breakdown" title="매출 ' + moneyMan(state.monthlyRevenue) + ' − 운영경비 '
            + moneyMan(state.monthlyRevenue * state.opexRatio / 100) + ' = 매출이익 '
            + moneyMan(state.monthlyRevenue * (1 - state.opexRatio / 100)) + ' − 위탁수수료 '
            + moneyMan(state.monthlyRevenue * (1 - state.opexRatio / 100) * state.mgmtFeeRatio / 100)
            + ' = 순수익 ' + moneyMan(state.monthlyNet) + '">ⓘ 매출 → 경비 → 매출이익 → 수수료 → 순수익</em>' : "")
        + "</article>";
    }).join("");
    host.querySelectorAll("[data-operation-rent-link]").forEach(function (node) {
      var openRental = function () {
        crossRent();
        var tab = $("rentalTab");
        if (tab) tab.click();
      };
      node.addEventListener("click", openRental);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openRental(); }
      });
    });
  }
  function renderSensitivity(state) {
    var host = $("operationSensitivity");
    if (!host) return;
    if (state.adr == null || state.occ == null || state.opexRatio == null || state.mgmtFeeRatio == null) {
      host.innerHTML = "<p>ADR·OCC와 비용 기준이 필요합니다.</p>"; return;
    }
    var adrInterval = sliderUtils.niceStep((state.baseAdr || state.adr) * 0.07);
    var columns = [-3, -2, -1, 0, 1, 2, 3]
      .map(function (offset) { return state.adr + offset * adrInterval; })
      .filter(function (adr) { return adr > 0; });
    var rows = [-3, -2, -1, 0, 1, 2, 3]
      .map(function (offset) { return state.occ + offset * 5; })
      .filter(function (occ) { return occ >= 0 && occ <= 100; });
    var cellNet = function (adr, occ) {
      return monthRevenue(adr, occ, state.monthlyDays, state.opexRatio, state.mgmtFeeRatio);
    };
    var currentNet = state.monthlyNet;
    host.innerHTML = '<h3>ADR × OCC 민감도 — 호실 월 순수익 (만원, 운영경비율 '
      + state.opexRatio + '% · 위탁수수료율 ' + state.mgmtFeeRatio + '% 반영)</h3>'
      + '<div class="operation-sensitivity-scroll"><table><thead><tr><th>OCC \\ ADR</th>'
      + columns.map(function (adr) { return "<th>" + format(adr / 1000, 0) + "천</th>"; }).join("")
      + "</tr></thead><tbody>" + rows.map(function (occ) {
        return "<tr><th>" + format(occ, 1) + "%</th>" + columns.map(function (adr) {
          var net = cellNet(adr, occ), rent = state.compareRent;
          var cls = rent == null ? "unavailable" : net / 10000 >= rent ? "above"
            : net / 10000 >= rent * 0.8 ? "middle" : "below";
          var selected = Math.abs(adr - state.adr) < 0.01 && Math.abs(occ - state.occ) < 0.01;
          if (selected) cls += " selected";
          return '<td class="' + cls + '"' + (selected ? ' aria-current="true"' : "")
            + '>' + (net == null ? "—" : moneyMan(net).replace(/만원$/, "")) + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>"
      + '<div class="operation-sensitivity-legend"><span>월세 이상 · 월세보다 유리</span>'
      + '<span>월세의 80~100%</span><span>월세의 80% 미만</span>'
      + (state.compareRent == null ? "<span>비교 월세 입력 시 색상 표시</span>" : "") + "</div>";
    host.dataset.currentMonthlyNet = currentNet == null ? "" : String(currentNet);
  }
  function renderVerdict(state) {
    var host = $("operationVerdict");
    if (!host) return;
    var assumedPerformance = assumed.adr || assumed.occ;
    var verdict = assumedPerformance
      ? "지역 평균 가정 — 실제 실적을 입력하면 정확한 판정이 나옵니다"
      : grade(state.adr, state.occ);
    var breakEven = state.breakEvenOcc;
    host.innerHTML = "<strong>" + escapeHtml(verdict) + "</strong><span>"
      + (state.compareRent == null ? "비교 월세를 입력하면 손익 교차 OCC를 계산합니다."
        : breakEven == null ? "ADR·비용 기준이 없어 손익 교차 OCC를 계산할 수 없습니다."
          : breakEven > 100 ? "현재 요금으로는 가동률 100%여도 월세에 못 미칩니다."
            : "현재 ADR·비용 조건에서 월세 " + format(state.compareRent, 0)
              + "만원과 같아지는 OCC는 " + format(breakEven, 1) + "%")
      + (assumed.opexRatio || assumed.mgmtFeeRatio ? " (비용 가정값 기준)" : "") + "</span>";
  }
  function renderBuildingTotals(state) {
    var host = $("operationBuildingTotals");
    if (!host) return;
    if (state.roomCount == null || state.monthlyRevenue == null) {
      host.innerHTML = "<p>적용 객실 수와 운영 기준을 확인해야 건물 전체를 환산할 수 있습니다.</p>"; return;
    }
    var roomCount = state.roomCount, revenue = state.monthlyRevenue * roomCount;
    var opex = revenue * state.opexRatio / 100;
    var profit = revenue - opex;
    var fee = profit * state.mgmtFeeRatio / 100;
    host.innerHTML = '<div class="operation-total-grid">'
      + [["적용 객실", format(roomCount, 0) + "실"], ["건물 월 매출", moneyMan(revenue)],
        ["운영경비", moneyMan(opex)], ["위탁수수료", moneyMan(fee)], ["건물 월 순수익", moneyMan(profit - fee)]]
        .map(function (row) { return "<article><small>" + row[0] + "</small><strong>" + row[1] + "</strong></article>"; }).join("")
      + "</div>";
  }
  function publishOperationState() {
    var adr = value("adr"), occ = value("occ"), base = regionalBaseline();
    var opex = value("opexRatio"), fee = value("mgmtFeeRatio"), buy = value("purchasePrice");
    var rent = value("compareRent"), dayBasis = monthlyDayBasis(), days = dayBasis.days;
    var revpar = adr != null && occ != null ? adr * occ / 100 : null;
    var revenue = adr != null && occ != null ? adr * occ / 100 * days : null;
    var net = monthRevenue(adr, occ, days, opex, fee);
    var breakEven = adr != null && opex != null && fee != null && adr > 0 && rent != null
      ? rent * 10000 / (adr * days * (1 - opex / 100) * (1 - fee / 100)) * 100 : null;
    var state = {
      selectedName: operationName(), roomCount: selectedRooms(), adr: adr, occ: occ,
      baseAdr: base.adr, baseOcc: base.occ, benchmarkCount: benchmarks.length,
      opexRatio: opex, mgmtFeeRatio: fee, purchasePrice: buy, compareRent: rent,
      compareRentAssumed: assumed.compareRent,
      compareRentSource: compareRentSource ? compareRentSource.text : "",
      monthlyDays: days, revpar: revpar, monthlyRevenue: revenue,
      monthlyDaysSource: dayBasis.source,
      monthlyProfit: revenue == null || opex == null ? null : revenue * (1 - opex / 100),
      monthlyNet: net, breakEvenOcc: breakEven,
      annualYield: buy != null && buy > 0 && net != null ? net * 12 / (buy * 10000) * 100 : null,
      assumed: Object.assign({}, assumed),
      ready: adr != null && occ != null && opex != null && fee != null,
    };
    window.__operationAnalysisState = state;
    renderCoreMetrics(state);
    renderSensitivity(state);
    renderVerdict(state);
    renderBuildingTotals(state);
    return state;
  }
  function renderOperationChart() {
    if (!$("operationChart") || typeof Chart === "undefined") return;
    if (!settings()) {
      var missingSettingsChart = Chart.getChart($("operationChart"));
      if (missingSettingsChart) missingSettingsChart.destroy();
      var errorCanvas = $("operationChart"), errorWrap = errorCanvas.parentElement;
      var errorMessage = $("operationChartEmpty");
      if (!errorMessage && errorWrap) {
        errorMessage = document.createElement("p");
        errorMessage.id = "operationChartEmpty";
        errorMessage.className = "operation-chart-empty";
        errorWrap.appendChild(errorMessage);
      }
      errorCanvas.classList.add("hidden");
      if (errorMessage) {
        errorMessage.textContent = "운영 분석 설정 모듈을 불러오지 못했습니다. 페이지를 새로고침하거나 관리자에게 문의해 주세요.";
        errorMessage.classList.remove("hidden");
      }
      window.__operationAnalysisState = { ready: false, error: "operation-settings.js missing" };
      window.__operationChartLayout = { ready: false };
      return;
    }
    var state = publishOperationState();
    renderTop();
    renderEvidence(state.baseAdr, state.baseOcc);
    var selected = state.adr != null && state.occ != null
      ? { region: state.selectedName, adr: state.adr, occ: state.occ, revpar: state.revpar, selected: true } : null;
    renderDetail(selected);
    bindOperationShare();
    var canvas = $("operationChart"), existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    var wrapper = canvas.parentElement;
    var empty = $("operationChartEmpty");
    if (!empty && wrapper) {
      empty = document.createElement("p"); empty.id = "operationChartEmpty";
      empty.className = "operation-chart-empty"; wrapper.appendChild(empty);
    }
    var baseAdr = state.baseAdr, baseOcc = state.baseOcc;
    var comparisons = benchmarks.map(function (item) {
      var x = number(item.adr), y = number(item.occ);
      return x != null && y != null && x > 0 && y >= 0 && y <= 100
        ? { x: x, y: y, item: item, label: item.region, revpar: number(item.revpar) } : null;
    }).filter(Boolean);
    if (baseAdr == null || baseOcc == null || baseAdr <= 0 || baseOcc < 0 || baseOcc > 100) {
      canvas.classList.add("hidden");
      if (empty) {
        empty.textContent = benchmarkLoadError
          || "확인된 2024년 지역 호텔 비교자료가 없어 기준선·비교점을 표시할 수 없습니다. 임의값은 사용하지 않습니다.";
        empty.classList.remove("hidden");
      }
      window.__operationChartLayout = { ready: false, comparisonPoints: comparisons.length };
      return;
    }
    if (empty) empty.classList.add("hidden");
    canvas.classList.remove("hidden");
    var lowerOcc = Math.max(0, baseOcc - (100 - baseOcc));
    var transformOcc = function (occ) {
      occ = Number(occ);
      if (occ <= baseOcc) {
        return baseOcc === lowerOcc ? 50 : (occ - lowerOcc) / (baseOcc - lowerOcc) * 50;
      }
      return baseOcc >= 100 ? 50 : 50 + (occ - baseOcc) / (100 - baseOcc) * 50;
    };
    var inverseOcc = function (position) {
      if (position <= 50) return lowerOcc + (baseOcc - lowerOcc) * position / 50;
      return baseOcc + (100 - baseOcc) * (position - 50) / 50;
    };
    var baselineOcc = Math.max(0, Math.min(100, baseOcc));
    var xDeviation = Math.max.apply(null, comparisons.map(function (point) {
      return Math.abs(point.x - baseAdr);
    }).concat([100000]));
    var xMin = baseAdr - xDeviation * 1.1;
    var xMax = baseAdr + xDeviation * 1.1;
    var topItems = comparisons.slice().sort(function (a, b) {
      return (b.revpar || b.x * b.y / 100) - (a.revpar || a.x * a.y / 100);
    }).slice(0, 5);
    var topNames = new Set(topItems.map(function (item) { return String(item.item.region); }));
    var datasets = [{
      key: "comparison", label: "시군구 호텔 평균",
      data: comparisons.map(function (point) {
        return { x: point.x, y: transformOcc(point.y), item: point.item, actualOcc: point.y,
          topLabel: topNames.has(String(point.item.region)) };
      }),
      pointRadius: function (context) { return context.raw.topLabel ? 7 : 6; },
      pointHoverRadius: 8, pointStyle: "circle", pointBackgroundColor: "#7F77DD",
      pointBorderColor: "#fff", pointBorderWidth: 1.5, order: 1,
    }, {
      key: "baseline", label: "지역 평균",
      data: [{ x: baseAdr, y: 50, item: { region: subregion || region + " 시도 평균", adr: baseAdr, occ: baselineOcc } }],
      pointRadius: 9, pointHoverRadius: 11, pointStyle: "rectRot",
      pointBackgroundColor: "#2a78d6", pointBorderColor: "#fff", pointBorderWidth: 2, order: 0,
    }];
    var selectedData = null;
    if (selected) {
      var offscale = selected.adr < xMin || selected.adr > xMax;
      selectedData = {
        x: Math.max(xMin + 1, Math.min(xMax - 1, selected.adr)), y: transformOcc(selected.occ),
        item: selected, actualAdr: selected.adr, actualOcc: selected.occ, offscale: offscale,
        direction: selected.adr > xMax ? "right" : "left",
      };
      datasets.push({
        key: "selected", label: "내 호실", data: [selectedData],
        pointRadius: 13, pointHoverRadius: 15, pointStyle: offscale ? "triangle" : "circle",
        pointRotation: offscale && selectedData.direction === "right" ? 90 : offscale ? -90 : 0,
        pointBackgroundColor: "#eb6834", pointBorderColor: "#fff", pointBorderWidth: 3, order: -10,
      });
    }
    var revparLines = [
      { label: "평균 매출선", color: "#88949b", value: baseAdr * baselineOcc / 100 },
      { label: "내 매출선", color: "#eb6834", value: state.revpar },
    ].filter(function (line) { return Number.isFinite(line.value) && line.value > 0; });
    revparLines.forEach(function (line, index) {
      var points = [];
      for (var occ = 2; occ <= 100; occ += 1) {
        var adr = line.value * 100 / occ;
        if (adr >= xMin && adr <= xMax) points.push({ x: adr, y: transformOcc(occ) });
      }
      datasets.push({
        key: index === 0 ? "averageRevpar" : "selectedRevpar", label: line.label,
        data: points, showLine: true, borderColor: line.color, borderWidth: 1.5,
        borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 0, order: 5 + index,
      });
    });
    var chartPlugin = {
      id: "operationAnalysisOverlays",
      beforeDatasetsDraw: function (chart) {
        var ctx = chart.ctx, area = chart.chartArea, centerX = chart.scales.x.getPixelForValue(baseAdr);
        var centerY = chart.scales.y.getPixelForValue(50);
        var quadrants = wrapper.querySelectorAll(".operation-quadrant");
        var boxes = [[area.left, area.top, centerX - area.left, centerY - area.top],
          [centerX, area.top, area.right - centerX, centerY - area.top],
          [area.left, centerY, centerX - area.left, area.bottom - centerY],
          [centerX, centerY, area.right - centerX, area.bottom - centerY]];
        quadrants.forEach(function (quadrant, index) {
          var box = boxes[index];
          quadrant.style.left = box[0] + "px"; quadrant.style.top = box[1] + "px";
          quadrant.style.right = "auto"; quadrant.style.bottom = "auto";
          quadrant.style.width = box[2] + "px"; quadrant.style.height = box[3] + "px";
        });
        ctx.save();
        ctx.strokeStyle = "#526a7d"; ctx.lineWidth = 1.3; ctx.setLineDash([5, 5]);
        ctx.beginPath(); ctx.moveTo(centerX, area.top); ctx.lineTo(centerX, area.bottom);
        ctx.moveTo(area.left, centerY); ctx.lineTo(area.right, centerY); ctx.stroke();
        ctx.setLineDash([]); ctx.font = "700 10px 'Noto Sans KR', sans-serif";
        ctx.fillStyle = "#526a7d"; ctx.fillText("지역 평균 ADR " + format(baseAdr, 0) + "원", centerX + 6, area.bottom - 7);
        ctx.restore();
      },
      afterDatasetsDraw: function (chart) {
        var ctx = chart.ctx, used = [], selectedElement = selectedData
          ? chart.getDatasetMeta(datasets.findIndex(function (set) { return set.key === "selected"; })).data[0] : null;
        var pulse = $("operationSelectedPulse");
        if (pulse) {
          pulse.style.display = selectedElement ? "block" : "none";
          if (selectedElement) {
            pulse.style.left = selectedElement.x + "px";
            pulse.style.top = selectedElement.y + "px";
            pulse.style.setProperty("--pulse-color", "#eb6834");
          }
        }
        var overlaps = function (a, b) {
          return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
        };
        if (selectedElement) used.push({ x: selectedElement.x - 34, y: selectedElement.y - 28, w: 70, h: 25 });
        var comparisonSet = datasets.find(function (set) { return set.key === "comparison"; });
        comparisonSet.data.forEach(function (point, index) {
          if (!point.topLabel) return;
          var element = chart.getDatasetMeta(datasets.indexOf(comparisonSet)).data[index];
          var text = String(point.item.region || "지역").slice(0, 8);
          ctx.font = "700 9px 'Noto Sans KR', sans-serif";
          var box = { x: element.x + 8, y: element.y - 15, w: ctx.measureText(text).width + 9, h: 18 };
          var area = chart.chartArea;
          box.x = Math.max(area.left + 2, Math.min(area.right - box.w - 2, box.x));
          box.y = Math.max(area.top + 2, Math.min(area.bottom - box.h - 2, box.y));
          if (used.some(function (prior) { return overlaps(box, prior); })) return;
          used.push(box); ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillRect(box.x, box.y, box.w, box.h);
          ctx.fillStyle = "#5149a0"; ctx.fillText(text, box.x + 4, box.y + 12);
        });
        if (selectedElement && selectedData) {
          var text = selectedData.offscale
            ? (selectedData.direction === "right" ? "▶ " : "◀ ") + format(selectedData.actualAdr, 0) + "원"
            : "내 호실";
          ctx.font = "800 12px 'Noto Sans KR', sans-serif";
          var width = ctx.measureText(text).width + 14, area = chart.chartArea;
          var x = Math.max(area.left + 2, Math.min(area.right - width - 2, selectedElement.x - width / 2));
          var y = Math.max(area.top + 2, Math.min(area.bottom - 23, selectedElement.y - 31));
          ctx.save(); ctx.fillStyle = "#fff4ec"; ctx.strokeStyle = "#eb6834"; ctx.lineWidth = 1.5;
          ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, width, 22, 6); else ctx.rect(x, y, width, 22);
          ctx.fill(); ctx.stroke(); ctx.fillStyle = "#873714"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(text, x + width / 2, y + 11); ctx.restore();
          selectedElement.draw(ctx, area);
        }
        revparLines.forEach(function (line) {
          var label = line.label + " " + format(line.value, 0) + "원/실";
          ctx.save(); ctx.font = "700 9px 'Noto Sans KR', sans-serif";
          var textWidth = ctx.measureText(label).width;
          ctx.fillStyle = line.color; ctx.textAlign = "right";
          ctx.fillText(label, chart.chartArea.right - 4, chart.chartArea.top + 12 + revparLines.indexOf(line) * 13);
          ctx.restore();
        });
        window.__operationChartLayout = {
          ready: true,
          comparisonPoints: comparisons.length,
          comparisonColor: "#7F77DD",
          baselineAdr: baseAdr,
          baselineOcc: baselineOcc,
          baselineRegion: subregion,
          baselinePixelX: chart.scales.x.getPixelForValue(baseAdr),
          baselinePixelY: chart.scales.y.getPixelForValue(50),
          chartCenterX: (chart.chartArea.left + chart.chartArea.right) / 2,
          chartCenterY: (chart.chartArea.top + chart.chartArea.bottom) / 2,
          selectedRadius: selectedElement ? 13 : 0,
          pulseVisible: !!selectedElement,
          isoRevparLines: revparLines.length,
          quadrantBoxes: Array.from(wrapper.querySelectorAll(".operation-quadrant")).map(function (quadrant) {
            return {
              left: parseFloat(quadrant.style.left),
              top: parseFloat(quadrant.style.top),
              width: parseFloat(quadrant.style.width),
              height: parseFloat(quadrant.style.height),
            };
          }),
        };
      },
    };
    new Chart(canvas, {
      type: "scatter", data: { datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, parsing: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (context) {
          var raw = context.raw, item = raw.item || {};
          return " " + (item.region || "내 호실") + " · ADR " + format(raw.actualAdr || item.adr || raw.x, 0)
            + "원 · OCC " + format(raw.actualOcc || item.occ, 1) + "% · RevPAR "
            + format(item.revpar || raw.actualAdr * raw.actualOcc / 100 || raw.x * raw.y / 100, 0) + "원";
        } } } },
        scales: {
          x: { min: xMin, max: xMax, title: { display: true, text: "판매객실 평균요금 ADR (천원)" },
            ticks: { callback: function (tick) {
              var axisValue = Number(tick);
              return axisValue < 0 ? "" : format(axisValue / 1000, 0) + "천";
            } } },
          y: { min: 0, max: 100, title: { display: true, text: "객실 이용률 OCC (%)" },
            ticks: { callback: function (tick) { return format(inverseOcc(Number(tick)), 0) + "%"; } } },
        },
      },
      plugins: [chartPlugin],
    });
    window.__operationChartLayout = window.__operationChartLayout || {};
  }
  function renderChart() {
    renderOperationChart();
    return;
    var occ = number($("operationOcc").value);
    var adr = number($("operationAdr").value);
    var selected = occ != null && adr != null ? {
      region: operationName(),
      adr: adr, occ: occ, revpar: Math.round(adr * occ / 100), selected: true,
    } : null;
    var baseline = regionalBaseline();
    var baseAdr = baseline.adr;
    var baseOcc = baseline.occ;
    renderTop();
    renderEvidence(baseAdr, baseOcc);
    renderDetail(selected);
    window.__operationAnalysisState = {
      selectedName: selected && selected.region || null,
      roomCount: selectedRooms(),
      occ: occ,
      adr: adr,
      baseAdr: baseAdr,
      baseOcc: baseOcc,
      benchmarkCount: benchmarks.length,
    };
    var canvas = $("operationChart");
    var existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    var points = benchmarks.concat(selected ? [selected] : []);
    if (!points.length) return;
    var xDeviation = Math.max.apply(null, points.map(function (item) {
      return Math.abs(number(item.adr) - baseAdr);
    }).concat([Math.max(baseAdr * 0.25, 20000)]));
    var yDeviation = Math.max.apply(null, points.map(function (item) {
      return Math.abs(number(item.occ) - baseOcc);
    }).concat([15]));
    var pulse = $("operationSelectedPulse");
    pulse.style.display = "none";
    new Chart(canvas, {
      type: "scatter",
      data: { datasets: [{
        data: points.map(function (item) { return { x: item.adr, y: item.occ, item: item }; }),
        pointRadius: function (context) { return context.raw.item.selected ? 11 : 7; },
        pointHoverRadius: function (context) { return context.raw.item.selected ? 13 : 9; },
        pointBackgroundColor: function (context) { return context.raw.item.selected ? "#102a43" : "#8798a8"; },
        pointBorderColor: "#fff",
        pointBorderWidth: function (context) { return context.raw.item.selected ? 3 : 1.5; },
      }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (context) {
          var item = context.raw.item;
          return " " + item.region + " · ADR " + format(item.adr, 0) + "원 · OCC "
            + format(item.occ, 1) + "% · RevPAR " + format(item.revpar, 0) + "원";
        } } } },
        scales: {
          x: { min: baseAdr - xDeviation * 1.08, max: baseAdr + xDeviation * 1.08,
            title: { display: true, text: "판매객실 평균요금 ADR (원)" } },
          y: { min: baseOcc - yDeviation * 1.08, max: baseOcc + yDeviation * 1.08,
            title: { display: true, text: "객실 이용률 OCC (%)" } },
        },
      },
      plugins: [{
        id: "regionalAverageBaselines",
        beforeDatasetsDraw: function (chart) {
          if (baseAdr == null || baseOcc == null) return;
          var context = chart.ctx;
          var x = chart.scales.x.getPixelForValue(baseAdr);
          var y = chart.scales.y.getPixelForValue(baseOcc);
          var area = chart.chartArea;
          var quadrants = chart.canvas.parentElement.querySelectorAll(".operation-quadrant");
          var boxes = [
            [area.left, area.top, x - area.left, y - area.top],
            [x, area.top, area.right - x, y - area.top],
            [area.left, y, x - area.left, area.bottom - y],
            [x, y, area.right - x, area.bottom - y],
          ];
          quadrants.forEach(function (quadrant, index) {
            var box = boxes[index];
            quadrant.style.left = box[0] + "px";
            quadrant.style.top = box[1] + "px";
            quadrant.style.right = "auto";
            quadrant.style.bottom = "auto";
            quadrant.style.width = box[2] + "px";
            quadrant.style.height = box[3] + "px";
          });
          context.save();
          context.strokeStyle = "#526a7d";
          context.fillStyle = "#526a7d";
          context.font = "700 10px 'Noto Sans KR'";
          context.setLineDash([5, 5]);
          context.beginPath();
          context.moveTo(x, chart.chartArea.top);
          context.lineTo(x, chart.chartArea.bottom);
          context.moveTo(chart.chartArea.left, y);
          context.lineTo(chart.chartArea.right, y);
          context.stroke();
          context.setLineDash([]);
          context.fillText("지역 평균 ADR " + format(baseAdr, 0) + "원", x + 6, chart.chartArea.bottom - 8);
          context.fillText("지역 평균 OCC " + format(baseOcc, 1) + "%", chart.chartArea.left + 6, y - 7);
          context.restore();
        },
        afterDatasetsDraw: function (chart) {
          var selectedIndex = points.findIndex(function (item) { return item.selected; });
          var element = selectedIndex >= 0 && chart.getDatasetMeta(0).data[selectedIndex];
          if (!element) {
            pulse.style.display = "none";
            return;
          }
          pulse.style.display = "block";
          pulse.style.left = element.x + "px";
          pulse.style.top = element.y + "px";
          pulse.style.setProperty("--pulse-color", "#102a43");
          window.__operationChartLayout = {
            selectedRadius: 11,
            comparisonPoints: benchmarks.length,
            comparisonColor: "#8798a8",
            pulseVisible: true,
            baselineAdr: baseAdr,
            baselineOcc: baseOcc,
            baselineRegion: subregion,
            baselinePixelX: chart.scales.x.getPixelForValue(baseAdr),
            baselinePixelY: chart.scales.y.getPixelForValue(baseOcc),
            chartCenterX: (chart.chartArea.left + chart.chartArea.right) / 2,
            chartCenterY: (chart.chartArea.top + chart.chartArea.bottom) / 2,
            quadrantBoxes: Array.from(
              chart.canvas.parentElement.querySelectorAll(".operation-quadrant")
            ).map(function (quadrant) {
              return {
                left: parseFloat(quadrant.style.left),
                top: parseFloat(quadrant.style.top),
                width: parseFloat(quadrant.style.width),
                height: parseFloat(quadrant.style.height),
              };
            }),
          };
        },
      }],
    });
  }
  function setupOperationSliders() {
    ensureOperationInputs();
    var host = $("operationSliders");
    if (!host || host.dataset.bound === "true") return;
    host.dataset.bound = "true";
    host.addEventListener("input", function (event) {
      var range = event.target.closest("[data-operation-slider]");
      if (!range) return;
      var field = range.dataset.operationSlider;
      activeSliderField = field;
      setInput(field, range.value);
      assumed[field] = false;
      if (field === "compareRent") { compareRentSource = null; roneRentStatus = ""; }
      updateSliderLabel(field);
      scheduleRender();
    });
    host.addEventListener("change", function (event) {
      var range = event.target.closest("[data-operation-slider]");
      if (!range) return;
      scheduleSliderCommit(range.dataset.operationSlider);
    });
    host.addEventListener("click", function (event) {
      var button = event.target.closest("[data-operation-value]");
      if (!button || button.querySelector("input")) return;
      var field = button.dataset.operationValue, input = document.createElement("input");
      input.type = "number"; input.step = "any";
      input.min = field === "adr" ? "1" : field === "occ" ? "0"
        : field === "opexRatio" ? "10" : field === "mgmtFeeRatio" ? "0"
          : field === "purchasePrice" ? "100" : field === "compareRent" ? "5" : "0";
      input.max = field === "occ" ? "100" : field === "opexRatio" ? "60"
        : field === "mgmtFeeRatio" ? "50" : field === "purchasePrice" ? "1000000"
          : field === "compareRent" ? "1000" : "1000000";
      input.value = value(field) == null ? "" : String(value(field));
      input.setAttribute("aria-label", labels[field][1] + " 직접 입력");
      button.textContent = ""; button.appendChild(input); input.focus(); input.select();
      var cancelled = false;
      var commit = function () {
        if (!button.contains(input)) return;
        if (cancelled) {
          button.textContent = displayValue(field);
          updateSliderLabel(field);
          return;
        }
        var raw = input.value.trim(), parsed = raw === "" ? null : Number(raw);
        if (parsed != null && Number.isFinite(parsed)) {
          var limits = {
            adr: [1, 1000000], occ: [0, 100],
            opexRatio: [10, 60], mgmtFeeRatio: [0, 50],
            purchasePrice: [100, 1000000],
            compareRent: [5, 1000],
          }[field];
          setInput(field, Math.max(limits[0], Math.min(limits[1], parsed)));
          if (field === "purchasePrice" && purchasePriceBase == null) purchasePriceBase = parsed;
          assumed[field] = false;
          if (field === "compareRent") { compareRentSource = null; roneRentStatus = ""; }
          syncSliderPositions();
          updateSliderLabel(field);
          scheduleSliderCommit(field);
        } else {
          syncSliderPositions();
        }
        button.textContent = displayValue(field);
        updateSliderLabel(field);
        scheduleRender();
      };
      input.addEventListener("blur", commit, { once: true });
      input.addEventListener("keydown", function (keyEvent) {
        if (keyEvent.key === "Enter") { keyEvent.preventDefault(); input.blur(); }
        if (keyEvent.key === "Escape") {
          cancelled = true;
          input.value = value(field) == null ? "" : String(value(field));
          input.blur();
        }
      });
    });
  }
  function restoreRentalScenario() {
    if (window.__analysisShareToken || !rentalScenarioMatchesBuilding()) return;
    var purchase = sharedPurchaseValue(), rent = sharedRentValue(), changedFields = [];
    var generatedRent = window.__operationRentalRentGenerated;
    var isGeneratedRent = !!(rent && compareRentSource && assumed.compareRent && generatedRent
      && String(generatedRent.buildingId) === buildingId() && generatedRent.value === rent.value);
    if (purchase && value("purchasePrice") !== purchase.value) {
      setInput("purchasePrice", purchase.value); setAssumption("purchasePrice", purchase.assumed);
      purchasePriceBase = purchase.value;
      changedFields.push("purchasePrice");
    }
    if (rent && !isGeneratedRent
      && (value("compareRent") !== rent.value || rentalRentUserChanged)) {
      setInput("compareRent", rent.value); setAssumption("compareRent", false);
      compareRentSource = null; roneRentStatus = "";
      changedFields.push("compareRent");
    } else if (!rent && rentalRentUserChanged && value("compareRent") != null) {
      setInput("compareRent", "");
      setAssumption("compareRent", true);
      if (!compareRentSource) roneRentStatus = "";
      changedFields.push("compareRent");
    }
    rentalRentUserChanged = false;
    if (changedFields.length) {
      syncOperationSliders();
      updateOperationUrl(changedFields);
      ensureRoneCompareRent(loadSequence);
    }
  }
  function bindAnalysisTabs() {
    var tabs = $("analysisTabs");
    if (!tabs || tabs.dataset.operationTabsBound) return;
    tabs.dataset.operationTabsBound = "true";
    tabs.addEventListener("click", function (event) {
      var button = event.target.closest("[data-analysis-mode]");
      if (!button) return;
      var targetMode = button.dataset.analysisMode;
      if (targetMode === "rental") {
        // Run before the rental tab calculation so both rental inputs recalculate immediately.
        crossRent();
        return;
      }
      if (targetMode !== "operation" || window.__analysisShareToken) return;
      var active = tabs.querySelector('[aria-selected="true"]');
      if (!active || active.dataset.analysisMode !== "rental") return;
      var rentalFields = {
        r_unit_area: "rentalUnitArea", r_purchase: "rentalPurchasePrice", r_deposit: "rentalDeposit",
        r_rent: "rentalMonthlyRent", r_vacancy: "rentalVacancyMonths", r_loan: "rentalLoanAmount",
        r_rate: "rentalLoanRate", r_years: "rentalLoanYears", r_method: "rentalLoanMethod",
        r_management: "rentalManagementCost", r_other: "rentalOtherCost",
      };
      var preserved = {};
      if (rentalScenarioMatchesBuilding()) {
        Object.keys(rentalFields).forEach(function (key) {
          var input = $(rentalFields[key]);
          if (input && String(input.value).trim() !== "") preserved[key] = String(input.value).trim();
        });
        var modeButton = document.querySelector("#rentalPositioning [data-mode].active")
          || document.querySelector("#rentalPositioning [data-mode][aria-pressed='true']");
        if (modeButton && modeButton.dataset.mode) preserved.r_yieldmode = modeButton.dataset.mode;
      }
      restoreRentalScenario();
      window.setTimeout(function () {
        var params = new URLSearchParams(location.search);
        Object.keys(preserved).forEach(function (key) { params.set(key, preserved[key]); });
        params.set("mode", "operation");
        if (buildingId()) params.set("building_id", buildingId());
        history.replaceState({}, "", "/analysis?" + params.toString());
      }, 0);
    }, true);
  }
  function bindRentalRentInput() {
    var rentInput = $("rentalMonthlyRent");
    if (!rentInput || rentInput.dataset.operationRentBound) return;
    rentInput.dataset.operationRentBound = "true";
    ["input", "change"].forEach(function (type) {
      rentInput.addEventListener(type, function (event) {
        if (crossRentSync || !event.isTrusted) return;
        rentalRentUserChanged = true;
        window.__operationRentalRentGenerated = null;
        assumed.compareRent = false;
        compareRentSource = null;
        roneRentStatus = "";
      });
    });
  }
  function load() {
    setModeClass();
    var id = buildingId();
    if (id !== activeBuildingId) {
      resetOperationScenarioForBuildingChange(id);
      activeBuildingId = id;
    }
    var sequence = ++loadSequence;
    if (!id) {
      building = null; benchmarks = []; region = ""; subregion = "";
      benchmarkLoadError = "";
      window.__operationBenchmarkSource = "";
      window.__operationAnalysisBuilding = null;
      if (window.livingstayRenderAnalysisBuildingIdentity) window.livingstayRenderAnalysisBuildingIdentity($("operationBuildingIdentity"), null);
      $("operationLodging").innerHTML = '<option value="">건물을 먼저 선택해 주세요</option>';
      $("operationBusinessName").value = "";
      $("operationRoomCountInput").value = "";
      renderRoomCount();
      setupOperationSliders();
      seedScenario();
      renderChart();
      return;
    }
    Promise.all([
      fetch("/api/building/" + encodeURIComponent(id), { credentials: "same-origin" }).then(function (response) {
        return response.ok ? response.json() : response.json().catch(function () { return {}; }).then(function (payload) {
          return { loadError: payload.message || "선택 건물 정보를 불러오지 못했습니다." };
        });
      }),
      fetch("/api/analysis/operation-benchmarks?building_id=" + encodeURIComponent(id)
        + (window.__analysisShareToken ? "&share=" + encodeURIComponent(window.__analysisShareToken) : ""),
        { credentials: "same-origin" }).then(function (response) {
          return response.ok ? response.json() : response.json().catch(function () { return {}; }).then(function (payload) {
            return { loadError: payload.message || "지역 호텔 비교자료를 불러오지 못했습니다." };
          });
        }),
    ]).then(function (results) {
      if (sequence !== loadSequence) return;
      if (!results[0] || results[0].loadError) {
        benchmarkLoadError = results[0] && results[0].loadError || "선택 건물 정보를 불러오지 못했습니다.";
        building = null; benchmarks = []; region = ""; subregion = "";
        window.__operationAnalysisBuilding = null; window.__operationBenchmarkSource = "";
        renderChart();
        return;
      }
      building = results[0];
      building.building_id = building.building_id || building.id || Number(id);
      window.__operationAnalysisBuilding = building;
      benchmarks = results[1] && Array.isArray(results[1].items) ? results[1].items : [];
      window.__operationBenchmarkSource = results[1] && results[1].source
        ? [results[1].source.name, results[1].source.reference_year].filter(Boolean).join(" · ") : "";
      benchmarkLoadError = results[1] && results[1].loadError || "";
      region = results[1] && results[1].sido || "";
      subregion = results[1] && results[1].sgg || "";
      $("operationBusinessName").value = building.display_building_name || building.building_name || "";
      if (window.livingstayRenderAnalysisBuildingIdentity) window.livingstayRenderAnalysisBuildingIdentity($("operationBuildingIdentity"), building);
      setBuildingStatus(building.display_building_name || building.building_name || "선택 건물", true);
      renderLodgingOptions();
      setupOperationSliders();
      seedScenario();
      renderChart();
    }).catch(function () {
      if (sequence !== loadSequence) return;
      benchmarkLoadError = "운영분석 자료를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
      building = null; benchmarks = []; region = ""; subregion = "";
      window.__operationAnalysisBuilding = null; window.__operationBenchmarkSource = "";
      renderChart();
    });
  }

  async function analyzeFiles(files) {
    if (!files.length) return;
    var status = $("operationFileStatus");
    var input = $("operationFiles");
    if (files.length > 5) {
      status.textContent = "한 번에 5개 파일까지 선택해 주세요";
      input.value = "";
      return;
    }
    var requestSequence = ++uploadSequence;
    var requestBuildingId = buildingId();
    status.textContent = files.length + "개 파일 자동 분석 중…";
    input.disabled = true;
    try {
      var form = new FormData();
      Array.from(files).forEach(function (file) { form.append("files", file); });
      var response = await fetch("/api/analysis/operation-upload", {
        method: "POST", body: form, credentials: "same-origin",
      });
      var payload = await response.json().catch(function () { return {}; });
      if (requestSequence !== uploadSequence || requestBuildingId !== buildingId()) return;
      if (!response.ok) throw Error(payload.message || "자료를 분석하지 못했습니다.");
      var result = payload.result || {};
      var appliedOcc = number(result.occ);
      uploadedOccupancyBasis = null;
      setUploadedMonthBasis(result);
      if (appliedOcc != null) {
        $("operationOcc").value = appliedOcc;
        setAssumption("occ", false);
      } else if (number(result.sold_rooms) != null) {
        uploadedOccupancyBasis = {
          soldRooms: result.sold_rooms,
          days: result.occupancy_days,
        };
        appliedOcc = applyDerivedOcc();
      }
      if (appliedOcc != null) setAssumption("occ", false);
      if (result.adr != null) { $("operationAdr").value = Math.round(result.adr); setAssumption("adr", false); }
      var uploadedOpex = result.opex_ratio, uploadedFee = result.mgmt_fee_ratio;
      if (typeof uploadedOpex === "number" && Number.isFinite(uploadedOpex) && uploadedOpex >= 10 && uploadedOpex <= 60) {
        setInput("opexRatio", uploadedOpex); setAssumption("opexRatio", false);
      }
      if (typeof uploadedFee === "number" && Number.isFinite(uploadedFee) && uploadedFee >= 0 && uploadedFee <= 50) {
        setInput("mgmtFeeRatio", uploadedFee); setAssumption("mgmtFeeRatio", false);
      }
      var found = [
        result.period_start && ("기간 " + result.period_start + "~" + result.period_end),
        appliedOcc != null && ("OCC " + format(appliedOcc, 2) + "%"
          + (result.occ == null ? " 자동계산" : "")),
        result.room_revenue != null && ("객실매출 " + format(result.room_revenue, 0) + "원"),
        result.sold_rooms != null && ("판매객실 " + format(result.sold_rooms, 0) + "실"),
        result.adr != null && ("ADR " + format(result.adr, 0) + "원"),
        result.occ == null && result.sold_rooms != null && appliedOcc == null
          && "OCC 계산 불가 · 분석기간과 적용 객실 수를 확인해 주세요",
      ].filter(Boolean);
      var occupancyInsufficient = (
        result.occ == null && result.sold_rooms != null && appliedOcc == null
      );
      status.textContent = found.length
        ? (occupancyInsufficient ? "자료 인식 완료 · 운영분석 보류 · " : "자동 인식 완료 · ")
          + found.join(" · ")
        : "확인 가능한 운영지표를 찾지 못했습니다.";
      seedScenario();
      scheduleRender();
    } catch (error) {
      if (requestSequence === uploadSequence && requestBuildingId === buildingId()) {
        status.textContent = error && error.message ? error.message : "자료를 분석하지 못했습니다.";
      }
    } finally {
      if (requestSequence === uploadSequence) {
        input.disabled = false;
        input.value = "";
      }
    }
  }
  $("operationLodging").addEventListener("change", function () {
    renderRoomCount();
    setTimeout(renderChart, 0);
  });
  $("operationRoomCountInput").addEventListener("input", function () {
    var derived = applyDerivedOcc();
    if (uploadedOccupancyBasis) {
      $("operationFileStatus").textContent = derived == null
        ? "OCC 계산 불가 · 분석기간과 적용 객실 수를 확인해 주세요"
        : "적용 객실 수 변경 반영 · OCC " + format(derived, 2) + "% 자동계산";
    }
    setTimeout(renderChart, 0);
  });
  $("operationOcc").addEventListener("input", function () {
    uploadedOccupancyBasis = null;
    setAssumption("occ", false);
    updateOperationUrl("occ");
    scheduleRender();
  });
  $("operationAdr").addEventListener("input", function () {
    setAssumption("adr", false);
    updateOperationUrl("adr");
    scheduleRender();
  });
  $("operationBusinessName").addEventListener("input", function () {
    scheduleRender();
  });
  $("operationRun").addEventListener("click", scheduleRender);
  $("operationFiles").addEventListener("change", function () { analyzeFiles(this.files); });
  bindAnalysisTabs();
  bindRentalRentInput();
  $("analysisTabs").addEventListener("click", function () {
    setTimeout(function () { setModeClass(); if ($("operationTab").getAttribute("aria-selected") === "true") load(); }, 0);
  });
  window.addEventListener("livingstay:analysis-reset", function () {
    $("operationOcc").value = "";
    $("operationAdr").value = "";
    assumed = { adr: true, occ: true, opexRatio: true, mgmtFeeRatio: true, purchasePrice: true, compareRent: true };
    var config = settings();
    if (config) {
      setInput("opexRatio", config.DEFAULT_OPEX_RATIO);
      setInput("mgmtFeeRatio", config.DEFAULT_MGMT_FEE_RATIO);
    }
    setInput("purchasePrice", "");
    setInput("compareRent", "");
    purchasePriceBase = null;
    uploadedMonthlyDayBasis = null;
    uploadedMonthPeriod = null;
    uploadedOccupancyBasis = null;
    $("operationBusinessName").value = "";
    $("operationRoomCountInput").value = "";
    $("operationFiles").value = "";
    $("operationFileStatus").textContent = "파일을 끌어놓거나 눌러서 선택";
    load();
  });
  window.addEventListener("livingstay:analysis-building-clear", load);
  window.addEventListener("popstate", load);
  window.addEventListener("livingstay:operation-context", load);
  load();
}());
