# Phase 8 — 내부 Work 구현 검토

검색·지도 source/API/UI는 새 경로의 독립 모듈이다. 기존 본체 route·통계·기존
공매 3탭과 marker 로직·권한 정책을 바꾸지 않는다. Native S11~14의 사용자
기능을 actual acceptance 네 그룹으로 검사한다. 이는 외부 감사나 live 연결 승인이 아니다.

- 기간 총액·방 수(0 스튜디오 포함 정확 개수)·유형·최소 면적·수용인원·옵션/
  즉시입주/할인을 실제 승인 원장의 운영자 공개 동의 요약으로 검사한다. 보호된
  필드는 검색 결과의 유무로도 추론할 수 없게 한다. 1박/주/월 단가 비교·0원
  fallback은 없다. 기간 총액 한도는 엔진의 단위 한도×최대 일수와 구분한다.
- 원래 동 평균 >=5·시군구 평균 >=10 SQL을 실제 owned PostgreSQL temp table에서
  실행하고 실제 원래 redactor도 검사한다. 임의 정확 좌표를 approximate로
  재명명하지 않는다. 안전한 공개 집계가 없으면 목록은 남기고 위치·marker만 숨긴다.
- 기존 /api/listings의 공개/제한공개·매매/거래대상과 /api/auctions/map의
  공개 조회 계약을 GET adapter로 재사용한다. 제한공개 native 검색에는 기존
  building_name SQL 필터를 전달하지 않고, redactor가 제공한 지역명만 비교한다.
- stay 기본 ON·sale/business/auction 독립 토글, 각 레이어 별도 count/미완전
  표시를 제공한다. 공매는 square, stay는 실제 기간총액 bubble이다.
- 동일좌표의 레이어별 고정 pixel slot과 유형 내 개수/개별 선택은 실제 좌표를
  바꾸지 않는다. 접힌 선택 메뉴로 작은 화면의 마커 클릭 영역을 보존한다.
- Abort + generation + layer/ID pair로 늦은 검색/bounds/상세 응답을 폐기한다.
  같은 42번 ID라도 sale과 auction을 구분한다. OFF/검색/뒤로가기는 이전 상세를
  지우며 모든 레이어 OFF 상태도 URL 재진입에서 그대로 복원한다.
- SDK URL/config와 공개 DTO는 허용된 값만 반환한다. 오류·SDK 부재·원장 부재를
  성공·빈 총계·허위 위치로 대체하지 않는다. source 예산 port는 명시적으로 요구한다.

## 검증 범위

실제 owned PostgreSQL 원장과 Chromium 1280/390, 동일좌표 SDK interface double,
실제 SQL/HTTP/DOM/마커 hit-test·개별선택·빠른 상세 충돌·전체 OFF·재진입·오류/
retry를 검사한다. 별도 canonical whole-registry receipt가 최종 근거다.

원래 앱 공개 API의 adapter 입력/출력을 검사했지만 live API·real Kakao SDK·실회원
세션·production DB/실제 PG/배포는 연결하거나 검사하지 않았다. 새 UI의 앱 본체
mount/운영 geometry 및 위치검색 callback·실제 native GET reader/rate budget은
후속 host composition/통합 단계에 연결한다. 가격 견적은 예약·hold·결제가 아니다.
기존 smoke/api workflow의 실패를 이 검사의 PASS로 해결했다고 주장하지 않는다.
