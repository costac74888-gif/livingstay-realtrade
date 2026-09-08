const fs = require("fs");

const html = fs.readFileSync("static/transactions.html", "utf8");
const app = fs.readFileSync("app.py", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(
  html.indexOf('id="txTrendChart"') < html.indexOf('id="board"'),
  "실거래추세 그래프가 실거래 목록 위에 배치되지 않았습니다.",
);
expect(
  html.includes('label:"거래건수"') &&
    html.includes('label:"거래금액(억)"') &&
    html.includes("loadTrendChart(state.favOnly ? items : null)"),
  "실거래 목록의 건수·금액 그래프 또는 검색 연동이 없습니다.",
);
expect(
  html.includes(".tx-trend-empty[hidden]{ display:none; }"),
  "거래 데이터가 있을 때 빈 상태 안내가 그래프 위에 겹칠 수 있습니다.",
);
expect(
  html.includes("q:state.q") &&
    html.includes("transaction_scope:state.transaction_scope") &&
    app.includes('q = request.args.get("q", "").strip()') &&
    app.includes('lodging_type = request.args.get("lodging_type", "").strip()'),
  "실거래추세가 목록의 검색조건을 함께 사용하지 않습니다.",
);

console.log("OK  실거래목록 상단 추세 그래프·검색 연동");