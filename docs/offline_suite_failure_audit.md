# 전체 검사 실패 분류와 오프라인 배포 점검

검사일: 2026-10-05

## 판정 원칙

- 실패·시간초과는 항상 종료 코드가 0이 아닌 실패로 남긴다. 기준선 allowlist, xfail, 무조건 성공 처리, 검사 삭제는 사용하지 않는다.
- 기존 실패라는 사실과 기능이 정상이라는 판정은 다르다. 기존에 실패하던 기능 누락도 배포 차단 대상으로 남긴다.
- 소스 문자열·fixture 오류와 실제 기능 문제를 구별한다. 정책이 불명확한 차이를 현재 코드에 맞춰 자동 승인하지 않는다.
- 검사가 통과해도 실서비스의 공급자 인증·quota·운영 DB·배포 연결까지 검증한 것은 아니다.

## 실행 방법과 안전 범위

```sh
python tests/run_offline_suite.py
python tests/run_offline_suite.py --only api_test.py --only frontend_distribution_test.py
python tests/run_offline_suite.py --timeout 10 --only frontend_distribution_test.py --results .local/suite-audit/deadline-check
```

전체 발견 범위는 Python pytest 1회, 별도 Python 실행형 검사 13개, JS/CJS 검사 73개로 **87개 실행 단위**다. 브라우저를 쓰는 이름의 검사는 14개다. pytest의 개별 검사 수 및 subtest 수는 실행 단위 수와 합산하지 않는다.

실행기는 가짜 서비스키, 외부 알림 차단, 공공 API 중계 OFF, 시작 시 스키마 초기화·자동 수집 OFF를 자식 프로세스에 전달한다. Python requests/urllib 외부 HTTP와 localhost→외부 리다이렉트도 차단한다. 브라우저에서는 정부 API 도메인을 차단한다. requests/urllib 리다이렉트 검사는 실제 transport를 mock으로 대체하여 실제 요청 없이 검증한다.

브라우저 검사의 대상 웹 서버에도 다음 조건이 필요하다. 앱 내부 인증을 우회하지 않는다.

```sh
env HOMENSTAY_OFFLINE_TESTS=1 DISABLE_EXTERNAL_NOTIFICATIONS=1 \
  SKIP_STARTUP_SCHEMA_INIT=1 SKIP_APP_BOOT_TASKS=1 \
  RELAY_ENABLED=0 RELAY_USE_BLDG_HUB=0 RELAY_USE_RTMS=0 \
  BLD_SERVICE_KEY=offline-test-bld \
  BLD_INSPECTION_SERVICE_KEY=offline-test-inspection \
  RTMS_SERVICE_KEY=offline-test-rtms \
  DATA_GO_KR_BROKER_API_KEY=offline-test-broker \
  PYTHONPATH=tests/offline_support:. \
  gunicorn --bind 0.0.0.0:5000 --timeout 120 --workers 2 --preload \
    --config gunicorn.conf.py app:app
```

실행당 별도 TMPDIR·프로세스 그룹을 소유하고, 정상 종료·실패·deadline·실행기 취소 때 정리한다. Python deadline은 먼저 스택을 기록하고 SIGTERM으로 finally 정리를 허용한 후 남은 자식에 SIGKILL을 적용한다. 실행 중인 자식이 남으면 성공적인 정리로 기록하지 않는다. 기존의 소유권 불명 임시 파일은 임의로 삭제하지 않았다.

프런트 배포·스모크 검사는 실제 빌더와 실제 Flask 라우팅을 임시 static workspace에서 사용한다. preview의 현재 릴리스 마커를 교체하지 않는다. 빌드 실패 시 기존 마커 유지, 원본 JS 차단, 전체 HTML 및 압축 JS 생성 검증은 그대로 유지한다.

## 수정 전 증거

