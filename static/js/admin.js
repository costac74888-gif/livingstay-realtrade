/*
 * admin.js — 재사용 가능한 관리자 데이터그리드
 * ------------------------------------------------------------
 * DataGrid 하나로 어떤 테이블이든 붙일 수 있게 컬럼 정의(columns)만 바꾸면
 * 검색·정렬·페이지네이션·추가/수정/삭제·엑셀다운로드가 동작한다.
 * E-2(매물/실거래)에서 columns/endpoint만 교체해 그대로 재사용한다.
 *
 * config = {
 *   mount:       그리드를 그릴 DOM 엘리먼트
 *   endpoint:    목록/생성 API (GET 목록, POST 생성)  예: "/api/admin/buildings"
 *   itemEndpoint(id): 수정/삭제 API URL (기본: endpoint + "/" + id)
 *   exportUrl:   엑셀 다운로드 URL (없으면 버튼 숨김)
 *   idField:     행 식별 키 (기본 "id")
 *   title:       화면 제목
 *   pageSize:    페이지당 행수 (기본 50)
 *   allowAdd:    "+ 추가" 버튼 노출 (기본 true)
 *   allowDelete: 행별 "삭제" 버튼 노출 (기본 true)
 *   searchPlaceholder: 검색창 안내문구 (기본 "건물명·주소 검색")
 *   entityLabel: 모달 제목/삭제확인에 쓰는 대상 이름 (기본 "건물")
 *   columns: [{
 *     key, label,
 *     sortable:  헤더 클릭 정렬 허용
 *     editable:  추가/수정 폼에 표시
 *     required:  추가/수정 시 필수
 *     type:      "text" | "number" | "select"
 *     options:   type==="select" 일 때 값 배열
 *     render(v,row): 셀 커스텀 렌더 (HTML 문자열 반환, 이스케이프 책임은 render 쪽)
 *     hideInTable: 목록 표에는 숨기고 폼에만 노출
 *   }]
 * }
 */

