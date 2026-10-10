# Phase 6 — 내부 Work 구현검토

이 문서는 외부 독립감사나 운영 승인서가 아니다. 소스와 actual acceptance의 대응을
내부 Work 역할로 검토한다. 최종 PASS/로그·소스 지문은 state의 전체 레지스트리 영수증을 따른다.

## 구현 경계

- 실제 격리 PostgreSQL에 초안·수정·제출·반려·승인·철회와 비공개 사진을 저장한다.
- 기존 계정/선택 사업장/관리자/CSRF는 trusted callback으로 요구하며 익명 기본 승인이 없다.
  회원·사업장 계정을 복제하지 않고 actor/context별 재검증으로 읽기·쓰기·공개를 제한한다.
- 기존 주소확인 service의 actor-owned workflow 및 원래 PostgreSQL reference store를
  연결한다. 다른 회원 workflow와 미확인/만료 workflow는 신규 등록에 쓸 수 없다.
  저장된 초안의 수정은 영속 후보 연결을 사용해 검색 session 만료로 잠기지 않는다.
- 관리자가 등록권한·공개정보를 확인한다. 건축물 용도에 따른 법적 사용 가능성 판정
  Gate는 추가하지 않는다. warehouse reference도 등록·승인 검사에 포함한다.
- 승인 revision·365일 유효기간·현재 계정/사업장/권한이 맞을 때만 기존 제한공개
  view의 안전한 세 필드를 제공한다. 운영자 선언을 정부 허가로 표시하지 않는다.
- 승인 후 수정은 원자적으로 기존 공개를 해제하고 새 revision 검토를 요구한다.
  철회는 최종 상태이며 매물·사진·이력 원본을 삭제하지 않는다.
- actual browser는 desktop/mobile에서 업로드·새로고침 이후 재진입·제출·관리자 승인·
  공개·수정 후 공개 해제·철회를 수행한다. 독립 admin은 operator 역할 없이 own 화면/
  자산을 읽을 수 있지만 일반 등록자 API를 우회하지 못한다.

## 검증에서 발견하여 고친 사항

저장한 초안은 새로고침 때 최초 workflow dropdown이 비어도 제출할 수 있어야 한다.
독립 admin 자산에 operator context를 요구하지 않는다. CSP를 완화하지 않고 inline
style을 CSS로 옮겼다. 새 viewport 검사는 이전 DB 상태를 존중하고 새 등록을 명시한다.
브라우저 검사는 credential-free Chromium 자체의 same-origin 요청으로 SQL-backed
HTTP를 검사하며 Node API request guard를 해제하지 않는다.

## 완료와 혼동하지 않는 경계

1280px 실제 private fixture screenshot과 390px browser 검사에 한정한다.
실제 사용자/관리자 로그인 렌더링·실제 공공 API·카카오 SDK·사진 App Storage 연결,
운영 migration·외부 발송·예약·실제 결제는 수행하지 않았다. app.py/live mount도 없다.
기존 smoke/api workflow 실패는 새 레지스트리 PASS로 해결됐다고 주장하지 않는다.
가격/calendar 등 후속 Phase와 운영 승인은 별개다.