| 범위 | 실행/검사 수 | 결과 | 근거 |
|---|---:|---|---|
| 과거 동일 조건 변경 전/후 비교 | 각각 25 pytest 항목 | 각각 7 통과·18 실패, 실패 목록 일치 | `.local/relay-test-results/{baseline,current-comparison}-python.log` |
| 이번 작업의 수정 전 Python 전체 | 886 pytest 항목 | 861 통과·25 실패, subtest 131 통과, 60.40초 | `.local/suite-audit/before/python.log` |
| 과거 전체 실행 단위 | 79 | 60 통과·19 실패, 시간초과 2개 포함 | `.local/relay-test-results/summary.json` |
| 이번 API 수정 전 | 실행형 1개 | 180초 제한 내 종료하지 못함 | `.local/suite-audit/before/api_test.py.log` |

과거 전체 실행과 현재 전체 발견 수가 다른 이유는 검사 파일이 추가되었기 때문이다. 79→87을 같은 고정 검사 목록의 통과율 변화로 해석하지 않는다. 과거 Python 전체 로그도 시점·fixture 환경에 따라 실패/수집 오류 수가 달랐다.

## 원인 분류와 수정 근거

### 1. 기존 기준선

18개 비교 실패는 중계 변경 전후에 동일했다. 이번 수정 전 전체 25개 실패에는 해당 18개와 모의 환경 오염 때문에 추가로 실패한 7개 invalidation 검사가 포함됐다.

이는 중계의 신규 회귀가 아니라는 근거다. 해당 기능을 통과로 간주하는 근거는 아니다.

### 2. 낡은 소스 문자열·추출 범위

- 스키마 검사는 특정 옛 날짜 문자열 대신 버전 형식을 검사하고, 실제 스키마 fast path·불일치 DDL 검사는 유지했다. 제품 스키마·버전은 변경하지 않았다.
- 업로드 입력 검사는 예전 무제한 숫자 대입 대신 hard clamp와 문자열 대입을 검사한다. 금액·점유율 제한 자체를 제거하지 않았다.
- 사진 갤러리 renderer 이름 변경, HTML 헤더 표현, 카드 배열의 개행·추가 카드, 관리 화면 payload 공백 때문에 실패한 소스 검사를 현재의 정확한 계약으로 교정했다.
- 건물명 검사는 유사한 다른 bName 선언이 아니라 property_info를 포함하는 상세 renderer의 선언을 대상으로 잡았다.
- 방문자 추이 VM 검사는 관련 차트·기간 전환만 추출한다. 무관한 회원통계 메뉴 이벤트는 제외하되 최초 일별 렌더 호출이 실제 소스에 있는지 검증한다.
- 공개 데이터랩 메뉴에서 폐업 항목을 요구하던 기준은 공개 비노출 원칙에 맞춰 신고순위 및 폐업 메뉴 부재를 검사한다. 기존 통계 계산 검사는 삭제하지 않았다.
- 법정분류 목록에는 필터용 `전체`가 앞에 추가돼 있었다. 이를 별도로 검사하고 나머지 분류·순서는 기존 기대값과 정확히 비교한다. **에어비앤비 키를 바꾸지 않았다.**
- 공식 원장 안내는 활성 멤버십 분기로 바뀌어 있다. 비회원 안내 분기에 원장번호·전화가 없는지 검사한다. 멤버십 사용자의 정상 표시까지 무조건 비공개로 요구하지 않는다.

### 3. fixture 수명·실행 순서·준비 데이터

