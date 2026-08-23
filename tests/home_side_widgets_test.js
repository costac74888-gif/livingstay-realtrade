// 홈 좌측 패널의 최근검색/관심물건 위젯 구성을 검증한다.
const fs = require("fs");
const path = require("path");

const index = fs.readFileSync(path.join(__dirname, "..", "static", "index.html"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const recentStart = index.indexOf('id="recentRow"');
const rankingStart = index.indexOf('id="sideRankingCard"');
expect(recentStart >= 0 && rankingStart > recentStart, "최근검색 위젯 위치를 찾을 수 없습니다.");
const recentSection = index.slice(recentStart, rankingStart);
expect(recentSection.includes("최근검색"), "최근검색 위젯 제목이 없습니다.");
expect(recentSection.includes("내 방문 기록"), "최근검색 위젯의 방문 기록 보조 라벨이 사라졌습니다.");
expect(!index.includes("최근 관심물건"), "최근 관심물건 위젯이 홈 마크업에 남아 있습니다.");
expect(!index.includes('id="sideFavList"'), "최근 관심물건 위젯의 목록 컨테이너가 남아 있습니다.");

expect(main.includes('const HS_RECENT_KEY = "hs_recent_buildings"'), "최근검색 localStorage 키가 바뀌었습니다.");
expect(main.includes("function trackRecentBuilding"), "최근검색 기록 함수가 사라졌습니다.");
expect(main.includes("function renderRecentChips"), "최근검색 렌더링 함수가 사라졌습니다.");
expect(main.includes("renderRecentChips(); // 페이지 로드 시 최근 본 건물 칩 복원"),
  "페이지 로드 시 최근검색 복원 호출이 사라졌습니다.");

const sideFavoriteCallSites = main.match(/(?:^|[^\w])loadSideFavorites\s*\(/g) || [];
expect(sideFavoriteCallSites.length === 1 && main.includes("async function loadSideFavorites"),
  "관심물건 위젯 데이터 로드 호출부가 남아 있습니다.");

console.log("OK  홈 좌측 최근검색 유지·최근 관심물건 제거·localStorage 회귀");