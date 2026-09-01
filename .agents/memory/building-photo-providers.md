---
name: 건물사진 공급자 제약
description: TourAPI·Street View·Vworld 건물사진 수집에서 확인된 외부 서비스 및 키 보안 제약
---

건물사진 수집은 한국관광공사 TourAPI 4.0 `KorService2`를 기준으로 한다. 기존 `KorService1`은 폐기 응답을 반환하며, 공용 공공데이터 키가 존재해도 국문 관광정보 서비스 활용 승인이 별도로 없으면 403이 발생한다.

**Why:** 실제 Replit 호출에서 기존 서비스는 폐기 오류, 현행 서비스는 현재 키 권한 403을 반환했다. Vworld WMS도 도메인 파라미터를 포함한 Replit 서버 요청에 502를 반환했다. Street View Static API는 파노라마가 없어도 안내문 JPEG를 HTTP 200으로 반환한다.

**How to apply:** 공급자별 첫 요청을 사전검증하고 실패 시 진행 위치를 전진시키지 않는다. 공공데이터포털의 `%2B`·`%3D` 인코딩 인증키는 요청 전에 한 번 디코딩하고, TourAPI 숙박 대표사진은 `detailImage2`가 아니라 검색 결과의 `firstimage`를 우선 저장한다. Street View는 Static 이미지 응답이 아니라 Metadata의 `status=OK`를 확인한 건만 저장한다. Google/Vworld 키가 들어간 원격 URL을 공개 DB/API에 저장하지 말고 키 없는 내부 URL과 서버 중계를 사용한다. Vworld는 실행 환경 접근 가능 여부를 먼저 확인한다.

Google Maps Platform의 2026년 Essentials 무료 사용량은 SKU별 월 10,000 요청이다. Street View Static 이미지와 Static Street View Metadata는 별도 SKU다. 현재 수집기는 Metadata를 먼저 호출하고 내부 프록시 URL만 저장하며, 실제 Static 이미지 호출은 화면 표시 때 발생할 수 있으므로 저장 행 수와 과금 요청 수는 같지 않다.

**Why:** 일일 500건은 관리자 실행 1회의 처리 제한이며 Google 무료 월 한도가 아니다. 일일 캡을 월 한도처럼 올리면 다른 화면 조회·재시도까지 합쳐져 예상 밖 과금이 생길 수 있다.

**How to apply:** 무료 범위만 목표로 하면 월별 예산과 여유분을 두고 내부 일일 처리량은 약 300건부터 운영한다. Google Cloud Console에도 프로젝트별 quota를 설정한다.

건물 사진의 기본 운영 방식은 전체 사전수집이 아니라 상세 진입 시 TourAPI 온디맨드 조회다. 성공 사진과 매칭 없음·공급자 실패를 모두 캐시한다. TourAPI 매칭 없음에만 Street View를 fallback하며 Vworld는 공개 중계하지 않는다. 과거 대량 수집 진입점은 직접 실행도 실패 폐쇄한다.

**Why:** 8만여 건을 순회하면 무료 범위를 넘기고, 기존 사진 행만으로 공개 프록시를 허용하면 ID 열거로 외부 공급자 비용을 소진할 수 있다.

**How to apply:** 별도 사진 API가 TourAPI를 조회한다. 최근 30일 no_match 상태만 Street View 내부 프록시를 허용하고, 실제 이미지 프록시 호출마다 KST 월 10,000회 원자 카운터를 차감한다.