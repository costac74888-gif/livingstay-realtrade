# 홈앤스테이 공공 API 중계 운영 안내

## 적용 범위

기존 앱에 `public_api_client.py`만 공통 전송 계층으로 추가했다. 새 앱·중계 서버를 만들지 않는다.
파싱, 페이지 순회, 기존 호출 예산 차감, 결과 코드 `0/00/000`, 반환 자료 구조는 기존 호출자가 담당한다.
클라이언트에는 추가 재시도 루프나 직접 호출 폴백이 없다.

| 연결 위치 | 용도 |
|---|---|
| `building_registry.py`: 표제부·층별개요·전유공용면적·지역지구구역 | 기본 `realtime` |
| `sync_batch.py`: `fetch_nrg_trade`, 건물 분류 경유 표제부 | `batch` |
| `discover_new_buildings.py`: 실거래·건물 분류 | `batch` |
| `sync_rural_hanok_trades.py`: SH/RH/Nrg/Land, 페이지별 `_claim_call` | `batch` |
| `sync_brhub.py`: `_fetch_page`, 기존 건축HUB 예산 차감 후 요청 | `batch` |
| 기존 건축물대장 사용 배치: 표제부 백필·면적 프리워밍·호실 검증·재분류·숙박 원장 보강·관광 TOP100 보강 | 선택 인자 `purpose="batch"` |

`sync_batch.py`의 `BLD_TITLE_URL` 상수는 남겨 뒀다. 현재 직접 호출 지점은 없으며, 공통 건물 분류 함수를 통해 표제부가 호출되므로 그 경로에 `batch`를 전달한다.

### 반드시 직접 호출을 유지하는 대상

`MtnChkHubService` 유지관리 이력, `ArchPmsHubService` 건축인허가, 온비드,
고캠핑, 숙박업, 상가정보, 기타 실거래 서비스 등 허용 접두어 외의 API.
`apis.data.go.kr` 호스트 전체를 중계하지 않는다.
DB 스키마·`SCHEMA_VERSION`·건물 ID·캠핑 표시·에어비앤비 키·운영 DB 연결 설정은 변경하지 않았다.

## 설정 항목 — 실제 값은 문서·로그·Git에 적지 않는다

| Secrets 이름 | 기본값/설정 의미 |
|---|---|
| `RELAY_ENABLED` | 미설정 또는 `0`: 전체 OFF. 정확히 `1`일 때만 ON |
| `RELAY_USE_BLDG_HUB` | 미설정 또는 `0`: 건축HUB 직접 호출. 정확히 `1`: 중계 허용 |
| `RELAY_USE_RTMS` | 미설정 또는 `0`: 실거래 직접 호출. 정확히 `1`: 지정 4종 중계 허용 |
| `RELAY_BASE_URL` | 기본 빈 값. 활성화 시 `https://relay.homenstay.com` 설정 |
| `RELAY_TOKEN` | 기본 빈 값. 중계 서버가 발급한 realtime 전용 토큰을 안전하게 입력 |
| `RELAY_TOKEN_BATCH` | 기본 빈 값. 중계 서버가 발급한 batch 전용 토큰을 안전하게 입력 |

활성화된 대상에서 해당 용도 토큰이 비어 있으면 요청 없이 `RELAY_AUTH`로 실패한다.
BASE URL이 유효하지 않으면 안전한 설정 오류로 실패한다. 다른 토큰이나 직접 호출로 우회하지 않는다.

## 운영 웹 앱

단계 순서를 바꾸지 않는다. 워크스페이스 실호출 성공을 운영 배포 완료로 해석하지 않는다.

