/* 관리자 페이지네이션 표시 규칙 회귀 테스트 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/admin.js", "utf8");
const context = { console };
vm.runInNewContext(`${source}\nthis.__buildPageList = buildPageList;`, context);
const buildPageList = (...args) => Array.from(context.__buildPageList(...args));

const range = (start, end) => Array.from({ length: end - start + 1 }, (_, i) => start + i);

assert.deepStrictEqual(
  buildPageList(1, 423, 10),
  [...range(1, 10), "...", 423],
  "1페이지에서는 첫 10개와 마지막 페이지를 보여줘야 합니다"
);
assert.deepStrictEqual(
  buildPageList(200, 423, 10),
  [1, "...", 198, 199, 200, 201, 202, "...", 423],
  "중간 페이지에서는 현재 ±2를 보여줘야 합니다"
);
assert.deepStrictEqual(
  buildPageList(423, 423, 10),
  [1, "...", ...range(414, 423)],
  "마지막 페이지에서는 뒤쪽 10개를 자연스럽게 이어 보여줘야 합니다"
);
assert.deepStrictEqual(
  buildPageList(420, 423, 10),
  [1, "...", ...range(414, 423)],
  "마지막 10페이지 구간에서는 뒤쪽 10개를 유지해야 합니다"
);
assert.deepStrictEqual(buildPageList(2, 4, 10), [1, 2, 3, 4], "작은 목록은 생략 없이 보여줘야 합니다");

console.log("OK  관리자 페이지네이션 처음/마지막 이동용 번호 표시 규칙");