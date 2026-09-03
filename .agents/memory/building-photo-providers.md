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

건물 사진의 기본 운영 방식은 전체 사전수집이 아니라 상세 진입 시 브라우저 TourAPI 온디맨드 조회다. 서버의 기존 성공 사진은 그대로 사용하며, 사진 URL은 검증 후 저장하고 매칭 없음 상태만 만료형 로컬 캐시와 제한된 서버 상태에 함께 기록한다. TourAPI 매칭 없음에만 Street View를 fallback하며 Vworld는 공개 중계하지 않는다.

**Why:** 8만여 건을 순회하면 무료 범위를 넘긴다. 익명 브라우저가 보낸 임의 URL은 공용 캐시를 오염시킬 수 있지만, no_match가 로컬에만 남으면 서버 Street View 허용 조건이 영원히 열리지 않는다.

**How to apply:** URL은 공급자 호스트 검증 후에만 저장한다. 빈 결과는 짧은 만료 상태로 서버에 기록하되 요청별 rate limit과 Street View 전역 월 예산을 함께 적용한다. 기존 로컬 no_match도 서버 상태와 동기화해 같은 방문에서 fallback이 열리게 한다.

TourAPI 숙박 사전조회는 우리 건물마다 이름 검색하지 않고 `contentTypeId=32` 전국 목록을 페이지 단위로 한 번 읽는다. 사진 파일·URL은 저장하지 않고, 정확한 주소 매칭 뒤 `contentId`와 대표사진 유무만 건물 메타데이터로 보관한다.

**Why:** 운영 건물은 3만 건 이상이지만 TourAPI 숙박 콘텐츠는 약 3천 건이라 건물별 검색은 불필요한 API 호출을 크게 늘린다. 사용자가 목록 기반 메타데이터 사전조회 방식을 승인했다.

**How to apply:** 도로명 우선·지번 보조의 정확한 주소 매칭만 사전 반영한다. 상세 화면은 저장된 `contentId`로 검색 단계를 건너뛰고, 매칭됐지만 대표사진이 없는 건물만 Street View 후보로 삼는다.

Replit 운영 autoscale에서 `apis.data.go.kr:443` 연결 타임아웃이 반복될 수 있으며, 같은 시각 개발 컨테이너에서는 정상 호출될 수 있다.

**Why:** 운영 건물사진 조회가 공급자 오류로 캐시된 동안 개발의 기존 성공 사진은 계속 보여 키 문제처럼 보였지만, 운영 로그에서 실제 ConnectTimeout이 확인됐다.

**How to apply:** 운영 서버 egress 장애를 우회해야 하면 브라우저 직접 호출을 사용하되, 실패는 로컬에 장시간 고정하지 않는다. 기존 성공 사진 캐시와 현재 공급자 연결 상태를 별도로 확인한다.