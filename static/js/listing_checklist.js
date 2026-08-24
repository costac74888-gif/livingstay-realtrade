/* 건물전체 공개매물 실사 체크리스트 — 홈 상세·매물목록에서 공통 사용 */
(function () {
  "use strict";

  const STORAGE_PREFIX = "hs_listing_checklist:";
  const CATEGORY_ORDER = ["건물", "권리", "법적", "소방", "주차", "입지", "매출", "금융", "운영", "출구"];
  const GENERAL_CHECKLIST_ITEMS = [
    ["building_register", "건물", "건축물대장과 실제 건물 정보가 일치하나요?", "https://cloud.eais.go.kr", "세움터에서 건축물대장 확인"],
    ["registry", "권리", "등기부등본으로 소유권·근저당권을 확인했나요?", "https://www.iros.go.kr", "인터넷등기소에서 확인"],
    ["land_use", "법적", "토지이용계획과 용도지역 제한을 확인했나요?", "https://www.eum.go.kr", "토지이음에서 확인"],
    ["permit", "법적", "숙박업 인허가·영업신고 상태를 확인했나요?", "https://www.gov.kr", "정부24에서 확인"],
    ["fire", "소방", "소방시설 점검·완비증명 대상 여부를 확인했나요?", "https://www.nfa.go.kr", "소방청 안내 확인"],
    ["parking", "주차", "주차장 설치 기준과 실제 확보 대수를 확인했나요?", "https://cloud.eais.go.kr", "건축물대장에서 확인"],
    ["surroundings", "입지", "주변 경쟁 숙박업소와 접근성을 확인했나요?", "https://www.vworld.kr", "공간정보 확인"],
    ["sales", "매출", "매출 자료와 증빙의 일치 여부를 확인했나요?", "https://www.hometax.go.kr", "홈택스 증빙 확인"],
    ["loan", "금융", "승계할 대출·근저당 조건을 금융기관에 확인했나요?", "https://www.iros.go.kr", "등기부등본 재확인"],
    ["tax", "금융", "국세·지방세 체납 여부와 납세증명서를 확인했나요?", "https://www.hometax.go.kr", "홈택스 납세증명"],
    ["operation", "운영", "예약 채널·직원·시설 유지보수 계약을 확인했나요?", "https://www.gov.kr", "관련 서류 확인"],
    ["insurance", "운영", "화재·배상책임 등 보험 가입 상태를 확인했나요?", "https://www.gov.kr", "보험 증빙 확인"],
    ["contract", "출구", "계약 전 법률·세무·중개 전문가 검토를 받았나요?", "https://www.law.go.kr", "국가법령정보센터"],
    ["exit", "출구", "향후 매각·임대 전환 시 제약을 확인했나요?", "https://www.eum.go.kr", "토지이용계획 재확인"],
  ].map(([key, category, question, link_url, link_label]) => ({
    key, category, question, link_url, link_label, type: "official",
  }));

  function escapeHtml(value) {
    const node = document.createElement("div");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function localKey(listingId) {
    return `${STORAGE_PREFIX}${listingId}`;
  }

  function readLocalProgress(listingId) {
    try {
      const saved = JSON.parse(localStorage.getItem(localKey(listingId)) || "[]");
      return new Set(Array.isArray(saved) ? saved.filter(item => typeof item === "string") : []);
    } catch (_) {
      return new Set();
    }
  }

  function writeLocalProgress(listingId, keys) {
    try {
      localStorage.setItem(localKey(listingId), JSON.stringify([...keys]));
    } catch (_) {}
  }

  function itemValue(item) {
    if (item.requires_login) return '<span class="listing-checklist-muted">로그인 후 확인 가능</span>';
    if (!item.value) return '<span class="listing-checklist-muted">정보 없음</span>';
    const sellerBadge = item.type === "seller"
      ? '<span class="listing-checklist-seller">매도자 제공, 미검증</span>'
      : "";
    return `${sellerBadge}<span>${escapeHtml(item.value)}</span>`;
  }

  function itemContent(item) {
    if (item.type === "official") {
      return `<a class="listing-checklist-link" href="${escapeHtml(item.link_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.link_label || "바로가기")} →</a>`;
    }
    return itemValue(item);
  }

  function makeContent(data, checkedKeys) {
    const groups = new Map(CATEGORY_ORDER.map(category => [category, []]));
    (data.items || []).forEach(item => {
      if (!groups.has(item.category)) groups.set(item.category, []);
      groups.get(item.category).push(item);
    });
    const completed = (data.items || []).filter(item => checkedKeys.has(item.key)).length;
    const rows = [...groups.entries()].filter(([, items]) => items.length).map(([category, items], index) => `
      <details class="listing-checklist-group" ${index === 0 ? "open" : ""}>
        <summary>${escapeHtml(category)} <span>${items.filter(item => checkedKeys.has(item.key)).length}/${items.length}</span></summary>
        <div class="listing-checklist-items">
          ${items.map(item => `
            <label class="listing-checklist-item">
              <input type="checkbox" data-checklist-key="${escapeHtml(item.key)}" ${checkedKeys.has(item.key) ? "checked" : ""}>
              <span class="listing-checklist-copy">
                <strong>${escapeHtml(item.question)}</strong>
                <span class="listing-checklist-value">${itemContent(item)}</span>
              </span>
            </label>
          `).join("")}
        </div>
      </details>
    `).join("");
    return `
      <div class="listing-checklist-disclaimer">🔍 공인기관 확인 항목은 홈앤스테이가 아닌 매수자 본인이 직접 조회해야 하며, 홈앤스테이는 정확성을 보증하지 않습니다</div>
      <div class="listing-checklist-progress"><strong>${completed}/${data.total_items || 14} 확인 완료</strong><span>체크 상태는 ${data.is_authenticated ? "계정에 저장됩니다" : "이 기기에 저장됩니다"}</span></div>
      ${rows}
    `;
  }

  async function open(listingId) {
    const hasListing = Number.isInteger(Number(listingId)) && Number(listingId) > 0;
    const progressId = hasListing ? String(listingId) : "general";
    document.getElementById("listingChecklistOverlay")?.remove();
    const overlay = document.createElement("div");
    overlay.id = "listingChecklistOverlay";
    overlay.className = "listing-checklist-overlay";
    overlay.innerHTML = `<section class="listing-checklist-dialog" role="dialog" aria-modal="true" aria-label="숙박업소 거래 체크리스트" tabindex="-1">
      <header><div><strong>숙박업소 거래 체크리스트</strong><span>${hasListing ? "건물전체 매물 전용" : "매수 전 공통 확인 항목"}</span></div><button type="button" aria-label="닫기">×</button></header>
      <div class="listing-checklist-body"><p class="listing-checklist-loading">체크리스트를 불러오는 중…</p></div>
    </section>`;
    document.body.appendChild(overlay);
    const dialog = overlay.querySelector(".listing-checklist-dialog");
    const body = overlay.querySelector(".listing-checklist-body");
    const close = () => overlay.remove();
    overlay.querySelector("header button").addEventListener("click", close);
    overlay.addEventListener("click", event => { if (event.target === overlay) close(); });
    const escapeListener = event => {
      if (event.key === "Escape") {
        close();
        document.removeEventListener("keydown", escapeListener);
      }
    };
    document.addEventListener("keydown", escapeListener);
    dialog.focus();

    let response;
    let data;
    if (!hasListing) {
      data = {
        ok: true,
        is_authenticated: false,
        total_items: GENERAL_CHECKLIST_ITEMS.length,
        items: GENERAL_CHECKLIST_ITEMS,
      };
    } else {
      try {
        response = await fetch(`/api/listing-requests/${encodeURIComponent(listingId)}/checklist`, { credentials: "same-origin" });
        data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) throw new Error(data.message || "체크리스트를 불러오지 못했습니다.");
      } catch (error) {
        body.innerHTML = `<p class="listing-checklist-loading">${escapeHtml(error.message || "체크리스트를 불러오지 못했습니다.")}</p>`;
        return;
      }
    }

    const checkedKeys = data.is_authenticated
      ? new Set(data.checked_keys || [])
      : readLocalProgress(progressId);
    const render = () => {
      if (!overlay.isConnected) return;
      body.innerHTML = makeContent(data, checkedKeys);
      body.querySelectorAll("[data-checklist-key]").forEach(input => {
        input.addEventListener("change", async () => {
          const key = input.dataset.checklistKey;
          const checked = input.checked;
          if (checked) checkedKeys.add(key);
          else checkedKeys.delete(key);
          render();
          if (!data.is_authenticated) {
            writeLocalProgress(progressId, checkedKeys);
            return;
          }
          try {
            const saveResponse = await fetch(`/api/listing-requests/${encodeURIComponent(listingId)}/checklist/progress`, {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ item_key: key, checked }),
            });
            const saved = await saveResponse.json().catch(() => ({}));
            if (!saveResponse.ok || !saved.ok) throw new Error(saved.message || "체크 상태를 저장하지 못했습니다.");
          } catch (error) {
            if (checked) checkedKeys.delete(key);
            else checkedKeys.add(key);
            render();
            window.alert(error.message || "체크 상태를 저장하지 못했습니다.");
          }
        });
      });
    };
    render();
  }

  window.LivingstayListingChecklist = { open };
})();