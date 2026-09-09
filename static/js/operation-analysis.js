(function () {
  "use strict";
  var uploadedOccupancyBasis = null;

  var building = null;
  var benchmarks = [];
  var region = "";
  var subregion = "";
  var loadSequence = 0;

  function $(id) { return document.getElementById(id); }
  function number(value) {
    return value == null || value === "" || isNaN(Number(value)) ? null : Number(value);
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
    $("operationMethodRegion").textContent = subregion
      ? subregion + "의 2024년 전체등급 운영지표 ADR·OCC를 사분면 중앙 기준선으로 사용합니다."
      : region
        ? region + " 내 " + benchmarks.length
          + "개 시군구의 운영지표 평균을 사분면 기준선으로 사용합니다."
      : "선택 건물의 주소로 비교지역을 자동 산정합니다.";
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
      $("operationDetail").innerHTML = '<div class="detail-empty"><div><strong>운영자료를 입력해 주세요</strong>ADR과 OCC를 입력하면 운영분석 보고서와 공유 버튼이 표시됩니다.</div></div>';
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
    window.livingstayAnalysisReportActions($("operationReportActions"), buildingId(), name);
  }
  function renderChart() {
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
          };
        },
      }],
    });
  }
  function load() {
    setModeClass();
    var id = buildingId();
    var sequence = ++loadSequence;
    if (!id) {
      building = null; benchmarks = []; region = ""; subregion = "";
      window.__operationAnalysisBuilding = null;
      $("operationLodging").innerHTML = '<option value="">건물을 먼저 선택해 주세요</option>';
      $("operationBusinessName").value = "";
      $("operationRoomCountInput").value = "";
      renderRoomCount();
      renderChart();
      return;
    }
    Promise.all([
      fetch("/api/building/" + encodeURIComponent(id), { credentials: "same-origin" }).then(function (response) {
        return response.ok ? response.json() : null;
      }),
      fetch("/api/analysis/operation-benchmarks?building_id=" + encodeURIComponent(id),
        { credentials: "same-origin" }).then(function (response) { return response.ok ? response.json() : null; }),
    ]).then(function (results) {
      if (sequence !== loadSequence || !results[0]) return;
      building = results[0];
      window.__operationAnalysisBuilding = building;
      benchmarks = results[1] && Array.isArray(results[1].items) ? results[1].items : [];
      region = results[1] && results[1].sido || "";
      subregion = results[1] && results[1].sgg || "";
      $("operationBusinessName").value = building.display_building_name || building.building_name || "";
      setBuildingStatus(building.display_building_name || building.building_name || "선택 건물", true);
      renderLodgingOptions();
      renderChart();
    }).catch(function () {});
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
    status.textContent = files.length + "개 파일 자동 분석 중…";
    input.disabled = true;
    try {
      var form = new FormData();
      Array.from(files).forEach(function (file) { form.append("files", file); });
      var response = await fetch("/api/analysis/operation-upload", {
        method: "POST", body: form, credentials: "same-origin",
      });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok) throw Error(payload.message || "자료를 분석하지 못했습니다.");
      var result = payload.result || {};
      var appliedOcc = number(result.occ);
      uploadedOccupancyBasis = null;
      if (appliedOcc != null) {
        $("operationOcc").value = appliedOcc;
      } else if (number(result.sold_rooms) != null) {
        uploadedOccupancyBasis = {
          soldRooms: result.sold_rooms,
          days: result.occupancy_days,
        };
        appliedOcc = applyDerivedOcc();
      }
      if (result.adr != null) $("operationAdr").value = Math.round(result.adr);
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
      renderChart();
    } catch (error) {
      status.textContent = error && error.message ? error.message : "자료를 분석하지 못했습니다.";
    } finally {
      input.disabled = false;
      input.value = "";
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
    setTimeout(renderChart, 0);
  });
  $("operationAdr").addEventListener("input", function () {
    setTimeout(renderChart, 0);
  });
  $("operationBusinessName").addEventListener("input", function () {
    setTimeout(renderChart, 0);
  });
  $("operationRun").addEventListener("click", function () { setTimeout(renderChart, 0); });
  $("operationFiles").addEventListener("change", function () { analyzeFiles(this.files); });
  $("analysisTabs").addEventListener("click", function () {
    setTimeout(function () { setModeClass(); if ($("operationTab").getAttribute("aria-selected") === "true") load(); }, 0);
  });
  window.addEventListener("livingstay:analysis-reset", function () {
    $("operationOcc").value = "";
    $("operationAdr").value = "";
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