- presale 검사 cleanup이 선행 모듈의 가짜 환경키를 삭제했다. 소유한 patch.dict로 들어오기 전 값을 복원하도록 바꿨다.
- schema/Gunicorn/pool fake에 현재 경로가 요구하는 상태·hook·분류 count 필드를 추가했다.
- 단일 연결 건물 pool 검사는 별도 공매 집계의 연결 수명을 mock으로 격리한다. 건물 연결의 정확히 한 번 반환, 예외, 반복 cache miss, 요청용 여유 연결 보존 검증은 유지한다.
- master invalidation 검사는 새 auth ledger의 보조 DB 쓰기와 해당 검사의 가짜 연결을 분리한다.
- 공매 알림 fixture는 오래된 실사용자·과거 dedup marker·실행일에 의존하지 않고, rollback되는 고유 회원과 물건의 최초 발견 시각보다 이른 구독 시각을 쓴다. opt-in, 즐겨찾기, 1회 알림, OFF 검증은 유지한다.
- 액션센터 count 계약에 추가된 현황조사 count를 정확히 포함하고 음수가 아닌 정수인지 검사한다.
- 브로커 준비 주소가 시계의 마지막 세 자리를 건물번호로 사용해 leading zero 및 중복에 취약했다. 고유 도로명/동명과 정상적인 고정 건물번호를 쓰도록 바꾸고, 정확히 두 도로명 매칭·지번-only 제외·엑셀 동일 집계 조건은 유지했다.
- 두 홈 브라우저 검사의 `ERR_ABORTED`는 기본 HeadlessChrome 식별값을 앱이 204로 차단한 결과였다. 테스트용 browser context에 일반 방문자 UA 기본값을 주되, 테스트가 명시한 모바일/봇 UA는 보존한다. 제품 봇 차단·로그인·멤버십 검사는 변경하지 않는다.

### 4. 실제 기능 문제 또는 정책 판단이 필요한 잔여 항목

최종 잔여 목록과 재검사 결과는 아래 최종 판정에 기록한다. 다음 항목은 단순 문자열만 바꾸어 통과시키지 않는다.

- 관리자 정기 수집 카드: 기존 검사에서 요구하는 카드/수동 보완 영역이 현재 UI에 없다. 별도 복구 작업 범위다.
- 운영자 사진 순서: 관리 UI에 대표사진·삭제는 있지만 reorder 호출/조작이 없다. 기존 검사 실패를 유지한다.
- 최근검색: 검사는 5개를 요구하지만 현 소스는 10개다. 요구사항 확인 없이 5→10으로 기대값을 낮추거나 제품 표시를 바꾸지 않는다.
- 공매 상세/현황조사: 숨겨진 패널·멤버십/펼침 상태 등 실제 브라우저 상태와 fixture를 구별해야 한다. 실패 로그를 성공으로 대체하지 않는다.
- 모바일 길게 누르기: 손을 뗀 뒤 값이 더 바뀌는 관측은 실제 상호작용 위험으로 남긴다.
- homepage `ERR_ABORTED`: 네트워크/내비게이션 fixture 문제와 기능 문제를 확정하기 전에 별도 재검사를 기록한다.

## 시간초과 재현과 정리

API를 180초로 재현한 뒤 60초 재현의 스택에서 파트너 지역 fixture의 SQL에 머무는 것을 확인했다 (`.local/suite-audit/timeout-reproduction/api_test.py.log`). 건물마다 같은 지역 건물 수를 상관 조회하던 조건을 GROUP BY CTE로 계산하도록 바꿨다. 최소 12개 건물·뱃지 제외·두 지역 선택 조건은 유지했다. 제품 SQL/건물 ID는 변경하지 않았다.

frontend_distribution은 과거 180초 timeout 기록이 있지만 이번 자연 실행에서는 같은 timeout이 다시 나타나지 않았다. 이를 자연 재현했다고 주장하지 않는다. preload를 lazy 처리한 뒤 실제 빌드는 정상 종료한다. 별도로 **빌더가 minifier 자식을 기다리는 도중 10초 deadline**을 걸어 스택·자식 종료·임시 workspace 삭제를 검증했다.

- `.local/suite-audit/forced-build-timeout/summary.json`: exit 124, timed_out=true, process_group_cleaned=true, temporary_directory_cleaned=true.
- 해당 로그의 isolated frontend workspace가 삭제된 것을 별도로 확인했다.
- 실행기 단위 검사: deadline의 자식 종료·temp 제거, 정상 종료 후 잔여 자식 종료, Python finally 실행을 검사한다.

강제 deadline 검사는 예상 실패다. 정상 전체 검사 통과 수에 포함하지 않는다.

## 이번 전체 실행과 재검사

오프라인 전체 실행 원본: `.local/suite-audit/after/summary.json`, 상세 로그 같은 디렉터리.

