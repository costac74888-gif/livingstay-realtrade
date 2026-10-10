# Work 검토 범위와 재현 절차

결과는 state.json의 사용자 Phase 5 verification/work_review 영수증으로 판정한다.
이 문서는 승인하거나 실행하지 않은 실제 운영 연결을 PASS라고 주장하지 않는다.

- 원문·MASTER_SPEC·original native 계획과 기존 17개 등록검사 보존.
- Phase 4 완료 tag/과거 영수증은 변경하지 않음.
- 선택 기간 총액: 날짜 없이 가격 필터 금지, 숙박 1일/비숙박 7일 경계,
  누락 견적·기간 불일치·불완전/미승인 견적 제외. 실제 유효한 0원과 누락을 구별.
- 실제 owned PostgreSQL에서 원본 공개 view·게시/철회·public DB role·일자 요금
  완전성 검사. 원본 legacy 데이터/회원/가격 snapshot 추가·수정 없음.
- 실제 Chromium 1280/390에서 빈 mock 성공이 아닌 3개 카드와 단일 기간가격
  필터 결과, 선택, URL 복원, 오류와 동일 조건 재시도를 검사.
- Main 최초 진입 자동 검색 누락을 실제 브라우저 검사에서 발견해 수정함.
- Phase 5 재시도 검사는 실패 당시 조건을 재시도한 뒤 새 조건 검색을 따로 검사.
  재시도에서 미적용 입력값을 강제로 사용하게 만드는 구현 변경을 하지 않음.
- Phase 4 신규 UI 검사에서 feedback 표시만 기다리면 처리중 문구를 읽는 경합이
  드러남. 기존 성공/실패·권한 assertion을 유지하고 실제 401 응답 및 입력 대기 상태를
  추가로 기다리도록 보강. immutable 기존 17개 검사나 과거 완료 증거는 변경 안 함.
- 공개 자료에 없는 상세 필터는 비활성으로 고지함. location query 완성은 Phase 8;
  보호된 metadata를 써서 결과 존재 여부를 유출하는 oracle도 만들지 않음.
- Kakao 인터페이스의 owned synthetic SDK 초기화만 검사함. 실제 공급자/domain,
  실사용 요금·full 공개·사진·지도 layer·예약·결제는 검증하지 않음.
- app.py/new DB/provider key/실제 회원·business/운영 schema/main/배포 무변경.

최종 source 지문에 대해 전체 24개 등록검사를 실행하고 실제 로그 SHA를 검토해야
완료할 수 있다. 실패·skip·문서만의 criterion은 완료 기준이 아니다.
