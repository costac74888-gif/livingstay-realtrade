const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");
const manage = fs.readFileSync("static/lodging_operator_manage.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(main.includes('const STRUCTURE_A_TYPES = ["생활"]'), "Structure A 유형 목록이 없습니다.");
expect(main.includes('const STRUCTURE_B_TYPES = ["에어비앤비", "캠핑", "농어촌민박", "한옥", "일반", "관광"]'), "Structure B 유형 목록이 없습니다.");
expect(main.includes('firstValid("booking_url")') && main.includes('firstValid("airbnb_url")') && main.includes("campingReservationUrl"), "운영자 우선·캠핑 예약 URL 보조 우선순위가 없습니다.");
expect(!main.includes('|| firstValid("gocamping_url")'), "고캠핑 정보 링크가 예약 URL 우선순위에 남아 있습니다.");
expect(main.includes('data-panel="operations"') && main.includes('data-panel="property"'), "운영정보/부동산정보 탭이 없습니다.");
expect(main.includes("window.__openBuildingId === Number(id)") && main.includes("_buildingDetailRequestToken === requestToken"), "건물 전환 시 오래된 응답 차단이 없습니다.");
expect(main.includes('href="https://jnjclub.co.kr/"') && main.includes('/static/banner_biz_report.png'), "행정운영 영업신고업소 아래 숙박업등록 배너가 없습니다.");
expect(main.includes("const bizReportBannerHtml") && main.includes(") + bizReportBannerHtml;"), "미준공 건물의 행정운영에 숙박업등록 배너가 없습니다.");
expect(main.includes("${lodgingListHtml}\n      ${bizReportBannerHtml}"), "영업상호 목록 다음에 숙박업등록 배너가 배치되지 않았습니다.");
expect(main.includes('operations: ["bCampCard", "bNonCampingOperationsCard", "bReservationCard", "bLodgingOperatorCard", "bOperatorInfoDisclaimer"]'), "운영자 정보 고지가 운영정보 맨 아래에 배치되지 않았습니다.");
expect(main.includes("_reservationBar(b, false)"), "생활·관광·일반숙박의 미연결 예약 안내가 숨겨지지 않았습니다.");
expect(main.includes('"bAreaFilterCard", "bTrendCard", "bTimelineCard", "bTxCard"'), "Structure B 부동산 패널에 실거래 카드가 묶이지 않았습니다.");
expect(main.includes('property: [\n      "bRequestCard", "bSignalCard", "bAdminCard"'), "매물내놓기·매수의뢰와 숙박알리미·행정운영이 부동산정보 패널에 묶이지 않았습니다.");
expect(
  main.includes('<div class="b-request-privacy-note">매물내놓기와 매수의뢰 비공개 진행가능</div>') &&
  css.includes(".b-request-privacy-note"),
  "매물내놓기·매수의뢰 비공개 진행 안내가 없습니다.",
);
expect(main.includes('class="bld-photo-actions bld-photo-actions-left"') && main.includes('class="bld-photo-actions bld-photo-actions-right"'), "사진 위 뒤로가기·관심·공유 버튼이 없습니다.");
expect(
  main.includes('aria-label="이전 목록으로"') &&
  main.includes("history.state?.buildingId === Number(id)") &&
  main.includes("restoreDefaultPanel(event.state?.returnDataLabKey || \"\")") &&
  main.includes('panel.innerHTML = DEFAULT_SIDE_PANEL_HTML;\n  closeMapSearchbar();') &&
  main.includes("function scrollHomeListsToStart()") &&
  main.includes("if (panel) panel.scrollTop = 0;") &&
  main.includes("Promise.resolve(loadDataLab(returnDataLabKey)).finally(scrollHomeListsToStart)"),
  "사진 위 뒤로가기와 브라우저 뒤로가기가 이전 목록 상태를 복원하지 않습니다.",
);
expect(main.includes('class="bld-photo-empty-logo"') && main.includes('/static/home_stay_footer_logo.png'), "사진 없음 상단 바의 가로 로고가 없습니다.");
expect(main.includes('id="bMapBtn" class="b-map-return-btn"'), "우편번호 줄의 지도위치 버튼이 없습니다.");
expect(
  main.includes('manageParams.set("type", manageType)') &&
  main.includes('manageParams.set("building_id", String(Number(b.building_id)))') &&
  main.includes('`/lodging-operator/manage${manageQuery ? `?${manageQuery}` : ""}`'),
  "예약 미연결 운영자 연결 링크에 숙박 유형과 건물이 함께 전달되지 않습니다.",
);
expect(main.includes('aria-controls="bOperationsPanel"') && main.includes('role="tabpanel"'), "탭과 패널의 접근성 연결이 없습니다.");
expect(
  main.includes('const phone = String(b.lr_phone || op.facility_phone || "").trim();') &&
  main.includes('class="camp-quick-actions b-ops-contact-actions"') &&
  main.includes('class="camp-contact-btn camp-homepage-btn"') &&
  main.includes('class="camp-contact-btn camp-phone-btn"') &&
  main.includes("운영자가 홈페이지를 등록하면 연결됩니다") &&
  main.includes("정부 공개자료에 전화번호가 없습니다") &&
  css.includes(".b-ops-contact-actions{grid-template-columns:repeat(2,minmax(0,1fr))}"),
  "비캠핑 운영정보의 공통 홈페이지·전화 버튼 또는 CSV 전화 우선순위가 없습니다.",
);
expect(main.includes("_buildingDetailRequestToken") && main.includes("_isActiveBuilding(id, requestToken)"), "비동기 상세 응답의 요청 세대 차단이 없습니다.");
expect(main.includes("_buildingTrendRequestSeq") && main.includes("_buildingTxRequestSeq"), "동일 건물의 실거래 재조회 순서 차단이 없습니다.");
expect(main.includes("b.camping?.reservation_url") && main.includes("b.camping_resve_url") && main.includes("safeBookingUrl(b.booking_url)"), "예약 후보의 HTTP(S) 검증 또는 구형 캠핑 URL 호환이 누락됐습니다.");
expect(!main.includes('const action = op.booking_url'), "시설 운영 파트너 카드에 중복 예약 링크가 남아 있습니다.");
expect(!main.includes("onclick=\"window.open('${escapeHtml(safeBuildingBookingUrl)}"), "예약 URL이 인라인 JavaScript 문자열에 삽입됩니다.");
expect(main.includes("return { url, platform }") && !main.includes("return { url: safeUrl(url), platform }"), "공유 범위 밖 URL 함수 호출이 남아 있습니다.");
expect(manage.includes("예약 사이트 URL") && manage.includes("에어비앤비 리스팅 URL"), "운영자 URL 도움말 라벨이 없습니다.");
expect(main.includes("bNonCampingOperationsCard") && main.includes("_renderNonCampingOperations"), "비캠핑 공통 운영정보 카드가 없습니다.");
expect(main.includes("lr_western_rooms") && main.includes("lr_toilet_count") && main.includes("lr_surroundings"), "신고 데이터 특수 필드가 운영정보에 연결되지 않았습니다.");
expect(main.includes("FacilityIcons.html(item") && main.includes("_bookingTarget(b)"), "편의시설 아이콘 또는 예약 권위 함수가 연결되지 않았습니다.");
expect(manage.includes("badges:selectedBadges") && !manage.includes("approved_badges") && !manage.includes("evidence_url") && !manage.includes("관리자 검증 필요"), "운영자 인증 선택 저장 정책이 올바르지 않습니다.");
expect(main.includes("일부 운영정보와 인증 표시는 시설 운영자가 직접 등록한 내용이며, 실제 정보와 다를 수 있습니다."), "운영자 정보 고지 문구가 없습니다.");
expect(main.includes('id="bOperatorInfoDisclaimer"') && main.includes('Boolean(op.operator_supplied_info)'), "운영자 입력이 있을 때만 맨 아래 고지가 표시되지 않습니다.");

console.log("OK  건물 유형별 상세 패널 회귀 점검");