**87개 실행 단위 중 76 통과·11 실패·실행기 deadline 0개**, 총 508.82초. 이 전체 실행 중 마지막 fixture/소스 검사 수정도 진행돼 Python/일부 JS는 별도 최종 재검사를 했다. 따라서 이 결과를 최종 코드의 단일 전체 녹색 실행이라고 표현하지 않는다.

- 이 실행의 API: 통과, 63.03초.
- frontend_distribution: 통과, 34.63초, 압축 JS 93개·HTML 41개.
- smoke: 통과, 37.86초.
- 별도 Python 재검사: **889 통과·0 실패, subtest 131 통과, 54.83초** (`.local/suite-audit/final-python`). 이후 리다이렉트 차단 검사 2개를 추가한 최종 재검사는 별도 기록한다.

## 최종 판정

마지막 일괄 실행은 검사 코드를 더 바꾸지 않은 상태에서 전체를 다시 실행했다. 원본은 `.local/suite-audit/final-all/summary.json` 및 같은 디렉터리 로그다. 아래 891개는 그 전체 실행 시점의 Python 수이며, 병합 후 단독 명령 보강과 892개 재검사는 별도로 기록한다.

| 범위 | 수정 전 | 최종 |
|---|---|---|
| Python pytest | 861 통과·25 실패 (886개) | **891 통과·0 실패**, subtest 131 통과, 32.04초 |
| 전체 실행 단위 | 과거 60 통과·19 실패 (79개) | **80 통과·7 실패 (87개)**, 총 440.56초 |
| API 실행형 | 180초 timeout 재현 | **통과**, 65.87초 |
| frontend_distribution | 과거 180초 timeout; 이번 자연 재현 없음 | **통과**, 26.93초 |
| smoke | 과거 실행 결과와 별도 비교 | **통과**, 20.65초 |
| 실행기 deadline | 과거 2개 | **0개** |
| 실행기 소유 자식·TMPDIR 정리 | 별도 소유권 없음 | 최종 87개 모두 정리 완료 |

Python 검사 5개가 추가됐다: 실행기 종료/정리 3개, 외부 HTTP 리다이렉트 차단 2개. 실패한 기존 검사를 없애서 숫자를 줄인 것이 아니다.

**전체 통과 아님. 마지막 전체 명령은 exit 1이다.** 다음 7개를 통과 예외로 등록하거나 삭제하지 않았다.

| 실패 검사 | 분류 | 근거·처리 |
|---|---|---|
| `admin_scheduled_sync_test.js` | 기존 기능 누락/화면 기준 차이 | 정기 수집 카드·수동 보완 영역 없음. 기존 관리자 동기화 화면 복구 작업과 연결해 해결해야 한다. |
| `auction_sort_browser_test.cjs` | 간헐적 실제 화면 전환 위험 | 390px 정렬 후 상세의 `.auction-panel-general`이 숨겨진 채 30초 대기. 별도 재검사에는 통과했지만 마지막 전체에는 재실패. 성공 재시도로 감추지 않는다. |
| `home_side_widgets_test.js` | 기존 정책 차이·소스 계약 미결 | 검사 5개 vs 현재 최근검색 상한 10개. 승인된 표시 기준 확인 없이 기대값/제품을 바꾸지 않았다. |
| `lodging_operator_wizard_frontend_test.js` | 기존 실제 기능 누락 | 대표사진/삭제는 있지만 사진 순서 UI와 reorder 호출은 없다. backend가 존재하는 것만으로 UI 검사를 성공 처리하지 않는다. |
| `map_location_browser_test.js` | 브라우저 fixture의 패널 상태 전제 미결 | 봇 차단으로 인한 초기 진입 실패는 해결. 이후 관심단지 상세 진입 시 검색 패널이 열려 있어야 한다는 전제에서 실패해 지도 위치/마커 단계까지 못 갔다. 무조건 toggle로 준비하는 별도 시도도 숨겨진 버튼에서 실패했다. 그 미완료 수정은 적용하지 않았다. |
| `operation_redesign_browser_test.js` | 간헐적 실제 터치 종료 위험 | 길게 누르기에서 해제 후 `66→70→72`. 별도 재검사에는 통과했지만 마지막 전체에서는 재실패. 사용자가 손을 뗀 뒤 값이 더 바뀔 가능성을 확인해야 한다. |
| `survey_browser_test.cjs` | 멤버십 역할 fixture/옛 공개 계약 | 비회원은 현재 확인 항목 대신 멤버십 안내를 받는다. 공개 방문에서 확인 항목 3개를 기다리는 기존 fixture가 시간초과. 권한을 우회하지 않았으며, 실제 활성 회원 로그인으로 신청 흐름을 검증하는 보강이 필요하다. |

