(() => {
  "use strict";

  const form = document.getElementById("help-form");
  const searchInput = document.getElementById("help-search");
  const audienceSelect = document.getElementById("help-audience");
  const clearButton = document.getElementById("help-clear");
  const feedback = document.getElementById("help-feedback");
  const faqResults = document.getElementById("faq-results");
  const guides = document.getElementById("help-guides");
  const policies = document.getElementById("help-policies");
  const publicationLabel = document.getElementById("help-publication-label");
  const liveStatus = document.getElementById("help-live-status");
  const version = document.getElementById("help-version");
  let requestNumber = 0;
  let activeController = null;

  function setFeedback(state, message) {
    feedback.dataset.state = state;
    feedback.textContent = message;
  }

  function clearContent() {
    faqResults.replaceChildren();
    guides.replaceChildren();
    policies.replaceChildren();
    publicationLabel.textContent = "";
    liveStatus.textContent = "";
    version.textContent = "";
  }

  function validText(value) {
    return typeof value === "string" ? value : "";
  }

  function sameOriginHref(uri) {
    if (typeof uri !== "string" || !uri.startsWith("/") || uri.startsWith("//")) return null;
    try {
      const resolved = new URL(uri, window.location.origin);
      return resolved.origin === window.location.origin ? `${resolved.pathname}${resolved.search}${resolved.hash}` : null;
    } catch (_) {
      return null;
    }
  }

  function appendResourceLink(parent, uri, label) {
    const href = sameOriginHref(uri);
    if (!href) return;
    const link = document.createElement("a");
    link.className = "resource-link";
    link.href = href;
    link.textContent = label;
    parent.append(link);
  }

  function renderFaqs(items) {
    const valid = items.filter((item) =>
      item && typeof item.id === "string" && typeof item.question === "string" &&
      typeof item.answer === "string" && typeof item.topic === "string"
    );
    if (!valid.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "일치하는 안내가 없습니다.";
      const copy = document.createElement("p");
      copy.textContent = "검색어를 바꾸거나 전체 안내를 선택해 다시 확인해 주세요.";
      empty.append(title, copy);
      faqResults.append(empty);
      return;
    }
    valid.forEach((item, index) => {
      const details = document.createElement("details");
      details.className = "faq-item";
      details.dataset.faqId = item.id;
      details.style.animationDelay = `${Math.min(index, 8) * 35}ms`;

      const summary = document.createElement("summary");
      const number = document.createElement("span");
      number.className = "faq-index";
      number.textContent = String(index + 1).padStart(2, "0");
      const question = document.createElement("span");
      question.className = "faq-title";
      question.textContent = item.question;
      const chevron = document.createElement("span");
      chevron.className = "faq-chevron";
      chevron.setAttribute("aria-hidden", "true");
      chevron.textContent = "+";
      summary.append(number, question, chevron);

      const answer = document.createElement("p");
      answer.className = "faq-answer";
      answer.textContent = item.answer;
      details.append(summary, answer);
      faqResults.append(details);
    });
  }

  function renderGuides(items) {
    items.filter((item) => item && typeof item.title === "string" && Array.isArray(item.steps))
      .forEach((item) => {
        const card = document.createElement("article");
        card.className = "guide-card";
        const title = document.createElement("h3");
        title.className = "guide-title";
        title.textContent = item.title;
        const list = document.createElement("ol");
        list.className = "guide-steps";
        item.steps.forEach((step) => {
          if (typeof step !== "string") return;
          const li = document.createElement("li");
          li.textContent = step;
          list.append(li);
        });
        card.append(title, list);
        appendResourceLink(card, item.uri, "관련 화면 열기 ↗");
        guides.append(card);
      });
  }

  function renderPolicies(items) {
    items.filter((item) => item && typeof item.title === "string" && typeof item.body === "string")
      .forEach((item) => {
        const card = document.createElement("article");
        card.className = "policy-card";
        const title = document.createElement("h3");
        title.className = "policy-title";
        title.textContent = item.title;
        const body = document.createElement("p");
        body.className = "policy-body";
        body.textContent = item.body;
        card.append(title, body);
        appendResourceLink(card, item.uri, "기존 문서 확인 ↗");
        policies.append(card);
      });
  }

  async function loadContent() {
    const currentRequest = ++requestNumber;
    if (activeController) activeController.abort();
    activeController = new AbortController();
    const query = searchInput.value.trim().slice(0, 80);
    const audience = audienceSelect.value;
    const params = new URLSearchParams({ audience, q: query });
    clearContent();
    setFeedback("loading", "안내 내용을 확인하고 있습니다.");
    faqResults.setAttribute("aria-busy", "true");

    try {
      const response = await fetch(`/hs2/help/api/content?${params.toString()}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: activeController.signal
      });
      if (!response.ok) throw new Error("HELP_REQUEST_FAILED");
      const data = await response.json();
      if (currentRequest !== requestNumber) return;
      if (!data || data.ok !== true || !Array.isArray(data.faqs) ||
          !Array.isArray(data.guides) || !Array.isArray(data.policies) ||
          typeof data.version !== "string" ||
          typeof data.live_operations_approved !== "boolean") {
        throw new Error("HELP_RESPONSE_INVALID");
      }

      renderFaqs(data.faqs);
      renderGuides(data.guides);
      renderPolicies(data.policies);
      publicationLabel.textContent = `게시 상태: ${validText(data.publication) || "확인되지 않음"}`;
      liveStatus.textContent = data.live_operations_approved
        ? "라이브 운영 승인: 승인됨"
        : "라이브 운영 승인: 승인되지 않음";
      version.textContent = `콘텐츠 버전 · ${data.version}`;
      const count = data.faqs.length;
      setFeedback("ready", query
        ? `“${query}” 검색 결과 ${count}건 · 서버 안내 기준`
        : `서버 안내 ${count}건을 확인했습니다.`);
    } catch (error) {
      if (currentRequest !== requestNumber || error.name === "AbortError") return;
      clearContent();
      setFeedback("error", "안내 내용을 불러오지 못했습니다. 검색어는 유지됩니다. 연결을 확인한 뒤 다시 시도해 주세요.");
      const retry = document.createElement("button");
      retry.className = "retry-button";
      retry.type = "button";
      retry.textContent = "다시 시도";
      retry.addEventListener("click", loadContent, { once: true });
      feedback.append(" ", retry);
    } finally {
      if (currentRequest === requestNumber) {
        faqResults.removeAttribute("aria-busy");
        activeController = null;
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    loadContent();
  });
  audienceSelect.addEventListener("change", loadContent);
  clearButton.addEventListener("click", () => {
    searchInput.value = "";
    loadContent();
    searchInput.focus();
  });

  loadContent();
})();
