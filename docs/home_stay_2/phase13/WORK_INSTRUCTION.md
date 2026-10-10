# Phase13 내부 Work 실행 지시

원문 USER Phase13과 native S15-A01/A02를 수행한다. 현재 Phase12는 COMPLETE,
전체45개 PASS, 개발 branch 원격 해시 검증 완료이며 main은 변경하지 않았다.

1. 계정별 관심 저장/중복/해제/재조회. 공개 중단된 항목은 비공개 정보를
   노출하지 않는 이용 불가 상태로 보존한다. 기존 관심·채팅 테이블은 변경하지 않는다.
2. 매물 문의와 내 예약을 통해서만 상대방을 서버에서 선정한다. recipient/user/
   context를 browser에서 정하지 않는다. 참여자만 조회/전송/읽음 변경 가능하다.
   메시지 멱등 키의 내용 변경 재사용은 거절하고 본문은 안전한 text로 표시한다.
3. 알림은 원본 이벤트와 동일 SQL transaction에 적재한다. 계정별 동의·해제,
   읽음, 대기/실패/재시도 상태를 구분한다. 검사는 실제 email/SMS 발송0회다.
   owned sandbox 발송 port만 검증하며 live delivery 자동 활성화하지 않는다.
4. 내 예약은 기존 실제 booking/finance API로 조회하고 paid-cancel/expired를
   구분한다. 기존 메뉴와 데이터·역사를 보존한다.
5. desktop/mobile 실제 DOM/상대방 권한/관심 해제·재진입/채팅·읽음/
   예약알림/동의·실패 재시도 검사→전체 registry→내부 검토→개발 GitHub→Phase14.

실제 PG/settlement·production migration·publish/main 반영은 NOT_APPROVED다.
