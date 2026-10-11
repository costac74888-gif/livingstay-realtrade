/* Pure Preview-only rate/date presentation helpers. CommonJS exports are kept
   deliberately dependency-free for focused Node-side consumer tests. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.HS2PreviewRateDate = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const NOTICE = "기본 요금이며 날짜에 따라 다를 수 있습니다";
  const MAX_RATE = 1000000000;
  const isRate = value => Number.isSafeInteger(value) && value >= 0 && value <= MAX_RATE;
  const won = value => Number.isSafeInteger(value) && value >= 0
    ? `${value.toLocaleString("ko-KR")}원` : null;
  const isoParts = value => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 &&
      date.getUTCDate() === day ? { year, month, day, date } : null;
  };
  const iso = date => date.toISOString().slice(0, 10);
  function addDays(value, days) {
    const parts = isoParts(value);
    if (!parts || !Number.isInteger(days)) return "";
    const date = new Date(parts.date);
    date.setUTCDate(date.getUTCDate() + days);
    return iso(date);
  }
  function addMonthsClamped(value, months) {
    const parts = isoParts(value);
    if (!parts || !Number.isInteger(months)) return "";
    const first = new Date(Date.UTC(parts.year, parts.month - 1 + months, 1));
    const lastDay = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
    first.setUTCDate(Math.min(parts.day, lastDay));
    return iso(first);
  }
  function nightsBetween(start, end) {
    const a = isoParts(start), b = isoParts(end);
    if (!a || !b || end <= start) return null;
    return Math.round((b.date - a.date) / 86400000);
  }
  function quickPeriods(kind) {
    return kind === "non_lodging"
      ? [{ label: "1주", days: 7 }, { label: "2주", days: 14 },
        { label: "4주", days: 28 }, { label: "1개월", months: 1 }, { label: "3개월", months: 3 }]
      : [{ label: "1박", days: 1 }, { label: "2박", days: 2 }, { label: "7박", days: 7 }];
  }
  function checkoutFor(start, period) {
    return period.months ? addMonthsClamped(start, period.months) : addDays(start, period.days);
  }
  function validQuote(quote, checkIn, checkOut) {
    return !!quote && Number.isSafeInteger(quote.total_krw) && quote.total_krw >= 0 &&
      quote.check_in === checkIn && quote.check_out === checkOut &&
      nightsBetween(checkIn, checkOut) !== null;
  }
  function quoteNights(quote) {
    return quote && nightsBetween(quote.check_in, quote.check_out);
  }
  function basePresentation(kind, rates, quote, checkIn, checkOut) {
    const result = { headline: "기준 요금 비공개", notice: null, quote: null };
    const keys = rates && typeof rates === "object" ? Object.keys(rates) : [];
    const valid = kind === "lodging"
      ? keys.length === 1 && keys[0] === "night" && isRate(rates.night)
      : kind === "non_lodging" && keys.every(key => ["week", "month"].includes(key)) &&
        keys.length > 0 && keys.every(key => rates[key] === null || isRate(rates[key])) &&
        (isRate(rates.week) || isRate(rates.month));
    if (!valid) rates = null;
    if (kind === "lodging") {
      if (rates && isRate(rates.night)) result.headline = `1박 ${won(rates.night)}`;
      if (rates && rates.night !== null && rates.night !== undefined) result.notice = NOTICE;
    } else if (kind === "non_lodging") {
      const pieces = [];
      if (rates && isRate(rates.week)) pieces.push(`1주 ${won(rates.week)}`);
      if (rates && isRate(rates.month)) pieces.push(`1개월 ${won(rates.month)}`);
      if (pieces.length) result.headline = pieces.join(" · ");
      if (rates && (rates.week !== null && rates.week !== undefined ||
          rates.month !== null && rates.month !== undefined)) result.notice = NOTICE;
    }
    if (validQuote(quote, checkIn, checkOut)) {
      const nights = quoteNights(quote);
      result.quote = { total: won(quote.total_krw), nights,
        text: kind === "lodging"
          ? `선택 ${nights}박 총 ${won(quote.total_krw)}`
          : `선택 ${nights}일 총 ${won(quote.total_krw)}` };
    }
    return result;
  }
  function quoteIssue(item) {
    return item && item.quote_issue === "EXACT_PERIOD_QUOTE_UNAVAILABLE" ? item.quote_issue : null;
  }
  function candidateDates(item) {
    return Array.isArray(item && item.candidate_check_outs)
      ? item.candidate_check_outs.filter(value => isoParts(value)) : [];
  }
  function rateWarnings(kind, week, month) {
    if (kind === "lodging") return isRate(week) && week === 0
      ? ["요금이 0원입니다. 의도한 금액인지 확인해 주세요."] : [];
    if (kind !== "non_lodging") return [];
    const warnings = [];
    if ((isRate(week) && week === 0) || (isRate(month) && month === 0))
      warnings.push("요금이 0원입니다. 의도한 금액인지 확인해 주세요.");
    if (isRate(week) && week > 0 && isRate(month) && month > week * 5)
      warnings.push("월 요금이 주 요금의 5배보다 큽니다. 금액을 확인해 주세요.");
    if (isRate(week) && week > 0 && isRate(month) && month < week * 2)
      warnings.push("월 요금이 주 요금의 2배보다 작습니다. 금액을 확인해 주세요.");
    return warnings;
  }
  // Display only: night remains the source tariff and quotes still count nights.
  // Do not convert calendar months to weeks, or null/withheld rates to zero.
  function displayRate(kind, rates) {
    const valid = basePresentation(kind, rates).notice !== null;
    if (!valid) return {text: "요금 비공개", unit: null, kind};
    if (kind === "lodging") return {text: `${won(rates.night)}/일`, unit: "day", kind};
    if (isRate(rates.week)) return {text: `${won(rates.week)}/주`, unit: "week", kind};
    if (isRate(rates.month)) return {text: `${won(rates.month)}/월`, unit: "month", kind};
    return {text: "요금 비공개", unit: null, kind};
  }
  return { NOTICE, MAX_RATE, isRate, won, isoParts, addDays, addMonthsClamped,
    nightsBetween, quickPeriods, checkoutFor, validQuote, quoteNights,
     basePresentation, quoteIssue, candidateDates, rateWarnings, displayRate };
});
