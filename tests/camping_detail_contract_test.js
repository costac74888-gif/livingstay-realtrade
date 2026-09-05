const fs = require("fs");
const path = require("path");

const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "static", "css", "main.css"), "utf8");
const facilityIcons = fs.readFileSync(path.join(__dirname, "..", "static", "js", "facility_icons.js"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(main.includes("_publicHttpUrl(camp.info_url) || _publicHttpUrl(camp.source_url)"), "공식 링크 fallback 계약이 잘못되었습니다.");
expect(main.includes("function openBuildingPhotoGallery") && main.includes('aria-modal", "true"'), "접근 가능한 전체 사진 모달이 없습니다.");
expect(main.includes("function _campingDetailEntries") && main.includes("camp.detail_fields"), "동적 상세 필드 렌더링 계약이 없습니다.");
expect(css.includes(".b-photo-gallery") && !main.includes("class=\"camp-gallery-strip\""), "중복 캠핑 사진 스트립이 남아 있습니다.");
expect(facilityIcons.includes("window.FacilityIcons") && facilityIcons.includes("일반 야영"), "공용 시설 아이콘 라이브러리가 없습니다.");
expect(main.includes("FacilityIcons.html(item)") && main.includes(">고캠핑</a>"), "시설 아이콘·고캠핑 라벨 계약이 없습니다.");
expect(main.includes("|| campingReservationUrl;"), "네이버 외 고캠핑 예약 URL이 예약 버튼에 연결되지 않습니다.");
expect(!main.includes("naverReservationUrl"), "예약 URL이 네이버 주소로만 제한되어 있습니다.");

const bookingStart = main.indexOf("function _bookingTarget(b){");
const bookingEnd = main.indexOf("\nfunction _reservationBar(", bookingStart);
const bookingSource = main.slice(bookingStart, bookingEnd);
const publicUrl = value => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_) {
    return null;
  }
};
const bookingTarget = new Function(
  "_publicHttpUrl",
  `${bookingSource}; return _bookingTarget;`
)(publicUrl);
const yeongok = bookingTarget({
  camping: {
    reservation_url: "https://camping.gtdc.or.kr/DZ_reservation/reserCamping_v3.php"
  }
});
expect(
  yeongok?.url === "https://camping.gtdc.or.kr/DZ_reservation/reserCamping_v3.php",
  "연곡해변처럼 네이버가 아닌 고캠핑 예약 URL을 선택하지 못합니다."
);
const guideOnly = bookingTarget({
  camping: {
    info_url: "https://www.gocamping.or.kr/camp/123",
    reservation_url: "https://www.gocamping.or.kr/camp/123"
  }
});
expect(guideOnly === null, "고캠핑 안내 URL을 예약 URL로 오인하면 안 됩니다.");
const fallbackReservation = bookingTarget({
  camping: {
    info_url: "https://www.gocamping.or.kr/camp/123"
  },
  camping_resve_url: "https://reserve.example.test/camp/123"
});
expect(
  fallbackReservation?.url === "https://reserve.example.test/camp/123",
  "camping_resve_url fallback 예약 링크가 유지되지 않습니다."
);
expect(main.includes("operator-banner-cta") && main.includes("운영 파트너 등록"), "운영 파트너 CTA 배너가 없습니다.");
expect(css.includes(".camp-facts div:last-child:nth-child(odd)"), "홀수 시설 정보의 빈 셀 처리 계약이 없습니다.");

console.log("OK camping detail contract");