(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const addressQuery = $("#addressQuery");
  const searchForm = $("#searchForm");
  const searchBtn = $("#searchBtn");
  const addressChoices = $("#addressChoices");
  const buildingChoices = $("#buildingChoices");
  const coordinateBtn = $("#coordinateBtn");
  const confirmBtn = $("#confirmBtn");
  const statusText = $("#workflowStatus");
  const statusBand = $("#statusBand");
  const coordinatePreview = $("#coordinatePreview");
  const coordinateValues = $("#coordinateValues");
  const coordinateEvidence = $("#coordinateEvidence");

  const statusMessages = {
    ADDRESS_SELECTION_REQUIRED: "주소 원본의 후보가 있습니다. 정확한 주소를 직접 선택해 주세요.",
    ADDRESS_NOT_FOUND: "주소 원본에서 일치하는 주소를 찾지 못했습니다. 주소를 확인하고 다시 조회해 주세요.",
    ADDRESS_LOOKUP: "주소 원본을 조회하고 있습니다. 결과가 올 때까지 잠시 기다려 주세요.",
    ADDRESS_PROVIDER_FAILED: "테스트 주소 원본 조회에 실패했습니다. 입력 주소를 확인한 뒤 다시 시도해 주세요.",
    ADDRESS_INCOMPLETE: "주소 원본 결과가 완전하지 않아 선택할 수 없습니다. 다시 조회해 주세요.",
    ADDRESS_IDENTITY_AMBIGUOUS: "주소 원본에서 구별할 수 없는 중복 결과가 발견됐습니다. 현재 결과를 사용할 수 없습니다.",
    REFINE_ADDRESS: "주소 후보가 너무 많아 결과를 사용할 수 없습니다. 더 구체적인 주소로 다시 조회해 주세요.",
    REGISTRY_LOOKUP: "선택한 주소의 건축물 근거를 조회하고 있습니다.",
    BUILDING_SELECTION_REQUIRED: "건물 후보가 있습니다. 건물 정보를 확인하고 하나를 직접 선택해 주세요.",
    REGISTRY_UNCONFIRMED: "선택 주소와 대조할 건축물 근거가 없습니다. 다른 주소를 확인해 주세요.",
    REGISTRY_PROVIDER_FAILED: "테스트 건축물 원본 조회에 실패했습니다. 주소를 다시 선택해 주세요.",
    REGISTRY_INVALID: "건축물 원본 결과의 형식이 올바르지 않아 확인할 수 없습니다.",
    REGISTRY_IDENTITY_AMBIGUOUS: "건축물 원본에 중복 식별자가 있어 안전하게 선택할 수 없습니다.",
    REGISTRY_ADDRESS_MISMATCH: "건물 원본 주소가 선택한 주소와 일치하지 않아 확인을 중단했습니다.",
    COORDINATES_REQUIRED: "건물을 선택했습니다. 버튼을 눌러 선택 주소의 서버 확인 좌표를 조회해 주세요.",
    COORDINATES_PROVIDER_FAILED: "테스트 좌표 원본 조회에 실패했습니다. 다시 시도하거나 다른 주소를 확인해 주세요.",
    COORDINATES_INCOMPLETE: "좌표 원본 응답이 완전하지 않아 위치를 확인할 수 없습니다.",
    COORDINATES_UNCONFIRMED: "주소에 대응하는 확인된 좌표가 없습니다. 좌표를 추정하지 않았습니다.",
    COORDINATES_AMBIGUOUS: "좌표 원본에 여러 결과가 있어 위치를 확정할 수 없습니다.",
    COORDINATE_ADDRESS_MISMATCH: "좌표 원본 주소가 선택한 주소와 일치하지 않아 위치를 표시하지 않습니다.",
    COORDINATES_INVALID: "좌표 원본 값이 유효하지 않아 위치를 확인할 수 없습니다.",
    MASTER_LOOKUP_FAILED: "기존 참고자료 원본 연결이 미확인입니다. 참고자료 저장을 중단했습니다.",
    MASTER_LINK_MISMATCH: "기존 참고자료에서 일치하지 않는 식별 결과가 발견됐습니다. 확인을 중단했습니다.",
    MASTER_LINK_AMBIGUOUS: "기존 참고자료에 중복 일치 결과가 있습니다. 확인을 진행할 수 없습니다.",
    READY_FOR_REFERENCE: "주소·건물·좌표 근거를 확인했습니다. 내용을 확인한 뒤 비공개 참고자료로 저장할 수 있습니다.",
    REFERENCE_CONFIRMED: "비공개 건물 참고자료 확인이 완료됐습니다. 공개 매물이나 권리 승인이 아닙니다.",
    REFERENCE_SAVE_FAILED: "비공개 참고자료를 저장하지 못했습니다. 다시 시도해 주세요.",
    REFERENCE_NOT_READY: "필요한 원본 근거 확인이 완료되지 않아 저장할 수 없습니다.",
    WORKFLOW_NOT_FOUND: "확인 절차를 찾을 수 없습니다. 주소 조회부터 다시 시작해 주세요.",
    WORKFLOW_EXPIRED: "확인 절차가 만료됐습니다. 주소 조회부터 다시 시작해 주세요.",
    REFERENCE_ALREADY_CONFIRMED: "이미 비공개 참고자료 확인이 완료된 절차입니다. 새 절차가 필요하면 주소를 다시 조회해 주세요.",
    ADDRESS_SELECTION_INVALID: "선택한 주소를 이 조회 결과에서 확인할 수 없습니다. 주소를 다시 조회해 주세요.",
    BUILDING_SELECTION_INVALID: "선택한 건물을 이 주소의 결과에서 확인할 수 없습니다. 주소를 다시 선택해 주세요.",
    BUILDING_REQUIRED: "건물을 먼저 직접 선택해야 좌표를 조회할 수 있습니다.",
    AUTH_REQUIRED: "테스트 fixture identity를 확인할 수 없습니다. 접근 권한을 확인해 주세요.",
    CSRF_REQUIRED: "요청 보안 확인에 실패했습니다. 페이지를 새로 연 뒤 다시 시도해 주세요.",
    WORKFLOW_CAPACITY: "현재 테스트 확인 요청이 가득 찼습니다. 잠시 후 다시 시도해 주세요.",
    INVALID_ADDRESS_INPUT: "주소를 2자 이상 160자 이하로 입력해 주세요.",
    INVALID_INPUT: "요청 내용을 확인할 수 없습니다. 다시 시작해 주세요.",
    INVALID_ACTION: "요청한 확인 동작을 처리할 수 없습니다. 주소 조회부터 다시 시작해 주세요."
  };

  function request(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-HS2-CSRF": "fixture-only"
      },
      body: JSON.stringify(body)
    }).then(async (response) => {
      let result;
      try {
        result = await response.json();
      } catch (_) {
        result = {};
      }
      if (!response.ok) {
        const error = new Error(result.error || "REQUEST_FAILED");
        error.code = result.error;
        throw error;
      }
      return result;
    });
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function clear(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }

  function showEmpty(container, message) {
    container.appendChild(node("p", "field-hint", message));
  }

  function renderAddresses(state, busy) {
    clear(addressChoices);
    addressChoices.setAttribute("aria-busy", String(busy));
    const addresses = state && Array.isArray(state.addresses) ? state.addresses : [];
    if (!addresses.length) {
      showEmpty(addressChoices, busy ? "주소 후보를 불러오는 중입니다." : "조회된 주소가 없습니다. 검색 결과가 있을 때만 선택할 수 있습니다.");
      return;
    }
    addresses.forEach((address) => {
      const button = node("button", "choice-button");
      button.type = "button";
      button.dataset.addressKey = address.address_key;
      button.disabled = busy || Boolean(state.reference_id);
      button.setAttribute("aria-pressed", String(Boolean(state.address && state.address.address_key === address.address_key)));
      button.appendChild(node("span", "choice-title", address.road_address));
      button.appendChild(node("span", "choice-sub", "지번 " + address.jibun_address + " · 행정코드 " + address.adm_code));
      button.addEventListener("click", () => controller.action("address", { address_key: address.address_key }));
      addressChoices.appendChild(button);
    });
  }

  function renderBuildings(state, busy) {
    clear(buildingChoices);
    buildingChoices.setAttribute("aria-busy", String(busy));
    const buildings = state && Array.isArray(state.buildings) ? state.buildings : [];
    if (!buildings.length) {
      showEmpty(buildingChoices, busy ? "건축물 근거를 불러오는 중입니다." : "주소를 먼저 직접 선택하면 해당 주소의 건축물 근거가 표시됩니다.");
      return;
    }
    buildings.forEach((building) => {
      const button = node("button", "choice-button");
      button.type = "button";
      button.dataset.buildingKey = building.building_key;
      button.disabled = busy || Boolean(state.reference_id);
      button.setAttribute("aria-pressed", String(Boolean(state.building && state.building.building_key === building.building_key)));
      button.appendChild(node("span", "choice-title", building.name || "건물명 미기재"));
      button.appendChild(node("span", "choice-sub", [building.dong, building.building_use].filter(Boolean).join(" · ") || "건물 세부정보 없음"));
      button.addEventListener("click", () => controller.action("building", { building_key: building.building_key }));
      buildingChoices.appendChild(button);
    });
    if (state.building) {
      const card = node("div", "selection-card");
      card.appendChild(node("h3", "", "선택한 건물 · 확인 정보"));
      const details = node("dl", "detail-list");
      const rows = [
        ["건물명", state.building.name],
        ["동", state.building.dong],
        ["주용도", state.building.building_use],
        ["도로명", state.building.road_address],
        ["지번", state.building.jibun_address],
        ["근거 버전", state.building.evidence_version]
      ];
      rows.forEach(([label, value]) => {
        details.appendChild(node("dt", "", label));
        details.appendChild(node("dd", "", value || "미기재"));
      });
      card.appendChild(details);
      buildingChoices.appendChild(card);
    }
  }

  function progressStep(state) {
    if (!state) return "address";
    if (state.status === "REFERENCE_CONFIRMED") return "confirm";
    if (state.status === "READY_FOR_REFERENCE" || state.coordinates) return "coordinates";
    if (state.building) return "building";
    if (state.address) return "building";
    return "address";
  }

  function render(state, options) {
    const busy = Boolean(options && options.busy);
    const statusError = options && options.error;
    const message = busy
      ? (state ? "선택한 항목을 확인하고 있습니다. 잠시 기다려 주세요." : "테스트 주소 원본을 조회하고 있습니다. 잠시 기다려 주세요.")
      : statusError
        ? translateError(statusError)
        : state
          ? (statusMessages[state.status] || "현재 확인 상태를 완료할 수 없습니다. 주소 원본 결과와 상태를 확인한 뒤 다시 시작해 주세요.")
          : "주소를 입력해 비공개 개발 fixture 조회를 시작해 주세요.";
    statusText.textContent = message;
    statusBand.dataset.tone = statusError || (state && state.error) ? "error" : state && state.status === "REFERENCE_CONFIRMED" ? "good" : "neutral";

    renderAddresses(state, busy);
    renderBuildings(state, busy);
    searchBtn.disabled = busy;
    addressQuery.disabled = busy;
    coordinateBtn.disabled = busy || !state || !state.building || Boolean(state.reference_id);
    confirmBtn.disabled = busy || !state || state.status !== "READY_FOR_REFERENCE";
    $("#searchHint").textContent = busy ? "조회 중에는 새 요청과 후보 선택이 잠시 비활성화됩니다." : "검색 결과 중 주소를 직접 선택한 뒤 해당 건물을 확인합니다.";
    document.querySelectorAll(".step").forEach((step) => {
      const current = progressStep(state);
      const order = ["address", "building", "coordinates", "confirm"];
      step.classList.toggle("is-active", step.dataset.step === current);
      step.classList.toggle("is-done", Boolean(state) && order.indexOf(step.dataset.step) < order.indexOf(current));
    });

    if (!busy && state && state.coordinates && validCoordinate(state.coordinates.lat, -90, 90) && validCoordinate(state.coordinates.lng, -180, 180)) {
      coordinatePreview.hidden = false;
      coordinateValues.textContent = "위도 " + state.coordinates.lat + "  /  경도 " + state.coordinates.lng;
      coordinateEvidence.textContent = "공식 주소 응답 좌표 · 개별 동 중심·호실 위치를 의미하지 않습니다. 확인 근거 · " + String(state.coordinates.evidence_version || "버전 미기재");
    } else {
      coordinatePreview.hidden = true;
      coordinateValues.textContent = "";
      coordinateEvidence.textContent = "";
    }

    if (state && state.status === "READY_FOR_REFERENCE") {
      const legacyText = state.legacy_state === "EXACT_EXISTING"
        ? "기존 참고자료와 정확히 연결됨"
        : state.legacy_state === "SEPARATE_REFERENCE"
          ? "기존 참고자료와 별도 항목"
          : "";
      statusText.textContent = message + (legacyText ? " " + legacyText + "." : "");
    }
  }

  function validCoordinate(value, min, max) {
    return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
  }

  function translateError(error) {
    const code = error && (error.code || error.message);
    return statusMessages[code] || "요청 처리에 실패했습니다. 연결 상태를 확인하고 주소 조회부터 다시 시도해 주세요.";
  }

  const controller = new window.RegistrationController(request, render);

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = addressQuery.value.trim();
    if (query.length < 2 || query.length > 160) {
      statusBand.dataset.tone = "error";
      statusText.textContent = statusMessages.INVALID_ADDRESS_INPUT;
      addressQuery.focus();
      return;
    }
    controller.start(query);
  });

  coordinateBtn.addEventListener("click", () => controller.action("coordinates", {}));
  confirmBtn.addEventListener("click", () => controller.action("confirm", {}));
})();
