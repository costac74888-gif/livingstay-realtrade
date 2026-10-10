(function () {
  "use strict";

  var SESSION_API = "/hs2/dashboard/api/session";
  var OVERVIEW_API = "/hs2/dashboard/api/overview";
  var state = { requestId: 0, controller: null, loading: false };
  var el = {
    feedback: document.getElementById("dashboard-feedback"),
    refresh: document.getElementById("refresh-dashboard"),
    scope: document.getElementById("dashboard-scope"),
    summary: document.getElementById("dashboard-summary"),
    finance: document.getElementById("dashboard-finance"),
    applications: document.getElementById("dashboard-applications"),
    bookings: document.getElementById("dashboard-bookings"),
    contracts: document.getElementById("dashboard-contracts"),
    workLinks: document.getElementById("dashboard-work-links"),
    legacyLinks: document.getElementById("dashboard-legacy-links")
  };

  var countFields = [
    ["registrations_all", "전체 등록 신청", "건"],
    ["published_rooms", "공개 게시 중인 객실", "건"],
    ["bookings_pending_operator", "운영자 확인 대기 예약", "건"],
    ["bookings_awaiting_payment", "결제 대기 예약", "건"],
    ["bookings_confirmed_active", "활성 확정 예약", "건"],
    ["bookings_cancelled_paid", "결제 후 취소된 예약", "건"]
  ];
  var moneyFields = [
    ["sandbox_capture_krw", "샌드박스 캡처 증빙", "테스트 환경의 capture·late_capture 합계", "sandbox"],
    ["live_capture_krw", "라이브 캡처 증빙", "라이브 capture·late_capture 이벤트 합계", "live"],
    ["active_stay_krw", "활성 숙박 기준액", "캡처된 미취소 계약의 숙박 조건", "basis"],
    ["deposit_liability_krw", "활성 보증금 기준액", "캡처된 미취소 계약의 보증금 조건", "basis"],
    ["host_payout_review_basis_krw", "호스트 지급 검토 기준액", "캡처된 미취소 계약의 지급 조건", "basis"],
    ["refund_review_krw", "환불 검토액", "환불 검토 이벤트 금액 합계", "review"],
    ["deposit_review_krw", "보증금 검토액", "보증금 검토 이벤트 금액 합계", "review"],
    ["payout_review_krw", "지급 검토액", "지급 검토 이벤트 금액 합계", "review"]
  ];

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }
  function requiredString(value) { return typeof value === "string" && value.length > 0; }
  function integer(value) { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0; }
  function requireObject(value, label) {
    if (!isObject(value)) throw new Error(label + " 응답 형식이 올바르지 않습니다.");
    return value;
  }
  function requireKeys(object, keys, label) {
    keys.forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(object, key)) throw new Error(label + " 응답에 " + key + " 항목이 없습니다.");
    });
  }
  function validateList(value, fields, label) {
    requireObject(value, label);
    requireKeys(value, ["items", "total", "has_more"], label);
    if (!Array.isArray(value.items) || value.items.length > 20 || !integer(value.total) ||
        typeof value.has_more !== "boolean" || value.total < value.items.length ||
        value.has_more !== (value.total > value.items.length)) {
      throw new Error(label + " 목록의 전체 건수 또는 제한 상태가 올바르지 않습니다.");
    }
    value.items.forEach(function (item) {
      requireObject(item, label + " 항목");
      requireKeys(item, fields, label + " 항목");
    });
    return value;
  }
  function validateOverview(payload) {
    requireObject(payload, "대시보드");
    if (payload.ok !== true) throw new Error("대시보드 조회가 승인되지 않았습니다.");
    var dashboard = requireObject(payload.dashboard, "대시보드");
    requireKeys(dashboard, ["scope", "counts", "finance", "applications", "bookings", "contracts", "work_links", "legacy_links", "basis"], "대시보드");
    if (dashboard.basis !== "scoped_ledger_not_executed_cash") throw new Error("원장 기준을 확인할 수 없습니다.");
    requireObject(dashboard.scope, "범위");
    requireKeys(dashboard.scope, ["role", "context_id"], "범위");
    if (dashboard.scope.role !== "operator" || dashboard.scope.context_id == null ||
        !["string", "number"].includes(typeof dashboard.scope.context_id)) throw new Error("승인된 운영 범위를 확인할 수 없습니다.");
    requireObject(dashboard.counts, "건수");
    countFields.forEach(function (field) {
      if (!integer(dashboard.counts[field[0]])) throw new Error("원장 건수 응답이 올바르지 않습니다.");
    });
    requireObject(dashboard.finance, "금융");
    moneyFields.forEach(function (field) {
      if (!integer(dashboard.finance[field[0]])) throw new Error("금융 금액 응답이 올바르지 않습니다.");
    });
    if (dashboard.finance.actual_money_executed !== false) throw new Error("자금 실행 여부를 올바르게 확인할 수 없습니다.");
    validateList(dashboard.applications, ["application_id", "title", "stay_kind", "status", "revision", "manage_uri", "calendar_uri"], "등록 신청");
    dashboard.applications.items.forEach(function (item) {
      if (!requiredString(item.application_id) || !requiredString(item.title) || !requiredString(item.stay_kind) ||
          !requiredString(item.status) || !integer(item.revision) || !requiredString(item.manage_uri) ||
          !requiredString(item.calendar_uri)) throw new Error("등록 신청 응답 형식이 올바르지 않습니다.");
    });
    validateList(dashboard.bookings, ["booking_id", "application_id", "status", "check_in", "check_out", "total_krw", "uri"], "예약");
    dashboard.bookings.items.forEach(function (item) {
      if (!requiredString(item.booking_id) || !requiredString(item.application_id) || !requiredString(item.status) ||
          !integer(item.total_krw) || !requiredString(item.check_in) || !requiredString(item.check_out) ||
          !requiredString(item.uri)) throw new Error("예약 응답 형식이 올바르지 않습니다.");
    });
    validateList(dashboard.contracts, ["contract_id", "booking_id", "uri"], "금융 계약");
    dashboard.contracts.items.forEach(function (item) {
      if (!requiredString(item.contract_id) || !requiredString(item.booking_id) || !requiredString(item.uri)) throw new Error("금융 계약 응답 형식이 올바르지 않습니다.");
    });
    if (!isObject(dashboard.work_links) || !Array.isArray(dashboard.legacy_links)) throw new Error("업무 링크 응답이 올바르지 않습니다.");
    ["register", "manage", "calendar", "bookings", "contracts", "finance", "chat"].forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(dashboard.work_links, key)) throw new Error("업무 링크 응답에 " + key + " 항목이 없습니다.");
      var link = dashboard.work_links[key];
      if (!requiredString(link)) throw new Error("업무 링크 주소가 올바르지 않습니다.");
    });
    dashboard.legacy_links.forEach(function (link) {
      requireObject(link, "기존 서비스 링크");
      requireKeys(link, ["key", "label", "href"], "기존 서비스 링크");
      if (!requiredString(link.label) || !requiredString(link.href)) throw new Error("기존 서비스 링크 응답이 올바르지 않습니다.");
    });
    return dashboard;
  }
  function safePath(path) {
    if (!requiredString(path) || path.charAt(0) !== "/" || path.slice(0, 2) === "//" || /[\u0000-\u001f\\]/.test(path)) return null;
    try {
      var url = new URL(path, window.location.origin);
      if (url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) return null;
      return url.pathname + url.search + url.hash;
    } catch (error) {
      return null;
    }
  }
  function setFeedback(message, status) {
    el.feedback.textContent = message;
    el.feedback.dataset.state = status;
  }
  function formatInteger(number) { return new Intl.NumberFormat("ko-KR").format(number); }
  function formatWon(number) { return formatInteger(number) + "원"; }
  function node(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }
  function setBusy(isBusy) {
    state.loading = isBusy;
    el.refresh.disabled = isBusy;
    [el.summary, el.finance, el.applications, el.bookings, el.contracts, el.workLinks, el.legacyLinks].forEach(function (container) {
      container.setAttribute("aria-busy", isBusy ? "true" : "false");
    });
  }
  function skeleton(element, number) {
    element.replaceChildren();
    for (var i = 0; i < number; i += 1) element.appendChild(node("div", "skeleton"));
  }
  function empty(element, title, copy) {
    var box = node("div", "empty");
    box.appendChild(node("strong", "", title));
    box.appendChild(node("p", "", copy));
    element.replaceChildren(box);
  }
  function appendEmpty(element, title, copy) {
    var box = node("div", "empty");
    box.appendChild(node("strong", "", title));
    box.appendChild(node("p", "", copy));
    element.appendChild(box);
  }
  function renderSummary(data) {
    var fragment = document.createDocumentFragment();
    countFields.forEach(function (field) {
      var tile = node("div", "metric");
      tile.appendChild(node("span", "metric-label", field[1]));
      var value = node("strong", "metric-value");
      value.appendChild(document.createTextNode(formatInteger(data.counts[field[0]])));
      value.appendChild(node("small", "", field[2]));
      tile.appendChild(value);
      fragment.appendChild(tile);
    });
    el.summary.replaceChildren(fragment);
    el.scope.replaceChildren(node("span", "", "승인 사업장 컨텍스트"), node("strong", "", String(data.scope.context_id)));
    el.scope.hidden = false;
  }
  function renderFinance(finance) {
    var fragment = document.createDocumentFragment();
    moneyFields.forEach(function (field) {
      var row = node("div", "money-row");
      row.dataset.tone = field[3];
      var copy = node("div", "money-copy");
      copy.appendChild(node("strong", "", field[1]));
      copy.appendChild(node("span", "", field[2]));
      row.appendChild(copy);
      row.appendChild(node("strong", "amount", formatWon(finance[field[0]])));
      fragment.appendChild(row);
    });
    var note = node("p", "warning-note");
    note.appendChild(node("strong", "", "실제 지급·환불 실행액은 없습니다."));
    note.appendChild(document.createTextNode(" 표시된 모든 합계는 서버가 제공한 증빙·조건 기준 또는 검토액입니다. actual_money_executed: false."));
    el.finance.replaceChildren(fragment, note);
  }
  function statusPill(status) {
    var labels = {draft:"초안",submitted:"검토 요청",approved:"등록 승인",rejected:"반려",
      withdrawn:"철회",pending_operator:"운영자 확인 대기",awaiting_payment:"결제 증빙 대기",
      confirmed:"예약 확정",cancelled:"취소",cancelled_paid:"결제 후 취소 · 환불 검토",expired:"기한 만료"};
    var pill = node("span", "status", labels[status] || "상태 확인 필요");
    pill.dataset.status = status;
    return pill;
  }
  function addSafeLink(parent, label, path, className) {
    var href = safePath(path);
    if (!href) throw new Error("서버 제공 링크가 같은 출처의 안전한 경로가 아닙니다.");
    var link = node("a", className || "record-link", label);
    link.href = href;
    parent.appendChild(link);
    return link;
  }
  function listFootnote(list) {
    return node("p", "list-total", "최근 " + formatInteger(list.items.length) + "건 표시 · 전체 " + formatInteger(list.total) + "건" + (list.has_more ? " · 일부만 표시" : " · 전체 표시"));
  }
  function renderApplications(list) {
    el.applications.replaceChildren(listFootnote(list));
    if (!list.items.length) {
      appendEmpty(el.applications, "등록 신청 기록이 없습니다.", "현재 승인된 사업장 범위에서 서버가 반환한 신청이 없습니다.");
      return;
    }
    list.items.forEach(function (item) {
      var card = node("article", "record-card");
      card.dataset.applicationId = item.application_id;
      var top = node("div", "record-top");
      var copy = node("div");
      copy.appendChild(node("h3", "record-title", item.title));
      copy.appendChild(node("p", "record-id", "신청 " + item.application_id));
      top.appendChild(copy);
      top.appendChild(statusPill(item.status));
      card.appendChild(top);
      var facts = node("div", "record-meta");
      facts.appendChild(node("span", "", "등록 유형 " + (item.stay_kind === "lodging" ? "숙박형" : item.stay_kind === "non_lodging" ? "비숙박형" : "서버 분류 확인 필요")));
      facts.appendChild(node("span", "", "수정 차수 " + item.revision));
      card.appendChild(facts);
      var actions = node("div", "record-meta");
      addSafeLink(actions, "등록 내용 관리", item.manage_uri);
      addSafeLink(actions, "운영 캘린더", item.calendar_uri);
      card.appendChild(actions);
      el.applications.appendChild(card);
    });
  }
  function renderBookings(list) {
    el.bookings.replaceChildren(listFootnote(list));
    if (!list.items.length) {
      appendEmpty(el.bookings, "예약 기록이 없습니다.", "예약이 생성되면 서버 기록이 여기에 표시됩니다.");
      return;
    }
    list.items.forEach(function (item) {
      var card = node("article", "record-card");
      card.dataset.bookingId = item.booking_id;
      var top = node("div", "record-top");
      var copy = node("div");
      copy.appendChild(node("h3", "record-title", item.check_in + " — " + item.check_out));
      copy.appendChild(node("p", "record-id", "예약 " + item.booking_id + " · 신청 " + item.application_id));
      top.appendChild(copy);
      top.appendChild(statusPill(item.status));
      card.appendChild(top);
      var facts = node("div", "record-meta");
      facts.appendChild(node("span", "", "예약 금액"));
      facts.appendChild(node("strong", "", formatWon(item.total_krw)));
      card.appendChild(facts);
      addSafeLink(card, "예약 업무 열기", item.uri);
      el.bookings.appendChild(card);
    });
  }
  function renderContracts(list) {
    el.contracts.replaceChildren(listFootnote(list));
    if (!list.items.length) {
      appendEmpty(el.contracts, "금융 계약 기록이 없습니다.", "계약이 생성되면 서버 기록이 여기에 표시됩니다.");
      return;
    }
    list.items.forEach(function (item) {
      var card = node("article", "record-card");
      card.dataset.contractId = item.contract_id;
      card.appendChild(node("h3", "record-title", "금융 계약"));
      card.appendChild(node("p", "record-id", "계약 " + item.contract_id + " · 예약 " + item.booking_id));
      addSafeLink(card, "금융 기록 열기", item.uri);
      el.contracts.appendChild(card);
    });
  }
  var workLabels = {
    register: "숙박 등록", manage: "등록 관리", calendar: "운영 캘린더",
    bookings: "예약 관리", contracts: "계약 기록", finance: "금융 업무", chat: "문의 · 채팅"
  };
  function renderLinks(container, entries, labels, legacy) {
    var fragment = document.createDocumentFragment();
    entries.forEach(function (entry) {
      var label = legacy ? entry.label : labels[entry[0]];
      addSafeLink(fragment, label || entry[0], legacy ? entry.href : entry[1], "");
    });
    if (!entries.length) empty(container, "링크가 없습니다.", "서버가 제공한 링크가 없습니다.");
    else container.replaceChildren(fragment);
  }
  function render(data) {
    renderSummary(data);
    renderFinance(data.finance);
    renderApplications(data.applications);
    renderBookings(data.bookings);
    renderContracts(data.contracts);
    renderLinks(el.workLinks, Object.keys(data.work_links).map(function (key) { return [key, data.work_links[key]]; }), workLabels, false);
    renderLinks(el.legacyLinks, data.legacy_links, workLabels, true);
  }
  async function getJson(url, signal) {
    var response = await fetch(url, { method: "GET", credentials: "same-origin", headers: { Accept: "application/json" }, signal: signal });
    var payload;
    try { payload = await response.json(); }
    catch (error) { throw new Error(response.ok ? "서버 응답을 읽을 수 없습니다." : "서버 오류 (" + response.status + ")"); }
    if (!response.ok) throw new Error("서버 오류 (" + response.status + ")");
    if (!isObject(payload)) throw new Error("서버 응답 형식이 올바르지 않습니다.");
    return payload;
  }
  async function loadDashboard() {
    var requestId = ++state.requestId;
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    var signal = state.controller.signal;
    setBusy(true);
    el.scope.hidden = true;
    skeleton(el.summary, 3);
    skeleton(el.finance, 2);
    skeleton(el.applications, 2);
    skeleton(el.bookings, 2);
    skeleton(el.contracts, 1);
    skeleton(el.workLinks, 2);
    skeleton(el.legacyLinks, 2);
    setFeedback("승인된 운영 세션과 서버 요약을 확인하고 있습니다.", "loading");
    try {
      var session = await getJson(SESSION_API, signal);
      if (requestId !== state.requestId) return;
      if (session.ok !== true || typeof session.can_operator !== "boolean") throw new Error("운영 세션 응답 형식이 올바르지 않습니다.");
      if (session.can_operator !== true) {
        el.scope.hidden = true;
        empty(el.summary, "운영자 접근이 허용되지 않았습니다.", "활성 승인 사업장 컨텍스트가 확인되지 않아 원장 정보에 접근하지 않았습니다.");
        [el.finance, el.applications, el.bookings, el.contracts, el.workLinks, el.legacyLinks].forEach(function (container) {
          container.replaceChildren();
        });
        setFeedback("운영자 권한이 확인되지 않았습니다. 사업장 승인을 확인한 뒤 모드 선택에서 다시 전환해 주세요.", "forbidden");
        return;
      }
      if (session.context_id == null || !["string", "number"].includes(typeof session.context_id)) throw new Error("승인된 컨텍스트 정보를 확인할 수 없습니다.");
      var payload = await getJson(OVERVIEW_API, signal);
      if (requestId !== state.requestId) return;
      var data = validateOverview(payload);
      if (String(data.scope.context_id) !== String(session.context_id)) throw new Error("세션과 원장 응답의 승인 범위가 일치하지 않습니다.");
      render(data);
      setFeedback("승인된 사업장 범위의 서버 원장 정보를 불러왔습니다. 기록은 실행 또는 지급 완료를 뜻하지 않습니다.", "ready");
    } catch (error) {
      if (requestId !== state.requestId || error.name === "AbortError") return;
      el.scope.hidden = true;
      var message = error.message || "대시보드 정보를 불러오지 못했습니다.";
      empty(el.summary, "서버 정보를 표시할 수 없습니다.", "새로고침으로 다시 시도해 주세요. 실패한 값을 0으로 대체하지 않습니다.");
      [el.finance, el.applications, el.bookings, el.contracts, el.workLinks, el.legacyLinks].forEach(function (container) { container.replaceChildren(); });
      setFeedback(message + " 서버 오류와 누락된 데이터는 0으로 처리하지 않습니다.", "error");
    } finally {
      if (requestId === state.requestId) setBusy(false);
    }
  }
  el.refresh.addEventListener("click", loadDashboard);
  loadDashboard();
})();
