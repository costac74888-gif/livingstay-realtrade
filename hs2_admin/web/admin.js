(() => {
  "use strict";

  const API = "/hs2/admin/api";
  const $ = (selector, root = document) => root.querySelector(selector);
  const feedback = $("#admin-feedback");
  const feedbackMessage = $("#admin-feedback-message");
  const kindSelect = $("#admin-record-kind");
  const fieldsRoot = $("#admin-record-fields");
  const recordForm = $("#admin-record-form");
  const recordContainer = $("#admin-records");
  const editing = { id: null, revision: null };
  let csrf = "";
  let kinds = [];
  let faqs = [];
  let faqUnavailable = false;
  let overview = null;
  let busy = false;

  const labels = {
    faq: "도움말 FAQ",
    policy: "수수료·보증금 정책",
    promotion: "프로모션 기록",
    report: "내부 보고 메모",
    review: "관리자 검토 메모",
    draft: "초안",
    approved: "승인됨",
    archived: "보관됨",
    pending: "검토 대기",
    rejected: "거절됨",
    approved_until: "승인 만료일",
    booking_id: "예약 ID",
    application_id: "신청 ID",
    contract_id: "계약 ID",
    public_id: "공개 ID",
    total_krw: "예약 합계",
    check_in: "체크인",
    check_out: "체크아웃"
  };

  function setFeedback(state, message, retry = false) {
    feedback.dataset.state = state;
    feedbackMessage.textContent = message;
    $("#admin-refresh").hidden = !retry;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function empty(message, detail) {
    const box = el("div", "empty-state");
    box.append(el("strong", "", message), el("p", "", detail));
    return box;
  }

  function pretty(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") {
      try { return JSON.stringify(value, null, 2); } catch { return String(value); }
    }
    return String(value);
  }

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? `${new Intl.NumberFormat("ko-KR").format(number)}원` : String(value);
  }

  function statusLabel(status) {
    return labels[status] || status || "상태 미표시";
  }

  async function request(path, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["X-HS2-CSRF"] = csrf;
    }
    const response = await fetch(path, { method: options.method || "GET", headers, body: options.body, credentials: "same-origin", cache: "no-store" });
    let result;
    try { result = await response.json(); } catch { result = {}; }
    if (!response.ok || result.ok === false) {
      const error = new Error(result.code || `HTTP_${response.status}`);
      error.status = response.status;
      error.code = result.code || "";
      throw error;
    }
    return result;
  }

  function isAuthFailure(error) {
    return error.status === 401 || error.status === 403 || error.code === "ADMIN_REQUIRED" || error.code === "CSRF_REQUIRED";
  }

  function markBusy(value) {
    busy = value;
    document.querySelectorAll("button,input,select,textarea").forEach((button) => {
      if (button.id !== "admin-refresh") button.disabled = value;
    });
  }

  function clearProtected(message) {
    overview = null;
    csrf = "";
    resetEditor();
    $("#admin-review-note").value = "";
    $("#admin-rights").checked = false;
    $("#admin-disclosure").checked = false;
    ["#admin-records", "#admin-registrations", "#admin-bookings", "#admin-finances", "#admin-audits", "#admin-summary"].forEach((selector) => {
      const node = $(selector);
      node.replaceChildren(empty("보호된 정보를 표시하지 않습니다.", "관리자 인증을 확인한 뒤 다시 불러오세요."));
      node.setAttribute("aria-busy", "false");
    });
    $("#admin-scope-note").textContent = "인증된 관리자 세션이 필요합니다.";
    setFeedback("error", message, true);
  }

  function clearUnsafeForStale() {
    overview = null;
    ["#admin-records", "#admin-registrations", "#admin-bookings", "#admin-finances", "#admin-audits", "#admin-summary"].forEach((selector) => {
      const node = $(selector);
      node.replaceChildren(empty("최신 데이터 확인 필요", "이전 원장 결과는 숨겼습니다. 새로고침으로 현재 revision을 확인하세요."));
      node.setAttribute("aria-busy", "false");
    });
    setFeedback("error", "기록 버전이 변경되었습니다. 오래된 결과를 숨겼습니다. 새로고침 후 다시 검토하세요.", true);
  }

  function handleError(error, fallback) {
    if (error.code === "STALE_ADMIN_REVISION") {
      clearUnsafeForStale();
      return;
    }
    if (isAuthFailure(error)) {
      clearProtected("관리자 인증 또는 CSRF 확인이 필요합니다. 보호된 데이터는 지웠습니다.");
      return;
    }
    const messages = {
      "INVALID_ADMIN_COMMAND": "입력 항목을 확인하고 다시 시도하세요.",
      "ADMIN_TEXT_REQUIRED": "필수 메모와 텍스트를 입력해 주세요.",
      "KNOWN_FAQ_REQUIRED": "현재 도움말에서 FAQ 항목을 다시 선택해 주세요.",
      "INITIAL_PLATFORM_ZERO_REQUIRED": "플랫폼 수수료는 초기 기준 0%만 기록할 수 있습니다.",
      "DRAFT_APPROVAL_REQUIRED": "승인 가능한 초안인지 새로고침해 확인해 주세요.",
      "ARCHIVE_TERMINAL": "이미 보관된 기록은 변경할 수 없습니다.",
      "INVALID_PROMOTION_DATES": "프로모션 기간은 1~366일 범위로 입력해 주세요.",
      "EXPLICIT_POLICY_REQUIRED": "정책에 필요한 모든 값을 명시해 주세요.",
      "EXPLICIT_LISTING_REVIEW_REQUIRED": "검토 메모와 필수 확인 항목을 모두 확인해 주세요."
    };
    setFeedback("error", messages[error.code] || `${fallback} (${error.code || "NETWORK_ERROR"})`, true);
  }

  function addField({ name, label, type = "text", wide = false, required = true, options, hint, value = "", min, max, step }) {
    const wrap = el("div", `field${wide ? " field-wide" : ""}`);
    const inputId = `record-${name}`;
    const labelNode = el("label", "", label);
    labelNode.htmlFor = inputId;
    let control;
    if (options) {
      control = document.createElement("select");
      const initial = document.createElement("option");
      initial.value = "";
      initial.textContent = "선택하세요";
      control.append(initial);
      options.forEach((option) => {
        const item = document.createElement("option");
        item.value = option.value;
        item.textContent = option.label;
        control.append(item);
      });
    } else if (type === "textarea") {
      control = document.createElement("textarea");
      control.maxLength = name === "answer" ? 3000 : 2000;
    } else {
      control = document.createElement("input");
      control.type = type;
      if (min !== undefined) control.min = String(min);
      if (max !== undefined) control.max = String(max);
      if (step !== undefined) control.step = String(step);
      if (type === "number") control.inputMode = "numeric";
    }
    control.id = inputId;
    control.name = name;
    control.required = required;
    if (value) control.value = value;
    wrap.append(labelNode, control);
    if (hint) wrap.append(el("small", "field-hint", hint));
    fieldsRoot.append(wrap);
  }

  function applicationOptions() {
    return (overview?.registrations || []).map((item) => ({
      value: item.application_id,
      label: `${item.title || "제목 없음"} · ${item.status} · ${item.application_id}`
    }));
  }

  function renderFields(kind) {
    fieldsRoot.replaceChildren();
    if (!kind) return;
    if (kind === "faq") {
      const choices = faqs.map((faq) => ({ value: faq.id, label: `${faq.question || "질문"} · ${faq.id}` }));
      if (!choices.length) {
        fieldsRoot.append(empty("FAQ 선택지를 불러오지 못했습니다.", "도움말 콘텐츠에 연결된 실제 FAQ만 선택할 수 있습니다."));
        return;
      }
      addField({ name: "faq_id", label: "기존 FAQ 항목", options: choices, wide: true });
      addField({ name: "question", label: "질문", wide: true });
      addField({ name: "answer", label: "답변", type: "textarea", wide: true, hint: "승인된 FAQ는 실제 도움말 콘텐츠에 반영됩니다." });
      return;
    }
    if (kind === "policy") {
      addField({ name: "title", label: "정책 제목" });
      addField({ name: "note", label: "정책 근거 메모", type: "textarea", wide: true });
      addField({ name: "deposit_krw", label: "보증금 (원)", type: "number", min: 0, step: 1 });
      addField({ name: "pg_processing_krw", label: "PG 처리 비용 (원)", type: "number", min: 0, step: 1 });
      addField({ name: "platform_bps", label: "플랫폼 수수료 (bps)", type: "number", min: 0, max: 0, step: 1, value: "0", hint: "초기 플랫폼 수수료 0% 기준은 변경할 수 없습니다." });
      addField({ name: "deposit_return_days", label: "보증금 반환 기간 (일)", type: "number", min: 0, step: 1 });
      addField({ name: "settlement_days", label: "정산 기준 기간 (일)", type: "number", min: 0, step: 1, hint: "새 정책 초안 값입니다. 기존 계약은 변경되지 않습니다." });
      return;
    }
    if (kind === "promotion") {
      addField({ name: "application_id", label: "등록 신청", options: applicationOptions(), wide: true, hint: "프로모션 관리자 기록이며 결제나 게시 상태를 바꾸지 않습니다." });
      addField({ name: "title", label: "프로모션 제목" });
      addField({ name: "amount_krw", label: "표시 금액 (원)", type: "number", min: 0, step: 1 });
      addField({ name: "start", label: "시작일", type: "date" });
      addField({ name: "end", label: "종료일", type: "date" });
      addField({ name: "note", label: "운영 메모", type: "textarea", wide: true });
      return;
    }
    if (kind === "report" || kind === "review") {
      addField({ name: "application_id", label: "등록 신청", options: applicationOptions(), wide: true });
      addField({ name: "title", label: kind === "report" ? "보고 메모 제목" : "검토 메모 제목", wide: true });
      addField({ name: "note", label: "내부 메모", type: "textarea", wide: true, hint: "내부 개발 관리자 기록이며 고객 공개 후기나 실제 분석 결과가 아닙니다." });
    }
  }

  function fillKindOptions() {
    kindSelect.replaceChildren();
    const prompt = document.createElement("option");
    prompt.value = "";
    prompt.textContent = "기록 종류를 선택하세요";
    kindSelect.append(prompt);
    kinds.forEach((kind) => {
      const option = document.createElement("option");
      option.value = kind;
      option.textContent = labels[kind] || kind;
      kindSelect.append(option);
    });
  }

  function buildPayload() {
    const kind = kindSelect.value;
    const payload = {};
    new FormData(recordForm).forEach((value, key) => {
      if (key !== "kind") payload[key] = value;
    });
    if (kind === "policy") {
      ["deposit_krw", "pg_processing_krw", "platform_bps", "deposit_return_days", "settlement_days"].forEach((key) => {
        payload[key] = Number(payload[key]);
      });
    }
    if (kind === "promotion") payload.amount_krw = Number(payload.amount_krw);
    return { kind, payload };
  }

  function hydrateRecord(record) {
    kindSelect.value = record.kind;
    renderFields(record.kind);
    Object.entries(record.payload || {}).forEach(([name, value]) => {
      const input = fieldsRoot.querySelector(`[name="${CSS.escape(name)}"]`);
      if (input) input.value = value === null || value === undefined ? "" : String(value);
    });
    editing.id = record.id;
    editing.revision = record.revision;
    $("#admin-form-mode").textContent = `기록 수정 · revision ${record.revision} · 저장 시 초안`;
    recordForm.querySelector('[type="submit"]').textContent = "변경 내용 저장";
    $("#admin-record-cancel").hidden = false;
    recordForm.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function resetEditor() {
    editing.id = null;
    editing.revision = null;
    recordForm.reset();
    kindSelect.value = "";
    renderFields("");
    $("#admin-form-mode").textContent = "새 기록 · 초안으로 생성";
    recordForm.querySelector('[type="submit"]').textContent = "초안 저장";
    $("#admin-record-cancel").hidden = true;
  }

  function recordCard(record) {
    const card = el("article", "record-card reveal");
    card.dataset.recordId = record.id;
    const head = el("div", "record-card-head");
    const title = el("h3", "", record.payload?.title || record.payload?.question || labels[record.kind] || record.kind);
    const badge = el("span", "state-pill", statusLabel(record.status));
    badge.dataset.status = record.status || "";
    const kindLabel = el("span", "", labels[record.kind] || record.kind);
    head.append(el("div", "", ""));
    head.firstChild.append(title, kindLabel);
    head.append(badge);
    card.append(head);
    const details = el("p", "subcopy", record.payload?.note || record.payload?.answer || "저장된 관리자 기록");
    details.style.margin = "9px 0 0";
    card.append(details);
    const meta = el("div", "record-meta");
    meta.append(el("span", "", `ID ${record.id}`), el("span", "", `revision ${record.revision}`), el("span", "", `수정 ${record.updated_at || "—"}`));
    card.append(meta);
    const actions = el("div", "record-actions");
    if (record.status === "draft") {
      actions.append(
        actionButton("edit", "편집", "button button-quiet", record.id),
        actionButton("approve", "초안 승인", "button button-primary", record.id),
        actionButton("archive", "보관", "button button-danger", record.id)
      );
    } else if (record.status !== "archived") {
      actions.append(
        actionButton("edit", "편집 후 재검토", "button button-quiet", record.id),
        actionButton("archive", "보관", "button button-danger", record.id)
      );
    }
    if (actions.childElementCount) card.append(actions);
    return card;
  }

  function actionButton(action, text, className, recordId) {
    const button = el("button", className, text);
    button.type = "button";
    button.dataset.action = action;
    button.dataset.recordId = recordId;
    return button;
  }

  function renderRecords() {
    const records = overview?.records || [];
    $("#record-count").textContent = `${records.length}건`;
    recordContainer.replaceChildren();
    if (!records.length) {
      recordContainer.append(empty("아직 관리자 기록이 없습니다.", "위 입력 폼에서 첫 초안을 작성하면 이 원장에 표시됩니다."));
    } else {
      records.forEach((record) => recordContainer.append(recordCard(record)));
    }
    recordContainer.setAttribute("aria-busy", "false");
  }

  function renderRegistrations() {
    const container = $("#admin-registrations");
    container.replaceChildren();
    const rows = overview?.registrations || [];
    if (!rows.length) container.append(empty("최근 등록 신청이 없습니다.", "서버가 반환한 최근 신청 100건 범위입니다."));
    rows.forEach((item) => {
      const card = el("article", "record-card review-card reveal");
      const head = el("div", "record-card-head");
      const titleBox = el("div");
      titleBox.append(el("h3", "", item.title || "제목 없음"));
      const badge = el("span", "state-pill", statusLabel(item.status));
      badge.dataset.status = item.status || "";
      head.append(titleBox, badge);
      card.append(head);
      const meta = el("div", "record-meta");
      meta.append(
        el("span", "", `신청 ${item.application_id}`),
        el("span", "", `공개 ID ${item.public_id || "미발급"}`),
        el("span", "", `revision ${item.revision}`),
        el("span", "", `승인 만료 ${item.approved_until || "—"}`)
      );
      const rate = el("div", "record-meta");
      rate.append(el("span", "", `요금 정보 ${pretty(item.rate)}`));
      card.append(meta, rate);
      if (item.status === "submitted") {
        const actions = el("div", "record-actions");
        const approve = actionButton("review-approve", "신청 승인", "button button-primary", item.application_id);
        const reject = actionButton("review-reject", "신청 거절", "button button-danger", item.application_id);
        approve.dataset.revision = String(item.revision);
        reject.dataset.revision = String(item.revision);
        actions.append(approve, reject);
        card.append(actions);
      }
      container.append(card);
    });
    container.setAttribute("aria-busy", "false");
  }

  function renderTable(container, headings, rows, emptyTitle, emptyDetail) {
    container.replaceChildren();
    if (!rows.length) {
      container.append(empty(emptyTitle, emptyDetail));
      container.setAttribute("aria-busy", "false");
      return;
    }
    const table = el("table", "data-table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    headings.forEach((heading) => headerRow.append(el("th", "", heading.label)));
    thead.append(headerRow);
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      headings.forEach((heading) => {
        const td = document.createElement("td");
        const value = row[heading.key];
        if (heading.code) {
          const code = el("code", "", value ?? "—");
          td.append(code);
        } else td.textContent = heading.format ? heading.format(value, row) : pretty(value);
        tr.append(td);
      });
      tbody.append(tr);
    });
    table.append(thead, tbody);
    container.append(table);
    container.setAttribute("aria-busy", "false");
  }

  function renderFinances() {
    const container = $("#admin-finances");
    container.replaceChildren();
    const rows = overview?.finances || [];
    if (!rows.length) container.append(empty("금융 계약 원장이 비어 있습니다.", "계약 레코드가 반환되지 않았습니다. 새 계약이나 거래를 만들지 않습니다."));
    rows.forEach((finance) => {
      const card = el("article", "ledger-entry reveal");
      card.append(el("h3", "", `계약 ${finance.contract_id}`));
      card.append(el("p", "", `예약 ${finance.booking_id} · ${finance.sandbox ? "샌드박스" : "샌드박스 아님"} · 실제 실행 없음`));
      const termsTitle = el("p", "", "저장된 계약 약정");
      const terms = el("pre", "", pretty(finance.terms));
      card.append(termsTitle, terms);
      const events = Array.isArray(finance.events) ? finance.events : [];
      const details = document.createElement("details");
      const summary = el("summary", "", `금융 이벤트 ${events.length}건 · 증빙 기록`);
      details.append(summary);
      if (!events.length) details.append(el("p", "", "기록된 이벤트가 없습니다."));
      events.forEach((event) => {
        const eventRow = el("p", "", `${event.kind || "이벤트"} · ${money(event.amount_krw)} · ${event.at || "시간 미표시"} · 실제 실행 아님`);
        details.append(eventRow);
      });
      card.append(details);
      container.append(card);
    });
    container.setAttribute("aria-busy", "false");
  }

  function renderSummary() {
    const summary = $("#admin-summary");
    summary.replaceChildren();
    const counts = overview?.counts || {};
    [
      ["신청", counts.registrations],
      ["예약", counts.bookings],
      ["계약", counts.contracts],
      ["기록", counts.records]
    ].forEach(([label, count]) => {
      const cell = el("div", "summary-cell");
      cell.append(el("span", "", label), el("strong", "", count ?? "—"));
      summary.append(cell);
    });
    summary.setAttribute("aria-busy", "false");
    $("#admin-scope-note").textContent = `최근 표시 범위: 최대 ${overview?.recent_limit ?? 100}건 · 플랫폼 기준 ${overview?.initial_platform_bps ?? 0} bps (0%) · 기존 관리자 ${overview?.preserved_admin_uri || "/admin"}`;
  }

  function renderAll() {
    renderRecords();
    renderRegistrations();
    renderTable($("#admin-bookings"), [
      { key: "booking_id", label: "예약 ID", code: true },
      { key: "status", label: "상태", format: statusLabel },
      { key: "total_krw", label: "예약 합계", format: money },
      { key: "check_in", label: "체크인" },
      { key: "check_out", label: "체크아웃" },
      { key: "revision", label: "Revision" }
    ], overview?.bookings || [], "예약 원장이 비어 있습니다.", "SQL 원장에서 반환된 예약이 없습니다.");
    renderFinances();
    renderTable($("#admin-audits"), [
      { key: "id", label: "이벤트 ID", code: true },
      { key: "record_id", label: "기록 ID", code: true },
      { key: "revision", label: "Revision" },
      { key: "action", label: "작업" },
      { key: "note", label: "변경 메모" },
      { key: "created_at", label: "시각" }
    ], overview?.audits || [], "변경 감사 기록이 없습니다.", "관리자 기록의 변경 이벤트가 여기에 표시됩니다.");
    renderSummary();
    renderFields(kindSelect.value);
  }

  async function load() {
    if (busy) return;
    markBusy(true);
    setFeedback("loading", "관리자 접근 권한과 최신 원장 데이터를 확인하고 있습니다.");
    document.querySelectorAll('[aria-busy="false"]').forEach((node) => node.setAttribute("aria-busy", "true"));
    try {
      const [meta, data, help] = await Promise.all([
        request(`${API}/meta`),
        request(`${API}/overview`),
        fetch("/hs2/help/api/content", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" }).then(async (response) => {
          if (!response.ok) return { faqs: [], unavailable: true };
          return response.json();
        }).catch(() => ({ faqs: [], unavailable: true }))
      ]);
      csrf = meta.csrf;
      kinds = Array.isArray(meta.kinds) ? meta.kinds : [];
      overview = data;
      faqs = Array.isArray(help.faqs) ? help.faqs : [];
      faqUnavailable = Boolean(help.unavailable) || !Array.isArray(help.faqs);
      fillKindOptions();
      renderAll();
      setFeedback("ready", `최신 SQL 원장 데이터를 불러왔습니다. 최근 ${overview.recent_limit ?? 100}건 범위 · 라이브 작업 승인 없음.${faqUnavailable ? " FAQ 선택지는 도움말 콘텐츠를 불러오지 못해 비활성 상태입니다." : ""}`);
    } catch (error) {
      if (isAuthFailure(error)) {
        clearProtected("관리자 인증이 필요합니다. 보호된 원장 내용을 표시하지 않습니다.");
      } else {
        setFeedback("error", "관리자 데이터를 불러오지 못했습니다. 연결과 접근 권한을 확인한 뒤 다시 시도하세요.", true);
        if (!overview) {
          ["#admin-records", "#admin-registrations", "#admin-bookings", "#admin-finances", "#admin-audits", "#admin-summary"].forEach((selector) => {
            const node = $(selector);
            node.replaceChildren(empty("데이터를 불러오지 못했습니다.", "새로고침을 눌러 서버 원장을 다시 요청하세요."));
            node.setAttribute("aria-busy", "false");
          });
        }
      }
    } finally {
      markBusy(false);
    }
  }

  async function submitRecord(event) {
    event.preventDefault();
    if (busy) return;
    if (!recordForm.reportValidity()) return;
    const { kind, payload } = buildPayload();
    const wasEditing = Boolean(editing.id);
    markBusy(true);
    setFeedback("loading", "관리자 기록을 저장하고 최신 원장을 확인하고 있습니다.");
    try {
      if (editing.id) {
        const note = $("#admin-review-note").value.trim();
        if (!note) {
          setFeedback("error", "기록을 수정할 때는 검토 메모를 입력해야 합니다.");
          $("#admin-review-note").focus();
          return;
        }
        await request(`${API}/records/${encodeURIComponent(editing.id)}/change`, {
          method: "POST",
          body: JSON.stringify({ revision: editing.revision, action: "save", note, payload })
        });
      } else {
        await request(`${API}/records`, { method: "POST", body: JSON.stringify({ kind, payload }) });
      }
      resetEditor();
      await refreshOverviewOnly();
      setFeedback("ready", wasEditing ? "기록 변경 내용을 초안으로 저장했습니다." : "새 관리자 초안을 생성했습니다.");
    } catch (error) {
      handleError(error, "기록 저장 실패");
    } finally {
      markBusy(false);
    }
  }

  async function refreshOverviewOnly() {
    const latest = await request(`${API}/overview`);
    overview = latest;
    renderAll();
  }

  async function changeRecord(record, action) {
    const note = $("#admin-review-note").value.trim();
    if (!note) {
      setFeedback("error", "기록을 승인하거나 보관하려면 검토 메모를 입력하세요.");
      $("#admin-review-note").focus();
      return;
    }
    markBusy(true);
    setFeedback("loading", "관리자 결정을 저장하고 최신 원장을 확인하고 있습니다.");
    try {
      await request(`${API}/records/${encodeURIComponent(record.id)}/change`, {
        method: "POST",
        body: JSON.stringify({ revision: record.revision, action, note, payload: null })
      });
      await refreshOverviewOnly();
      setFeedback("ready", action === "approve" ? "초안을 관리자 검토 상태로 승인했습니다." : "기록을 보관했습니다.");
    } catch (error) {
      handleError(error, "기록 변경 실패");
    } finally {
      markBusy(false);
    }
  }

  async function reviewApplication(button) {
    const note = $("#admin-review-note").value.trim();
    if (!note) {
      setFeedback("error", "등록 신청 결정에는 검토 메모가 필요합니다.");
      $("#admin-review-note").focus();
      return;
    }
    const rights = $("#admin-rights").checked;
    const disclosure = $("#admin-disclosure").checked;
    const decision = button.dataset.action === "review-approve" ? "approve" : "reject";
    if (decision === "approve" && (!rights || !disclosure)) {
      setFeedback("error", "승인 전에 권리와 필수 고지를 모두 확인해 주세요.");
      return;
    }
    markBusy(true);
    setFeedback("loading", "등록 신청 결정을 저장하고 최신 상태를 확인하고 있습니다.");
    try {
      await request(`${API}/applications/${encodeURIComponent(button.dataset.recordId)}/review`, {
        method: "POST",
        body: JSON.stringify({
          revision: Number(button.dataset.revision),
          decision,
          note,
          rights,
          disclosure
        })
      });
      await refreshOverviewOnly();
      setFeedback("ready", decision === "approve" ? "등록 신청을 승인했습니다." : "등록 신청을 거절했습니다.");
    } catch (error) {
      handleError(error, "등록 신청 검토 실패");
    } finally {
      markBusy(false);
    }
  }

  kindSelect.addEventListener("change", () => renderFields(kindSelect.value));
  recordForm.addEventListener("submit", submitRecord);
  $("#admin-record-cancel").addEventListener("click", resetEditor);
  $("#admin-refresh").addEventListener("click", load);
  recordContainer.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || busy) return;
    const record = (overview?.records || []).find((item) => item.id === button.dataset.recordId);
    if (!record) return;
    if (button.dataset.action === "edit") hydrateRecord(record);
    else if (button.dataset.action === "approve" || button.dataset.action === "archive") changeRecord(record, button.dataset.action);
  });
  $("#admin-registrations").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action^='review-']");
    if (button && !busy) reviewApplication(button);
  });
  load();
})();
