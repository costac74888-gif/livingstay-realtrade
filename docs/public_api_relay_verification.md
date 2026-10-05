# 공공 API 중계 연동 검증 결과

## 최신 운영 연결 점검

사용자가 설정 존재 확인 및 건축HUB·실거래 각 1회 실호출을 승인한 뒤 수행했다.
토큰 값은 조회·표시하지 않았으며, 실제 요청의 인증은 기존 전송 계층이 처리했다.
두 토큰의 개발·운영 환경 존재 여부를 확인했다.

| 점검 | 용도 | 결과 |
|---|---|---|
| 건축HUB 표제부 | realtime | HTTP 200, 공급자 정상 코드 `00`, 데이터 1건 |
| 실거래 NrgTrade | batch | HTTP 403, 중계 오류 `RELAY_FORBIDDEN` |

각 요청은 한 번만 수행했고 재시도·대량 수집·DB 쓰기를 하지 않았다.
실거래 거절은 허용 주소·권한·용도·쿼리 정책 중 어느 항목 때문인지 아직 확정하지 않았다.
현재 저장소에는 중계 서버의 정책/토큰 관리 코드가 없으므로 클라이언트에서 권한을 우회하거나 직접 호출로 폴백하지 않는다.
재점검은 별도 호출 승인 후에만 수행한다.

운영 환경에는 사양의 중계 URL을 설정했으며 세 스위치는 모두 `0`으로 유지했다.
이 설정은 다음 재게시 때 적용되는 설정이며, 현재 운영 빌드를 재게시하지 않았다.
건축HUB realtime의 성공을 건축HUB batch·실거래 전체·운영 배포 환경의 성공으로 확대 해석하지 않는다.

전체 검사 최신 기록은 `docs/offline_suite_failure_audit.md`를 따른다:
전체 87개 실행 단위 중 80개 통과·7개 실패이며, 별도 최종 Python 재검사는 892개 및 subtest 131개 통과다.
실거래 중계 거절과 전체 검사 실패가 남아 있으므로 중계 활성화 및 게시 준비 완료로 판정하지 않는다.

## 최초 코드 검증 기록

아래는 실호출 승인 전의 검증 기록이다. 최신 설정·실호출·전체 검사 판정은 위 항목을 따른다.

검증일: 2026-10-05. 실제 공공 API·relay 서버를 시험 호출하지 않았다.
실제 Secrets 값 조회, 운영 DB·스키마 변경, 신규 수집 배치 실행, 새 예약 생성, Publish는 하지 않았다.

## 완료 항목

- 허용 경로에만 선택적으로 중계하는 공통 전송 계층, realtime/batch 토큰 분리.
- 건축물대장 4종, 지정 실거래 4종, 기존 건축HUB 수집기의 호출 연결.
- 기존 건축물대장 사용 배치의 선택 인자 전달. 관광 보강의 주입형 검사 함수는 기존 5개 위치 인자를 유지.
- 공급자 429와 중계 429 분리, 오류 8종, 기존 재시도 횟수·대기 유지, 자동 직접 호출 폴백 없음.
- 원문·URL 인코딩·이중 인코딩 마스킹. 공급자 결과 메시지가 인증값을 되돌려 주는 경우도 마스킹.
- 기존 관리자 데이터 동기화 메뉴의 서비스별 상태 한 줄과 기존 관리자 인증으로 보호되는 상태 API.
- DB·`SCHEMA_VERSION`·캠핑 렌더러·에어비앤비 분류키·건물 ID·운영 DB 연결 설정 미변경.

OFF 검사는 기존 URL·params·timeout으로 `requests.get`이 정확히 한 번 호출되고 동일 응답 객체를 돌려주는지 확인했다.
비허용 API는 모든 스위치를 켜도 직접 호출을 유지하는지 검사했다.
파싱·페이지별 호출 예산·원래 반환형은 호출자 쪽에 남겼으며, 전송 계층에서 새 예산 차감을 넣지 않았다.

## 통과한 검사

최종 관련 검사 명령:

```text
python -m pytest tests/test_public_api_client.py tests/test_secret_redaction.py tests/test_scheduled_sync.py tests/test_tourism_stats_import.py -q
```

외부 HTTP와 알림 발송을 차단하고 테스트용 설정으로 실행:
**87 passed, 56 subtests passed**.