1. **A — 설정 준비:** 운영 환경에 realtime/batch 토큰과 중계 URL을 준비한다. 이미 존재하는 토큰은 재입력하지 않는다. 개발 설정만 넣었다고 운영 적용을 가정하지 않는다.
2. **B — OFF 재게시:** 세 스위치는 모두 `0` 또는 미설정으로 유지하고 사용자가 Republish한다. 중계 경로는 아직 사용하지 않는다. 첫 재게시 성공을 확인하기 전 C 설정을 미리 적용하지 않는다.
3. **C — 웹 건축HUB 활성화:** B 성공 후 운영 웹 앱의 `RELAY_ENABLED=1`, `RELAY_USE_BLDG_HUB=1`을 설정하고 다시 Republish한다. `RELAY_USE_RTMS=0`은 유지한다. 별도 예약 배치는 아직 활성화하지 않는다.
4. **D — 운영 점검:** 운영 사이트에서 실제 건축HUB 요청을 수행하는 기능으로 건물 하나를 조회하고 관리자 → 데이터 동기화의 최근 성공 시각을 확인한다. 캐시 응답만 반환된 조회는 새 중계 통신의 성공 증거가 아니다. 워크스페이스의 성공 시각은 별도 운영 환경에 공유되지 않는다.
5. **E — 실거래 활성화:** 건축HUB가 안정적인 것을 확인한 뒤에만 운영 웹 앱의 `RELAY_USE_RTMS=1`을 설정하고 다시 Republish해 하나씩 확인한다.

건축HUB 스위치는 실행 환경 내의 서비스 단위 설정이다. 같은 웹 실행 환경에서 수행되는 건축HUB batch 요청도 이 스위치를 따르며, realtime만 구분하는 별도 스위치는 없다. 웹과 별도 예약 배치를 구분해 단계적으로 적용한다.

스위치를 끄면 기존 직접 호출 경로로 돌아간다. 기존 배포 환경에서 직접 연결이 막혔던 문제까지 해결되는 것은 아니다.

## 기존 예약 배치

1. 현재 사용 중인 **각 Scheduled Deployment**의 Publishing 설정에서 같은 이름의 설정을 명시적으로 준비한다.
2. 웹 앱의 운영 Secrets나 개발 Secrets가 별도 예약 배치에 자동 공유된다고 가정하지 않는다.
3. 예약 배치도 최초에는 세 스위치를 OFF로 둔다. 기존 실행 명령·일정·DB 연결 방식은 바꾸지 않는다.
4. batch 권한이 있는 `RELAY_TOKEN_BATCH`를 해당 실행 환경에 입력한다. realtime 토큰으로 대체하지 않는다.
5. 사용자 승인 후 기존 배치의 게시 설정을 갱신하고 기존 예약 실행에 적용한다. 새 예약이나 수동 대량 실행은 만들지 않는다.
6. 이미 실행 중인 프로세스는 설정 갱신만으로 환경을 다시 읽지 않는다. 새 설정은 새 실행/재게시된 실행에 적용한다.

공식 문서상 Scheduled Deployment도 Secrets를 사용한다. 운영 웹 환경의 두 토큰 존재는 확인했지만,
현재 각 예약 배포의 게시 시점 설정에 이번 RELAY 설정이 반영됐는지는 확인하지 않았다.
웹 설정 변경만으로 기존 예약 배포에 자동 반영된다고 보고 활성화하지 않는다.

공식 문서:
- https://docs.replit.com/core-concepts/project-editor/app-setup/secrets
- https://docs.replit.com/features/publishing/deployment-types#scheduled
- https://docs.replit.com/features/publishing/overview

## 요청·오류·재시도

중계 쿼리는 `url` 하나뿐이다. 대상 URL은 `requests.Request(...).prepare().url`로 만든다.
용도와 토큰은 각각 `X-Relay-Purpose`, `X-Relay-Token` 헤더에만 담는다.
relay timeout은 기존값보다 짧아지지 않으며 최소 20초다. `(15, 60)`은 `(20, 60)`이 된다.
클라이언트는 relay 리디렉션을 따라가지 않는다.

| 코드 | HTTP | 기존 재시도 대상 |
|---|---|---|
| RELAY_AUTH | 401 | 아니오 |
| RELAY_FORBIDDEN | 403 | 아니오 |
| RELAY_QUOTA | 429 | 아니오 |
| CIRCUIT_OPEN | 503 | 아니오 |
| RELAY_BUSY | 503 | 예 |
| UPSTREAM_TIMEOUT | 504 | 예 |
| UPSTREAM_CONNECT | 502 | 예 |
| RELAY_INTERNAL | 500 | 아니오 |

