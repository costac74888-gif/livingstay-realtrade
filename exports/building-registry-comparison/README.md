# 홈앤스테이 건축물대장 호출·배포 설정 비교 자료

이 ZIP은 **현재 작업공간의 소스 코드와 배포 설정**을 다른 프로젝트와 비교하기 위한 자료입니다.
운영 컨테이너에서 직접 추출한 실행본은 아니므로, 현재 배포본과 동일한 버전인지는 별도로 확인해야 합니다.
API 호출이나 이메일 발송, 데이터베이스 변경은 이 자료 생성 과정에서 수행하지 않았습니다.

## 포함 파일

- `source/building_registry.py`: 건축물대장 공용 HTTP 호출, XML 파싱, 표제부·층별개요·전유공용면적 등의 조회.
- `source/backfill_title_info.py`: 관리자 '건축정보 채우기'가 실행하는 백필. 타임아웃, 재시도, 냉각 대기, 실패 대기열, 진행 상태 기록.
- `source/sync_brhub.py`: 법정동별 전국 표제부 조회. JSON 응답, API 사용량 제한, 페이지 재시도.
- `source/secret_redaction.py`: 오류 메시지의 API 인증값 마스킹.
- `source/app_registry_excerpt.py`: 실제 app.py에서 관리자 실행·상태 조회·분리 프로세스 실행 함수만 발췌. 전체 앱이 아님.
- `config/.replit`: 원본의 런타임 모듈·Nix·deployment·5000 포트와 관련 워크플로 설정만 발췌. 무관한 설정·스토리지 식별자는 제외.
- `config/scripts/start-prod.sh`: 운영 실행 스크립트.
- `config/gunicorn.conf.py`: 워커 수·타임아웃·preload·fork 후 처리.
- `config/replit.nix`: 시스템 패키지 설정.
- `config/requirements.txt`: 원본 Python 의존성 선언. 버전이 고정되어 있지 않아 운영에서 설치된 정확한 버전을 의미하지는 않음.
- `MANIFEST.json`: 원본 경로, 발췌 범위, 파일 SHA-256 목록.

## 먼저 비교할 두 가지 호출 경로

### 관리자 '건축정보 채우기'

`admin_title_info_run` → `_start_detached_sync` → `backfill_title_info.py`
→ `building_registry._fetch_title_rows` → `_get_with_retry` → `requests.get`.

- 표제부 URL: `https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo`
- 인증 환경변수 이름: `BLD_SERVICE_KEY` (실제 값은 포함하지 않음).
- XML 요청: `type=xml`.
- 백필은 연결 타임아웃 15초, 읽기 타임아웃 30초를 별도로 지정.
- 백필에서 공용 HTTP 함수의 자체 재시도는 `retry_max=0`으로 끔.
- 대신 백필 바깥쪽에서 공급자 연결 오류를 최대 3회 재시도하며 15/30/60초 대기.
- 연속 공급자 실패 10회 시 300초 냉각 대기. 지속 실패 건은 완료 처리하지 않고 대기열에 보관.
- 관리자 시작 버튼은 `Popen(..., start_new_session=True)`으로 웹 워커와 분리된 프로세스를 실행.
- DB 상태·하트비트·run_id로 진행과 작업 소유권을 관리.

공용 `_get_with_retry`를 다른 조회에서 기본값으로 사용할 때는 `ConnectTimeout`에 한해 2회 재시도
(총 3회 시도), 시도 간 2.5초 대기입니다. 백필의 바깥쪽 재시도와 혼동하지 않아야 합니다.

### BRHUB 전국 스캔

`sync_brhub.py` → `_fetch_all_dong_pages` → `_fetch_page` → `requests.get`.

- 표제부 URL은 위와 같지만 인증 환경변수 이름은 `DATA_GO_KR_BROKER_API_KEY`.
- JSON 요청: `_type=json`.
- 요청 타임아웃: `timeout=30`.
- 페이지당 최대 3회 시도. 429이면 재시도 전에 60/120초 대기, 그 외 오류는 15초 대기.
- 요청 전에 DB 기반 공용 API 사용량을 예약.

**두 경로 모두 명시적인 `requests.Session`이나 사용자 정의 HTTPAdapter를 사용하지 않습니다.**
따라서 'Python 세션을 사용해서 성공한다'고 단정하면 안 됩니다.

## 배포 설정

원본 `.replit`의 배포 대상은 `autoscale`입니다.
Build 명령은 `npm run build:frontend`, Run 명령은 `bash scripts/start-prod.sh`입니다.
운영 스크립트는 `PROD_DATABASE_URL`을 `DATABASE_URL`로 넘기고 Gunicorn을 실행합니다.
Gunicorn은 워커 2개, 타임아웃 120초, preload 설정을 사용합니다.
이는 **저장된 설정**이며 현재 운영 네트워크 경로·배포 지역·실행 중 버전의 증거는 아닙니다.

## 비밀값 및 실행 주의

API 키·비밀번호·실제 DB 접속 문자열·회원 데이터·운영 로그·`.env`는 포함하지 않았습니다.
소스에 보이는 `os.environ.get(...)`와 셸의 `$PROD_DATABASE_URL` 등은 환경변수 **이름/참조**일 뿐입니다.

이 ZIP은 독립 실행용 프로그램이 아닙니다. 전체 앱과 DB 스키마, 법정동 자료, 아래 의존 모듈은
비교 목적에 불필요하므로 제외했습니다:
`db`, `address_utils`, `lodging_matching`, `stats_cache`, `sync_lodgings`,
`quota_policy`, `addr_norm`, `geocode_buildings`.

백필과 스캔 코드를 다른 프로젝트에서 그대로 실행하지 마세요. API 호출 한도를 사용하고 DB를 수정할 수 있습니다.
네트워크 비교 시에는 URL, 응답 형식 파라미터, 키 인코딩, 타임아웃, 재시도,
실행 환경 및 배포본 버전을 각각 구분해서 확인해야 합니다.