# HOME & STAY 2.0 — 개발 검증과 운영 전환 준비

검증일: 2026-10-11. **PARTIAL / NOT_ACCEPTED / 운영 전환 승인 전**.
이 문서는 실제 토스 연동·Phase18 완료·운영 복구 성공을 증명하지 않는다.
소스 저장 후 pytest 통과 및 GitHub 백업 확인은 `FINAL_VERIFICATION_APPENDIX.md` 참조.

## 안전 경계

- 운영 DB 쓰기, main 병합, 운영 게시, 실제 결제·환불·지급, 실제 이메일·SMS 발송 없음.
- 검사 DB는 가상 자료를 넣은 소유 임시 UNIX PostgreSQL이며 외부 연결·알림을 차단했다.
- 기존 동결 13개 파일·616개 라우트·필수 기능 10개 보존 검사 PASS.
- 키 검사는 존재·테스트 형식·문서 예제 여부만 boolean으로 출력했다.
  실제 값·길이·지문·인증 헤더를 보고서와 로그에 넣지 않았다.
- 본인인증·소셜 로그인·지도·금융의 fixture/mock 검사를 실제 공급자 검사로 표시하지 않는다.

## 검사 결과와 한계

첫 전체 실행은 152명령, 138 PASS / 14 FAIL / 0 skipped였다.
실행 중 수정이 있었으므로 한 버전의 최종 전체 PASS 증거가 아니다.
원본 실패 로그는 삭제하거나 허용 목록으로 성공 처리하지 않았다.

증거 디렉터리:
- `.local/suite-audit/final-continuation/`: 전체 명령별 결과, 로그, pytest XML.
- `.local/suite-audit/membership-chart-dependency/`: PC 1280px·모바일 390px의
  소유 DB 실제 비밀번호 로그인, 입금신청·취소·가상 직원 승인·확인 신청·보고서·갱신 PASS.
  **은행 가상 승인이지 토스 승인이 아니다.**
- `.local/suite-audit/auction-initial-auth-boundary/`: 공매 초기 상세 탭,
  목록 복귀, 정렬·필터·페이지 이동 세 브라우저 검사 PASS.
- `.local/suite-audit/mobile-auth-final/`: 초기 인증 경계 단위 검사와
  PC↔모바일 전환·모바일 검색/매물/달력/예약/금융/대시보드/워크스페이스/도움말 PASS.
- `.local/suite-audit/final-targeted-contracts/`: 일반회원 팝업의 화면 유지와
  명시적 마이페이지 이동, 사업자 로그인 경로 PASS. 검토 지문 갱신 후 네 게이트 검사 PASS.
- `.local/suite-audit/final-coherent-impact/`: 공매 전체·멤버십 PC/모바일·
  TourAPI 부분 갤러리·소비자 필터 계약 네 검사 PASS.
  갤러리는 실제 키 대신 가상 meta 설정과 모의 API 응답으로 검증했다.
  공급자 실제 연결 증거가 아니다.

주요 수정:
- 오프라인 검사에서 설치된 실제 Chart.js datalabels UMD를 제공해 관리자 JS 오류를 해결.
  CDN 외부 전송을 허용하거나 오류 assertion을 삭제하지 않았다.
- 첫 인증 상태 확인이 아직 완료되지 않은 공매 딥링크의 기본 탭을 복사하지 않게 함.
  이후 인증 갱신의 접근권한 재조회와 선택 탭 보존은 유지.
- 모바일 검사에서 viewport 호출 완료와 matchMedia 처리 완료를 구분.
  원래 가시성 assertion은 유지했고 검토 SHA만 변경된 검사와 맞췄다.
- 일반회원 팝업 로그인은 현재 화면 유지, 마이페이지는 명시적 이동으로 검사.
- 소비자 검색의 dict 파서 이름을 명확히 하고 기존 query 인터페이스는 호환 별칭으로 보존.
  해당 함수는 SQL을 만들거나 실행하지 않는다.

검사 중 덮어쓴 기존 기준 이미지 10개는 검사 후 원본 바이트로 복원했다.
원본 이미지를 변경 파일로 개발 브랜치에 저장하지 않는다.
캡처의 영구 분리 작업은 이미 존재하는 후속 작업과 중복 진행하지 않았다.

