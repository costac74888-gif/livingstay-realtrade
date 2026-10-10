(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view") === "operator" ? "operator" : "consumer";
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const feedback = $("#workspace-feedback");
  const feedbackText = $(".feedback-text", feedback);
  const csrfMeta = document.querySelector('meta[name="hs2-csrf"]');
  let csrf = "";
  let currentThread = null;
  let threadItems = [];
  let bookingItems = [];
  let activeRequest = false;
  let requestText = null;
  let requestId = null;
  let failedMessage = null;
  let preferenceSaved = { email_enabled: false, sms_enabled: false };
  let busy = false;

  function setFeedback(message, state) {
    feedbackText.textContent = message;
    feedback.dataset.state = state;
  }

  function viewUrl(path) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set("view", view);
    return `${url.pathname}${url.search}`;
  }

  function errorMessage(code, status) {
    const known = {
      ACTIVE_MEMBER_REQUIRED: "이 역할의 활성 세션을 확인할 수 없습니다. 로그인 상태와 계정 권한을 확인해 주세요.",
      OPERATOR_CONTEXT_REQUIRED: "운영자 컨텍스트를 확인할 수 없습니다.",
      CSRF_REQUIRED: "보안 토큰을 확인할 수 없습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.",
      CHAT_NOT_FOUND: "이 대화는 현재 인증된 계정에서 확인할 수 없습니다.",
      OWNED_BOOKING_REQUIRED: "본인 예약으로 확인된 항목에서만 대화를 시작할 수 있습니다.",
      PUBLIC_LISTING_NOT_FOUND: "현재 문의 가능한 공개 숙소를 찾을 수 없습니다.",
      CHAT_IDEMPOTENCY_CONFLICT: "이전 전송 키에 다른 내용이 연결되어 있습니다. 내용을 확인하고 새로 시도해 주세요.",
      INVALID_CHAT_BODY: "메시지는 공백이 아닌 1~2,000자로 입력해 주세요.",
      WORKSPACE_RATE_LIMIT: "요청이 잠시 많습니다. 잠시 후 다시 확인해 주세요."
    };
    if (known[code]) return known[code];
    if (status === 403) return "인증 또는 권한 확인이 필요합니다.";
    if (status === 404) return "요청한 서버 기록을 찾을 수 없습니다.";
    if (status === 429) return "요청 횟수가 많습니다. 잠시 후 다시 확인해 주세요.";
    return "서버 기록을 불러오거나 저장하지 못했습니다. 연결 상태를 확인해 주세요.";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* Uniform error below. */ }
    if (!response.ok || !payload || payload.ok !== true) {
      const error = new Error(errorMessage(payload && payload.code, response.status));
      error.code = payload && payload.code;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function mutation(method, body) {
    return {
      method,
      headers: { "Content-Type": "application/json", "X-HS2-CSRF": csrf },
      body: JSON.stringify(body)
    };
  }

  function clearToEmpty(node, message) {
    node.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty-inline";
    empty.textContent = message;
    node.append(empty);
    node.setAttribute("aria-busy", "false");
  }

  function timeLabel(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime())
      ? new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date)
      : "시간 정보 없음";
  }

  function statusName(status) {
    return ({
      pending_operator: "운영자 확인 대기",
      awaiting_payment: "결제 대기",
      confirmed: "예약 확정",
      rejected: "운영자 거절",
      cancelled: "취소됨",
      expired: "기한 만료"
    })[status] || "상태 확인 필요";
  }

  function money(booking) {
    const amount = booking && booking.quote && booking.quote.total_krw;
    return Number.isSafeInteger(amount) && amount > 0
      ? `${new Intl.NumberFormat("ko-KR").format(amount)}원`
      : "금액 확인 필요";
  }

  function safeSameOriginUri(value) {
    if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return null;
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin) return null;
      return `${url.pathname}${url.search}${url.hash}`;
    } catch (_) { return null; }
  }

  function addSafeMessageText(parent, body) {
    const pattern = /https?:\/\/[^\s<>"']+/gi;
    let cursor = 0;
    for (const match of body.matchAll(pattern)) {
      const index = match.index;
      parent.append(document.createTextNode(body.slice(cursor, index)));
      let raw = match[0];
      let trailing = "";
      while (/[),.!?;:]$/.test(raw)) {
        trailing = raw.slice(-1) + trailing;
        raw = raw.slice(0, -1);
      }
      let href = null;
      try {
        const url = new URL(raw);
        if (url.origin === window.location.origin) href = `${url.pathname}${url.search}${url.hash}`;
      } catch (_) { /* Keep untrusted or malformed URLs as text. */ }
      if (href) {
        const link = document.createElement("a");
        link.href = href;
        link.rel = "noopener";
        link.textContent = raw;
        parent.append(link);
      } else parent.append(document.createTextNode(raw));
      if (trailing) parent.append(document.createTextNode(trailing));
      cursor = index + match[0].length;
    }
    parent.append(document.createTextNode(body.slice(cursor)));
  }

  function validThread(thread) {
    return thread && typeof thread.thread_id === "string" && uuid.test(thread.thread_id) &&
      (thread.booking_id === null || thread.booking_id === undefined || uuid.test(thread.booking_id)) &&
      Number.isSafeInteger(thread.unread) && thread.unread >= 0;
  }

  function renderThreads(items) {
    if (!Array.isArray(items)) throw new Error("대화 목록 응답을 확인할 수 없습니다.");
    threadItems = items.filter(validThread);
    const list = $("#threads-list");
    list.replaceChildren();
    if (!threadItems.length) {
      clearToEmpty(list, "아직 서버에 기록된 대화가 없습니다.");
      return;
    }
    threadItems.forEach((thread) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "thread-card";
      button.dataset.threadId = thread.thread_id;
      button.setAttribute("aria-current", String(thread.thread_id === currentThread));
      const top = document.createElement("span");
      top.className = "thread-card-top";
      const title = document.createElement("strong");
      title.textContent = thread.booking_id ? "예약 관련 대화" : "숙소 문의";
      top.append(title);
      if (thread.unread > 0) {
        const unread = document.createElement("span");
        unread.className = "unread-count";
        unread.textContent = `${thread.unread} 새 기록`;
        top.append(unread);
      }
      const subtitle = document.createElement("small");
      subtitle.textContent = thread.booking_id ? `예약 · ${thread.booking_id.slice(0, 8)}` : `대화 · ${thread.thread_id.slice(0, 8)}`;
      button.append(top, subtitle);
      button.addEventListener("click", () => selectThread(thread.thread_id));
      list.append(button);
    });
    list.setAttribute("aria-busy", "false");
  }

  function renderMessages(items) {
    const list = $("#messages-list");
    list.replaceChildren();
    if (!Array.isArray(items)) throw new Error("메시지 목록 응답을 확인할 수 없습니다.");
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-composition";
      const orbit = document.createElement("span");
      orbit.className = "empty-orbit";
      orbit.setAttribute("aria-hidden", "true");
      const heading = document.createElement("strong");
      heading.textContent = "아직 메시지가 없습니다";
      const copy = document.createElement("p");
      copy.textContent = "필요한 내용을 남기면 이 대화에 서버 기록으로 저장됩니다.";
      empty.append(orbit, heading, copy);
      list.append(empty);
      list.setAttribute("aria-busy", "false");
      return;
    }
    items.forEach((message) => {
      if (!message || typeof message.message_id !== "string" || !uuid.test(message.message_id) ||
          typeof message.body !== "string" || typeof message.mine !== "boolean") return;
      const bubble = document.createElement("article");
      bubble.className = `message-bubble${message.mine ? " mine" : ""}`;
      bubble.dataset.messageId = message.message_id;
      addSafeMessageText(bubble, message.body);
      const stamp = document.createElement("time");
      stamp.className = "message-time";
      stamp.textContent = timeLabel(message.at);
      bubble.append(stamp);
      list.append(bubble);
    });
    list.scrollTop = list.scrollHeight;
    list.setAttribute("aria-busy", "false");
  }

  async function loadMessages(threadId) {
    $("#messages-list").setAttribute("aria-busy", "true");
    $("#messages-list").replaceChildren();
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton-row";
    $("#messages-list").append(skeleton);
    try {
      const result = await api(viewUrl(`/hs2/workspace/api/threads/${encodeURIComponent(threadId)}/messages`));
      if (currentThread !== threadId) return;
      renderMessages(result.items);
      if (result.items.length > 0) {
        const lastMessage = result.items[result.items.length - 1];
        if (!lastMessage || typeof lastMessage.message_id !== "string" || !uuid.test(lastMessage.message_id)) {
          throw new Error("읽음 위치를 마지막 서버 메시지에서 확인할 수 없습니다.");
        }
        await api(viewUrl(`/hs2/workspace/api/threads/${encodeURIComponent(threadId)}/read`), mutation("POST", {
          through_message_id: lastMessage.message_id
        }));
        await loadThreads(false);
      }
    } catch (error) {
      if (currentThread !== threadId) return;
      clearToEmpty($("#messages-list"), error.message);
      setFeedback(error.message, "error");
    }
  }

  async function selectThread(threadId) {
    if (!uuid.test(threadId) || !threadItems.some((item) => item.thread_id === threadId)) return;
    currentThread = threadId;
    const selected = threadItems.find((item) => item.thread_id === threadId);
    $("#selected-thread-title").textContent = selected && selected.booking_id ? "예약 관련 대화" : "숙소 문의";
    $("#message-body").disabled = false;
    $("#send-message").disabled = false;
    $("#threads-list").querySelectorAll("[data-thread-id]").forEach((card) => {
      card.setAttribute("aria-current", String(card.dataset.threadId === threadId));
    });
    if (requestText !== null && failedMessage !== null && failedMessage.threadId !== threadId) {
      requestText = null;
      requestId = null;
      failedMessage = null;
    }
    await loadMessages(threadId);
  }

  async function loadThreads(autoselect = true) {
    const result = await api(viewUrl("/hs2/workspace/api/threads"));
    renderThreads(result.items);
    const requestedThread = params.get("thread_id");
    const validRequested = uuid.test(requestedThread || "") && threadItems.some((item) => item.thread_id === requestedThread);
    const preferred = validRequested ? requestedThread : currentThread && threadItems.some((item) => item.thread_id === currentThread) ? currentThread : null;
    if (autoselect && preferred) await selectThread(preferred);
    else if (!threadItems.length) {
      currentThread = null;
      $("#selected-thread-title").textContent = "대화를 선택해 주세요";
      $("#message-body").disabled = true;
      $("#send-message").disabled = true;
      clearToEmpty($("#messages-list"), "목록에서 대화를 선택하면 서버 메시지를 확인할 수 있습니다.");
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const body = $("#message-body").value;
    if (activeRequest || !currentThread || !body.trim()) return;
    if (requestText !== body || !requestId) {
      requestText = body;
      requestId = crypto.randomUUID();
    }
    const threadId = currentThread;
    activeRequest = true;
    $("#send-message").disabled = true;
    setFeedback("메시지를 서버 기록에 저장하고 있습니다.", "loading");
    try {
      await api(viewUrl(`/hs2/workspace/api/threads/${encodeURIComponent(threadId)}/messages`), mutation("POST", { body, request_id: requestId }));
      $("#message-body").value = "";
      requestText = null;
      requestId = null;
      failedMessage = null;
      await loadMessages(threadId);
      setFeedback("메시지가 서버 대화 기록에 저장되었습니다. 실제 발송을 의미하지 않습니다.", "ready");
    } catch (error) {
      failedMessage = { threadId, body, requestId };
      setFeedback(`${error.message} 입력은 그대로 유지했습니다. 같은 내용을 다시 보내면 같은 요청 키로 재시도합니다.`, "error");
    } finally {
      activeRequest = false;
      $("#send-message").disabled = !currentThread;
    }
  }

  function renderBookings(items) {
    if (!Array.isArray(items)) throw new Error("예약 목록 응답을 확인할 수 없습니다.");
    bookingItems = items.filter((booking) => booking && uuid.test(booking.booking_id || "") &&
      uuid.test(booking.public_id || "") && typeof booking.status === "string" &&
      typeof booking.check_in === "string" && typeof booking.check_out === "string");
    const list = $("#my-bookings-list");
    list.replaceChildren();
    if (!bookingItems.length) {
      clearToEmpty(list, "소비자 예약 API에 표시할 본인 예약이 없습니다.");
      return;
    }
    bookingItems.forEach((booking) => {
      const card = document.createElement("article");
      card.className = "booking-record";
      card.dataset.bookingId = booking.booking_id;
      const main = document.createElement("div");
      main.className = "record-main";
      const name = document.createElement("strong");
      name.textContent = `숙소 예약 · ${booking.booking_id.slice(0, 8)}`;
      const detail = document.createElement("p");
      detail.textContent = `${booking.check_in} – ${booking.check_out} · ${booking.guests}명`;
      main.append(name, detail);
      const status = document.createElement("span");
      status.className = "status-tag";
      status.dataset.tone = booking.status === "pending_operator" || booking.status === "awaiting_payment" ? "pending" : booking.status === "rejected" || booking.status === "cancelled" || booking.status === "expired" ? "alert" : "normal";
      status.textContent = statusName(booking.status);
      const total = document.createElement("div");
      total.className = "record-total";
      total.textContent = money(booking);
      const actions = document.createElement("div");
      actions.className = "record-actions";
      const bookingLink = document.createElement("a");
      bookingLink.href = `/hs2/bookings/?view=consumer&booking_id=${encodeURIComponent(booking.booking_id)}`;
      bookingLink.textContent = "예약 기록";
      const financeLink = document.createElement("a");
      financeLink.href = `/hs2/finance/?booking_id=${encodeURIComponent(booking.booking_id)}`;
      financeLink.textContent = "금융 조건";
      const inquiry = document.createElement("button");
      inquiry.type = "button";
      inquiry.textContent = "운영자에게 문의";
      inquiry.addEventListener("click", () => openThread({ booking_id: booking.booking_id }));
      actions.append(bookingLink, financeLink, inquiry);
      card.append(main, total, status, actions);
      list.append(card);
    });
    list.setAttribute("aria-busy", "false");
  }

  function renderFavorites(items) {
    if (!Array.isArray(items)) throw new Error("관심 숙소 응답을 확인할 수 없습니다.");
    const list = $("#favorites-list");
    list.replaceChildren();
    if (!items.length) {
      clearToEmpty(list, "저장한 숙소가 없습니다. 숙소 상세에서 관심 숙소로 저장할 수 있습니다.");
      return;
    }
    items.forEach((entry) => {
      if (!entry || typeof entry.public_id !== "string" || !uuid.test(entry.public_id)) return;
      const card = document.createElement("article");
      card.className = "favorite-card";
      card.dataset.publicId = entry.public_id;
      const copy = document.createElement("div");
      copy.className = "favorite-copy";
      const title = document.createElement("strong");
      const meta = document.createElement("small");
      if (entry.available === true && entry.item && typeof entry.item.title === "string") {
        title.textContent = entry.item.title;
        meta.textContent = "공개 숙소 정보";
      } else {
        title.textContent = "현재 공개되지 않는 숙소";
        meta.textContent = "비공개 정보는 표시하지 않습니다.";
      }
      copy.append(title, meta);
      const actions = document.createElement("div");
      actions.className = "favorite-actions";
      if (entry.available === true) {
        const link = document.createElement("a");
        const safeUri = safeSameOriginUri(entry.uri);
        if (safeUri) {
          link.href = safeUri;
          link.textContent = "상세 보기";
          actions.append(link);
        }
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "저장 해제";
      remove.addEventListener("click", () => setFavorite(entry.public_id, false));
      actions.append(remove);
      card.append(copy, actions);
      list.append(card);
    });
    list.setAttribute("aria-busy", "false");
  }

  async function setFavorite(publicId, enabled) {
    if (!uuid.test(publicId)) return;
    try {
      await api(`/hs2/workspace/api/favorites/${encodeURIComponent(publicId)}`, mutation("PUT", { enabled }));
      await loadFavorites();
      setFeedback(enabled ? "관심 숙소를 저장했습니다." : "관심 숙소 저장을 해제했습니다.", "ready");
    } catch (error) { setFeedback(error.message, "error"); }
  }

  const notificationLabels = {
    chat: "새 메시지 기록",
    booking_pending: "예약 신청 기록",
    booking_approved: "예약 승인 기록",
    booking_rejected: "예약 거절 기록",
    booking_cancelled: "예약 취소 기록",
    booking_expired: "예약 만료 기록"
  };

  function renderNotifications(items) {
    if (!Array.isArray(items)) throw new Error("알림 목록 응답을 확인할 수 없습니다.");
    const list = $("#notifications-list");
    list.replaceChildren();
    if (!items.length) {
      clearToEmpty(list, "서버에 기록된 알림이 없습니다.");
      return;
    }
    items.forEach((item) => {
      if (!item || typeof item.notification_id !== "string" || !uuid.test(item.notification_id)) return;
      const card = document.createElement("article");
      card.className = "notification-card";
      card.dataset.notificationId = item.notification_id;
      const copy = document.createElement("div");
      copy.className = "notification-copy";
      const title = document.createElement("strong");
      title.textContent = notificationLabels[item.kind] || "서버 알림 기록";
      const note = document.createElement("p");
      note.textContent = "알림 기록이며 이메일 또는 문자 전달 완료를 뜻하지 않습니다.";
      const when = document.createElement("small");
      when.textContent = timeLabel(item.at);
      copy.append(title, note, when);
      const actions = document.createElement("div");
      actions.className = "notification-actions";
      if (!item.read) {
        const read = document.createElement("button");
        read.className = "notification-action";
        read.type = "button";
        read.textContent = "읽음 처리";
        read.addEventListener("click", () => markNotification(item.notification_id));
        actions.append(read);
      }
      const safeUri = safeSameOriginUri(item.uri);
      if (safeUri) {
        const link = document.createElement("a");
        link.className = "notification-action";
        link.href = safeUri;
        link.textContent = "기록 열기";
        actions.append(link);
      }
      const deliveries = document.createElement("div");
      deliveries.className = "delivery-list";
      const rows = Array.isArray(item.deliveries) ? item.deliveries : [];
      rows.forEach((delivery) => {
        if (!delivery || typeof delivery.delivery_id !== "string" || !uuid.test(delivery.delivery_id)) return;
        const status = typeof delivery.status === "string" ? delivery.status : "unknown";
        const tag = document.createElement("span");
        tag.className = "delivery-tag";
        tag.dataset.status = status;
        const channel = delivery.channel === "email" ? "이메일" : delivery.channel === "sms" ? "문자" : "채널";
        const labels = { pending: "대기", failed: "실패", suppressed: "억제", sandbox_sent: "샌드박스 처리", sent: "처리됨" };
        tag.textContent = `${channel} · ${labels[status] || "상태 확인 필요"}${status === "sandbox_sent" ? " (실제 발송 아님)" : ""}`;
        deliveries.append(tag);
        if (status === "failed" && Number.isSafeInteger(delivery.attempts) && delivery.attempts < 5) {
          const retry = document.createElement("button");
          retry.type = "button";
          retry.className = "notification-action";
          retry.textContent = "재시도";
          retry.addEventListener("click", () => retryDelivery(delivery.delivery_id));
          actions.append(retry);
        }
      });
      copy.append(deliveries);
      card.append(copy, actions);
      list.append(card);
    });
    list.setAttribute("aria-busy", "false");
  }

  async function loadThreadsAndBookings() {
    const sections = [
      [loadThreads(true), "threads-list"],
    ];
    if (view === "consumer") sections.push(
      [loadBookings(), "my-bookings-list"],
      [loadFavorites(), "favorites-list"],
      [loadNotifications(), "notifications-list"],
      [loadPreferences(), null]
    );
    const tasks = sections.map(([promise, listId]) => Promise.resolve(promise).catch((error) => {
      if (listId) {
        const list = document.getElementById(listId);
        clearToEmpty(list, error.message || "서버 기록을 불러오지 못했습니다.");
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "notification-action";
        retry.textContent = "다시 시도";
        retry.addEventListener("click", initialize);
        list.append(retry);
      }
      throw error;
    }));
    const results = await Promise.allSettled(tasks);
    const failure = results.find((result) => result.status === "rejected");
    if (failure) setFeedback(failure.reason.message || "일부 서버 기록을 불러오지 못했습니다.", "error");
    else setFeedback(view === "operator" ? "승인 운영자 범위의 대화 기록을 확인했습니다." : "소비자 세션의 대화·예약·알림 기록을 확인했습니다.", "ready");
    showInquiryEntry();
  }

  async function loadBookings() {
    $("#my-bookings-list").setAttribute("aria-busy", "true");
    const result = await api("/hs2/bookings/api/consumer");
    renderBookings(result.bookings);
  }

  async function loadFavorites() {
    $("#favorites-list").setAttribute("aria-busy", "true");
    const result = await api("/hs2/workspace/api/favorites");
    renderFavorites(result.items);
  }

  async function loadNotifications() {
    $("#notifications-list").setAttribute("aria-busy", "true");
    const result = await api("/hs2/workspace/api/notifications");
    renderNotifications(result.items);
  }

  async function loadPreferences() {
    const result = await api("/hs2/workspace/api/preferences");
    if (!result.preferences || typeof result.preferences.email_enabled !== "boolean" || typeof result.preferences.sms_enabled !== "boolean") {
      throw new Error("알림 설정 서버 응답을 확인할 수 없습니다.");
    }
    preferenceSaved = { email_enabled: result.preferences.email_enabled, sms_enabled: result.preferences.sms_enabled };
    $("#email-enabled").checked = preferenceSaved.email_enabled;
    $("#sms-enabled").checked = preferenceSaved.sms_enabled;
    $("#email-enabled").disabled = false;
    $("#sms-enabled").disabled = false;
    $("#save-preferences").disabled = false;
  }

  async function markNotification(key) {
    try {
      await api(`/hs2/workspace/api/notifications/${encodeURIComponent(key)}/read`, mutation("POST", {}));
      await loadNotifications();
      setFeedback("알림을 읽음으로 기록했습니다.", "ready");
    } catch (error) { setFeedback(error.message, "error"); }
  }

  async function retryDelivery(key) {
    try {
      const result = await api(`/hs2/workspace/api/deliveries/${encodeURIComponent(key)}/retry`, mutation("POST", {}));
      if (!result || result.status !== "pending") throw new Error("재시도 상태를 서버 응답에서 확인할 수 없습니다.");
      await loadNotifications();
      setFeedback("발송 재시도가 대기 상태로 기록되었습니다. 실제 이메일·문자는 발송되지 않습니다.", "ready");
    } catch (error) { setFeedback(error.message, "error"); }
  }

  async function savePreferences(event) {
    event.preventDefault();
    const values = { email_enabled: $("#email-enabled").checked, sms_enabled: $("#sms-enabled").checked };
    $("#save-preferences").disabled = true;
    try {
      const result = await api("/hs2/workspace/api/preferences", mutation("PUT", values));
      if (!result.preferences || result.preferences.email_enabled !== values.email_enabled || result.preferences.sms_enabled !== values.sms_enabled) {
        throw new Error("서버가 저장한 설정과 현재 선택이 일치하지 않습니다.");
      }
      preferenceSaved = values;
      setFeedback("알림 채널 동의를 저장했습니다. 라이브 발송은 활성화되어 있지 않습니다.", "ready");
    } catch (error) {
      $("#email-enabled").checked = preferenceSaved.email_enabled;
      $("#sms-enabled").checked = preferenceSaved.sms_enabled;
      setFeedback(error.message, "error");
    } finally { $("#save-preferences").disabled = false; }
  }

  function showInquiryEntry() {
    const entry = $("#inquiry-entry");
    entry.replaceChildren();
    if (view !== "consumer") return;
    const listingId = params.get("public_id");
    const bookingId = params.get("booking_id");
    let command = null;
    let title = "";
    let copy = "";
    if (uuid.test(listingId || "")) {
      command = { public_id: listingId };
      title = "이 공개 숙소에 문의";
      copy = "공개 숙소 참조를 사용해 대화를 시작합니다. 버튼을 누르기 전에는 문의를 만들지 않습니다.";
    } else if (uuid.test(bookingId || "") && bookingItems.some((booking) => booking.booking_id === bookingId)) {
      command = { booking_id: bookingId };
      title = "이 예약에 대해 문의";
      copy = "본인 예약으로 확인된 기록에 연결합니다. 버튼을 누르기 전에는 대화를 만들지 않습니다.";
    }
    if (!command) return;
    const text = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = title;
    text.append(strong, document.createTextNode(copy));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry-action";
    button.textContent = "문의 대화 시작";
    button.addEventListener("click", () => openThread(command));
    entry.append(text, button);
    entry.hidden = false;
  }

  async function openThread(reference) {
    if (view !== "consumer" || !reference || Object.keys(reference).length !== 1 ||
        (reference.public_id && !uuid.test(reference.public_id)) ||
        (reference.booking_id && !bookingItems.some((booking) => booking.booking_id === reference.booking_id))) return;
    setFeedback("요청한 공개 숙소 또는 본인 예약 참조를 확인하고 대화를 여는 중입니다.", "loading");
    try {
      const result = await api(viewUrl("/hs2/workspace/api/threads"), mutation("POST", reference));
      if (!result || !uuid.test(result.thread_id || "")) throw new Error("대화 식별자를 서버 응답에서 확인할 수 없습니다.");
      currentThread = result.thread_id;
      await loadThreads(false);
      await selectThread(result.thread_id);
      setFeedback("대화가 서버에서 확인되었습니다. 메시지 전송은 별도의 명시적 동작입니다.", "ready");
    } catch (error) { setFeedback(error.message, "error"); }
  }

  async function initialize() {
    if (busy) return;
    busy = true;
    csrf = "";
    setFeedback("인증된 세션과 기록을 확인하고 있습니다.", "loading");
    document.querySelectorAll("[data-consumer-only]").forEach((node) => { node.hidden = view !== "consumer"; });
    $("#scope-label").textContent = view === "operator" ? "승인 운영자 · 담당 대화 범위" : "소비자 · 본인 기록 범위";
    try {
      const meta = await api(viewUrl("/hs2/workspace/api/meta"));
      if (meta.view !== view || typeof meta.csrf !== "string" || !meta.csrf || meta.live_delivery_enabled !== false) {
        throw new Error("인증 세션 또는 발송 제한 상태를 서버 응답에서 확인할 수 없습니다.");
      }
      csrf = meta.csrf;
      if (csrfMeta) csrfMeta.content = csrf;
      await loadThreadsAndBookings();
    } catch (error) {
      setFeedback(`워크스페이스가 차단되었습니다. ${error.message || "인증 세션을 확인할 수 없습니다."}`, "error");
      ["threads-list", "messages-list", "my-bookings-list", "favorites-list", "notifications-list"].forEach((id) => {
        const node = document.getElementById(id);
        if (node) clearToEmpty(node, "인증 실패로 서버 기록을 표시하지 않습니다.");
      });
      $("#message-body").disabled = true;
      $("#send-message").disabled = true;
      $("#email-enabled").disabled = true;
      $("#sms-enabled").disabled = true;
      $("#save-preferences").disabled = true;
    } finally { busy = false; }
  }

  $("#workspace-refresh").addEventListener("click", initialize);
  $("#message-form").addEventListener("submit", sendMessage);
  $("#preferences-form").addEventListener("submit", savePreferences);
  initialize();
})();
