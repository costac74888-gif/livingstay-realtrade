const fs = require("fs");
const path = require("path");

const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "static", "css", "main.css"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(main.includes("function _campingPhotoList(camp)"), "캠핑 사진 정규화 함수가 없습니다.");
expect(main.includes("camp.layout_images") && main.includes("camp.safety_images"), "레이아웃·안전 사진 계약이 없습니다.");
expect(main.includes("_publicHttpUrl(camp.info_url) || _publicHttpUrl(camp.source_url)"), "공식 링크 fallback 계약이 잘못되었습니다.");
expect(main.includes("function openBuildingPhotoGallery") && main.includes('aria-modal", "true"'), "접근 가능한 전체 사진 모달이 없습니다.");
expect(main.includes("function _campingDetailEntries") && main.includes("camp.detail_fields"), "동적 상세 필드 렌더링 계약이 없습니다.");
expect(css.includes(".b-photo-gallery") && css.includes(".camp-gallery-strip"), "캠핑 갤러리 CSS가 없습니다.");

console.log("OK camping detail contract");