남은 실패/미확인:
- 관리자 정기 동기화 UI: 기존 검사에서 요구하는 통합 카드·수동 접기 영역 부재.
  기존 제안 작업과 중복 개발하지 않았다.
- 기존 지도위치 검사: 관심단지 선택 후 모바일 검색 패널/상세 버튼의 실제 클릭 상태 불일치.
  패널 준비 조건을 보강했지만 성공하지 않았다. 강제 클릭으로 우회하지 않았다.
- 기존 현황조사 검사: 익명 진입의 survey-check-state 가시성 대기 실패.
  유료 정보 정책과 fixture 조건을 더 확인해야 하며 임의 권한 우회로 통과시키지 않았다.
- 변경된 Preview 실행 명령은 저장 전 diff-HEAD 범위 검사와 충돌했다.
  원래 assertion은 그대로이며, 아래 개발 설정 변경을 별도로 검토했다.
- 실제 소셜/본인인증 및 로그인한 운영 화면, 실제 토스 공급자 왕복은 미검증.

## 개발 Preview

Start application만 `python -u scripts/hs2_dev_preview.py`로 교체했다.
운영 배포 실행 명령 `bash scripts/start-prod.sh`와 운영 수집 워크플로는 변경하지 않았다.

- `/hs2/consumer`: 소비자 검색/매물 화면, PC 1280px·모바일 390px 캡처 확인.
- `/hs2/search/`: 통합 검색, `/hs2/bookings/`: 예약,
  `/hs2/dashboard/`: 대시보드, `/hs2/workspace/`: 사업자 작업공간.
- `/__development__/status`: 가상 DB·OwnedSandbox·외부 발송 차단을 명시.
- 부모 환경 전체를 복사하지 않고 허용된 실행 환경만 전달한다.
  실제 DSN·토스·알림 키를 자식 프로세스에 넣지 않는다.
- 화면에 가상 자료·모의 결제·fixture 신원임을 표시한다.
  실제 개인정보를 입력하지 말아야 하며 재시작하면 자료가 초기화된다.
- 이것은 여러 모듈을 함께 볼 수 있는 fixture Preview다.
  운영 로그인부터 모든 모듈까지 단일 실제 신원으로 연결된 통합 서비스가 아니다.
  fixture 전용 신원/관리자 도구를 운영 인증으로 사용하거나 게시하면 안 된다.

## 실제 토스 — 전 항목 NOT_RUN

저장된 두 키는 테스트 형식이나 문서 예제용으로 판정됐다.
상점별 연동·본인 상점의 결제 내역·키 쌍 유효성을 검증하지 않았다.
값이나 일부 문자열을 기록하지 않는다.

| 요구 항목 | 실제 공급자 결과 |
|---|---|
| 결제 승인·실패·사용자 취소 | NOT_RUN |
| 승인 후 전체/부분 환불 | NOT_RUN |
| 중복 승인/콜백·멱등성 | NOT_RUN |
| 예약 상태·재고 복구·경합 | 실제 토스 연계 NOT_RUN |
| 서명/원본 webhook·지연/재전송 | NOT_RUN |
| 지급·정산 | 미실행, 실제 지급은 승인 범위 밖 |

현재 에이전트의 결제 연동 절차는 토스 구현을 허용하지 않는다.
이는 Replit 네트워크나 토스 직접 API의 기술적 불가능 판정이 아니다.
다른 결제 공급자로 임의 교체하지 않았다.
본인 상점 테스트키 확보만으로 구현·검증 완료가 되는 것도 아니다.

## 개인정보·보안

- 의존성 감사: critical/high/moderate/low 발견 0.
- 개인정보 데이터흐름 검사: 발견사항 0. 모든 개인정보 처리가 안전하다는 보증은 아님.
- 정적 검사: 처음 CRITICAL 1/MEDIUM 2.
  SQL을 실행하지 않는 검색 파서의 이름을 명확히 한 뒤 CRITICAL 0/MEDIUM 2.
- 남은 두 MEDIUM은 static/js/auctions.js의 목록·지역 HTML 렌더링 경고.
  동적 값에 escaping이 있지만 자동 경고를 숨기거나 전체 보안 PASS로 선언하지 않는다.
  운영 승인 전 문맥별 인코딩/URL/DOM 검토와 담당자 확인이 필요하다.

## 운영 적용 시 변경과 데이터 필요 여부

