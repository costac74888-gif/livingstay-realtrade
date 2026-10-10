# Phase16 내부 Work 실행 지시

Phase15 COMPLETE·전체51개 PASS·개발 원격 해시 검증 뒤 진행한다.
원문19절: PC와 동일 데이터 규칙, 휴대폰 목록↔지도 전환을 우선 적용한다.
기존 /hs2/search PC/responsive 경로와 역사적 검사를 바꾸지 않고 동일 HTML·
controller·API·SDK·선택/가격/재고 규칙을 공유하는 /hs2/search/mobile/을 추가한다.
화면 상태만 분리하고 지도 노출 때 원래 relayout을 호출한다.

소비자·운영자·예약·금융·workspace·도움말·관리자까지 최소320/390px에서
가로 넘침/좁은 조작/기록 손실을 검증한다. 새 검색 전환은 검색 조건·선택·
레이어를 버리거나 별도 원장을 만들지 않는다. desktop 폭에서는 원래 두
패널을 유지한다. 이전 HTML에 잘못 추측한 검색 링크가 있으면 실제
/hs2/search 경로로 바로잡고 등록된 원래 검사를 수정하지 않는다.
실제 SDK와 배포host는 운영 gate를 유지하고 화면 검사는 owned adapter다.
