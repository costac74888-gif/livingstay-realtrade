/**
 * buildPageList(current, total, edgeSize=10)
 * 첫 구간과 마지막 구간은 10개씩, 중간 구간은 현재 페이지 ±2를 반환합니다.
 * 반환 예) [1, 2, ..., 10, '...', 423]
 *       또는 [1, '...', 198, 199, 200, 201, 202, '...', 423]
 *       또는 [1, '...', 414, 415, ..., 423]
 */
function buildPageList(current, total, edgeSize) {
  const page = Math.max(1, Math.min(Number(current) || 1, Number(total) || 1));
  const totalPages = Math.max(1, Number(total) || 1);
  const edgeCount = Math.max(5, Number(edgeSize) || 10);
  const pages = [];

  if (totalPages <= edgeCount) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
    return pages;
  }

  // 첫 10개와 마지막 10개는 끊지 않고 보여줘 방향 탐색을 쉽게 한다.
  if (page <= edgeCount) {
    for (let i = 1; i <= edgeCount; i++) pages.push(i);
    pages.push("...", totalPages);
    return pages;
  }
  if (page > totalPages - edgeCount) {
    pages.push(1, "...");
    for (let i = totalPages - edgeCount + 1; i <= totalPages; i++) pages.push(i);
    return pages;
  }

  pages.push(1, "...");
  for (let i = page - 2; i <= page + 2; i++) pages.push(i);
  pages.push("...", totalPages);
  return pages;
}