이 7개는 공공 API 중계의 신규 회귀로 확인된 항목이 아니다. 그렇다고 정상 기능이라고 판단하거나 배포를 전체 승인하지도 않는다. 공매 탭·터치 문제는 실제 브라우저에서 실패를 관측했지만 fixture와 제품 중 어느 쪽이 최종 원인인지 아직 확정하지 않았다.

별도 재검사 원본(`final-python`, `final-verification`, `final-browser`, `final-js`, `final-map`)도 삭제하지 않았다. API의 한 중간 재검사에서 브로커 표본 4개 assertion이 실패했으며, 고유하고 유효한 fixture 주소를 사용한 최종 전체 실행에서는 그 정확한 count/도로명 우선/엑셀 assertion을 유지한 채 통과했다.

### 병합 후 등록된 단독 명령 검증

완료 검증의 `python tests/smoke_test.py`가 한 번 실패했다. 전체 실행기에는 프로젝트 root가 PYTHONPATH에 있었지만 단독 명령에는 없었다. 임시 작업공간에서 호출된 실제 빌더의 사진 선택 사전검사 자식이 `app`을 찾지 못했다. 빌드/검사를 제거하거나 사전검사를 건너뛰지 않았다.

테스트용 workspace가 자식의 프로젝트 import 경로와 오프라인·알림 차단·자동 실행 차단을 직접 제공하고, 종료 시 이전 환경을 복원하도록 수정했다. 등록된 단독 명령에는 실행기 포장을 요구하지 않는다.

- 포장 없이 `python tests/smoke_test.py`: **통과**, `.local/suite-audit/standalone-smoke-fixed.log`.
- Python 전체: **892 통과·0 실패**, subtest 131 통과, 35.63초.
- frontend_distribution: **통과**, 22.02초.
- 후자의 두 검사 원본: `.local/suite-audit/post-merge-verification`.
- 추가된 회귀 검사 1개는 부모 PYTHONPATH가 잘못되어 있고 오프라인 플래그가 꺼진 상황에서 자식 import·HTTP 차단·환경 복원을 검증한다. HTTP transport도 mock 처리해 실제 요청은 불가능하다. 전체 추가 검사는 실행기 4개·HTTP 리다이렉트 2개로 **6개**다.

그 뒤 JS/브라우저 전체를 다시 실행한 것은 아니다. 해당 코드 및 마지막 7개 실패의 기대조건은 그대로이며, **전체 통과 판정으로 변경하지 않는다.**

## 환경 제약·범위 보존

- Python 3.11 및 설치된 pytest/Node/Playwright, 기존 개발 DB 데이터와 테스트용 웹 서버를 사용했다. 운영 DB/Secrets의 실제 값을 조회하지 않았다.
- government 실호출·메일/SMS 실발송·실제 공급자 키/한도는 검증하지 않았다.
- 일부 브라우저 검사는 mock Kakao SDK/공개 API 응답을 쓴다. 실제 지도 공급자 SDK의 도메인 승인까지 검증한 것은 아니다.
- 홈페이지 screenshot에서 로그인 전 검색 화면이 표시되는 것을 확인했다. 로그인한 관리자 화면의 시각 검증은 수행하지 않았다.
- 캠핑 표시, 에어비앤비 분류키, 건물 ID, 운영 DB 연결, 제품 스키마를 수정하지 않았다. 기존 중계 작업의 제품 변경을 되돌리지 않았다.
