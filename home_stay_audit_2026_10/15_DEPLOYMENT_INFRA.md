# 배포·DB·저장소·수집·외부 서비스

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 배포 메타데이터
| primaryUrl | additionalUrls | deploymentType | isDeployed | hasSuccessfulBuild | visibility |
| --- | --- | --- | --- | --- | --- |
| https://homenstay.com | ['https://livingstay-realtrade.replit.app'] | autoscale | True | True | public |

CONFIRMED `.replit` deployment run: `bash scripts/start-prod.sh`; build: `npm run build:frontend`. `scripts/start-prod.sh`와 `gunicorn.conf.py`가 production boot/schema gate 및 worker runtime에 관여합니다. 배포 설정 조회만 했고 publish·workflow 실행하지 않았습니다.

## 개발/운영 DB
`db.py._get_connection_pool()`은 현재 프로세스 DATABASE_URL을 사용합니다. 많은 수집 workflow는 PROD_DATABASE_URL을 DATABASE_URL로 명시 주입합니다; merge/dev 관련 경로는 별도로 DEV_DATABASE_URL을 사용하기도 합니다. 값/호스트/계정은 읽지 않았으므로 각 현재 프로세스의 실제 DSN을 이 보고서가 확정하지는 않습니다. production read-only 조회 지문은 이전 검증 운영 대상과 일치합니다.
`db.py` version gate/init_db는 이미 적용한 schema의 boot DDL을 건너뛰기 위한 코드이며 조사에서는 import/DDL/migration 미실행. Publish schema diff 또는 운영 schema 반영도 실행하지 않았습니다.

## Workflows / 배치
| name | state | command |
| --- | --- | --- |
| Start application | running | gunicorn --bind 0.0.0.0:5000 --reuse-port --timeout 120 --workers 2 --preload --config gunicorn.conf.py app:app |
| smoke | failed | python tests/smoke_test.py |
| api | failed | python tests/api_test.py |
| Backfill Retry | failed | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 19 python -u backfill_tourapi_images.py --status-key admin:tourapi_image_backfill:status --run-id "workflow-$(date +%s)" --sleep 0.2 |
| Fast Sync | finished | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 10 python -u sync_realty_stores.py --daily-cap 7500 --sleep 1.5 --status-key realty_stores_sync_status |
| Fill PK | running | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 19 python -u backfill_building_details.py --continuous --batch-limit 1000 --sleep 1.0 |
| BRHUB Sync | not_started | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 19 python -u sync_brhub.py --end-idx 8877 --progress-key brhub_rescan_progress --status-key brhub_rescan_status --daily-cap 7976 --sleep 1.0 |
| Merge Dev→Prod (dry-run) | not_started | python -u merge_dev_to_prod.py --dry-run |
| Merge Dev→Prod (실제반영) | not_started | python -u merge_dev_to_prod.py |
| Backfill General Lodging | not_started | env DATABASE_URL="$PROD_DATABASE_URL" python -u sync_lodgings.py --include-camping |
| Prewarm Unit Areas | not_started | nice -n 19 python -u prewarm_unit_areas.py --sleep 0.3 --daily-cap 2000 |
| Weekly Digest | not_started | env DATABASE_URL="$PROD_DATABASE_URL" SITE_URL="https://homenstay.com" python -u weekly_digest.py --scheduled |
| 정기 API 통합 동기화 | not_started | env DEV_DATABASE_URL="$DATABASE_URL" DATABASE_URL="$PROD_DATABASE_URL" nice -n 10 python -u scheduled_sync.py --status-key scheduled_sync_status --skip-stage transactions --skip-stage rural --skip-stage hanok |
| 최근 실거래 자동 동기화 | not_started | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 10 python -u scheduled_sync.py --stage transactions --status-key scheduled_sync_status:transactions --orchestrated |
| 농어촌민박 자동 동기화 | not_started | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 10 python -u scheduled_sync.py --stage rural --status-key scheduled_sync_status:rural --orchestrated |
| 한옥체험업 자동 동기화 | not_started | env DATABASE_URL="$PROD_DATABASE_URL" nice -n 10 python -u scheduled_sync.py --stage hanok --status-key scheduled_sync_status:hanok --orchestrated |
| artifacts/mockup-sandbox: Component Preview Server | running | npm run dev |

