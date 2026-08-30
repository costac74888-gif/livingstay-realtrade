"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/admin.js", "utf8");
const context = {
  console,
  URLSearchParams,
  AbortController,
  setTimeout,
  clearTimeout,
  window: { location: { href: "" } },
};
vm.runInNewContext(`${source}\nthis.__DataGrid = DataGrid;`, context);
const DataGrid = context.__DataGrid;

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function gridForReload() {
  const grid = Object.create(DataGrid.prototype);
  grid.state = { q: "", sort: "id", order: "asc", page: 1, filters: {} };
  grid.cfg = { endpoint: "/api/test", pageSize: 50 };
  grid._reloadSeq = 0;
  grid._reloadController = null;
  grid.$count = { textContent: "" };
  grid.messages = [];
  grid._bodyMessage = (text) => grid.messages.push(text);
  grid._renderHead = () => {};
  grid._renderBody = () => {};
  grid._renderTotals = () => {};
  grid._renderPager = () => {};
  return grid;
}

(async () => {
  const first = deferred();
  const second = deferred();
  let call = 0;
  context.fetch = () => (++call === 1 ? first.promise : second.promise);

  const grid = gridForReload();
  const firstReload = grid.reload();
  const secondReload = grid.reload();
  second.resolve({
    ok: true,
    status: 200,
    json: async () => ({ total: 1, items: [{ id: "new" }] }),
  });
  await secondReload;
  first.resolve({
    ok: true,
    status: 200,
    json: async () => ({ total: 9, items: [{ id: "old" }] }),
  });
  await firstReload;

  assert.strictEqual(grid.total, 1, "이전 요청 총건수가 최신 결과를 덮었습니다.");
  assert.strictEqual(grid.items[0].id, "new", "이전 요청 행이 최신 결과를 덮었습니다.");
  assert.strictEqual(grid.$count.textContent, "총 1건");

  context.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => { throw new SyntaxError("invalid json"); },
  });
  await grid.reload();
  assert.strictEqual(grid.$count.textContent, "조회 실패");
  assert.strictEqual(grid.messages.at(-1), "목록 응답을 확인하지 못했습니다.");

  console.log("OK  관리자 필터 요청 경합·잘못된 응답 로딩 종료 점검");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});