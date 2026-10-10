(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const feedback = $("#detail-feedback");
  const feedbackCopy = feedback.querySelector(".feedback-copy");
  const itemSection = $("#detail-content");
  const backLink = $("#back-to-search");
  const form = $("#quote-form");
  const checkInInput = $("#quote-check-in");
  const checkOutInput = $("#quote-check-out");
  const guestsInput = $("#quote-guests");
  const quoteButton = $("#request-quote");
  const totalNode = $("#quote-total");
  const termsNode = $("#quote-terms");
  const linesNode = $("#quote-lines");
  const ackWrap = $("#quote-ack-wrap");
  const ackInput = $("#quote-ack");
  const confirmButton = $("#confirm-quote");
  const receiptPanel = $("#quote-receipt");
  const receiptExpiry = $("#receipt-expiry");
  const countdownNode = $("#receipt-countdown");
  const loginPrompt = $("#login-prompt");
  const loginLink = $("#consumer-login-link");
  const params = new URLSearchParams(window.location.search);
  const publicId = (params.get("public_id") || "").trim();
  const safeId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(publicId);
  const receiptStorageKey = "hs2_detail_quote_receipt";
  let item = null;
  let sessionInfo = null;
  let currentQuote = null;
  let activeQuoteController = null;
  let activeConfirmController = null;
  let sequence = 0;
  let requestId = null;
  let requestIdQuoteKey = "";
  let receiptTimer = null;
  let currentReceipt = null;
  let pageIdentity = publicId;

  function setFeedback(message, state) {
    feedbackCopy.textContent = message;
    feedback.dataset.state = state;
  }

  function validDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const parts = value.split("-").map(Number);
    const date = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
    return date.getUTCFullYear() === parts[0] && date.getUTCMonth() === parts[1] - 1 && date.getUTCDate() === parts[2];
  }

  function selection() {
    const guests = Number(guestsInput.value);
    return { check_in: checkInInput.value, check_out: checkOutInput.value, guests };
  }

  function usableSelection(value = selection()) {
    return validDate(value.check_in) && validDate(value.check_out) &&
      value.check_out > value.check_in && Number.isSafeInteger(value.guests) && value.guests >= 1 && value.guests <= 100;
  }

  function selectionKey(value) {
    return `${value.check_in}|${value.check_out}|${value.guests}`;
  }

  function money(value) {
    return `${new Intl.NumberFormat("ko-KR").format(value)}원`;
  }

  function displayTitle(raw) {
    if (typeof raw !== "string" || !raw.trim()) return "공개 숙소 정보";
    return raw.trim().slice(0, 120);
  }

  function safeReturn(value) {
    if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return null;
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || url.pathname !== "/hs2/search/") return null;
      url.hash = "";
      return `${url.pathname}${url.search}`;
    } catch (_) {
      return null;
    }
  }

  function returnHref() {
    const restored = safeReturn(params.get("restoredReturn"));
    const url = restored ? new URL(restored, window.location.origin) : new URL("/hs2/search/", window.location.origin);
    const input = selection();
    if (validDate(input.check_in)) url.searchParams.set("check_in", input.check_in);
    if (validDate(input.check_out)) url.searchParams.set("check_out", input.check_out);
    if (Number.isSafeInteger(input.guests) && input.guests > 0) url.searchParams.set("guests", String(input.guests));
    return `${url.pathname}${url.search}`;
  }

  function updateReturnLinks() {
    const href = returnHref();
    backLink.href = href;
    const loginUrl = new URL("/hs2/mode", window.location.origin);
    loginUrl.searchParams.set("return", href);
    loginLink.href = `${loginUrl.pathname}${loginUrl.search}`;
  }

  function safePublicSummary(summary) {
    return summary && typeof summary === "object" && !Array.isArray(summary) ? summary : {};
  }

  function factText(container, value) {
    container.textContent = value;
  }

  function renderItem(payload) {
    const data = payload && payload.item;
    if (!data || typeof data !== "object" || data.public_id !== publicId || data.layer !== "stay") {
      throw new Error("공개 숙소 상세 정보를 확인할 수 없습니다.");
    }
    item = data;
    const summary = safePublicSummary(data.summary);
    const nonLodging = data.stay_kind === "non_lodging";
    $("#stay-type").textContent = nonLodging ? "비숙박형 단기임대" : "숙박형 단기임대";
    $("#detail-title").textContent = displayTitle(data.title);
    $("#detail-summary-copy").textContent = nonLodging
      ? "운영자가 공개한 비숙박형 단기임대 요약입니다. 숙박 예약 상품이 아닙니다."
      : "운영자가 공개에 동의한 숙박 요약만 표시합니다. 정확한 이름·주소와 등록 사진은 공개하지 않습니다.";
    const guests = summary.guests;
    factText($("#capacity"), Number.isSafeInteger(guests) && guests > 0 ? `${guests}명` : "미공개");
    const minStay = summary.min_stay;
    const minimum = Number.isSafeInteger(minStay) && minStay > 0 ? minStay : (nonLodging ? 7 : 1);
    factText($("#minimum-stay"), nonLodging ? `${minimum}일부터` : `${minimum}박부터`);
    const rooms = summary.rooms;
    factText($("#rooms-value"), Number.isSafeInteger(rooms) && rooms >= 0 ? (rooms === 0 ? "원룸·스튜디오" : `${rooms}개`) : "미공개");
    const area = summary.area_m2;
    factText($("#area-value"), typeof area === "number" && Number.isFinite(area) && area > 0 ? `${area.toLocaleString("ko-KR")}㎡` : "미공개");
    factText($("#instant-value"), typeof summary.instant === "boolean" ? (summary.instant ? "가능" : "해당 없음") : "미공개");
    factText($("#discount-value"), typeof summary.discount === "boolean" ? (summary.discount ? "등록됨" : "해당 없음") : "미공개");
    const optionNames = { wifi: "와이파이", kitchen: "주방", parking: "주차", washer: "세탁기" };
    const options = Array.isArray(summary.options)
      ? summary.options.filter((entry) => typeof entry === "string" && entry.length <= 40)
        .slice(0, 12).map((entry) => optionNames[entry] || entry)
      : [];
    factText($("#options-value"), options.length ? options.join(" · ") : "공개된 정보 없음");
    const point = data.point;
    factText($("#location-copy"), point && point.precision === "approx"
      ? "등록자가 공개한 대략 위치(약 500m)를 안내합니다. 정확한 주소와 자동 건물 정보는 표시하지 않습니다."
      : "정확한 위치 정보는 공개되지 않았습니다. 주소·지도 핀·자동 건물 정보는 표시하지 않습니다.");
    const defaultIn = params.get("check_in") || "";
    const defaultOut = params.get("check_out") || "";
    const defaultGuests = Number(params.get("guests"));
    if (validDate(defaultIn)) checkInInput.value = defaultIn;
    if (validDate(defaultOut)) checkOutInput.value = defaultOut;
    if (Number.isSafeInteger(defaultGuests) && defaultGuests > 0 && defaultGuests <= 100) guestsInput.value = String(defaultGuests);
    checkOutInput.min = checkInInput.value || "";
    checkInInput.max = checkOutInput.value || "";
    const summaryGuests = Number.isSafeInteger(guests) && guests > 0 ? guests : 100;
    guestsInput.max = String(Math.max(1, Math.min(summaryGuests, 100)));
    updateReturnLinks();
    itemSection.hidden = false;
  }

  function clearReceiptStorage() {
    try { window.sessionStorage.removeItem(receiptStorageKey); } catch (_) { /* Storage can be disabled. */ }
  }

  function clearReceipt() {
    if (receiptTimer) window.clearInterval(receiptTimer);
    receiptTimer = null;
    currentReceipt = null;
    receiptPanel.hidden = true;
    ackWrap.hidden = !currentQuote;
    clearReceiptStorage();
  }

  function clearQuote(message = "유효한 견적을 조회하면 기간별 금액을 표시합니다.") {
    currentQuote = null;
    linesNode.replaceChildren();
    totalNode.textContent = "견적 전";
    termsNode.textContent = message;
    ackInput.checked = false;
    ackWrap.hidden = true;
    confirmButton.disabled = true;
    quoteButton.disabled = false;
  }

  function cancelPending() {
    sequence += 1;
    if (activeQuoteController) activeQuoteController.abort();
    if (activeConfirmController) activeConfirmController.abort();
    activeQuoteController = null;
    activeConfirmController = null;
  }

  function invalidateForInput() {
    cancelPending();
    currentQuote = null;
    requestId = null;
    requestIdQuoteKey = "";
    clearReceipt();
    clearQuote();
    updateReturnLinks();
  }

  function explainError(code, status) {
    const messages = {
      PUBLIC_LISTING_NOT_FOUND: "이 공개 숙소를 찾을 수 없거나 더 이상 공개되지 않습니다.",
      QUOTE_SOURCE_CHANGED: "가격 또는 공개 정보가 변경되어 이전 견적을 폐기했습니다. 조건을 확인한 뒤 새로 조회해 주세요.",
      QUOTE_RECEIPT_EXPIRED: "견적 조건 확인서의 유효 시간이 끝났습니다. 기간 총액을 다시 조회해 주세요.",
      QUOTE_SOURCE_WITHDRAWN: "공개가 종료되어 이전 견적을 사용할 수 없습니다.",
      VERIFIED_CONSUMER_REQUIRED: "인증된 소비자 로그인이 필요합니다.",
      ACTIVE_CONSUMER_REQUIRED: "현재 활성화된 소비자 계정을 확인할 수 없습니다.",
      CSRF_REQUIRED: "보안 확인이 만료되었습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.",
      GUEST_CAPACITY_UNAVAILABLE: "인원 조건을 확인할 수 없습니다. 공개 수용 인원 또는 운영자 정보를 확인해 주세요.",
      DATES_AND_GUESTS_REQUIRED: "유효한 입실일, 퇴실일과 인원 수를 입력해 주세요.",
      QUOTE_RETRY_CONFLICT: "요청 내용이 달라 이전 확인 요청을 재사용할 수 없습니다. 새 견적을 조회해 주세요.",
      DETAIL_RATE_LIMIT: "요청이 잠시 많습니다. 잠시 후 다시 시도해 주세요."
    };
    if (messages[code]) return messages[code];
    if (status === 404) return "요청한 공개 정보를 찾을 수 없습니다.";
    if (status === 409) return "공개 정보가 변경되었거나 확인서가 만료되었습니다. 가격을 새로 조회해 주세요.";
    if (status === 403) return "로그인 또는 보안 확인이 필요합니다.";
    if (status === 429) return "요청 횟수가 많습니다. 잠시 후 다시 시도해 주세요.";
    return "요청을 완료하지 못했습니다. 조건을 확인한 뒤 다시 시도해 주세요.";
  }

  async function api(path, options = {}, signal) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, signal });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* Non-JSON errors are handled uniformly. */ }
    if (!response.ok || !payload || payload.ok !== true) {
      const error = new Error(explainError(payload && payload.code, response.status));
      error.code = payload && payload.code;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function quoteIsUsable(quote, value) {
    if (!quote || quote.public_id !== publicId || quote.check_in !== value.check_in || quote.check_out !== value.check_out ||
        !Number.isSafeInteger(quote.total_krw) || quote.total_krw <= 0 ||
        quote.currency !== "KRW" || quote.complete !== true || quote.public_price_allowed !== true ||
        quote.fees_included !== true || quote.deposit_included !== false || quote.booking_confirmed !== false ||
        !/^[0-9a-f]{64}$/.test(quote.source_version) || !Array.isArray(quote.lines) || quote.lines.length < 1) return false;
    const validLines = quote.lines.every((line) => line && typeof line.start === "string" && typeof line.end === "string" &&
      validDate(line.start) && validDate(line.end) && line.end > line.start &&
      ["night", "week", "month"].includes(line.unit) && Number.isSafeInteger(line.amount_krw) && line.amount_krw > 0);
    if (!validLines) return false;
    const total = quote.lines.reduce((sum, line) => sum + line.amount_krw, 0);
    return Number.isSafeInteger(total) && total === quote.total_krw;
  }

  function unitLabel(unit) {
    return unit === "night" ? "숙박 기간" : unit === "week" ? "주 단위 기간" : "입실 기념일 기준 월 단위";
  }

  function renderQuote(quote) {
    linesNode.replaceChildren();
    for (const line of quote.lines) {
      const row = document.createElement("li");
      row.className = "quote-line";
      const period = document.createElement("span");
      period.textContent = `${line.start} – ${line.end} · ${unitLabel(line.unit)}`;
      const amount = document.createElement("strong");
      amount.textContent = money(line.amount_krw);
      row.append(period, amount);
      linesNode.append(row);
    }
    totalNode.textContent = money(quote.total_krw);
    const version = typeof quote.terms_version === "string" && quote.terms_version.length <= 80 ? quote.terms_version : "확인됨";
    termsNode.textContent = `운영자 확인 총액 · 필수 비용 포함 · 정책 버전 ${version}. 주 단위는 7일, 월 단위는 입실일 기념일 기준입니다. 보증금은 포함되지 않았으며 결제 전 확인이 필요합니다.`;
    currentQuote = { quote, selection: selection(), sequence };
    ackInput.checked = false;
    ackWrap.hidden = false;
    receiptPanel.hidden = true;
    confirmButton.disabled = true;
  }

  function resetRetryKeyForQuote() {
    requestId = null;
    requestIdQuoteKey = "";
  }

  async function getQuote(event) {
    event.preventDefault();
    const value = selection();
    if (!usableSelection(value)) {
      invalidateForInput();
      setFeedback("입실일·퇴실일과 1명 이상의 인원을 정확히 입력해 주세요.", "error");
      return;
    }
    cancelPending();
    const operation = sequence;
    if (activeQuoteController) activeQuoteController.abort();
    if (activeConfirmController) activeConfirmController.abort();
    clearReceipt();
    clearQuote("현재 기간 총액을 확인하고 있습니다.");
    resetRetryKeyForQuote();
    quoteButton.disabled = true;
    setFeedback("운영자가 공개한 현재 기간 가격을 확인하고 있습니다.", "loading");
    const controller = new AbortController();
    activeQuoteController = controller;
    const query = new URLSearchParams({ check_in: value.check_in, check_out: value.check_out, guests: String(value.guests) });
    try {
      const result = await api(`/hs2/details/api/items/${encodeURIComponent(publicId)}/quote?${query}`, {}, controller.signal);
      if (operation !== sequence || pageIdentity !== publicId) return;
      if (result.guests !== value.guests || result.booking_confirmed !== false || result.inventory_held !== false ||
          !quoteIsUsable(result.quote, value)) throw new Error("서버에서 받은 견적을 안전하게 확인하지 못했습니다. 다시 조회해 주세요.");
      renderQuote(result.quote);
      setFeedback("현재 공개 source 기준의 기간 총액입니다. 입력을 바꾸면 이 견적은 즉시 폐기됩니다.", "ready");
    } catch (error) {
      if (error.name === "AbortError" || operation !== sequence) return;
      clearQuote(error.message);
      if (error.code === "QUOTE_SOURCE_CHANGED" || error.code === "PUBLIC_LISTING_NOT_FOUND") clearReceipt();
      setFeedback(error.message || "기간 총액을 확인하지 못했습니다.", "error");
    } finally {
      if (operation === sequence) {
        activeQuoteController = null;
        quoteButton.disabled = false;
      }
    }
  }

  function expirationDate(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date : null;
  }

  function renderReceipt(receipt) {
    if (!receipt || receipt.public_id !== publicId || receipt.booking_confirmed !== false || receipt.inventory_held !== false ||
        !/^[0-9a-f]{64}$/.test(receipt.source_version || "") ||
        !/^[0-9a-f-]{36}$/i.test(receipt.receipt_id || "") ||
        !Number.isSafeInteger(receipt.source_revision) || receipt.source_revision < 1 ||
        !Number.isSafeInteger(receipt.guests) || receipt.guests < 1 || !expirationDate(receipt.expires_at) ||
        !quoteIsUsable(receipt.quote, { check_in: receipt.quote && receipt.quote.check_in, check_out: receipt.quote && receipt.quote.check_out }) ||
        receipt.quote.source_version !== receipt.source_version || receipt.quote.guests !== undefined && receipt.quote.guests !== receipt.guests) {
      throw new Error("견적 확인서의 발급 정보를 검증하지 못했습니다.");
    }
    const expires = expirationDate(receipt.expires_at);
    if (expires.getTime() <= Date.now()) throw new Error(explainError("QUOTE_RECEIPT_EXPIRED"));
    currentReceipt = receipt;
    renderQuote(receipt.quote);
    currentQuote = null;
    ackWrap.hidden = true;
    confirmButton.disabled = true;
    termsNode.textContent = "서버가 발급한 기간별 총액 및 정책 버전입니다. 이 확인서는 예약·재고 확보·결제가 아닙니다.";
    receiptExpiry.textContent = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"
    }).format(expires);
    receiptPanel.hidden = false;
    receiptTimer = window.setInterval(() => {
      if (!currentReceipt) return;
      const remaining = Math.max(0, Math.ceil((expires.getTime() - Date.now()) / 1000));
      if (remaining <= 0) {
        clearReceipt();
        clearQuote("견적 조건 확인서가 만료되었습니다. 기간 총액을 다시 조회해 주세요.");
        setFeedback("견적 확인서가 만료되었습니다. 새 견적을 조회해 주세요.", "error");
        return;
      }
      countdownNode.textContent = `남은 시간 ${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;
    }, 1000);
    countdownNode.textContent = "남은 시간 10분";
    receiptPanel.hidden = false;
    try { window.sessionStorage.setItem(receiptStorageKey, receipt.receipt_id); } catch (_) { /* Receipt remains on screen. */ }
  }

  async function confirmQuote() {
    if (!currentQuote || !sessionInfo || sessionInfo.can_confirm_quote !== true ||
        typeof sessionInfo.csrf_token !== "string" || !sessionInfo.csrf_token ||
        !ackInput.checked || !usableSelection() ||
        selectionKey(selection()) !== selectionKey(currentQuote.selection) ||
        currentQuote.sequence !== sequence || !quoteIsUsable(currentQuote.quote, currentQuote.selection)) {
      setFeedback("현재 견적·인증 소비자 세션·확인 동의가 모두 필요합니다. 새 견적을 조회해 주세요.", "error");
      return;
    }
    const quote = currentQuote.quote;
    const bodyKey = selectionKey(currentQuote.selection) + "|" + quote.source_version;
    if (!requestId || requestIdQuoteKey !== bodyKey) {
      requestId = crypto.randomUUID();
      requestIdQuoteKey = bodyKey;
    }
    const operation = sequence;
    activeConfirmController = new AbortController();
    confirmButton.disabled = true;
    setFeedback("현재 source를 다시 확인해 견적 조건 확인서를 요청하고 있습니다.", "loading");
    const body = {
      check_in: currentQuote.selection.check_in,
      check_out: currentQuote.selection.check_out,
      guests: currentQuote.selection.guests,
      expected_source_version: quote.source_version,
      acknowledged: true,
      request_id: requestId
    };
    try {
      const result = await api(`/hs2/details/api/items/${encodeURIComponent(publicId)}/confirm-quote`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": sessionInfo.csrf_token },
        body: JSON.stringify(body)
      }, activeConfirmController.signal);
      if (operation !== sequence || pageIdentity !== publicId) return;
      const receipt = result.receipt;
      if (!receipt || receipt.guests !== body.guests || receipt.source_version !== quote.source_version ||
          receipt.quote.check_in !== body.check_in || receipt.quote.check_out !== body.check_out) {
        throw new Error("발급된 견적 확인서가 현재 입력과 일치하지 않습니다.");
      }
      renderReceipt(receipt);
      resetRetryKeyForQuote();
      setFeedback("견적 조건 확인서가 발급되었습니다. 예약·재고 확보·결제는 진행되지 않았습니다.", "ready");
    } catch (error) {
      if (operation !== sequence || error.name === "AbortError") return;
      if (error.status >= 400 && error.status < 500) {
        resetRetryKeyForQuote();
        if (["QUOTE_SOURCE_CHANGED", "QUOTE_RECEIPT_EXPIRED", "PUBLIC_LISTING_NOT_FOUND"].includes(error.code)) {
          cancelPending();
          clearQuote(error.message);
          clearReceipt();
        }
      } else {
        // A network/5xx outcome can be uncertain. Keep this request id so an explicit retry is idempotent.
        confirmButton.disabled = false;
      }
      setFeedback(error.message || "견적 조건 확인서를 발급하지 못했습니다.", "error");
    } finally {
      if (operation === sequence) activeConfirmController = null;
    }
  }

  async function restoreReceipt(receiptId) {
    if (!receiptId || !/^[0-9a-f-]{36}$/i.test(receiptId)) return;
    const operation = sequence;
    try {
      const result = await api(`/hs2/details/api/receipts/${encodeURIComponent(receiptId)}`);
      if (operation !== sequence || pageIdentity !== publicId) return;
      renderReceipt(result.receipt);
      setFeedback("본인에게 발급된 현재 견적 조건 확인서를 불러왔습니다. 예약·재고 확보·결제는 아닙니다.", "ready");
    } catch (error) {
      clearReceipt();
      if (["QUOTE_SOURCE_CHANGED", "QUOTE_RECEIPT_EXPIRED", "QUOTE_RECEIPT_NOT_FOUND"].includes(error.code)) {
        try { window.history.replaceState(null, "", `${window.location.pathname}?${(() => {
          const next = new URLSearchParams(window.location.search);
          next.delete("receipt_id");
          return next.toString();
        })()}`); } catch (_) { /* Keep page state if history is unavailable. */ }
      }
      setFeedback(error.message || "저장된 확인서를 불러오지 못했습니다.", "error");
    }
  }

  async function initialize() {
    if (!publicId || !safeId) {
      setFeedback("숙소 식별 정보가 없거나 올바르지 않습니다. 검색 결과에서 숙소를 다시 선택해 주세요.", "error");
      return;
    }
    const operation = sequence;
    setFeedback("공개된 숙소 정보를 확인하고 있습니다.", "loading");
    try {
      const [detailResult, sessionResult] = await Promise.allSettled([
        api(`/hs2/details/api/items/${encodeURIComponent(publicId)}`),
        api("/hs2/details/api/session")
      ]);
      if (operation !== sequence) return;
      if (detailResult.status !== "fulfilled") throw detailResult.reason;
      renderItem(detailResult.value);
      sessionInfo = sessionResult.status === "fulfilled" &&
        typeof sessionResult.value.can_confirm_quote === "boolean" ? sessionResult.value : null;
      const canConfirm = !!sessionInfo && sessionInfo.can_confirm_quote === true &&
        typeof sessionInfo.csrf_token === "string" && !!sessionInfo.csrf_token;
      loginPrompt.hidden = canConfirm;
      if (!canConfirm) {
        setFeedback("공개 숙소 정보를 불러왔습니다. 확인서 발급은 인증된 소비자 로그인이 필요합니다.", "ready");
      } else {
        setFeedback("공개 숙소 정보를 불러왔습니다. 기간 총액을 확인할 수 있습니다.", "ready");
      }
      const queryReceipt = params.get("receipt_id");
      let stored = null;
      try { stored = window.sessionStorage.getItem(receiptStorageKey); } catch (_) { /* Optional. */ }
      await restoreReceipt(queryReceipt || stored);
    } catch (error) {
      if (operation !== sequence) return;
      setFeedback(error.message || "공개 숙소 정보를 불러오지 못했습니다.", "error");
      itemSection.hidden = true;
    }
  }

  [checkInInput, checkOutInput, guestsInput].forEach((input) => input.addEventListener("input", () => {
    checkOutInput.min = checkInInput.value || "";
    checkInInput.max = checkOutInput.value || "";
    invalidateForInput();
  }));
  form.addEventListener("submit", getQuote);
  ackInput.addEventListener("change", () => {
    confirmButton.disabled = !ackInput.checked || !currentQuote ||
      currentQuote.sequence !== sequence || !sessionInfo || sessionInfo.can_confirm_quote !== true;
  });
  confirmButton.addEventListener("click", confirmQuote);
  backLink.addEventListener("click", updateReturnLinks);
  window.addEventListener("popstate", () => {
    const nextParams = new URLSearchParams(window.location.search);
    const nextId = (nextParams.get("public_id") || "").trim();
    if (nextId !== pageIdentity) {
      cancelPending();
      pageIdentity = nextId;
      window.location.reload();
      return;
    }
    updateReturnLinks();
  });

  updateReturnLinks();
  if (publicId && safeId) initialize();
  else setFeedback("숙소 식별 정보가 없거나 올바르지 않습니다. 검색 결과에서 숙소를 다시 선택해 주세요.", "error");
})();
