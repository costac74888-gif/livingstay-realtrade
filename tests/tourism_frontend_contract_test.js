const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const main = fs.readFileSync(path.join(root, "static/js/main.js"), "utf8");
const html = fs.readFileSync(path.join(root, "static/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "static/css/main.css"), "utf8");
function expect(value, message) { if (!value) throw new Error(message); }

expect(main.includes("const visitorCount = Number(item.visitor_count)") &&
  main.includes('clusterLevel === "sido" || clusterLevel === "sgg"') &&
  main.includes("cluster-visitor-count"), "시도·시군구 방문객 보조 표기가 없습니다.");
expect(html.includes('id="tourismAttractionsTool"') && html.includes(">관광지</span>"),
  "관광지 지도 도구 버튼이 없습니다.");
expect(main.includes('fetch("/api/tourism/attractions/top20")') &&
  main.includes("_tourismAttractionsLoaded") &&
  main.includes("_setTourismAttractionsVisible") &&
  main.includes("DataLab 검색 순위"),
  "관광지 순위 오버레이의 캐시·대표위치 안내 계약이 없습니다.");
expect(main.includes("function _tourismAttractionFanOffset") &&
  main.includes("coordinateGroups = new Map()") &&
  main.includes("duplicateIndex") &&
  main.includes("duplicateCount"),
  "동일 시군구 중심점 관광지 마커의 팬 오프셋 계약이 없습니다.");
expect(main.includes('item?.coordinate_scope === "sgg_office_fallback"') &&
  main.includes('"시군구청 대표 위치"') &&
  main.includes('"시군구 대표 위치"'),
  "관광지 좌표 범위별 대표 위치 안내가 없습니다.");
expect(main.includes("renderedCount > 0") &&
  main.includes("if (!_tourismAttractionOverlays.length)"),
  "렌더 가능한 관광지 0건일 때 비활성 상태 유지 계약이 없습니다.");
expect(main.includes("TOURISM_ATTRACTIONS_TTL_MS") &&
  main.includes("_tourismAttractionsLoadedAt") &&
  main.includes("_clearTourismAttractions()"),
  "관광지 레이어의 주기적 새 데이터 갱신 계약이 없습니다.");
expect(css.includes(".map-tourism-marker") && css.includes(".map-tourism-info"),
  "관광지 마커/정보창 스타일이 CSS에 없습니다.");
expect(main.includes('b.lodging_type === "에어비앤비"') &&
  main.includes("tourism_foreign_ratio") &&
  main.includes("외국인 방문 활성 지역") &&
  main.includes("TOP3 방문국"),
  "에어비앤비 외국인 방문 활성 배지가 없습니다.");
expect(main.includes("/tourism-stats") &&
  main.includes('new Set(["캠핑", "농어촌민박", "한옥"])') &&
  main.includes('id = "bTourismAttractions"') &&
  main.includes("_isActiveBuilding(buildingId, requestToken)"),
  "적격 상세의 주변 인기 관광지 조회/멱등성 계약이 없습니다.");
expect(css.includes(".b-tourism-attractions") && css.includes(".b-foreign-visitor-badge"),
  "관광 상세 보조 정보 스타일이 CSS에 없습니다.");
console.log("tourism frontend contract checks passed");