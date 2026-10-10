(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const feedback = $("#finance-feedback");
  const termsNode = $("#finance-terms");
  const previewNode = $("#finance-preview");
  const ack = $("#finance-ack");
  const ackCopy = $("#finance-ack-copy");
  const createButton = $("#create-financial-contract");
  const list = $("#finance-list");
  const consumerButton = $("#finance-consumer-view");
  const operatorButton = $("#finance-operator-view");
  const roleNote = $("#finance-role-note");
  const providerState = $("#provider-state");
  const params = new URLSearchParams(window.location.search);
  const bookingId = (params.get("booking_id") || "").trim();
  const selectedId = (params.get("contract_id") || "").trim();
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  const labels = {
    awaiting_payment: "결제 대기 · 미실행",
    captured: "결제 증빙 확인",
    late_payment_review: "기한 외 결제 검토",
    refund_review: "환불 검토 요청"
  };
  const eventLabels = {
    capture: "결제 증빙 수신 · 서버 기록",
    late_capture: "기한 외 결제 증빙 · 검토 필요",
    refund_review: "환불 검토 요청 · 미실행",
    deposit_review: "보증금 반환 검토 · 미실행",
    payout_review: "호스트 정산 검토 · 미실행"
  };
  let session = null;
  let view = params.get("view") === "operator" ? "operator" : "consumer";
  let generation = 0;
  let controller = null;
  let createKey = null;
  let busy = false;
  let quotePreview = null;
  const pending = new Set();

  function say(message, state = "ready") {
    feedback.textContent = message;
    feedback.dataset.state = state;
  }

  function validDate(value) {
    if (typeof value !== "string" || !datePattern.test(value)) return false;
    const [y, m, d] = value.split("-").map(Number);
    const parsed = new Date(Date.UTC(y, m - 1, d));
    return parsed.getUTCFullYear() === y && parsed.getUTCMonth() === m - 1 && parsed.getUTCDate() === d;
  }

  function won(value, currency = "KRW") {
    if (!Number.isSafeInteger(value) || value < 0 || typeof currency !== "string") return "금액 확인 필요";
    try { return new Intl.NumberFormat("ko-KR", { style: "currency", currency }).format(value); }
    catch (_) { return `${new Intl.NumberFormat("ko-KR").format(value)} ${currency}`; }
  }

  function range(start, end) {
    return validDate(start) && validDate(end) && end > start ? `${start} – ${end}` : "날짜 확인 필요";
  }

  function errorText(code, status) {
    const messages = {
      VERIFIED_CONSUMER_REQUIRED: "인증된 소비자 로그인이 필요합니다.",
      ACTIVE_CONSUMER_REQUIRED: "활성화된 소비자 계정을 확인할 수 없습니다.",
      APPROVED_BUSINESS_REQUIRED: "승인된 운영자 계정이 필요합니다.",
      ACTIVE_MEMBER_REQUIRED: "활성화된 운영자 계정을 확인할 수 없습니다.",
      OPERATOR_CONTEXT_REQUIRED: "운영자 계정을 확인할 수 없습니다.",
      CSRF_REQUIRED: "보안 확인이 만료되었습니다. 새로고침 후 다시 시도해 주세요.",
      FINANCIAL_CONTRACT_NOT_FOUND: "본인 계정에서 확인할 수 있는 금융 계약이 없습니다.",
      FINANCIAL_QUOTE_NOT_FOUND: "이 예약의 금융 조건을 찾을 수 없습니다. 예약 현황에서 다시 확인해 주세요.",
      FINANCIAL_POLICY_UNAVAILABLE: "예약에 적용할 검토 완료 금융 정책을 확인할 수 없습니다.",
      FINANCIAL_TERMS_UNAVAILABLE: "금융 조건을 구성할 수 없어 요청을 진행할 수 없습니다.",
      FINANCIAL_ACK_REQUIRED: "금융 조건 안내를 확인하고 동의해 주세요.",
      FINANCIAL_TERMS_CHANGED: "금융 조건이 변경되었습니다. 최신 서버 조건을 다시 확인하고 새로 동의해 주세요.",
      REVIEWED_FINANCIAL_POLICY_REQUIRED: "이 예약에 적용할 검토 완료 금융 조건이 아직 구성되지 않았습니다.",
      REVIEWED_PG_COST_REQUIRED: "결제대행(PG) 처리 비용을 검토된 정수 금액으로 확인할 수 없어 금융 조건을 제공할 수 없습니다. 비용이 확인되기 전에는 요청할 수 없습니다.",
      BOOKING_STATE_CHANGED: "현재 예약 상태에서는 금융 조건을 요청할 수 없습니다. 예약 상태를 새로 확인해 주세요.",
      BOOKING_DEADLINE_EXPIRED: "예약 신청 기한이 지나 금융 조건을 요청할 수 없습니다.",
      FINANCIAL_RETRY_CONFLICT: "같은 요청 키가 다른 예약에 사용되었습니다. 새로고침한 뒤 조건을 다시 확인해 주세요.",
      VERIFIED_PAYMENT_REQUIRED: "서버에서 확인한 결제 증빙이 없어 환불 검토를 요청할 수 없습니다.",
      POST_CHECKIN_MANUAL_REVIEW_REQUIRED: "체크인 이후 취소는 별도 수동 검토가 필요합니다.",
      SETTLEMENT_REVIEW_NOT_ELIGIBLE: "현재 서버 기록에서는 보증금·정산 검토 요청 대상이 아닙니다.",
      LIVE_SETTLEMENT_NOT_APPROVED: "실제 정산 실행은 승인되지 않았습니다. 검토 기록만 제공됩니다.",
      LIVE_PAYMENT_NOT_APPROVED: "실제 결제 실행은 승인되지 않았습니다.",
      FINANCIAL_RATE_LIMIT: "요청이 잠시 많습니다. 잠시 후 다시 시도해 주세요."
    };
    if (messages[code]) return messages[code];
    if (status === 404) return "요청한 금융 기록을 찾을 수 없습니다.";
    if (status === 409) return "금융 상태가 변경되었습니다. 최신 서버 기록을 불러와 확인해 주세요.";
    if (status === 403) return "선택한 역할의 인증 세션을 확인할 수 없습니다.";
    if (status === 429) return "요청이 잠시 많습니다. 잠시 후 다시 시도해 주세요.";
    return "요청을 완료하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.";
  }

  async function api(path, options = {}, signal) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, signal });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* Non-JSON errors use a consistent message. */ }
    if (!response.ok || !payload || payload.ok !== true) {
      const error = new Error(errorText(payload && payload.code, response.status));
      error.code = payload && payload.code;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function authorized(role = view) {
    const allowed = role === "consumer" ? session && session.can_consumer : session && session.can_operator;
    const csrf = role === "consumer" ? session && session.consumer_csrf : session && session.operator_csrf;
    return allowed === true && typeof csrf === "string" && csrf.length > 0;
  }

  function validContract(c) {
    if (!c || !uuid.test(c.contract_id || "") || !uuid.test(c.booking_id || "") ||
        !["awaiting_payment", "captured", "late_payment_review", "refund_review"].includes(c.status) ||
        typeof c.sandbox !== "boolean" || c.actual_money_executed !== false ||
        typeof c.payment_verified !== "boolean" || typeof c.booking_confirmed !== "boolean" ||
        typeof c.booking_cancelled !== "boolean" || !validDate(c.check_in) || !validDate(c.check_out) ||
        c.check_out <= c.check_in || !validTerms(c.terms) ||
        !Array.isArray(c.events) || !c.events.every((e) => e && typeof e.kind === "string" &&
          Number.isSafeInteger(e.amount_krw) && e.amount_krw > 0 && typeof e.at === "string")) return false;
    return true;
  }

  function validTerms(t) {
    if (!t || typeof t !== "object" ||
        !["stay_krw", "deposit_krw", "payable_krw", "platform_fee_krw", "platform_vat_krw", "pg_processing_krw", "host_payout_krw"]
          .every((key) => Number.isSafeInteger(t[key]) && t[key] >= 0) ||
        t.payable_krw <= 0 || typeof t.currency !== "string" || !t.currency ||
        !t.policy || typeof t.policy !== "object") return false;
    const deductions = t.platform_fee_krw + t.platform_vat_krw + t.pg_processing_krw;
    return Number.isSafeInteger(deductions) &&
      t.host_payout_krw === t.stay_krw - deductions &&
      t.host_payout_krw >= 0;
  }

  function setSwitch() {
    consumerButton.setAttribute("aria-pressed", String(view === "consumer"));
    operatorButton.setAttribute("aria-pressed", String(view === "operator"));
    roleNote.textContent = view === "consumer"
      ? "인증된 소비자 계정의 본인 금융 기록만 조회합니다."
      : "인증된 운영자 계정에 배정된 금융 기록만 조회합니다.";
    if (view === "operator") ackCopy.textContent = "검토할 금융 기록의 서버 금액과 정책을 확인했습니다. 요청은 실제 보증금 반환이나 송금 실행이 아닙니다.";
  }

  function current(operation, role) {
    return operation === generation && role === view && authorized(role);
  }

  function invalidate() {
    generation += 1;
    if (controller) controller.abort();
    controller = null;
    pending.clear();
    return generation;
  }

  function updateUrl() {
    const url = new URL(window.location.href);
    if (view === "consumer") url.searchParams.delete("view");
    else url.searchParams.set("view", "operator");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function setSkeleton() {
    list.replaceChildren();
    for (let i = 0; i < 2; i += 1) {
      const skeleton = document.createElement("div");
      skeleton.className = "skeleton";
      list.append(skeleton);
    }
    list.setAttribute("aria-busy", "true");
  }

  function empty(title, copy) {
    list.replaceChildren();
    const box = document.createElement("div");
    box.className = "empty-state";
    const heading = document.createElement("strong");
    heading.textContent = title;
    const text = document.createElement("p");
    text.textContent = copy;
    box.append(heading, text);
    list.append(box);
    list.setAttribute("aria-busy", "false");
  }

  function textElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function renderTerms(target, t) {
    const grid = document.createElement("dl");
    grid.className = "terms-grid";
    const rows = [
      ["숙박 금액", t.stay_krw],
      ["보증금", t.deposit_krw],
      ["플랫폼 수수료", t.platform_fee_krw],
      ["플랫폼 부가세", t.platform_vat_krw],
      ["결제대행(PG) 처리 비용", t.pg_processing_krw],
      ["호스트 지급 예정액", t.host_payout_krw]
    ];
    rows.forEach(([label, amount]) => {
      const term = document.createElement("div");
      term.className = "term";
      term.append(textElement("dt", "", label), textElement("dd", "", won(amount, t.currency)));
      grid.append(term);
    });
    const total = document.createElement("div");
    total.className = "terms-total";
    total.append(textElement("span", "", "결제 예정 총액 (서버 기록)"),
      textElement("strong", "", won(t.payable_krw, t.currency)));
    const note = textElement("p", "policy-note",
      `취소·보증금·정산 정책: ${JSON.stringify(t.policy)} · 조건은 서버 검토값입니다. 실제 결제·환불·송금은 실행되지 않습니다.`);
    target.replaceChildren(grid, total, note);
  }

  function showTerms(c) {
    const t = c.terms;
    renderTerms(termsNode, t);
    ackCopy.textContent = "표시된 서버 검토 금액과 취소·보증금·정산 정책을 확인했습니다. 동의는 검토 요청을 위한 것이며 실제 결제·환불·송금 동의가 아닙니다.";
    ack.disabled = !authorized(view);
    if (view === "operator") ackCopy.textContent = "표시된 서버 검토 금액과 반환·정산 기준일을 확인했습니다. 요청은 실제 보증금 반환이나 송금 실행이 아닙니다.";
    createButton.disabled = true;
    createButton.textContent = "금융 조건 요청";
  }

  function validQuotePreview(value) {
    return !!value && value.booking_id === bookingId && uuid.test(value.booking_id || "") &&
      typeof value.terms_sha256 === "string" && /^[a-f0-9]{64}$/i.test(value.terms_sha256) &&
      typeof value.sandbox === "boolean" && validTerms(value.terms);
  }

  function clearQuote(message, clearAcknowledgment = true) {
    quotePreview = null;
    previewNode.textContent = message;
    previewNode.setAttribute("aria-busy", "false");
    if (clearAcknowledgment) ack.checked = false;
    updateCreateButton();
  }

  function renderQuotePreview(value) {
    const changed = quotePreview && quotePreview.terms_sha256 !== value.terms_sha256;
    if (changed) ack.checked = false;
    quotePreview = value;
    renderTerms(previewNode, value.terms);
    previewNode.setAttribute("aria-busy", "false");
    const mode = textElement("p", "policy-note", value.sandbox
      ? "샌드박스 기준 미리 보기 · 실제 결제·환불·송금은 실행되지 않습니다."
      : "실제 제공자 모드 조건 미리 보기 · 실제 결제·환불·송금 실행은 승인되지 않았습니다.");
    previewNode.prepend(mode);
    ackCopy.textContent = "위 서버 검토 금액과 정책을 확인했습니다. 이 동의는 조건 요청일 뿐 결제·환불·송금 실행 동의가 아닙니다.";
    updateCreateButton();
  }

  async function loadQuote(operation, role, signal) {
    if (role !== "consumer" || !uuid.test(bookingId) || !authorized("consumer")) {
      clearQuote("소비자 인증과 유효한 예약 링크가 있어야 서버 금융 조건을 미리 볼 수 있습니다.");
      ack.disabled = true;
      return false;
    }
    ack.disabled = true;
    createButton.disabled = true;
    previewNode.setAttribute("aria-busy", "true");
    previewNode.textContent = "서버가 현재 예약에 적용할 금융 조건을 확인하고 있습니다.";
    try {
      const result = await api(`/hs2/finance/api/quote/${encodeURIComponent(bookingId)}`, {}, signal);
      if (operation !== generation || role !== view) return false;
      if (!validQuotePreview(result.quote)) throw new Error("서버 금융 조건의 예약 ID, 금액 또는 검증 지문을 확인할 수 없습니다.");
      renderQuotePreview(result.quote);
      ack.disabled = false;
      return true;
    } catch (error) {
      if (error.name === "AbortError" || operation !== generation) return false;
      clearQuote(error.message || "서버 금융 조건 미리 보기를 불러오지 못했습니다.");
      ack.disabled = true;
      say(error.message || "금융 조건을 미리 볼 수 없어 요청할 수 없습니다.", "error");
      return false;
    }
  }

  function clearTerms() {
    termsNode.textContent = "선택한 역할에서 허용된 서버 금융 조건만 표시합니다. 운영자 화면에서는 소비자 조건 요청을 사용할 수 없습니다.";
    quotePreview = null;
    previewNode.textContent = "역할을 변경했습니다. 해당 역할에 허용된 서버 조건을 다시 확인합니다.";
    ack.checked = false;
    ack.disabled = true;
    ackCopy.textContent = "역할을 변경했습니다. 허용된 기록을 불러온 뒤 필요한 확인을 진행해 주세요.";
    updateCreateButton();
  }

  function createAction(label, action, contract, role) {
    const button = textElement("button", `action-button${role === "consumer" ? " secondary" : ""}`, label);
    button.type = "button";
    button.dataset.action = action;
    button.dataset.contractId = contract.contract_id;
    button.disabled = pending.has(contract.contract_id) || !ack.checked;
    button.addEventListener("click", () => performAction(contract, action, role));
    return button;
  }

  function renderContract(c, role) {
    const card = document.createElement("article");
    card.className = "contract-card";
    card.dataset.contractId = c.contract_id;
    card.dataset.status = c.status;
    const top = document.createElement("div");
    top.className = "card-top";
    const identity = document.createElement("div");
    identity.append(
      textElement("p", "booking-ref", `계약 ${c.contract_id}`),
      textElement("p", "card-dates", range(c.check_in, c.check_out))
    );
    const status = textElement("span", "status-pill", labels[c.status]);
    status.dataset.status = c.status;
    top.append(identity, status);
    card.append(top);
    const facts = document.createElement("div");
    facts.className = "card-facts";
    const items = [
      ["예약 ID", c.booking_id],
      ["결제 상태", c.payment_verified ? "증빙 확인" : "증빙 없음"],
      ["예약 상태", c.booking_confirmed && !c.booking_cancelled ? "확정 기록" : c.booking_cancelled ? "취소 기록" : "확정 전"],
      ["환불 요청액", c.refund_krw === null ? "해당 없음" : won(c.refund_krw, c.terms.currency)],
      ["결제 예정 총액", won(c.terms.payable_krw, c.terms.currency)],
      ["보증금", won(c.terms.deposit_krw, c.terms.currency)],
      ["플랫폼 수수료", won(c.terms.platform_fee_krw, c.terms.currency)],
      ["플랫폼 부가세", won(c.terms.platform_vat_krw, c.terms.currency)],
      ["결제대행(PG) 처리 비용", won(c.terms.pg_processing_krw, c.terms.currency)],
      ["호스트 지급 예정액 · 보증금 제외", won(c.terms.host_payout_krw, c.terms.currency)]
    ];
    items.forEach(([label, value]) => {
      const fact = document.createElement("div");
      fact.className = "fact";
      fact.append(textElement("span", "", label), textElement("strong", "", value));
      facts.append(fact);
    });
    card.append(facts);
    const stateCopy = c.actual_money_executed === false
      ? `실행 내역 없음 · ${c.sandbox ? "샌드박스 기록" : "실제 실행은 승인되지 않음"} · 결제 증빙은 ${c.payment_verified ? "서버 수신" : "미확인"}`
      : "실행 여부를 확인할 수 없습니다.";
    card.append(textElement("div", "evidence", stateCopy));
    const events = document.createElement("ul");
    events.className = "event-list";
    if (!c.events.length) {
      events.append(textElement("li", "", "서버 이벤트 증빙이 아직 없습니다."));
    } else {
      c.events.forEach((event) => {
        const row = document.createElement("li");
        row.append(textElement("span", "", eventLabels[event.kind] || "서버 금융 이벤트"),
          textElement("strong", "", `${won(event.amount_krw, c.terms.currency)} · ${event.at}`));
        events.append(row);
      });
    }
    card.append(events);
    const due = document.createElement("div");
    due.className = "card-facts";
    due.append(
      textElement("div", "fact", ""),
      textElement("div", "fact", "")
    );
    const returnFact = due.children[0];
    returnFact.replaceChildren(textElement("span", "", "보증금 반환 검토 기준일"), textElement("strong", "", c.deposit_return_on || "서버 확인 불가"));
    const payoutFact = due.children[1];
    payoutFact.replaceChildren(textElement("span", "", "정산 검토 기준일"), textElement("strong", "", c.payout_review_on || "서버 확인 불가"));
    card.append(due);
    const actions = document.createElement("div");
    actions.className = "card-actions";
    if (role === "consumer" && c.payment_verified && c.status !== "refund_review" && !c.booking_cancelled) {
      actions.append(createAction("환불 검토 요청", "cancel", c, role));
    }
    if (role === "operator" && c.payment_verified && !c.booking_cancelled) {
      actions.append(createAction("보증금·정산 검토", "release-review", c, role));
    }
    if (actions.childElementCount) card.append(actions);
    if (selectedId === c.contract_id) card.setAttribute("aria-current", "true");
    return card;
  }

  function render(contracts, role) {
    if (!Array.isArray(contracts)) throw new Error("금융 기록 목록 응답 형식이 올바르지 않습니다.");
    const valid = contracts.filter(validContract);
    list.replaceChildren();
    if (selectedId && !valid.some((item) => item.contract_id === selectedId)) {
      say("선택한 계약은 이 역할에서 확인할 수 없습니다. 본인에게 허용된 기록만 표시합니다.", "error");
    }
    if (!valid.length) {
      empty(role === "operator" ? "담당 금융 기록이 없습니다" : "아직 금융 기록이 없습니다",
        role === "operator"
          ? "인증된 운영자 계정에 배정된 기록이 있을 때 여기에 표시됩니다."
          : bookingId && uuid.test(bookingId)
            ? "예약과 금융 조건이 유효하면 위에서 조건 요청을 시작할 수 있습니다. 요청은 결제나 실행이 아닙니다."
            : "예약 카드의 ‘금융 조건 확인’ 링크에서 booking_id를 선택하면 서버 조건 요청을 시작할 수 있습니다.");
      return;
    }
    valid.forEach((c) => list.append(renderContract(c, role)));
    list.setAttribute("aria-busy", "false");
  }

  function updateCreateButton() {
    const availableBooking = view === "consumer" && uuid.test(bookingId) && authorized("consumer");
    const hasTerms = termsNode.querySelector(".terms-grid");
    createButton.hidden = !availableBooking || !!hasTerms;
    createButton.disabled = !availableBooking || !!hasTerms || !quotePreview ||
      quotePreview.booking_id !== bookingId || !ack.checked || busy;
  }

  async function loadList() {
    const operation = invalidate();
    const role = view;
    setSkeleton();
    if (role === "consumer" && uuid.test(bookingId)) {
      ack.disabled = true;
      createButton.disabled = true;
    }
    if (!authorized(role)) {
      empty("이 역할의 인증 세션이 없습니다", "모드 선택에서 해당 역할로 로그인한 뒤 새로고침해 주세요.");
      say(role === "consumer" ? "소비자 역할 인증이 없어 금융 기록을 표시할 수 없습니다." : "운영자 역할 인증이 없어 금융 기록을 표시할 수 없습니다.", "error");
      updateCreateButton();
      return;
    }
    const localController = new AbortController();
    controller = localController;
    try {
      const result = await api(`/hs2/finance/api/${role}`, {}, localController.signal);
      if (operation !== generation || role !== view) return;
      const records = result.contracts;
      if (role === "consumer" && selectedId && uuid.test(selectedId) &&
          Array.isArray(records) && !records.some((c) => c && c.contract_id === selectedId)) {
        try {
          const selectedResult = await api(`/hs2/finance/api/consumer/${encodeURIComponent(selectedId)}`, {}, localController.signal);
          if (operation !== generation || role !== view) return;
          if (validContract(selectedResult.contract) && selectedResult.contract.contract_id === selectedId) records.push(selectedResult.contract);
        } catch (error) {
          if (error.name === "AbortError" || operation !== generation) return;
          // Keep the authorized list visible; inaccessible selections are explained below.
        }
      }
      render(records, role);
      const selected = Array.isArray(records) && records.find((c) => c && validContract(c) &&
        (selectedId ? c.contract_id === selectedId : bookingId && c.booking_id === bookingId));
      let previewLoaded = false;
      if (selected) {
        showTerms(selected);
        clearQuote("이미 연결된 금융 기록의 서버 조건을 위에 표시했습니다.", true);
      } else if (role === "consumer" && uuid.test(bookingId)) {
        termsNode.textContent = "이 예약에 연결된 금융 계약이 아직 없습니다. 아래 서버 미리 보기의 금액과 정책을 먼저 확인해 주세요.";
        ackCopy.textContent = "아래 서버 검토 금액과 정책을 확인했습니다. 이 동의는 금융 조건 요청일 뿐 결제·환불·송금 실행 동의가 아닙니다.";
        previewLoaded = await loadQuote(operation, role, localController.signal);
        if (operation !== generation || role !== view) return;
      } else {
        termsNode.textContent = role === "operator"
          ? "선택한 운영자 기록에 포함된 서버 조건은 기록 카드에서 확인할 수 있습니다."
          : "예약을 선택하거나 금융 계약을 불러오면 서버가 반환한 조건이 여기에 표시됩니다. 추정 금액은 표시하지 않습니다.";
        clearQuote("예약 카드의 금융 조건 확인 링크를 이용하면 소비자 권한으로 미리 보기를 불러옵니다.", true);
      }
      const canCreate = role === "consumer" && uuid.test(bookingId) && authorized("consumer") &&
        !termsNode.querySelector(".terms-grid");
      ack.disabled = !authorized(role) ||
        (role === "consumer" && (canCreate
          ? !quotePreview || quotePreview.booking_id !== bookingId
          : !termsNode.querySelector(".terms-grid")));
      updateCreateButton();
      if (!(role === "consumer" && uuid.test(bookingId) && !selected && !previewLoaded)) {
        say("현재 인증된 역할이 접근할 수 있는 금융 기록을 서버에서 불러왔습니다.", "ready");
      }
    } catch (error) {
      if (error.name === "AbortError" || operation !== generation) return;
      let previewAvailable = false;
      if (role === "consumer" && uuid.test(bookingId)) {
        previewAvailable = await loadQuote(operation, role, localController.signal);
        if (operation !== generation || role !== view) return;
      } else clearQuote("금융 조건 미리 보기를 사용할 예약이 없습니다.", true);
      empty("금융 기록을 불러오지 못했습니다", error.message);
      list.setAttribute("aria-busy", "false");
      const retry = textElement("button", "quiet-button", "다시 불러오기");
      retry.type = "button";
      retry.addEventListener("click", loadList);
      list.append(retry);
      if (previewAvailable) {
        ack.disabled = false;
        updateCreateButton();
        say("기록 목록은 불러오지 못했지만 서버 금융 조건은 미리 볼 수 있습니다. 조건을 확인한 뒤 요청할 수 있습니다.", "error");
      } else say(error.message, "error");
    } finally {
      if (operation === generation) controller = null;
    }
  }

  async function createContract() {
    if (busy || view !== "consumer" || !authorized("consumer") || !uuid.test(bookingId) ||
        !quotePreview || quotePreview.booking_id !== bookingId || !ack.checked) {
      say("소비자 인증, 서버 금융 조건 미리 보기, 그리고 해당 조건에 대한 명시적 확인이 필요합니다.", "error");
      return;
    }
    if (!createKey) createKey = crypto.randomUUID();
    const operation = generation;
    const role = view;
    busy = true;
    updateCreateButton();
    say("확인한 서버 조건 지문과 예약 상태를 대조하고 있습니다. 결제는 실행되지 않습니다.", "loading");
    try {
      const result = await api("/hs2/finance/api/contracts", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": session.consumer_csrf },
        body: JSON.stringify({
          booking_id: bookingId,
          request_id: createKey,
          acknowledged: true,
          expected_terms_sha256: quotePreview.terms_sha256
        })
      });
      if (!current(operation, role)) return;
      if (!validContract(result.contract) || result.contract.booking_id !== bookingId) {
        throw new Error("서버가 반환한 금융 계약을 검증할 수 없습니다.");
      }
      createKey = null;
      showTerms(result.contract);
      ack.checked = false;
      say("서버 금융 조건을 받았습니다. 금액과 정책을 확인해 주세요. 계약 생성은 결제 완료가 아닙니다.", "ready");
      await loadList();
    } catch (error) {
      if (operation !== generation || error.name === "AbortError") return;
      if (error.code === "FINANCIAL_TERMS_CHANGED") {
        ack.checked = false;
        createKey = null;
        quotePreview = null;
        previewNode.textContent = "금융 조건이 바뀌었습니다. 최신 서버 조건을 다시 불러오고 있습니다.";
        ack.disabled = true;
        updateCreateButton();
        const refreshed = await loadQuote(operation, role);
        if (operation !== generation || role !== view) return;
        say(refreshed
          ? "금융 조건이 변경되었습니다. 새 미리 보기의 금액과 정책을 다시 확인하고 동의해 주세요."
          : "조건이 변경되었으며 최신 미리 보기도 확인할 수 없습니다. 요청은 비활성화되어 있습니다.", "error");
        return;
      }
      if (["FINANCIAL_RETRY_CONFLICT", "BOOKING_STATE_CHANGED", "BOOKING_DEADLINE_EXPIRED", "REVIEWED_FINANCIAL_POLICY_REQUIRED"].includes(error.code)) createKey = null;
      // Keep the same request key after uncertain failures so retry is idempotent.
      say(error.message || "금융 조건 요청 결과를 확인하지 못했습니다.", "error");
    } finally {
      busy = false;
      updateCreateButton();
    }
  }

  async function performAction(contract, action, role) {
    if (!validContract(contract) || role !== view || !ack.checked || pending.has(contract.contract_id) || !authorized(role)) {
      say("선택한 역할 인증과 명시적 검토 확인이 필요합니다.", "error");
      return;
    }
    const operation = generation;
    const csrf = role === "consumer" ? session.consumer_csrf : session.operator_csrf;
    pending.add(contract.contract_id);
    list.querySelectorAll(`[data-contract-id="${CSS.escape(contract.contract_id)}"] button`).forEach((button) => { button.disabled = true; });
    say(action === "cancel" ? "환불 검토 요청을 기록하고 있습니다. 실제 환불은 실행되지 않습니다." : "보증금·정산 검토 가능 여부를 서버에 요청하고 있습니다. 실제 송금은 실행되지 않습니다.", "loading");
    const endpoint = role === "consumer"
      ? `/hs2/finance/api/consumer/${encodeURIComponent(contract.contract_id)}/cancel`
      : `/hs2/finance/api/operator/${encodeURIComponent(contract.contract_id)}/release-review`;
    try {
      const result = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ acknowledged: true })
      });
      if (!current(operation, role)) return;
      if (!validContract(result.contract) || result.contract.contract_id !== contract.contract_id) throw new Error("서버의 검토 응답을 검증할 수 없습니다.");
      ack.checked = false;
      say(action === "cancel"
        ? "환불 검토 요청이 기록되었습니다. 환불이 실행되었거나 완료된 것은 아닙니다."
        : "서버가 검토 기록을 갱신했습니다. 보증금 반환이나 호스트 송금은 실행되지 않았습니다.", "ready");
      await loadList();
    } catch (error) {
      if (operation !== generation || error.name === "AbortError") return;
      say(error.message, "error");
      await loadList();
    } finally {
      pending.delete(contract.contract_id);
    }
  }

  async function initialize() {
    setSwitch();
    termsNode.textContent = bookingId && uuid.test(bookingId)
      ? "예약을 조회하고 서버 검토 조건을 확인합니다. 조건 요청은 실제 결제나 송금이 아닙니다."
      : "예약을 선택하거나 금융 계약을 불러오면 서버가 반환한 조건이 여기에 표시됩니다. 추정 금액은 표시하지 않습니다.";
    ackCopy.textContent = bookingId && uuid.test(bookingId)
      ? "이 예약에 적용할 서버 검토 금융 조건을 요청하고, 반환된 조건은 이후 직접 확인합니다. 이 확인은 결제·환불·송금 실행 동의가 아닙니다."
      : "표시할 서버 금융 조건이 없습니다. 예약 링크를 통해 조건을 불러온 뒤 확인해 주세요.";
    if (bookingId && !uuid.test(bookingId)) {
      say("예약 식별자가 올바르지 않습니다. 예약 현황에서 해당 예약의 링크를 다시 사용해 주세요.", "error");
    }
    try {
      const result = await api("/hs2/finance/api/session");
      if (typeof result.can_consumer !== "boolean" || typeof result.can_operator !== "boolean" ||
          typeof result.sandbox !== "boolean" || typeof result.provider_available !== "boolean" ||
          result.actual_execution_available !== false) throw new Error("인증 및 결제 실행 상태 응답을 검증할 수 없습니다.");
      session = result;
      providerState.textContent = `${result.sandbox ? "샌드박스 모드" : "실제 제공자 모드"} · 결제 제공자 ${result.provider_available ? "사용 가능" : "사용 불가"} · 실제 실행 승인 없음. 제공자 이벤트는 서버 증빙으로만 반영되며 이 화면에서 실행하지 않습니다.`;
      ack.disabled = !authorized("consumer");
      await loadList();
    } catch (error) {
      empty("세션 상태를 확인할 수 없습니다", error.message);
      say(error.message, "error");
      providerState.textContent = "실행 상태를 확인할 수 없습니다. 결제·환불·송금을 실행하지 마세요.";
    }
  }

  consumerButton.addEventListener("click", () => {
    if (view === "consumer") return;
    invalidate();
    view = "consumer";
    setSwitch();
    updateUrl();
    clearTerms();
    loadList();
  });
  operatorButton.addEventListener("click", () => {
    if (view === "operator") return;
    invalidate();
    view = "operator";
    setSwitch();
    updateUrl();
    clearTerms();
    loadList();
  });
  $("#refresh-finance").addEventListener("click", loadList);
  createButton.addEventListener("click", createContract);
  ack.addEventListener("change", () => {
    updateCreateButton();
    list.querySelectorAll(".contract-card").forEach((card) => {
      card.querySelectorAll("[data-action]").forEach((button) => { button.disabled = !ack.checked || pending.has(card.dataset.contractId); });
    });
  });
  initialize();
})();
