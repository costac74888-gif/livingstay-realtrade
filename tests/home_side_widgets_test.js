// 홈 좌측 패널의 최근검색/관심물건 위젯 구성을 검증한다.
const fs = require("fs");
const path = require("path");

const index = fs.readFileSync(path.join(__dirname, "..", "static", "index.html"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "static", "css", "main.css"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const recentStart = index.indexOf('id="recentRow"');
const partnerStart = index.indexOf('파트너가 되고 싶으신가요?');
expect(recentStart >= 0 && partnerStart > recentStart, "최근검색 위젯 위치를 찾을 수 없습니다.");
const recentSection = index.slice(recentStart, partnerStart);
expect(recentSection.includes("최근검색"), "최근검색 위젯 제목이 없습니다.");
expect(recentSection.includes("내 방문 기록"), "최근검색 위젯의 방문 기록 보조 라벨이 사라졌습니다.");
expect(!index.includes("최근 관심물건"), "최근 관심물건 위젯이 홈 마크업에 남아 있습니다.");
expect(!index.includes('id="sideFavList"'), "최근 관심물건 위젯의 목록 컨테이너가 남아 있습니다.");
expect(!index.includes('id="sideRankingCard"'), "거래량 TOP 별도 위젯이 데이터랩 편입 후에도 남아 있습니다.");
expect(index.includes('id="dataLabCard"'), "데이터랩 컨테이너가 없습니다.");
["lodging", "volume", "change", "highest", "closure", "rate"].forEach((key) => {
  expect(index.includes(`data-datalab-key="${key}"`), `데이터랩 ${key} 항목이 없습니다.`);
});

expect(main.includes('const HS_RECENT_KEY = "hs_recent_buildings"'), "최근검색 localStorage 키가 바뀌었습니다.");
expect(main.includes("function trackRecentBuilding"), "최근검색 기록 함수가 사라졌습니다.");
expect(main.includes("function renderRecentChips"), "최근검색 렌더링 함수가 사라졌습니다.");
expect(main.includes("renderRecentChips(); // 페이지 로드 시 최근 본 건물 칩 복원"),
  "페이지 로드 시 최근검색 복원 호출이 사라졌습니다.");

const sideFavoriteCallSites = main.match(/(?:^|[^\w])loadSideFavorites\s*\(/g) || [];
expect(sideFavoriteCallSites.length === 1 && main.includes("async function loadSideFavorites"),
  "관심물건 위젯 데이터 로드 호출부가 남아 있습니다.");
expect(main.includes("function loadDataLab"), "데이터랩 전환 로더가 없습니다.");
expect(
  index.indexOf('id="recentRow"') < index.indexOf('id="sideTxList"') &&
  index.indexOf('id="sideTxList"') < index.indexOf('id="dataLabNav"'),
  "좌측 패널 순서가 최근검색 → 실거래목록 → 데이터랩이 아닙니다."
);
expect(
  main.includes('const HS_RECENT_MAX = 3') &&
  main.includes("list.slice(0, HS_RECENT_MAX)"),
  "최근검색 화면 표시 개수가 3개로 제한되지 않았습니다."
);
expect(
  css.includes("grid-template-columns:repeat(3,minmax(0,1fr))") &&
  css.includes(".datalab-content{min-width:0; min-height:210px; margin-top:10px;}"),
  "데이터랩이 3열 탭 그리드와 탭 아래 콘텐츠 구조가 아닙니다."
);
expect(main.includes("/api/stats/price-change-top"), "가격변동 데이터랩 API 연결이 없습니다.");
expect(main.includes("/api/stats/report-rate-by-sido"), "시도별 신고율 데이터랩 API 연결이 없습니다.");

console.log("OK  홈 최근검색·데이터랩 편입·관심물건 제거·localStorage 회귀");