`.replit`의 작업 정의와 메타데이터를 조회했습니다. 실제 cron OS 설정·YES24 scheduler·정기 작업이 어떤 외부 schedule에서 트리거되는지는 UNKNOWN입니다. 실행 중인 Fill PK 같은 기존 배치를 멈추지 않았으므로 통계 시점이 이동할 수 있습니다. FAILED 표시는 조회 당시 상태이지 이번 조사에서 실패를 유발한 증거가 아닙니다.

## 저장소·사진·서류
`storage_util.py`는 Replit Object Storage Client 및 sidecar 서명 URL, UUID key·파일 signature/확장자·크기·key 정규식 검증. 신청 서류는 비공개 참조·관리자 서명 열람, 매물/건물/운영자 사진은 공개용 key proxy를 별도 사용. bucket ID·signed URL·서류 이미지·업로드 원본은 추출하지 않았습니다. 정적 이미지/사진 provider URL도 별도로 존재하므로 파일 전체를 새 방식으로 옮긴다고 가정하지 않습니다.

## 알림·연락·외부 API
email_util.py(Resend), sms_util.py(Solapi/Aligo 등), weekly_digest·거래/신고/매물 알림·admin outbox·헤더 알림이 존재. provider 전달 성공·동의 이력·계좌 결제 내역은 개인 데이터로 읽지 않았습니다. 운영 email/전화/sender 실제 값은 NOT READ.

