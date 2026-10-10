# Phase17 내부 Work 실행 지시

Phase16 COMPLETE·전체53 PASS·개발원격 해시와 main 불변을 확인한 뒤 진행한다.
원문Phase17 통합 Regression/Security/Payment Validation과 native
S17-A01/S17-A02/S18-A01을 실제 자동검사로 연결한다.

모든 기존 acceptance와 회귀를 다시 실행한다. 복합 SQL 원장에서 공개 등록·
달력 견적·예약·관리자 정책·결제 모의 서명/replay·확정·취소·환불/보증금/
지급 검토·관심·참여자 채팅·알림을 연계한다. 권한 변경·외부 ID·CSRF·
민감정보·캐시·비용 불변·제한공개·실제 실행 닫힘을 확인한다.
의존성·SAST·개인정보 스캐너를 실행하고 결과와 scope/false positive/차단을
분리한다. 오류/미검증을 PASS로 꾸미지 않는다.

운영자산 변경·새 main mount·실제 PG/발송·운영 migration/게시를 실행하지 않는다.
owned adapter 검사는 실제 provider/SDK·기존 host 인증 통합 검증의 대체가
아니다. Phase18는 actual cutover evidence와 각각의 사용자 승인 없이는
완료로 기록할 수 없다. 불명확한 legacy 검사도 전체 프로젝트 PASS라고
표시하지 않는다.