- 중계 최종 사양 T1–T10, 두 기존 재시도 루프, 관리자 API 인증, 추가 마스킹 검사 포함.
- `node tests/public_api_relay_admin_test.cjs`: 통과.
- `npm run build:frontend`: 통과. 134개 파일의 프런트 릴리스 생성.
- 변경 Python 코드 구문 검사, `git diff --check`: 통과.
- 관리자 로그인 페이지 스크린샷: 정상 렌더링. 로그인 뒤 관리자 상태 줄의 시각적 렌더링은 확인하지 않았으며 실제 함수의 DOM 검사와 인증 API 검사로 확인했다.

## 전체 검사 — T11은 미충족

전체 Python/JS 실행 묶음: **87개 검사 실행, 66개 통과, 21개 실패**.
이 숫자는 검사 파일/명령 단위이며 Python 개별 테스트 수와 합산하지 않는다.
API 검사와 프런트 배포 파일 검사는 180초 제한으로 종료했다.
수집기 엔트리포인트나 예약 작업을 실행한 것이 아니다.

전체 Python 최종 재실행 당시:
**858 passed, 27 failed, 131 subtests passed**.
이후 공급자 결과 메시지의 추가 마스킹 검사를 더해 관련 87개 검사를 통과했다.
전체 검사를 전부 통과했다고 보고하지 않는다.

변경 전후 같은 25개 실패 후보를 동일 조건으로 비교:
**양쪽 모두 18 failed, 7 passed이며 실패 집합이 동일**.
기존 관리자 동기화·방문 추이의 두 JS 검사도 변경 전 코드에서 동일하게 실패했다.
전체 실행의 나머지 실패가 모두 기존 문제라고 단정하지 않는다. 오래된 문자열 기준, 검사 환경·실행 순서, 시간초과, 실제 화면 오류를 별도 정리해야 한다.

실패한 실행 단위:

```text
Python pytest
admin_scheduled_sync_test.js
admin_visit_trend_chart_test.js
api_test.py
auction_detail_navigation_browser_test.cjs
auction_sort_browser_test.cjs
building_name_status_test.js
building_type_panels_test.js
camping_detail_contract_test.js
frontend_distribution_test.py
guide_content_test.js
home_side_widgets_test.js
lodging_operator_wizard_frontend_test.js
lodging_type_ui_test.js
map_location_browser_test.js
operation_redesign_browser_test.js
rental_redesign_browser_test.js
request_area_visibility_test.py
smoke_test.py
survey_browser_test.cjs
tourapi_partial_gallery_browser_test.js
```

결과 원본은 `.local/relay-test-results/summary.json`, `pytest-final.log`,
`baseline-python.log`, `current-comparison-python.log`와 실행별 로그에 보관한다.
검사 중의 웹 서버 외부 HTTP 차단과 가짜 키 설정은 제거하고 원래 gunicorn 명령으로 복구했다.
실행 설정 파일도 원본과 동일하다. 복구 후 정상 기동과 관리자 로그인 HTTP 200, 비로그인 상태 API HTTP 401을 확인했다.
향후 전체 검사 제한시간 초과 시에는 검사 프로세스 그룹까지 종료하도록 실행기를 보강했다.
검사가 갱신한 기존 렌탈 화면 캡처는 중계 코드 커밋에 포함하지 않는다.

## 웹·예약 배치 설정 및 게시

상세 안내: `docs/public_api_relay_operations.md`.

입력할 이름만 정리하며 실제 값은 조회·표시하지 않았다:
`RELAY_ENABLED`, `RELAY_USE_BLDG_HUB`, `RELAY_USE_RTMS`,
`RELAY_BASE_URL`, `RELAY_TOKEN`, `RELAY_TOKEN_BATCH`.
모든 스위치는 기본 OFF, URL·토큰은 기본 빈 값이다.

개발 환경, 웹 배포, 각 별도 Scheduled Deployment에 같은 이름의 설정을 명시적으로 준비해야 한다.
웹 설정이 별도 예약 배치에 자동 공유된다고 가정하지 않는다.
실제 배포 설정의 존재 여부나 토큰 권한은 조회하지 않았으므로 확인되지 않았다.
로컬 상태 이력도 별도 배포 실행 환경끼리 공유되지 않는다.

현재 **T11 전체 통과와 실제 운영 설정 확인이 남아 있으므로 게시 준비 완료로 판정하지 않는다**.
사용자의 별도 실제 호출 승인과 설정 확인 없이 중계 스위치를 켜지 않는다.
Publish는 사용자가 진행한다.
