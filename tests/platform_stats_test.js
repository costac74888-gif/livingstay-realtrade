// 홈 검색바에서 데이터 규모 위젯은 제거하되, 데이터랩 재사용용 함수/API는 보존되는지 점검한다.
const fs = require("fs");

const index = fs.readFileSync("static/index.html", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");

if (index.includes('id="platformStats"') || index.includes('data-platform-stat=')) {
  throw new Error("검색바 영역의 플랫폼 통계 위젯 마크업이 남아 있습니다.");
}
if (!main.includes("async function loadPlatformStats(){")) {
  throw new Error("데이터랩 재사용용 loadPlatformStats 함수가 사라졌습니다.");
}
if (!main.includes('/api/stats/platform-summary')) {
  throw new Error("platform-summary API 재사용 경로가 사라졌습니다.");
}
if (main.includes("loadPlatformStats();")) {
  throw new Error("홈 초기화에서 loadPlatformStats 호출이 남아 있습니다.");
}

console.log("OK  홈 검색바 플랫폼 통계 위젯 제거·함수/API 보존");