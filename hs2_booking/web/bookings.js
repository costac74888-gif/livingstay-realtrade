(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const feedback = $("#booking-feedback");
  const feedbackCopy = feedback.querySelector(".feedback-copy");
  const list = $("#booking-list");
  const requestPanel = $("#request-panel");
  const quoteNode = $("#booking-quote");
  const ackInput = $("#booking-ack");
  const requestButton = $("#request-booking");
  const refreshButton = $("#refresh-bookings");
  const consumerButton = $("#consumer-view");
  const operatorButton = $("#operator-view");
  const roleNote = $("#role-note");
  const paymentNote = $("#payment-note");
  const params = new URLSearchParams(window.location.search);
  const receiptId = (params.get("receipt_id") || "").trim();
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  const statuses = {
    pending_operator: "운영자 확인 대기",
    awaiting_payment: "결제 대기",
    confirmed: "예약 확정",
    rejected: "운영자 거절",
    cancelled: "취소됨",
    expired: "기한 만료"
  };
  let session = null;
  let view = params.get("view") === "operator" ? "operator" : "consumer";
  let currentReceipt = null;
  let requestKey = null;
  let requestInFlight = false;
  let generation = 0;
  let listController = null;
  let deadlineTimer = null;
  const refreshedExpiredDeadlines = new Set();
  const pendingActions = new Set();

  function setFeedback(message, state) {
    feedbackCopy.textContent = message;
    feedback.dataset.state = state;
  }

  function validDate(value) {
    if (typeof value !== "string" || !datePattern.test(value)) return false;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  }

  function money(value, currency = "KRW") {
    if (!Number.isSafeInteger(value) || value <= 0 || typeof currency !== "string") return "금액 확인 필요";
    try {
      return new Intl.NumberFormat("ko-KR", { style: "currency", currency }).format(value);
    } catch (_) {
      return `${new Intl.NumberFormat("ko-KR").format(value)} ${currency}`;
    }
  }

  function dateRange(start, end) {
    if (!validDate(start) || !validDate(end) || end <= start) return "날짜 확인 필요";
    return `${start} – ${end}`;
  }

  function explainError(code, status) {
    const messages = {
      VERIFIED_CONSUMER_REQUIRED: "인증된 소비자 로그인이 필요합니다.",
      ACTIVE_CONSUMER_REQUIRED: "현재 활성화된 소비자 계정을 확인할 수 없습니다.",
      APPROVED_BUSINESS_REQUIRED: "승인된 운영자 계정이 필요합니다.",
      ACTIVE_MEMBER_REQUIRED: "현재 활성화된 운영자 계정을 확인할 수 없습니다.",
      OPERATOR_CONTEXT_REQUIRED: "운영자 계정을 확인할 수 없습니다.",
      CSRF_REQUIRED: "보안 확인이 만료되었습니다. 새로고침 후 다시 시도해 주세요.",
      QUOTE_RECEIPT_NOT_FOUND: "본인에게 발급된 견적 확인서를 찾을 수 없습니다.",
      QUOTE_RECEIPT_EXPIRED: "견적 확인서의 유효 시간이 끝났습니다. 상세 페이지에서 새 견적을 확인해 주세요.",
      QUOTE_RECEIPT_ALREADY_USED: "이 확인서는 이미 신청에 사용되었습니다.",
      QUOTE_SOURCE_CHANGED: "가격 또는 공개 조건이 변경되었습니다. 오래된 신청 정보를 폐기했습니다.",
      BOOKING_REVISION_CHANGED: "예약 상태가 먼저 변경되었습니다. 최신 서버 정보를 불러왔습니다.",
      BOOKING_STATE_CHANGED: "현재 예약 상태에서는 이 작업을 진행할 수 없습니다. 최신 정보를 불러왔습니다.",
      BOOKING_RETRY_CONFLICT: "이전 요청 키의 내용이 달라 신청을 재사용할 수 없습니다. 견적을 새로 확인해 주세요.",
      BOOKING_INVENTORY_CONFLICT: "선택한 기간의 재고가 변경되었습니다. 상세 페이지에서 조건을 다시 확인해 주세요.",
      INVENTORY_UNAVAILABLE: "현재 재고를 확인할 수 없습니다. 최신 정보를 다시 불러왔습니다.",
      ACTIVE_BOOKING_LIMIT: "동시에 진행할 수 있는 신청 한도에 도달했습니다.",
      PAYMENT_PROVIDER_UNAVAILABLE: "결제 제공자를 사용할 수 없습니다. 결제 완료로 처리되지 않았습니다.",
      PAYMENT_TERMS_REVIEW_REQUIRED: "결제 조건 확인이 완료되지 않아 확정할 수 없습니다.",
      VERIFIED_PAYMENT_REQUIRED: "서버의 결제 증빙을 확인할 수 없습니다."
    };
    if (messages[code]) return messages[code];
    if (status === 404) return "요청한 예약 또는 견적 확인서를 찾을 수 없습니다.";
    if (status === 409) return "예약 정보가 변경되었습니다. 최신 서버 정보를 불러왔습니다.";
    if (status === 403) return "선택한 역할의 인증 세션을 확인할 수 없습니다.";
    if (status === 429) return "요청이 잠시 많습니다. 잠시 후 다시 시도해 주세요.";
    return "요청을 완료하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.";
  }

  async function api(path, options = {}, signal) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, signal });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* Handle non-JSON errors uniformly. */ }
    if (!response.ok || !payload || payload.ok !== true) {
      const error = new Error(explainError(payload && payload.code, response.status));
      error.code = payload && payload.code;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function validQuote(quote, checkIn, checkOut) {
    if (!quote || !Number.isSafeInteger(quote.total_krw) || quote.total_krw <= 0 ||
        (quote.currency !== undefined && quote.currency !== "KRW")) return false;
    if (quote.check_in !== undefined && quote.check_in !== checkIn) return false;
    if (quote.check_out !== undefined && quote.check_out !== checkOut) return false;
    return Array.isArray(quote.lines) && quote.lines.length > 0 &&
      quote.lines.every((line) => line && typeof line === "object" &&
        (line.amount_krw === undefined || (Number.isSafeInteger(line.amount_krw) && line.amount_krw > 0)));
  }

  function quoteReceiptUsable(receipt) {
    const quote = receipt && receipt.quote;
    return !!receipt && uuidPattern.test(receipt.receipt_id || "") &&
      Number.isSafeInteger(receipt.guests) && receipt.guests > 0 &&
      receipt.booking_confirmed === false && receipt.inventory_held === false &&
      validDate(quote && quote.check_in) && validDate(quote && quote.check_out) &&
      quote.check_out > quote.check_in && validQuote(quote, quote.check_in, quote.check_out) &&
      Number.isFinite(Date.parse(receipt.expires_at)) && Date.parse(receipt.expires_at) > Date.now();
  }

  function clearReceipt(message = "상세 페이지에서 발급된 확인서를 불러옵니다.") {
    currentReceipt = null;
    requestKey = null;
    requestInFlight = false;
    requestPanel.hidden = true;
    ackInput.checked = false;
    ackInput.disabled = true;
    requestButton.disabled = true;
    quoteNode.replaceChildren();
    const placeholder = document.createElement("p");
    placeholder.className = "quote-placeholder";
    placeholder.textContent = message;
    quoteNode.append(placeholder);
  }

  function appendQuoteDetail(parent, label, value) {
    const block = document.createElement("div");
    block.className = "quote-detail";
    const title = document.createElement("span");
    title.textContent = label;
    const text = document.createElement("strong");
    text.textContent = value;
    block.append(title, text);
    parent.append(block);
  }

  function renderReceipt(receipt) {
    if (!quoteReceiptUsable(receipt)) throw new Error("견적 확인서의 날짜·인원·총액 또는 유효 기간을 검증할 수 없습니다.");
    currentReceipt = receipt;
    requestKey = null;
    quoteNode.replaceChildren();
    const grid = document.createElement("div");
    grid.className = "quote-grid";
    appendQuoteDetail(grid, "이용 기간", dateRange(receipt.quote.check_in, receipt.quote.check_out));
    appendQuoteDetail(grid, "인원", `${receipt.guests}명`);
    appendQuoteDetail(grid, "유효 종료", new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"
    }).format(new Date(receipt.expires_at)));
    quoteNode.append(grid);
    const total = document.createElement("div");
    total.className = "quote-total";
    const label = document.createElement("span");
    label.textContent = "확인된 기간 총액";
    const amount = document.createElement("strong");
    amount.textContent = money(receipt.quote.total_krw, receipt.quote.currency || "KRW");
    total.append(label, amount);
    quoteNode.append(total);
    if (Array.isArray(receipt.quote.lines)) {
      const lines = document.createElement("ul");
      lines.className = "quote-line-list";
      receipt.quote.lines.forEach((line) => {
        const row = document.createElement("li");
        const period = document.createElement("span");
        const start = line.start || line.check_in || "";
        const end = line.end || line.check_out || "";
        period.textContent = validDate(start) && validDate(end) ? `${start} – ${end}` : "견적 구성";
        const lineAmount = document.createElement("strong");
        lineAmount.textContent = money(line.amount_krw, receipt.quote.currency || "KRW");
        row.append(period, lineAmount);
        lines.append(row);
      });
      quoteNode.append(lines);
    }
    requestPanel.hidden = false;
    ackInput.checked = false;
    ackInput.disabled = false;
    requestButton.disabled = true;
  }

  function setRoleButtons() {
    consumerButton.setAttribute("aria-pressed", String(view === "consumer"));
    operatorButton.setAttribute("aria-pressed", String(view === "operator"));
  }

  function updateViewUrl() {
    const url = new URL(window.location.href);
    if (view === "consumer") url.searchParams.delete("view");
    else url.searchParams.set("view", "operator");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function invalidateCurrentList() {
    generation += 1;
    if (listController) listController.abort();
    listController = null;
    pendingActions.clear();
    return generation;
  }

  function switchView(next) {
    if (next === view) return;
    invalidateCurrentList();
    view = next;
    setRoleButtons();
    updateViewUrl();
    clearReceipt("역할을 변경했습니다. 견적 확인서는 소비자 화면에서 다시 확인할 수 있습니다.");
    loadBookings().then(() => {
      if (view === "consumer" && receiptId) loadReceipt();
    });
  }

  function showSkeleton() {
    list.replaceChildren();
    for (let i = 0; i < 2; i += 1) {
      const skeleton = document.createElement("div");
      skeleton.className = "list-skeleton";
      list.append(skeleton);
    }
    list.setAttribute("aria-busy", "true");
  }

  function showEmpty(title, copy) {
    list.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const mark = document.createElement("span");
    mark.className = "empty-symbol";
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = "⌂";
    const heading = document.createElement("strong");
    heading.textContent = title;
    const description = document.createElement("p");
    description.textContent = copy;
    empty.append(mark, heading, description);
    list.append(empty);
    list.setAttribute("aria-busy", "false");
  }

  function validBooking(booking) {
    return booking && uuidPattern.test(booking.booking_id || "") &&
      typeof booking.public_id === "string" && booking.public_id.length <= 100 &&
      Object.hasOwn(statuses, booking.status) && Number.isSafeInteger(booking.revision) &&
      validDate(booking.check_in) && validDate(booking.check_out) && booking.check_out > booking.check_in &&
      Number.isSafeInteger(booking.guests) && booking.guests > 0 &&
      booking.quote && Number.isSafeInteger(booking.quote.total_krw) && booking.quote.total_krw > 0 &&
      (booking.quote.currency === undefined || booking.quote.currency === "KRW") &&
      typeof booking.booking_confirmed === "boolean" && typeof booking.payment_verified === "boolean" &&
      typeof booking.inventory_held === "boolean" &&
      (booking.status !== "confirmed" || (booking.booking_confirmed === true && booking.payment_verified === true));
  }

  function remainingDeadline(booking) {
    if (typeof booking.deadline !== "string") return null;
    const ms = Date.parse(booking.deadline);
    return Number.isFinite(ms) ? ms : null;
  }

  function deadlineText(booking) {
    const deadline = remainingDeadline(booking);
    if (deadline === null) return null;
    const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    return `서버 기한까지 ${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function isTerminal(booking) {
    return ["confirmed", "rejected", "cancelled", "expired"].includes(booking.status);
  }

  function createActionButton(label, action, booking, operator, className = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `action-button ${className}`.trim();
    button.dataset.action = action;
    button.dataset.bookingId = booking.booking_id;
    button.textContent = label;
    button.disabled = pendingActions.has(booking.booking_id) ||
      (action === "confirm-payment" && !(session && session.payment_available === true));
    button.addEventListener("click", () => performAction(booking, action, operator));
    return button;
  }

  function renderBooking(booking, operator) {
    const card = document.createElement("article");
    card.className = "booking-card";
    card.dataset.bookingId = booking.booking_id;
    card.dataset.status = booking.status;
    const top = document.createElement("div");
    top.className = "booking-card-top";
    const identity = document.createElement("div");
    const code = document.createElement("p");
    code.className = "booking-code";
    code.textContent = `예약 ${booking.public_id}`;
    const dates = document.createElement("p");
    dates.className = "booking-dates";
    dates.textContent = dateRange(booking.check_in, booking.check_out);
    identity.append(code, dates);
    const status = document.createElement("span");
    status.className = "status-pill";
    status.dataset.status = booking.status;
    status.textContent = booking.status === "confirmed" &&
      (booking.booking_confirmed !== true || booking.payment_verified !== true)
      ? "확정 증빙 확인 필요" : statuses[booking.status];
    top.append(identity, status);
    card.append(top);
    const meta = document.createElement("div");
    meta.className = "booking-meta";
    const totalLabel = document.createElement("span");
    totalLabel.textContent = `서버 보관 견적 총액 · ${booking.guests}명`;
    const total = document.createElement("strong");
    total.textContent = money(booking.quote.total_krw, booking.quote.currency || "KRW");
    meta.append(totalLabel, total);
    const deadline = deadlineText(booking);
    if (deadline && !isTerminal(booking)) {
      const deadlineNode = document.createElement("span");
      deadlineNode.dataset.deadlineFor = booking.booking_id;
      deadlineNode.dataset.deadlineAt = booking.deadline;
      deadlineNode.textContent = deadline;
      meta.append(deadlineNode);
    } else if (booking.status === "confirmed" && booking.booking_confirmed === true && booking.payment_verified === true) {
      const confirmed = document.createElement("span");
      confirmed.textContent = "서버 결제 증빙 확인";
      meta.append(confirmed);
    }
    card.append(meta);

    const actions = document.createElement("div");
    actions.className = "booking-actions";
    if (!isTerminal(booking) && operator && booking.status === "pending_operator") {
      actions.append(
        createActionButton("승인", "approve", booking, true, "primary-action"),
        createActionButton("거절", "reject", booking, true)
      );
    } else if (!isTerminal(booking) && !operator &&
      ["pending_operator", "awaiting_payment"].includes(booking.status)) {
      actions.append(createActionButton("신청 취소", "cancel", booking, false));
      if (booking.status === "awaiting_payment") {
        if (session && session.payment_available === true) {
          actions.append(createActionButton("결제 확인", "confirm-payment", booking, false, "primary-action"));
        } else {
          const hint = document.createElement("p");
          hint.className = "action-hint";
          hint.textContent = "결제 제공자 이용 불가 · 결제 완료나 확정으로 처리할 수 없습니다.";
          actions.append(hint);
        }
      }
    }
    if (actions.childElementCount) card.append(actions);
    return card;
  }

  function renderBookings(bookings, operator) {
    if (!Array.isArray(bookings)) throw new Error("예약 목록 응답을 확인할 수 없습니다.");
    const valid = bookings.filter(validBooking);
    list.replaceChildren();
    if (!valid.length) {
      showEmpty(operator ? "확인할 예약이 없습니다" : "아직 예약 신청이 없습니다", operator
        ? "현재 인증된 운영자 계정의 담당 예약이 표시됩니다."
        : "상세 화면에서 발급된 견적 확인서로 예약 신청을 시작할 수 있습니다.");
      return;
    }
    valid.forEach((booking) => list.append(renderBooking(booking, operator)));
    list.setAttribute("aria-busy", "false");
  }

  async function loadBookings(fallbackBooking = null) {
    const operation = invalidateCurrentList();
    const role = view;
    if (deadlineTimer) window.clearInterval(deadlineTimer);
    showSkeleton();
    const authorized = session && (role === "consumer" ? session.can_consumer === true : session.can_operator === true);
    const csrf = session && (role === "consumer" ? session.consumer_csrf : session.operator_csrf);
    if (!authorized || typeof csrf !== "string" || !csrf) {
      showEmpty("이 역할의 인증 세션이 없습니다", "모드 선택에서 해당 역할로 로그인한 뒤 다시 확인해 주세요.");
      setFeedback(role === "consumer"
        ? "인증된 소비자 역할이 없어 소비자 예약 목록을 표시할 수 없습니다."
        : "인증된 운영자 역할이 없어 운영자 예약 목록을 표시할 수 없습니다.", "error");
      return;
    }
    roleNote.textContent = view === "consumer"
      ? "인증된 소비자 계정에서 본인 예약만 조회합니다."
      : "인증된 운영자 계정에서 담당 숙소 예약만 조회합니다.";
    const controller = new AbortController();
    listController = controller;
    try {
      const result = await api(`/hs2/bookings/api/${role}`, {}, controller.signal);
      if (operation !== generation || view !== role) return;
      if (fallbackBooking && role === "consumer" &&
          !result.bookings.some((booking) => booking && booking.booking_id === fallbackBooking.booking_id)) {
        result.bookings.unshift(fallbackBooking);
      }
      renderBookings(result.bookings, role === "operator");
      setFeedback(role === "consumer" ? "소비자 본인의 최신 예약 현황입니다." : "운영자에게 배정된 최신 예약 현황입니다.", "ready");
      deadlineTimer = window.setInterval(() => refreshDeadlineLabels(), 1000);
    } catch (error) {
      if (error.name === "AbortError" || operation !== generation) return;
      if (fallbackBooking && role === "consumer" && validBooking(fallbackBooking)) {
        list.replaceChildren(renderBooking(fallbackBooking, false));
        const problem = document.createElement("p");
        problem.className = "action-hint";
        problem.textContent = "신청은 서버에서 접수되었습니다. 목록 연결을 확인한 뒤 다시 새로고침해 주세요.";
        list.append(problem);
      } else {
        showEmpty("예약 현황을 불러오지 못했습니다", error.message || "연결 상태를 확인해 주세요.");
      }
      list.setAttribute("aria-busy", "false");
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "retry-list";
      retry.textContent = "다시 불러오기";
      retry.addEventListener("click", loadBookings);
      list.append(retry);
      setFeedback(error.message || "예약 현황을 불러오지 못했습니다.", "error");
    } finally {
      if (operation === generation) listController = null;
    }
  }

  function refreshDeadlineLabels() {
    list.querySelectorAll("[data-deadline-for]").forEach((node) => {
      const card = node.closest("[data-booking-id]");
      if (!card) return;
      const deadline = Date.parse(node.dataset.deadlineAt);
      if (!Number.isFinite(deadline)) return;
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      node.textContent = `서버 기한까지 ${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
      if (seconds === 0 && !refreshedExpiredDeadlines.has(card.dataset.bookingId)) {
        refreshedExpiredDeadlines.add(card.dataset.bookingId);
        loadBookings();
      }
    });
  }

  function currentRoleStillValid(role, operation) {
    return operation === generation && role === view &&
      !!session && (role === "consumer" ? session.can_consumer === true : session.can_operator === true);
  }

  async function loadReceipt() {
    if (view !== "consumer" || !receiptId || !uuidPattern.test(receiptId) ||
        !session || session.can_consumer !== true || typeof session.consumer_csrf !== "string" || !session.consumer_csrf) {
      clearReceipt(view === "operator"
        ? "운영자 화면에서는 소비자 견적 확인서를 불러오지 않습니다."
        : "유효한 견적 확인서가 없거나 소비자 인증이 필요합니다. 본인 예약 현황은 아래에 표시됩니다.");
      return;
    }
    clearReceipt("발급된 견적과 현재 만료 시각을 서버에서 확인하고 있습니다.");
    const operation = generation;
    try {
      const result = await api(`/hs2/details/api/receipts/${encodeURIComponent(receiptId)}`);
      if (!currentRoleStillValid("consumer", operation)) return;
      if (!result.receipt || result.receipt.receipt_id !== receiptId) throw new Error("서버가 반환한 견적 확인서가 요청과 일치하지 않습니다.");
      renderReceipt(result.receipt);
      setFeedback("본인에게 발급된 유효한 견적 확인서입니다. 동의 후 예약 신청을 보낼 수 있습니다.", "ready");
    } catch (error) {
      if (operation !== generation) return;
      clearReceipt(error.message || "유효한 견적 확인서를 불러오지 못했습니다.");
      setFeedback(error.message || "견적 확인서를 불러오지 못했습니다. 상세 페이지에서 새 견적을 확인해 주세요.", "error");
    }
  }

  async function requestBooking() {
    if (requestInFlight || !currentReceipt || !ackInput.checked || view !== "consumer" ||
        !session || session.can_consumer !== true || typeof session.consumer_csrf !== "string" ||
        !quoteReceiptUsable(currentReceipt)) {
      setFeedback("유효한 소비자 세션·견적 확인서와 명시적 신청 동의가 필요합니다.", "error");
      if (currentReceipt && !quoteReceiptUsable(currentReceipt)) {
        clearReceipt("견적 확인서가 만료되었거나 유효하지 않습니다. 상세 페이지에서 새 견적을 확인해 주세요.");
      }
      return;
    }
    if (!requestKey) requestKey = crypto.randomUUID();
    const operation = generation;
    const role = view;
    requestInFlight = true;
    requestButton.disabled = true;
    ackInput.disabled = true;
    setFeedback("견적 조건을 확인해 예약 신청을 보내고 있습니다.", "loading");
    try {
      const result = await api("/hs2/bookings/api/request", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": session.consumer_csrf },
        body: JSON.stringify({ receipt_id: currentReceipt.receipt_id, request_id: requestKey, acknowledged: true })
      });
      if (!currentRoleStillValid(role, operation)) return;
      if (!validBooking(result.booking) || result.booking.status !== "pending_operator") {
        throw new Error("서버 응답의 예약 신청 정보를 검증할 수 없습니다.");
      }
      const accepted = result.booking;
      clearReceipt("이 견적 확인서는 신청에 사용되었습니다. 새 신청에는 새 견적 확인서가 필요합니다.");
      const empty = list.querySelector(".empty-state");
      if (empty) list.replaceChildren();
      const existing = list.querySelector(`[data-booking-id="${CSS.escape(accepted.booking_id)}"]`);
      if (existing) existing.remove();
      list.prepend(renderBooking(accepted, false));
      list.setAttribute("aria-busy", "false");
      setFeedback("서버가 예약 신청을 접수했습니다. 운영자 확인 대기 상태이며 아직 확정·결제가 아닙니다.", "ready");
      loadBookings(accepted);
    } catch (error) {
      if (operation !== generation || error.name === "AbortError") return;
      requestInFlight = false;
      if (error.status === 409 || ["QUOTE_SOURCE_CHANGED", "QUOTE_RECEIPT_EXPIRED", "QUOTE_RECEIPT_ALREADY_USED", "BOOKING_RETRY_CONFLICT"].includes(error.code)) {
        clearReceipt("견적 또는 신청 조건이 변경되었습니다. 상세 페이지에서 새 견적 확인서를 발급받아 주세요.");
        requestKey = null;
        await loadBookings();
      } else {
        // Keep requestKey for the exact same receipt, making an uncertain retry idempotent.
        ackInput.disabled = false;
        requestButton.disabled = !ackInput.checked;
        await loadBookings();
      }
      setFeedback(error.message || "신청 결과를 확인하지 못했습니다.", "error");
    } finally {
      if (operation === generation) {
        requestInFlight = false;
        if (currentReceipt) {
          ackInput.disabled = false;
          requestButton.disabled = !ackInput.checked;
        }
      }
    }
  }

  async function performAction(booking, action, operator) {
    const role = operator ? "operator" : "consumer";
    if (!validBooking(booking) || view !== role || pendingActions.has(booking.booking_id)) return;
    if (action === "confirm-payment" && !(session && session.payment_available === true)) return;
    const operation = generation;
    const csrf = operator ? session && session.operator_csrf : session && session.consumer_csrf;
    if (!currentRoleStillValid(role, operation) || typeof csrf !== "string" || !csrf) {
      setFeedback("선택한 역할의 인증 세션이 없어 작업을 진행할 수 없습니다.", "error");
      return;
    }
    pendingActions.add(booking.booking_id);
    const card = list.querySelector(`[data-booking-id="${CSS.escape(booking.booking_id)}"]`);
    if (card) card.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    setFeedback(action === "confirm-payment"
      ? "서버가 실제 결제 증빙을 확인하고 있습니다."
      : "최신 예약 revision으로 요청을 처리하고 있습니다.", "loading");
    try {
      await api(`/hs2/bookings/api/${role}/${encodeURIComponent(booking.booking_id)}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ action, revision: booking.revision })
      });
      if (!currentRoleStillValid(role, operation)) return;
      setFeedback("예약 상태가 서버에서 변경되었습니다. 최신 목록을 확인하고 있습니다.", "ready");
      await loadBookings();
    } catch (error) {
      if (operation !== generation || error.name === "AbortError") return;
      pendingActions.delete(booking.booking_id);
      if (error.status === 409 || ["BOOKING_REVISION_CHANGED", "BOOKING_STATE_CHANGED", "QUOTE_SOURCE_CHANGED", "PAYMENT_PROVIDER_UNAVAILABLE"].includes(error.code)) {
        list.replaceChildren();
        if (["QUOTE_SOURCE_CHANGED", "QUOTE_RECEIPT_EXPIRED"].includes(error.code)) {
          clearReceipt("예약 조건 또는 견적 확인서가 만료되었습니다. 상세 페이지에서 새 견적을 확인해 주세요.");
        }
        await loadBookings();
      } else {
        await loadBookings();
      }
      setFeedback(error.message || "예약 상태를 변경하지 못했습니다.", "error");
    }
  }

  async function initialize() {
    setRoleButtons();
    clearReceipt(view === "operator" ? "운영자 화면에서는 소비자 견적 확인서를 불러오지 않습니다." : undefined);
    try {
      const result = await api("/hs2/bookings/api/session");
      if (!result || typeof result.can_consumer !== "boolean" || typeof result.can_operator !== "boolean" ||
          typeof result.payment_available !== "boolean") throw new Error("인증 세션 응답을 확인할 수 없습니다.");
      session = result;
      paymentNote.textContent = session.payment_available
        ? "결제 동작은 현재 세션의 서버 증빙 제공자에 위임되며, 실제 결제·정책은 서버 확인 기준입니다."
        : "결제 제공자를 현재 사용할 수 없습니다. 결제 완료·확정으로 처리되지 않습니다.";
      await loadBookings();
      if (view === "consumer" && receiptId) await loadReceipt();
      else if (view === "consumer") clearReceipt("예약 목록은 본인 세션에서 확인됩니다. 견적 확인서는 상세 페이지에서 발급받아 주세요.");
    } catch (error) {
      session = null;
      showEmpty("세션 정보를 확인하지 못했습니다", "페이지를 새로고침한 뒤 모드 선택에서 인증 상태를 확인해 주세요.");
      list.setAttribute("aria-busy", "false");
      setFeedback(error.message || "인증 세션을 확인하지 못했습니다.", "error");
    }
  }

  ackInput.addEventListener("change", () => {
    requestButton.disabled = !ackInput.checked || !currentReceipt || requestInFlight ||
      !session || session.can_consumer !== true || !quoteReceiptUsable(currentReceipt);
  });
  requestButton.addEventListener("click", requestBooking);
  refreshButton.addEventListener("click", loadBookings);
  consumerButton.addEventListener("click", () => switchView("consumer"));
  operatorButton.addEventListener("click", () => switchView("operator"));
  window.addEventListener("pagehide", () => {
    generation += 1;
    if (listController) listController.abort();
    if (deadlineTimer) window.clearInterval(deadlineTimer);
  });

  initialize();
})();