`X-Relay-Error: 1`인 경우에만 중계 자체 오류다. 공급자 429는 그대로 반환되어 기존 `RateLimitError` 흐름으로 간다.
중계 429는 `RelayError`이며 공급자 한도 오류로 재분류하거나 재시도하지 않는다.
retryable 중계 오류는 기존 `ConnectTimeout` 처리와 호환되며 **기존 호출자에 재시도 루프가 있는 경우에만** 그 횟수·대기를 쓴다.
예: 실시간 건축물대장은 기본 총 3회·2.5초 대기, 기존 건축HUB 수집기는 총 3회·15초 대기.
재시도가 없던 실거래 전송 함수에는 새 재시도 루프를 만들지 않았다.

공급자 응답의 상태·본문·헤더는 유지한다. 예외 출력에서 인증 URL이 노출되지 않도록 relay 응답의 URL 메타데이터만 인증 쿼리가 없는 서비스 경로로 바꾼다.
중계 오류의 원격 message, 요청/응답 객체는 예외에 보관하지 않는다. 오류 문자열에는 고정 문구와 허용 코드만 담긴다.
공통 마스킹은 원문·인코딩·이중 인코딩·relay 요청 URL 전체를 제거한다.

## 상태 표시 범위

DB를 변경하지 않고 로컬 임시 파일에 세 가지 비민감 값만 기록한다.
같은 실행 환경의 웹 워커·배치 프로세스끼리는 파일 잠금으로 공유한다.
**별도 Scheduled Deployment·다른 Autoscale 인스턴스와는 이력을 공유하지 않으며, 임시 저장소가 초기화되면 이력도 초기화된다.**
관리자 줄은 접속한 웹 실행 환경의 상태다. 스위치 설정 확인이나 화면 진입은 공급자 호출을 하지 않는다.
마지막 성공은 중계 HTTP 통신의 2xx 성공 시각이며, 영업 데이터·거래 데이터의 파싱 성공이나 배치 완료를 뜻하지 않는다.
최근 오류는 가장 최근의 중계 오류 코드이며, 이후 성공해도 그 과거 코드 자체는 유지한다.

## 검증

건축HUB realtime 조회는 HTTP 200 / 공급자 코드 `00`로 성공했다.
실거래 batch의 최초 HTTP 403은 서버의 RTMS 허용 추가 후 별도 승인된 1회 재점검에서
HTTP 200 / 공급자 코드 `000`으로 해소됐다. 운영 스위치는 모두 OFF로 유지했다.
이는 워크스페이스의 두 개별 요청 결과이며, 4종 실거래 전체나 운영 배포 환경의 검증이 아니다.
세부 결과와 남은 전체 검사 실패는 `docs/public_api_relay_verification.md`의 최신 운영 연결 점검을 따른다.

`tests/test_public_api_client.py`: T1–T10, 오류 8종, 두 retry 루프, 429 구분,
4종 실거래·건축물대장 파싱, 목적별 토큰, 예산 소유권, URL 검증, 인증 URL 비노출, 관리자 인증.
`tests/public_api_relay_admin_test.cjs`: 기존 메뉴의 상태 표시·안전한 문자열·조회 실패.
`tests/run_offline_suite.py`: 기존 Python pytest 및 Python/JS 실행형 검사 전체.

전체 실행 중 웹 서버에도 `tests/offline_support/sitecustomize.py`의 테스트 전용 차단을 적용해야 한다.
`HOMENSTAY_OFFLINE_TESTS=1`인 검사에서만 활성화되며, 평상시·운영 실행에는 넣지 않는다.
검사를 위해 정상 서버를 오프라인으로 전환했다면 검사 후 원래 gunicorn 실행 명령으로 복구한다.
작업 시작 전부터 오프라인 검사 서버였던 경우에는 그 안전한 상태를 유지하며 임의로 실호출을 활성화하지 않는다.
결과 원본: `.local/relay-test-results/summary.json` 및 각 검사 로그.
전체 검사에 기존 실패가 있다면 전부 통과했다고 보고하지 않고 기준선과 구분한다.

전체 실패 분류·프로세스 정리·최신 재검사 판정: `docs/offline_suite_failure_audit.md`.
현재 실행기는 검사별 deadline과 별도 임시 디렉터리/프로세스 그룹을 사용한다.
최신 작업의 전체 실행 로그는 `.local/suite-audit/`에 있으며, 과거 중계 기준선 원본은 변경하지 않는다.
