(() => {
  "use strict";
  const API = "/hs2/listings";
  const $ = (selector) => document.querySelector(selector);
  const form = $("#applicationForm");
  const feedback = $("#feedback");
  const select = $("#workflowSelect");
  const photoGrid = $("#photoGrid");
  const savedList = $("#savedApplications");
  const labels = { draft: "초안", submitted: "검토 중", approved: "승인", rejected: "반려", withdrawn: "철회" };
  const errorCopy = {
    AUTH_REQUIRED: "로그인이 필요합니다. 로그인한 뒤 다시 시도해 주세요.",
    APPROVED_BUSINESS_REQUIRED: "운영자 계정으로 전환한 뒤 이용해 주세요.",
    ACTIVE_MEMBER_REQUIRED: "현재 계정이 활성 상태가 아닙니다. 관리자에게 문의해 주세요.",
    BUSINESS_CONTEXT_REQUIRED: "운영 사업장 정보를 확인할 수 없습니다. 사업장을 다시 선택해 주세요.",
    CSRF_REQUIRED: "보안 확인이 만료되었습니다. 새로고침한 뒤 다시 시도해 주세요.",
    STALE_REVISION: "다른 변경 사항이 먼저 저장되었습니다. 최신 내용을 새로 불러와 다시 확인해 주세요. 입력 중인 내용은 그대로 보존했습니다.",
    OWNED_CONFIRMED_REFERENCE_REQUIRED: "선택한 주소 확인 기록을 사용할 수 없습니다. 주소 확인을 다시 진행해 주세요.",
    CONFIRMED_REFERENCE_REQUIRED: "주소 확인 기록이 만료되었습니다. 주소 확인을 다시 진행해 주세요.",
    COMPLETE_SPACE_REQUIRED: "제목, 공간 정보, 운영 형태, 방 수, 면적, 인원, 최소 이용 기간을 확인해 주세요.",
    MINIMUM_STAY_REQUIRED: "숙박형은 최소 1일, 비숙박형은 최소 7일을 설정해 주세요.",
    TYPE_PRICE_REQUIRED: "숙박형은 1박 요금, 비숙박형은 주 또는 월 요금을 입력해 주세요.",
    PHOTO_REQUIRED: "검토 요청에는 공간 사진이 필요합니다.",
    RESPONSIBILITY_REQUIRED: "운영 책임 확인을 체크해 주세요.",
    INVALID_AREA: "면적을 0보다 크고 소수점 둘째 자리 이내로 입력해 주세요.",
    INVALID_NUMBER: "숫자 입력 범위를 확인해 주세요.",
    INVALID_TEXT: "제목과 공간 이름은 100자 이내로 입력해 주세요.",
    INVALID_PAYLOAD: "등록 정보 형식을 확인하고 다시 저장해 주세요.",
    INVALID_ID: "등록 또는 사진 식별 정보를 확인할 수 없습니다. 목록을 새로고침해 주세요.",
    INVALID_SPACE_SCOPE: "등록 범위를 다시 선택해 주세요.",
    EXPLICIT_STAY_KIND_REQUIRED: "숙박형 또는 비숙박형 중 하나를 선택해 주세요.",
    INVALID_OPTIONS: "선택한 편의 시설을 다시 확인해 주세요.",
    INVALID_PHOTOS: "등록된 사진 정보를 확인할 수 없습니다. 사진을 다시 올려 주세요.",
    INVALID_BOOLEAN: "체크 항목을 확인하고 다시 시도해 주세요.",
    LIMITED_DISCLOSURE_REQUIRED: "등록은 제한 공개 방식으로만 진행할 수 있습니다.",
    PHOTO_FORMAT_OR_SIZE: "JPEG, PNG, WebP 이미지 파일을 512KiB 이하로 선택해 주세요.",
    PHOTO_LIMIT: "업로드할 수 있는 사진 수 한도에 도달했습니다.",
    OWNED_PHOTO_REQUIRED: "사진 권한을 확인할 수 없습니다. 사진을 다시 올려 주세요.",
    WITHDRAWAL_TERMINAL: "철회된 등록은 다시 편집할 수 없습니다.",
    SUBMISSION_STATE_REQUIRED: "현재 상태에서는 검토 요청을 보낼 수 없습니다.",
    INVALID_ACTION: "요청한 작업을 처리할 수 없습니다. 페이지를 새로고침해 주세요.",
    APPLICATION_NOT_FOUND: "등록을 찾을 수 없습니다. 목록을 새로고침해 주세요.",
    PHOTO_NOT_FOUND: "등록 사진을 찾을 수 없습니다. 사진을 다시 올려 주세요.",
    REVISION_REQUIRED: "등록 차수 정보를 확인할 수 없습니다. 목록을 새로고침해 주세요.",
    LIMIT_REACHED: "등록 개수 한도에 도달했습니다.",
    WITHDRAWN_APPLICATION: "철회된 등록은 다시 편집하거나 제출할 수 없습니다."
  };
  let csrf = "";
  let items = [];
  let current = null;
  let photos = [];
  let busy = false;

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function say(message, tone = "error") {
    feedback.textContent = message;
    feedback.dataset.tone = tone;
    feedback.hidden = !message;
  }
  function messageFor(error) {
    if (error && error.code && errorCopy[error.code]) return errorCopy[error.code];
    if (error && error.code) return `요청을 처리하지 못했습니다 (${error.code}). 입력은 보존했습니다. 잠시 후 다시 시도해 주세요.`;
    return "서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도해 주세요. 입력은 보존했습니다.";
  }
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (options.method && options.method !== "GET") headers.set("X-HS2-CSRF", csrf);
    const response = await fetch(`${API}${path}`, { ...options, headers, credentials: "same-origin" });
    const type = response.headers.get("content-type") || "";
    const result = type.includes("application/json") ? await response.json() : {};
    if (!response.ok || result.ok === false) {
      const error = new Error(result.message || "Request failed");
      error.code = result.code || `HTTP_${response.status}`;
      throw error;
    }
    return result;
  }
  function labelStatus(status) { return labels[status] || "상태 확인 필요"; }
  function renderState() {
    const status = current?.status || "draft";
    const pill = $("#statusline");
    pill.replaceChildren();
    const badge = node("span", "status-pill", current ? labelStatus(status) : "새 초안");
    badge.dataset.status = status;
    pill.append(badge);
    if (current?.approved_until) pill.append(node("span", "", `검토 만료 ${formatDate(current.approved_until)}`));
    $("#sideStatus").textContent = current ? labelStatus(status) : "새 초안";
    $("#revision").textContent = current ? `v${current.revision}` : "아직 저장 전";
    const reviewText = current?.reviewed_revision
      ? `${current.reviewed_revision === current.revision ? "현재 차수" : `v${current.reviewed_revision}`} · ${current.review_decision === "approve" || status === "approved" ? "승인" : status === "rejected" ? "반려" : "검토 완료"}`
      : "검토 전";
    $("#reviewResult").textContent = reviewText;
    $("#reviewNote").textContent = current?.review_note || current?.note || "없음";
    $("#submitButton").disabled = busy || (!current && !select.value) || status === "withdrawn" || status === "submitted";
    $("#saveButton").disabled = busy || status === "withdrawn";
    $("#withdrawButton").hidden = !current || status === "withdrawn";
    $("#withdrawButton").disabled = busy;
    select.disabled = busy || Boolean(current);
  }
  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(date);
  }
  function payloadFromForm() {
    const intOrNull = (id) => {
      const value = $(`#${id}`).value.trim();
      return value === "" ? null : Number(value);
    };
    const area = $("#area_m2").value.trim();
    return {
      title: $("#title").value,
      space_label: $("#space_label").value,
      space_scope: $("#space_scope").value,
      stay_kind: $("#stay_kind").value,
      rooms: intOrNull("rooms"),
      area_m2: area === "" ? null : area,
      guests: intOrNull("guests"),
      options: [...form.querySelectorAll('input[name="options"]:checked')].map((input) => input.value),
      nightly: intOrNull("nightly"),
      weekly: intOrNull("weekly"),
      monthly: intOrNull("monthly"),
      min_stay: intOrNull("min_stay"),
      instant: $("#instant").checked,
      discount: $("#discount").checked,
      photos: photos.map((photo) => photo.id),
      responsibility: $("#responsibility").checked,
      public_summary: $("#public_summary").checked,
      disclosure: "limited"
    };
  }
  function fillForm(payload = {}) {
    for (const key of ["title", "space_label", "space_scope", "stay_kind", "rooms", "area_m2", "guests", "nightly", "weekly", "monthly", "min_stay"]) {
      const input = $(`#${key}`);
      if (input) input.value = payload[key] === null || payload[key] === undefined ? "" : String(payload[key]);
    }
    for (const key of ["instant", "discount", "responsibility", "public_summary"]) $(`#${key}`).checked = Boolean(payload[key]);
    const selected = new Set(payload.options || []);
    form.querySelectorAll('input[name="options"]').forEach((input) => { input.checked = selected.has(input.value); });
    photos = (payload.photos || []).map((id) => ({ id, url: `${API}/photos/${encodeURIComponent(id)}` }));
    renderPhotos();
  }
  function renderPhotos() {
    photoGrid.replaceChildren();
    photos.forEach((photo, index) => {
      const figure = node("figure", "photo");
      const image = document.createElement("img");
      image.src = photo.url || `${API}/photos/${encodeURIComponent(photo.id)}`;
      image.alt = `등록한 공간 사진 ${index + 1}`;
      image.loading = "lazy";
      const caption = node("figcaption", "photo-caption", `사진 ${index + 1}`);
      const remove = node("button", "", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `사진 ${index + 1} 제거`);
      remove.addEventListener("click", () => {
        photos = photos.filter((_, i) => i !== index);
        renderPhotos();
      });
      figure.append(image, caption, remove);
      photoGrid.append(figure);
    });
    $("#photoFiles").disabled = busy || photos.length >= 10;
  }
  function renderItems() {
    savedList.replaceChildren();
    if (!items.length) {
      savedList.append(node("div", "empty", "저장한 등록이 없습니다. 확인된 주소를 선택하고 초안을 저장해 시작하세요."));
      return;
    }
    items.forEach((item) => {
      const button = node("button", "app-row");
      button.type = "button";
      button.setAttribute("aria-current", String(current?.id === item.id));
      const title = node("span", "app-row-title", item.payload?.title || "제목 없는 등록");
      const meta = node("span", "app-row-meta");
      meta.append(node("span", "", labelStatus(item.status)), node("span", "", `v${item.revision}`));
      button.append(title, meta);
      button.addEventListener("click", () => loadItem(item));
      savedList.append(button);
    });
  }
  function loadItem(item) {
    current = item;
    fillForm(item.payload || {});
    renderState();
    renderItems();
    say(`${labelStatus(item.status)} 등록을 불러왔습니다. 수정 후 저장하면 새 초안이 되어 관리자 재검토가 필요합니다.`, "info");
  }
  function startNew() {
    current = null;
    form.reset();
    photos = [];
    renderPhotos();
    renderState();
    renderItems();
    say("새 등록을 시작합니다. 주소 확인 기록을 선택해 주세요.", "info");
    select.focus();
  }
  async function refreshItems() {
    const result = await request("/applications");
    items = Array.isArray(result.items) ? result.items : [];
    renderItems();
  }
  async function saveDraft() {
    if (busy) return;
    if (!current && !select.value) {
      say("먼저 주소 확인을 완료한 기록을 선택하세요. 주소 확인이 필요하면 ‘주소 또는 건물 확인하기’를 이용해 주세요.");
      select.focus();
      return;
    }
    busy = true; renderState(); renderPhotos();
    try {
      const payload = payloadFromForm();
      const result = current
        ? await request(`/applications/${encodeURIComponent(current.id)}`, { method: "PUT", body: JSON.stringify({ revision: current.revision, payload }) })
        : await request("/applications", { method: "POST", body: JSON.stringify({ workflow_id: select.value, payload }) });
      current = result.item;
      await refreshItems();
      fillForm(current.payload || payload);
      say("초안을 저장했습니다. 소비자에게 공개된 상태는 아닙니다.", "success");
    } catch (error) { say(messageFor(error)); }
    finally { busy = false; renderState(); renderPhotos(); }
  }
  async function submitForReview() {
    if (busy) return;
    if (!$("#responsibility").checked) {
      say("제출 전에 운영 책임 확인을 선택해 주세요.");
      $("#responsibility").focus();
      return;
    }
    const kind = $("#stay_kind").value;
    if (kind === "lodging" && $("#nightly").value === "") {
      say("숙박형 운영은 1박 요금을 입력해야 검토를 요청할 수 있습니다."); $("#nightly").focus(); return;
    }
    if (kind === "non_lodging" && $("#weekly").value === "" && $("#monthly").value === "") {
      say("비숙박형 운영은 주 또는 월 요금을 입력해야 검토를 요청할 수 있습니다."); $("#weekly").focus(); return;
    }
    if (!photos.length) { say("검토 요청에 필요한 공간 사진을 먼저 올려 주세요."); $("#photoFiles").focus(); return; }
    busy = true; renderState();
    try {
      const payload = payloadFromForm();
      const saved = current
        ? await request(`/applications/${encodeURIComponent(current.id)}`, { method: "PUT", body: JSON.stringify({ revision: current.revision, payload }) })
        : await request("/applications", { method: "POST", body: JSON.stringify({ workflow_id: select.value, payload }) });
      current = saved.item;
      const result = await request(`/applications/${encodeURIComponent(current.id)}/submit`, { method: "POST", body: JSON.stringify({ revision: current.revision }) });
      current = result.item;
      await refreshItems();
      fillForm(current.payload || payload);
      say("등록 내용을 검토 요청으로 보냈습니다. 공개 전 관리자 확인을 기다립니다.", "success");
    } catch (error) { say(messageFor(error)); }
    finally { busy = false; renderState(); renderPhotos(); }
  }
  async function withdraw() {
    if (!current || busy) return;
    if (!window.confirm("이 등록을 철회할까요? 철회한 등록은 다시 편집하거나 제출할 수 없습니다.")) return;
    busy = true; renderState();
    try {
      const result = await request(`/applications/${encodeURIComponent(current.id)}`, { method: "DELETE", body: JSON.stringify({ revision: current.revision }) });
      current = result.item;
      await refreshItems();
      say("등록을 철회했습니다. 철회는 되돌릴 수 없습니다.", "success");
    } catch (error) { say(messageFor(error)); }
    finally { busy = false; renderState(); }
  }
  async function uploadFiles(event) {
    const files = [...event.target.files];
    event.target.value = "";
    if (!files.length) return;
    if (photos.length + files.length > 10) {
      say("사진은 등록 한 건당 최대 10장까지 선택할 수 있습니다."); return;
    }
    const validTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
    const invalid = files.find((file) => !validTypes.has(file.type) || file.size > 524288);
    if (invalid) { say("JPEG, PNG, WebP 이미지를 장당 512KiB 이하로 선택해 주세요."); return; }
    busy = true; renderState(); renderPhotos();
    try {
      for (const file of files) {
        const data = new FormData();
        data.append("file", file);
        const result = await request("/photos", { method: "POST", body: data });
        photos.push({ id: result.id, url: `${API}/photos/${encodeURIComponent(result.id)}` });
        renderPhotos();
      }
      say("사진을 비공개로 올렸습니다. 사진 ID는 등록 내용 저장 시 연결됩니다.", "success");
    } catch (error) { say(messageFor(error)); }
    finally { busy = false; renderState(); renderPhotos(); }
  }
  async function initialize() {
    try {
      const meta = await request("/meta");
      csrf = meta.csrf || "";
      select.replaceChildren();
      const prompt = node("option", "", "확인된 주소 기록을 선택하세요");
      prompt.value = "";
      select.append(prompt);
      (meta.references || []).forEach((reference) => {
        const option = node("option");
        option.value = reference.workflow_id;
        const use = reference.building_use ? ` · 용도 참고: ${reference.building_use}` : "";
        option.textContent = `${reference.label}${use}`;
        select.append(option);
      });
      select.disabled = false;
      if (!(meta.references || []).length) {
        $("#referenceHint").textContent = "확인된 주소 기록이 없습니다. 주소 확인을 완료한 뒤 이 화면으로 돌아오세요.";
      }
      await refreshItems();
      if (items.length) loadItem(items[0]);
      else renderState();
    } catch (error) {
      select.replaceChildren(node("option", "", "주소 정보를 불러오지 못했습니다"));
      select.disabled = true;
      say(messageFor(error));
    }
  }
  form.addEventListener("submit", (event) => event.preventDefault());
  $("#saveButton").addEventListener("click", saveDraft);
  $("#submitButton").addEventListener("click", submitForReview);
  $("#withdrawButton").addEventListener("click", withdraw);
  $("#newApplication").addEventListener("click", startNew);
  $("#photoFiles").addEventListener("change", uploadFiles);
  select.addEventListener("change", () => { if (!current) renderState(); });
  initialize();
})();