function dgEscape(v) {
  if (v === null || v === undefined) return "";
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

class DataGrid {
  constructor(config) {
    this.cfg = Object.assign(
      {
        idField: "id", pageSize: 50, title: "", allowAdd: true, allowEdit: true, allowDelete: true,
        searchPlaceholder: "건물명·주소 검색", entityLabel: "건물",
        filters: [], rowActions: [],
      },
      config
    );
    // 관리 열은 수정/삭제/커스텀 액션 중 하나라도 있을 때만 그린다.
    this.hasActions = !!(this.cfg.allowEdit || this.cfg.allowDelete || (this.cfg.rowActions && this.cfg.rowActions.length));
    this.state = { q: "", sort: "id", order: "asc", page: 1, filters: {} };
    (this.cfg.filters || []).forEach((f) => {
      this.state.filters[f.key] = f.default != null ? f.default : "";
    });
    this.total = 0;
    this.items = [];
    this._build();
    this.reload();
  }

  itemUrl(id) {
    if (typeof this.cfg.itemEndpoint === "function") return this.cfg.itemEndpoint(id);
    return this.cfg.endpoint + "/" + encodeURIComponent(id);
  }

  tableColumns() {
    return this.cfg.columns.filter((c) => !c.hideInTable);
  }

  formColumns() {
    return this.cfg.columns.filter((c) => c.editable);
  }

  _build() {
    const c = this.cfg;
    const el = c.mount;
    el.innerHTML = `
      <div class="dg-header">
        <h2 class="dg-title">${dgEscape(c.title)}</h2>
        <div class="dg-actions">
          ${c.exportUrl ? `<button class="admin-btn dg-export">엑셀 다운로드</button>` : ""}
          ${c.allowAdd ? `<button class="admin-btn admin-btn-primary dg-add">+ 추가</button>` : ""}
        </div>
      </div>
      <div class="dg-toolbar">
        <input class="admin-input dg-search" type="search" placeholder="${dgEscape(c.searchPlaceholder)}" />
        <button class="admin-btn dg-search-btn">검색</button>
        ${(c.filters || []).map((f) => `
          <select class="admin-input dg-filter" data-filter="${dgEscape(f.key)}">
            ${(f.options || []).map((o) => `<option value="${dgEscape(o.value)}" ${String(this.state.filters[f.key]) === String(o.value) ? "selected" : ""}>${dgEscape(o.label)}</option>`).join("")}
          </select>`).join("")}
        <span class="dg-count"></span>
      </div>
      <div class="dg-table-wrap">
        <table class="dg-table">
          <thead><tr class="dg-head-row"></tr></thead>
          <tbody class="dg-body"></tbody>
        </table>
      </div>
      <div class="dg-pager"></div>
    `;

    this.$search = el.querySelector(".dg-search");
    this.$body = el.querySelector(".dg-body");
    this.$headRow = el.querySelector(".dg-head-row");
    this.$pager = el.querySelector(".dg-pager");
    this.$count = el.querySelector(".dg-count");

    el.querySelector(".dg-search-btn").addEventListener("click", () => {
      this.state.q = this.$search.value.trim();
      this.state.page = 1;
      this.reload();
    });
    this.$search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        this.state.q = this.$search.value.trim();
        this.state.page = 1;
        this.reload();
      }
    });
    el.querySelectorAll(".dg-filter").forEach((sel) => {
      sel.addEventListener("change", () => {
        this.state.filters[sel.getAttribute("data-filter")] = sel.value;
        this.state.page = 1;
        this.reload();
      });
    });
    const addBtn = el.querySelector(".dg-add");
    if (addBtn) addBtn.addEventListener("click", () => this.openForm(null));
    if (c.exportUrl) {
      el.querySelector(".dg-export").addEventListener("click", () => this.exportXlsx());
    }
    this._renderHead();
  }

  _renderHead() {
    const cols = this.tableColumns();
    const ths = cols.map((col) => {
      if (!col.sortable) return `<th>${dgEscape(col.label)}</th>`;
      let arrow = "";
      if (this.state.sort === col.key) arrow = this.state.order === "asc" ? " ▲" : " ▼";
      return `<th class="dg-sortable" data-key="${dgEscape(col.key)}">${dgEscape(col.label)}${arrow}</th>`;
    });
    if (this.hasActions) ths.push(`<th class="dg-col-actions">관리</th>`);
    this.$headRow.innerHTML = ths.join("");
    this.$headRow.querySelectorAll(".dg-sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-key");
        if (this.state.sort === key) {
          this.state.order = this.state.order === "asc" ? "desc" : "asc";
        } else {
          this.state.sort = key;
          this.state.order = "asc";
        }
        this.state.page = 1;
        this.reload();
      });
    });
  }

  async reload() {
    const s = this.state;
    const params = new URLSearchParams({
      q: s.q,
      sort: s.sort,
      order: s.order,
      page: s.page,
      size: this.cfg.pageSize,
    });
    Object.keys(s.filters).forEach((k) => {
      if (s.filters[k] !== "" && s.filters[k] != null) params.set(k, s.filters[k]);
    });
    let res;
    try {
      res = await fetch(this.cfg.endpoint + "?" + params.toString());
    } catch (e) {
      this._bodyMessage("네트워크 오류가 발생했습니다.");
      return;
    }
    if (res.status === 401) {
      window.location.href = "/admin/login";
      return;
    }
    if (!res.ok) {
      this._bodyMessage("목록을 불러오지 못했습니다.");
      return;
    }
    const data = await res.json();
    this.items = data.items || [];
    this.total = data.total || 0;
    this._renderHead();
    this._renderBody();
    this._renderPager();
    this.$count.textContent = `총 ${this.total.toLocaleString()}건`;
  }

  _bodyMessage(text) {
    const span = this.tableColumns().length + (this.hasActions ? 1 : 0);
    this.$body.innerHTML = `<tr><td class="dg-empty" colspan="${span}">${dgEscape(text)}</td></tr>`;
  }

  _renderBody() {
    const cols = this.tableColumns();
    if (!this.items.length) {
      this._bodyMessage("데이터가 없습니다.");
      return;
    }
    const rows = this.items.map((row) => {
      const tds = cols.map((col) => {
        let cell;
        if (typeof col.render === "function") {
          cell = col.render(row[col.key], row);
        } else {
          cell = dgEscape(row[col.key]);
        }
        return `<td>${cell}</td>`;
      });
      const id = row[this.cfg.idField];
      if (this.hasActions) {
        const editBtn = this.cfg.allowEdit
          ? `<button class="dg-icon-btn dg-edit" data-id="${dgEscape(id)}">수정</button>`
          : "";
        const delBtn = this.cfg.allowDelete
          ? `<button class="dg-icon-btn dg-del" data-id="${dgEscape(id)}">삭제</button>`
          : "";
        // 커스텀 액션(예: 승인/반려) — hidden(row)이 true면 그 행에선 숨긴다.
        const acts = (this.cfg.rowActions || [])
          .map((a, i) => (typeof a.hidden === "function" && a.hidden(row)) ? "" :
            `<button class="dg-icon-btn ${dgEscape(a.className || "")}" data-act="${i}" data-id="${dgEscape(id)}">${dgEscape(a.label)}</button>`)
          .join("");
        tds.push(`<td class="dg-col-actions">${editBtn}${acts}${delBtn}</td>`);
      }
      return `<tr>${tds.join("")}</tr>`;
    });
    this.$body.innerHTML = rows.join("");
    this.$body.querySelectorAll(".dg-edit").forEach((b) => {
      b.addEventListener("click", () => {
        const id = b.getAttribute("data-id");
        const row = this.items.find((r) => String(r[this.cfg.idField]) === String(id));
        this.openForm(row);
      });
    });
    this.$body.querySelectorAll(".dg-del").forEach((b) => {
      b.addEventListener("click", () => this.remove(b.getAttribute("data-id")));
    });
    this.$body.querySelectorAll("[data-act]").forEach((b) => {
      b.addEventListener("click", () => {
        const id = b.getAttribute("data-id");
        const row = this.items.find((r) => String(r[this.cfg.idField]) === String(id));
        const action = this.cfg.rowActions[Number(b.getAttribute("data-act"))];
        if (action && typeof action.onClick === "function") action.onClick(row, this);
      });
    });
  }

  _renderPager() {
    const pages = Math.max(Math.ceil(this.total / this.cfg.pageSize), 1);
    const p = this.state.page;
    this.$pager.innerHTML = `
      <button class="admin-btn dg-prev" ${p <= 1 ? "disabled" : ""}>‹ 이전</button>
      <span class="dg-pageinfo">${p} / ${pages}</span>
      <button class="admin-btn dg-next" ${p >= pages ? "disabled" : ""}>다음 ›</button>
    `;
    const prev = this.$pager.querySelector(".dg-prev");
    const next = this.$pager.querySelector(".dg-next");
    if (prev) prev.addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.reload(); } });
    if (next) next.addEventListener("click", () => { if (this.state.page < pages) { this.state.page++; this.reload(); } });
  }

  exportXlsx() {
    const params = new URLSearchParams({
      q: this.state.q,
      sort: this.state.sort,
      order: this.state.order,
    });
    Object.keys(this.state.filters).forEach((k) => {
      if (this.state.filters[k] !== "" && this.state.filters[k] != null) params.set(k, this.state.filters[k]);
    });
    window.location.href = this.cfg.exportUrl + "?" + params.toString();
  }

  // ---- 추가/수정 모달 ----
  openForm(row) {
    const isEdit = !!row;
    const fields = this.formColumns();
    const inputs = fields
      .map((col) => {
        const val = isEdit && row[col.key] != null ? row[col.key] : "";
        let control;
        if (col.type === "select") {
          const opts = ['<option value="">(선택 안 함)</option>']
            .concat(
              (col.options || []).map(
                (o) => `<option value="${dgEscape(o)}" ${String(val) === String(o) ? "selected" : ""}>${dgEscape(o)}</option>`
              )
            )
            .join("");
          control = `<select class="admin-input" data-key="${dgEscape(col.key)}">${opts}</select>`;
        } else if (col.type === "boolean") {
          // 불리언: true/false 값을 보내되 화면에는 사람이 읽는 라벨을 보여준다.
          const on = val === true || String(val) === "true";
          control = `<select class="admin-input" data-key="${dgEscape(col.key)}">
            <option value="false" ${!on ? "selected" : ""}>${dgEscape(col.falseLabel || "아니오")}</option>
            <option value="true" ${on ? "selected" : ""}>${dgEscape(col.trueLabel || "예")}</option>
          </select>`;
        } else if (col.type === "textarea") {
          control = `<textarea class="admin-input" rows="6" data-key="${dgEscape(col.key)}" ${col.required ? "required" : ""}>${dgEscape(val)}</textarea>`;
        } else {
          const t = col.type === "number" ? "number" : "text";
          control = `<input class="admin-input" type="${t}" data-key="${dgEscape(col.key)}" value="${dgEscape(val)}" ${col.required ? "required" : ""} />`;
        }
        return `
          <label class="admin-form-row">
            <span class="admin-form-label">${dgEscape(col.label)}${col.required ? ' <em class="req">*</em>' : ""}</span>
            ${control}
          </label>`;
      })
      .join("");

    const overlay = document.createElement("div");
    overlay.className = "admin-modal-overlay";
    overlay.innerHTML = `
      <div class="admin-modal" role="dialog" aria-modal="true">
        <div class="admin-modal-head">
          <h3>${dgEscape(this.cfg.entityLabel)} ${isEdit ? "수정" : "추가"}</h3>
          <button class="admin-modal-close" aria-label="닫기">×</button>
        </div>
        <form class="admin-modal-body">${inputs}</form>
        <div class="admin-modal-msg" role="alert"></div>
        <div class="admin-modal-foot">
          <button class="admin-btn admin-modal-cancel" type="button">취소</button>
          <button class="admin-btn admin-btn-primary admin-modal-save" type="button">${isEdit ? "저장" : "추가"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector(".admin-modal-close").addEventListener("click", close);
    overlay.querySelector(".admin-modal-cancel").addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

    const msgBox = overlay.querySelector(".admin-modal-msg");
    const saveBtn = overlay.querySelector(".admin-modal-save");
    saveBtn.addEventListener("click", async () => {
      const payload = {};
      overlay.querySelectorAll("[data-key]").forEach((inp) => {
        payload[inp.getAttribute("data-key")] = inp.value;
      });
      // 필수값 프런트 검증
      for (const col of fields) {
        if (col.required && !String(payload[col.key] || "").trim()) {
          msgBox.textContent = `${col.label}은(는) 필수입니다.`;
          return;
        }
      }
      saveBtn.disabled = true;
      const prevText = saveBtn.textContent;
      saveBtn.textContent = "저장 중…";
      try {
        const url = isEdit ? this.itemUrl(row[this.cfg.idField]) : this.cfg.endpoint;
        const method = isEdit ? "PUT" : "POST";
        const res = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.status === 401) { window.location.href = "/admin/login"; return; }
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.ok) {
          close();
          this.reload();
          return;
        }
        msgBox.textContent = data.message || "저장에 실패했습니다.";
      } catch (e) {
        msgBox.textContent = "네트워크 오류가 발생했습니다.";
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = prevText;
      }
    });
  }

  async remove(id) {
    const row = this.items.find((r) => String(r[this.cfg.idField]) === String(id));
    const label = row && row.building_name ? `'${row.building_name}' ` : "";
    if (!window.confirm(`${label}${this.cfg.entityLabel}을(를) 삭제할까요? 되돌릴 수 없습니다.`)) return;
    try {
      const res = await fetch(this.itemUrl(id), { method: "DELETE" });
      if (res.status === 401) { window.location.href = "/admin/login"; return; }
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        this.reload();
        return;
      }
      window.alert(data.message || "삭제에 실패했습니다.");
    } catch (e) {
      window.alert("네트워크 오류가 발생했습니다.");
    }
  }
}

/*
 * dgPromptModal — 사유 입력 등 짧은 텍스트를 받는 재사용 모달.
 * 확인 시 입력값(문자열)을, 취소/닫기 시 null을 resolve한다.
 * required가 true면 빈 값으로 확인을 못 누른다.
 */
function dgPromptModal(opts) {
  const o = Object.assign(
    { title: "입력", label: "내용", placeholder: "", required: true, submitLabel: "확인", submitClass: "admin-btn-primary" },
    opts || {}
  );
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "admin-modal-overlay";
    overlay.innerHTML = `
      <div class="admin-modal" role="dialog" aria-modal="true">
        <div class="admin-modal-head">
          <h3>${dgEscape(o.title)}</h3>
          <button class="admin-modal-close" aria-label="닫기">×</button>
        </div>
        <form class="admin-modal-body">
          <label class="admin-form-row">
            <span class="admin-form-label">${dgEscape(o.label)}${o.required ? ' <em class="req">*</em>' : ""}</span>
            <textarea class="admin-input dg-prompt-input" rows="3" placeholder="${dgEscape(o.placeholder)}"></textarea>
          </label>
        </form>
        <div class="admin-modal-msg" role="alert"></div>
        <div class="admin-modal-foot">
          <button class="admin-btn admin-modal-cancel" type="button">취소</button>
          <button class="admin-btn ${dgEscape(o.submitClass)} admin-modal-ok" type="button">${dgEscape(o.submitLabel)}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector(".dg-prompt-input");
    const msgBox = overlay.querySelector(".admin-modal-msg");
    input.focus();
    const done = (val) => { overlay.remove(); resolve(val); };
    overlay.querySelector(".admin-modal-close").addEventListener("click", () => done(null));
    overlay.querySelector(".admin-modal-cancel").addEventListener("click", () => done(null));
    overlay.addEventListener("click", (e) => { if (e.target === overlay) done(null); });
    overlay.querySelector(".admin-modal-ok").addEventListener("click", () => {
      const v = input.value.trim();
      if (o.required && !v) { msgBox.textContent = `${o.label}은(는) 필수입니다.`; return; }
      done(v);
    });
  });
}
