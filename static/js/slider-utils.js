(function (window) {
  "use strict";

  var HARD_CAPS = Object.freeze({
    purchase: Object.freeze([100, 300000]),
    deposit: Object.freeze([0, 20000]),
    rent: Object.freeze([1, 1000]),
    vacancy: Object.freeze([0, 12]),
    adr: Object.freeze([10000, 2000000]),
    occ: Object.freeze([0, 100]),
    opex: Object.freeze([0, 90]),
    mgmtFee: Object.freeze([0, 90]),
  });

  function clampHard(kind, value, purchasePrice) {
    var bounds = kind === "loan" ? [0, Number(purchasePrice)] : HARD_CAPS[kind];
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

  window.analysisSliderUtils = Object.freeze({
    HARD_CAPS: HARD_CAPS,
    clampHard: clampHard,
    niceStep: niceStep,
    formatMan: formatMan,
    purchaseBounds: purchaseBounds,
    rentBounds: rentBounds,
    nearest: nearest,
    includeValue: includeValue,
  });
}(window));