// 첫/마지막 버튼과 구분되는 좌우 이동 버튼은 한 번에 10페이지씩 이동한다.
function jumpPage(current, total, direction, step) {
  const page = Math.max(1, Number(current) || 1);
  const totalPages = Math.max(1, Number(total) || 1);
  const amount = Math.max(1, Number(step) || 10);
  const next = page + (Number(direction) < 0 ? -amount : amount);
  return Math.max(1, Math.min(totalPages, next));
}

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
        filters: [], rowActions: [], bulkDeleteEndpoint: "", bulkDeleteLabel: "선택 삭제",
        fixedParams: {}, fixedPayload: {},
      },
      config
    );
    // 관리 열은 수정/삭제/커스텀 액션 중 하나라도 있을 때만 그린다.
    this.hasActions = !!(this.cfg.allowEdit || this.cfg.allowDelete || (this.cfg.rowActions && this.cfg.rowActions.length));
    this.state = {
      q: "",
      sort: this.cfg.defaultSort || "id",
      order: this.cfg.defaultOrder || "asc",
      page: 1,
      filters: {},
    };
    (this.cfg.filters || []).forEach((f) => {
      this.state.filters[f.key] = f.default != null ? f.default : "";
    });
    this.total = 0;
    this.items = [];
    this._reloadSeq = 0;
    this._reloadController = null;
    this.selected = new Set();  // allowSelect 모드 선택 상태 (idField 값 문자열 Set)
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
          ${c.bulkDeleteEndpoint ? `<button class="admin-btn dg-bulk-delete" disabled>${dgEscape(c.bulkDeleteLabel)} (0)</button>` : ""}
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
          <thead>
            <tr class="dg-head-row"></tr>
            <tr class="dg-totals-row" style="display:none;"></tr>
          </thead>
          <tbody class="dg-body"></tbody>
        </table>
      </div>
      <div class="dg-pager"></div>
    `;

    this.$search = el.querySelector(".dg-search");
    this.$body = el.querySelector(".dg-body");
    this.$headRow = el.querySelector(".dg-head-row");
    this.$totalsRow = el.querySelector(".dg-totals-row");
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
    this.$bulkDelete = el.querySelector(".dg-bulk-delete");
    if (this.$bulkDelete) {
      this.$bulkDelete.addEventListener("click", () => this.bulkDeleteSelected());
    }
    if (c.exportUrl) {
      el.querySelector(".dg-export").addEventListener("click", () => this.exportXlsx());
    }
    this._renderHead();
    this._updateBulkDeleteButton();
  }

  _renderHead() {
    const cols = this.tableColumns();
    const ths = [];
    // 체크박스 선택 모드: 헤더에 전체선택 체크박스 추가
    if (this.cfg.allowSelect) {
      const pageIds = (this.items || []).map((r) => String(r[this.cfg.idField]));
      const allChecked = pageIds.length > 0 && pageIds.every((id) => this.selected.has(id));
      ths.push(`<th class="dg-col-cb" style="width:36px;text-align:center;padding:4px;"><input type="checkbox" class="dg-select-all"${allChecked ? " checked" : ""} title="이 페이지 전체 선택/해제"></th>`);
    }
    ths.push(...cols.map((col) => {
      const wStyle = col.width ? ` style="min-width:${dgEscape(String(col.width))}"` : "";
      if (!col.sortable && !col.clientSort) return `<th${wStyle}>${dgEscape(col.label)}</th>`;
      let arrow = "";
      if (this._clientSortKey === col.key) {
        arrow = this._clientSortOrder === "asc" ? " ▲" : " ▼";
      } else if (this.state.sort === col.key) {
        arrow = this.state.order === "asc" ? " ▲" : " ▼";
      }
      return `<th class="dg-sortable"${wStyle} data-key="${dgEscape(col.key)}" data-client="${col.clientSort ? "1" : "0"}">${dgEscape(col.label)}${arrow}</th>`;
    }));
    if (this.hasActions) ths.push(`<th class="dg-col-actions">관리</th>`);
    this.$headRow.innerHTML = ths.join("");
    // 전체선택 체크박스 이벤트
    if (this.cfg.allowSelect) {
      const allChk = this.$headRow.querySelector(".dg-select-all");
      if (allChk) {
        allChk.addEventListener("change", () => {
          const pageIds = (this.items || []).map((r) => String(r[this.cfg.idField]));
          if (allChk.checked) { pageIds.forEach((id) => this.selected.add(id)); }
          else { pageIds.forEach((id) => this.selected.delete(id)); }
          this.$body.querySelectorAll(".dg-row-cb").forEach((cb) => { cb.checked = allChk.checked; });
          this._dispatchSelectionChange();
        });
      }
    }
    this.$headRow.querySelectorAll(".dg-sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-key");
        const isClient = th.getAttribute("data-client") === "1";
        if (isClient) {
          // 서버로 안 가고, 현재 페이지에 이미 로드된 items만 재정렬
          if (this._clientSortKey === key) {
            this._clientSortOrder = this._clientSortOrder === "asc" ? "desc" : "asc";
          } else {
            this._clientSortKey = key;
            this._clientSortOrder = "asc";
          }
          this.state.sort = null; // 서버 정렬 상태와 헷갈리지 않게 해제
          const dir = this._clientSortOrder === "asc" ? 1 : -1;
          // sortValue 함수가 정의된 컬럼이면 우선 사용 (예: report_rate = biz_units/units)
          const col = (this.cfg.cols || []).find((c) => c.key === key);
          const getVal = col && col.sortValue ? col.sortValue : (row) => row[key];
          this.items.sort((a, b) => {
            const av = getVal(a);
            const bv = getVal(b);
            // 숫자 비교 (null/undefined는 가장 뒤로)
            if (typeof av === "number" || typeof bv === "number") {
              return ((av == null ? -Infinity : av) - (bv == null ? -Infinity : bv)) * dir;
            }
            return ((av || "").toString()).localeCompare((bv || "").toString(), "ko") * dir;
          });
          this._renderHead();
          this._renderBody();
          return;
        }
        this._clientSortKey = null; // 서버 정렬로 전환 시 클라이언트 정렬 표시 해제
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
    const requestSeq = ++this._reloadSeq;
    if (this._reloadController) this._reloadController.abort();
    this._reloadController = new AbortController();
    const signal = this._reloadController.signal;
    this._bodyMessage("불러오는 중…");
    this.$count.textContent = "조회 중…";
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
    Object.keys(this.cfg.fixedParams || {}).forEach((k) => {
      params.set(k, this.cfg.fixedParams[k]);
    });
    let res;
    try {
      res = await fetch(this.cfg.endpoint + "?" + params.toString(), { signal });
    } catch (e) {
      if (e && e.name === "AbortError") return;
      if (requestSeq !== this._reloadSeq) return;
      this._bodyMessage("네트워크 오류가 발생했습니다.");
      this.$count.textContent = "조회 실패";
      return;
    }
    if (requestSeq !== this._reloadSeq) return;
    if (res.status === 401) {
      window.location.href = "/admin/login";
      return;
    }
    if (!res.ok) {
      this._bodyMessage("목록을 불러오지 못했습니다.");
      this.$count.textContent = "조회 실패";
      return;
    }
    let data;
    try {
      data = await res.json();
    } catch (e) {
      if (requestSeq !== this._reloadSeq) return;
      this._bodyMessage("목록 응답을 확인하지 못했습니다.");
      this.$count.textContent = "조회 실패";
      return;
    }
    if (requestSeq !== this._reloadSeq) return;
    this.items = data.items || [];
    this.total = data.total || 0;
    this.totals = data.totals || null;
    this._renderHead();
    this._renderBody();
    this._renderTotals();
    this._renderPager();
    this.$count.textContent = `총 ${this.total.toLocaleString()}건`;
  }

  // ─── 합계 행 렌더링 ───────────────────────────────────────────────────────
  // cfg.totalsRow: { [colKey]: (totals) => HTML문자열 } 형태로 정의.
  // API 응답의 data.totals 객체를 받아 헤더 바로 아래 고정 행에 표시한다.
  // 합산이 의미 없는 컬럼은 totalsRow에서 생략하면 빈 칸으로 표시된다.
  _renderTotals() {
    if (!this.$totalsRow) return;
    if (!this.cfg.totalsRow || !this.totals) {
      this.$totalsRow.style.display = "none";
      return;
    }
    const cols = this.tableColumns();
    const tds = [];
    // allowSelect 모드: 체크박스 열 자리 확보
    if (this.cfg.allowSelect) tds.push(`<td></td>`);
    cols.forEach((col) => {
      const fn = this.cfg.totalsRow[col.key];
      // fn이 있으면 HTML 반환 함수로 호출, 없으면 빈 칸
      tds.push(`<td class="dg-totals-cell">${fn ? fn(this.totals) : ""}</td>`);
    });
    // 관리 열 자리 확보
    if (this.hasActions) tds.push(`<td></td>`);
    this.$totalsRow.innerHTML = tds.join("");
    this.$totalsRow.style.display = "";
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
      const id = row[this.cfg.idField];
      const tds = [];
      // 체크박스 선택 모드: 행마다 개별 체크박스 추가
      if (this.cfg.allowSelect) {
        const chk = this.selected.has(String(id)) ? " checked" : "";
        tds.push(`<td class="dg-col-cb" style="text-align:center;padding:4px;"><input type="checkbox" class="dg-row-cb" data-id="${dgEscape(id)}"${chk}></td>`);
      }
      cols.forEach((col) => {
        let cell;
        if (typeof col.render === "function") {
          cell = col.render(row[col.key], row);
        } else if (col.key === "building_name") {
          // building_id 또는 master_building_id가 있으면 새 창 링크로 자동 렌더링
          const bid = row.building_id || row.master_building_id;
          const text = dgEscape(row[col.key]);
          cell = bid
            ? `<a href="/building/${bid}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;border-bottom:1px dashed var(--brass);">${text}</a>`
            : text;
        } else {
          cell = dgEscape(row[col.key]);
        }
        tds.push(`<td>${cell}</td>`);
      });
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
    // 체크박스 행 단위 이벤트 바인딩
    if (this.cfg.allowSelect) {
      this.$body.querySelectorAll(".dg-row-cb").forEach((cb) => {
        cb.addEventListener("change", () => {
          const cbId = cb.getAttribute("data-id");
          if (cb.checked) { this.selected.add(cbId); } else { this.selected.delete(cbId); }
          // 전체선택 체크박스 상태 동기화
          const allChk = this.$headRow.querySelector(".dg-select-all");
          if (allChk) {
            const pageIds = this.items.map((r) => String(r[this.cfg.idField]));
            allChk.checked = pageIds.length > 0 && pageIds.every((pid) => this.selected.has(pid));
          }
          this._dispatchSelectionChange();
        });
      });
    }
  }

  _dispatchSelectionChange() {
    this._updateBulkDeleteButton();
    this.cfg.mount.dispatchEvent(new CustomEvent("dg:selectionchange", {
      bubbles: true,
      detail: { count: this.selected.size, ids: [...this.selected] },
    }));
  }

  selectedIds() {
    return [...this.selected].map(Number).filter((n) => !isNaN(n));
  }

  selectedItems() {
    return this.items.filter((r) => this.selected.has(String(r[this.cfg.idField])));
  }

  _updateBulkDeleteButton() {
    if (!this.$bulkDelete) return;
    const count = this.selected.size;
    this.$bulkDelete.disabled = count === 0;
    this.$bulkDelete.textContent = `${this.cfg.bulkDeleteLabel} (${count})`;
  }

  async bulkDeleteSelected() {
    const ids = this.selectedIds();
    if (!ids.length || !this.cfg.bulkDeleteEndpoint) return;
    const warning =
      `선택한 ${ids.length}건의 ${this.cfg.entityLabel}을(를) 완전히 삭제할까요?\n\n` +
      "연결된 사진, 찜, 채팅 및 변경 이력도 함께 삭제되며 복구할 수 없습니다.";
    if (!window.confirm(warning)) return;
    const btn = this.$bulkDelete;
    if (btn) { btn.disabled = true; btn.textContent = "삭제 중…"; }
    try {
      const res = await fetch(this.cfg.bulkDeleteEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (res.status === 401) { window.location.href = "/admin/login"; return; }
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        window.alert(data.message || "선택 항목 삭제에 실패했습니다.");
        return;
      }
      this.selected.clear();
      this._updateBulkDeleteButton();
      window.alert(`${data.deleted || 0}건이 삭제되었습니다.${data.skipped ? ` (${data.skipped}건은 이미 없거나 삭제할 수 없습니다.)` : ""}`);
      this.reload();
    } catch (e) {
      window.alert("네트워크 오류가 발생했습니다.");
    } finally {
      this._updateBulkDeleteButton();
    }
  }

  _renderPager() {
    const totalPages = Math.max(Math.ceil(this.total / this.cfg.pageSize), 1);
    const p = this.state.page;
    const pageNums = buildPageList(p, totalPages, 10);
    const pageHtml = pageNums.map((n) =>
      n === "..."
        ? `<span class="dg-page-ellipsis">…</span>`
        : `<button class="dg-page-btn${n === p ? " active" : ""}" data-pg="${n}">${n}</button>`
    ).join("");
    this.$pager.innerHTML =
      `<button class="dg-nav-btn dg-first" ${p <= 1 ? "disabled" : ""} title="처음 페이지로 이동" aria-label="처음 페이지로 이동">|«</button>` +
      `<button class="dg-nav-btn dg-prev" ${p <= 1 ? "disabled" : ""} title="이전 10페이지로 이동" aria-label="이전 10페이지로 이동">&#8249;</button>` +
      pageHtml +
      `<button class="dg-nav-btn dg-next" ${p >= totalPages ? "disabled" : ""} title="다음 10페이지로 이동" aria-label="다음 10페이지로 이동">&#8250;</button>` +
      `<button class="dg-nav-btn dg-last" ${p >= totalPages ? "disabled" : ""} title="마지막 페이지로 이동" aria-label="마지막 페이지로 이동">»|</button>`;
    this.$pager.querySelector(".dg-first").addEventListener("click", () => {
      if (this.state.page > 1) { this.state.page = 1; this.reload(); }
    });
    this.$pager.querySelector(".dg-prev").addEventListener("click", () => {
      if (this.state.page > 1) { this.state.page = jumpPage(this.state.page, totalPages, -1, 10); this.reload(); }
    });
    this.$pager.querySelector(".dg-next").addEventListener("click", () => {
      if (this.state.page < totalPages) { this.state.page = jumpPage(this.state.page, totalPages, 1, 10); this.reload(); }
    });
    this.$pager.querySelector(".dg-last").addEventListener("click", () => {
      if (this.state.page < totalPages) { this.state.page = totalPages; this.reload(); }
    });
    this.$pager.querySelectorAll(".dg-page-btn:not(.active)").forEach((btn) => {
      btn.addEventListener("click", () => { this.state.page = Number(btn.dataset.pg); this.reload(); });
    });
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
        const initVal = (!isEdit && typeof col.default === "function") ? col.default() : val;
        let control;
        if (col.type === "file") {
          const existing = isEdit && row[col.key] ? row[col.key] : "";
          control = `
            <input type="file" accept="application/pdf" class="admin-input" data-filekey="${dgEscape(col.key)}" />
            ${existing ? `<div class="admin-form-hint">현재 첨부됨 (새 파일을 선택하면 교체, 비워두면 유지)</div>` : ""}
            <input type="hidden" data-key="${dgEscape(col.key)}" value="${dgEscape(existing)}" />`;
        } else if (col.type === "imageUrl") {
          // 이미지 URL 텍스트 입력 + 파일 업로드 버튼 조합
          // 업로드 성공 시 반환된 절대 URL을 텍스트 입력에 자동 채움; 수동 입력도 허용
          control = `
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
              <input class="admin-input" type="text" data-key="${dgEscape(col.key)}"
                     value="${dgEscape(initVal)}" ${col.required ? "required" : ""}
                     placeholder="${dgEscape(col.placeholder || "https://...")}"
                     style="flex:1;min-width:200px;" />
              <label style="cursor:pointer;white-space:nowrap;">
                <input type="file" accept=".jpg,.jpeg,.png" style="display:none;"
                       data-imgupload="${dgEscape(col.key)}"
                       data-imgendpoint="${dgEscape(col.uploadEndpoint || "")}" />
                <span class="admin-btn" style="padding:4px 10px;font-size:12px;">📁 파일 선택</span>
              </label>
            </div>
            <div class="admin-form-hint" data-imgstatus="${dgEscape(col.key)}" style="min-height:16px;"></div>`;
        } else if (col.type === "date") {
          // <input type="date"> — 브라우저 달력 피커 자동 지원, 값은 항상 YYYY-MM-DD
          control = `<input class="admin-input" type="date" data-key="${dgEscape(col.key)}" value="${dgEscape(initVal)}" ${col.required ? "required" : ""} />`;
        } else if (col.type === "select") {
          const opts = ['<option value="">(선택 안 함)</option>']
            .concat(
              (col.options || []).map(
                (o) => `<option value="${dgEscape(o)}" ${String(initVal) === String(o) ? "selected" : ""}>${dgEscape(o)}</option>`
              )
            )
            .join("");
          control = `<select class="admin-input" data-key="${dgEscape(col.key)}">${opts}</select>`;
        } else if (col.type === "boolean") {
          // 불리언: true/false 값을 보내되 화면에는 사람이 읽는 라벨을 보여준다.
          const on = initVal === true || String(initVal) === "true";
          control = `<select class="admin-input" data-key="${dgEscape(col.key)}">
            <option value="false" ${!on ? "selected" : ""}>${dgEscape(col.falseLabel || "아니오")}</option>
            <option value="true" ${on ? "selected" : ""}>${dgEscape(col.trueLabel || "예")}</option>
          </select>`;
        } else if (col.type === "textarea") {
          control = `<textarea class="admin-input" rows="6" data-key="${dgEscape(col.key)}" ${col.required ? "required" : ""}>${dgEscape(initVal)}</textarea>`;
        } else {
          const t = col.type === "number" ? "number" : "text";
          control = `<input class="admin-input" type="${t}" data-key="${dgEscape(col.key)}" value="${dgEscape(initVal)}" ${col.required ? "required" : ""} />`;
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

    // imageUrl 타입 컬럼: 파일 선택 → 업로드 → URL 텍스트 입력에 자동 채움
    overlay.querySelectorAll("[data-imgupload]").forEach((fileInput) => {
      const key = fileInput.getAttribute("data-imgupload");
      const endpoint = fileInput.getAttribute("data-imgendpoint");
      const textInput = overlay.querySelector(`[data-key="${key}"]`);
      const statusEl = overlay.querySelector(`[data-imgstatus="${key}"]`);
      if (!endpoint || !textInput) return;
      // label > span 클릭 → hidden file input 클릭 위임
      const span = fileInput.nextElementSibling;
      if (span) span.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", async () => {
        const f = fileInput.files && fileInput.files[0];
        if (!f) return;
        if (statusEl) { statusEl.style.color = ""; statusEl.textContent = "업로드 중…"; }
        const fd = new FormData();
        fd.append("file", f);
        try {
          const res = await fetch(endpoint, { method: "POST", body: fd });
          if (res.status === 401) { window.location.href = "/admin/login"; return; }
          const d = await res.json().catch(() => ({}));
          if (res.ok && d.ok) {
            textInput.value = d.image_url;
            if (statusEl) { statusEl.style.color = "#1a7f37"; statusEl.textContent = "✓ 업로드 완료"; }
          } else {
            if (statusEl) { statusEl.style.color = "#b3261e"; statusEl.textContent = d.message || "업로드에 실패했습니다."; }
          }
        } catch (_) {
          if (statusEl) { statusEl.style.color = "#b3261e"; statusEl.textContent = "네트워크 오류가 발생했습니다."; }
        }
      });
    });

    const msgBox = overlay.querySelector(".admin-modal-msg");
    const saveBtn = overlay.querySelector(".admin-modal-save");
    saveBtn.addEventListener("click", async () => {
      const payload = Object.assign({}, this.cfg.fixedPayload || {});
      // 파일 업로드 먼저 처리 — 업로드 성공 시 반환된 키를 payload에 세팅
      const fileInputs = overlay.querySelectorAll("[data-filekey]");
      for (const fi of fileInputs) {
        if (fi.files && fi.files[0]) {
          const uploadCol = fields.find((c) => c.key === fi.getAttribute("data-filekey"));
          if (uploadCol && uploadCol.uploadEndpoint) {
            const fd = new FormData();
            fd.append("file", fi.files[0]);
            const upRes = await fetch(uploadCol.uploadEndpoint, { method: "POST", body: fd });
            const upData = await upRes.json().catch(() => ({}));
            if (!upRes.ok || !upData.ok) {
              msgBox.textContent = upData.message || "파일 업로드에 실패했습니다.";
              return;
            }
            payload[uploadCol.key] = upData.attachment_key;
          }
        }
      }
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
        msgBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (e) {
        msgBox.textContent = "네트워크 오류가 발생했습니다.";
        msgBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
