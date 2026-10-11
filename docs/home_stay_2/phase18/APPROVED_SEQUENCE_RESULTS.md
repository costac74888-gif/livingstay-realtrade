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

### 추가 진단·부분 수정 (아직 통합 완료 아님)

- 전체 검사 실행은 작업공간 재시작으로 중단됐다. 최종 집계가 없고 실행
  중 추가 수정도 있었으므로 전체 소스가 일관되게 PASS했다는 증거가 아니다.
- 일반회원 팝업 로그인 후 `/mypage` 강제 이동을 막아 진행 중인 화면을
  유지했다. 사업자 전용 이동은 보존했다. 멤버십 검사에서 로그인 이후
  입금신청·가상 승인 단계까지 진행되지만 `#memberCheckForm` 대기가 실패했다.
- 로그인 실패 진단, 이동 수정, 브라우저 동일-origin fetch 분리의 세 접근을
  적용했다. 현재 멤버십 검사 전체는 FAIL이며 성공으로 표시하지 않는다.
- 공매 헤더 링크를 기존 `/auctions`로 복원했다. 목록·상세·지도·그룹선택은
  진행되지만 미연결 물건의 URL 정확 일치 계약이 FAIL이다.
- 최근검색과 데이터랩의 추출 실행에 필요한 지역 상수를 함수 안에서
  정의했다. 관광 세부행은 일반 세부행 분기에 통합하되 출력 내용은 유지했다.
  `node tests/home_navigation_test.js`, `node tests/home_side_widgets_test.js`
  모두 PASS. 기존 assertion은 유지했다.
- 남은 실패, 모든 회원/역할 이용 흐름을 연결한 Preview, 실제 Toss
  테스트는 미완료다. Phase18 및 운영 Gate 상태를 바꾸지 않았다.
