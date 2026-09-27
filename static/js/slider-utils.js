(function (window) {
  "use strict";

  var HARD_CAPS = Object.freeze({
    purchase: Object.freeze([0, 500000]),
    loan: Object.freeze([0, 500000]),
    deposit: Object.freeze([0, 50000]),
    rent: Object.freeze([0, 1000]),
    vacancy: Object.freeze([0, 12]),
    adr: Object.freeze([10000, 2000000]),
    occ: Object.freeze([20, 100]),
    opex: Object.freeze([10, 80]),
    mgmtFee: Object.freeze([0, 50]),
  });

  function clampHard(kind, value) {
    var bounds = HARD_CAPS[kind];
    if (!bounds) throw new Error("알 수 없는 슬라이더 항목: " + kind);
    if (value === "" || value === null || value === undefined) return null;
    var parsed = Number(value);
    return Number.isFinite(parsed) && Number.isFinite(bounds[1])
      && parsed >= bounds[0] && parsed <= bounds[1] ? parsed : null;
  }

  function niceStep(rawStep) {
    if (!Number.isFinite(rawStep) || rawStep <= 0) throw new RangeError("간격은 양수여야 합니다.");
    var magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
    var scale = rawStep / magnitude;
    return (scale <= 1 ? 1 : scale <= 2 ? 2 : scale <= 5 ? 5 : 10) * magnitude;
  }

  // 금액은 모두 만원 단위로 입력받습니다.
  function formatMan(amount, digits) {
    if (!Number.isFinite(Number(amount))) return "입력 필요";
    var value = Number(amount), precision = digits == null ? 2 : digits;
    var options = { maximumFractionDigits: precision };
    if (Math.abs(value) < 10000) return value.toLocaleString("ko-KR", options) + "만원";
    var eok = Math.trunc(value / 10000);
    var remainder = Math.abs(value % 10000);
    return eok.toLocaleString("ko-KR") + "억"
      + (remainder ? " " + remainder.toLocaleString("ko-KR", options) + "만원" : "원");
  }

  function purchaseBounds(base) {
    if (!Number.isFinite(base) || base <= 0) return null;
    var min = Math.max(0, Math.floor(base * 0.7));
    var max = Math.ceil(base * 1.3);
    return { min: min, max: max, step: niceStep((max - min) / 40) };
  }

  function rentBounds(center) {
    if (!Number.isFinite(center) || center <= 0) return null;
    var min = Math.max(5, Math.floor(center * 0.5));
    var max = Math.max(center + 20, Math.ceil(center * 1.5));
    return { min: min, max: max, step: niceStep((max - min) / 40) };
  }

  function nearest(value, bounds) {
    return Math.max(bounds.min, Math.min(bounds.max,
      bounds.min + Math.round((value - bounds.min) / bounds.step) * bounds.step));
  }

  function includeValue(bounds, value) {
    if (!bounds || !Number.isFinite(value)) return bounds;
    return {
      min: Math.min(bounds.min, value),
      max: Math.max(bounds.max, value),
      step: bounds.step,
    };
  }

  function rangeTicks(bounds) {
    if (!bounds || !Number.isFinite(Number(bounds.min)) || !Number.isFinite(Number(bounds.max))
      || !Number.isFinite(Number(bounds.step)) || Number(bounds.step) <= 0) return [];
    var min = Number(bounds.min), max = Number(bounds.max), step = Number(bounds.step);
    if (max < min) return [];
    var count = Math.floor((max - min) / step + 1e-10);
    var ticks = [];
    for (var index = 0; index <= count; index += 1) ticks.push(min + index * step);
    if (!ticks.length || ticks[ticks.length - 1] < max - Math.max(1, Math.abs(max)) * 1e-12) {
      ticks.push(max);
    } else {
      ticks[ticks.length - 1] = Math.min(max, ticks[ticks.length - 1]);
    }
    return ticks;
  }

  function mappedTicks(maxIndex, mapper) {
    var ticks = [];
    for (var index = 0; index <= maxIndex; index += 1) {
      var value = Number(mapper(index));
      if (Number.isFinite(value)) ticks.push(value);
    }
    return ticks;
  }

  // Find the strictly adjacent attainable value. This deliberately does not
  // snap a directly-entered between-tick value before choosing its direction.
  function adjacentTick(value, ticks, direction) {
    if (value === "" || value === null || value === undefined
      || !ticks || !ticks.length || !Number.isFinite(Number(value))) return null;
    var current = Number(value), low = 0, high = ticks.length;
    if (direction > 0) {
      while (low < high) {
        var middle = Math.floor((low + high) / 2);
        if (ticks[middle] <= current) low = middle + 1;
        else high = middle;
      }
      return low < ticks.length ? ticks[low] : null;
    }
    while (low < high) {
      var previousMiddle = Math.floor((low + high) / 2);
      if (ticks[previousMiddle] < current) low = previousMiddle + 1;
      else high = previousMiddle;
    }
    return low > 0 ? ticks[low - 1] : null;
  }

  function syncStepButtons(row, value, ticks) {
    if (!row) return;
    ["-1", "1"].forEach(function (direction) {
      var button = row.querySelector('[data-slider-direction="' + direction + '"]');
      if (button) button.disabled = adjacentTick(value, ticks, Number(direction)) == null;
    });
  }

  function bindStepButtons(container, onStep) {
    if (!container) return;
    Array.prototype.forEach.call(container.querySelectorAll("[data-slider-step]"), function (button) {
      var delayTimer = 0, repeatTimer = 0, repeating = false;
      function stopRepeating() {
        window.clearTimeout(delayTimer);
        window.clearInterval(repeatTimer);
        delayTimer = repeatTimer = 0;
        repeating = false;
      }
      function step() {
        if (button.disabled || onStep(button) === false) stopRepeating();
      }
      button.addEventListener("pointerdown", function (event) {
        if (event.button != null && event.button !== 0) return;
        stopRepeating();
        repeating = true;
        step();
        if (!repeating || button.disabled) return;
        delayTimer = window.setTimeout(function () {
          if (!repeating || button.disabled) return stopRepeating();
          repeatTimer = window.setInterval(function () {
            if (!repeating || button.disabled) return stopRepeating();
            step();
          }, 120);
        }, 400);
      });
      ["pointerup", "pointerleave", "pointercancel", "lostpointercapture"].forEach(function (type) {
        button.addEventListener(type, stopRepeating);
      });
      button.addEventListener("click", function (event) {
        // Pointer activation already stepped on pointerdown. detail === 0 is
        // the native keyboard activation path (Enter/Space).
        if (event.detail === 0) step();
      });
    });
  }

  window.analysisSliderUtils = Object.freeze({
    HARD_CAPS: HARD_CAPS,
    clampHard: clampHard,
    niceStep: niceStep,
    formatMan: formatMan,
    purchaseBounds: purchaseBounds,
    rentBounds: rentBounds,
    nearest: nearest,
    includeValue: includeValue,
    rangeTicks: rangeTicks,
    mappedTicks: mappedTicks,
    adjacentTick: adjacentTick,
    syncStepButtons: syncStepButtons,
    bindStepButtons: bindStepButtons,
  });
}(window));