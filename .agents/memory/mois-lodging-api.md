---
name: 행안부 숙박업 조회서비스 (lodgings/info)
description: 페이지 크기 무시 동작·완료 판정 함정, 필터/키 관련 실측 사실
---
- 엔드포인트: apis.data.go.kr/1741000/lodgings/info (STORE_INFO_SERVICE_KEY 사용, localdata 인허가 데이터).
- **numOfRows를 무시하고 항상 100행/페이지 반환** (1000 요청해도 100). 완료 판정을 요청값 기준 `(page-1)*num_rows >= totalCount`로 하면 ~10%만 훑고 조기 종료함.
  **How to apply:** 완료 판정은 반드시 응답의 실제 items 길이(또는 빈 페이지)로 계산.
- totalCount ~58,530 전체 숙박업 중 위생업태 '숙박업(생활)'만 필터하면 ~8,200건. API에 업태 필터 파라미터 없음 → 전 페이지 스캔 필수(586페이지, ~10페이지/분).
- 영업 여부는 SALS_STTS_NM이 '영업/정상' 류 — LIKE '영업%' 매칭이 안전.
