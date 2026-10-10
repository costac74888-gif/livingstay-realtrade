# Phase13 내부 Work 구현 검토

기존 관심·매물 채팅/신청 채팅·회원·예약 원장은 수정하지 않는다. 새 관심과
참여자 채팅/알림은 hs2_dev의 별도 원장에 보존하며 consumer 계정과 운영
사업장 context는 기존 trusted port로만 결정한다.

- 공개 중인 실제 매물만 저장/문의할 수 있다. 관심 중복 저장은 멱등이고
  삭제·재조회되며 공개 중단 이후에는 항목 ID와 이용불가 상태만 제공한다.
- 매물 문의/본인 예약에서 서버가 상대방을 선택한다. 다른 소비자/사업장
  context는 대화 조회·발송·읽음에 접근할 수 없다. 본문은 textContent다.
  메시지 요청키 재전송은 동일 결과, 본문 변경 재사용은 충돌이다.
- 읽음은 마지막 실제 수신 message ID에만 적용한다. GET 이후 들어온
  메시지를 읽음으로 처리하지 않으며 과거 cursor 재전송은 읽음 상태를 되돌리지 않는다.
- 메시지/예약 event와 알림은 동일 SQL transaction이다. 알림 적재 실패는
  원본을 포함해 rollback하므로 성공한 저장에 알림만 누락되지 않는다.
- 알림 email/SMS 동의는 명시적 boolean이며 기본 off, 해제 후 pending도
  발송이 억제된다. 실패·재시도 대기·sandbox_sent·suppressed를 구분한다.
  sandbox_sent는 실제 이메일/문자를 발송한 상태가 아니다. live transport는 닫힌다.
- 내 예약은 기존 원장 API를 조회하며 결제 전·기한 만료·유료 취소를 구분한다.
  새 workspace는 desktop/mobile 데이터 DOM과 상세 저장/문의 재진입을 검사한다.

알림 transport는 명시적인 owned sandbox test port만 호출 가능하다. production
발송·SDK 계정·host mount는 검증되지 않았으며 Phase17/18에서 별도로 게이트한다.
실제 money/provider·운영 schema·publish/main 활성화는 NOT_APPROVED다.
