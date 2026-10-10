(() => {
  "use strict";
  const API = "/hs2/listings";
  const $ = (selector) => document.querySelector(selector);
  const list = $("#reviewList");
  const detail = $("#reviewDetail");
  const feedback = $("#adminFeedback");
  const translations = {
    AUTH_REQUIRED: "운영자 인증 정보를 확인할 수 없습니다.",
    ADMIN_REQUIRED: "관리자 권한이 필요합니다. 관리자 계정으로 로그인해 주세요.",
    APPROVED_BUSINESS_REQUIRED: "운영자 또는 사업장 상태를 다시 확인해 주세요.",
    ACTIVE_MEMBER_REQUIRED: "등록 운영자의 계정이 비활성 상태입니다.",
    CSRF_REQUIRED: "보안 확인이 만료되었습니다. 새로고침한 뒤 다시 시도해 주세요.",
    STALE_REVISION: "선택한 등록이 변경되었습니다. 목록을 새로고침한 뒤 최신 내용을 다시 확인해 주세요.",
    RIGHTS_CONFIRMATION_REQUIRED: "승인에는 등록 권한 확인이 필요합니다.",
    DISCLOSURE_CONFIRMATION_REQUIRED: "승인에는 제한 공개 범위 확인이 필요합니다.",
    EXPLICIT_REVIEW_REQUIRED: "승인에는 등록 권한과 제한 공개 범위 확인이 모두 필요합니다.",
    REVIEW_NOTE_REQUIRED: "승인·반려 결과 메모를 1자 이상 입력해 주세요.",
    REJECTION_NOTE_REQUIRED: "반려 사유를 메모에 입력해 주세요.",
    SUBMITTED_APPLICATION_REQUIRED: "검토 대기 중인 등록만 승인 또는 반려할 수 있습니다.",
    ACTIVE_SPACE_CONFLICT: "같은 확인 건물에 중복되는 공간 등록이 이미 승인되어 있습니다.",
    APPLICATION_NOT_FOUND: "등록이 목록에서 사라졌습니다. 최신 목록을 다시 불러와 주세요.",
    PHOTO_NOT_FOUND: "비공개 사진을 불러올 수 없습니다."
  };
  let csrf = "";
  let applications = [];
  let selectedId = null;
  let busy = false;
  function el(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function setFeedback(message, tone = "error") {
    feedback.textContent = message;
    feedback.dataset.tone = tone;
    feedback.hidden = !message;
  }
  function translate(error) {
    if (error?.code && translations[error.code]) return translations[error.code];
    if (error?.code) return `처리 중 오류가 발생했습니다 (${error.code}). 입력한 검토 메모는 유지됩니다.`;
    return "서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.";
  }
  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set("Content-Type", "application/json");
    if (options.method && options.method !== "GET") headers.set("X-HS2-CSRF", csrf);
    const response = await fetch(`${API}${path}`, { ...options, headers, credentials: "same-origin" });
    const json = (response.headers.get("content-type") || "").includes("application/json") ? await response.json() : {};
    if (!response.ok || json.ok === false) {
      const error = new Error(json.message || "Request failed");
      error.code = json.code || `HTTP_${response.status}`;
      throw error;
    }
    return json;
  }
  function statusName(value) {
    return ({ submitted: "검토 대기", approved: "승인", rejected: "반려", draft: "초안", withdrawn: "철회" })[value] || "확인 필요";
  }
  function addDetail(grid, label, value) {
    const item = el("div", "detail-item");
    item.append(el("small", "", label), el("strong", "", value === null || value === undefined || value === "" ? "미기재" : String(value)));
    grid.append(item);
  }
  function renderList() {
    list.replaceChildren();
    const submitted = applications.filter((app) => app.status === "submitted");
    $("#queueCount").textContent = `${submitted.length}건`;
    if (!submitted.length) {
      list.append(el("div", "empty", "검토 대기 중인 등록이 없습니다. 목록 새로고침으로 최신 상태를 확인할 수 있습니다."));
      return;
    }
    submitted.forEach((app) => {
      const button = el("button", "review-row");
      button.type = "button";
      button.setAttribute("aria-current", String(selectedId === app.id));
      button.append(el("strong", "", app.payload?.title || "제목 없는 등록"));
      button.append(el("span", "", `${app.payload?.space_label || "공간 이름 없음"} · v${app.revision}`));
      button.append(el("span", "", `운영자 선언 형태: ${app.payload?.stay_kind === "lodging" ? "숙박형" : app.payload?.stay_kind === "non_lodging" ? "비숙박형" : "미선택"}`));
      button.addEventListener("click", () => { selectedId = app.id; renderList(); renderDetail(app); });
      list.append(button);
    });
  }
  async function loadAdminPhoto(photoId, image) {
    try {
      const response = await fetch(`${API}/admin/photos/${encodeURIComponent(photoId)}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("photo unavailable");
      const blob = await response.blob();
      image.src = URL.createObjectURL(blob);
    } catch {
      image.alt = "비공개 사진을 불러오지 못했습니다";
      image.replaceWith(el("div", "screen-message", "이 비공개 사진을 불러오지 못했습니다."));
    }
  }
  function renderDetail(app) {
    detail.replaceChildren();
    const body = el("div", "review-detail");
    const heading = el("div", "detail-title");
    const titleBlock = el("div");
    titleBlock.append(el("p", "kicker", "APPLICATION INSPECTION"), el("h2", "", app.payload?.title || "제목 없는 등록"));
    const badge = el("span", "status-pill", statusName(app.status));
    badge.dataset.status = app.status;
    heading.append(titleBlock, badge);
    body.append(heading);
    const grid = el("div", "detail-grid");
    const p = app.payload || {};
    addDetail(grid, "운영자 선언 운영 형태 (정부 인증 아님)", p.stay_kind === "lodging" ? "숙박형 · 운영자 선언" : p.stay_kind === "non_lodging" ? "비숙박형 · 운영자 선언" : "미선택");
    addDetail(grid, "공간", `${p.space_label || "미기재"} · ${p.space_scope === "whole" ? "건물 전체" : "일부 공간"}`);
    addDetail(grid, "방 / 면적 / 인원", `${p.rooms ?? "—"}실 · ${p.area_m2 ?? "—"}㎡ · ${p.guests ?? "—"}명`);
    addDetail(grid, "최소 이용 기간", p.min_stay ? `${p.min_stay}일` : "미기재");
    addDetail(grid, "1박 요금", p.nightly === null || p.nightly === undefined ? "미기재" : `${Number(p.nightly).toLocaleString("ko-KR")}원`);
    addDetail(grid, "주 / 월 요금", `${p.weekly == null ? "미기재" : `${Number(p.weekly).toLocaleString("ko-KR")}원 / 주`} · ${p.monthly == null ? "미기재" : `${Number(p.monthly).toLocaleString("ko-KR")}원 / 월`}`);
    addDetail(grid, "편의 시설", (p.options || []).join(", ") || "미기재");
    addDetail(grid, "등록 책임 확인", p.responsibility ? "확인함" : "확인하지 않음");
    addDetail(grid, "제한 공개 동의", p.public_summary ? "동의함" : "동의하지 않음");
    addDetail(grid, "수정 차수", `v${app.revision}`);
    addDetail(grid, "신청 ID", app.id);
    body.append(grid);
    const photoHeading = el("div", "section-divider", `비공개 등록 사진 · ${(p.photos || []).length}장`);
    body.append(photoHeading);
    const photoStrip = el("div", "admin-photos");
    (p.photos || []).forEach((photoId, index) => {
      const figure = el("figure", "photo");
      const image = document.createElement("img");
      image.alt = `관리자 검토 사진 ${index + 1}`;
      image.loading = "lazy";
      figure.append(image, el("figcaption", "photo-caption", `사진 ${index + 1}`));
      photoStrip.append(figure);
      loadAdminPhoto(photoId, image);
    });
    if (!(p.photos || []).length) photoStrip.append(el("div", "empty", "등록된 사진이 없습니다."));
    body.append(photoStrip);
    const review = el("section", "review-box");
    review.setAttribute("aria-labelledby", "review-controls-title");
    review.append(el("h3", "", "검토 결과 기록"));
    review.lastChild.id = "review-controls-title";
    review.append(el("p", "warning-copy", "승인은 등록 권한 및 공개 정보를 확인한 결과입니다. 이는 건축물의 법적 용도 적합성 판단이 아닙니다."));
    const noteField = el("div", "field");
    const noteLabel = el("label", "", "검토 메모 / 반려 사유");
    noteLabel.htmlFor = "reviewNoteInput";
    const note = document.createElement("textarea");
    note.id = "reviewNoteInput";
    note.maxLength = 1000;
    note.setAttribute("aria-describedby", "reviewNoteHint");
    note.placeholder = "검토 결과 또는 반려 사유를 기록하세요";
    if (app.review_note) note.value = app.review_note;
    const noteHint = el("span", "hint", "승인과 반려 모두 1자 이상의 검토 메모가 필요합니다. 반려에는 사유를 기록해 주세요.");
    noteHint.id = "reviewNoteHint";
    noteField.append(noteLabel, note, noteHint);
    const checks = el("div", "review-checks");
    const rightsLabel = document.createElement("label");
    const rights = document.createElement("input");
    rights.type = "checkbox"; rights.id = "reviewRights";
    rightsLabel.append(rights, document.createTextNode("등록 권한 확인 완료"));
    const disclosureLabel = document.createElement("label");
    const disclosure = document.createElement("input");
    disclosure.type = "checkbox"; disclosure.id = "reviewDisclosure";
    disclosureLabel.append(disclosure, document.createTextNode("제한 공개 정보 확인 완료 (주소·건물명·사진·GPS·연락처 비공개)"));
    checks.append(rightsLabel, disclosureLabel);
    const actions = el("div", "actions");
    const approve = el("button", "button primary", "승인");
    approve.type = "button"; approve.dataset.decision = "approve";
    const reject = el("button", "button danger", "반려");
    reject.type = "button"; reject.dataset.decision = "reject";
    actions.append(approve, reject);
    review.append(noteField, checks, actions);
    approve.addEventListener("click", () => submitReview(app, "approve", note.value, rights.checked, disclosure.checked, approve, reject));
    reject.addEventListener("click", () => submitReview(app, "reject", note.value, rights.checked, disclosure.checked, approve, reject));
    body.append(review);
    detail.append(body);
  }
  async function submitReview(app, decision, note, rights, disclosure, approveButton, rejectButton) {
    if (busy) return;
    if (decision === "approve" && (!rights || !disclosure)) {
      setFeedback("승인 전 등록 권한과 제한 공개 정보를 각각 확인해 주세요.");
      if (!rights) $("#reviewRights").focus(); else $("#reviewDisclosure").focus();
      return;
    }
    if (decision === "reject" && !note.trim()) {
      setFeedback("반려 사유를 메모에 입력해 주세요.");
      $("#reviewNoteInput").focus();
      return;
    }
    if (decision === "approve" && !note.trim()) {
      setFeedback("승인 결과에도 1자 이상의 검토 메모가 필요합니다.");
      $("#reviewNoteInput").focus();
      return;
    }
    busy = true;
    approveButton.disabled = true; rejectButton.disabled = true;
    try {
      await api(`/admin/applications/${encodeURIComponent(app.id)}/review`, {
        method: "POST",
        body: JSON.stringify({ revision: app.revision, decision, note: note.trim(), rights, disclosure })
      });
      setFeedback(decision === "approve" ? "검토 결과를 기록하고 승인했습니다. 공개 승인은 등록 권한·공개 정보 검토에 한정됩니다." : "반려 결과를 기록했습니다.", "success");
      await refresh();
    } catch (error) {
      setFeedback(translate(error));
      approveButton.disabled = false; rejectButton.disabled = false;
    } finally { busy = false; }
  }
  async function refresh() {
    $("#queueCount").textContent = "불러오는 중";
    list.replaceChildren(el("div", "loading", ""));
    const skeleton = list.firstChild;
    skeleton.classList.add("skeleton");
    try {
      const result = await api("/admin/applications");
      applications = Array.isArray(result.items) ? result.items : [];
      renderList();
      const selected = applications.find((app) => app.id === selectedId && app.status === "submitted");
      if (selected) renderDetail(selected);
      else {
        selectedId = null;
        detail.replaceChildren(el("div", "screen-message", applications.some((app) => app.id === selectedId) ? "현재 상태에서는 검토할 수 없습니다." : "목록에서 제출된 등록을 선택하면 세부 내용을 확인할 수 있습니다."));
      }
      setFeedback("", "success");
    } catch (error) {
      $("#queueCount").textContent = "오류";
      list.replaceChildren();
      const panel = el("div", "empty");
      panel.append(el("strong", "", "목록을 불러오지 못했습니다."), document.createTextNode(" "));
      const retry = el("button", "button secondary", "다시 시도");
      retry.type = "button"; retry.addEventListener("click", refresh);
      panel.append(retry); list.append(panel);
      setFeedback(translate(error));
    }
  }
  async function initialize() {
    try {
      const meta = await api("/admin/meta");
      csrf = meta.csrf || "";
      await refresh();
    } catch (error) {
      setFeedback(translate(error));
      list.replaceChildren(el("div", "empty", "관리자 정보를 확인할 수 없습니다. 관리자 계정으로 로그인한 뒤 새로고침해 주세요."));
      $("#queueCount").textContent = "접근 불가";
    }
  }
  $("#refreshButton").addEventListener("click", refresh);
  initialize();
})();
