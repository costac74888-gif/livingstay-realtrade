---
name: 행안부 숙박업 조회서비스
description: 일반숙박·농어촌민박·한옥 API의 페이지 크기 무시 동작과 완료 판정 함정
---
- 엔드포인트: `lodgings/info`, `rural_homestays/info`, `hanok_experience/info` (LODGING_SERVICE_KEY 사용).
- **세 API 모두 numOfRows를 무시하고 항상 최대 100행/페이지 반환** (1000 요청해도 100). 요청값 기준 완료 판정은 약 10%만 훑고 조기 종료한다.
  **How to apply:** 첫 응답의 totalCount와 실제 누적 items 수가 정확히 같을 때만 완료하고, 중간 빈 페이지·총건수 변경·초과 응답은 실패로 처리한다.
- totalCount ~58,530 전체 숙박업 중 위생업태 '숙박업(생활)'만 필터하면 ~8,200건. API에 업태 필터 파라미터 없음 → 전 페이지 스캔 필수(586페이지, ~10페이지/분).
- 활성 신고는 SALS_STTS_NM이 정확히 `영업/정상`인 행만 인정한다.
