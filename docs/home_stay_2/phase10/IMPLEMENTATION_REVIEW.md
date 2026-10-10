# Phase10 — 내부 Work Booking Engine 검토

Native S09/S10과 사용자 Phase10을 실제 owned PostgreSQL 예약 엔진·소비자/
운영자 UI로 연결한다. 개발 구현/내부 검토이며 운영/실결제 승인이 아니다.

- 본인·확인된 소비자·활성 회원·명시적 신청 동의·현재 receipt/가격/등록
  revision·최소 체류·공개/권한·운영자 blocked day를 같은 source 잠금에서 확인한다.
- receipt마다 신청은1개, 소비자 request key와 payload가 같으면 동시 retry도
  같은 예약을 반환한다. 다른 내용으로 같은 key를 쓰거나 다른 사람 receipt를
  가져오는 것은 실패한다. actor/price/paid는 client body로 받지 않는다.
- 건물 source 잠금 뒤 동일 pool/전체→descendant 공유재고를 재검사하고
  반개구간(checkout=다음 checkin 허용) 날짜를 사용한다. 동시 두 소비자 신청은
  한 건만 성공한다. 다른 호실은 독립이고, held 전체에 새 child가 연결되면
  현재 graph로 재확장하여 여전히 충돌한다. 원래 DB cycle guard는 보존한다.
- 거래 요청30분·승인 후 결제 대기2시간·소비자 활성 신청3개가 개발 기본 정책이다.
  deadline은 DB 시각이다. 성공적인 상태 조회/신청/액션에서 만료를 영속 처리하고
  슬롯을 해제하며 availability는 cleanup 이전에도 만료 슬롯을 제외한다.
- 상태는 pending_operator / awaiting_payment / confirmed / rejected / cancelled /
  expired다. 신청·승인은 결제·확정이 아니다. 즉시입주를 자동 예약 승인으로
  해석하지 않는다. 소비자는 본인 미확정 신청만 취소하고 운영자는 해당 사업장
  신청만 승인/거절한다. 이후 유료 확정 취소·환불은 Phase11/14 정책 경계다.
- 원래 immutable FK snapshot을 연결하며 client 재계산 없이 정확한 기간 구성과
  총액을 쓴다. 미확정 source 변경은 재견적, 확정 후 가격표 변경은 기존 가격 유지다.
- 결제확정은 신뢰된 서버 지급 증빙의 예약ID·정확한 KRW 금액·유일 reference와
  지급 정책 확인 callback이 있어야 한다. 동시 reference replay도 잠금/unique
  제약으로 막는다. provider 부재·미검토 정책·underpayment는 실패한다.
- 소비자/운영자 UI의 실제 저장 응답 뒤 상태/기한/가격을 표시하고 새 scope·
  source/revision·stale 응답·인증 해제 시 액션을 폐기한다. 상세의 유효한 quote
  receipt만 실제 신청 화면으로 연결한다. client countdown은 서버 상태조회만
  유발하며 스스로 예약 만료/지급 완료를 확정하지 않는다.

## 검증과 제한

계약 검사·실제 SQL 동시성/재시도/만료/취소·거절/공유재고/원래 cycle guard/
권한·사업장/미확정 가격 변경/fixture 지급 확인·중복확정/가격 불변/reference
replay와 desktop1280/mobile390의 실제 상세→신청→운영자 승인→대기→취소,
거절·재고 복구·로그인 제한·영속 재진입을 확인한다.

전체 등록된 검사 receipt가 최종 근거다. fixture 지급 증빙은 actual PG/settlement가
아니다. 실제 provider/session/storage/SDK/host mount와 운영 권한/DB는 후속 통합·
별도 승인 영역이다. 결제 증빙 adapter를 기본 fixture UI에 연결하지 않는다.
production migration·실제 PG·publish는 실행하지 않았고 기존 smoke/api 실패도
고쳤다고 하지 않는다.
