(function (window) {
  "use strict";
  // 참고 가정값입니다. 추후 관리자 설정(app_meta)으로 교체할 수 있습니다.
  // 공개된 수도권 생활숙박시설 정산 보도(2021)의 26.65%를 반올림해 적용했습니다.
  // 실제 비용은 건물·운영사·계약 구조에 따라 다르므로 사용자가 조정해야 합니다.
  window.operationAnalysisSettings = Object.freeze({
    DEFAULT_OPEX_RATIO: 27,
    DEFAULT_MGMT_FEE_RATIO: 30,
    MONTH_DAYS_FALLBACK: 30.4,
  });
}(window));