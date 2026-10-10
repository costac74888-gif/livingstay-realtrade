# Phase16 내부 Work 검토

원본 HTML·search/controller·네 API·SDK 어댑터를 그대로 공유하는 모바일
presentation 경로 /hs2/search/mobile/을 추가했다. 기존 /hs2/search/ 화면과
역사적 검사 파일을 대체하지 않았다. 소비자에 모바일 입구를 추가했고,
도움말의 잘못 추측한 /hs2/supermap 링크는 실제 /hs2/search/로 수정했다.

760px 이하에서48px 목록/지도 버튼·aria-controls/pressed·단일 패널을 제공한다.
지도 표시 뒤 원래 resize/relayout을 호출한다. 761px 이상은 원래 두 패널이며
다시 휴대폰 크기가 돼도 선택한 보기 상태를 보존한다. 새 가격/공개/재고
엔진이나 별도 데이터는 없다.

실제 SQL-backed owned Chromium에서320/390px 목록 기본→지도→PC 양쪽→지도
재진입→목록과 API 행 동일성·원래 지도 마커를 확인했다.
소비자·등록·달력·예약·금융·운영자대시보드·workspace·도움말·관리자의 실제
본문과 가로 넘침·JS exception을 확인했다. 이전 역할별 검사는 전체 registry에서
같이 실행한다. 실제 운영 SDK/도메인·host mount를 검증한 것은 아니며
운영 승인 경계는 유지한다.

첫 전체53그룹 검사에서15 관리자 완료 feedback과 실제 overview 갱신의
경합을 발견했다. 쓰기·결정 동안 입력을 잠그고 새 원장 조회 뒤에만 ready를
표시하도록 보수했다. 실제 overview 요청을700ms 지연시킨 브라우저 검사로
후속 편집 잠금·완료 후 실제 기록을 확인한다. 단순 상태문구를 완료로
읽던 기존15 검사도 input 잠금 해제까지 기다리도록 강화했다.
