# 승인된 후속 순차 작업 — 진행 기록

Phase18 완료·운영 승인 기록이 아니다. 운영 DB·실제 발송·실제 금융 처리·
main 병합·운영 게시는 승인 범위 밖이며 기존 Gate를 유지한다.

## 1. 공매 참고행과 숙박 통계 분리 재검증

- 기존 숙박 필수 컬럼 검사는 유지했다. 공매는 별도 참고행 계약과 완전한
  중립 호환 컬럼만 허용하고 임의 숙박 수치를 거부한다.
- 실제 관리자 인증/API 통합 검사를 강화했다. 소유 임시 DB에 건물 연결
  공매 1건과 미연결 공매 1건을 추가한 뒤 물건수 +2, 연결 건물수 +1을
  확인했다. 모든 숙박 유형행과 전체행은 공매 참고 건수를 제외한 나머지
  컬럼이 추가 전후 완전히 동일해야 한다.
- 실행: `python tests/run_offline_suite.py --only "Python pytest" --only api_test.py --only smoke_test.py --results .local/suite-audit/approved-reference`
- 결과: 세 체크 PASS. Python 1,064 tests·239 subtests PASS. 숙박 assertion을
  삭제·약화하지 않았으며 외부 서비스·운영 DB를 사용하지 않았다.
- 증거: `.local/suite-audit/approved-reference/summary.json`과 개별 로그.

## 2. 운영분석 모바일 버튼

수정 전 기존 브라우저 검사도 이번 실행에서는 PASS였다.
과거 터치 해제 오류를 항상 재현되는 제품 결함이라고 단정하지 않는다.
추가한 결정적 검사에서는 수정 전 터치 호환 클릭이 1→2로 중복 증가했고,
버튼 밖 해제·취소 이후 타이머가 2→4로 증가했다.

- 포인터 활성화와 키보드 활성화를 분리해 터치 호환 클릭의 추가 증가를
  차단했다. detail=0만으로 키보드 클릭이라고 판단하지 않는다.
- 버튼 자체뿐 아니라 전역 pointerup/cancel, touchend/cancel, blur,
  문서 숨김에서 활성 반복을 종료한다. 전역 listener는 한 번만 등록하고
  종료된 버튼의 반복 callback은 활성 목록에서 제거한다.
- 새 7개 경계 검사 PASS. 기존 운영분석 브라우저 검사에 실제 CDP
  touchCancel 뒤 400ms 값 유지 검증을 추가했다. 기존 touchEnd·PC
  반복·키보드·직접입력·슬라이더 assertion은 유지했다.
- 실행: `python tests/run_offline_suite.py --only operation_redesign_browser_test.js --only slider_utils_test.js --only analysis_slider_step_controls_test.js --only slider_release_boundary_test.js --results .local/suite-audit/approved-mobile-fixed`
- 결과: 네 체크 PASS. 수정 전 실패 로그와 수정 후 로그를 모두 보존했다.
- 캡처를 `.local` 검사 산출물로 분리했다. 저장소의 원래 PNG 기준선을
  덮어쓰지 않는다. 화면의 계정·자료·SDK는 가상 fixture이며 실제
  소셜 로그인·공급자 연동 검증으로 해석하지 않는다.

## 3. 전체 회귀·통합 Preview·Toss

이 후속 작업의 전체 회귀와 통합 Preview 및 실제 Toss 테스트는 아직
완료하지 않았다. 개별 fixture PASS를 전체 이용 흐름이나 실제 공급자
성공으로 대체하지 않는다.
