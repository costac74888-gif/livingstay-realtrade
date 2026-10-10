# Phase12 — 내부 Work 운영자 대시보드 검토

운영자 세션·최신 회원 활성·승인 context를 server port로 확인하고 원장의
동일 REPEATABLE READ snapshot에서 합계와 최근 목록을 구성한다. browser가
user/context/조회필터를 정하지 않는다. 오류는 빈0으로 바꾸지 않는다.

- 등록 합계는 전체 own context 기준, 공개 수는 실제 유효 승인/등록 grant/
  listing 공개 상태를 함께 확인한다. 초안·철회·만료를 공개 건으로 세지 않는다.
- 예약 승인 대기/결제 증빙 대기/미취소 확정/유료 취소를 구분한다.
  기한이 지난 대기를 대시보드에서 살아 있는 대기로 표시하지 않는다.
- signed sandbox 원장과 live provider 원장 합계를 분리한다. actual execution은
  없다. 모의 증빙은 실제 현금/실서비스 매출이나 정산 완료로 표시하지 않는다.
- 활성 숙박·보증금·사업자 지급 검토 기준은 미취소 capture만 계산한다.
  late_capture는 역사적 증빙에는 남지만 정상 숙박 기준에는 들어가지 않는다.
  유료 취소는 refund_review와 역사를 보존하면서 활성 기준에서 빠진다.
  반환/환불/지급 review 합계는 실제 반환/환불/지급 완료가 아니다.
- 합계는 전체 범위이고 최근 목록은20건이다. total/has_more를 표시하여 목록
  길이를 전체 수로 오인하지 않는다. 본인 context에 데이터가 없으면 실제0이다.
- 작업 링크는 새 등록/내 방/달력/예약/금융계약·정산/기존 채팅에 연결한다.
  등록·달력의 application 링크는 실제 선택 건으로 재진입하며 다른 건으로
  조용히 대체하지 않는다. 뒤 단계에서 확장할 Chat을 완료한 것처럼 꾸미지 않는다.
- 원문 기존 자산8개 메뉴 링크를 보존한다. 지도 기반 DataLab/공매/영업신고는
  기존 지도에서 이용하고 자산분석은 기존 /analysis로 연결한다.

SQL은 권한·활성·늦은 지급·유료 취소·범위별 빈 상태·한도 넘는 전체 합계를
검사한다. 브라우저는 desktop/mobile 실제 비어있지 않은 원장 DOM·변경 후
refresh·선택 기록 재진입·malformed/forbidden 상태를 검사한다.
검사는 owned fixture이며 실제 SDK/계정/host mount와 운영 원장을 검증했다는
뜻이 아니다. production migration·실제 PG/settlement·publish는 미승인이다.
