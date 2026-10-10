# YES24 API Relay 전수 추적

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## CONFIRMED 클라이언트 구조
`public_api_client.py:148` · `public_api_get()`; `public_api_client.py:62` · `_enabled()`; `public_api_client.py:134` · `_valid_target()`.

```text
요청: HOME & STAY 수집기/조회 코드
  → public_api_get(service allowlist + RELAY_ENABLED/RELAY_USE_* gate)
  → HTTPS RELAY_BASE_URL /v1/fetch
     query: url = upstream URL + parameters (service key 포함 가능, 출력 금지)
     headers: X-Relay-Token, X-Relay-Purpose(realtime|batch)
  → [YES24 서버에서 외부기관 조회: INFERRED protocol intent, server code UNKNOWN]
응답: Relay HTTP response
  → 안전한 Relay error class / sanitized response.url
  → 기존 XML/JSON parser 및 호출자 retry/quota
  → DB transaction/원장 저장
```

## 범위/인증/시간/재시도
- 허용 host/path: HUB /1613000/BldRgstHubService, RTMS NrgTrade/RHTrade/SHTrade/LandTrade, Onbid /B010003, Juso /addrlink. spooﬁng host, 비HTTPS, path traversal/인코딩 path, fragment, 과도한 URL은 차단.
- RELAY_ENABLED와 각 서비스 switch가 문자열 `1`일 때 활성. 값은 읽지 않아 현재 ON/OFF UNKNOWN. 키 존재는 활성의 증거가 아닙니다.
- realtime token은 RELAY_TOKEN, batch token은 RELAY_TOKEN_BATCH. 값 및 실제 base URL은 미수집.
- base URL은 HTTPS·hostname 존재, userinfo/query/fragment 없음 조건. `allow_redirects=False`.
- 전달 timeout은 각 caller 값을 기반으로 scalar/tuple 각각 최소 20초. 예: 온비드 caller(15,30) → Relay(20,30).
- 공통 함수는 HTTP **한 번** 호출. retryable code: UPSTREAM_TIMEOUT/UPSTREAM_CONNECT/RELAY_BUSY; RelayRetryableError는 ConnectTimeout 계열로 기존 호출자 retry budget에 합류. retry 횟수는 호출자별 다름 (building_registry/store 등 별도 budget); 중계 함수가 새 재시도 loop를 추가하지 않음.
- 활성 Relay 오류에서 direct fallback **없음**. service 미지원/switch OFF에서는 기존 requests.get direct 유지. 이는 장애 시 자동 우회와 다릅니다.
- X-Relay-Error 응답은 정의된 code만 수용. error 객체가 remote URL/메시지를 보유하지 않으며 response.url을 hostname+path로 치환해 키가 포함된 query 유출을 줄입니다.
- local telemetry는 tempfile status JSON+fcntl lock; relay_status() 호출 자체도 상태 디렉터리/lock을 만들 수 있어 이번 조사에서 실행 안 함.

## 사용처
| environment_variable | file | line | function | purpose | status |
| --- | --- | --- | --- | --- | --- |
| RELAY_ENABLED | public_api_client.py | 64 | _enabled | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | CONFIRMED static reference |
| RELAY_BASE_URL | public_api_client.py | 179 | public_api_get | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | CONFIRMED static reference |
| RELAY_AUTH | address_utils.py | 78 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | address_utils.py | 78 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_QUOTA | address_utils.py | 82 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_QUOTA | datasync_transport_advice.py | 132 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_AUTH | datasync_transport_advice.py | 132 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | datasync_transport_advice.py | 132 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_QUOTA | datasync_transport_advice.py | 134 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_USE_BLDG_HUB | public_api_client.py | 33 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_USE_RTMS | public_api_client.py | 34 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_USE_ONBID | public_api_client.py | 35 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_USE_JUSO | public_api_client.py | 36 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_AUTH | public_api_client.py | 39 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | public_api_client.py | 39 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_QUOTA | public_api_client.py | 39 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_BUSY | public_api_client.py | 40 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_INTERNAL | public_api_client.py | 41 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_BUSY | public_api_client.py | 43 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_TOKEN_BATCH | public_api_client.py | 175 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_TOKEN | public_api_client.py | 175 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_INTERNAL | public_api_client.py | 52 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | public_api_client.py | 174 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_AUTH | public_api_client.py | 178 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_INTERNAL | public_api_client.py | 185 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | public_api_client.py | 187 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | public_api_client.py | 190 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | public_api_client.py | 192 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_INTERNAL | public_api_client.py | 214 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_TOKEN | secret_redaction.py | 12 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_TOKEN_BATCH | secret_redaction.py | 12 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_QUOTA | sync_onbid.py | 53 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_AUTH | sync_onbid.py | 55 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |
| RELAY_FORBIDDEN | sync_onbid.py | 55 | <dynamic key / module constant> | 공공 API 중계 전송 설정·목적별 인증; actual value UNKNOWN | INFERRED env key literal; accessor may be dynamic |


## UNKNOWN / 서버 미확인
현재 파일의 클라이언트 프로토콜은 CONFIRMED이며 YES24라는 호스팅 사업자·실제 서버 프로그램·TLS·방화벽·quota·batch 격리·server token 저장·upstream key 로그 제거·연결 성공은 코드만으로 확인되지 않습니다. 사용자가 YES24 중계 운영이라고 설명했으므로 호스팅은 USER-STATED, 독립 검증 UNKNOWN입니다. 중계 서버에 로그인/조회 요청/설정 변경하지 않았습니다.
