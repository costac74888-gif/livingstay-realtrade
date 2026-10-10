(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    csrf: "", today: "", items: [], currentId: "", item: null, month: null,
    dirty: false, busy: false, quoteToken: 0
  };
  const weekdayNames = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"];
  const statusLabels = {
    draft: "작성 중",
    submitted: "제출됨",
    approved: "승인됨",
    rejected: "반려됨",
    withdrawn: "철회됨"
  };
  const errorMessages = {
    AUTH_REQUIRED: "사업자 인증이 필요합니다. 다시 로그인한 뒤 이 페이지를 새로고침해 주세요.",
    CSRF_REQUIRED: "보안 확인에 실패했습니다. 등록 목록을 새로고침한 뒤 다시 시도해 주세요.",
    ACTIVE_MEMBER_REQUIRED: "이 작업에는 활성 회원 권한이 필요합니다.",
    APPROVED_BUSINESS_REQUIRED: "승인된 사업자 정보가 있어야 이 작업을 할 수 있습니다.",
    STALE_CALENDAR_REVISION: "달력 또는 원본 등록 내용이 변경되었습니다. 입력한 내용은 그대로 보존했습니다. 내용을 확인하고 필수 비용 포함 요금을 다시 확인해 주세요. 화면의 달력 내용을 바꾸려는 경우에만 최신 내용을 다시 불러오세요.",
    INCLUSIVE_PRICE_ACK_REQUIRED: "저장하기 전에 필수 비용 포함 요금 안내를 확인해 주세요.",
    FUTURE_CALENDAR_RANGE_REQUIRED: "오늘 이후 730일 이내의 날짜 범위를 선택해 주세요. 종료일은 범위에 포함되지 않습니다.",
    PRICE_RANGE_REQUIRED: "요금은 1원 이상의 정수여야 하며 1,000,000,000원을 초과할 수 없습니다.",
    WITHDRAWAL_TERMINAL: "철회된 등록 건의 달력은 읽기 전용입니다.",
    CURRENT_PRICE_VERSION_REQUIRED: "현재 등록 버전에 사용할 수 있는 요금 버전이 없습니다.",
    CURRENT_PUBLICATION_REQUIRED: "견적을 내려면 현재 승인된 공개 숙소가 필요합니다.",
    PUBLIC_LISTING_NOT_FOUND: "현재 공개 견적을 제공할 수 없는 숙소입니다.",
    CALENDAR_UNAVAILABLE: "선택한 숙박 날짜 중 이용할 수 없는 날짜가 있습니다.",
    EXACT_PERIOD_QUOTE_UNAVAILABLE: "선택한 날짜에 적용할 수 있는 정확한 월·주 단위 요금 조합이 없습니다.",
    MINIMUM_STAY_NOT_MET: "선택한 숙박 기간이 이 숙소의 최소 이용 기간보다 짧습니다.",
    QUOTE_RATE_LIMIT: "견적 요청이 일시적으로 제한되었습니다. 잠시 후 다시 시도해 주세요.",
    FUTURE_STAY_REQUIRED: "오늘 또는 그 이후의 체크인 날짜를 선택해 주세요.",
    INVENTORY_UNAVAILABLE: "재고 정보상 선택한 날짜에는 이용할 수 없습니다.",
    INVALID_QUOTE_QUERY: "견적 요청의 날짜 정보가 올바르지 않습니다.",
    QUOTE_UNAVAILABLE: "선택한 날짜의 견적을 현재 확인할 수 없습니다."
  };
  const weekdayPresets = {
    all: [0, 1, 2, 3, 4, 5, 6],
    weekdays: [0, 1, 2, 3, 4],
    weekend: [4, 5, 6],
    friday: [4],
    saturday: [5],
    sunday: [6]
  };

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
  }
  function asDate(iso) {
    const parts = String(iso).split("-").map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2], 12);
  }
  function localIso(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }
  function addDays(iso, days) {
    const date = asDate(iso);
    date.setDate(date.getDate() + days);
    return localIso(date);
  }
  function isoWeekday(iso) {
    return (asDate(iso).getDay() + 6) % 7;
  }
  function currency(value) {
    return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(value);
  }
  function messageFor(code) {
    return errorMessages[code] || `요청을 완료하지 못했습니다 (${code || "UNKNOWN_ERROR"}). 입력한 내용은 화면에 보존되어 있습니다.`;
  }
  function showFeedback(text, tone = "error") {
    const box = $("#feedback");
    box.textContent = text;
    box.dataset.tone = tone;
    box.hidden = false;
  }
  function clearFeedback() {
    $("#feedback").hidden = true;
    $("#feedback").textContent = "";
  }
  async function request(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {})
      }
    });
    let result;
    try { result = await response.json(); } catch { result = null; }
    if (!response.ok || !result || result.ok !== true) {
      const code = result && result.code ? result.code : `HTTP_${response.status}`;
      const error = new Error(messageFor(code));
      error.code = code;
      error.status = response.status;
      throw error;
    }
    return result;
  }
  function selectedItemMeta() {
    return state.items.find((item) => item.id === state.currentId) || null;
  }
  function invalidateQuote() {
    state.quoteToken += 1;
    $("#quote-result").removeAttribute("data-state");
    $("#quote-result").innerHTML = '<div class="quote-empty"><span class="quote-mark" aria-hidden="true">—</span><strong>요청한 견적이 없습니다</strong><span>날짜, 숙소 또는 요금이 변경되어 이전 견적을 지웠습니다.</span></div>';
  }
  function showQuoteUnavailable(text) {
    const result = $("#quote-result");
    result.dataset.state = "error";
    result.innerHTML = `<div class="quote-empty"><span class="quote-mark" aria-hidden="true">!</span><strong>견적을 확인할 수 없습니다</strong><span>${escapeText(text)}</span></div>`;
  }
  function dirtyCheck() {
    if (!state.dirty) return true;
    return window.confirm("저장하지 않은 달력 입력 내용이 있습니다. 계속하면 입력 내용이 사라집니다. 진행할까요?");
  }
  function markDirty() {
    state.dirty = true;
    invalidateQuote();
    updateSaveAvailability();
  }
  function clearEntryForm() {
    $("#price-form").reset();
    $$(".clear-rate").forEach((button) => {
      button.classList.remove("is-cleared");
      const key = button.dataset.clear;
      button.textContent = `${key === "weekly" ? "주간" : "월간"} 요금 지우기`;
      $(`#${key}-amount`).placeholder = "변경하지 않음";
    });
    $("#range-start").value = state.item.today;
    $("#range-end").value = addDays(state.item.today, 1);
    state.dirty = false;
  }
  function updateSaveAvailability() {
    const withdrawn = state.item && state.item.status === "withdrawn";
    $("#save-rates").disabled = !state.item || state.busy || withdrawn;
    $("#reload-item").disabled = !state.item || state.busy;
    $("#close-range").disabled = !state.item || state.busy || withdrawn;
    $("#open-range").disabled = !state.item || state.busy || withdrawn;
    $("#request-quote").disabled = !selectedItemMeta() || selectedItemMeta().status !== "approved";
  }
  function setBusy(busy) {
    state.busy = busy;
    updateSaveAvailability();
    $("#editor-content").classList.toggle("is-busy", busy);
  }
  function updateEditorState() {
    const item = state.item;
    const empty = !item;
    $("#editor-empty").hidden = !empty;
    $("#editor-content").hidden = empty;
    $("#editor-loading").hidden = true;
    $("#stale-banner").hidden = !item || !item.stale;
    if (!item) {
      $("#calendar-title").textContent = "등록 건을 선택하세요";
      $("#version-label").textContent = "불러온 버전 없음";
      $("#version-label").removeAttribute("data-stale");
      updateSaveAvailability();
      return;
    }
    $("#calendar-title").textContent = item.title;
    $("#version-label").textContent = `버전 ${item.version} · 원본 r${item.source_revision}${item.stale ? " · 변경됨" : ""}`;
    $("#version-label").dataset.stale = String(Boolean(item.stale));
    const withdrawn = item.status === "withdrawn";
    const statusText = statusLabels[item.status] || "기타 상태";
    $("#registration-status").innerHTML = `<span class="status-pill" data-status="${escapeText(item.status)}">${escapeText(statusText)}</span>${withdrawn ? '<p class="read-only-note">철회된 등록 건은 읽기 전용입니다.</p>' : ""}`;
    $("#price-form").classList.toggle("read-only", withdrawn);
    $$("input,button", $("#price-form")).forEach((control) => { control.disabled = withdrawn; });
    $("#lodging-fields").hidden = item.calendar.kind !== "lodging";
    $("#period-fields").hidden = item.calendar.kind !== "non_lodging";
    $("#range-start").min = item.today;
    $("#range-end").min = item.today;
    if (!$("#range-start").value) $("#range-start").value = item.today;
    if (!$("#range-end").value || $("#range-end").value <= item.today) $("#range-end").value = addDays(item.today, 1);
    $("#quote-check-in").min = item.today;
    updateSaveAvailability();
    renderCalendar();
  }
  async function loadMeta({ retry = false } = {}) {
    clearFeedback();
    $("#global-loading").hidden = false;
    $("#fatal").hidden = true;
    $("#workspace").hidden = true;
    try {
      const result = await request("/hs2/calendar/meta");
      state.csrf = result.csrf;
      state.today = result.today;
      state.items = result.items;
      const select = $("#listing-select");
      const keep = state.currentId && state.items.some((row) => row.id === state.currentId) ? state.currentId : "";
      select.innerHTML = '<option value="">등록 건을 선택하세요</option>' + state.items.map((row) =>
        `<option value="${escapeText(row.id)}">${escapeText(row.title)} · ${escapeText(statusLabels[row.status] || "기타 상태")}</option>`
      ).join("");
      select.value = keep;
      $("#registration-status").textContent = state.items.length ? `내 비공개 등록 ${state.items.length}건을 선택할 수 있습니다.` : "이 계정에서 조회된 등록 건이 없습니다.";
      $("#global-loading").hidden = true;
      $("#workspace").hidden = false;
      updateSaveAvailability();
      if (keep && !state.item) await loadItem(keep);
      else if (!keep) updateEditorState();
    } catch (error) {
      $("#global-loading").hidden = true;
      $("#fatal-copy").textContent = error.message || "등록 목록을 불러오지 못했습니다.";
      $("#fatal").hidden = false;
      if (retry) showFeedback(error.message, "error");
    }
  }
  async function loadItem(id, { explicit = false } = {}) {
    if (!id) {
      state.currentId = "";
      state.item = null;
      state.dirty = false;
      invalidateQuote();
      updateEditorState();
      return;
    }
    if (explicit && !dirtyCheck()) {
      $("#listing-select").value = state.currentId;
      return;
    }
    state.currentId = id;
    state.item = null;
    state.dirty = false;
    clearFeedback();
    invalidateQuote();
    $("#editor-empty").hidden = true;
    $("#editor-content").hidden = true;
    $("#editor-loading").hidden = false;
      $("#calendar-title").textContent = "등록 건을 불러오는 중…";
    try {
      const result = await request(`/hs2/calendar/applications/${encodeURIComponent(id)}/prices`);
      state.item = result.item;
      clearEntryForm();
      if (!state.month) {
        const now = asDate(state.item.today);
        state.month = new Date(now.getFullYear(), now.getMonth(), 1, 12);
      }
      updateEditorState();
      if (state.item.status === "withdrawn") showFeedback("철회된 등록 건입니다. 요금 달력은 읽기 전용입니다.", "info");
    } catch (error) {
      state.item = null;
      updateEditorState();
      showFeedback(error.message, "error");
    }
  }
  function rateForDate(iso) {
    const calendar = state.item.calendar;
    const dayOverride = calendar.daily && Object.prototype.hasOwnProperty.call(calendar.daily, iso);
    const dailyAmount = dayOverride ? calendar.daily[iso] : calendar.base;
    const period = (calendar.periods && calendar.periods[iso]) || {};
    return { dayOverride, dailyAmount, period };
  }
  function renderCalendar() {
    if (!state.item || !state.month) return;
    const month = state.month;
    const year = month.getFullYear();
    const monthIndex = month.getMonth();
    $("#month-label").textContent = new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long" }).format(month);
    const first = new Date(year, monthIndex, 1, 12);
    const startOffset = (first.getDay() + 6) % 7;
    const count = new Date(year, monthIndex + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < startOffset; i += 1) cells.push('<div class="day-cell empty-day" role="gridcell" aria-hidden="true"></div>');
    const calendar = state.item.calendar;
    const blocked = new Set(calendar.blocked || []);
    let rateCount = 0;
    let blockedCount = 0;
    for (let n = 1; n <= count; n += 1) {
      const date = new Date(year, monthIndex, n, 12);
      const iso = localIso(date);
      const { dayOverride, dailyAmount, period } = rateForDate(iso);
      const isBlocked = blocked.has(iso);
      const isPast = iso < state.item.today;
      const isToday = iso === state.item.today;
      const hasDaily = calendar.kind === "lodging" && Number.isInteger(dailyAmount) && dailyAmount > 0;
      const hasPeriod = calendar.kind === "non_lodging" && [period.weekly, period.monthly].some((x) => Number.isInteger(x) && x > 0);
      if (hasDaily || hasPeriod) rateCount += 1;
      if (isBlocked) blockedCount += 1;
      let detail = "";
      if (calendar.kind === "lodging") {
        if (hasDaily) detail = `<strong>${currency(dailyAmount)}</strong>${dayOverride ? '<span class="override-tag">날짜별 변경</span>' : '<span>기본 요금</span>'}`;
        else detail = '<span>요금 없음</span>';
      } else {
        const parts = [];
        if (period.weekly !== undefined) parts.push(period.weekly === null ? "주간 요금 미설정" : `주 ${currency(period.weekly)}`);
        if (period.monthly !== undefined) parts.push(period.monthly === null ? "월간 요금 미설정" : `월 ${currency(period.monthly)}`);
        detail = parts.length ? `<strong>${parts.map(escapeText).join("<br>")}</strong>` : '<span>기간 요금</span>';
      }
      const classes = ["day-cell", isBlocked ? "blocked-day" : "", isPast ? "past" : "", isToday ? "today" : ""].filter(Boolean).join(" ");
      const statusLabel = isBlocked ? "이용 불가" : hasDaily || hasPeriod ? "요금 설정됨" : "별도 요금 없음";
      const aria = `${iso} ${weekdayNames[isoWeekday(iso)]}, ${statusLabel}${hasDaily ? `, 1박 ${currency(dailyAmount)}` : ""}${isBlocked ? ", 이용 불가 날짜" : ""}`;
      cells.push(`<div class="${classes}" role="gridcell" aria-label="${escapeText(aria)}"><div class="day-top"><span class="day-number">${n}</span><span class="day-status ${isBlocked ? "is-blocked" : hasDaily || hasPeriod ? "has-rate" : ""}" aria-hidden="true"></span></div><div class="day-rate">${detail}</div></div>`);
    }
    const trailing = (7 - (cells.length % 7)) % 7;
    for (let i = 0; i < trailing; i += 1) cells.push('<div class="day-cell empty-day" role="gridcell" aria-hidden="true"></div>');
    $("#calendar-days").innerHTML = cells.join("");
    const rateType = calendar.kind === "lodging" ? "1박 요금" : "기간 요금";
    $("#calendar-summary").textContent = `이번 달 별도 ${rateType}이 설정된 날짜 ${rateCount}일 · 이용 불가 날짜 ${blockedCount}일`;
  }
  function getFormDateRange() {
    const start = $("#range-start").value;
    const end = $("#range-end").value;
    if (!start || !end || start >= end) throw new Error("올바른 날짜 범위를 선택해 주세요. 시작일은 종료일보다 빨라야 하며 종료일은 범위에 포함되지 않습니다.");
    if (start < state.item.today) throw new Error("오늘 이후의 날짜만 변경할 수 있습니다.");
    const max = addDays(state.item.today, 731);
    if (end > max) throw new Error("선택한 기간이 향후 730일 범위를 초과합니다.");
    return { start, end };
  }
  function parseAmount(input, label) {
    const raw = input.value;
    if (!raw || !/^[0-9]+$/.test(raw)) throw new Error(`${label}은(는) 1원 이상의 정수여야 합니다.`);
    const amount = Number(raw);
    if (!Number.isSafeInteger(amount) || amount < 1 || amount > 1000000000) throw new Error(`${label}은(는) 1원 이상 1,000,000,000원 이하여야 합니다.`);
    return amount;
  }
  function inclusiveAcknowledged() {
    if (!$("#inclusive-ack").checked) throw new Error("저장하기 전에 필수 비용 포함 요금 안내를 확인해 주세요.");
    return true;
  }
  function commandFor(action, values = {}) {
    const range = getFormDateRange();
    const inclusive = inclusiveAcknowledged();
    return { ...range, action, values, inclusive };
  }
  async function saveCommand(command) {
    if (!state.item || state.item.status === "withdrawn") return;
    if (state.busy) return;
    clearFeedback();
    invalidateQuote();
    const snapshot = state.item;
    setBusy(true);
    try {
      const result = await request(`/hs2/calendar/applications/${encodeURIComponent(state.currentId)}/prices`, {
        method: "POST",
        headers: { "X-HS2-CSRF": state.csrf },
        body: JSON.stringify({
          version: snapshot.version,
          source_revision: snapshot.source_revision,
          command
        })
      });
      state.item = { ...snapshot, ...result.item, title: snapshot.title, status: snapshot.status };
      state.dirty = false;
      $("#inclusive-ack").checked = false;
      setBusy(false);
      updateEditorState();
      showFeedback("달력 변경을 저장했습니다. 서버의 최신 버전을 표시하고 있습니다.", "success");
    } catch (error) {
      setBusy(false);
      if (error.code === "STALE_CALENDAR_REVISION") {
        showFeedback(`${error.message} 화면의 입력 내용을 버리기로 한 경우에만 ‘최신 내용 다시 불러오기’를 선택하세요.`, "error");
      } else {
        showFeedback(error.message, "error");
      }
    }
  }
  function buildRateValues() {
    const kind = state.item.calendar.kind;
    if (kind === "lodging") {
      const range = getFormDateRange();
      const weekdays = range.end === addDays(range.start, 1)
        ? [String(isoWeekday(range.start))]
        : $$('input[name="weekday"]:checked').map((input) => input.value);
      if (!weekdays.length) throw new Error("1박 요금을 적용할 요일을 하나 이상 선택해 주세요.");
      const amount = parseAmount($("#nightly-amount"), "1박 요금");
      return Object.fromEntries(weekdays.map((day) => [day, amount]));
    }
    const values = {};
    const weekly = $("#weekly-amount").value.trim();
    const monthly = $("#monthly-amount").value.trim();
    if (weekly) values.weekly = parseAmount($("#weekly-amount"), "주간 요금");
    if (monthly) values.monthly = parseAmount($("#monthly-amount"), "월간 요금");
    $$("[data-clear].is-cleared").forEach((button) => { values[button.dataset.clear] = null; });
    if (!Object.keys(values).length) throw new Error("주간 또는 월간 요금을 입력하거나 기간 요금을 명시적으로 지워 주세요.");
    return values;
  }
  function clearRateInput(event) {
    const button = event.currentTarget;
    const key = button.dataset.clear;
    const input = $(`#${key}-amount`);
    if (button.classList.toggle("is-cleared")) {
      input.value = "";
      input.placeholder = "이 요금을 지웁니다";
      button.textContent = `${key === "weekly" ? "주간" : "월간"} 요금 지우기 취소`;
    } else {
      input.placeholder = "변경하지 않음";
      button.textContent = `${key === "weekly" ? "주간" : "월간"} 요금 지우기`;
    }
    markDirty();
  }
  function prepareQuoteDates() {
    const checkIn = $("#quote-check-in").value;
    const checkOut = $("#quote-check-out").value;
    if (!checkIn || !checkOut || checkIn >= checkOut) throw new Error("체크인 날짜와 그 이후의 체크아웃 날짜를 선택해 주세요.");
    if (state.item && checkIn < state.item.today) throw new Error("오늘 또는 그 이후의 체크인 날짜를 선택해 주세요.");
    if (state.item && state.item.calendar.kind === "lodging" && checkOut <= checkIn) throw new Error("숙박업 이용 기간은 최소 1박이어야 합니다.");
    return { checkIn, checkOut };
  }
  async function requestQuote() {
    const meta = selectedItemMeta();
    if (!meta || meta.status !== "approved") {
      showQuoteUnavailable("공개 숙소가 있는 승인 등록 건을 선택해 주세요.");
      return;
    }
    let dates;
    try { dates = prepareQuoteDates(); } catch (error) { showQuoteUnavailable(error.message); return; }
    invalidateQuote();
    const token = state.quoteToken;
    const result = $("#quote-result");
    result.dataset.state = "loading";
    result.innerHTML = '<div class="quote-empty"><span class="quote-mark" aria-hidden="true">…</span><strong>현재 견적을 요청하는 중</strong><span>공개 견적을 실제로 조회하고 있습니다.</span></div>';
    const query = new URLSearchParams({ public_id: meta.public_id, check_in: dates.checkIn, check_out: dates.checkOut });
    try {
      const response = await request(`/hs2/calendar/quote?${query.toString()}`);
      if (token !== state.quoteToken) return;
      renderQuote(response.quote);
    } catch (error) {
      if (token !== state.quoteToken) return;
      showQuoteUnavailable(error.message);
    }
  }
  function renderQuote(quote) {
    if (!quote || !Array.isArray(quote.lines) || !Number.isInteger(quote.total_krw)) {
      showQuoteUnavailable("견적 조회 결과를 확인할 수 없습니다.");
      return;
    }
    const result = $("#quote-result");
    result.dataset.state = "ready";
    const unitLabels = { night: "박", week: "주", month: "개월" };
    const lines = quote.lines.map((line) =>
      `<div class="quote-line"><span>${escapeText(line.start)} → ${escapeText(line.end)} · ${escapeText(unitLabels[line.unit] || "단위 확인 필요")}</span><strong>${currency(line.amount_krw)}</strong></div>`
    ).join("");
    result.innerHTML = `<div class="quote-total"><span>실제 숙박 견적 · 원화</span><strong>${currency(quote.total_krw)}</strong></div><div class="quote-lines">${lines}</div><p class="quote-terms">필수 운영 비용 포함: ${quote.fees_included === true ? "예" : "아니요"} · 보증금 포함: ${quote.deposit_included === true ? "예" : "아니요"} · 예약 확정: ${quote.booking_confirmed === true ? "예" : "아니요"}</p>`;
  }
  function onDateEdit() {
    markDirty();
    invalidateQuote();
  }
  function setDateDefaultsForQuote() {
    const today = state.item ? state.item.today : state.today;
    if (!today) return;
    if (!$("#quote-check-in").value || $("#quote-check-in").value < today) $("#quote-check-in").value = today;
    if (!$("#quote-check-out").value || $("#quote-check-out").value <= $("#quote-check-in").value) $("#quote-check-out").value = addDays($("#quote-check-in").value, 1);
  }

  $("#retry-meta").addEventListener("click", () => loadMeta({ retry: true }));
  $("#reload-meta").addEventListener("click", async () => {
    if (!dirtyCheck()) return;
    state.dirty = false;
    state.item = null;
    invalidateQuote();
    await loadMeta();
    if ($("#listing-select").value) await loadItem($("#listing-select").value);
  });
  $("#listing-select").addEventListener("change", async (event) => {
    const nextId = event.target.value;
    if (state.dirty && !dirtyCheck()) {
      event.target.value = state.currentId;
      return;
    }
    await loadItem(nextId, { explicit: false });
    setDateDefaultsForQuote();
  });
  $("#reload-item").addEventListener("click", async () => {
    if (!state.currentId || !dirtyCheck()) return;
    state.dirty = false;
    $("#inclusive-ack").checked = false;
    await loadItem(state.currentId);
  });
  $("#month-prev").addEventListener("click", () => {
    if (!state.month) return;
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1, 12);
    renderCalendar();
  });
  $("#month-next").addEventListener("click", () => {
    if (!state.month) return;
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1, 12);
    renderCalendar();
  });
  $("#price-form").addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const action = state.item && state.item.calendar.kind === "non_lodging" ? "periods" : "nightly";
      saveCommand(commandFor(action, buildRateValues()));
    }
    catch (error) { showFeedback(error.message, "error"); }
  });
  $("#close-range").addEventListener("click", () => {
    try { saveCommand(commandFor("close", {})); }
    catch (error) { showFeedback(error.message, "error"); }
  });
  $("#open-range").addEventListener("click", () => {
    try { saveCommand(commandFor("open", {})); }
    catch (error) { showFeedback(error.message, "error"); }
  });
  $("#price-form").addEventListener("input", (event) => {
    if (event.target.matches('input[type="date"],input[type="number"]')) onDateEdit();
    if (event.target.matches("#weekly-amount,#monthly-amount")) {
      const key = event.target.id.replace("-amount", "");
      const clearButton = $(`[data-clear="${key}"]`);
      clearButton.classList.remove("is-cleared");
      clearButton.textContent = `${key === "weekly" ? "주간" : "월간"} 요금 지우기`;
      event.target.placeholder = "변경하지 않음";
    }
  });
  $("#price-form").addEventListener("change", (event) => {
    if (event.target.matches('input[name="weekday"],#inclusive-ack')) markDirty();
    if (event.target.matches('input[type="date"]')) invalidateQuote();
  });
  $$(".preset-button").forEach((button) => button.addEventListener("click", () => {
    const chosen = new Set(weekdayPresets[button.dataset.preset]);
    $$('input[name="weekday"]').forEach((input) => { input.checked = chosen.has(Number(input.value)); });
    $$(".preset-button").forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
    markDirty();
  }));
  $$(".clear-rate").forEach((button) => button.addEventListener("click", clearRateInput));
  $("#quote-check-in").addEventListener("change", () => {
    if ($("#quote-check-in").value && $("#quote-check-out").value <= $("#quote-check-in").value) $("#quote-check-out").value = addDays($("#quote-check-in").value, 1);
    invalidateQuote();
  });
  $("#quote-check-out").addEventListener("change", invalidateQuote);
  $("#request-quote").addEventListener("click", requestQuote);
  loadMeta();
})();
