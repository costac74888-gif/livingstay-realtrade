---
name: 건물사진 공급자 제약
description: TourAPI·Street View·Vworld 건물사진 수집에서 확인된 외부 서비스 및 키 보안 제약
---

건물사진 수집은 한국관광공사 TourAPI 4.0 `KorService2`를 기준으로 한다. 기존 `KorService1`은 폐기 응답을 반환하며, 공용 공공데이터 키가 존재해도 국문 관광정보 서비스 활용 승인이 별도로 없으면 403이 발생한다.

**Why:** 실제 Replit 호출에서 기존 서비스는 폐기 오류, 현행 서비스는 현재 키 권한 403을 반환했다. Vworld WMS도 도메인 파라미터를 포함한 Replit 서버 요청에 502를 반환했다. Street View Static API는 파노라마가 없어도 안내문 JPEG를 HTTP 200으로 반환한다.

**How to apply:** 공급자별 첫 요청을 사전검증하고 실패 시 진행 위치를 전진시키지 않는다. Street View는 Static 이미지 응답이 아니라 Metadata의 `status=OK`를 확인한 건만 저장한다. Google/Vworld 키가 들어간 원격 URL을 공개 DB/API에 저장하지 말고 키 없는 내부 URL과 서버 중계를 사용한다. Vworld는 실행 환경 접근 가능 여부를 먼저 확인한다.