## 환경변수 이름·사용처
실제 프로세스 환경 **이름** 221개, Secret 존재 **이름** 44개, 코드 참조 이름 106개. 값은 수집하지 않았습니다.
### Secret 이름 (존재 확인만)
`ADMIN_ACCESS_KEY`, `ALIGO_API_KEY`, `ALIGO_SENDER`, `ALIGO_USER_ID`, `BLD_INSPECTION_SERVICE_KEY`, `BLD_SERVICE_KEY`, `CONNECTORS_HOSTNAME`, `DATA_GO_KR_BROKER_API_KEY`, `DEFAULT_OBJECT_STORAGE_BUCKET_ID`, `FLASK_SECRET_KEY`, `GA4_MEASUREMENT_ID`, `GOOGLE_MAPS_API_KEY`, `JUSO_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_JS_KEY`, `KAKAO_REST_API_KEY`, `LODGING_SERVICE_KEY`, `PGDATABASE`, `PGHOST`, `PGPASSWORD`, `PGPORT`, `PGUSER`, `PRIVATE_OBJECT_DIR`, `PROD_DATABASE_URL`, `PUBLIC_OBJECT_SEARCH_PATHS`, `RELAY_ENABLED`, `RELAY_TOKEN`, `RELAY_TOKEN_BATCH`, `RELAY_USE_BLDG_HUB`, `RELAY_USE_JUSO`, `RELAY_USE_ONBID`, `RELAY_USE_RTMS`, `REPLIT_CONNECTORS_HOSTNAME`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RONE_API_KEY`, `RTMS_SERVICE_KEY`, `SESSION_SECRET`, `SOLAPI_API_KEY`, `SOLAPI_API_SECRET`, `SOLAPI_SENDER`, `STORE_INFO_SERVICE_KEY`, `TOUR_API_SERVICE_KEY`, `VWORLD_API_KEY`
### 런타임 환경 이름 (값 미수집)
`ADMIN_ACCESS_KEY`, `ALIGO_API_KEY`, `ALIGO_SENDER`, `ALIGO_USER_ID`, `AR`, `AS`, `BJDONG_CODE_CSV`, `BLD_INSPECTION_SERVICE_KEY`, `BLD_SERVICE_KEY`, `CC`, `CFLAGS`, `COLORTERM`, `CONFIG_SHELL`, `CONNECTORS_HOSTNAME`, `CXX`, `DATABASE_URL`, `DATA_GO_KR_BROKER_API_KEY`, `DD_AGENT_HOST`, `DD_AGENT_PORT`, `DEFAULT_OBJECT_STORAGE_BUCKET_ID`, `DISPLAY`, `DOCKER_CONFIG`, `EDITOR`, `FLASK_SECRET_KEY`, `GA4_MEASUREMENT_ID`, `GIT_ASKPASS`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_EDITOR`, `GIT_PAGER`, `GIT_TERMINAL_PROMPT`, `GI_TYPELIB_PATH`, `GLIBC_TUNABLES`, `GOOGLE_MAPS_API_KEY`, `GOPROXY`, `GOSUMDB`, `HISTCONTROL`, `HISTFILE`, `HISTFILESIZE`, `HISTSIZE`, `HOME`, `HOST_PATH`, `JUSO_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_JS_KEY`, `KAKAO_REST_API_KEY`, `LANG`, `LD`, `LDFLAGS`, `LD_AUDIT`, `LIBGL_DRIVERS_PATH`, `LOCALE_ARCHIVE`, `LODGING_SERVICE_KEY`, `NIXPKGS_ALLOW_UNFREE`, `NIX_BINTOOLS`, `NIX_BINTOOLS_WRAPPER_TARGET_HOST_x86_64_unknown_linux_gnu`, `NIX_BUILD_CORES`, `NIX_BUILD_TOP`, `NIX_CC`, `NIX_CC_WRAPPER_TARGET_HOST_x86_64_unknown_linux_gnu`, `NIX_CFLAGS_COMPILE`, `NIX_ENFORCE_NO_NATIVE`, `NIX_HARDENING_ENABLE`, `NIX_LDFLAGS`, `NIX_PATH`, `NIX_PS1`, `NIX_STORE`, `NM`, `NO_COLOR`, `NPM_CONFIG_REGISTRY`, `OBJCOPY`, `OBJDUMP`, `PAGER`, `PATH`, `PGDATABASE`, `PGHOST`, `PGPASSWORD`, `PGPORT`, `PGUSER`, `PIP_INDEX_URL`, `PIP_TRUSTED_HOST`, `PKG_CONFIG_PATH`, `PKG_CONFIG_PATH_FOR_TARGET`, `POETRY_CACHE_DIR`, `POETRY_CONFIG_DIR`, `POETRY_DOWNLOAD_WITH_CURL`, `POETRY_INSTALLER_MODERN_INSTALLATION`, `POETRY_PIP_FROM_PATH`, `POETRY_PIP_NO_ISOLATE`, `POETRY_PIP_NO_PREFIX`, `POETRY_PIP_USE_PIP_CACHE`, `POETRY_USE_USER_SITE`, `POETRY_VIRTUALENVS_CREATE`, `PRIVATE_OBJECT_DIR`, `PROD_DATABASE_URL`, `PROMPT_DIRTRIM`, `PUBLIC_BASE_URL`, `PUBLIC_OBJECT_SEARCH_PATHS`, `PWD`, `PYTHONPATH`, `PYTHONUSERBASE`, `RANLIB`, `READELF`, `RELAY_BASE_URL`, `RELAY_ENABLED`, `RELAY_TOKEN`, `RELAY_TOKEN_BATCH`, `RELAY_USE_BLDG_HUB`, `RELAY_USE_JUSO`, `RELAY_USE_ONBID`, `RELAY_USE_RTMS`, `REPLIT_ARTIFACT_ROUTER`, `REPLIT_ASKPASS_PID2_SESSION`, `REPLIT_BASHRC`, `REPLIT_CLI`, `REPLIT_CLUSTER`, `REPLIT_CONNECTORS_HOSTNAME`, `REPLIT_CONNECTOR_TOOLS_PATH`, `REPLIT_CONTAINER`, `REPLIT_DB_URL`, `REPLIT_DEV_DOMAIN`, `REPLIT_DOMAINS`, `REPLIT_ENABLE_INSTRUMENTATION`, `REPLIT_ENVIRONMENT`, `REPLIT_EXPO_DEV_DOMAIN`, `REPLIT_GIT_PROXY_SOURCE_ORIGINS`, `REPLIT_HELIUM_ENABLED`, `REPLIT_HELIUM_USER_QUOTA_BYTES`, `REPLIT_LD_AUDIT`, `REPLIT_LD_LIBRARY_PATH`, `REPLIT_NIX_CHANNEL`, `REPLIT_PID1_NIX_BIN_DIR`, `REPLIT_PID1_VERSION`, `REPLIT_PID2`, `REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE`, `REPLIT_PYTHONPATH`, `REPLIT_PYTHON_LD_LIBRARY_PATH`, `REPLIT_RIPPKGS_INDICES`, `REPLIT_RTLD_LOADER`, `REPLIT_RUN_PATH`, `REPLIT_SEMGREP_RUNTIME_PATH`, `REPLIT_SESSION`, `REPLIT_USER`, `REPLIT_USERID`, `REPLIT_USER_RUN`, `REPL_HOME`, `REPL_ID`, `REPL_IDENTITY`, `REPL_IDENTITY_KEY`, `REPL_IN_MICROVM`, `REPL_LANGUAGE`, `REPL_ORG_ID`, `REPL_ORG_IS_ENTERPRISE`, `REPL_ORG_TYPE`, `REPL_OWNER`, `REPL_OWNER_ID`, `REPL_PUBKEYS`, `REPL_SLUG`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RONE_API_KEY`, `RTMS_SERVICE_KEY`, `SESSION_SECRET`, `SHLVL`, `SITE_URL`, `SIZE`, `SOLAPI_API_KEY`, `SOLAPI_API_SECRET`, `SOLAPI_SENDER`, `SOURCE_DATE_EPOCH`, `STORE_INFO_SERVICE_KEY`, `STRINGS`, `STRIP`, `TERM`, `TOUR_API_SERVICE_KEY`, `TZDIR`, `UV_PROJECT_ENVIRONMENT`, `UV_PYTHON_DOWNLOADS`, `UV_PYTHON_PREFERENCE`, `VWORLD_API_KEY`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_DIRS`, `XDG_DATA_HOME`, `YARN_NPM_REGISTRY_SERVER`, `YARN_REGISTRY`, `_`, `__EGL_VENDOR_LIBRARY_FILENAMES`, `__ETC_PROFILE_SOURCED`, `__structuredAttrs`, `buildInputs`, `buildPhase`, `builder`, `cmakeFlags`, `configureFlags`, `depsBuildBuild`, `depsBuildBuildPropagated`, `depsBuildTarget`, `depsBuildTargetPropagated`, `depsHostHost`, `depsHostHostPropagated`, `depsTargetTarget`, `depsTargetTargetPropagated`, `doCheck`, `doInstallCheck`, `mesonFlags`, `nativeBuildInputs`, `npm_config_prefix`, `npm_config_registry`, `out`, `outputs`, `patches`, `phases`, `preferLocalBuild`, `propagatedBuildInputs`, `propagatedNativeBuildInputs`, `shell`, `shellHook`, `stdenv`, `strictDeps`, `system`
CSV environment_variable_usage.csv에 파일/함수/목적/전송 경로를 기록. 이름만 있고 사용처 없음은 unused의 확증이 아니며 runtime/외부 설정 소비는 UNKNOWN입니다.
