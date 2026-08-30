// 건물상세 명칭 출처별 상태 라벨·제안 링크 회귀 테스트.
const fs = require("fs");

const app = fs.readFileSync("app.py", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");
const brhub = fs.readFileSync("sync_brhub.py", "utf8");

function expect(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

// 공개 건물상세 API가 자동명명 출처를 클라이언트에 전달하는지 확인한다.
const detailApi = app.slice(
  app.indexOf('@app.route("/api/building/<int:building_id>")'),
  app.indexOf('@app.route("/api/building/<int:building_id>")') + 18000,
);
expect(
  detailApi.includes("mb.building_name_source"),
  "건물상세 API SELECT에 building_name_source가 없습니다.",
);

const detailRender = main.slice(
  main.indexOf("const lodgingNameTag ="),
  main.indexOf("const lodgingNameTag =") + 7000,
);
expect(
  detailRender.includes(
    'const namePendingNeedsReview = b.name_pending && b.building_name_source !== "lodging_report";',
  ),
  "명칭 확인 필요 여부가 영업신고 기준 출처를 제외하지 않습니다.",
);
expect(
  detailRender.includes("${namePendingNeedsReview ?") &&
    detailRender.includes("정식명칭 확인중"),
  "정식명칭 확인중 라벨이 공통 조건을 사용하지 않습니다.",
);
expect(
  detailRender.includes("${namePendingNeedsReview && b.sgg_cd && b.umd_nm && b.jibun ?") &&
    detailRender.includes("건물명 제안하기"),
  "건물명 제안하기 링크가 공통 조건을 사용하지 않습니다.",
);

// 실제 조건의 truth table: 자동명명만 두 요소를 모두 숨긴다.
const shouldShowPendingActions = (building) =>
  Boolean(building.name_pending && building.building_name_source !== "lodging_report");
expect(
  shouldShowPendingActions({ name_pending: true, building_name_source: "lodging_report" }) === false,
  "영업신고 기준 자동명명 건물에서 명칭 확인 요소가 노출될 수 있습니다.",
);
expect(
  shouldShowPendingActions({ name_pending: true, building_name_source: "pending" }) === true,
  "일반 미확정 건물의 명칭 확인 요소가 숨겨집니다.",
);
expect(
  shouldShowPendingActions({ name_pending: false, building_name_source: "official" }) === false,
  "공식명칭 확정 건물에서 명칭 확인 요소가 노출될 수 있습니다.",
);

const adminBuildingColumn = admin.slice(
  admin.indexOf('{ key: "building_name"'),
  admin.indexOf('{ key: "building_name"') + 1800,
);
expect(
  adminBuildingColumn.includes(
    "row && row.name_pending && !row.building_name_report_display",
  ),
  "관리자 목록의 명칭 미확정 배지가 활성 영업신고 대표 표시를 제외하지 않습니다.",
);
expect(
  adminBuildingColumn.includes("row.display_building_name || v") &&
    adminBuildingColumn.includes("row && row.building_name_report_display"),
  "관리자 목록이 활성 영업신고 상호와 영업신고 기준 배지를 표시하지 않습니다.",
);

expect(
  brhub.includes("from lodging_matching import refresh_auto_building_names"),
  "건물수집 배치에 자동명명 갱신 모듈이 연결되지 않았습니다.",
);
expect(
  brhub.includes("RETURNING id") && brhub.includes('new_building_ids.add(inserted["id"])'),
  "새로 INSERT된 건물 ID 추적이 없습니다.",
);
expect(
  brhub.includes("refresh_auto_building_names(conn, sorted(new_building_ids))") &&
    brhub.includes("refresh_auto_building_names(conn)"),
  "건물수집의 일일 부분 갱신 또는 완료 전체 갱신이 없습니다.",
);

expect(
  app.includes('biz_status_filter = (request.args.get("biz_status_filter") or "").strip()') &&
    app.includes('biz_status_filter in ("active", "closed")') &&
    app.includes("def _building_ids_by_lodging_status") &&
    app.includes("도로명 우선·지번 보조") &&
    app.includes("ACTIVE_LODGING_STATUS"),
  "건물마스터 영업상태 필터 백엔드 조건이 없습니다.",
);
const adminBuildingFilters = admin.slice(
  admin.indexOf('filters: [', admin.indexOf('buildings:')),
  admin.indexOf('columns: [', admin.indexOf('buildings:')),
);
expect(
  adminBuildingFilters.includes('{ key: "biz_status_filter", default: "", options: [') &&
    adminBuildingFilters.includes('{ value: "active", label: "정상 운영중만" }') &&
    adminBuildingFilters.includes('{ value: "closed", label: "폐업만" }'),
  "건물마스터 영업상태 필터 옵션이 없습니다.",
);

console.log("OK  건물명 출처별 정식명칭 라벨·제안 링크 회귀 점검");