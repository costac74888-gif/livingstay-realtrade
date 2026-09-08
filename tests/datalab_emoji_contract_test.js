const fs = require("fs");

const index = fs.readFileSync("static/index.html", "utf8");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

[
  ["presale", "🏗️", "준공전"],
  ["tourism_domestic", "🇰🇷", "국내 관광"],
  ["tourism_foreign", "🌏", "외국인 관광"],
  ["tourism_consume", "🛍️", "관광 소비"],
  ["visitor_surge", "🚀", "방문객 급증"],
].forEach(([key, emoji, label]) => {
  const button = new RegExp(
    `data-datalab-key="${key}"[\\s\\S]*?aria-hidden="true">${emoji}<\\/span><span>${label}<\\/span>`,
  );
  expect(button.test(index), `${label} 데이터랩 버튼의 이모지가 올바르지 않습니다.`);
});

console.log("datalab emoji checks passed");