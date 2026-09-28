const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../static/admin.html"), "utf8");
const start = html.indexOf("function renderDashboardOverview(overview) {");
const end = html.indexOf("function bindDashboardOverview() {", start);
assert(start !== -1 && end > start, "상단 현황 렌더 함수가 있어야 합니다.");

const context = {
  num: (value) => Number(value).toLocaleString("ko-KR"),
};
vm.createContext(context);
vm.runInContext(html.slice(start, end), context);

const members = {
  all: 67, general: 55, agent: 2, operator: 4,
  lodging_operator: 2, loan_consultant: 1, pending: 3,
};
const pending_types = {
  agent: 1, operator: 1, lodging_operator: 0, loan_consultant: 0, presale: 1,
};
const actions = {
  new_signup: 5, direct_listing: 6, broker_listing: 7, buy_request: 8,
  partner_agent: 1, partner_operator: 1, partner_lodging_operator: 0,
  partner_loan_consultant: 0, ota_request: 9, building_request: 10,
  presale_application: 11, bug_report: 12, sync_failure: 13,
};
const output = context.renderDashboardOverview({ members, pending_types, actions });
assert.equal((output.match(/class="dashboard-overview-card/g) || []).length, 20);
assert.match(output, /일반회원[\s\S]*?<strong class="dashboard-overview-value">55<\/strong>/);
assert.match(output, /직거래 매물[\s\S]*?<strong class="dashboard-overview-value">6<\/strong>/);
assert.match(output, /매수 의뢰[\s\S]*?<strong class="dashboard-overview-value">8<\/strong>/);
assert.match(output, /대출상담사 신청[\s\S]*?<strong class="dashboard-overview-value">0<\/strong>/);
assert.match(output, /href="#members" data-overview-member="pending"/);
assert.match(output, /href="#listings"/);
assert.match(output, /href="#requests"/);
assert.match(context.renderDashboardOverview(null), /불러오지 못했습니다/);
console.log("OK  관리자 상단 회원·액션 20개 카드와 이동 경로");