### 이번 회귀 수정만 적용할 경우

- 기능: `static/js/main.js`, `hs2_consumer/api.py`, `hs2_consumer/search.py`.
- 검사 의존성: `package.json`, `package-lock.json`, `tests/offline_support/browser_guard.cjs`.
- 보강 검사·검토 지문: 변경된 tests 파일들과 `docs/home_stay_2/checks.json`.
- 개발 전용: `.replit`의 Start application, `scripts/hs2_dev_preview.py`,
  `scripts/check_toss_test_keys.py`. **운영 Preview 진입점으로 쓰지 않는다.**
- 이번 변경에는 운영 DDL·원장 데이터 변경·실제 금융 처리 필요 없음.
  본인 테스트키 설정은 코드/DB 마이그레이션이 아니다.
- npm 추가 패키지는 검사 중 실제 차트 플러그인을 제공하기 위한 것이다.
  운영 UI의 CDN 전략을 전환했다는 뜻은 아니다.

### HOME & STAY 2.0을 운영에 활성화할 경우

현재 fixture-only 등록을 운영 Flask 진입점에 그대로 복사하면 안 된다.
실제 계정·역할·사업장·공개 카탈로그·관리자·CSRF·금융 정책 resolver,
공급자와 callback 도메인, 권한/개인정보 검증을 먼저 연결해야 한다.

새 원장 적용 대상은 다음 SQL의 정확한 diff를 승인된 DB 지문과 대조해 확정한다:
`hs2_data/migrations/001_up.sql`, `hs2_listings/migrations/001.sql`,
`hs2_calendar/migrations/001.sql`, `hs2_booking/migrations/001.sql`,
`hs2_finance/migrations/001.sql`, `hs2_workspace/migrations/001.sql`,
`hs2_admin/migrations/001.sql`.
모든 파일을 자동 일괄 실행하라는 지시가 아니며 실제로 실행하지 않았다.
추가 역할/정책 migrations와 기존 원장 연결도 승인 SQL 명세에 포함해야 한다.
가상 예약·가상 결제·fixture 사업장은 운영에 복사하지 않는다.

## 백업·복원 및 수동 승인 순서 — 계획만, 운영 실행 없음

1. 배포 후보 commit·빌드 산출물·SQL diff·대상 DB 지문을 고정하고 담당자가 승인.
2. 승인된 변경 창에서 운영 DB 전체 백업과 변경 대상 before-image를
   접근 제한 저장소에 보관. 파일·객체 저장소 목록/버전도 별도 보존.
   백업에는 개인정보가 있을 수 있어 Git/Library/공개 Preview에 올리지 않는다.
3. 운영과 분리된 복원 DB에 백업을 복원하고 행 수·FK·권한·원장 합계·예약 재고를 검증.
   현재 가상 DB 검사로 운영 백업 복원 성공을 대체하지 않는다.
4. 기존 발송/수집/금융 작업을 포함한 실행 계획, 변경 중 읽기/쓰기 정책,
   중단 기준과 담당자를 확정. 실제 지급 작업은 별도 승인 대상.
5. 개발→운영 원장 일괄 복사를 하지 않고 승인 SQL과 필요한 최소 데이터만 적용.
   기존 숙박/공매/신고/회원/결제 원장을 보존. fixture 경로가 없는지 확인.
6. 승인 후에만 운영 게시. 공개·회원·각 사업자·관리자의 PC/모바일 점검,
   실제 테스트 merchant 결과, 예약/환불/재고/중복 이벤트를 대조.
7. 문제가 나면 신규 쓰기/외부 처리를 먼저 제한하고 이전 승인 코드·빌드로 복귀.
   데이터는 after-image/동시 쓰기/원장 계보를 비교해 승인된 절차로 복구.
   Git 복귀만으로 DB나 외부 환불·지급을 되돌릴 수 없다.
8. 신규 결제/예약이 기록된 뒤 전체 DB를 과거 백업으로 덮어쓰지 않는다.
   실제 PG 원장과 대사한 보상 처리 및 변경 대상별 복원 승인 필요.

운영 백업 생성·실제 복원 리허설·배포·실제 토스 승인·Phase18 완료는 수행하지 않았다.
Gate A/B/C 및 금융/게시 승인은 NOT_APPROVED 상태다.
