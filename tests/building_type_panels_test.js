const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const manage = fs.readFileSync("static/lodging_operator_manage.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(main.includes('const STRUCTURE_A_TYPES = ["생활", "관광", "일반"]'), "Structure A 유형 목록이 없습니다.");
expect(main.includes('const STRUCTURE_B_TYPES = ["에어비앤비", "캠핑", "농어촌민박", "한옥"]'), "Structure B 유형 목록이 없습니다.");
expect(main.includes('firstValid("booking_url")') && main.includes('firstValid("airbnb_url")') && main.includes('firstValid("gocamping_url")') && main.includes("b.booking_url"), "예약 URL 우선순위가 없습니다.");
expect(main.includes('data-panel="operations"') && main.includes('data-panel="property"'), "운영정보/부동산정보 탭이 없습니다.");
expect(main.includes("window.__openBuildingId === Number(id)") && main.includes("_buildingDetailRequestToken === requestToken"), "건물 전환 시 오래된 응답 차단이 없습니다.");
expect(main.includes('href="https://jnjclub.co.kr/"') && main.includes('/static/banner_biz_report.png'), "행정운영 영업신고업소 아래 숙박업등록 배너가 없습니다.");
expect(main.includes("STRUCTURE_B_TYPES.includes(b.lodging_type)") && main.includes("_reservationBar(b)"), "Structure B 운영 예약 영역이 없습니다.");
expect(main.includes('_reservationBar(b, !["생활", "일반"].includes(b.lodging_type))'), "생활·일반숙박의 미연결 예약 안내가 숨겨지지 않았습니다.");
expect(main.includes('"bAreaFilterCard", "bTrendCard", "bTimelineCard", "bTxCard"'), "Structure B 부동산 패널에 실거래 카드가 묶이지 않았습니다.");
expect(main.includes('property: [\n      "bRequestCard", "bSignalCard", "bAdminCard"'), "매물내놓기·매수의뢰와 숙박알리미·행정운영이 부동산정보 패널에 묶이지 않았습니다.");
expect(main.includes('class="bld-photo-actions bld-photo-actions-left"') && main.includes('class="bld-photo-actions bld-photo-actions-right"'), "사진 위 뒤로가기·관심·공유 버튼이 없습니다.");
expect(main.includes('class="bld-photo-empty-logo"') && main.includes('/static/home_stay_footer_logo.png'), "사진 없음 상단 바의 가로 로고가 없습니다.");
expect(main.includes('id="bMapBtn" class="b-map-return-btn"'), "우편번호 줄의 지도위치 버튼이 없습니다.");
expect(main.includes('href="/lodging-operator/manage"'), "예약 미연결 운영자 연결 링크가 없습니다.");
expect(main.includes('aria-controls="bOperationsPanel"') && main.includes('role="tabpanel"'), "탭과 패널의 접근성 연결이 없습니다.");
expect(main.includes("_buildingDetailRequestToken") && main.includes("_isActiveBuilding(id, requestToken)"), "비동기 상세 응답의 요청 세대 차단이 없습니다.");
expect(main.includes("_buildingTrendRequestSeq") && main.includes("_buildingTxRequestSeq"), "동일 건물의 실거래 재조회 순서 차단이 없습니다.");
expect(main.includes("_publicHttpUrl(camp.reservation_url") && main.includes("b.camping?.reservation_url ?? b.camping_resve_url") && main.includes("_publicHttpUrl(b.booking_url)"), "예약 URL의 HTTP(S) 검증 또는 구형 캠핑 URL 호환이 누락됐습니다.");
expect(!main.includes("onclick=\"window.open('${escapeHtml(safeBuildingBookingUrl)}"), "예약 URL이 인라인 JavaScript 문자열에 삽입됩니다.");
expect(main.includes("return { url, platform }") && !main.includes("return { url: safeUrl(url), platform }"), "공유 범위 밖 URL 함수 호출이 남아 있습니다.");
expect(manage.includes("예약 사이트 URL") && manage.includes("에어비앤비 리스팅 URL"), "운영자 URL 도움말 라벨이 없습니다.");

console.log("OK  건물 유형별 상세 패널 회귀 점검");