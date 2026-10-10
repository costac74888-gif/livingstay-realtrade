# HOME & STAY 2.0 — Phase 0 Full Read-only Audit

## 목차
- [00_EXECUTIVE_SUMMARY.md](00_EXECUTIVE_SUMMARY.md)
- [01_PROJECT_STRUCTURE.md](01_PROJECT_STRUCTURE.md)
- [02_ROUTE_API_INVENTORY.md](02_ROUTE_API_INVENTORY.md)
- [03_DATABASE_SCHEMA.md](03_DATABASE_SCHEMA.md)
- [04_EXISTING_LODGING_DATA.md](04_EXISTING_LODGING_DATA.md)
- [05_BUILDING_API_PIPELINE.md](05_BUILDING_API_PIPELINE.md)
- [06_MAP_GEO_SYSTEM.md](06_MAP_GEO_SYSTEM.md)
- [07_RTMS_REALTRADE.md](07_RTMS_REALTRADE.md)
- [08_STORE_COMMERCIAL_DATA.md](08_STORE_COMMERCIAL_DATA.md)
- [09_TOURISM_DATA.md](09_TOURISM_DATA.md)
- [10_ONBID_AUCTION.md](10_ONBID_AUCTION.md)
- [11_YES24_RELAY.md](11_YES24_RELAY.md)
- [12_ADMIN_SYSTEM.md](12_ADMIN_SYSTEM.md)
- [13_LISTING_SYSTEM.md](13_LISTING_SYSTEM.md)
- [14_AUTH_USER_SYSTEM.md](14_AUTH_USER_SYSTEM.md)
- [15_DEPLOYMENT_INFRA.md](15_DEPLOYMENT_INFRA.md)
- [16_REUSE_CLASSIFICATION.md](16_REUSE_CLASSIFICATION.md)
- [17_RISK_REGISTER.md](17_RISK_REGISTER.md)
- [18_HOME_STAY_2_READINESS.md](18_HOME_STAY_2_READINESS.md)


---

<!-- 00_EXECUTIVE_SUMMARY.md -->

# HOME & STAY 2.0 — 0단계 조사 요약

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 조사 범위 및 수량
| 항목 | 수량 |
| --- | --- |
| code_files | 433 |
| db_tables | 135 |
| db_columns | 1625 |
| route_method_pairs | 616 |
| distinct_route_paths | 546 |
| external_api_sdk_url_candidates | 58 |
| external_api_endpoints_static | 39 |
| environment_usage_sites_application_config | 339 |
| environment_usage_sites_all | 740 |
| environment_names_referenced | 106 |
| master_direct_fk_constraints | 38 |
| master_direct_fk_tables | 37 |
| admin_menus | 32 |
| major_risks | 20 |

- CONFIRMED: 운영 건물마스터 **85,617건**, 좌표 보유 **85,013건**. 숙박 신고 원장 **145,631행**. 집계는 조회 시점이며 서비스 대표 총계와 같다고 보장하지 않습니다.
- CONFIRMED: 서비스는 `https://homenstay.com`, `autoscale` 배포. 이번 조사에서 HTTP 방문/배포하지 않았습니다.
- CONFIRMED: 모든 운영 관계를 `master_buildings.id` 중심으로 공유하고, 법정 영업분류와 건축물 용도를 별도 필드로 보유합니다.
- CONFIRMED: Relay는 4개 계열(bldg_hub/rtms/onbid/juso)의 옵션 전송 계층이며 파서·재시도·쿼터는 수집기 소관입니다. UNKNOWN: YES24 서버의 실제 배포 코드·실행 스위치 값·quota·TLS.
- INFERRED: 신규 단기임대를 모든 건축물 용도에 개방하는 것은 별도 등록 자산/매물/지도 레이어로 확장하면 가능성이 있습니다. 기존 숙박 원장 재구축으로 대체하는 방식은 부적합합니다.
- UNKNOWN: 신규 예약·캘린더·재고·취소·환불·정산·법적 운영 정책의 완성 여부. 이름만 비슷한 현재 테이블로 완성됐다고 판단하지 않았습니다.

## 산출물 사용법
19개 상세 Markdown, 7개 필수 CSV, 추가 schema/파일 CSV, 통합 Markdown을 제공합니다. `02_ROUTE_API_INVENTORY.md`와 `routes.csv`의 AUTH/DB/외부API 후보는 정적 조사 범위를 표시합니다. 인증 guard가 보인다고 항상 인증 필수인 것은 아닙니다. `03_DATABASE_SCHEMA.md`에 전체 컬럼·제약·인덱스·sequence가 포함됩니다.

## 금지 작업 준수
보고서 작성 이외의 변경·실행은 없음. 개편 제안은 분석 의견이며 구현하지 않았습니다. 기존 수집기의 자율 실행을 중단하거나 조정하지 않았습니다.

외부 API 수는 API/OAuth/WMS endpoint의 고유 정적 URL 기준이며 provider 수/실제 호출 횟수와 다릅니다. base URL·웹링크·폰트는 분리했습니다. 환경 사용처 수는 직접 accessor와 동적 key/이름 참조를 포함하며 CSV에서 CONFIRMED/INFERRED 및 TEST를 구분합니다.


---

<!-- 01_PROJECT_STRUCTURE.md -->

# 프로젝트 전체 구조

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## Git / 디렉터리
- CONFIRMED 현재 branch: `main`. 원격 URL은 userinfo/query/fragment를 제거했습니다.
| name | url |
| --- | --- |
| gitsafe-backup | git://gitsafe:5418/backup.git |
| origin | https://github.com/costac74888-gif/livingstay-realtrade |
| subrepl-01m4i8pw | <redacted/non-HTTP remote> |
| subrepl-0x3kab0a | <redacted/non-HTTP remote> |
| subrepl-2n44rey9 | <redacted/non-HTTP remote> |
| subrepl-2to8ro2f | <redacted/non-HTTP remote> |
| subrepl-36ehb43f | <redacted/non-HTTP remote> |
| subrepl-3ih0c2wh | <redacted/non-HTTP remote> |
| subrepl-5hlamrru | <redacted/non-HTTP remote> |
| subrepl-7gjpofgw | <redacted/non-HTTP remote> |
| subrepl-7hp6cduo | <redacted/non-HTTP remote> |
| subrepl-83xt5dwr | <redacted/non-HTTP remote> |
| subrepl-8kv93bqx | <redacted/non-HTTP remote> |
| subrepl-95obhvcv | <redacted/non-HTTP remote> |
| subrepl-9ce8x8po | <redacted/non-HTTP remote> |
| subrepl-9dgsvp97 | <redacted/non-HTTP remote> |
| subrepl-9qbibbnx | <redacted/non-HTTP remote> |
| subrepl-ae2hdepe | <redacted/non-HTTP remote> |
| subrepl-aglpmw0l | <redacted/non-HTTP remote> |
| subrepl-ay0i5tc6 | <redacted/non-HTTP remote> |
| subrepl-bfr50wck | <redacted/non-HTTP remote> |
| subrepl-crvosl58 | <redacted/non-HTTP remote> |
| subrepl-d0s0h4v6 | <redacted/non-HTTP remote> |
| subrepl-dav8me6p | <redacted/non-HTTP remote> |
| subrepl-dnsgirs3 | <redacted/non-HTTP remote> |
| subrepl-ej8t65be | <redacted/non-HTTP remote> |
| subrepl-f19paane | <redacted/non-HTTP remote> |
| subrepl-f32fqx89 | <redacted/non-HTTP remote> |
| subrepl-fo9rorwz | <redacted/non-HTTP remote> |
| subrepl-fv9bdd0s | <redacted/non-HTTP remote> |
| subrepl-fzikwico | <redacted/non-HTTP remote> |
| subrepl-g57jy1zb | <redacted/non-HTTP remote> |
| subrepl-ga2gs2er | <redacted/non-HTTP remote> |
| subrepl-gaop7geb | <redacted/non-HTTP remote> |
| subrepl-h0hu6kly | <redacted/non-HTTP remote> |
| subrepl-hm0jq8hv | <redacted/non-HTTP remote> |
| subrepl-j9ir94hd | <redacted/non-HTTP remote> |
| subrepl-jij9s9yr | <redacted/non-HTTP remote> |
| subrepl-jj91vh4m | <redacted/non-HTTP remote> |
| subrepl-jneg0dz9 | <redacted/non-HTTP remote> |
| subrepl-m1vzhfzi | <redacted/non-HTTP remote> |
| subrepl-mjslwxwv | <redacted/non-HTTP remote> |
| subrepl-n6uaenf7 | <redacted/non-HTTP remote> |
| subrepl-no7v6cik | <redacted/non-HTTP remote> |
| subrepl-oghxy3c7 | <redacted/non-HTTP remote> |
| subrepl-otzgmsim | <redacted/non-HTTP remote> |
| subrepl-owi8y7dn | <redacted/non-HTTP remote> |
| subrepl-pdq12pe1 | <redacted/non-HTTP remote> |
| subrepl-pfwn1ze9 | <redacted/non-HTTP remote> |
| subrepl-pvmta8re | <redacted/non-HTTP remote> |
| subrepl-pxlydd6a | <redacted/non-HTTP remote> |
| subrepl-q62c78vg | <redacted/non-HTTP remote> |
| subrepl-qpbkh55e | <redacted/non-HTTP remote> |
| subrepl-r3ufg84l | <redacted/non-HTTP remote> |
| subrepl-s836vxyx | <redacted/non-HTTP remote> |
| subrepl-sl0i95j9 | <redacted/non-HTTP remote> |
| subrepl-sm9qwgkg | <redacted/non-HTTP remote> |
| subrepl-sqrnuokk | <redacted/non-HTTP remote> |
| subrepl-tb79pru4 | <redacted/non-HTTP remote> |
| subrepl-tg802oxi | <redacted/non-HTTP remote> |
| subrepl-toq2zlvl | <redacted/non-HTTP remote> |
| subrepl-tvgkv3kd | <redacted/non-HTTP remote> |
| subrepl-u727aavg | <redacted/non-HTTP remote> |
| subrepl-ueby3rln | <redacted/non-HTTP remote> |
| subrepl-uh4c7nbc | <redacted/non-HTTP remote> |
| subrepl-umd0ljde | <redacted/non-HTTP remote> |
| subrepl-uo97dege | <redacted/non-HTTP remote> |
| subrepl-uqdbvmn0 | <redacted/non-HTTP remote> |
| subrepl-uqnuhc48 | <redacted/non-HTTP remote> |
| subrepl-ux668i47 | <redacted/non-HTTP remote> |
| subrepl-v42yj9vk | <redacted/non-HTTP remote> |
| subrepl-v6ezebwx | <redacted/non-HTTP remote> |
| subrepl-v6ma6bhp | <redacted/non-HTTP remote> |
| subrepl-vcwarchw | <redacted/non-HTTP remote> |
| subrepl-xb9irgnv | <redacted/non-HTTP remote> |
| subrepl-xbt96ian | <redacted/non-HTTP remote> |
| subrepl-xjf7tm5s | <redacted/non-HTTP remote> |
| subrepl-xl7y5pmt | <redacted/non-HTTP remote> |
| subrepl-xnhzlo6h | <redacted/non-HTTP remote> |
| subrepl-y3s8u1y4 | <redacted/non-HTTP remote> |
| subrepl-y88e2se6 | <redacted/non-HTTP remote> |
| subrepl-ye3mxzb4 | <redacted/non-HTTP remote> |
| subrepl-yjfmxpga | <redacted/non-HTTP remote> |
| subrepl-zgt7yi9b | <redacted/non-HTTP remote> |

- CONFIRMED 최근 commit 구조 (SHA/날짜만, author/이메일/커밋본문 미수집): 8285754 2026-10-10; fc766f5 2026-10-10; 6af25ab 2026-10-10; 60d3d47 2026-10-10; 0d4a57c 2026-10-10; 5ddd567 2026-10-10; 6e75ea5 2026-10-10; 2eddaf7 2026-10-10.
| directory | files |
| --- | --- |
| <root> | 126 |
| artifacts | 23 |
| exports | 5 |
| reports | 1 |
| scripts | 7 |
| static | 88 |
| tests | 182 |
| utils | 1 |

| extension | files |
| --- | --- |
| .py | 240 |
| .toml | 1 |
| .json | 18 |
| .js | 101 |
| .css | 19 |
| .html | 54 |

## 핵심 파일
- `app.py`: Flask UI/API·회원·파트너·매물·관리자·통계와 외부 모듈 route 등록. 38,402행.
- `db.py`: pooled PostgreSQL 연결, schema bootstrap, version gate. 5,152행. import/init_db 미실행.
- `static/js/main.js`: 지도·검색·마커·공매/분석 UI 연결. 9,126행.
- `static/index.html`: 진입 UI, 스크립트 로딩, 검색 패널 및 상세 DOM.
- `static/admin.html`: 관리자 sidebar + inline JavaScript; 독립 CRUD·배치 실행 버튼 다수.
- `scripts/build_frontend.py`: 원본 HTML/JS를 content-addressed release로 빌드; 이번 조사에서 실행 안 함.

## 기능별 파일 지도
### 건물·건축대장
- `app.py` — CONFIRMED file
- `db.py` — CONFIRMED file
- `building_registry.py` — CONFIRMED file
- `sync_brhub.py` — CONFIRMED file
- `backfill_building_details.py` — CONFIRMED file
- `building_detail_enrichment.py` — CONFIRMED file
- `building_detail_budget.py` — CONFIRMED file
- `geocode_buildings.py` — CONFIRMED file
- `discover_new_buildings.py` — CONFIRMED file

### 숙박 원장·분류
- `lodging_classification.py` — CONFIRMED file
- `lodging_categories.py` — CONFIRMED file
- `lodging_registry` — logical family / exact file UNKNOWN
- `sync_lodgings.py` — CONFIRMED file
- `lodging_import_staging.py` — CONFIRMED file
- `lodging_promotion.py` — CONFIRMED file
- `lodging_data_contract.py` — CONFIRMED file
- `legacy_lodging_gate.py` — CONFIRMED file
- `camping_stats.py` — CONFIRMED file
- `lodging_stats_dedup.py` — CONFIRMED file

### 실거래
- `sync_batch.py` — CONFIRMED file
- `sync_runner.py` — CONFIRMED file
- `sync_rural_hanok_trades.py` — CONFIRMED file
- `deal_alert_digest.py` — CONFIRMED file

### 지도·UI
- `static/index.html` — CONFIRMED file
- `static/js/main.js` — CONFIRMED file
- `static/js/header.js` — CONFIRMED file
- `static/js/auth.js` — CONFIRMED file
- `static/css/main.css` — CONFIRMED file

### 공매
- `auction_domain.py` — CONFIRMED file
- `auction_service.py` — CONFIRMED file
- `auction_schema.py` — CONFIRMED file
- `sync_onbid.py` — CONFIRMED file
- `auction_building_matching.py` — CONFIRMED file
- `auction_building_enrichment.py` — CONFIRMED file
- `survey_service.py` — CONFIRMED file
- `membership_service.py` — CONFIRMED file

### 관광·분석
- `import_tourism_stats.py` — CONFIRMED file
- `tourism_datalab_admin.py` — CONFIRMED file
- `sync_tourism_monthly.py` — CONFIRMED file
- `annual_tourism_roster.py` — CONFIRMED file
- `sync_rone_rental_benchmarks.py` — CONFIRMED file
- `operation_document_parser.py` — CONFIRMED file
- `static/asset_analysis.html` — logical family / exact file UNKNOWN
- `static/js/asset_analysis.js` — logical family / exact file UNKNOWN
- `static/js/operation_analysis.js` — logical family / exact file UNKNOWN

### 상가·중개업소
- `store_info_util.py` — CONFIRMED file
- `sync_stores.py` — CONFIRMED file
- `sync_realty_stores.py` — CONFIRMED file
- `sync_brokers.py` — CONFIRMED file
- `vworld_broker_fetch.py` — CONFIRMED file

### 수집·배포·알림
- `scheduled_sync.py` — CONFIRMED file
- `scheduled_sync_state.py` — CONFIRMED file
- `quota_policy.py` — CONFIRMED file
- `public_api_client.py` — CONFIRMED file
- `data_sync_transport.py` — CONFIRMED file
- `gunicorn.conf.py` — CONFIRMED file
- `scripts/start-prod.sh` — CONFIRMED file
- `scripts/build_frontend.py` — CONFIRMED file
- `email_util.py` — CONFIRMED file
- `sms_util.py` — CONFIRMED file
- `weekly_digest.py` — CONFIRMED file
- `storage_util.py` — CONFIRMED file
- `admin_action_center.py` — CONFIRMED file
- `admin_action_digest.py` — CONFIRMED file

## 전체 조사 코드 파일
| file | scope |
| --- | --- |
| addr_norm.py | APPLICATION/MOCKUP |
| address_utils.py | APPLICATION/MOCKUP |
| admin_action_center.py | APPLICATION/MOCKUP |
| admin_action_digest.py | APPLICATION/MOCKUP |
| analyze_lodging_staging_matches.py | APPLICATION/MOCKUP |
| annual_tourism_roster.py | APPLICATION/MOCKUP |
| app.py | APPLICATION/MOCKUP |
| apply_lodging_import.py | APPLICATION/MOCKUP |
| apply_lodging_promotion.py | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/.replit-artifact/artifact.toml | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/components.json | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/Current-CEsS0EQE.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/CurrentReport-6ftZUWS6.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/DesktopWithPhoto-Btd_Qzrf.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/PrintWithPhoto-Dj64w35o.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/Proposal-ChR81eLr.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/ReportCore-DMPNa7kk.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/_group-panxU72g.css | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/index-BCjbppDl.js | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/assets/index-D6JrBVwT.css | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/index.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/weekly-current.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/dist/weekly-production.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/index.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/package-lock.json | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/package.json | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/public/weekly-current.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/public/weekly-production.html | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/src/components/mockups/analysis-photo/_group.css | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/src/components/mockups/property-purchase/_group.css | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/src/index.css | APPLICATION/MOCKUP |
| artifacts/mockup-sandbox/tsconfig.json | APPLICATION/MOCKUP |
| auction_building_enrichment.py | APPLICATION/MOCKUP |
| auction_building_matching.py | APPLICATION/MOCKUP |
| auction_domain.py | APPLICATION/MOCKUP |
| auction_schema.py | APPLICATION/MOCKUP |
| auction_service.py | APPLICATION/MOCKUP |
| backfill_address.py | APPLICATION/MOCKUP |
| backfill_broker_norm.py | APPLICATION/MOCKUP |
| backfill_building_details.py | APPLICATION/MOCKUP |
| backfill_from_lodging_registry.py | APPLICATION/MOCKUP |
| backfill_gocamping_web.py | APPLICATION/MOCKUP |
| backfill_permits.py | APPLICATION/MOCKUP |
| backfill_title_info.py | APPLICATION/MOCKUP |
| backfill_tourapi_images.py | APPLICATION/MOCKUP |
| bjdong_codes.json | APPLICATION/MOCKUP |
| build_lodging_production_manifest.py | APPLICATION/MOCKUP |
| building_detail_budget.py | APPLICATION/MOCKUP |
| building_detail_enrichment.py | APPLICATION/MOCKUP |
| building_registry.py | APPLICATION/MOCKUP |
| camping_stats.py | APPLICATION/MOCKUP |
| classify_original_buildings.py | APPLICATION/MOCKUP |
| cleanup_permit_pipeline.py | APPLICATION/MOCKUP |
| compare_lodging_parallel.py | APPLICATION/MOCKUP |
| data_sync_transport.py | APPLICATION/MOCKUP |
| datasync_board.py | APPLICATION/MOCKUP |
| datasync_controls.py | APPLICATION/MOCKUP |
| datasync_transport_advice.py | APPLICATION/MOCKUP |
| db.py | APPLICATION/MOCKUP |
| deal_alert_digest.py | APPLICATION/MOCKUP |
| discover_new_buildings.py | APPLICATION/MOCKUP |
| email_util.py | APPLICATION/MOCKUP |
| exports/HOME_AND_STAY_COMPREHENSIVE_OPERATIONS_MANUAL_V01_0_2026-09-04.html | APPLICATION/MOCKUP |
| exports/HOME_AND_STAY_DATA_POLICY_V03_0_2026-09-04.html | APPLICATION/MOCKUP |
| exports/HOME_AND_STAY_PHOTO_OPERATIONS_MANUAL_V01_0_2026-09-04.html | APPLICATION/MOCKUP |
| exports/HOME_AND_STAY_POLICY_DOCUMENT_REGISTER_V01_0_2026-09-04.html | APPLICATION/MOCKUP |
| exports/HOME_AND_STAY_PUBLIC_DATA_PRIVACY_POLICY_V01_0_2026-09-04.html | APPLICATION/MOCKUP |
| geocode_brokers.py | APPLICATION/MOCKUP |
| geocode_buildings.py | APPLICATION/MOCKUP |
| gunicorn.conf.py | APPLICATION/MOCKUP |
| import_airbnb_lodging.py | APPLICATION/MOCKUP |
| import_camping_lodging.py | APPLICATION/MOCKUP |
| import_hanok_lodging.py | APPLICATION/MOCKUP |
| import_hotel_operation.py | APPLICATION/MOCKUP |
| import_rural_lodging.py | APPLICATION/MOCKUP |
| import_subway_stations.py | APPLICATION/MOCKUP |
| import_tourism_stats.py | APPLICATION/MOCKUP |
| import_vworld_brokers.py | APPLICATION/MOCKUP |
| legacy_lodging_gate.py | APPLICATION/MOCKUP |
| listing_extensions.py | APPLICATION/MOCKUP |
| load_authority_contacts.py | APPLICATION/MOCKUP |
| load_master.py | APPLICATION/MOCKUP |
| lodging_categories.py | APPLICATION/MOCKUP |
| lodging_classification.py | APPLICATION/MOCKUP |
| lodging_data_contract.py | APPLICATION/MOCKUP |
| lodging_import_staging.py | APPLICATION/MOCKUP |
| lodging_matching.py | APPLICATION/MOCKUP |
| lodging_promotion.py | APPLICATION/MOCKUP |
| lodging_report_status.py | APPLICATION/MOCKUP |
| lodging_staging.py | APPLICATION/MOCKUP |
| lodging_stats_dedup.py | APPLICATION/MOCKUP |
| membership_checks.py | APPLICATION/MOCKUP |
| membership_common.py | APPLICATION/MOCKUP |
| membership_schema.py | APPLICATION/MOCKUP |
| membership_service.py | APPLICATION/MOCKUP |
| merge_dev_to_prod.py | APPLICATION/MOCKUP |
| migrate_regions.py | APPLICATION/MOCKUP |
| operation_document_parser.py | APPLICATION/MOCKUP |
| package-lock.json | APPLICATION/MOCKUP |
| package.json | APPLICATION/MOCKUP |
| premium_membership.py | APPLICATION/MOCKUP |
| prewarm_tourapi_metadata.py | APPLICATION/MOCKUP |
| prewarm_unit_areas.py | APPLICATION/MOCKUP |
| public_api_client.py | APPLICATION/MOCKUP |
| quota_policy.py | APPLICATION/MOCKUP |
| reclassify_brhub.py | APPLICATION/MOCKUP |
| reclassify_buildings.py | APPLICATION/MOCKUP |
| reclassify_unclassified.py | APPLICATION/MOCKUP |
| report_authority_match.py | APPLICATION/MOCKUP |
| reports/rural_hanok_classification_conflicts.json | APPLICATION/MOCKUP |
| run_backfill.py | APPLICATION/MOCKUP |
| run_tourapi_full_collection.py | APPLICATION/MOCKUP |
| scheduled_sync.py | APPLICATION/MOCKUP |
| scheduled_sync_state.py | APPLICATION/MOCKUP |
| scripts/build_frontend.py | APPLICATION/MOCKUP |
| scripts/build_policy_manual_bundle.py | APPLICATION/MOCKUP |
| scripts/ensure_presale_schema.py | APPLICATION/MOCKUP |
| scripts/ensure_tourism_datalab_schema.py | APPLICATION/MOCKUP |
| scripts/generate_tourism_datalab_checklist.py | APPLICATION/MOCKUP |
| scripts/test_localdata_api.py | APPLICATION/MOCKUP |
| scripts/unify_approved_brokers.py | APPLICATION/MOCKUP |
| secret_redaction.py | APPLICATION/MOCKUP |
| seed_house_agent.py | APPLICATION/MOCKUP |
| sms_util.py | APPLICATION/MOCKUP |
| static/admin.html | APPLICATION/MOCKUP |
| static/admin_ad_products.html | APPLICATION/MOCKUP |
| static/admin_login.html | APPLICATION/MOCKUP |
| static/agent_dashboard.html | APPLICATION/MOCKUP |
| static/agent_login.html | APPLICATION/MOCKUP |
| static/agent_profile.html | APPLICATION/MOCKUP |
| static/agents.html | APPLICATION/MOCKUP |
| static/analysis.html | APPLICATION/MOCKUP |
| static/apply_agent.html | APPLICATION/MOCKUP |
| static/apply_edit.html | APPLICATION/MOCKUP |
| static/apply_loan_consultant.html | APPLICATION/MOCKUP |
| static/apply_lodging_operator.html | APPLICATION/MOCKUP |
| static/apply_operator.html | APPLICATION/MOCKUP |
| static/apply_presale.html | APPLICATION/MOCKUP |
| static/auctions.html | APPLICATION/MOCKUP |
| static/broker_listing_review.html | APPLICATION/MOCKUP |
| static/building.html | APPLICATION/MOCKUP |
| static/css/admin-membership.css | APPLICATION/MOCKUP |
| static/css/analysis-chart-fixes.css | APPLICATION/MOCKUP |
| static/css/analysis-common.css | APPLICATION/MOCKUP |
| static/css/analysis-layout.css | APPLICATION/MOCKUP |
| static/css/analysis-mobile.css | APPLICATION/MOCKUP |
| static/css/analysis.css | APPLICATION/MOCKUP |
| static/css/auctions.css | APPLICATION/MOCKUP |
| static/css/main.css | APPLICATION/MOCKUP |
| static/css/membership.css | APPLICATION/MOCKUP |
| static/css/mobile-readable-standalone.css | APPLICATION/MOCKUP |
| static/css/operation-redesign.css | APPLICATION/MOCKUP |
| static/css/rental-analysis.css | APPLICATION/MOCKUP |
| static/css/rental-positioning.css | APPLICATION/MOCKUP |
| static/css/survey.css | APPLICATION/MOCKUP |
| static/guide.html | APPLICATION/MOCKUP |
| static/index.html | APPLICATION/MOCKUP |
| static/js/admin-membership.js | APPLICATION/MOCKUP |
| static/js/admin-survey.js | APPLICATION/MOCKUP |
| static/js/admin.js | APPLICATION/MOCKUP |
| static/js/analysis-print.js | APPLICATION/MOCKUP |
| static/js/analysis-terms.js | APPLICATION/MOCKUP |
| static/js/analysis.js | APPLICATION/MOCKUP |
| static/js/auction-panel.js | APPLICATION/MOCKUP |
| static/js/auction-survey.js | APPLICATION/MOCKUP |
| static/js/auctions.js | APPLICATION/MOCKUP |
| static/js/auth.js | APPLICATION/MOCKUP |
| static/js/broker_listing_review.js | APPLICATION/MOCKUP |
| static/js/chat_common.js | APPLICATION/MOCKUP |
| static/js/doc_dropzone.js | APPLICATION/MOCKUP |
| static/js/facility_icons.js | APPLICATION/MOCKUP |
| static/js/format_util.js | APPLICATION/MOCKUP |
| static/js/header.js | APPLICATION/MOCKUP |
| static/js/icons.js | APPLICATION/MOCKUP |
| static/js/listing_checklist.js | APPLICATION/MOCKUP |
| static/js/listing_icons.js | APPLICATION/MOCKUP |
| static/js/listing_modal.js | APPLICATION/MOCKUP |
| static/js/main.js | APPLICATION/MOCKUP |
| static/js/membership.js | APPLICATION/MOCKUP |
| static/js/operation-analysis.js | APPLICATION/MOCKUP |
| static/js/operation-settings.js | APPLICATION/MOCKUP |
| static/js/outbound-stats.js | APPLICATION/MOCKUP |
| static/js/partner_login.js | APPLICATION/MOCKUP |
| static/js/pw_toggle.js | APPLICATION/MOCKUP |
| static/js/rental-analysis.js | APPLICATION/MOCKUP |
| static/js/rental-costs.js | APPLICATION/MOCKUP |
| static/js/slider-utils.js | APPLICATION/MOCKUP |
| static/listings.html | APPLICATION/MOCKUP |
| static/loan_consultant_dashboard.html | APPLICATION/MOCKUP |
| static/loan_consultant_login.html | APPLICATION/MOCKUP |
| static/loan_consultant_profile.html | APPLICATION/MOCKUP |
| static/loan_consultants_list.html | APPLICATION/MOCKUP |
| static/loan_partners.html | APPLICATION/MOCKUP |
| static/lodging_operator_manage.html | APPLICATION/MOCKUP |
| static/manifest.json | APPLICATION/MOCKUP |
| static/membership.html | APPLICATION/MOCKUP |
| static/menu.html | APPLICATION/MOCKUP |
| static/mypage.html | APPLICATION/MOCKUP |
| static/notices.html | APPLICATION/MOCKUP |
| static/operator_dashboard.html | APPLICATION/MOCKUP |
| static/operator_login.html | APPLICATION/MOCKUP |
| static/operator_profile.html | APPLICATION/MOCKUP |
| static/operators.html | APPLICATION/MOCKUP |
| static/partner.html | APPLICATION/MOCKUP |
| static/partner_login.html | APPLICATION/MOCKUP |
| static/partners_directory.html | APPLICATION/MOCKUP |
| static/privacy.html | APPLICATION/MOCKUP |
| static/reset-password.html | APPLICATION/MOCKUP |
| static/survey_terms.html | APPLICATION/MOCKUP |
| static/terms.html | APPLICATION/MOCKUP |
| static/transactions.html | APPLICATION/MOCKUP |
| static/unsubscribe_done.html | APPLICATION/MOCKUP |
| stats_cache.py | APPLICATION/MOCKUP |
| step5_all_production_delta.json | APPLICATION/MOCKUP |
| step5_foreign_production_delta.json | APPLICATION/MOCKUP |
| step5_lodging_match_analysis.json | APPLICATION/MOCKUP |
| step7_lodging_approval_dry_run.json | APPLICATION/MOCKUP |
| step7_production_baseline_manifest.json | APPLICATION/MOCKUP |
| step8_lodging_parallel_comparison.json | APPLICATION/MOCKUP |
| step8_lodging_promotion_parity.json | APPLICATION/MOCKUP |
| step8_lodging_status_comparison.json | APPLICATION/MOCKUP |
| storage_util.py | APPLICATION/MOCKUP |
| store_info_util.py | APPLICATION/MOCKUP |
| survey_defaults.py | APPLICATION/MOCKUP |
| survey_schema.py | APPLICATION/MOCKUP |
| survey_service.py | APPLICATION/MOCKUP |
| sync_batch.py | APPLICATION/MOCKUP |
| sync_brhub.py | APPLICATION/MOCKUP |
| sync_brokers.py | APPLICATION/MOCKUP |
| sync_building_photos.py | APPLICATION/MOCKUP |
| sync_lodgings.py | APPLICATION/MOCKUP |
| sync_onbid.py | APPLICATION/MOCKUP |
| sync_permits.py | APPLICATION/MOCKUP |
| sync_realty_stores.py | APPLICATION/MOCKUP |
| sync_rone_rental_benchmarks.py | APPLICATION/MOCKUP |
| sync_runner.py | APPLICATION/MOCKUP |
| sync_rural_hanok.py | APPLICATION/MOCKUP |
| sync_rural_hanok_trades.py | APPLICATION/MOCKUP |
| sync_stores.py | APPLICATION/MOCKUP |
| sync_tourism_monthly.py | APPLICATION/MOCKUP |
| tests/admin_data_sync_scope_test.js | TEST |
| tests/admin_grid_reload_test.js | TEST |
| tests/admin_listing_tabs_test.js | TEST |
| tests/admin_lodging_filter_display_test.js | TEST |
| tests/admin_pagination_test.js | TEST |
| tests/admin_scheduled_sync_test.js | TEST |
| tests/admin_visit_trend_chart_test.js | TEST |
| tests/agency_link_reorder_test.js | TEST |
| tests/agent_listing_status_edit_test.py | TEST |
| tests/analysis_building_scope_test.js | TEST |
| tests/analysis_frontend_contract_test.js | TEST |
| tests/analysis_menu_access_browser_test.js | TEST |
| tests/analysis_mobile_browser_test.js | TEST |
| tests/analysis_print_detail_contract_test.py | TEST |
| tests/analysis_print_terms_test.js | TEST |
| tests/analysis_print_verdict_terms_contract_test.py | TEST |
| tests/analysis_quadrant_print_contract_test.js | TEST |
| tests/analysis_recent_api_test.py | TEST |
| tests/analysis_slider_step_controls_test.js | TEST |
| tests/analysis_terms_details_browser_test.js | TEST |
| tests/analysis_transient_retry_test.py | TEST |
| tests/api_test.py | TEST |
| tests/auth_reset_modal_test.js | TEST |
| tests/brhub_progress_test.py | TEST |
| tests/building_name_status_test.js | TEST |
| tests/building_photo_provider_test.py | TEST |
| tests/building_type_panels_test.js | TEST |
| tests/camping_detail_contract_test.js | TEST |
| tests/camping_image_backfill_admin_contract_test.js | TEST |
| tests/chat_ui_test.js | TEST |
| tests/datalab_emoji_contract_test.js | TEST |
| tests/deal_alert_digest_test.py | TEST |
| tests/favorite_limit_consistency_test.py | TEST |
| tests/favorite_save_rollback_test.js | TEST |
| tests/fixtures/building_photo_candidates/manifest.json | TEST |
| tests/frontend_distribution_test.py | TEST |
| tests/gocamping_web_admin_contract_test.js | TEST |
| tests/guide_content_test.js | TEST |
| tests/home_navigation_test.js | TEST |
| tests/home_search_panel_test.js | TEST |
| tests/home_side_widgets_test.js | TEST |
| tests/hotel_operation_admin_contract_test.js | TEST |
| tests/listing_checklist_static_test.js | TEST |
| tests/listing_deletion_archive_test.py | TEST |
| tests/listing_modal_registrant_test.js | TEST |
| tests/listing_withdrawal_state_test.py | TEST |
| tests/listings_card_layout_test.js | TEST |
| tests/lodging_operator_manage_onboarding_test.js | TEST |
| tests/lodging_operator_wizard_frontend_test.js | TEST |
| tests/lodging_stats_collapse_test.js | TEST |
| tests/lodging_type_ui_test.js | TEST |
| tests/map_legend_spacing_test.py | TEST |
| tests/map_location_browser_test.js | TEST |
| tests/map_location_test.js | TEST |
| tests/map_marker_color_contrast_test.js | TEST |
| tests/map_search_feedback_test.js | TEST |
| tests/map_toolbar_tools_test.js | TEST |
| tests/map_zero_activity_marker_test.js | TEST |
| tests/member_admin_loan_contract_test.py | TEST |
| tests/menu_shortcuts_contract_test.js | TEST |
| tests/mobile_favorite_expand_test.js | TEST |
| tests/mobile_recent_search_layout_test.py | TEST |
| tests/mypage_listing_controls_test.js | TEST |
| tests/mypage_room_inventory_channels_test.js | TEST |
| tests/mypage_room_inventory_test.js | TEST |
| tests/offline_support/frontend_workspace.py | TEST |
| tests/offline_support/process_runner.py | TEST |
| tests/offline_support/sitecustomize.py | TEST |
| tests/operation_building_switch_test.js | TEST |
| tests/operation_cost_rules_test.js | TEST |
| tests/operation_print_report_quality_test.py | TEST |
| tests/operation_redesign_browser_test.js | TEST |
| tests/operator_partner_cta_mobile_test.js | TEST |
| tests/partner_api_integration_test.py | TEST |
| tests/partner_favorites_weekly_test.py | TEST |
| tests/partner_hub_contract_test.js | TEST |
| tests/platform_stats_test.js | TEST |
| tests/presale_frontend_contract_test.js | TEST |
| tests/presale_pending_members_test.py | TEST |
| tests/public_business_listing_summary_test.js | TEST |
| tests/rental_redesign_browser_test.js | TEST |
| tests/request_area_visibility_test.py | TEST |
| tests/rone_rental_sync_test.py | TEST |
| tests/run_offline_suite.py | TEST |
| tests/slider_utils_test.js | TEST |
| tests/smoke_test.py | TEST |
| tests/test_admin_dashboard_overview.js | TEST |
| tests/test_admin_transaction_search.py | TEST |
| tests/test_admin_visit_trends.py | TEST |
| tests/test_airbnb_import.py | TEST |
| tests/test_all_partner_login.py | TEST |
| tests/test_analysis_assets_contract.py | TEST |
| tests/test_annual_tourism_roster.py | TEST |
| tests/test_annual_tourism_roster_routes.py | TEST |
| tests/test_apply_lodging_promotion.py | TEST |
| tests/test_auction_api.py | TEST |
| tests/test_auction_building_enrichment.py | TEST |
| tests/test_auction_building_matching.py | TEST |
| tests/test_auction_building_stats.py | TEST |
| tests/test_auction_category.py | TEST |
| tests/test_auction_domain.py | TEST |
| tests/test_auction_lookup_integration.py | TEST |
| tests/test_backfill_title_info_reconnect.py | TEST |
| tests/test_bank_membership.py | TEST |
| tests/test_building_detail_enrichment.py | TEST |
| tests/test_camping_detail_ui.py | TEST |
| tests/test_camping_import.py | TEST |
| tests/test_camping_stats.py | TEST |
| tests/test_data_sync_transport.py | TEST |
| tests/test_datasync_board.py | TEST |
| tests/test_datasync_controls.py | TEST |
| tests/test_datasync_transport_advice.py | TEST |
| tests/test_db_connection_pool.py | TEST |
| tests/test_db_schema_version.py | TEST |
| tests/test_gocamping_web_backfill.py | TEST |
| tests/test_gunicorn_stats_lifecycle.py | TEST |
| tests/test_hanok_import.py | TEST |
| tests/test_hotel_operation_import.py | TEST |
| tests/test_juso_relay.py | TEST |
| tests/test_listing_extensions.py | TEST |
| tests/test_lodging_admin_controls.py | TEST |
| tests/test_lodging_all_production_delta.py | TEST |
| tests/test_lodging_approval_promotion.py | TEST |
| tests/test_lodging_categories.py | TEST |
| tests/test_lodging_data_contract.py | TEST |
| tests/test_lodging_operator_partner.py | TEST |
| tests/test_lodging_production_delta.py | TEST |
| tests/test_lodging_promotion.py | TEST |
| tests/test_lodging_promotion_automation.py | TEST |
| tests/test_lodging_report_status.py | TEST |
| tests/test_lodging_staging.py | TEST |
| tests/test_lodging_staging_matching.py | TEST |
| tests/test_lodging_stats_dedup.py | TEST |
| tests/test_lodging_stats_ui.py | TEST |
| tests/test_membership_visibility.py | TEST |
| tests/test_offline_egress_guard.py | TEST |
| tests/test_offline_suite_runner.py | TEST |
| tests/test_onbid_relay.py | TEST |
| tests/test_operation_benchmarks_contract.py | TEST |
| tests/test_operation_benchmarks_integration.py | TEST |
| tests/test_operation_document_parser.py | TEST |
| tests/test_operation_upload_contract.py | TEST |
| tests/test_operation_upload_integration.py | TEST |
| tests/test_photo_validate.py | TEST |
| tests/test_policy_manual_contract.py | TEST |
| tests/test_presale_feature_contract.py | TEST |
| tests/test_prewarm_unit_areas.py | TEST |
| tests/test_public_api_client.py | TEST |
| tests/test_public_operating_records.py | TEST |
| tests/test_region_transaction_stats.py | TEST |
| tests/test_rental_market_price.py | TEST |
| tests/test_role_login.py | TEST |
| tests/test_rural_hanok_sync.py | TEST |
| tests/test_rural_hanok_trade_sync.py | TEST |
| tests/test_rural_import.py | TEST |
| tests/test_scheduled_sync.py | TEST |
| tests/test_secret_redaction.py | TEST |
| tests/test_stats_invalidation_paths.py | TEST |
| tests/test_store_batch_priority.py | TEST |
| tests/test_survey.py | TEST |
| tests/test_tourapi_backfill_launch_contract.py | TEST |
| tests/test_tourapi_image_backfill.py | TEST |
| tests/test_tourism_api_contract.py | TEST |
| tests/test_tourism_datalab_admin.py | TEST |
| tests/test_tourism_monthly_sync.py | TEST |
| tests/test_tourism_stats_import.py | TEST |
| tests/test_transaction_scope_isolation.py | TEST |
| tests/test_transaction_sync_deadlock.py | TEST |
| tests/test_unified_account.py | TEST |
| tests/test_weekly_digest_manual.py | TEST |
| tests/test_weekly_digest_news.py | TEST |
| tests/test_zip_code_backfill.py | TEST |
| tests/tourapi_metadata_test.py | TEST |
| tests/tourapi_partial_gallery_browser_test.js | TEST |
| tests/tourapi_partial_gallery_contract_test.py | TEST |
| tests/tourism_datalab_admin_contract_test.js | TEST |
| tests/tourism_frontend_contract_test.js | TEST |
| tests/transaction_sync_boot_contract_test.py | TEST |
| tests/transactions_trend_layout_test.js | TEST |
| tests/unified_account_context_frontend_test.js | TEST |
| tests/weekly_digest_test.py | TEST |
| tests/weekly_email_optin_test.py | TEST |
| tourism_datalab_admin.py | APPLICATION/MOCKUP |
| utils/photo_validate.py | APPLICATION/MOCKUP |
| validate_lodging_all_production_delta.py | APPLICATION/MOCKUP |
| validate_lodging_approval_promotion.py | APPLICATION/MOCKUP |
| validate_lodging_production_delta.py | APPLICATION/MOCKUP |
| verify_units.py | APPLICATION/MOCKUP |
| vworld_broker_fetch.py | APPLICATION/MOCKUP |
| weekly_digest.py | APPLICATION/MOCKUP |
| weekly_digest_news.py | APPLICATION/MOCKUP |
| weekly_digest_runner.py | APPLICATION/MOCKUP |
| zip_code_backfill.py | APPLICATION/MOCKUP |


---

<!-- 02_ROUTE_API_INVENTORY.md -->

# Route/API 전수 정적 인벤토리

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 계수·해석
- CONFIRMED 애플리케이션 정의: **616 METHOD/PATH 조합**, **546 고유 PATH**. 테스트 fixture의 route 4조합은 서비스 수에서 제외했습니다.
- HEAD/OPTIONS의 Flask 자동 추가는 제외. Blueprint prefix, 동적 add_url_rule, 런타임 dependency injection은 정적 정의만으로 완전 증명할 수 없어 UNKNOWN입니다. 앱을 import하면 DB bootstrap/스레드/서버 부수효과가 생길 수 있어 import하지 않았습니다.
- `app.py:38389` 부근에서 auction/survey/membership/listing extension route 등록을 확인. 등록 dependency의 실제 실행은 수행하지 않았습니다.
- AUTH decorator는 CONFIRMED. 함수 내 guard/4단계 정적 호출망은 INFERRED candidate이며 optional guard일 수 있습니다. SQL literal table은 CONFIRMED 참조, 동적 SQL·helper table은 UNKNOWN/INFERRED입니다.

## 관리자/사용자 구분
| audience | definitions |
| --- | --- |
| USER/PUBLIC | 352 |
| ADMIN | 264 |


## 전체 목록
CSV에 직접/전이 후보·외부 URL·Relay·등록 상태를 추가했습니다.
| method | path | function | file | line | purpose | auth | db_table | external_api | relay |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | / | index | app.py | 737 | index | UNKNOWN: no recognized static guard | INFERRED listing_requests;master_buildings | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /reset-password | reset_password_page | app.py | 742 | 이메일 비밀번호 재설정 페이지 — 토큰 검증은 API에서 수행한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /manifest.json | pwa_manifest | app.py | 748 | PWA 매니페스트 — 루트 경로로 서빙 (모든 페이지의 <link rel="manifest">가 참조). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /robots.txt | robots_txt | app.py | 754 | 정상 크롤러용 크롤링 규칙 — 관리자/API 경로는 크롤링 제외. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /favicon.ico | favicon_ico | app.py | 760 | 브라우저가 관성적으로 루트 /favicon.ico를 요청하는 경우 대응. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /vendor/chart.umd.js | chart_js_vendor | app.py | 766 | 원본 HTML 폴백에서도 투자분석 그래프 라이브러리를 로컬 제공한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /building/<int:building_id> | building_page | app.py | 780 | 건물 상세 — 별도 페이지가 아니라 홈화면(index.html)을 그대로 서빙한다. | UNKNOWN: no recognized static guard | INFERRED listing_requests;master_buildings | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /membership | membership_page | app.py | 792 | membership_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/building-photo/<int:building_id>/<source> | get_building_provider_photo | app.py | 1447 | 최근 TourAPI no_match 건물의 Street View fallback만 제한적으로 중계한다. | UNKNOWN: no recognized static guard | building_photo_fetches;master_buildings | https://maps.googleapis.com/maps/api/streetview;https://maps.googleapis.com/maps/api/streetview/metadata | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/photos | get_building_photos_on_demand | app.py | 1687 | 사진 캐시를 반환하고, 필요한 경우 브라우저 TourAPI 조회를 안내한다. | UNKNOWN: no recognized static guard | building_photo_fetches;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/building/<int:building_id>/photos/tourapi | save_tourapi_building_photos | app.py | 1780 | 브라우저의 TourAPI 조회 결과와 신뢰된 사진 URL을 서버 캐시에 저장한다. | UNKNOWN: no recognized static guard | building_photo_fetches;building_photos;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/building/<int:building_id>/photos/upload | upload_building_photo | app.py | 1946 | upload_building_photo | INFERRED guards: current_user | building_photos;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/building/<int:building_id>/photos/<int:photo_id> | delete_building_photo | app.py | 2059 | delete_building_photo | INFERRED guards: current_user | building_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building-photo-upload/<path:key> | building_photo_upload_proxy | app.py | 2115 | building_photo_upload_proxy | UNKNOWN: no recognized static guard | agents;building_photos;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id> | get_building | app.py | 2233 | 건물 상세페이지용 단건 조회 — master_buildings 기준. | UNKNOWN: no recognized static guard | agent_buildings;agent_service_regions;agents;booking_url_requests;building_photo_fetches;building_unit_areas;business_room_inventory;listing_likes;listing_photos;listing_requests;loan_consultant_buildings;loan_consultant_service_areas;loan_consultants;master_buildings;operator_buildings;operator_lodging;operator_service_regions;operators;page_views;tourism_stats;transactions | https://www.gocamping.or.kr/bsite/camp/info/read.do | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/area-types | get_building_area_types | app.py | 3195 | 전용면적 타입 목록 — 순수 DB 조회 (외부 API 없음, 빠름). | UNKNOWN: no recognized static guard | building_unit_areas;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/rental-market-price | get_rental_market_price | app.py | 3260 | 선택 건물·호실 면적의 최근 36개월 매매 실거래 중앙값. | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/rental-benchmark | get_rental_benchmark | app.py | 3451 | 선택 건물에 적용할 최신 R-ONE 임대수익·공실 기준값. | UNKNOWN: no recognized static guard | master_buildings;rone_rental_benchmarks | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/lodging-summary | get_building_lodging_summary | app.py | 3563 | 사업주 매물등록용 활성 숙박업 대표 신고 정보. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/unit-areas | get_building_unit_areas | app.py | 3604 | 전유부(호실별 전용면적) 온디맨드 조회 + DB 캐싱. | UNKNOWN: no recognized static guard | building_unit_areas;master_buildings | UNKNOWN / no URL literal reached | INFERRED helper reachable |
| GET | /api/building/<int:building_id>/nearby-stores | get_building_nearby_stores | app.py | 3825 | 이 건물(지번, PNU 기준)의 상가업소 목록 — 업종별 개수 + 층별 목록. | UNKNOWN: no recognized static guard | building_stores;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/transactions | get_transactions | app.py | 3979 | get_transactions | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/v1/m/6b4 | map_poi | app.py | 4187 | 현재 지도 중심 주변의 교육·편의시설을 Kakao Local에서 조회한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/buildings-cluster | get_buildings_cluster | app.py | 4427 | 행정구역 단위 클러스터 집계 — level=sido\|sgg\|umd. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/ranking | get_ranking | app.py | 4635 | 재방문 유인용 랭킹 — 이번 주 신고가 갱신 TOP5 + 거래량 TOP5. | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/buildings-geo | get_buildings_geo | app.py | 4804 | 지도 마커용 — 좌표(lat/lng)가 있는 마스터 건물. | UNKNOWN: no recognized static guard | listing_requests;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/monthly-trend | get_monthly_trend | app.py | 5085 | 실거래 추세 집계 (좌측 패널 '실거래추세' 콤보차트용). | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tx-count | get_tx_count | app.py | 5231 | 전체 실거래 건수 (실시간 COUNT — 관리자 대시보드 '누적 거래' KPI와 동일 기준). | UNKNOWN: no recognized static guard | transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building-count | get_building_count | app.py | 5245 | 전체 생숙 단지 수 + 용도별 분포 + 실거래 건수. | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/regions | get_regions | app.py | 5315 | 시도 > 시군구 > 읍면동 계층 트리 (계층 검색 드롭다운용). | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/years | get_years | app.py | 5359 | 실거래 연도 목록 (기간 필터 드롭다운용). | UNKNOWN: no recognized static guard | transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/favorites | get_favorites | app.py | 5380 | 관심단지 전용 조회 — /api/transactions의 size 상한(200)과 무관하게 | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/submit-building | submit_building | app.py | 5502 | 사용자가 "내 건물이 목록에 없다"며 도로명주소를 제출하면: | UNKNOWN: no recognized static guard | building_requests;master_buildings | UNKNOWN / no URL literal reached | INFERRED helper reachable |
| GET | /apply/agent | apply_agent_page | app.py | 5807 | 중개사 회원신청(C화면) 정적 폼 HTML 서빙. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/agent/upload | apply_agent_upload | app.py | 5861 | 중개사 신청 서류 업로드 (비로그인, IP 기준 rate limit). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/operator/upload | apply_operator_upload | app.py | 5874 | 운영업체 신청 서류 업로드 (비로그인, IP 기준 rate limit). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/lodging-operator/upload | apply_lodging_operator_upload | app.py | 5887 | Optional business/permit evidence for an unauthenticated lodging application. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/agent | apply_agent | app.py | 6092 | 중개사 회원신청 접수 API. | UNKNOWN: no recognized static guard | applications;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /apply/operator | apply_operator_page | app.py | 6210 | 운영업체 등록신청(D화면) 정적 폼 HTML 서빙. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /apply/lodging-operator | apply_lodging_operator_page | app.py | 6226 | 영업신고 대표자용 숙박 운영 파트너 신청서. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /lodging-operator/manage | lodging_operator_manage_page | app.py | 6232 | lodging_operator_manage_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/buildings/<int:building_id>/brief | lodging_operator_building_brief | app.py | 6382 | Minimal selected-building data; no registry/permit data is disclosed. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/apply/lodging-operator/buildings/<int:building_id>/brief | lodging_operator_building_brief | app.py | 6382 | Minimal selected-building data; no registry/permit data is disclosed. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/lodging-operator/permit-check | lodging_operator_permit_check | app.py | 6398 | Exact permit + selected building lookup used solely for fast-review eligibility. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/lodging-operator/phone-challenge | lodging_operator_phone_challenge | app.py | 6421 | Unauthenticated, throttled SMS challenge. OTP is never persisted in plaintext. | UNKNOWN: no recognized static guard | lodging_operator_phone_challenges | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/lodging-operator/phone-challenge/<challenge_id>/verify | lodging_operator_phone_challenge_verify | app.py | 6463 | lodging_operator_phone_challenge_verify | UNKNOWN: no recognized static guard | lodging_operator_phone_challenges | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/partner/lodging-operator-stats | partner_lodging_operator_stats | app.py | 6491 | 파트너 카드 수치를 공개 전국숙박업통계와 같은 행·필드에서 가져온다. | UNKNOWN: no recognized static guard | INFERRED agent_buildings;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/lodging-operator | apply_lodging_operator | app.py | 6541 | apply_lodging_operator | UNKNOWN: no recognized static guard | applications;lodging_operator_phone_challenges;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/lodging-operator/me | lodging_operator_me | app.py | 6720 | 승인된 신고 대표자는 자신의 공개 소개와 링크만 수정할 수 있다. | INFERRED guards: current_user | lodging_registry;operator_lodging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/lodging-operator/me | lodging_operator_me | app.py | 6720 | 승인된 신고 대표자는 자신의 공개 소개와 링크만 수정할 수 있다. | INFERRED guards: current_user | lodging_registry;operator_lodging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/lodging-operator/photo | lodging_operator_photo | app.py | 6820 | 승인 대표자 본인만 공개 카드 사진을 올리거나 지운다. | INFERRED guards: current_user | operator_lodging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/lodging-operator/photo | lodging_operator_photo | app.py | 6820 | 승인 대표자 본인만 공개 카드 사진을 올리거나 지운다. | INFERRED guards: current_user | operator_lodging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/lodging-operator/photo/<int:op_id> | lodging_operator_photo_proxy | app.py | 6852 | 승인 공개 레코드에 연결된 키만 이미지로 제공한다. | UNKNOWN: no recognized static guard | operator_lodging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/lodging-operator/photos | lodging_operator_gallery | app.py | 6883 | Private operator gallery management; each image stays bound to its owner record. | INFERRED guards: current_user | operator_lodging;operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/lodging-operator/photos | lodging_operator_gallery | app.py | 6883 | Private operator gallery management; each image stays bound to its owner record. | INFERRED guards: current_user | operator_lodging;operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/lodging-operator/photos/<int:photo_id> | lodging_operator_gallery_delete | app.py | 6936 | lodging_operator_gallery_delete | INFERRED guards: current_user | operator_lodging;operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/lodging-operator/photos/<int:photo_id> | lodging_operator_gallery_delete | app.py | 6936 | lodging_operator_gallery_delete | INFERRED guards: current_user | operator_lodging;operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/lodging-operator/photos/reorder | lodging_operator_gallery_reorder | app.py | 6982 | lodging_operator_gallery_reorder | INFERRED guards: current_user | operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/lodging-operator/photos/<int:photo_id>/primary | lodging_operator_gallery_primary | app.py | 7004 | lodging_operator_gallery_primary | INFERRED guards: current_user | operator_lodging;operator_lodging_photos | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/operator | apply_operator | app.py | 7025 | 운영업체 등록신청 접수 API. | UNKNOWN: no recognized static guard | applications;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /apply/loan | apply_loan_page | app.py | 7139 | 대출상담사 등록신청 정적 폼 HTML 서빙 (apply_agent_page()와 동일 패턴). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/buildings/search | public_building_search | app.py | 7152 | 공개 건물명 검색 — 신청서(중개사/운영업체) 희망건물 자동완성용. 로그인 불필요. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/apply/loan | apply_loan | app.py | 7200 | 대출상담사 등록신청 접수 API. | UNKNOWN: no recognized static guard | applications;loan_consultants;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /api/applications/token/<token> | get_application_by_token | app.py | 7344 | get_application_by_token | UNKNOWN: no recognized static guard | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/applications/token/<token> | update_application_by_token | app.py | 7457 | update_application_by_token | UNKNOWN: no recognized static guard | applications;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/applications/token/<token> | cancel_application_by_token | app.py | 7516 | cancel_application_by_token | UNKNOWN: no recognized static guard | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /apply/edit/<token> | apply_edit_page | app.py | 7538 | 신청 내용 수정·취소 페이지(D화면 변형) — 접수 이메일의 링크로만 진입. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultants | loan_consultants_list | app.py | 7553 | 승인된 대출상담사 공개 목록 — B화면 '금융' 카드에서 사용. | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultants/all | loan_consultants_list_all | app.py | 7578 | 승인된 대출상담사 전체 공개 목록 — /loan-consultants 전체 목록 페이지에서 사용. | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /loan-consultants | loan_consultants_list_page | app.py | 7597 | 전체 대출상담사 목록 페이지 (공개). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /partners-directory | partners_directory_page | app.py | 7605 | 파트너 소개 게시판 (공개) — 로고 없이 텍스트/표 기반 (상표권 이슈 회피). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/partners/directory | partners_directory_api | app.py | 7611 | 승인 + 노출중(approved & is_visible) 파트너 전체 목록 — /partners-directory 게시판용. | UNKNOWN: no recognized static guard | agent_buildings;agents;applications;loan_consultants;master_buildings;operator_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/partners/operators | partners_operators_list | app.py | 7716 | 로고가 등록된 승인 운영지원업체 공개 목록 — /partner '등록된 파트너' 섹션용. | UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/partners/operator-logo/<int:operator_id> | partners_operator_logo | app.py | 7742 | 승인 업체 로고 이미지 공개 프록시 — 승인 + 로고 보유 업체만 서빙 (팝업 이미지 프록시와 동일 패턴). | UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/partners/loan-consultant-logo/<int:lc_id> | partners_loan_consultant_logo | app.py | 7768 | 승인 대출상담사 로고/아바타 공개 프록시 — 운영업체 로고 프록시와 동일 패턴. | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/partners/agent-photo/<int:agent_id> | partners_agent_photo | app.py | 7796 | 승인 중개사 프로필 사진 공개 프록시 — 운영업체 로고 프록시와 동일 패턴. | UNKNOWN: no recognized static guard | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/request-correction | request_correction | app.py | 7820 | 이미 목록에 있는 건물의 용도 라벨이 잘못됐다고 생각될 때 정정을 요청하는 API. | UNKNOWN: no recognized static guard | building_requests;master_buildings;transactions | UNKNOWN / no URL literal reached | INFERRED helper reachable |
| GET | /api/admin/action-center | admin_action_center | app.py | 8027 | Live, privacy-minimised queue used by the approved admin action centre. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED applications;booking_url_requests;bug_reports;building_requests;buy_requests;listing_requests;master_buildings;operators;presale_applications;streetview_evaluation_metrics;survey_requests;sync_log;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/notification-subscriptions | admin_notification_subscriptions | app.py | 8053 | 수신 대상 관리자와 채널을 한 화면에서 관리한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_event_subscriptions;admin_users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/notification-subscriptions | admin_notification_subscriptions | app.py | 8053 | 수신 대상 관리자와 채널을 한 화면에서 관리한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_event_subscriptions;admin_users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/notifications | admin_notifications | app.py | 8108 | admin_notifications | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/notifications/unread-count | admin_notifications_unread_count | app.py | 8123 | admin_notifications_unread_count | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/notifications/<int:notification_id>/read | admin_notification_read | app.py | 8136 | admin_notification_read | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/notification-email-attempts | admin_notification_email_attempts | app.py | 8152 | admin_notification_email_attempts | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_notification_email_attempt_history;admin_notification_email_attempts;admin_notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /guide | guide_page | app.py | 8271 | 이용안내 페이지 — 로그인 여부 무관 항상 접근 가능. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /analysis | analysis_page | app.py | 8277 | 관광수요·실거래 비교 화면. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /notices | notices_page | app.py | 8283 | 공지사항 페이지 (현재는 정적 안내만). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /menu | menu_page | app.py | 8289 | 모바일 전용 전체 메뉴 페이지 (햄버거 버튼에서 진입). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /mypage | mypage_page | app.py | 8295 | 마이페이지 — 로그인 여부는 /api/auth/me로 클라이언트에서 판단한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /unsubscribe | unsubscribe_weekly_email | app.py | 8301 | 원클릭 수신거부 — 이메일 링크의 토큰만으로 로그인 없이 처리. | UNKNOWN: no recognized static guard | users | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /email/open | weekly_email_open | app.py | 8372 | 1x1 open marker. Opens are approximate because mailbox proxies may fetch it. | UNKNOWN: no recognized static guard | weekly_email_deliveries | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /email/pixel | weekly_email_open | app.py | 8372 | 1x1 open marker. Opens are approximate because mailbox proxies may fetch it. | UNKNOWN: no recognized static guard | weekly_email_deliveries | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/email/open | weekly_email_open | app.py | 8372 | 1x1 open marker. Opens are approximate because mailbox proxies may fetch it. | UNKNOWN: no recognized static guard | weekly_email_deliveries | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /email/click | weekly_email_click | app.py | 8411 | Same-site click redirect; absolute URLs and protocol-relative URLs are rejected. | UNKNOWN: no recognized static guard | weekly_email_deliveries | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/email/click | weekly_email_click | app.py | 8411 | Same-site click redirect; absolute URLs and protocol-relative URLs are rejected. | UNKNOWN: no recognized static guard | weekly_email_deliveries | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /transactions | transactions_page | app.py | 8444 | 실거래목록 전용 페이지 (검색 필터 + 게시판, /api/transactions 재사용). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /terms | terms_page | app.py | 8450 | 이용약관 페이지 (정적). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /partner | partner_page | app.py | 8456 | 파트너(중개사·운영업체) 등록 안내 페이지. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /agents | agents_landing_page | app.py | 8462 | 담당중개사 아웃바운드/소개용 랜딩 페이지 (?company=업체명 개인화). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /operators | operators_landing_page | app.py | 8468 | 위탁운영업체 이메일 아웃바운드용 랜딩 페이지 (?company=업체명 개인화). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /loan-partners | loan_partners_landing_page | app.py | 8474 | 대출상담사(금융 파트너) 아웃바운드용 랜딩 페이지 (?company=업체명 개인화). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /privacy | privacy_page | app.py | 8480 | 개인정보처리방침 페이지 — 뼈대는 정적, 본문은 /api/legal/privacy에서 로드. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /listings | listings_page | app.py | 8486 | 직거래 공개 매물 목록 페이지. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /apply/presale | apply_presale_page | app.py | 8492 | 분양사·시행사 담당자를 위한 분양 정보 등록 안내 화면. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/legal/<doc_type> | public_legal_get | app.py | 8503 | 공개 조회 — 인증 불필요. /terms, /privacy 페이지가 본문을 채울 때 사용. | UNKNOWN: no recognized static guard | legal_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/legal/<doc_type> | admin_legal_get | app.py | 8527 | 관리자 조회 — 현재 저장된 본문 반환. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | legal_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/legal/<doc_type> | admin_legal_update | app.py | 8551 | 관리자 저장 — content 통째로 교체. 없으면 새로 만든다(upsert). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | legal_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/policies | admin_policy_list | app.py | 8634 | admin_policy_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | policy_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/policies/<int:policy_id> | admin_policy_get | app.py | 8658 | admin_policy_get | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | policy_document_revisions;policy_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/policies | admin_policy_create | app.py | 8676 | admin_policy_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | policy_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/policies/<int:policy_id> | admin_policy_update | app.py | 8710 | admin_policy_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | policy_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/policies/<int:policy_id>/<action> | admin_policy_action | app.py | 8738 | admin_policy_action | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | policy_documents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auth/contexts | auth_contexts | app.py | 9072 | 현재 users 계정에 연결된 역할·사업장 목록. | INFERRED guards: _get_account_contexts;current_user | INFERRED account_business_memberships;account_role_memberships;agents;loan_consultants;operator_lodging;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/context | auth_switch_context | app.py | 9087 | 명시적으로 역할 또는 사업장을 전환한다. 소유권은 DB 멤버십으로 확인한다. | INFERRED guards: _get_account_contexts;current_user | account_business_memberships;account_role_memberships;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/auth/context | auth_switch_context | app.py | 9087 | 명시적으로 역할 또는 사업장을 전환한다. 소유권은 DB 멤버십으로 확인한다. | INFERRED guards: _get_account_contexts;current_user | account_business_memberships;account_role_memberships;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/link-legacy-role | auth_link_legacy_role | app.py | 9163 | 현재 계정과 같은 이메일의 기존 사업자 로그인을 양쪽 비밀번호로 연결한다. | INFERRED guards: current_user | account_business_memberships;account_role_memberships | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/reauthenticate | auth_reauthenticate | app.py | 9249 | auth_reauthenticate | INFERRED guards: current_user | INFERRED users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/request-password-reset | auth_request_password_reset | app.py | 9262 | 모든 회원 유형의 이메일 비밀번호 재설정 링크 요청. | UNKNOWN: no recognized static guard | agents;loan_consultants;operators;password_reset_tokens;users | https://homenstay.com | UNKNOWN / not statically reached |
| POST | /api/auth/reset-password | auth_reset_password | app.py | 9361 | 재설정 토큰으로 모든 회원 유형의 비밀번호를 원자적으로 변경한다. | UNKNOWN: no recognized static guard | agents;loan_consultants;operators;password_reset_tokens;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/signup | auth_signup | app.py | 9455 | 이메일 회원가입 → 성공 시 자동 로그인. | UNKNOWN: no recognized static guard | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/login | auth_login | app.py | 9607 | 이메일/비밀번호 로그인 — 일반회원 → 중개사 → 운영업체 → 대출상담사 순으로 | INFERRED guards: _get_account_contexts | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/logout | auth_logout | app.py | 9659 | 로그아웃 — 일반회원·사업자 3종 세션 키를 모두 제거한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auth/me | auth_me | app.py | 9674 | 로그인 상태 조회. 프런트 헤더가 로그인/로그아웃 표시를 결정하는 데 쓴다. | INFERRED guards: _get_account_contexts;current_user | INFERRED account_business_memberships;account_role_memberships;agents;loan_consultants;operator_lodging;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/auth/me | auth_update_name | app.py | 9746 | 이름 변경 및 재인증된 이메일 변경 — users 계정 단위로 저장한다. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/auth/email-alert | auth_update_email_alert | app.py | 9799 | 실거래 이메일 알림 수신 여부 변경 — 로그인 필요. 인앱 알림에는 영향 없음. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/auth/weekly-email | auth_update_weekly_email | app.py | 9822 | 주간 소식 이메일 수신 동의 변경 — 로그인 필요. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/send-phone-code | auth_send_phone_code | app.py | 9848 | SMS 인증번호 발송 — 로그인 필요. 6자리 OTP, 3분 유효. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auth/verify-phone-code | auth_verify_phone_code | app.py | 9892 | 인증번호 확인 — 성공 시 users.phone + phone_verified 업데이트. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/auth/password | auth_change_password | app.py | 9930 | 비밀번호 변경 — 로그인 필요, 이메일 계정만. 현재 비밀번호 확인 후 교체. | INFERRED guards: current_user | users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/auth/me | auth_withdraw | app.py | 9963 | 회원탈퇴 — 로그인 필요. 완전삭제 대신 status='withdrawn' 소프트삭제 후 세션 초기화. | INFERRED guards: current_user | account_business_memberships;account_role_memberships;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /auth/kakao/start | kakao_start | app.py | 10018 | 카카오 인증 페이지로 리다이렉트. CSRF 방지용 state를 세션에 저장한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://{host}/auth/kakao/callback | UNKNOWN / not statically reached |
| GET | /auth/kakao/callback | kakao_callback | app.py | 10035 | 카카오 콜백: code→token→사용자정보→users upsert→세션 저장→홈으로. | UNKNOWN: no recognized static guard | users | https://{host}/auth/kakao/callback | UNKNOWN / not statically reached |
| GET | /api/favorites/mine | favorites_mine | app.py | 10151 | 로그인 회원의 관심단지 목록 + 각 단지의 최신 실거래가 + 건물상세 링크용 building_id. | INFERRED guards: current_user | master_buildings;transactions;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/favorites/mine | favorites_mine_add | app.py | 10283 | 관심단지 1건 저장 — 이미 있으면 무시(중복 스킵). | INFERRED guards: current_user | master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/favorites/mine | favorites_mine_remove | app.py | 10394 | 관심단지 1건 삭제. | INFERRED guards: current_user | user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/favorites/mine/urgent-alert | favorites_mine_urgent_alert | app.py | 10420 | 관심단지와 별도로 급매 알림을 켜거나 끈다. | INFERRED guards: current_user | master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/favorites/mine/urgent-alert | favorites_mine_urgent_alert | app.py | 10420 | 관심단지와 별도로 급매 알림을 켜거나 끈다. | INFERRED guards: current_user | master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/favorites/mine/signal-alert | favorites_mine_signal_alert | app.py | 10479 | 숙박알리미 통합 토글 — 실거래·급매·신규매물·신고변동을 함께 관리한다. | INFERRED guards: current_user | master_buildings;user_alert_subscriptions;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/favorites/mine/signal-alert | favorites_mine_signal_alert | app.py | 10479 | 숙박알리미 통합 토글 — 실거래·급매·신규매물·신고변동을 함께 관리한다. | INFERRED guards: current_user | master_buildings;user_alert_subscriptions;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/favorites/migrate | favorites_migrate | app.py | 10571 | 로그인 직후 1회 호출용. localStorage favKey 배열을 받아 없는 것만 채우고, | INFERRED guards: current_user | user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/alerts/mine | alerts_mine | app.py | 10644 | 실거래 알림을 받는 관심단지와 독립 구독 목록. | INFERRED guards: current_user | master_buildings;transactions;user_alert_subscriptions;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/alerts/mine | alerts_mine_add | app.py | 10705 | 실거래 알림 구독 1건 추가 — 이미 있으면 무시(중복 스킵). | INFERRED guards: current_user | user_alert_subscriptions;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/alerts/mine | alerts_mine_remove | app.py | 10737 | 실거래 알림 구독 1건 삭제. | INFERRED guards: current_user | user_alert_subscriptions;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/alerts/migrate | alerts_migrate | app.py | 10768 | 로그인 직후 1회 호출용. localStorage 알림구독(favKey 배열)을 서버로 이관하고, | INFERRED guards: current_user | user_alert_subscriptions;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/notifications/mine | notifications_mine | app.py | 10821 | 최근 알림 목록 — 안읽음 우선, 최신순, 최대 30개. 클릭 이동용 building_id 포함. | INFERRED guards: current_user | app_meta;listing_requests;master_buildings;notifications;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/notifications/unread-count | notifications_unread_count | app.py | 10863 | 헤더 벨 뱃지용 안 읽은 알림 개수. | INFERRED guards: current_user | notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/notifications/mine/read-all | notifications_read_all | app.py | 10883 | 전체 읽음 처리. | INFERRED guards: current_user | notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/notifications/mine/read | notifications_read_one | app.py | 10903 | 알림 1건 읽음 처리 — 항목 클릭 시 사용. | INFERRED guards: current_user | notifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /admin/login | admin_login_page | app.py | 10930 | admin_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| POST | /api/admin/login | admin_login | app.py | 10936 | admin_users 테이블 기반 이메일/비밀번호 로그인. | UNKNOWN: no recognized static guard | admin_users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/logout | admin_logout | app.py | 10969 | admin_logout | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/password | admin_change_password | app.py | 10977 | 관리자 비밀번호 변경 — 로그인 필요. 현재 비밀번호 확인 후 새 비밀번호로 교체. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /agent/login | agent_login_page | app.py | 11085 | agent_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /agent/<slug> | agent_profile_page | app.py | 11090 | 중개사 공개 프로필 페이지. Flask는 정적 룰(/agent/login)을 우선 매칭하므로 충돌 없음. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/agent/profile/<slug> | agent_public_profile | app.py | 11096 | 중개사 공개 프로필 API — 인증 불필요. approved 상태만 노출. | UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agent_service_regions;agents;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/login | agent_login | app.py | 11169 | Broker entry uses the same users credential and approved linked office. | INFERRED guards: _get_account_contexts | INFERRED account_business_memberships;account_role_memberships;agents;loan_consultants;login_history;operator_lodging;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/logout | agent_logout | app.py | 11176 | agent_logout | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/password | agent_change_password | app.py | 11187 | 중개사 비밀번호 변경 — 현재 비밀번호 확인 후 교체 (admin/mypage와 같은 패턴). | CONFIRMED decorator: require_agent; INFERRED guards: current_user | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /agent/dashboard | agent_dashboard_page | app.py | 11220 | agent_dashboard_page | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /admin/preview/agent/<int:agent_id> | admin_preview_agent_page | app.py | 11226 | admin_preview_agent_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/admin/preview/agent/<int:agent_id> | admin_preview_agent_me | app.py | 11232 | admin_preview_agent_me | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;agents;master_buildings;premium_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/preview/agent/<int:agent_id>/leads | admin_preview_agent_leads | app.py | 11241 | admin_preview_agent_leads | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /admin/preview/operator/<int:operator_id> | admin_preview_operator_page | app.py | 11248 | admin_preview_operator_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/admin/preview/operator/<int:operator_id> | admin_preview_operator_profile | app.py | 11254 | 관리자 전용 operator 프로필 조회 — 승인/노출 여부 무관. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;operator_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /admin/preview/loan_consultant/<int:lc_id> | admin_preview_lc_page | app.py | 11296 | admin_preview_lc_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/admin/preview/loan_consultant/<int:lc_id> | admin_preview_lc_profile | app.py | 11302 | 관리자 전용 loan_consultant 프로필 조회 — 승인/노출 여부 무관. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | loan_consultant_buildings;loan_consultants;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/me | agent_me | app.py | 11434 | agent_me | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED agent_buildings;agents;master_buildings;premium_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/photo | agent_photo_upload | app.py | 11443 | 마이페이지에서 프로필 사진 업로드/교체 — 신청서 업로드와 동일한 검증. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/me | agent_me_update | app.py | 11518 | 부분 업데이트 — 전달된 키만 수정. 등록번호류 변경 시 재승인 대기 전환. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/visibility | agent_visibility_update | app.py | 11576 | 노출 여부 토글 — 본인 세션 기준. is_visible만 갱신 (status와 무관). | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /s/<code> | short_link_redirect | app.py | 11709 | 유효한 단축 링크는 인증된 내부 화면으로, 나머지는 홈페이지로 보낸다. | UNKNOWN: no recognized static guard | short_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/buildings | agent_building_add | app.py | 12133 | agent_building_add | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agents;master_buildings;premium_waitlist | https://homenstay.com | UNKNOWN / not statically reached |
| POST | /api/agent/buildings/<int:mbid>/claim-premium | agent_building_claim_premium | app.py | 12289 | 구버전 대시보드 호환용: 신규 전속단지는 등록 시 이미 단지뱃지가 부여된다. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agents;master_buildings;premium_waitlist | https://homenstay.com | UNKNOWN / not statically reached |
| POST | /api/agent/service-regions | agent_service_region_claim | app.py | 12392 | 시군구 단위 지역뱃지를 등록하고, 정원이 찼으면 대기 명단에 넣는다. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_service_regions;agents;master_buildings;region_badge_waitlist | https://homenstay.com | UNKNOWN / not statically reached |
| DELETE | /api/agent/service-regions | agent_service_region_delete | app.py | 12509 | 담당 지역 삭제 — 그 지역의 담당단지도 함께 전부 삭제된다. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_region_buildings;agent_service_regions;region_badge_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/region-buildings/search | agent_region_building_search | app.py | 12528 | 담당지역 내 단지 검색 — 본인이 등록한 시군구 안의 건물만, | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agent_service_regions;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/region-buildings | agent_region_building_add | app.py | 12573 | 담당지역 내 담당단지 추가 — 지역당(=중개사당) 최대 10개. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agent_service_regions;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/agent/region-buildings/<int:mbid> | agent_region_building_remove | app.py | 12622 | agent_region_building_remove | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_region_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/sgg-options | agent_sgg_options | app.py | 12636 | 지역뱃지에서 선택할 수 있는 실제 시군구 목록. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/buildings/<int:mbid>/notify-me | agent_building_notify_me | app.py | 12653 | 단지부동산 대기 알림 등록 — 해당 단지에 다른 부동산이 입점해 있을 때 | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agents;master_buildings;premium_waitlist | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /api/agent/tier-status | agent_tier_status | app.py | 12724 | 대시보드에서 버튼 상태(신청가능/적용중/만료) 판단용. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agent_service_regions;master_buildings;region_badge_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/agent/buildings/<int:mbid> | agent_building_delete | app.py | 12777 | agent_building_delete | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;premium_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/buildings/<int:mbid>/counts | agent_building_counts | app.py | 12803 | agent_building_counts | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/buildings/search | agent_building_search | app.py | 12833 | 단지관리 모달용 건물명 검색 — 이미 등록된 건물은 already_added 표시. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;master_buildings;premium_waitlist | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/leads | agent_leads | app.py | 12912 | 나에게 배정된 매물의뢰 목록 — routed_agent_id = 내 agent_id. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED agent_buildings;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/leads/<int:lead_id>/status | agent_lead_update_status | app.py | 12931 | 내게 배정된 매물의뢰의 상태를 신규·처리중·완료 중 하나로 수정한다. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | agent_buildings;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/buy-requests | agent_buy_requests | app.py | 13020 | 나에게 배정된 매수의뢰 목록 — routed_agent_id = 내 agent_id. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED agent_buildings;buy_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/buy-requests/<int:req_id>/status | agent_buy_request_update_status | app.py | 13027 | 내게 배정된 매수의뢰의 상태 변경 — submitted → in_progress → done 순방향만. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | buy_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/preview/agent/<int:agent_id>/buy-requests | admin_preview_agent_buy_requests | app.py | 13065 | admin_preview_agent_buy_requests | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;buy_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/whole-listing-context | whole_listing_context | app.py | 13396 | 건물전체 매물 폼에 필요한 건물·경쟁시설·지하철 입지 정보. | UNKNOWN: no recognized static guard | INFERRED lodging_registry;master_buildings;subway_stations | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/whole-listing-contexts | whole_listing_contexts | app.py | 13412 | 공개 매물 목록용 다건 입지 컨텍스트. 한 화면당 한 요청만 허용한다. | UNKNOWN: no recognized static guard | INFERRED lodging_registry;master_buildings;subway_stations | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consult-requests | create_loan_consult_request | app.py | 13510 | create_loan_consult_request | INFERRED guards: current_user | loan_consult_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator-consult-requests | create_operator_consult_request | app.py | 13544 | create_operator_consult_request | INFERRED guards: current_user | master_buildings;operator_consult_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/business-verification | get_business_verification | app.py | 13579 | 현재 사용자·건물의 사업주 영업신고번호 인증 상태를 반환한다. | INFERRED guards: current_user | INFERRED business_building_verifications;lodging_registry;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/building/<int:building_id>/business-verification | verify_business_building | app.py | 13598 | 대표 영업신고번호를 확인하고 사용자·건물별 인증 캐시를 저장한다. | INFERRED guards: current_user | business_building_verifications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listing-requests/<int:lr_id>/checklist | public_listing_checklist | app.py | 14332 | 건물전체 공개매물의 체크리스트 데이터와 로그인 회원 진행 상태. | INFERRED guards: current_user | listing_checklist_progress | https://www.gov.kr/portal/main/nologin;https://www.iros.go.kr/;https://www.nfa.go.kr/ | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:lr_id>/checklist/progress | save_listing_checklist_progress | app.py | 14356 | 로그인 회원의 체크리스트 항목 상태를 항목 단위로 저장한다. | INFERRED guards: current_user | listing_checklist_progress | https://www.gov.kr/portal/main/nologin;https://www.iros.go.kr/;https://www.nfa.go.kr/ | UNKNOWN / not statically reached |
| POST | /api/listing-requests | create_listing_request | app.py | 14394 | create_listing_request | INFERRED guards: current_user | listing_request_history;listing_requests;master_buildings;users | https://homenstay.com | UNKNOWN / not statically reached |
| POST | /api/buy-requests | create_buy_request | app.py | 14744 | 매수의뢰 접수 + 중개사 라우팅 — listing_requests와 동일 라우팅 로직. | INFERRED guards: current_user | buy_requests;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /api/buy-requests/mine | my_buy_requests | app.py | 14837 | 내가 접수한 매수의뢰 목록 — 마이페이지용. | INFERRED guards: current_user | agents;buy_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/buy-requests/<int:req_id> | withdraw_buy_request | app.py | 14864 | 본인이 접수한 매수의뢰를 철회 상태로 전환한다. | INFERRED guards: current_user | buy_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listing-requests/mine | my_listing_requests | app.py | 14894 | 내가 접수한 매물의뢰 목록 — 마이페이지 '매물의뢰 현황'용 (건물명/거래유형/상태). | INFERRED guards: current_user | agents;chat_rooms;listing_photos;listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/my/listing-requests/<int:lr_id>/rooms | my_room_inventory | app.py | 15019 | 내 매물의뢰에 연결된 방 재고 목록. | INFERRED guards: current_user | business_room_inventory | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/my/listing-requests/<int:lr_id>/rooms | create_my_room_inventory | app.py | 15045 | 내 매물의뢰에 방 재고 한 건을 추가한다. | INFERRED guards: current_user | business_room_inventory | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/my/listing-requests/<int:lr_id>/rooms/bulk | create_my_room_inventory_bulk | app.py | 15113 | 한 층의 방을 자동 호수로 묶어 추가한다. 기존 호수는 건너뛴다. | INFERRED guards: current_user | business_room_inventory | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/my/room-inventory/<int:room_id> | update_my_room_inventory | app.py | 15172 | 내 방 재고의 호실·월세·입실 상태·계약만기일을 저장한다. | INFERRED guards: current_user | business_room_inventory;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/my/listing-requests/<int:lr_id>/chat-rooms | my_listing_request_chat_rooms | app.py | 15277 | 내가 등록한 직거래 매물에 온 채팅방 목록 — 판매자(등록자) 전용. | INFERRED guards: current_user | chat_messages;chat_rooms;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listings | public_listings | app.py | 15316 | 직거래 공개 매물 목록 — 인증 불필요. deal_mode='direct' + withdrawn 아닌 것. | INFERRED guards: current_user | account_business_memberships;agents;building_photo_fetches;building_photos;business_room_inventory;listing_likes;listing_photos;listing_requests;master_buildings;page_views;transactions;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listings/views | record_listing_views | app.py | 15610 | record_listing_views | UNKNOWN: no recognized static guard | listing_requests;page_views | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listings/views | record_listing_views | app.py | 15610 | record_listing_views | UNKNOWN: no recognized static guard | listing_requests;page_views | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/my-listing-ids | my_listing_ids | app.py | 15708 | 로그인 사용자가 참여 중인 채팅방의 listing_request_id 목록. | UNKNOWN: no recognized static guard | chat_rooms;listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:lr_id>/photos | upload_listing_photo | app.py | 15813 | 직거래 매물 사진 업로드 — 등록자 권한·이미지 품질·EXIF GPS 검증을 수행한다. | INFERRED guards: current_user | agents;listing_photos;listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/listing-requests/<int:lr_id>/photos/order | reorder_listing_photos | app.py | 15931 | 매물 등록자가 사진의 표시 순서를 저장한다. 첫 번째 사진이 대표사진이다. | INFERRED guards: current_user | agents;listing_photos;listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/listing-requests/<int:lr_id>/photos/<int:photo_id> | delete_listing_photo | app.py | 16032 | 매물 등록자만 기존 사진을 삭제한다. DB와 Object Storage를 함께 정리한다. | INFERRED guards: current_user | listing_photos;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listing-photos/img/<path:key> | listing_photo_proxy | app.py | 16069 | listing_photo_proxy | INFERRED guards: current_user | listing_photos;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:lr_id>/like | toggle_listing_like | app.py | 16115 | toggle_listing_like | INFERRED guards: current_user | listing_likes;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/chat/rooms | create_chat_room | app.py | 16158 | create_chat_room | INFERRED guards: current_user | chat_rooms;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/rooms/<int:room_id>/messages | get_chat_messages | app.py | 16217 | 채팅 메시지 조회 — 채팅방 참여자(buyer/seller)만 접근 가능. | INFERRED guards: current_user | chat_messages;chat_rooms;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/unread-count | chat_unread_count | app.py | 16274 | 헤더 벨 배지용 — 현재 사용자에게 온 안 읽은 채팅 메시지 수. | INFERRED guards: current_user | chat_messages;chat_rooms | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/recent-unread | chat_recent_unread | app.py | 16296 | 헤더 알림 드롭다운용 — 안 읽은 채팅을 채팅방별 최신 1건씩 최대 10개 반환. | INFERRED guards: current_user | chat_messages;chat_rooms;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/rooms | list_chat_rooms | app.py | 16352 | 채팅목록 모달용 — 내가 참여한 모든 채팅방을 최신 메시지순으로 반환. | INFERRED guards: current_user | chat_messages;chat_rooms;listing_photos;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/chat/rooms/<int:room_id>/attachments | upload_chat_attachment | app.py | 16441 | 채팅 첨부파일 업로드 — 채팅방 참여자만, jpg/jpeg/png/pdf 5MB 이하. | INFERRED guards: current_user | chat_rooms | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/chat/attachments/<path:key> | chat_attachment_proxy | app.py | 16476 | 채팅 첨부파일 다운로드 프록시 — 로그인한 사용자만. | INFERRED guards: current_user | INFERRED users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/chat/rooms/<int:room_id>/messages | send_chat_message | app.py | 16492 | 메시지 전송 — 채팅방 참여자만. | INFERRED guards: current_user | chat_messages;chat_rooms | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/listing-requests/<int:req_id> | update_listing_request | app.py | 16527 | 매물의뢰 수정 — 접수됨 또는 보류 상태인 본인 의뢰만 수정 가능. | INFERRED guards: current_user | building_photos;listing_photos;listing_request_history;listing_requests;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:req_id>/withdraw | withdraw_listing_request | app.py | 16803 | 매물의뢰 철회 — 원본·배정·채팅·이력은 보존하고 최종 상태로 전환한다. | INFERRED guards: current_user | listing_request_history;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:req_id>/hold | hold_listing_request | app.py | 16889 | hold_listing_request | INFERRED guards: current_user | INFERRED account_business_memberships;agents;listing_request_history;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:req_id>/resume | resume_listing_request | app.py | 16895 | resume_listing_request | INFERRED guards: current_user | INFERRED account_business_memberships;agents;listing_request_history;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/listing-requests/<int:req_id>/unhold | resume_listing_request | app.py | 16895 | resume_listing_request | INFERRED guards: current_user | INFERRED account_business_memberships;agents;listing_request_history;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PATCH | /api/listing-requests/<int:req_id>/disclosure-scope | update_listing_disclosure_scope | app.py | 16900 | 본인 매물의 공개범위만 즉시 변경한다. | INFERRED guards: current_user | building_photos;listing_photos;listing_request_history;listing_requests;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| PUT | /api/listing-requests/<int:req_id>/disclosure-scope | update_listing_disclosure_scope | app.py | 16900 | 본인 매물의 공개범위만 즉시 변경한다. | INFERRED guards: current_user | building_photos;listing_photos;listing_request_history;listing_requests;master_buildings | https://homenstay.com | UNKNOWN / not statically reached |
| GET | /api/listing-requests/<int:req_id>/history | listing_request_history_api | app.py | 16988 | 매물의뢰 이력 조회 — 본인 것만. | INFERRED guards: current_user | listing_request_history;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /operator/login | operator_login_page | app.py | 17038 | operator_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /partner/login | partner_login_page | app.py | 17043 | partner_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /lodging-operator/login | partner_login_page | app.py | 17043 | partner_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| POST | /api/operator/login | operator_login | app.py | 17049 | operator_login | INFERRED guards: _get_account_contexts | INFERRED account_business_memberships;account_role_memberships;agents;loan_consultants;login_history;operator_lodging;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/logout | operator_logout | app.py | 17055 | operator_logout | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/password | operator_change_password | app.py | 17062 | 운영업체 비밀번호 변경 — 현재 비밀번호 확인 후 교체 (agent와 같은 패턴). | CONFIRMED decorator: require_operator; INFERRED guards: current_user | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /operator/<slug> | operator_profile_page | app.py | 17095 | 운영업체 공개 프로필 페이지. Flask는 정적 룰(/operator/login, /operator/dashboard)을 우선 매칭하므로 충돌 없음. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/operator/profile/<slug> | operator_public_profile | app.py | 17146 | 운영업체 공개 프로필 API — 인증 불필요. approved 상태만 노출. | UNKNOWN: no recognized static guard | master_buildings;operator_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /operator/dashboard | operator_dashboard_page | app.py | 17189 | operator_dashboard_page | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/operator/me | operator_me | app.py | 17195 | operator_me | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings;operator_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/me | operator_me_update | app.py | 17265 | 부분 업데이트 — 전달된 키만 수정 (agent와 동일 패턴). 사업자등록번호 변경 시 재승인 대기 전환. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/visibility | operator_visibility_update | app.py | 17324 | 노출 여부 토글 — 본인 세션 기준. is_visible만 갱신 (agent와 동일 패턴). | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/logo | operator_logo_upload | app.py | 17343 | 마이페이지에서 로고 업로드/교체 — 신청서 업로드와 동일한 검증. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/avatar | operator_avatar_upload | app.py | 17376 | 마이페이지 원형 아바타 업로드 — logo_url 필드에 저장, operator_logo_upload와 동일 검증. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/intro-image | operator_intro_image_upload | app.py | 17409 | 소개글 내 이미지 업로드 — 로고와 동일한 검증, 별도 스토리지 키. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/intro-image-file/<path:key> | operator_intro_image_serve | app.py | 17435 | 소개글 이미지 공개 서빙 — 인증 불필요, 키 형식 검증 후 스토리지에서 직접 서빙. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/intro-image | agent_intro_image_upload | app.py | 17452 | 중개사 소개글 내 이미지 업로드. | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/intro-image-file/<path:key> | agent_intro_image_serve | app.py | 17478 | 중개사 소개글 이미지 공개 서빙. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/favorites | agent_favorites | app.py | 17733 | agent_favorites | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/agent/favorites | agent_favorites | app.py | 17733 | agent_favorites | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/agent/favorites | agent_favorites | app.py | 17733 | agent_favorites | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/agent/favorites/<int:master_building_id> | agent_favorite_remove | app.py | 17746 | agent_favorite_remove | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | INFERRED partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/favorites | operator_favorites | app.py | 17752 | operator_favorites | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/favorites | operator_favorites | app.py | 17752 | operator_favorites | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/favorites | operator_favorites | app.py | 17752 | operator_favorites | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/favorites/<int:master_building_id> | operator_favorite_remove | app.py | 17765 | operator_favorite_remove | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | INFERRED partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/favorites | loan_consultant_favorites | app.py | 17771 | loan_consultant_favorites | UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/favorites | loan_consultant_favorites | app.py | 17771 | loan_consultant_favorites | UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/loan-consultant/favorites | loan_consultant_favorites | app.py | 17771 | loan_consultant_favorites | UNKNOWN: no recognized static guard | INFERRED master_buildings;partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/loan-consultant/favorites/<int:master_building_id> | loan_consultant_favorite_remove | app.py | 17784 | loan_consultant_favorite_remove | UNKNOWN: no recognized static guard | INFERRED partner_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agent/weekly-email | agent_weekly_email | app.py | 17790 | agent_weekly_email | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/agent/weekly-email | agent_weekly_email | app.py | 17790 | agent_weekly_email | CONFIRMED decorator: require_agent; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/weekly-email | operator_weekly_email | app.py | 17796 | operator_weekly_email | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/weekly-email | operator_weekly_email | app.py | 17796 | operator_weekly_email | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/weekly-email | loan_consultant_weekly_email | app.py | 17802 | loan_consultant_weekly_email | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/loan-consultant/weekly-email | loan_consultant_weekly_email | app.py | 17802 | loan_consultant_weekly_email | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /loan-consultant/<slug> | loan_consultant_profile_page | app.py | 17807 | 대출상담사 공개 프로필 페이지. Flask는 정적 룰(/loan-consultant/login, /loan-consultant/dashboard)을 우선 매칭하므로 충돌 없음. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/profile/<slug> | loan_consultant_public_profile | app.py | 17813 | 대출상담사 공개 프로필 API — 인증 불필요. approved 상태만 노출. | UNKNOWN: no recognized static guard | loan_consultant_buildings;loan_consultants;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /loan-consultant/login | loan_consultant_login_page | app.py | 17859 | loan_consultant_login_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/login | loan_consultant_login | app.py | 17865 | loan_consultant_login | INFERRED guards: _get_account_contexts | INFERRED account_business_memberships;account_role_memberships;agents;loan_consultants;login_history;operator_lodging;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/logout | loan_consultant_logout | app.py | 17871 | loan_consultant_logout | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/loan-consultant/password | loan_consultant_change_password | app.py | 17878 | 대출상담사 비밀번호 변경 — 현재 비밀번호 확인 후 교체 (agent와 같은 패턴). | INFERRED guards: current_user | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /loan-consultant/dashboard | loan_consultant_dashboard_page | app.py | 17909 | loan_consultant_dashboard_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/me | loan_consultant_me | app.py | 17915 | loan_consultant_me | UNKNOWN: no recognized static guard | loan_consultant_buildings;loan_consultants;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/loan-consultant/me | loan_consultant_me_update | app.py | 17951 | phone / intro_text / consultant_products / kakao_chat_url 부분 업데이트 — 전달된 키만 수정. | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/loan-consultant/visibility | loan_consultant_visibility_update | app.py | 18039 | 노출 여부 토글 — 본인 세션 기준. is_visible만 갱신 (agent와 동일 패턴). | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/consult-requests/mine | loan_consultant_consult_requests_mine | app.py | 18058 | loan_consultant_consult_requests_mine | UNKNOWN: no recognized static guard | loan_consult_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/loan-consultant/consult-requests/<int:req_id>/status | loan_consultant_consult_request_status | app.py | 18079 | loan_consultant_consult_request_status | UNKNOWN: no recognized static guard | loan_consult_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/consult-requests/mine | operator_consult_requests_mine | app.py | 18101 | operator_consult_requests_mine | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_consult_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/consult-requests/<int:req_id>/status | operator_consult_request_status | app.py | 18122 | operator_consult_request_status | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_consult_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/tier-status | loan_consultant_tier_status | app.py | 18144 | loan_consultant_tier_status | UNKNOWN: no recognized static guard | loan_consultant_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/tier-status | operator_tier_status | app.py | 18165 | operator_tier_status | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_buildings;operator_region_buildings;operator_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/service-areas/mine | loan_consultant_service_areas_mine | app.py | 18200 | loan_consultant_service_areas_mine | UNKNOWN: no recognized static guard | loan_consultant_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/service-areas | loan_consultant_service_area_add | app.py | 18213 | loan_consultant_service_area_add | UNKNOWN: no recognized static guard | loan_consultant_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/loan-consultant/service-areas/<path:region_name> | loan_consultant_service_area_remove | app.py | 18235 | loan_consultant_service_area_remove | UNKNOWN: no recognized static guard | loan_consultant_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/buildings | loan_consultant_building_add | app.py | 18250 | loan_consultant_building_add | UNKNOWN: no recognized static guard | loan_consultant_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/loan-consultant/buildings/<int:mbid> | loan_consultant_building_delete | app.py | 18303 | loan_consultant_building_delete | UNKNOWN: no recognized static guard | loan_consultant_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/buildings/search | loan_consultant_building_search | app.py | 18324 | loan_consultant_building_search | UNKNOWN: no recognized static guard | loan_consultant_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/avatar | loan_consultant_avatar_upload | app.py | 18352 | 마이페이지 원형 아바타 업로드 — logo_url 필드에 저장. | UNKNOWN: no recognized static guard | loan_consultants | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/loan-consultant/intro-image | loan_consultant_intro_image_upload | app.py | 18385 | 대출상담사 소개글 내 이미지 업로드. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/loan-consultant/intro-image-file/<path:key> | loan_consultant_intro_image_serve | app.py | 18411 | 대출상담사 소개글 이미지 공개 서빙. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/service-areas/mine | operator_service_areas_mine | app.py | 18428 | operator_service_areas_mine | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/service-areas | operator_service_area_add | app.py | 18441 | operator_service_area_add | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/service-areas/<path:region_name> | operator_service_area_remove | app.py | 18463 | operator_service_area_remove | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_service_areas | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/buildings | operator_building_add | app.py | 18478 | operator_building_add | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/buildings/<int:mbid>/claim-premium | operator_building_claim_premium | app.py | 18522 | 전속 단지를 무료 단지뱃지로 즉시 승격 — 단지당 1회 한정, | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_buildings;operator_region_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/service-regions | operator_service_regions_mine | app.py | 18592 | 현재 운영업체의 시군구 지역뱃지 등록 상태를 반환한다. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/service-regions | operator_service_region_claim | app.py | 18617 | 시군구 단위 지역뱃지를 업종별 활성 정원 안에서 즉시 등록한다. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_service_regions;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/service-regions | operator_service_region_delete | app.py | 18672 | 담당 지역 삭제 — 그 지역의 담당단지도 함께 전부 삭제된다. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_region_buildings;operator_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/region-buildings/search | operator_region_building_search | app.py | 18689 | operator_region_building_search | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_buildings;operator_region_buildings;operator_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/region-buildings | operator_region_building_add | app.py | 18727 | operator_region_building_add | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_buildings;operator_region_buildings;operator_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/region-buildings/<int:mbid> | operator_region_building_remove | app.py | 18768 | operator_region_building_remove | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_region_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/sgg-options | operator_sgg_options | app.py | 18782 | operator_sgg_options | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/operator/buildings/<int:mbid> | operator_building_delete | app.py | 18798 | operator_building_delete | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/operator/buildings/<int:mbid>/note | operator_building_note | app.py | 18820 | operator_building_note | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | operator_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/buildings/search | operator_building_search | app.py | 18847 | 단지관리 모달용 건물명 검색 — 이미 등록된 건물은 already_added 표시 (agent와 동일). | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | master_buildings;operator_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/operator/booking-url-requests | operator_booking_url_requests_list | app.py | 18878 | 내 모든 OTA 링크 신청 내역 — 건물별 최신 1건. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/booking-url-requests | operator_booking_url_request_submit | app.py | 18917 | 담당 건물의 OTA 링크 신청 — 기존 pending 취소 후 새 신청 삽입. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | booking_url_requests;operator_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/booking-url-requests/export.xlsx | admin_booking_url_requests_export | app.py | 18973 | OTA 신청 전체 이력 엑셀 다운로드 — 신청일 내림차순. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_users;booking_url_requests;master_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/booking-url-requests/summary | admin_booking_url_requests_summary | app.py | 19059 | OTA 신청 현황 요약: 대기중/운영중/만료임박(7일) 카운트. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/booking-url-requests | admin_booking_url_requests_list | app.py | 19087 | OTA 링크 신청 목록 — 기본 pending만, ?status=all 로 전체 조회. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/booking-url-requests/<int:req_id>/approve | admin_booking_url_request_approve | app.py | 19123 | OTA 링크 승인 — master_buildings 반영 + 3개월 만료일 설정. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/booking-url-requests/<int:req_id>/reject | admin_booking_url_request_reject | app.py | 19162 | OTA 링크 신청 거절 — admin_note(거절 사유) 선택 입력. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/booking-url-requests/<int:req_id>/cancel | admin_booking_url_request_cancel | app.py | 19190 | OTA 링크 신청 취소(관리자) — pending 상태 신청을 cancelled로 변경. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/booking-url-requests/<int:req_id>/extend | admin_booking_url_request_extend | app.py | 19216 | OTA 링크 연장(관리자) — 승인된 신청을 현재 시점에서 3개월 연장. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/booking-url-requests/<int:req_id>/revoke | admin_booking_url_request_revoke | app.py | 19253 | OTA 승인 철회(관리자) — approved 신청을 cancelled로, master_buildings 배지 제거. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/operator/booking-url-requests/<int:req_id>/cancel | operator_booking_url_request_cancel | app.py | 19291 | OTA 링크 신청 취소(운영자 본인) — 본인의 pending 신청만 취소 가능. | CONFIRMED decorator: require_operator; UNKNOWN: no recognized static guard | booking_url_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/bug-reports/upload-screenshot | bug_report_upload_screenshot | app.py | 19342 | 오류신고 스크린샷 업로드 (신고 제출 전 미리 업로드 → 키 반환). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/bug-reports | submit_bug_report | app.py | 19366 | 오류신고 제출 — 로그인 회원 전용. | UNKNOWN: no recognized static guard | bug_reports | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/bug-reports/summary | admin_bug_reports_summary | app.py | 19453 | 오류신고 요약: new / checking / blocking 카운트. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | bug_reports | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/bug-reports | admin_bug_reports_list | app.py | 19477 | 오류신고 목록 — 기본 긴급 우선 → 최신순. ?status=resolved 로 해결 목록. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | bug_reports | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PATCH | /api/admin/bug-reports/<int:report_id>/status | admin_bug_report_status | app.py | 19516 | 오류신고 상태 변경: new → checking → resolved. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | bug_reports | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/bug-reports/<int:report_id>/screenshot | admin_bug_report_screenshot | app.py | 19542 | 오류신고 스크린샷 서명 URL(5분) 발급. | CONFIRMED decorator: require_admin; INFERRED guards: require_admin | bug_reports | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/weekly-digest-status | admin_weekly_digest_status | app.py | 19810 | admin_weekly_digest_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;app_meta;loan_consultants;operators;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/weekly-digest-send-test | admin_weekly_digest_send_test | app.py | 19889 | admin_weekly_digest_send_test | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/weekly-digest-send-all | admin_weekly_digest_send_all | app.py | 19904 | admin_weekly_digest_send_all | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/geocode-buildings | admin_geocode_run | app.py | 19999 | 카카오맵 API 실시간 지오코딩 시작 — lat/lng가 NULL인 건물만 대상. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/geocode-status | admin_geocode_status | app.py | 20013 | 좌표 확보 현황 + 실행 상태 (관리자 화면 표시용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/geocode-brokers | admin_geocode_brokers_run | app.py | 20045 | 카카오맵 API로 broker_registry 좌표 채우기 시작 — lat NULL 행만 대상. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/geocode-brokers-status | admin_geocode_brokers_status | app.py | 20059 | 중개업소 좌표 확보 현황 + 실행 상태 (관리자 화면 표시용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | broker_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/backfill-title-info | admin_title_info_run | app.py | 20103 | 건축HUB 표제부 API 실시간 백필 시작 — 미백필(title_backfilled_at NULL) 건물만 대상. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/title-info-status | admin_title_info_status | app.py | 20118 | 표제부(건축정보) 확보 현황 + 실행 상태 (관리자 화면 표시용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-photos | admin_building_photos_sync_run | app.py | 20149 | 건물 사진 공급자별 수집을 detached 백그라운드로 시작한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/prewarm-tourapi-metadata | admin_tourapi_metadata_prewarm_run | app.py | 20169 | TourAPI 숙박 목록을 한 번 읽어 contentId·대표사진 유무만 저장한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/tourapi-image-backfill | admin_tourapi_image_backfill_run | app.py | 20193 | TourAPI 대표사진·다중사진 수집을 체크포인트부터 시작한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/tourapi-image-backfill-status | admin_tourapi_image_backfill_status | app.py | 20219 | admin_tourapi_image_backfill_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;building_photo_fetches | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/sync-photos-status | admin_building_photos_sync_status | app.py | 20298 | 건물 사진 적재·공급자별 현황과 백그라운드 실행 상태. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;building_photo_fetches;building_photos;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/datasync-overview | admin_datasync_overview | app.py | 20382 | '데이터 동기화' 페이지 배너용 — 배포(재시작) 후 미실행/대기 항목 요약. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/datasync-board | admin_datasync_board | app.py | 20441 | Read-only board: existing metadata only, no provider requests or jobs. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/datasync-board/action | admin_datasync_board_action | app.py | 20454 | Allowlisted adapter only; preserve existing runners and rate limits. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/public-api-relay/status | admin_public_api_relay_status | app.py | 20494 | Read-only, non-sensitive local relay telemetry; never probe the provider. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/scheduled-sync-status | admin_scheduled_sync_status | app.py | 20504 | 정기 API 통합 배치의 전체/단계별 상태를 한 번에 반환한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/lodging-staging/overview | admin_lodging_staging_overview | app.py | 20884 | 8종 staging 배치·승인 상태와 운영 기준 보완 요약을 반환한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;lodging_approval_batches;lodging_promotion_manifests;lodging_promotion_review_decisions;lodging_promotion_rows;lodging_source_batches;lodging_source_rows | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/<int:batch_id>/approval | admin_lodging_staging_create_approval | app.py | 21198 | 검증 통과한 staging 배치의 승인 초안을 개발 DB에 만든다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_approval_batches;lodging_approval_rows;lodging_source_batches;lodging_source_rows | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/approval/<int:approval_id>/approve | admin_lodging_staging_approve | app.py | 21216 | 승인을 기록하되 운영 원장은 변경하지 않는다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_approval_batches | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/approval/<int:approval_id>/dry-run | admin_lodging_staging_dry_run | app.py | 21234 | 승인 배치의 변경 건수만 개발 DB에서 검증한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_approval_attempts;lodging_approval_batches;lodging_approval_rows;lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/promotion/<int:manifest_id>/approve | admin_lodging_promotion_approve | app.py | 21249 | 운영 기준 manifest의 관리자 승인만 기록한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_promotion_manifests;lodging_promotion_rows;lodging_source_batches;lodging_source_rows | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/promotion/<int:manifest_id>/review/<int:source_row_id> | admin_lodging_promotion_resolve_review | app.py | 21268 | 수동검토 결정을 감사 기록과 함께 새 manifest 버전으로 고정한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_promotion_manifests;lodging_promotion_review_decisions;lodging_promotion_rows;lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/promotion/<int:manifest_id>/dry-run | admin_lodging_promotion_dry_run | app.py | 21290 | 고정 payload와 운영 기준선만 재검증하며 운영에는 쓰지 않는다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED lodging_promotion_manifests;lodging_promotion_rows;lodging_registry;lodging_source_batches;lodging_source_rows;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-staging/promotion/<int:manifest_id>/legacy-sync | admin_lodging_legacy_sync_control | app.py | 21305 | 명시적 관리자 승인으로 기존 숙박 수집을 종료하거나 복구한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta;lodging_parallel_comparisons;lodging_promotion_manifests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/lodging-source-overview | admin_lodging_source_overview | app.py | 21404 | 원본별 실제 적재·활성·건물 연결과 최근 실행 결과를 함께 반환한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_import_staging;lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-import/preview | admin_lodging_import_preview | app.py | 21503 | 파일을 파싱·매칭만 하고 DB 원본/건물 데이터는 변경하지 않는다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_import_staging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-import/<token>/apply | admin_lodging_import_apply | app.py | 21568 | 한 번만 승인할 수 있도록 초안을 원자적으로 선점하고 별도 프로세스로 반영한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_import_staging | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/scheduled-sync/run | admin_scheduled_sync_stage_run | app.py | 21762 | Safely run one existing checkpoint-aware stage as a manual source. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/scheduled-sync/run-all | admin_scheduled_sync_run_all | app.py | 21804 | 예약 실행이 없을 때 관리자가 전체 체크포인트 배치를 즉시 시작한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/scheduled-sync/retry | admin_scheduled_sync_retry | app.py | 21822 | 자동 배치의 실패·중단 단계만 체크포인트에서 재개한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-transactions | admin_sync_run | app.py | 21889 | 실거래 동기화 시작. 이미 실행 중이면 409. 시작되면 즉시 202 반환. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/sync-status | admin_sync_status | app.py | 21968 | 실거래 동기화 진행상황 + 거래 데이터 현황(총 건수·최근 계약일). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-backfill | admin_backfill_run | app.py | 22077 | 과거 데이터 백필 시작. 실행 중이면 409, 24시간 내 완료 이력 있으면 429. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/backfill-status | admin_backfill_status | app.py | 22168 | 과거 데이터 백필 진행상황 (sync-status 와 동일한 응답 형태). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/backfill-log | admin_backfill_log | app.py | 22242 | 마지막 백필 실행 로그의 마지막 50줄 — 실패 원인 확인용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/reset-backfill-checkpoint | admin_reset_backfill_checkpoint | app.py | 22286 | 일회성 — 과거 데이터 백필 체크포인트(tx_backfill_progress)만 초기화. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /admin | admin_page | app.py | 22323 | admin_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /admin/ | admin_page | app.py | 22323 | admin_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /admin/ad-products | admin_ad_products_page | app.py | 22329 | 광고상품 안내 (관리자 전용 참고용 정보 페이지 — 판매 기능/파트너 노출 없음). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | https://homenstay.com;https://www.googletagmanager.com/gtag/js | UNKNOWN / not statically reached |
| GET | /api/admin/buildings | admin_buildings_list | app.py | 22736 | admin_buildings_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;broker_registry;building_stores;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/full-stats | admin_buildings_full_stats | app.py | 24397 | admin_buildings_full_stats | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/v1/d/3f7 | stats_lodging_full_table | app.py | 24434 | 인증 없이 공개하는 데이터랩 전국 숙박업 통계표. | UNKNOWN: no recognized static guard | INFERRED agent_buildings;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/region-options | admin_buildings_region_options | app.py | 24442 | 건물마스터 지역 검색용 시/도·시군구·읍면동 목록 반환 (5분 캐시). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/stats | admin_buildings_stats | app.py | 24481 | 건물마스터 탭 상단 통계박스 — 현재 필터 기준 5가지 집계. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/<int:building_id>/lodgings | admin_building_lodgings | app.py | 24578 | 건물 ID에 해당하는 영업신고(lodging_registry) 전체 목록 — 상세모달용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/v1/r/8a1/<int:mbid> | admin_building_stores | app.py | 24616 | 건물 입점상가 전체 목록 (building_stores 캐시 기준). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | building_stores | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/buildings | admin_buildings_create | app.py | 24634 | admin_buildings_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/buildings/<int:building_id> | admin_buildings_update | app.py | 24665 | admin_buildings_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/buildings/<int:building_id>/kakao-promo-copy | admin_building_kakao_promo_copy | app.py | 24717 | 관리자용 카카오 홍보 문구 복사 횟수를 원자적으로 1회 증가한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/pending-completion | admin_pending_completion | app.py | 24741 | building_status가 완공이 아니면서 추정 완공일이 지난 건물 — | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/buildings/<int:building_id> | admin_buildings_delete | app.py | 24763 | admin_buildings_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests;master_buildings;slots;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/buildings/bulk-update | admin_buildings_bulk_update | app.py | 24827 | 선택한 건물 여러 건을 동일 필드/값으로 일괄 수정 (최대 500건). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/buildings/bulk-delete | admin_buildings_bulk_delete | app.py | 24870 | 선택한 건물 여러 건을 일괄 삭제 (최대 500건). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests;master_buildings;slots;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/export.xlsx | admin_buildings_export | app.py | 24939 | admin_buildings_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;broker_registry;building_stores;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings/<int:mbid>/favorites/export.xlsx | admin_building_favorites_export | app.py | 25192 | 건물별 관심저장 회원 목록 엑셀 다운로드. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/backup-export | admin_backup_export | app.py | 25259 | 핵심 테이블 10개 + 스키마 스냅샷을 zip으로 묶어 다운로드. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/run-backfill-permits | admin_run_backfill_permits | app.py | 25313 | 일회성 — 기존 permit_pipeline 14건 면적정보 보강. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/backfill-permits-log | admin_backfill_permits_log | app.py | 25327 | 위 작업의 실행 로그 확인용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-brokers | admin_broker_sync_run | app.py | 25347 | 중개업소 데이터 동기화 시작 — 실거래 동기화와 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-sync-status | admin_broker_sync_status | app.py | 25423 | 중개업소 동기화 진행상황 + 수집 현황 + 오늘 남은 호출 수. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;broker_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/v1/r/4c2/<int:mbid> | admin_building_brokers | app.py | 25606 | 건물 주소 정규화 키에 매칭된 중개업소 표준데이터 전체를 반환한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED broker_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-exact-match | admin_broker_exact_match | app.py | 25624 | admin_broker_exact_match | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED broker_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-exact-match/export.xlsx | admin_broker_exact_match_export | app.py | 25642 | admin_broker_exact_match_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED broker_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-registry/export.xlsx | admin_broker_registry_export | app.py | 25671 | admin_broker_registry_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | broker_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/lodging-registry/export.xlsx | admin_lodging_registry_export | app.py | 25707 | admin_lodging_registry_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/sync-progress-summary | admin_sync_progress_summary | app.py | 25740 | 통계 대시보드용 — 각 수집 파이프라인의 진행률을 한 번에 반환. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;broker_registry;lodging_registry;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-candidates | admin_broker_candidates | app.py | 25816 | 건물 좌표 기준 반경 내 중개업소 후보(거리순). 후보 '생성'만 — 자동 발송 없음. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;broker_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buildings-without-agent | admin_buildings_without_agent | app.py | 25838 | 담당중개사(agent_buildings)가 없는 건물 목록 — 후보 매칭 대상 선택용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-candidates/export.xlsx | admin_broker_candidates_export | app.py | 25867 | admin_broker_candidates_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;broker_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-lodgings | admin_lodging_sync_run | app.py | 25924 | 영업신고 데이터 동기화 시작 — 중개업소 동기화와 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/lodging-sync-status | admin_lodging_sync_status | app.py | 26013 | 영업신고 동기화 진행상황 + 수집 현황 + 오늘 남은 호출 수. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/camping-image-backfill | admin_camping_image_backfill_run | app.py | 26326 | Start only the resumable GoCamping multi-image backfill. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/camping-image-backfill-status | admin_camping_image_backfill_status | app.py | 26412 | admin_camping_image_backfill_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta;lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/gocamping-web-backfill-status | admin_gocamping_web_backfill_status | app.py | 26481 | admin_gocamping_web_backfill_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta;lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/gocamping-web-backfill | admin_gocamping_web_backfill_run | app.py | 26488 | admin_gocamping_web_backfill_run | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-brhub | admin_brhub_sync_run | app.py | 26629 | 건축HUB 전국 건물수집 시작 — 숙박업 동기화와 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/backfill-lodging-run | admin_backfill_lodging_run | app.py | 26706 | 영업신고 기반 누락건물 보완수집 시작. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/backfill-lodging-status | admin_backfill_lodging_status | app.py | 26792 | 영업신고 누락건물 보완수집 진행상황. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/reclassify-lodging-keywords | admin_reclassify_lodging_keywords | app.py | 26822 | 건물명 키워드로 lodging_type='기타' 건물을 일괄 재분류한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/reclassify-by-hygiene | admin_reclassify_by_hygiene | app.py | 26888 | 활성 공식 신고를 건물별로 합쳐 법정 영업분류를 드라이런/적용한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/lodging-classification-provenance | admin_lodging_classification_provenance | app.py | 27069 | 법정분류 출처 누락을 점검하고 검증 가능한 원본만 보수적으로 복원한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/lodging-classification-provenance | admin_lodging_classification_provenance | app.py | 27069 | 법정분류 출처 누락을 점검하고 검증 가능한 원본만 보수적으로 복원한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/brhub-rescan-run | admin_brhub_rescan_run | app.py | 27152 | 일반건축물 필터 확장 이전에 이미 지나간 법정동 구간을 | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/brhub-rescan-status | admin_brhub_rescan_status | app.py | 27217 | admin_brhub_rescan_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/brhub-sync-status | admin_brhub_sync_status | app.py | 27241 | 건물수집 진행상황 + brhub_bulk 수집 현황 + 체크포인트/오늘 호출량. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-stores | admin_stores_sync_run | app.py | 27331 | 상가정보 사전수집(sync_stores.py) 시작 — brhub_sync와 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/stores-sync-status | admin_stores_sync_status | app.py | 27408 | 상가정보 사전수집 진행상황 + 체크포인트/오늘 호출량. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;building_stores;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-permits | admin_permits_sync_run | app.py | 27511 | 준공전 건물수집(건축인허가) 시작 — brhub 버튼과 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/permits-sync-status | admin_permits_sync_status | app.py | 27605 | 준공전 건물수집 진행상황 + permit_pipeline 수집 현황 + 체크포인트/오늘 호출량. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/permits-cleanup | admin_permits_cleanup | app.py | 27674 | permit_pipeline 건물 중 이미 완공됐거나 오염된 건물 삭제. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/run-realty-sync | admin_realty_sync_run | app.py | 27737 | 단지부동산(상가정보 API) 배치 동기화 시작 — permits 버튼과 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/realty-sync-status | admin_realty_sync_status | app.py | 27808 | 단지부동산 동기화 진행상황 — 확보 건수/전체 + 실행 상태. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/run-reclassify-unclassified | admin_reclassify_unclassified_run | app.py | 27884 | 미분류 건물 재판정 배치 시작 — realty-sync와 동일한 잠금/러너 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/reclassify-unclassified-status | admin_reclassify_unclassified_status | app.py | 27900 | 미분류 건물 재판정 진행상황. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/unregistered-lodging-candidates | admin_unregistered_lodging_candidates | app.py | 28035 | operators에 등록되지 않은 '영업/정상' 생활숙박업 사업장 목록 — 위탁운영 유치 후보. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/unregistered-lodging-candidates/export.xlsx | admin_unregistered_lodging_export | app.py | 28072 | admin_unregistered_lodging_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/unmatched-building-candidates | admin_unmatched_building_candidates | app.py | 28125 | master_buildings에 매칭 안 되는 '영업/정상' 일반숙박업 사업장 — | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/unmatched-building-candidates/<permit_number>/create-building | admin_create_building_from_lodging | app.py | 28157 | 후보 사업장을 master_buildings에 신규 건물로 등록. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/unmatched-building-candidates/<permit_number>/dismiss | admin_dismiss_building_candidate | app.py | 28191 | 후보를 무시(건물로 등록하지 않고 목록에서만 제외). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/listings | admin_listings_list | app.py | 28280 | 직거래 매물(listing_requests, deal_mode='direct') 조회 — 읽기 전용 뷰. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/listings/<int:listing_id> | admin_listings_update | app.py | 28316 | 직거래 매물은 읽기 전용 — 수정 불가 (매물의뢰 탭에서 상태 관리). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/listings/<int:listing_id> | admin_listings_delete | app.py | 28323 | 직거래 매물을 관리자 철회 처리 (status='철회됨') — 데이터는 보존. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/listings/export.xlsx | admin_listings_export | app.py | 28343 | 직거래 매물 엑셀 다운로드 — listing_requests, deal_mode='direct'. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/listing-requests | admin_listing_requests_list | app.py | 28400 | admin_listing_requests_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agents;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/partner-building-counts | admin_partner_building_counts | app.py | 28474 | 중개사/운영업체별 담당 건물 수 목록 (무료 캡 대비 현황 파악용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agents;operator_buildings;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/listing-requests/<int:req_id> | admin_listing_requests_update | app.py | 28506 | 관리자 수정은 admin_note만 허용 — status 등 다른 필드는 값이 와도 무시한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/listing-requests/bulk-delete | admin_listing_requests_bulk_delete | app.py | 28575 | 관리자가 선택한 테스트/오등록 매물의뢰를 연관 데이터와 함께 영구 삭제한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | chat_messages;chat_rooms;listing_request_history;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/listings/bulk-delete | admin_listings_bulk_delete | app.py | 28630 | 관리자가 선택한 직거래 매물을 연관 데이터와 함께 영구 삭제한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | chat_messages;chat_rooms;listing_request_history;listing_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/listing-requests/export.xlsx | admin_listing_requests_export | app.py | 28689 | 매물의뢰 전체 엑셀 다운로드 — 접수일 내림차순. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buy-requests | admin_buy_requests_list | app.py | 28755 | admin_buy_requests_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;buy_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/buy-requests/<int:req_id> | admin_buy_requests_update | app.py | 28799 | 관리자 수정은 admin_note만 허용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | buy_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/buy-requests/bulk-delete | admin_buy_requests_bulk_delete | app.py | 28822 | 관리자가 선택한 매수의뢰를 영구 삭제한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | buy_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/buy-requests/export.xlsx | admin_buy_requests_export | app.py | 28862 | 매수의뢰 전체 엑셀 다운로드 — 접수일 내림차순. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;buy_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/transactions | admin_transactions_list | app.py | 29001 | admin_transactions_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/transactions/<int:tx_id> | admin_transactions_update | app.py | 29025 | admin_transactions_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_edit_log;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/transactions/export.xlsx | admin_transactions_export | app.py | 29082 | admin_transactions_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/notices | admin_notices_list | app.py | 29176 | admin_notices_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | notices | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/notices | admin_notices_create | app.py | 29202 | admin_notices_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | notices | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/notices/<int:notice_id> | admin_notices_update | app.py | 29241 | admin_notices_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | notices | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/agency-links | admin_agency_links_list | app.py | 29323 | admin_agency_links_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/agency-links | admin_agency_links_create | app.py | 29366 | admin_agency_links_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/agency-links/reorder | admin_agency_links_reorder | app.py | 29391 | admin_agency_links_reorder | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/agency-links/<int:link_id> | admin_agency_links_update | app.py | 29427 | admin_agency_links_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/agency-links/<int:link_id> | admin_agency_links_delete | app.py | 29455 | admin_agency_links_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/notices/<int:notice_id> | admin_notices_delete | app.py | 29480 | admin_notices_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | notices | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/popups | admin_popups_list | app.py | 29580 | admin_popups_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | site_popups | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/popups | admin_popups_create | app.py | 29606 | admin_popups_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | site_popups | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/popups/<int:popup_id> | admin_popups_update | app.py | 29627 | admin_popups_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | site_popups | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/popups/<int:popup_id> | admin_popups_delete | app.py | 29669 | admin_popups_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | site_popups | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/popups/upload-image | admin_popups_upload_image | app.py | 29684 | 팝업 이미지 업로드 — C/D 서류 업로드와 동일한 검증(확장자·5MB·매직바이트). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/email-banners/upload-image | admin_email_banners_upload_image | app.py | 29710 | 이메일 광고배너 이미지 업로드 — 이메일 img src로 직접 쓰므로 절대 URL 반환. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/email-banners/image/<path:key> | serve_email_banner_image | app.py | 29737 | 이메일 배너 이미지 공개 서빙 — 로그인 불필요, 이메일 클라이언트에서 직접 접근. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/notices/upload-attachment | admin_notices_upload_attachment | app.py | 29755 | 공지사항 첨부 PDF 업로드 — 팝업 이미지 업로드와 동일한 검증 패턴, PDF 전용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/agency-links/<int:link_id>/logo | admin_agency_link_logo | app.py | 29781 | admin_agency_link_logo | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/popups/active | get_active_popup | app.py | 29834 | 현재 노출 대상 팝업 1건(최신 등록순)을 반환. 없으면 popup: null. | UNKNOWN: no recognized static guard | site_popups | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/popups/image/<path:key> | get_popup_image | app.py | 29875 | 팝업 이미지 공개 프록시 — popups/… 형식 키만 허용(서류 등 다른 객체 접근 차단). | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/notices/attachment/<path:key> | get_notice_attachment | app.py | 29891 | 공지 첨부 PDF 공개 다운로드 — notices/… 형식 키만 허용. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/lodging-national-stats | get_lodging_national_stats | app.py | 29906 | lodging_registry 집계 — 업태별 영업중 사업장 수·객실수 합계. | UNKNOWN: no recognized static guard | lodging_registry | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agency-links | get_agency_links | app.py | 29935 | get_agency_links | UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/agency-links/<int:link_id>/logo | get_agency_link_logo | app.py | 29961 | get_agency_link_logo | UNKNOWN: no recognized static guard | agency_links | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/notices | get_notices | app.py | 29991 | 공개 공지 목록 — 고정 우선 → 최신순. {total, page, size, items} 형태. | UNKNOWN: no recognized static guard | notices | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/applications | admin_applications_list | app.py | 30063 | admin_applications_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/stats/overview | admin_stats_overview | app.py | 30198 | 대시보드 상단의 회원 현황·처리 대상 수. 회원관리와 같은 원장을 사용한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | booking_url_requests;bug_reports;building_requests;buy_requests;listing_requests;presale_applications;sync_log;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members | admin_members_list | app.py | 30250 | admin_members_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agent_region_buildings;agent_service_regions;agents;bug_reports;listing_requests;loan_consultant_service_areas;loan_consultants;operator_region_buildings;operator_service_regions;operators;revenue_records;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/premium-status | admin_premium_status | app.py | 30635 | admin_premium_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agent_service_regions;agents;loan_consultant_buildings;loan_consultants;master_buildings;operator_buildings;operator_service_regions;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/premium-status/extend | admin_extend_premium_status | app.py | 30757 | 예외적인 수동 조정용: 지정 뱃지를 현재 무료 정책 만료일까지 연장한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agent_service_regions;loan_consultant_buildings;master_buildings;operator_buildings;operator_service_regions;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/premium-status/toggle-paid | admin_toggle_paid | app.py | 30928 | 단지뱃지/지역Master의 유료전환 여부를 관리자가 수동으로 토글 | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agent_service_regions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/agents/<int:agent_id>/buildings | admin_agent_buildings | app.py | 30964 | 해당 중개사의 전속단지 목록 + 단지마크 부여 상태 — 단지마크 부여 모달용. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/agent-buildings/<int:agent_id>/<int:mbid>/priority-badge | admin_agent_building_priority_badge | app.py | 30984 | 관리자가 특정 중개사·건물 조합에 단지마크(우선노출)를 켜고 끈다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members/<member_type>/<int:member_id>/docs | admin_member_docs | app.py | 31025 | 회원의 신청 첨부서류 목록. 다운로드 URL은 기존 doc-url API(5분 서명)를 재사용한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members/<member_type>/<int:member_id>/docs.zip | admin_member_docs_zip | app.py | 31050 | 회원이 신청 시 올린 첨부서류 전체를 zip 하나로 묶어 다운로드. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/revenue-records | admin_revenue_records_list | app.py | 31175 | 특정 파트너의 매출 기록 이력 (최신순). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | revenue_records | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/revenue-records | admin_revenue_records_create | app.py | 31204 | admin_revenue_records_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | revenue_records | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/revenue-records/<int:rec_id> | admin_revenue_records_update | app.py | 31245 | admin_revenue_records_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | revenue_records | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/revenue-records/<int:rec_id> | admin_revenue_records_delete | app.py | 31274 | 오입력 정정용 삭제 (장부이므로 신중히 — 프런트에서 확인창 필수). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | revenue_records | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/revenue-summary | admin_revenue_summary | app.py | 31296 | 매출관리 화면용 집계 — 월(start_date 기준)×상품×파트너유형별 건수/금액. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | revenue_records | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-approve | admin_members_bulk_approve | app.py | 31349 | 승인대기(pending) 선택 건 일괄 승인 — 기존 단건 승인 함수를 그대로 반복 호출(로직 재사용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED account_business_memberships;account_role_memberships;agent_buildings;agents;app_meta;applications;listing_requests;loan_consultant_buildings;loan_consultant_service_areas;loan_consultants;lodging_registry;master_buildings;operator_buildings;operator_lodging;operators;users | https://homenstay.com;https://www.gocamping.or.kr/bsite/camp/info/read.do | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-reject | admin_members_bulk_reject | app.py | 31382 | 승인대기 선택 건 일괄 반려 — 기존 단건 반려 함수 재사용. reason은 본문에서 공유. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/<member_type>/<int:member_id>/re-approve | admin_member_reapprove | app.py | 31419 | 본인 정보수정으로 pending 전환된 파트너를 인라인 재승인 (계정·slug 유지, SMS 없음). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-tag | admin_members_bulk_tag | app.py | 31451 | 선택 회원들의 admin_tag 일괄 지정. tag를 빈 값으로 보내면 태그 해제(NULL). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-sms | admin_members_bulk_sms | app.py | 31485 | 중개사/운영업체 선택 대상에게 커스텀 문구 SMS 일괄 발송 (남용 방지 3회/시간). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-notify | admin_members_bulk_notify | app.py | 31524 | 일반회원 선택 대상에게 인앱 알림(notifications) 일괄 생성 — 공지성이라 건물 정보는 NULL. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | notifications;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-points | admin_members_bulk_points | app.py | 31559 | 일반회원 포인트 일괄 지급/차감 — 단일 트랜잭션 + point_transactions 감사로그. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | point_transactions;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-deactivate | admin_members_bulk_deactivate | app.py | 31603 | 일괄 비활성화(소프트 삭제) — DELETE 없이 상태값만 변경. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-reactivate | admin_members_bulk_reactivate | app.py | 31662 | 일괄 재활성화 — bulk-deactivate의 반대. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/bulk-delete | admin_members_bulk_delete | app.py | 31707 | 회원 완전 삭제 — 되돌릴 수 없음. 연관 데이터까지 함께 정리한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;applications;buy_requests;chat_messages;chat_rooms;listing_request_history;listing_requests;listings;loan_consult_requests;loan_consultants;mileage_submissions;operator_consult_requests;operators;slots;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/members/<member_type>/<int:member_id>/memo | admin_member_memo_put | app.py | 31824 | 회원 메모(admin_memo) 수정 — 빈 값이면 삭제. 매물의뢰 비고와 동일 패턴. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/me | admin_me | app.py | 31871 | 현재 로그인 관리자 정보 (프론트엔드 권한 분기용). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members/<member_type>/<int:member_id>/login-history | admin_member_login_history | app.py | 31893 | 일반회원의 최근 접속 이력 10건을 반환한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | login_history;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members/<member_type>/<int:member_id>/detail | admin_member_detail | app.py | 31925 | 회원 상세 정보 + 관련 데이터(건물·관심단지·지역뱃지·OTA 신청 등). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agent_buildings;agent_service_regions;agents;booking_url_requests;buy_requests;listing_requests;loan_consultants;master_buildings;operator_buildings;operators;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/members/<member_type>/<int:member_id>/detail | admin_member_detail_update | app.py | 32060 | 회원 상세페이지 편집 가능 필드 일괄 저장. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/members/<member_type>/<int:member_id>/notes | admin_member_notes_list | app.py | 32169 | 회원 메모 이력 목록 (기본: is_deleted=FALSE만). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | member_notes | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/members/<member_type>/<int:member_id>/notes | admin_member_notes_add | app.py | 32194 | 메모 신규 추가 — 모든 관리자 권한 가능. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | member_notes | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PATCH | /api/admin/members/<member_type>/<int:member_id>/notes/<int:note_id> | admin_member_notes_update | app.py | 32232 | 메모 내용 수정 — super_admin 권한만. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_users;member_notes | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/members/<member_type>/<int:member_id>/notes/<int:note_id> | admin_member_notes_delete | app.py | 32268 | 메모 소프트 삭제(is_deleted=TRUE) — super_admin 권한만. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | admin_users;member_notes | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/applications/<int:app_id>/doc-url | admin_application_doc_url | app.py | 32311 | 신청 서류의 서명된 임시 열람 URL(5분) 발급 — 관리자 전용. | CONFIRMED decorator: require_admin; INFERRED guards: require_admin | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/operators/<int:operator_id>/logo | admin_operator_logo_put | app.py | 32342 | 운영지원업체 로고 등록/수정/삭제 (건물마스터 수정처럼 PUT). | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/applications/<int:app_id>/approve | admin_applications_approve | app.py | 32402 | admin_applications_approve | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | account_business_memberships;account_role_memberships;agent_buildings;agents;applications;loan_consultant_buildings;loan_consultant_service_areas;loan_consultants;operator_buildings;operator_lodging;operators | https://homenstay.com;https://www.gocamping.or.kr/bsite/camp/info/read.do | UNKNOWN / not statically reached |
| POST | /api/admin/applications/<int:app_id>/reject | admin_applications_reject | app.py | 32748 | admin_applications_reject | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/applications/export.xlsx | admin_applications_export | app.py | 32777 | admin_applications_export | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/building-requests | admin_building_requests_list | app.py | 32858 | admin_building_requests_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | building_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/building-requests/<int:req_id>/approve-name | admin_building_request_approve_name | app.py | 32883 | '명칭 확인 필요'(name_review) 건 승인 — 사용자가 제안한 건물명을 마스터에 확정 | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | building_requests;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/user-stats | admin_user_stats | app.py | 32925 | 활성 이용자·회원 가입·페이지뷰를 운영 대시보드용으로 집계한다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;listing_requests;listings;operators;page_views;user_favorites;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/stats | admin_stats | app.py | 33217 | 관리자 통계 대시보드용 집계(매출 제외). 기존 데이터 집계 + 방문 기록. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | applications;master_buildings;operators;page_views;revenue_records;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/platform-summary | stats_platform_summary | app.py | 33526 | 홈 검색창 아래에 표시할 실시간 데이터 규모 신뢰지표. | UNKNOWN: no recognized static guard | listing_requests;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/heatmap/domestic | tourism_heatmap_domestic | app.py | 33644 | tourism_heatmap_domestic | UNKNOWN: no recognized static guard | INFERRED sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/analysis/operation-upload | analysis_operation_upload | app.py | 33709 | 예약표·매출자료를 영구 저장하지 않고 요청 중 즉시 분석한다. | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/operation-benchmarks | analysis_operation_benchmarks | app.py | 33767 | 선택 건물의 시도 안에서 실제 시군구 전체 운영지표만 반환한다. | UNKNOWN: no recognized static guard | hotel_operation_metrics;hotel_operation_source_versions;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/recent | analysis_recent | app.py | 34214 | 현재 일반회원의 마지막 분석 건물 30개를 조회하거나 갱신한다. | INFERRED guards: current_user | master_buildings;user_recent_analysis | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/analysis/recent | analysis_recent | app.py | 34214 | 현재 일반회원의 마지막 분석 건물 30개를 조회하거나 갱신한다. | INFERRED guards: current_user | master_buildings;user_recent_analysis | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/analysis/share-link | analysis_share_link | app.py | 34305 | analysis_share_link | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/building-search | analysis_building_search | app.py | 34324 | 로그인 사용자가 분석할 건물을 이름 우선으로 찾는다. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/analysis/assets | analysis_assets | app.py | 34378 | Authenticated, conservative building-level tourism × transaction comparison. | UNKNOWN: no recognized static guard | listing_requests;master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/heatmap/foreign | tourism_heatmap_foreign | app.py | 34963 | tourism_heatmap_foreign | UNKNOWN: no recognized static guard | INFERRED sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/heatmap/consume | tourism_heatmap_consume | app.py | 34971 | tourism_heatmap_consume | UNKNOWN: no recognized static guard | INFERRED sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/lodging-rank/location | tourism_lodging_rank_location | app.py | 35301 | TOP100 상호를 기존 건물 상세 또는 카카오의 정확한 위치로 연결한다. | UNKNOWN: no recognized static guard | INFERRED master_buildings;sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/lodging-rank/top99 | tourism_lodging_rank_top99 | app.py | 35407 | 최신 숙박 검색순위 원본의 TOP 99(건물명·대표 좌표 포함)를 반환한다. | UNKNOWN: no recognized static guard | INFERRED master_buildings;sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/lodging-rank/top100 | tourism_lodging_rank_top100 | app.py | 35430 | 최신 숙박 검색순위 원본의 목록용 TOP 100을 반환한다. | UNKNOWN: no recognized static guard | INFERRED master_buildings;sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/lodging-rank/all | tourism_lodging_rank_all | app.py | 35453 | 최신 숙박 검색순위 원본 TOP 500만 반환한다. 다른 통계와 섞지 않는다. | UNKNOWN: no recognized static guard | INFERRED master_buildings;sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/lodging-rank | get_building_lodging_rank | app.py | 35476 | 건물의 최신 숙박 검색순위. 최신 원본에 없으면 rank는 명시적으로 null이다. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/tourism-stats | get_building_tourism_stats | app.py | 35520 | 모든 건물의 지역 관광지표와 급등동네·인기 관광지를 반환한다. | UNKNOWN: no recognized static guard | master_buildings;tourism_building_dong_matches;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/attractions/top20 | tourism_attractions_top20 | app.py | 35684 | 최신 검색순위 TOP 20과 시군구 중심좌표(관광지 실제 좌표 아님)를 반환한다. | UNKNOWN: no recognized static guard | INFERRED sgg_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/surge/domestic | tourism_surge_domestic | app.py | 35804 | tourism_surge_domestic | UNKNOWN: no recognized static guard | INFERRED tourism_dong_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/tourism/surge/foreign | tourism_surge_foreign | app.py | 35810 | tourism_surge_foreign | UNKNOWN: no recognized static guard | INFERRED tourism_dong_coords;tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/price-change-top | stats_price_change_top | app.py | 35816 | 최근 30일 안의 동일 건물·주소·전용면적 거래 첫값 대비 최근값 변동 TOP5. | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/highest-price-top | stats_highest_price_top | app.py | 35930 | 건물별 역대 최고·최저 거래가 TOP5. | UNKNOWN: no recognized static guard | master_buildings;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/closure-rate-by-region | stats_closure_rate_by_region | app.py | 36143 | stats_closure_rate_by_region | UNKNOWN: no recognized static guard | INFERRED agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/transactions-by-sido | stats_transactions_by_sido | app.py | 36159 | 최근 30일 실거래를 시도 표기 편차를 합쳐 거래 건수 순으로 반환한다. | UNKNOWN: no recognized static guard | transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/consign-by-sido | stats_consign_by_sido | app.py | 36457 | 생활숙박시설 영업신고 현황을 시도별로 반환한다. | UNKNOWN: no recognized static guard | INFERRED agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/stats/master | admin_master_stats | app.py | 36625 | 통계 원본 창고 상태 조회와 관리자 수동 새로고침. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/stats/master | admin_master_stats | app.py | 36625 | 통계 원본 창고 상태 조회와 관리자 수동 새로고침. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/tourism-datalab/coverage | tourism_datalab_coverage | app.py | 36633 | Coverage only: never downloads from the authenticated Data Lab portal. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/tourism-datalab/collections | tourism_datalab_collections | app.py | 36666 | Persistent upload history and official monthly update reminders. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | tourism_stats | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/tourism-datalab/preview | tourism_datalab_preview | app.py | 36736 | tourism_datalab_preview | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED tourism_datalab_stages | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/tourism-datalab/apply | tourism_datalab_apply | app.py | 36752 | tourism_datalab_apply | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED master_buildings;sgg_coords;tourism_datalab_stages;tourism_dong_coords;tourism_stats | UNKNOWN / no URL literal reached | INFERRED helper reachable |
| POST | /api/admin/annual-tourism-roster/preview | annual_tourism_roster_preview | app.py | 36771 | Safely stage, but do not import, an approved annual XLSX roster. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED annual_tourism_roster_stages;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/annual-tourism-roster/status | annual_tourism_roster_status | app.py | 36794 | Show the exact approved annual roster currently driving public metrics. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_stages;annual_tourism_roster_versions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/annual-tourism-roster/apply | annual_tourism_roster_apply | app.py | 36837 | Production-only approval; no master-building or registry mutation. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_stages;annual_tourism_roster_versions;app_meta;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/hotel-operation/status | hotel_operation_status | app.py | 36863 | hotel_operation_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED hotel_operation_metrics;hotel_operation_source_versions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/hotel-operation/apply | hotel_operation_apply | app.py | 36889 | hotel_operation_apply | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED hotel_operation_metrics;hotel_operation_source_versions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/tourism-datalab/checklist.xlsx | tourism_datalab_checklist | app.py | 36916 | tourism_datalab_checklist | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/stats/refresh | admin_stats_refresh | app.py | 36924 | 관리자 요청으로 통합 통계 원본 캐시를 즉시 다시 만든다. | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | INFERRED agent_buildings;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/registration-rate | stats_registration_rate | app.py | 36958 | 전국 생활숙박 객실수 대비 신고율 — 다른 숙박 유형은 모두 제외. | UNKNOWN: no recognized static guard | INFERRED agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/agent-count | stats_agent_count | app.py | 37039 | 승인(approved)된 전속중개사 수 — 메인 좌측 패널 카드용 (하우스 계정 제외). | UNKNOWN: no recognized static guard | agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/operator-counts | stats_operator_counts | app.py | 37056 | 승인(approved)된 운영업체 수 — 메인 좌측 패널 카드용 그룹 집계. | UNKNOWN: no recognized static guard | loan_consultants;operators | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/health | health | app.py | 37085 | health | UNKNOWN: no recognized static guard | sync_log;transactions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/email-banners | admin_email_banners_list | app.py | 37333 | admin_email_banners_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | email_ad_banners | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/email-banners | admin_email_banners_create | app.py | 37347 | admin_email_banners_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | email_ad_banners | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/email-banners/<int:bid> | admin_email_banners_update | app.py | 37373 | admin_email_banners_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | email_ad_banners | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PATCH | /api/admin/email-banners/<int:bid> | admin_email_banners_update | app.py | 37373 | admin_email_banners_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | email_ad_banners | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/email-banners/<int:bid> | admin_email_banners_delete | app.py | 37398 | admin_email_banners_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | email_ad_banners | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/feature-tips | admin_feature_tips_list | app.py | 37478 | admin_feature_tips_list | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | weekly_feature_tips | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/feature-tips | admin_feature_tips_create | app.py | 37497 | admin_feature_tips_create | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | weekly_feature_tips | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PATCH | /api/admin/feature-tips/<int:tip_id> | admin_feature_tips_update | app.py | 37526 | admin_feature_tips_update | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | weekly_feature_tips | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/stats/presale | presale_stats | app.py | 37859 | 허가/착공 상태이며 사용승인 전인 준공전 건물을 광역 시·도별로 집계한다. | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/presale | building_presale | app.py | 37895 | building_presale | UNKNOWN: no recognized static guard | master_buildings;presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/presale/banner/<path:key> | presale_banner | app.py | 37917 | presale_banner | UNKNOWN: no recognized static guard | presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/presale/applications | create_presale_application | app.py | 37936 | create_presale_application | UNKNOWN: no recognized static guard | master_buildings;presale_applications;presale_projects | https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/{operation} | UNKNOWN / not statically reached |
| GET | /api/admin/presale/applications | admin_presale_applications | app.py | 38038 | admin_presale_applications | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/presale/applications/<int:application_id>/document | admin_presale_application_document | app.py | 38058 | admin_presale_application_document | CONFIRMED decorator: require_admin; INFERRED guards: require_admin | presale_applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/applications/<int:application_id>/review | admin_presale_application_review | app.py | 38086 | admin_presale_application_review | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications;presale_projects | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/applications/<int:application_id>/notify | admin_presale_application_notify | app.py | 38168 | admin_presale_application_notify | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_applications | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/presale/eligible-buildings | admin_presale_eligible_buildings | app.py | 38190 | admin_presale_eligible_buildings | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications;presale_projects | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/applications/<int:application_id>/applyhome-check | admin_presale_application_applyhome_check | app.py | 38208 | admin_presale_application_applyhome_check | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications | https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/{operation} | UNKNOWN / not statically reached |
| GET | /api/admin/presale/projects | admin_presale_projects | app.py | 38227 | admin_presale_projects | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications;presale_projects | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/projects | admin_presale_projects | app.py | 38227 | admin_presale_projects | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | master_buildings;presale_applications;presale_projects | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/presale/projects/<int:project_id> | admin_presale_project | app.py | 38254 | admin_presale_project | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/presale/projects/<int:project_id> | admin_presale_project | app.py | 38254 | admin_presale_project | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/presale/promotions | admin_presale_promotions | app.py | 38275 | admin_presale_promotions | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/promotions | admin_presale_promotions | app.py | 38275 | admin_presale_promotions | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_projects;presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/presale/banners | admin_presale_banner_upload | app.py | 38298 | admin_presale_banner_upload | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/presale/promotions/<int:promotion_id> | admin_presale_promotion | app.py | 38330 | admin_presale_promotion | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/presale/promotions/<int:promotion_id> | admin_presale_promotion | app.py | 38330 | admin_presale_promotion | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/admin/presale/banners/<path:key> | admin_presale_banner_delete | app.py | 38370 | admin_presale_banner_delete | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | presale_promotions | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /auctions | auction_page | auction_service.py | 256 | auction_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /auctions/<int:item_id> | auction_detail_page | auction_service.py | 260 | auction_detail_page | UNKNOWN: no recognized static guard | INFERRED auction_items;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auctions | auction_list | auction_service.py | 266 | auction_list | UNKNOWN: no recognized static guard | app_meta | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auctions/map | auction_map | auction_service.py | 334 | auction_map | UNKNOWN: no recognized static guard | master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/auctions | building_auctions | auction_service.py | 361 | building_auctions | UNKNOWN: no recognized static guard | auction_items;auction_photos;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auctions/<int:item_id> | auction_detail | auction_service.py | 399 | auction_detail | UNKNOWN: no recognized static guard | auction_items;auction_photos;auction_rounds;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auctions/<int:item_id>/building-lookup | auction_building_lookup | auction_service.py | 464 | auction_building_lookup | UNKNOWN: no recognized static guard | auction_items | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auctions/<int:item_id>/building-lookup | auction_building_lookup | auction_service.py | 464 | auction_building_lookup | UNKNOWN: no recognized static guard | auction_items | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/onbid-status | auction_admin_status | auction_service.py | 492 | auction_admin_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;auction_items | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/building/<int:building_id>/auction-watch | auction_watch | auction_service.py | 506 | auction_watch | UNKNOWN: no recognized static guard | auction_watches;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/building/<int:building_id>/auction-watch | auction_watch | auction_service.py | 506 | auction_watch | UNKNOWN: no recognized static guard | auction_watches;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| DELETE | /api/building/<int:building_id>/auction-watch | auction_watch | auction_service.py | 506 | auction_watch | UNKNOWN: no recognized static guard | auction_watches;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/sync-onbid | auction_admin_run | auction_service.py | 532 | auction_admin_run | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/listings/registration-context | listing_registration_context | listing_extensions.py | 127 | listing_registration_context | INFERRED guards: current_user | INFERRED account_business_memberships;agents | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /admin/broker-listings | broker_listing_review_page | listing_extensions.py | 142 | broker_listing_review_page | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/broker-listings | broker_listing_review_queue | listing_extensions.py | 147 | broker_listing_review_queue | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | agents;listing_photos;listing_requests;master_buildings;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/broker-listings/<int:listing_id>/review | review_broker_listing | listing_extensions.py | 194 | review_broker_listing | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | account_business_memberships;agents;listing_request_history;listing_requests;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/membership/checks | apply_check | membership_checks.py | 69 | apply_check | INFERRED guards: current_user | INFERRED auction_items;master_buildings;membership_checks;membership_history;membership_periods;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/membership/checks/<int:check_id>/status | update_check | membership_checks.py | 80 | update_check | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | membership_checks | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/membership/me | member_me | membership_service.py | 31 | member_me | INFERRED guards: current_user | membership_checks;membership_payments;membership_periods | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/membership/payments | apply_payment | membership_service.py | 63 | apply_payment | INFERRED guards: current_user | membership_payments | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/membership/payments/<int:payment_id>/cancel | cancel_payment | membership_service.py | 102 | cancel_payment | INFERRED guards: current_user | membership_payments | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/membership/requests | admin_requests | membership_service.py | 128 | admin_requests | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | membership_checks;membership_payments;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/membership/payments/<int:payment_id>/status | approve_payment | membership_service.py | 162 | approve_payment | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | membership_payments;membership_periods;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /auctions/<int:item_id>/survey | survey_page | survey_service.py | 282 | survey_page | UNKNOWN: no recognized static guard | INFERRED auction_items;master_buildings | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /terms/survey | survey_terms_page | survey_service.py | 287 | survey_terms_page | UNKNOWN: no recognized static guard | UNKNOWN / no SQL literal | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/survey/config | survey_config | survey_service.py | 292 | survey_config | UNKNOWN: no recognized static guard | INFERRED app_meta;legal_documents;membership_periods;users | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/auctions/<int:item_id>/survey-info | survey_info | survey_service.py | 310 | survey_info | UNKNOWN: no recognized static guard | auction_items;membership_checks | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/auctions/<int:item_id>/survey-requests | survey_create | survey_service.py | 358 | survey_create | UNKNOWN: no recognized static guard | survey_request_history;survey_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/survey/settings | survey_settings | survey_service.py | 431 | survey_settings | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;survey_settings_history | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| PUT | /api/admin/survey/settings | survey_settings | survey_service.py | 431 | survey_settings | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | app_meta;survey_settings_history | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/survey/requests | survey_requests | survey_service.py | 456 | survey_requests | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | survey_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| GET | /api/admin/survey/requests/<int:request_id> | survey_request_detail | survey_service.py | 490 | survey_request_detail | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | survey_request_history;survey_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |
| POST | /api/admin/survey/requests/<int:request_id>/status | survey_status | survey_service.py | 505 | survey_status | CONFIRMED decorator: require_admin; UNKNOWN: no recognized static guard | survey_request_history;survey_requests | UNKNOWN / no URL literal reached | UNKNOWN / not statically reached |

## 외부 서비스 URL 전수 목록
애플리케이션 외부 API endpoint **39개**(고유 URL 정적 구성 기준, HTTP/OAuth/WMS 포함). 외부 URL 참조 **58개**에는 base URL·웹링크·폰트 등이 포함됩니다. 실제 활성 호출·응답 성공은 전부 UNKNOWN; 테스트 URL은 service count에서 제외했습니다.
| endpoint | inventory_class | file | line | function | transport | status |
| --- | --- | --- | --- | --- | --- | --- |
| https://api.data.go.kr/openapi/tn_pubr_public_med_office_api | API_ENDPOINT_STATIC | sync_brokers.py | 33 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://api.resend.com/emails | API_ENDPOINT_STATIC | email_util.py | 11 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://api.solapi.com/messages/v4/send | API_ENDPOINT_STATIC | sms_util.py | 16 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://api.vworld.kr/ned/data/getEBOfficeInfo | API_ENDPOINT_STATIC | vworld_broker_fetch.py | 36 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://api.vworld.kr/req/wms | API_ENDPOINT_STATIC | sync_building_photos.py | 436 | make_vworld_url | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000 | API_BASE_OR_INCOMPLETE_REFERENCE | sync_rural_hanok_trades.py | 28 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo | API_ENDPOINT_STATIC | sync_permits.py | 48 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo | API_ENDPOINT_STATIC | building_registry.py | 39 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo | API_ENDPOINT_STATIC | building_registry.py | 38 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrJijiguInfo | API_ENDPOINT_STATIC | building_registry.py | 203 | fetch_jijigu_rows | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo | API_ENDPOINT_STATIC | building_registry.py | 37 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo | API_ENDPOINT_STATIC | sync_batch.py | 50 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo | API_ENDPOINT_STATIC | sync_brhub.py | 61 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/MtnChkHubService/getMaintenanceHistory | API_ENDPOINT_STATIC | building_registry.py | 218 | fetch_maintenance_history | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade | API_ENDPOINT_STATIC | discover_new_buildings.py | 58 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade | API_ENDPOINT_STATIC | sync_batch.py | 49 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1741000 | API_BASE_OR_INCOMPLETE_REFERENCE | sync_rural_hanok.py | 32 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1741000/lodgings/info | API_ENDPOINT_STATIC | scripts/test_localdata_api.py | 9 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1741000/lodgings/info | API_ENDPOINT_STATIC | scripts/test_localdata_api.py | 26 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/1741000/lodgings/info | API_ENDPOINT_STATIC | sync_lodgings.py | 52 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B010003/ | API_BASE_OR_INCOMPLETE_REFERENCE | sync_onbid.py | 152 | call | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B551011/GoCamping/basedList | API_ENDPOINT_STATIC | sync_lodgings.py | 54 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B551011/GoCamping/imageList | API_ENDPOINT_STATIC | sync_lodgings.py | 55 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B551011/KorService2 | API_BASE_OR_INCOMPLETE_REFERENCE | static/js/main.js | 5688 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B551011/KorService2 | API_BASE_OR_INCOMPLETE_REFERENCE | sync_building_photos.py | 34 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://apis.data.go.kr/B553077/api/open/sdsc2 | API_BASE_OR_INCOMPLETE_REFERENCE | store_info_util.py | 39 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://business.juso.go.kr/addrlink/addrLinkApi.do | API_ENDPOINT_STATIC | address_utils.py | 24 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com | API_BASE_OR_INCOMPLETE_REFERENCE | static/index.html | 28 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com | API_BASE_OR_INCOMPLETE_REFERENCE | static/listings.html | 17 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/geo/coord2regioncode.json | API_ENDPOINT_STATIC | import_tourism_stats.py | 1145 | refresh_building_dong_matches | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/address.json | API_ENDPOINT_STATIC | app.py | 35184 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/address.json | API_ENDPOINT_STATIC | geocode_brokers.py | 10 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/address.json | API_ENDPOINT_STATIC | geocode_brokers.py | 37 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/address.json | API_ENDPOINT_STATIC | geocode_buildings.py | 9 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/address.json | API_ENDPOINT_STATIC | geocode_buildings.py | 41 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/category.json | API_ENDPOINT_STATIC | app.py | 4158 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/keyword.json | API_ENDPOINT_STATIC | app.py | 35183 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/keyword.json | API_ENDPOINT_STATIC | import_tourism_stats.py | 648 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://dapi.kakao.com/v2/local/search/keyword.json | API_ENDPOINT_STATIC | import_tourism_stats.py | 1046 | geocode_missing_dong_coords | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | artifacts/mockup-sandbox/dist/index.html | 21 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | artifacts/mockup-sandbox/index.html | 21 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/agent_dashboard.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/agent_profile.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/agents.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/apply_agent.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/apply_edit.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/apply_loan_consultant.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/apply_operator.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/auctions.html | 10 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/building.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/guide.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/index.html | 27 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/listings.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/loan_consultant_dashboard.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/loan_consultant_profile.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/loan_consultants_list.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/loan_partners.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/membership.html | 10 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/menu.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/mypage.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/notices.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/operator_dashboard.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/operator_profile.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/operators.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/partner.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/partners_directory.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com | FONT_ASSET | static/transactions.html | 13 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/dist/assets/_group-panxU72g.css | 1 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/dist/index.html | 24 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/dist/index.html | 25 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/index.html | 24 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/index.html | 25 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/src/components/mockups/analysis-photo/_group.css | 1 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | artifacts/mockup-sandbox/src/components/mockups/property-purchase/_group.css | 1 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/agent_dashboard.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/agent_profile.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/agents.html | 15 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/apply_agent.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/apply_edit.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/apply_loan_consultant.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/apply_operator.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/auctions.html | 11 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/building.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/css/analysis.css | 1 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/guide.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/index.html | 30 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/listings.html | 15 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/loan_consultant_dashboard.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/loan_consultant_profile.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/loan_consultants_list.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/loan_partners.html | 15 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/membership.html | 11 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/menu.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/mypage.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/notices.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/operator_dashboard.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/operator_profile.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/operators.html | 15 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/partner.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/partners_directory.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://fonts.googleapis.com/css2 | FONT_ASSET | static/transactions.html | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://gocamping.or.kr | WEB_REFERENCE_OR_ENRICHMENT | backfill_gocamping_web.py | 20 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://kapi.kakao.com/v2/user/me | API_ENDPOINT_STATIC | app.py | 10006 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://kauth.kakao.com/oauth/authorize | API_ENDPOINT_STATIC | app.py | 10004 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://kauth.kakao.com/oauth/token | API_ENDPOINT_STATIC | app.py | 10005 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://map.kakao.com/link/map/ | EXTERNAL_WEB_OR_DEEP_LINK | static/js/listing_modal.js | 1731 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://maps.googleapis.com/maps/api/streetview | API_ENDPOINT_STATIC | app.py | 1389 | fetch_and_score | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://maps.googleapis.com/maps/api/streetview | API_ENDPOINT_STATIC | sync_building_photos.py | 418 | make_streetview_url | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://maps.googleapis.com/maps/api/streetview/metadata | API_ENDPOINT_STATIC | app.py | 844 | _google_streetview_metadata | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://maps.googleapis.com/maps/api/streetview/metadata | API_ENDPOINT_STATIC | sync_building_photos.py | 645 | _streetview_available | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://open.kakao.com/... | EXTERNAL_WEB_OR_DEEP_LINK | static/admin.html | 10339 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://open.kakao.com/o/... | EXTERNAL_WEB_OR_DEEP_LINK | static/apply_edit.html | 91 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://open.kakao.com/o/... | EXTERNAL_WEB_OR_DEEP_LINK | static/apply_loan_consultant.html | 44 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://open.kakao.com/o/… | EXTERNAL_WEB_OR_DEEP_LINK | static/loan_consultant_dashboard.html | 167 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.data.go.kr/data/15013205/standard.do | WEB_REFERENCE_OR_ENRICHMENT | import_subway_stations.py | 9 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.data.go.kr/data/15013205/standard.do | WEB_REFERENCE_OR_ENRICHMENT | import_subway_stations.py | 29 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.gocamping.or.kr | WEB_REFERENCE_OR_ENRICHMENT | db.py | 3653 | _run_init_db | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.gocamping.or.kr/bsite/camp/info/read.do | WEB_REFERENCE_OR_ENRICHMENT | app.py | 6294 | _gocamping_url_for_registry_key | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.gocamping.or.kr/bsite/camp/info/read.do | WEB_REFERENCE_OR_ENRICHMENT | app.py | 6301 | _gocamping_url_for_content_id | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.juso.go.kr/addrlink/addrLinkApi.do | API_ENDPOINT_STATIC | address_utils.py | 25 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://www.juso.go.kr/addrlink/openApi/searchApi.do | API_ENDPOINT_STATIC | address_utils.py | 7 | <module> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED literal; availability UNKNOWN |
| https://www.onbid.co.kr/op/cltrpbancinf/cltrdtl/CltrDtlController/mvmnCltrDtl.do | EXTERNAL_WEB_OR_DEEP_LINK | auction_domain.py | 223 | normalize | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://www.vworld.kr | WEB_REFERENCE_OR_ENRICHMENT | static/js/listing_checklist.js | 14 | <module> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED literal; availability UNKNOWN |
| https://kauth.kakao.com/oauth/authorize | API_ENDPOINT_STATIC | app.py | 10031 | kakao_start | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInPnu | API_ENDPOINT_STATIC | store_info_util.py | 40 | <module constant> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInBuilding | API_ENDPOINT_STATIC | store_info_util.py | 41 | <module constant> | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/B551011/KorService2/searchKeyword2 | API_ENDPOINT_STATIC | sync_building_photos.py | 443 | _tour_search | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/B551011/KorService2/detailImage2 | API_ENDPOINT_STATIC | sync_building_photos.py | 471 | _tour_images | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/1741000//info | API_BASE_OR_INCOMPLETE_REFERENCE | sync_rural_hanok.py | 190 | _fetch_page | DIRECT / SDK / URL reference; not in four-service relay allowlist | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade | API_ENDPOINT_STATIC | sync_rural_hanok_trades.py | 30 | <module constant> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade | API_ENDPOINT_STATIC | sync_rural_hanok_trades.py | 31 | <module constant> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade | API_ENDPOINT_STATIC | sync_rural_hanok_trades.py | 32 | <module constant> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade | API_ENDPOINT_STATIC | sync_rural_hanok_trades.py | 33 | <module constant> | CONDITIONAL_RELAY (on switch) / DIRECT (off switch) | CONFIRMED static construction; placeholders unresolved where shown |
| https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2 | API_ENDPOINT_STATIC | auction_domain.py + sync_onbid.py | 9-13;152 | ENDPOINTS[list] / upstream call | CONDITIONAL_RELAY / DIRECT when disabled | CONFIRMED constant + concatenation |
| https://apis.data.go.kr/B010003/OnbidRlstDtlSrvc2/getRlstDtlInf2 | API_ENDPOINT_STATIC | auction_domain.py + sync_onbid.py | 9-13;152 | ENDPOINTS[detail] / upstream call | CONDITIONAL_RELAY / DIRECT when disabled | CONFIRMED constant + concatenation |
| https://apis.data.go.kr/B010003/OnbidCltrBidDtlSrvc2/getCltrBidInf2 | API_ENDPOINT_STATIC | auction_domain.py + sync_onbid.py | 9-13;152 | ENDPOINTS[bid] / upstream call | CONDITIONAL_RELAY / DIRECT when disabled | CONFIRMED constant + concatenation |
| https://apis.data.go.kr/B010003/OnbidPbancDtlnfSrvc2/getPbancDtlInf2 | API_ENDPOINT_STATIC | auction_domain.py + sync_onbid.py | 9-13;152 | ENDPOINTS[notice] / upstream call | CONDITIONAL_RELAY / DIRECT when disabled | CONFIRMED constant + concatenation |
| https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do | API_ENDPOINT_STATIC | sync_rone_rental_benchmarks.py | 15 | API_URL / benchmark sync | DIRECT (outside relay allowlist) | CONFIRMED static reference |


---

<!-- 03_DATABASE_SCHEMA.md -->

# 운영 DB schema 전수조사

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 운영 schema 요약
CONFIRMED 135 tables/relations, 1625 columns, 503 constraints, 380 indexes, 116 sequences.

row count는 명시된 COUNT(*) 외에는 통계 추정치(reltuples)입니다. -1은 미확인이지 빈 테이블이 아닙니다. 서비스 화면 수치와 동일하지 않습니다.
| table_name | relkind | row_count | row_count_basis | total_bytes |
| --- | --- | --- | --- | --- |
| account_business_memberships | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| account_role_memberships | r | 54 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| admin_edit_log | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| admin_event_subscriptions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| admin_notification_deliveries | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| admin_notification_email_attempt_history | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| admin_notification_email_attempts | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| admin_notifications | r | 51 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 98304 |
| admin_users | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| agency_links | r | 5 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| agent_buildings | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| agent_region_buildings | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| agent_service_regions | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| agents | r | 3 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| analysis_assets_cache | r | 3 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 1851392 |
| analysis_source_versions | r | 3 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 106496 |
| annual_tourism_roster_building_evidence | r | 2996 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 360448 |
| annual_tourism_roster_entries | r | 2996 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 1114112 |
| annual_tourism_roster_stages | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 1015808 |
| annual_tourism_roster_versions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| app_meta | r | 3706 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 3375104 |
| applications | r | 11 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| auction_items | r | 8883 | CONFIRMED COUNT(*) at query time | 115130368 |
| auction_photos | r | 7063 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 5677056 |
| auction_rounds | r | 34166 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 12460032 |
| auction_watches | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 8192 |
| booking_url_requests | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| broker_registry | r | 66062 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 58572800 |
| broker_registry_members | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| bug_reports | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| building_photo_fetches | r | 3251 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 901120 |
| building_photos | r | 1256 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 1007616 |
| building_requests | r | 21 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| building_stores | r | 10603 | CONFIRMED COUNT(*) at query time | 1359872 |
| building_unit_areas | r | 1115 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 204800 |
| business_building_verifications | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| business_room_inventory | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 98304 |
| buy_requests | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| chat_messages | r | 11 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| chat_rooms | r | 6 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 73728 |
| deal_alert_logs | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| discover_progress | r | 2806 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 294912 |
| email_ad_banners | r | 3 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| gocamping_records | r | 1997 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 10117120 |
| hotel_operation_metrics | r | 1266 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 770048 |
| hotel_operation_source_versions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| legal_documents | r | 2 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 106496 |
| listing_checklist_progress | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| listing_likes | r | 7 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 57344 |
| listing_photos | r | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| listing_request_deletion_archive | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| listing_request_history | r | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 147456 |
| listing_requests | r | 28 | CONFIRMED COUNT(*) at query time | 131072 |
| listings | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| loan_consult_requests | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| loan_consultant_buildings | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| loan_consultant_service_areas | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| loan_consultants | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| lodging_approval_attempts | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| lodging_approval_batches | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| lodging_approval_rows | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| lodging_authority_contacts | r | 135 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 73728 |
| lodging_import_staging | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| lodging_operator_phone_challenges | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| lodging_parallel_comparisons | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| lodging_promotion_manifests | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| lodging_promotion_review_decisions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| lodging_promotion_rows | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| lodging_registry | r | 145631 | CONFIRMED COUNT(*) at query time | 126156800 |
| lodging_registry_alert_snapshots | r | 54049 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 11026432 |
| lodging_source_batches | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| lodging_source_rows | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| login_history | r | 111 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 98304 |
| master_buildings | r | 85617 | CONFIRMED COUNT(*) at query time | 98500608 |
| member_documents | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| member_notes | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| membership_checks | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| membership_history | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| membership_payments | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 98304 |
| membership_periods | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| mileage_missions | r | 8 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| mileage_submissions | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| new_listing_alert_logs | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| notices | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| notifications | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| operator_buildings | r | 3 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| operator_consult_requests | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| operator_lodging | r | 2 | CONFIRMED COUNT(*) at query time | 106496 |
| operator_lodging_photos | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| operator_region_buildings | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| operator_service_areas | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| operator_service_regions | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| operators | r | 5 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| page_views | r | 23993 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 7380992 |
| partner_favorites | r | 5 | CONFIRMED COUNT(*) at query time | 90112 |
| password_reset_tokens | r | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| permit_change_alert_deliveries | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| permit_change_alert_logs | r | 18 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| point_transactions | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| policy_document_revisions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| policy_documents | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| premium_waitlist | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| presale_applications | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| presale_audit_log | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| presale_projects | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| presale_promotions | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| region_badge_waitlist | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| revenue_records | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| rone_rental_benchmarks | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| room_expiry_alerts_sent | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 40960 |
| sgg_coords | r | 285 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 188416 |
| short_links | r | 6 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| site_popups | r | 2 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| slots | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| streetview_evaluation_metrics | r | 32 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 57344 |
| subway_stations | r | 1098 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 344064 |
| survey_request_history | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| survey_requests | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| survey_settings_history | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 16384 |
| sync_failures | r | 11521 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 2646016 |
| sync_log | r | 69 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 73728 |
| title_info_backfill_failures | r | 1071 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 8396800 |
| tourism_building_dong_matches | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 24576 |
| tourism_datalab_stages | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 114688 |
| tourism_dong_coords | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| tourism_stats | r | 3599 | CONFIRMED COUNT(*) at query time | 7036928 |
| transactions | r | 19094 | CONFIRMED COUNT(*) at query time | 13860864 |
| urgent_listing_alert_logs | r | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |
| user_alert_subscriptions | r | 13 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 81920 |
| user_favorites | r | 52 | CONFIRMED COUNT(*) at query time | 172032 |
| user_recent_analysis | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 49152 |
| users | r | 63 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 106496 |
| weekly_email_deliveries | r | 104 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 270336 |
| weekly_email_reports | r | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 32768 |
| weekly_feature_tips | r | 8 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN | 65536 |


## master_buildings.id 의존성
| table_name | name | definition |
| --- | --- | --- |
| agent_buildings | agent_buildings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| agent_region_buildings | agent_region_buildings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| annual_tourism_roster_building_evidence | annual_tourism_roster_building_evidence_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| applications | applications_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) |
| applications | applications_preferred_building_id_fkey | FOREIGN KEY (preferred_building_id) REFERENCES master_buildings(id) |
| auction_items | auction_items_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| auction_watches | auction_watches_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| booking_url_requests | booking_url_requests_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| building_photo_fetches | building_photo_fetches_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| building_photos | building_photos_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| building_stores | building_stores_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| building_unit_areas | building_unit_areas_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| business_building_verifications | business_building_verifications_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| buy_requests | buy_requests_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| listing_requests | listing_requests_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| listings | listings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| loan_consult_requests | loan_consult_requests_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| loan_consultant_buildings | loan_consultant_buildings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| lodging_registry | lodging_registry_applied_building_id_fkey | FOREIGN KEY (applied_building_id) REFERENCES master_buildings(id) |
| lodging_registry_alert_snapshots | lodging_registry_alert_snapshots_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| mileage_submissions | mileage_submissions_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| notifications | notifications_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| operator_buildings | operator_buildings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| operator_consult_requests | operator_consult_requests_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| operator_lodging | operator_lodging_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| operator_region_buildings | operator_region_buildings_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| partner_favorites | partner_favorites_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| permit_change_alert_logs | permit_change_alert_logs_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| premium_waitlist | premium_waitlist_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| presale_applications | presale_applications_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE RESTRICT |
| presale_projects | presale_projects_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE RESTRICT |
| slots | slots_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| survey_requests | survey_requests_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| title_info_backfill_failures | title_info_backfill_failures_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| tourism_building_dong_matches | tourism_building_dong_matches_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| tourism_stats | tourism_stats_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| transactions | transactions_master_building_id_fkey | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| user_recent_analysis | user_recent_analysis_building_id_fkey | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |

### FK 미확인 논리 연결
| table_name | column_name | status |
| --- | --- | --- |
| building_requests | master_building_id | INFERRED logical reference; no matching master FK |
| membership_checks | building_id | INFERRED logical reference; no matching master FK |
| user_favorites | master_building_id | INFERRED logical reference; no matching master FK |


## 전체 테이블별 columns / PK / FK / UNIQUE / CHECK / INDEX
### account_business_memberships
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('account_business_memberships_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| role | text | text | NO |  | NO |
| business_id | integer | int4 | NO |  | NO |
| business_table | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | account_business_memberships_business_table_check | - | CHECK ((business_table = ANY (ARRAY['agents'::text, 'operators'::text, 'loan_consultants'::text, 'operator_lodging'::text]))) |
| p | account_business_memberships_pkey | - | PRIMARY KEY (id) |
| c | account_business_memberships_role_check | - | CHECK ((role = ANY (ARRAY['agent'::text, 'operator'::text, 'loan_consultant'::text, 'lodging_operator'::text]))) |
| f | account_business_memberships_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | account_business_memberships_user_id_role_business_table_bu_key | - | UNIQUE (user_id, role, business_table, business_id) |
| indexname | indexdef |
| --- | --- |
| account_business_memberships_pkey | CREATE UNIQUE INDEX account_business_memberships_pkey ON public.account_business_memberships USING btree (id) |
| account_business_memberships_user_id_role_business_table_bu_key | CREATE UNIQUE INDEX account_business_memberships_user_id_role_business_table_bu_key ON public.account_business_memberships USING btree (user_id, role, business_table, business_id) |
| account_business_memberships_user_idx | CREATE INDEX account_business_memberships_user_idx ON public.account_business_memberships USING btree (user_id, status, role) |

### account_role_memberships
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('account_role_memberships_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| role | text | text | NO |  | NO |
| legacy_account_id | integer | int4 | YES |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | account_role_memberships_pkey | - | PRIMARY KEY (id) |
| c | account_role_memberships_role_check | - | CHECK ((role = ANY (ARRAY['general'::text, 'agent'::text, 'operator'::text, 'loan_consultant'::text, 'lodging_operator'::text]))) |
| f | account_role_memberships_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | account_role_memberships_user_id_role_legacy_account_id_key | - | UNIQUE (user_id, role, legacy_account_id) |
| indexname | indexdef |
| --- | --- |
| account_role_memberships_pkey | CREATE UNIQUE INDEX account_role_memberships_pkey ON public.account_role_memberships USING btree (id) |
| account_role_memberships_user_id_role_legacy_account_id_key | CREATE UNIQUE INDEX account_role_memberships_user_id_role_legacy_account_id_key ON public.account_role_memberships USING btree (user_id, role, legacy_account_id) |
| account_role_memberships_user_idx | CREATE INDEX account_role_memberships_user_idx ON public.account_role_memberships USING btree (user_id, status, role) |

### admin_edit_log
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('admin_edit_log_id_seq'::regclass) | NO |
| table_name | text | text | NO |  | NO |
| record_id | integer | int4 | NO |  | NO |
| field | text | text | NO |  | NO |
| old_value | text | text | YES |  | NO |
| new_value | text | text | YES |  | NO |
| reason | text | text | NO |  | NO |
| admin | boolean | bool | YES | true | NO |
| edited_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | admin_edit_log_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| admin_edit_log_pkey | CREATE UNIQUE INDEX admin_edit_log_pkey ON public.admin_edit_log USING btree (id) |

### admin_event_subscriptions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| admin_user_id | integer | int4 | NO |  | NO |
| event_type | text | text | NO |  | NO |
| in_app_enabled | boolean | bool | NO | true | NO |
| email_enabled | boolean | bool | NO | false | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | admin_event_subscriptions_admin_user_id_fkey | admin_users | FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE |
| c | admin_event_subscriptions_event_type_check | - | CHECK ((event_type = ANY (ARRAY['new_signup'::text, 'direct_listing'::text, 'broker_listing_request'::text, 'buy_request'::text, 'partner_agent'::text, 'partner_operator'::text, 'partner_loan_consultant'::text, 'partner_lodging_operator'::text, 'ota_booking_link_request'::text, 'survey_request'::text]))) |
| p | admin_event_subscriptions_pkey | - | PRIMARY KEY (admin_user_id, event_type) |
| indexname | indexdef |
| --- | --- |
| admin_event_subscriptions_pkey | CREATE UNIQUE INDEX admin_event_subscriptions_pkey ON public.admin_event_subscriptions USING btree (admin_user_id, event_type) |

### admin_notification_deliveries
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('admin_notification_deliveries_id_seq'::regclass) | NO |
| channel | text | text | NO |  | NO |
| idempotency_key | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| provider_message | text | text | YES |  | NO |
| attempted_at | timestamp with time zone | timestamptz | NO | now() | NO |
| sent_at | timestamp with time zone | timestamptz | YES |  | NO |
| source_kind | text | text | YES |  | NO |
| source_id | bigint | int8 | YES |  | NO |
| label | text | text | YES |  | NO |
| attempting_at | timestamp with time zone | timestamptz | YES |  | NO |
| attempts | integer | int4 | NO | 0 | NO |
| next_attempt_at | timestamp with time zone | timestamptz | NO | now() | NO |
| outcome | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | admin_notification_deliveries_channel_check | - | CHECK ((channel = ANY (ARRAY['immediate'::text, 'daily_digest'::text]))) |
| u | admin_notification_deliveries_channel_idempotency_key_key | - | UNIQUE (channel, idempotency_key) |
| p | admin_notification_deliveries_pkey | - | PRIMARY KEY (id) |
| c | admin_notification_deliveries_status_check | - | CHECK ((status = ANY (ARRAY['pending'::text, 'attempting'::text, 'sent'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| admin_notification_deliveries_channel_idempotency_key_key | CREATE UNIQUE INDEX admin_notification_deliveries_channel_idempotency_key_key ON public.admin_notification_deliveries USING btree (channel, idempotency_key) |
| admin_notification_deliveries_pkey | CREATE UNIQUE INDEX admin_notification_deliveries_pkey ON public.admin_notification_deliveries USING btree (id) |
| idx_admin_delivery_dispatch | CREATE INDEX idx_admin_delivery_dispatch ON public.admin_notification_deliveries USING btree (channel, status, next_attempt_at) |

### admin_notification_email_attempt_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('admin_notification_email_attempt_history_id_seq'::regclass) | NO |
| email_attempt_id | bigint | int8 | NO |  | NO |
| status | text | text | NO |  | NO |
| message | text | text | YES |  | NO |
| attempted_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | admin_notification_email_attempt_history_email_attempt_id_fkey | admin_notification_email_attempts | FOREIGN KEY (email_attempt_id) REFERENCES admin_notification_email_attempts(id) ON DELETE CASCADE |
| p | admin_notification_email_attempt_history_pkey | - | PRIMARY KEY (id) |
| c | admin_notification_email_attempt_history_status_check | - | CHECK ((status = ANY (ARRAY['sent'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| admin_notification_email_attempt_history_pkey | CREATE UNIQUE INDEX admin_notification_email_attempt_history_pkey ON public.admin_notification_email_attempt_history USING btree (id) |
| idx_admin_notification_email_history_attempt | CREATE INDEX idx_admin_notification_email_history_attempt ON public.admin_notification_email_attempt_history USING btree (email_attempt_id, attempted_at DESC) |

### admin_notification_email_attempts
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('admin_notification_email_attempts_id_seq'::regclass) | NO |
| notification_id | bigint | int8 | NO |  | NO |
| recipient_email | text | text | NO |  | NO |
| idempotency_key | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| attempt_count | integer | int4 | NO | 0 | NO |
| last_attempt_at | timestamp with time zone | timestamptz | YES |  | NO |
| sent_at | timestamp with time zone | timestamptz | YES |  | NO |
| error_message | text | text | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | admin_notification_email_attempts_idempotency_key_key | - | UNIQUE (idempotency_key) |
| f | admin_notification_email_attempts_notification_id_fkey | admin_notifications | FOREIGN KEY (notification_id) REFERENCES admin_notifications(id) ON DELETE CASCADE |
| u | admin_notification_email_attempts_notification_id_key | - | UNIQUE (notification_id) |
| p | admin_notification_email_attempts_pkey | - | PRIMARY KEY (id) |
| c | admin_notification_email_attempts_status_check | - | CHECK ((status = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| admin_notification_email_attempts_idempotency_key_key | CREATE UNIQUE INDEX admin_notification_email_attempts_idempotency_key_key ON public.admin_notification_email_attempts USING btree (idempotency_key) |
| admin_notification_email_attempts_notification_id_key | CREATE UNIQUE INDEX admin_notification_email_attempts_notification_id_key ON public.admin_notification_email_attempts USING btree (notification_id) |
| admin_notification_email_attempts_pkey | CREATE UNIQUE INDEX admin_notification_email_attempts_pkey ON public.admin_notification_email_attempts USING btree (id) |
| idx_admin_notification_email_pending | CREATE INDEX idx_admin_notification_email_pending ON public.admin_notification_email_attempts USING btree (status, created_at) |

### admin_notifications
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('admin_notifications_id_seq'::regclass) | NO |
| admin_user_id | integer | int4 | NO |  | NO |
| event_type | text | text | NO |  | NO |
| source_table | text | text | NO |  | NO |
| source_id | bigint | int8 | NO |  | NO |
| title | text | text | NO |  | NO |
| body | text | text | NO | <literal-redacted>::text | NO |
| deep_link | text | text | NO |  | NO |
| in_app_enabled | boolean | bool | NO | true | NO |
| read_at | timestamp with time zone | timestamptz | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | admin_notifications_admin_user_id_event_type_source_table_s_key | - | UNIQUE (admin_user_id, event_type, source_table, source_id) |
| f | admin_notifications_admin_user_id_fkey | admin_users | FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE |
| p | admin_notifications_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| admin_notifications_admin_user_id_event_type_source_table_s_key | CREATE UNIQUE INDEX admin_notifications_admin_user_id_event_type_source_table_s_key ON public.admin_notifications USING btree (admin_user_id, event_type, source_table, source_id) |
| admin_notifications_pkey | CREATE UNIQUE INDEX admin_notifications_pkey ON public.admin_notifications USING btree (id) |
| idx_admin_notifications_inbox | CREATE INDEX idx_admin_notifications_inbox ON public.admin_notifications USING btree (admin_user_id, read_at, created_at DESC) |

### admin_users
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('admin_users_id_seq'::regclass) | NO |
| email | text | text | NO |  | NO |
| password_hash | text | text | NO |  | NO |
| name | text | text | YES |  | NO |
| role | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| last_login_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | admin_users_email_unique | - | UNIQUE (email) |
| p | admin_users_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| admin_users_email_unique | CREATE UNIQUE INDEX admin_users_email_unique ON public.admin_users USING btree (email) |
| admin_users_pkey | CREATE UNIQUE INDEX admin_users_pkey ON public.admin_users USING btree (id) |

### agency_links
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('agency_links_id_seq'::regclass) | NO |
| name | text | text | NO |  | NO |
| logo_url | text | text | YES |  | NO |
| link_url | text | text | NO |  | NO |
| display_order | integer | int4 | YES | 0 | NO |
| is_active | boolean | bool | YES | true | NO |
| created_at | timestamp with time zone | timestamptz | YES | now() | NO |
| updated_at | timestamp with time zone | timestamptz | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | agency_links_link_url_key | - | UNIQUE (link_url) |
| p | agency_links_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| agency_links_link_url_key | CREATE UNIQUE INDEX agency_links_link_url_key ON public.agency_links USING btree (link_url) |
| agency_links_link_url_uidx | CREATE UNIQUE INDEX agency_links_link_url_uidx ON public.agency_links USING btree (link_url) |
| agency_links_pkey | CREATE UNIQUE INDEX agency_links_pkey ON public.agency_links USING btree (id) |

### agent_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('agent_buildings_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| sale_count | integer | int4 | YES | 0 | NO |
| jeonse_count | integer | int4 | YES | 0 | NO |
| wolse_count | integer | int4 | YES | 0 | NO |
| shortterm_count | integer | int4 | YES | 0 | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| presale_count | integer | int4 | YES | 0 | NO |
| has_priority_badge | boolean | bool | YES | false | NO |
| premium_granted_at | timestamp without time zone | timestamp | YES |  | NO |
| premium_expires_at | timestamp without time zone | timestamp | YES |  | NO |
| reminder_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| is_paid | boolean | bool | YES | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | agent_buildings_agent_building_unique | - | UNIQUE (agent_id, master_building_id) |
| f | agent_buildings_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| f | agent_buildings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | agent_buildings_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| agent_buildings_agent_building_unique | CREATE UNIQUE INDEX agent_buildings_agent_building_unique ON public.agent_buildings USING btree (agent_id, master_building_id) |
| agent_buildings_pkey | CREATE UNIQUE INDEX agent_buildings_pkey ON public.agent_buildings USING btree (id) |

### agent_region_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('agent_region_buildings_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| added_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | agent_region_buildings_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| f | agent_region_buildings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | agent_region_buildings_pkey | - | PRIMARY KEY (id) |
| u | agent_region_buildings_unique | - | UNIQUE (agent_id, master_building_id) |
| indexname | indexdef |
| --- | --- |
| agent_region_buildings_pkey | CREATE UNIQUE INDEX agent_region_buildings_pkey ON public.agent_region_buildings USING btree (id) |
| agent_region_buildings_unique | CREATE UNIQUE INDEX agent_region_buildings_unique ON public.agent_region_buildings USING btree (agent_id, master_building_id) |

### agent_service_regions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('agent_service_regions_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| sgg_text | text | text | NO |  | NO |
| granted_at | timestamp without time zone | timestamp | YES | now() | NO |
| expires_at | timestamp without time zone | timestamp | NO |  | NO |
| reminder_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| is_paid | boolean | bool | YES | false | NO |
| umd_nm | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | agent_service_regions_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| p | agent_service_regions_pkey | - | PRIMARY KEY (id) |
| u | agent_service_regions_unique | - | UNIQUE (agent_id, sgg_text) |
| indexname | indexdef |
| --- | --- |
| agent_service_regions_pkey | CREATE UNIQUE INDEX agent_service_regions_pkey ON public.agent_service_regions USING btree (id) |
| agent_service_regions_unique | CREATE UNIQUE INDEX agent_service_regions_unique ON public.agent_service_regions USING btree (agent_id, sgg_text) |
| idx_agent_service_regions_sgg_expiry | CREATE INDEX idx_agent_service_regions_sgg_expiry ON public.agent_service_regions USING btree (sgg_text, expires_at) |

### agents
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('agents_id_seq'::regclass) | NO |
| office_name | text | text | NO |  | NO |
| owner_name | text | text | NO |  | NO |
| reg_number | text | text | YES |  | NO |
| biz_reg_number | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| email | text | text | NO |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| subdomain_slug | text | text | YES |  | NO |
| intro_text | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| approved_at | timestamp without time zone | timestamp | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| password_hash | text | text | YES |  | NO |
| photo_url | text | text | YES |  | NO |
| admin_tag | text | text | YES |  | NO |
| logo_url | text | text | YES |  | NO |
| is_visible | boolean | bool | YES | true | NO |
| priority_score | integer | int4 | YES | 0 | NO |
| admin_memo | text | text | YES |  | NO |
| intro_title | text | text | YES |  | NO |
| office_phone | text | text | YES |  | NO |
| office_address | text | text | YES |  | NO |
| tax_invoice_email | text | text | YES |  | NO |
| rejection_reason | text | text | YES |  | NO |
| manager_name | text | text | YES |  | NO |
| desired_building | text | text | YES |  | NO |
| weekly_email_enabled | boolean | bool | NO | true | NO |
| weekly_email_opted_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_email_updated_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_unsubscribe_token | uuid | uuid | NO | gen_random_uuid() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | agents_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) |
| p | agents_pkey | - | PRIMARY KEY (id) |
| u | agents_reg_number_unique | - | UNIQUE (reg_number) |
| u | agents_subdomain_slug_unique | - | UNIQUE (subdomain_slug) |
| indexname | indexdef |
| --- | --- |
| agents_pkey | CREATE UNIQUE INDEX agents_pkey ON public.agents USING btree (id) |
| agents_reg_number_unique | CREATE UNIQUE INDEX agents_reg_number_unique ON public.agents USING btree (reg_number) |
| agents_subdomain_slug_unique | CREATE UNIQUE INDEX agents_subdomain_slug_unique ON public.agents USING btree (subdomain_slug) |
| uq_agents_weekly_unsubscribe_token | CREATE UNIQUE INDEX uq_agents_weekly_unsubscribe_token ON public.agents USING btree (weekly_unsubscribe_token) |

### analysis_assets_cache
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| cache_kind | text | text | NO |  | NO |
| cache_key | text | text | NO |  | NO |
| source_version | text | text | NO |  | NO |
| payload | jsonb | jsonb | NO |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | analysis_assets_cache_pkey | - | PRIMARY KEY (cache_kind, cache_key) |
| indexname | indexdef |
| --- | --- |
| analysis_assets_cache_pkey | CREATE UNIQUE INDEX analysis_assets_cache_pkey ON public.analysis_assets_cache USING btree (cache_kind, cache_key) |

### analysis_source_versions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| source_name | text | text | NO |  | NO |
| version | bigint | int8 | NO | 0 | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | analysis_source_versions_pkey | - | PRIMARY KEY (source_name) |
| indexname | indexdef |
| --- | --- |
| analysis_source_versions_pkey | CREATE UNIQUE INDEX analysis_source_versions_pkey ON public.analysis_source_versions USING btree (source_name) |

### annual_tourism_roster_building_evidence
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| entry_id | bigint | int8 | NO |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| match_method | text | text | NO |  | NO |
| match_status | text | text | NO |  | NO |
| checked_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | annual_tourism_roster_building_evidence_entry_id_fkey | annual_tourism_roster_entries | FOREIGN KEY (entry_id) REFERENCES annual_tourism_roster_entries(id) ON DELETE CASCADE |
| f | annual_tourism_roster_building_evidence_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| c | annual_tourism_roster_building_evidence_match_status_check | - | CHECK ((match_status = ANY (ARRAY['matched'::text, 'unmatched'::text, 'ambiguous'::text, 'conflict'::text]))) |
| p | annual_tourism_roster_building_evidence_pkey | - | PRIMARY KEY (entry_id) |
| indexname | indexdef |
| --- | --- |
| annual_tourism_roster_building_evidence_pkey | CREATE UNIQUE INDEX annual_tourism_roster_building_evidence_pkey ON public.annual_tourism_roster_building_evidence USING btree (entry_id) |

### annual_tourism_roster_entries
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('annual_tourism_roster_entries_id_seq'::regclass) | NO |
| version_id | bigint | int8 | NO |  | NO |
| source_row_number | integer | int4 | NO |  | NO |
| sido_name | text | text | NO | <literal-redacted>::text | NO |
| sgg_name | text | text | NO | <literal-redacted>::text | NO |
| facility_name | text | text | NO | <literal-redacted>::text | NO |
| address | text | text | NO | <literal-redacted>::text | NO |
| address_norm | text | text | NO | <literal-redacted>::text | NO |
| subtype | text | text | NO |  | NO |
| raw_subtype | text | text | NO | <literal-redacted>::text | NO |
| raw_status | text | text | NO | <literal-redacted>::text | NO |
| is_active | boolean | bool | NO | false | NO |
| room_count | integer | int4 | NO | 0 | NO |
| tourism_operator_name | text | text | NO | <literal-redacted>::text | NO |
| hotel_grade | text | text | NO | <literal-redacted>::text | NO |
| grade_date | text | text | NO | <literal-redacted>::text | NO |
| floor_count | text | text | NO | <literal-redacted>::text | NO |
| land_area | text | text | NO | <literal-redacted>::text | NO |
| gross_floor_area | text | text | NO | <literal-redacted>::text | NO |
| registration_number | text | text | NO | <literal-redacted>::text | NO |
| registration_date | text | text | NO | <literal-redacted>::text | NO |
| approval_date | text | text | NO | <literal-redacted>::text | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | annual_tourism_roster_entries_pkey | - | PRIMARY KEY (id) |
| c | annual_tourism_roster_entries_room_count_check | - | CHECK ((room_count >= 0)) |
| f | annual_tourism_roster_entries_version_id_fkey | annual_tourism_roster_versions | FOREIGN KEY (version_id) REFERENCES annual_tourism_roster_versions(id) ON DELETE CASCADE |
| u | annual_tourism_roster_entries_version_id_source_row_number_key | - | UNIQUE (version_id, source_row_number) |
| indexname | indexdef |
| --- | --- |
| annual_tourism_roster_entries_pkey | CREATE UNIQUE INDEX annual_tourism_roster_entries_pkey ON public.annual_tourism_roster_entries USING btree (id) |
| annual_tourism_roster_entries_version_id_source_row_number_key | CREATE UNIQUE INDEX annual_tourism_roster_entries_version_id_source_row_number_key ON public.annual_tourism_roster_entries USING btree (version_id, source_row_number) |

### annual_tourism_roster_stages
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| token | text | text | NO |  | NO |
| admin_user_id | integer | int4 | NO |  | NO |
| manifest | jsonb | jsonb | NO |  | NO |
| state | text | text | NO |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| expires_at | timestamp with time zone | timestamptz | NO |  | NO |
| applied_at | timestamp with time zone | timestamptz | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | annual_tourism_roster_stages_pkey | - | PRIMARY KEY (token) |
| c | annual_tourism_roster_stages_state_check | - | CHECK ((state = ANY (ARRAY['previewed'::text, 'applying'::text, 'applied'::text]))) |
| indexname | indexdef |
| --- | --- |
| annual_tourism_roster_stages_pkey | CREATE UNIQUE INDEX annual_tourism_roster_stages_pkey ON public.annual_tourism_roster_stages USING btree (token) |

### annual_tourism_roster_versions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('annual_tourism_roster_versions_id_seq'::regclass) | NO |
| reference_year | integer | int4 | NO |  | NO |
| source_file | text | text | NO |  | NO |
| source_sha256 | text | text | NO |  | NO |
| status | text | text | NO |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| approved_at | timestamp with time zone | timestamptz | NO | now() | NO |
| next_collection_year | integer | int4 | YES |  | NO |
| source_name | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | annual_tourism_roster_versions_pkey | - | PRIMARY KEY (id) |
| c | annual_tourism_roster_versions_reference_year_check | - | CHECK (((reference_year >= 2000) AND (reference_year <= 2100))) |
| u | annual_tourism_roster_versions_reference_year_source_sha256_key | - | UNIQUE (reference_year, source_sha256) |
| c | annual_tourism_roster_versions_status_check | - | CHECK ((status = ANY (ARRAY['approved'::text, 'superseded'::text]))) |
| indexname | indexdef |
| --- | --- |
| annual_tourism_roster_versions_pkey | CREATE UNIQUE INDEX annual_tourism_roster_versions_pkey ON public.annual_tourism_roster_versions USING btree (id) |
| annual_tourism_roster_versions_reference_year_source_sha256_key | CREATE UNIQUE INDEX annual_tourism_roster_versions_reference_year_source_sha256_key ON public.annual_tourism_roster_versions USING btree (reference_year, source_sha256) |
| idx_annual_tourism_roster_latest | CREATE INDEX idx_annual_tourism_roster_latest ON public.annual_tourism_roster_versions USING btree (status, reference_year DESC, approved_at DESC) |

### app_meta
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| key | text | text | NO |  | NO |
| value | text | text | YES |  | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | app_meta_pkey | - | PRIMARY KEY (key) |
| indexname | indexdef |
| --- | --- |
| app_meta_pkey | CREATE UNIQUE INDEX app_meta_pkey ON public.app_meta USING btree (key) |

### applications
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('applications_id_seq'::regclass) | NO |
| applicant_type | text | text | NO |  | NO |
| office_or_company_name | text | text | NO |  | NO |
| owner_name | text | text | NO |  | NO |
| reg_number | text | text | YES |  | NO |
| biz_reg_number | text | text | YES |  | NO |
| category | text | text | YES |  | NO |
| phone | text | text | NO |  | NO |
| email | text | text | NO |  | NO |
| website_url | text | text | YES |  | NO |
| preferred_region | text | text | YES |  | NO |
| preferred_building | text | text | YES |  | NO |
| intro_text | text | text | YES |  | NO |
| doc_license_url | text | text | YES |  | NO |
| doc_office_reg_url | text | text | YES |  | NO |
| doc_biz_reg_url | text | text | YES |  | NO |
| doc_business_card_url | text | text | YES |  | NO |
| doc_biz_license_url | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| reject_reason | text | text | YES |  | NO |
| linked_agent_id | integer | int4 | YES |  | NO |
| linked_operator_id | integer | int4 | YES |  | NO |
| reviewed_by | integer | int4 | YES |  | NO |
| submitted_at | timestamp without time zone | timestamp | YES | now() | NO |
| reviewed_at | timestamp without time zone | timestamp | YES |  | NO |
| terms_agreed_at | timestamp without time zone | timestamp | YES |  | NO |
| privacy_agreed_at | timestamp without time zone | timestamp | YES |  | NO |
| linked_loan_consultant_id | integer | int4 | YES |  | NO |
| doc_logo_url | text | text | YES |  | NO |
| preferred_building_id | integer | int4 | YES |  | NO |
| doc_photo_url | text | text | YES |  | NO |
| intro_title | text | text | YES |  | NO |
| edit_token | text | text | YES |  | NO |
| office_address | text | text | YES |  | NO |
| password_hash | text | text | YES |  | NO |
| kakao_chat_url | text | text | YES |  | NO |
| lodging_op_type | text | text | YES |  | NO |
| booking_url | text | text | YES |  | NO |
| airbnb_url | text | text | YES |  | NO |
| airbnb_urls | jsonb | jsonb | YES |  | NO |
| permit_no | text | text | YES |  | NO |
| linked_op_lodging_id | integer | int4 | YES |  | NO |
| building_id | integer | int4 | YES |  | NO |
| phone_verification_challenge_id | uuid | uuid | YES |  | NO |
| fast_review_eligible | boolean | bool | NO | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | applications_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) |
| f | applications_linked_agent_id_fkey | agents | FOREIGN KEY (linked_agent_id) REFERENCES agents(id) |
| f | applications_linked_loan_consultant_id_fkey | loan_consultants | FOREIGN KEY (linked_loan_consultant_id) REFERENCES loan_consultants(id) |
| f | applications_linked_op_lodging_fk | operator_lodging | FOREIGN KEY (linked_op_lodging_id) REFERENCES operator_lodging(id) |
| f | applications_linked_operator_id_fkey | operators | FOREIGN KEY (linked_operator_id) REFERENCES operators(id) |
| p | applications_pkey | - | PRIMARY KEY (id) |
| f | applications_preferred_building_id_fkey | master_buildings | FOREIGN KEY (preferred_building_id) REFERENCES master_buildings(id) |
| f | applications_reviewed_by_fkey | admin_users | FOREIGN KEY (reviewed_by) REFERENCES admin_users(id) |
| indexname | indexdef |
| --- | --- |
| applications_pkey | CREATE UNIQUE INDEX applications_pkey ON public.applications USING btree (id) |
| idx_applications_edit_token | CREATE UNIQUE INDEX idx_applications_edit_token ON public.applications USING btree (edit_token) WHERE (edit_token IS NOT NULL) |

### auction_items
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('auction_items_id_seq'::regclass) | NO |
| source | text | text | NO | <literal-redacted>::text | NO |
| source_item_id | text | text | NO |  | NO |
| pbct_cdtn_no | text | text | NO | <literal-redacted>::text | NO |
| sale_kind | text | text | YES |  | NO |
| usage_name | text | text | YES |  | NO |
| lodging_category | text | text | YES |  | NO |
| title | text | text | YES |  | NO |
| unit_label | text | text | YES |  | NO |
| address_road | text | text | YES |  | NO |
| address_jibun | text | text | YES |  | NO |
| area_m2 | real | float4 | YES |  | NO |
| appraisal_price | bigint | int8 | YES |  | NO |
| min_bid_price | bigint | int8 | YES |  | NO |
| min_bid_ratio | real | float4 | YES |  | NO |
| round_no | integer | int4 | YES |  | NO |
| failed_count | integer | int4 | YES | 0 | NO |
| bid_start_at | timestamp with time zone | timestamptz | YES |  | NO |
| bid_end_at | timestamp with time zone | timestamptz | YES |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| status_changed_at | timestamp with time zone | timestamptz | NO | now() | NO |
| disposal_method | text | text | YES |  | NO |
| notice_org | text | text | YES |  | NO |
| notice_no | text | text | YES |  | NO |
| detail_url | text | text | YES |  | NO |
| lat | double precision | float8 | YES |  | NO |
| lng | double precision | float8 | YES |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| raw | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| detail_fingerprint | text | text | YES |  | NO |
| first_seen_at | timestamp with time zone | timestamptz | NO | now() | NO |
| last_seen_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| check_business_report | text | text | NO | <literal-redacted>::text | NO |
| check_operation_succession | text | text | NO | <literal-redacted>::text | NO |
| check_fee_arrears | text | text | NO | <literal-redacted>::text | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | auction_items_check_business_report_check | - | CHECK ((check_business_report = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| c | auction_items_check_fee_arrears_check | - | CHECK ((check_fee_arrears = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| c | auction_items_check_operation_succession_check | - | CHECK ((check_operation_succession = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| f | auction_items_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| p | auction_items_pkey | - | PRIMARY KEY (id) |
| u | auction_items_source_source_item_id_pbct_cdtn_no_key | - | UNIQUE (source, source_item_id, pbct_cdtn_no) |
| indexname | indexdef |
| --- | --- |
| auction_items_pkey | CREATE UNIQUE INDEX auction_items_pkey ON public.auction_items USING btree (id) |
| auction_items_source_source_item_id_pbct_cdtn_no_key | CREATE UNIQUE INDEX auction_items_source_source_item_id_pbct_cdtn_no_key ON public.auction_items USING btree (source, source_item_id, pbct_cdtn_no) |
| idx_auction_building | CREATE INDEX idx_auction_building ON public.auction_items USING btree (master_building_id) |
| idx_auction_category | CREATE INDEX idx_auction_category ON public.auction_items USING btree (lodging_category) |
| idx_auction_coords | CREATE INDEX idx_auction_coords ON public.auction_items USING btree (lat, lng) |
| idx_auction_property | CREATE INDEX idx_auction_property ON public.auction_items USING btree (source, source_item_id) |
| idx_auction_status_deadline | CREATE INDEX idx_auction_status_deadline ON public.auction_items USING btree (status, bid_end_at) |

### auction_photos
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('auction_photos_id_seq'::regclass) | NO |
| auction_item_id | integer | int4 | NO |  | NO |
| url | text | text | NO |  | NO |
| sort_order | integer | int4 | NO | 0 | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | auction_photos_auction_item_id_fkey | auction_items | FOREIGN KEY (auction_item_id) REFERENCES auction_items(id) ON DELETE CASCADE |
| u | auction_photos_auction_item_id_url_key | - | UNIQUE (auction_item_id, url) |
| p | auction_photos_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| auction_photos_auction_item_id_url_key | CREATE UNIQUE INDEX auction_photos_auction_item_id_url_key ON public.auction_photos USING btree (auction_item_id, url) |
| auction_photos_pkey | CREATE UNIQUE INDEX auction_photos_pkey ON public.auction_photos USING btree (id) |

### auction_rounds
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('auction_rounds_id_seq'::regclass) | NO |
| auction_item_id | integer | int4 | NO |  | NO |
| round_no | integer | int4 | NO |  | NO |
| bid_start_at | timestamp with time zone | timestamptz | YES |  | NO |
| bid_end_at | timestamp with time zone | timestamptz | YES |  | NO |
| min_bid_price | bigint | int8 | YES |  | NO |
| result | text | text | YES |  | NO |
| source_round_key | text | text | NO | <literal-redacted>::text | NO |
| result_at | timestamp with time zone | timestamptz | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | auction_rounds_auction_item_id_fkey | auction_items | FOREIGN KEY (auction_item_id) REFERENCES auction_items(id) ON DELETE CASCADE |
| p | auction_rounds_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| auction_rounds_pkey | CREATE UNIQUE INDEX auction_rounds_pkey ON public.auction_rounds USING btree (id) |
| idx_auction_round_source | CREATE UNIQUE INDEX idx_auction_round_source ON public.auction_rounds USING btree (auction_item_id, source_round_key) |

### auction_watches
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| enabled | boolean | bool | NO | true | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | auction_watches_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | auction_watches_pkey | - | PRIMARY KEY (user_id, master_building_id) |
| f | auction_watches_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| auction_watches_pkey | CREATE UNIQUE INDEX auction_watches_pkey ON public.auction_watches USING btree (user_id, master_building_id) |

### booking_url_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('booking_url_requests_id_seq'::regclass) | NO |
| operator_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| booking_url | text | text | NO |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| submitted_at | timestamp without time zone | timestamp | YES | now() | NO |
| reviewed_at | timestamp without time zone | timestamp | YES |  | NO |
| reviewed_by | integer | int4 | YES |  | NO |
| admin_note | text | text | YES |  | NO |
| renewal_count | integer | int4 | YES | 0 | NO |
| expires_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | booking_url_requests_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| f | booking_url_requests_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | booking_url_requests_pkey | - | PRIMARY KEY (id) |
| f | booking_url_requests_reviewed_by_fkey | admin_users | FOREIGN KEY (reviewed_by) REFERENCES admin_users(id) |
| indexname | indexdef |
| --- | --- |
| booking_url_requests_pkey | CREATE UNIQUE INDEX booking_url_requests_pkey ON public.booking_url_requests USING btree (id) |
| idx_bur_operator | CREATE INDEX idx_bur_operator ON public.booking_url_requests USING btree (operator_id, submitted_at DESC) |
| idx_bur_status | CREATE INDEX idx_bur_status ON public.booking_url_requests USING btree (status, submitted_at DESC) |

### broker_registry
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('broker_registry_id_seq'::regclass) | NO |
| office_name | text | text | NO |  | NO |
| reg_number | text | text | NO |  | NO |
| road_address | text | text | YES |  | NO |
| jibun_address | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| reg_date | text | text | YES |  | NO |
| owner_name | text | text | YES |  | NO |
| lat | double precision | float8 | YES |  | NO |
| lng | double precision | float8 | YES |  | NO |
| homepage_url | text | text | YES |  | NO |
| source_updated_at | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| road_norm | text | text | YES |  | NO |
| jibun_norm | text | text | YES |  | NO |
| biz_status | text | text | YES |  | NO |
| source_reg_number | text | text | YES |  | NO |
| source_region_code | text | text | YES |  | NO |
| source_name | text | text | YES |  | NO |
| phone_numbers | ARRAY | _text | NO | <literal-redacted>::text[] | NO |
| member_count | integer | int4 | NO | 0 | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | broker_registry_pkey | - | PRIMARY KEY (id) |
| u | broker_registry_reg_number_key | - | UNIQUE (reg_number) |
| indexname | indexdef |
| --- | --- |
| broker_registry_pkey | CREATE UNIQUE INDEX broker_registry_pkey ON public.broker_registry USING btree (id) |
| broker_registry_reg_number_key | CREATE UNIQUE INDEX broker_registry_reg_number_key ON public.broker_registry USING btree (reg_number) |
| idx_broker_registry_jibun_norm | CREATE INDEX idx_broker_registry_jibun_norm ON public.broker_registry USING btree (jibun_norm) |
| idx_broker_registry_latlng | CREATE INDEX idx_broker_registry_latlng ON public.broker_registry USING btree (lat, lng) |
| idx_broker_registry_road_norm | CREATE INDEX idx_broker_registry_road_norm ON public.broker_registry USING btree (road_norm) |
| idx_broker_registry_source_reg | CREATE INDEX idx_broker_registry_source_reg ON public.broker_registry USING btree (source_region_code, source_reg_number) |

### broker_registry_members
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('broker_registry_members_id_seq'::regclass) | NO |
| source_row_key | text | text | NO |  | NO |
| source_name | text | text | NO |  | NO |
| region_code | text | text | YES |  | NO |
| region_name | text | text | YES |  | NO |
| reg_number | text | text | NO |  | NO |
| office_name | text | text | YES |  | NO |
| member_name | text | text | YES |  | NO |
| member_type_code | text | text | YES |  | NO |
| member_type_name | text | text | YES |  | NO |
| license_number | text | text | YES |  | NO |
| license_date | text | text | YES |  | NO |
| position_code | text | text | YES |  | NO |
| position_name | text | text | YES |  | NO |
| source_updated_at | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | broker_registry_members_pkey | - | PRIMARY KEY (id) |
| u | broker_registry_members_source_row_key_key | - | UNIQUE (source_row_key) |
| indexname | indexdef |
| --- | --- |
| broker_registry_members_pkey | CREATE UNIQUE INDEX broker_registry_members_pkey ON public.broker_registry_members USING btree (id) |
| broker_registry_members_source_row_key_key | CREATE UNIQUE INDEX broker_registry_members_source_row_key_key ON public.broker_registry_members USING btree (source_row_key) |
| idx_broker_registry_members_office | CREATE INDEX idx_broker_registry_members_office ON public.broker_registry_members USING btree (region_code, reg_number, office_name) |

### bug_reports
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('bug_reports_id_seq'::regclass) | NO |
| user_id | integer | int4 | YES |  | NO |
| account_type | text | text | YES |  | NO |
| description | text | text | NO |  | NO |
| page_url | text | text | YES |  | NO |
| user_agent | text | text | YES |  | NO |
| severity | text | text | YES | <literal-redacted>::text | NO |
| contact | text | text | YES |  | NO |
| screenshot_key | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| admin_note | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | bug_reports_pkey | - | PRIMARY KEY (id) |
| f | bug_reports_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| bug_reports_pkey | CREATE UNIQUE INDEX bug_reports_pkey ON public.bug_reports USING btree (id) |
| idx_bug_reports_status | CREATE INDEX idx_bug_reports_status ON public.bug_reports USING btree (status, created_at DESC) |

### building_photo_fetches
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| building_id | integer | int4 | NO |  | NO |
| source | text | text | NO |  | NO |
| status | text | text | NO |  | NO |
| last_attempt_at | timestamp with time zone | timestamptz | NO | now() | NO |
| error_message | text | text | YES |  | NO |
| provider_ref | text | text | YES |  | NO |
| photo_available | boolean | bool | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | building_photo_fetches_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | building_photo_fetches_pkey | - | PRIMARY KEY (building_id, source) |
| indexname | indexdef |
| --- | --- |
| building_photo_fetches_pkey | CREATE UNIQUE INDEX building_photo_fetches_pkey ON public.building_photo_fetches USING btree (building_id, source) |
| idx_bphoto_fetches_attempt | CREATE INDEX idx_bphoto_fetches_attempt ON public.building_photo_fetches USING btree (source, status, last_attempt_at) |

### building_photos
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('building_photos_id_seq'::regclass) | NO |
| building_id | integer | int4 | NO |  | NO |
| photo_url | text | text | NO |  | NO |
| source | text | text | NO |  | NO |
| photo_type | text | text | YES |  | NO |
| is_primary | boolean | bool | YES | false | NO |
| display_order | integer | int4 | YES | 0 | NO |
| created_at | timestamp with time zone | timestamptz | YES | now() | NO |
| photo_hash | text | text | YES |  | NO |
| uploaded_by_user_id | integer | int4 | YES |  | NO |
| registrant_type | text | text | YES |  | NO |
| gps_lat | double precision | float8 | YES |  | NO |
| gps_lng | double precision | float8 | YES |  | NO |
| gps_verified | boolean | bool | YES | false | NO |
| exif_taken_at | timestamp with time zone | timestamptz | YES |  | NO |
| listing_photo_id | integer | int4 | YES |  | NO |
| uploaded_by_agent_id | integer | int4 | YES |  | NO |
| listing_request_id | integer | int4 | YES |  | NO |
| priority_rank | smallint | int2 | YES | 99 | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | building_photos_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| f | building_photos_listing_photo_id_fkey | listing_photos | FOREIGN KEY (listing_photo_id) REFERENCES listing_photos(id) ON DELETE CASCADE |
| f | building_photos_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| p | building_photos_pkey | - | PRIMARY KEY (id) |
| f | building_photos_uploaded_by_agent_id_fkey | agents | FOREIGN KEY (uploaded_by_agent_id) REFERENCES agents(id) |
| indexname | indexdef |
| --- | --- |
| building_photos_pkey | CREATE UNIQUE INDEX building_photos_pkey ON public.building_photos USING btree (id) |
| idx_bphotos_building | CREATE INDEX idx_bphotos_building ON public.building_photos USING btree (building_id, display_order) |
| uq_bphotos_building_url | CREATE UNIQUE INDEX uq_bphotos_building_url ON public.building_photos USING btree (building_id, photo_url) |
| uq_bphotos_hash | CREATE UNIQUE INDEX uq_bphotos_hash ON public.building_photos USING btree (building_id, photo_hash) WHERE (photo_hash IS NOT NULL) |
| uq_bphotos_listing_photo | CREATE UNIQUE INDEX uq_bphotos_listing_photo ON public.building_photos USING btree (listing_photo_id) WHERE (listing_photo_id IS NOT NULL) |

### building_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('building_requests_id_seq'::regclass) | NO |
| road_address | text | text | YES |  | NO |
| building_name_hint | text | text | YES |  | NO |
| requester_note | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| reject_reason | text | text | YES |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| processed_at | timestamp without time zone | timestamp | YES |  | NO |
| request_type | text | text | YES | <literal-redacted>::text | NO |
| target_sgg_cd | text | text | YES |  | NO |
| target_umd_nm | text | text | YES |  | NO |
| target_jibun | text | text | YES |  | NO |
| suggested_lodging_type | text | text | YES |  | NO |
| verified_lodging_type | text | text | YES |  | NO |
| changed | boolean | bool | YES | false | NO |
| suggested_building_name | text | text | YES |  | NO |
| jibun_address_input | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | building_requests_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| building_requests_pkey | CREATE UNIQUE INDEX building_requests_pkey ON public.building_requests USING btree (id) |

### building_stores
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('building_stores_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| store_name | text | text | YES |  | NO |
| category | text | text | YES |  | NO |
| floor | text | text | YES |  | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| ho_no | text | text | YES |  | NO |
| inds_mcls_nm | text | text | YES |  | NO |
| inds_scls_nm | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | building_stores_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | building_stores_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| building_stores_pkey | CREATE UNIQUE INDEX building_stores_pkey ON public.building_stores USING btree (id) |
| idx_building_stores_building | CREATE INDEX idx_building_stores_building ON public.building_stores USING btree (master_building_id) |

### building_unit_areas
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('building_unit_areas_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| ho | character varying | varchar | YES |  | NO |
| area_sqm | numeric | numeric | YES |  | NO |
| fetched_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | building_unit_areas_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | building_unit_areas_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| building_unit_areas_pkey | CREATE UNIQUE INDEX building_unit_areas_pkey ON public.building_unit_areas USING btree (id) |
| idx_unit_areas_building | CREATE INDEX idx_unit_areas_building ON public.building_unit_areas USING btree (master_building_id) |

### business_building_verifications
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('business_building_verifications_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| permit_number | text | text | NO |  | NO |
| verified_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | business_building_verifications_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | business_building_verifications_pkey | - | PRIMARY KEY (id) |
| f | business_building_verifications_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | business_building_verifications_user_id_master_building_id_key | - | UNIQUE (user_id, master_building_id) |
| indexname | indexdef |
| --- | --- |
| business_building_verifications_pkey | CREATE UNIQUE INDEX business_building_verifications_pkey ON public.business_building_verifications USING btree (id) |
| business_building_verifications_user_id_master_building_id_key | CREATE UNIQUE INDEX business_building_verifications_user_id_master_building_id_key ON public.business_building_verifications USING btree (user_id, master_building_id) |
| idx_business_building_verifications_building | CREATE INDEX idx_business_building_verifications_building ON public.business_building_verifications USING btree (master_building_id) |

### business_room_inventory
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('business_room_inventory_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| room_label | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| contract_end_date | date | date | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES |  | NO |
| floor | integer | int4 | YES |  | NO |
| channel | text | text | NO | <literal-redacted>::text | NO |
| monthly_rent_krw | integer | int4 | YES |  | NO |
| deposit_krw | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | business_room_inventory_channel_check | - | CHECK ((channel = ANY (ARRAY['OTA전용'::text, '장박가능'::text]))) |
| f | business_room_inventory_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| u | business_room_inventory_listing_request_id_room_label_key | - | UNIQUE (listing_request_id, room_label) |
| p | business_room_inventory_pkey | - | PRIMARY KEY (id) |
| c | business_room_inventory_status_check | - | CHECK ((status = ANY (ARRAY['입실'::text, '공실'::text]))) |
| indexname | indexdef |
| --- | --- |
| business_room_inventory_listing_request_id_room_label_key | CREATE UNIQUE INDEX business_room_inventory_listing_request_id_room_label_key ON public.business_room_inventory USING btree (listing_request_id, room_label) |
| business_room_inventory_pkey | CREATE UNIQUE INDEX business_room_inventory_pkey ON public.business_room_inventory USING btree (id) |
| ix_business_room_inventory_listing | CREATE INDEX ix_business_room_inventory_listing ON public.business_room_inventory USING btree (listing_request_id, id) |

### buy_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('buy_requests_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| deal_type | text | text | NO |  | NO |
| desired_price | text | text | YES |  | NO |
| price_krw | integer | int4 | YES |  | NO |
| monthly_rent_krw | integer | int4 | YES |  | NO |
| contact_phone | text | text | NO |  | NO |
| routed_agent_id | integer | int4 | YES |  | NO |
| routed_reason | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| admin_note | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| area_sqm | numeric | numeric | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | buy_requests_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | buy_requests_pkey | - | PRIMARY KEY (id) |
| f | buy_requests_routed_agent_id_fkey | agents | FOREIGN KEY (routed_agent_id) REFERENCES agents(id) |
| f | buy_requests_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| buy_requests_pkey | CREATE UNIQUE INDEX buy_requests_pkey ON public.buy_requests USING btree (id) |

### chat_messages
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('chat_messages_id_seq'::regclass) | NO |
| room_id | integer | int4 | NO |  | NO |
| sender_user_id | integer | int4 | NO |  | NO |
| body | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| is_read | boolean | bool | NO | false | NO |
| attachment_key | text | text | YES |  | NO |
| attachment_name | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | chat_messages_pkey | - | PRIMARY KEY (id) |
| f | chat_messages_room_id_fkey | chat_rooms | FOREIGN KEY (room_id) REFERENCES chat_rooms(id) |
| f | chat_messages_sender_user_id_fkey | users | FOREIGN KEY (sender_user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| chat_messages_pkey | CREATE UNIQUE INDEX chat_messages_pkey ON public.chat_messages USING btree (id) |
| ix_chat_messages_room | CREATE INDEX ix_chat_messages_room ON public.chat_messages USING btree (room_id, created_at) |

### chat_rooms
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('chat_rooms_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| buyer_user_id | integer | int4 | YES |  | NO |
| seller_user_id | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | chat_rooms_buyer_user_id_fkey | users | FOREIGN KEY (buyer_user_id) REFERENCES users(id) |
| u | chat_rooms_listing_request_id_buyer_user_id_key | - | UNIQUE (listing_request_id, buyer_user_id) |
| f | chat_rooms_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) |
| p | chat_rooms_pkey | - | PRIMARY KEY (id) |
| f | chat_rooms_seller_user_id_fkey | users | FOREIGN KEY (seller_user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| chat_rooms_listing_request_id_buyer_user_id_key | CREATE UNIQUE INDEX chat_rooms_listing_request_id_buyer_user_id_key ON public.chat_rooms USING btree (listing_request_id, buyer_user_id) |
| chat_rooms_pkey | CREATE UNIQUE INDEX chat_rooms_pkey ON public.chat_rooms USING btree (id) |
| ix_chat_rooms_buyer | CREATE INDEX ix_chat_rooms_buyer ON public.chat_rooms USING btree (buyer_user_id) |
| ix_chat_rooms_seller | CREATE INDEX ix_chat_rooms_seller ON public.chat_rooms USING btree (seller_user_id) |

### deal_alert_logs
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('deal_alert_logs_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| transaction_id | integer | int4 | NO |  | NO |
| alert_date | date | date | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| claimed_at | timestamp without time zone | timestamp | YES | now() | NO |
| sent_at | timestamp without time zone | timestamp | YES |  | NO |
| error_message | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | deal_alert_logs_pkey | - | PRIMARY KEY (id) |
| f | deal_alert_logs_transaction_id_fkey | transactions | FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE |
| f | deal_alert_logs_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | deal_alert_logs_user_id_transaction_id_alert_date_key | - | UNIQUE (user_id, transaction_id, alert_date) |
| indexname | indexdef |
| --- | --- |
| deal_alert_logs_pkey | CREATE UNIQUE INDEX deal_alert_logs_pkey ON public.deal_alert_logs USING btree (id) |
| deal_alert_logs_user_id_transaction_id_alert_date_key | CREATE UNIQUE INDEX deal_alert_logs_user_id_transaction_id_alert_date_key ON public.deal_alert_logs USING btree (user_id, transaction_id, alert_date) |
| idx_deal_alert_logs_user_date | CREATE INDEX idx_deal_alert_logs_user_date ON public.deal_alert_logs USING btree (user_id, alert_date) |

### discover_progress
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| sgg_cd | text | text | NO |  | NO |
| deal_ymd | text | text | NO |  | NO |
| processed_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | discover_progress_pkey | - | PRIMARY KEY (sgg_cd, deal_ymd) |
| indexname | indexdef |
| --- | --- |
| discover_progress_pkey | CREATE UNIQUE INDEX discover_progress_pkey ON public.discover_progress USING btree (sgg_cd, deal_ymd) |

### email_ad_banners
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('email_ad_banners_id_seq'::regclass) | NO |
| image_url | text | text | NO |  | NO |
| link_url | text | text | NO |  | NO |
| start_date | date | date | NO |  | NO |
| end_date | date | date | NO |  | NO |
| is_active | boolean | bool | NO | true | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | email_ad_banners_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| email_ad_banners_pkey | CREATE UNIQUE INDEX email_ad_banners_pkey ON public.email_ad_banners USING btree (id) |

### gocamping_records
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| content_id | text | text | NO |  | NO |
| lodging_registry_id | integer | int4 | YES |  | NO |
| source_url | text | text | NO |  | NO |
| web_payload | jsonb | jsonb | NO |  | NO |
| photo_urls | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| payload_hash | text | text | YES |  | NO |
| parser_version | integer | int4 | NO | 1 | NO |
| fetched_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | gocamping_records_lodging_registry_id_fkey | lodging_registry | FOREIGN KEY (lodging_registry_id) REFERENCES lodging_registry(id) ON DELETE SET NULL |
| p | gocamping_records_pkey | - | PRIMARY KEY (content_id) |
| indexname | indexdef |
| --- | --- |
| gocamping_records_pkey | CREATE UNIQUE INDEX gocamping_records_pkey ON public.gocamping_records USING btree (content_id) |
| idx_gocamping_records_registry | CREATE INDEX idx_gocamping_records_registry ON public.gocamping_records USING btree (lodging_registry_id) |

### hotel_operation_metrics
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('hotel_operation_metrics_id_seq'::regclass) | NO |
| version_id | bigint | int8 | NO |  | NO |
| source_file | text | text | NO |  | NO |
| source_row_number | integer | int4 | NO |  | NO |
| sido_name | text | text | NO |  | NO |
| sgg_name | text | text | YES |  | NO |
| grade | text | text | NO |  | NO |
| occupancy_rate | numeric | numeric | YES |  | NO |
| adr | numeric | numeric | YES |  | NO |
| revpar | numeric | numeric | YES |  | NO |
| foreign_guest_rate | numeric | numeric | YES |  | NO |
| available_room_nights | bigint | int8 | YES |  | NO |
| sold_room_nights | bigint | int8 | YES |  | NO |
| room_count | integer | int4 | YES |  | NO |
| business_count | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | hotel_operation_metrics_pkey | - | PRIMARY KEY (id) |
| f | hotel_operation_metrics_version_id_fkey | hotel_operation_source_versions | FOREIGN KEY (version_id) REFERENCES hotel_operation_source_versions(id) ON DELETE CASCADE |
| u | hotel_operation_metrics_version_id_source_file_source_row_n_key | - | UNIQUE (version_id, source_file, source_row_number) |
| indexname | indexdef |
| --- | --- |
| hotel_operation_metrics_pkey | CREATE UNIQUE INDEX hotel_operation_metrics_pkey ON public.hotel_operation_metrics USING btree (id) |
| hotel_operation_metrics_version_id_source_file_source_row_n_key | CREATE UNIQUE INDEX hotel_operation_metrics_version_id_source_file_source_row_n_key ON public.hotel_operation_metrics USING btree (version_id, source_file, source_row_number) |
| idx_hotel_operation_metrics_region | CREATE INDEX idx_hotel_operation_metrics_region ON public.hotel_operation_metrics USING btree (version_id, sido_name, sgg_name, grade) |

### hotel_operation_source_versions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('hotel_operation_source_versions_id_seq'::regclass) | NO |
| reference_year | integer | int4 | NO |  | NO |
| source_name | text | text | NO |  | NO |
| source_file | text | text | NO |  | NO |
| source_sha256 | text | text | NO |  | NO |
| imported_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | hotel_operation_source_version_reference_year_source_sha256_key | - | UNIQUE (reference_year, source_sha256) |
| p | hotel_operation_source_versions_pkey | - | PRIMARY KEY (id) |
| c | hotel_operation_source_versions_reference_year_check | - | CHECK (((reference_year >= 2000) AND (reference_year <= 2100))) |
| u | hotel_operation_source_versions_source_sha256_key | - | UNIQUE (source_sha256) |
| indexname | indexdef |
| --- | --- |
| hotel_operation_source_sha256_unique | CREATE UNIQUE INDEX hotel_operation_source_sha256_unique ON public.hotel_operation_source_versions USING btree (source_sha256) |
| hotel_operation_source_version_reference_year_source_sha256_key | CREATE UNIQUE INDEX hotel_operation_source_version_reference_year_source_sha256_key ON public.hotel_operation_source_versions USING btree (reference_year, source_sha256) |
| hotel_operation_source_versions_pkey | CREATE UNIQUE INDEX hotel_operation_source_versions_pkey ON public.hotel_operation_source_versions USING btree (id) |
| hotel_operation_source_versions_source_sha256_key | CREATE UNIQUE INDEX hotel_operation_source_versions_source_sha256_key ON public.hotel_operation_source_versions USING btree (source_sha256) |

### legal_documents
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('legal_documents_id_seq'::regclass) | NO |
| doc_type | text | text | NO |  | NO |
| content | text | text | NO |  | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | legal_documents_doc_type_key | - | UNIQUE (doc_type) |
| p | legal_documents_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| legal_documents_doc_type_key | CREATE UNIQUE INDEX legal_documents_doc_type_key ON public.legal_documents USING btree (doc_type) |
| legal_documents_pkey | CREATE UNIQUE INDEX legal_documents_pkey ON public.legal_documents USING btree (id) |

### listing_checklist_progress
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listing_checklist_progress_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| item_key | text | text | NO |  | NO |
| checked_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listing_checklist_progress_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| p | listing_checklist_progress_pkey | - | PRIMARY KEY (id) |
| f | listing_checklist_progress_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | listing_checklist_progress_user_id_listing_request_id_item__key | - | UNIQUE (user_id, listing_request_id, item_key) |
| indexname | indexdef |
| --- | --- |
| ix_listing_checklist_progress_listing_user | CREATE INDEX ix_listing_checklist_progress_listing_user ON public.listing_checklist_progress USING btree (listing_request_id, user_id) |
| listing_checklist_progress_pkey | CREATE UNIQUE INDEX listing_checklist_progress_pkey ON public.listing_checklist_progress USING btree (id) |
| listing_checklist_progress_user_id_listing_request_id_item__key | CREATE UNIQUE INDEX listing_checklist_progress_user_id_listing_request_id_item__key ON public.listing_checklist_progress USING btree (user_id, listing_request_id, item_key) |

### listing_likes
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listing_likes_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| user_id | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listing_likes_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| u | listing_likes_listing_request_id_user_id_key | - | UNIQUE (listing_request_id, user_id) |
| p | listing_likes_pkey | - | PRIMARY KEY (id) |
| f | listing_likes_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| ix_listing_likes_lr | CREATE INDEX ix_listing_likes_lr ON public.listing_likes USING btree (listing_request_id) |
| listing_likes_listing_request_id_user_id_key | CREATE UNIQUE INDEX listing_likes_listing_request_id_user_id_key ON public.listing_likes USING btree (listing_request_id, user_id) |
| listing_likes_pkey | CREATE UNIQUE INDEX listing_likes_pkey ON public.listing_likes USING btree (id) |

### listing_photos
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listing_photos_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| image_key | text | text | NO |  | NO |
| sort_order | integer | int4 | YES | 0 | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| is_public | boolean | bool | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listing_photos_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| p | listing_photos_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| ix_listing_photos_lr | CREATE INDEX ix_listing_photos_lr ON public.listing_photos USING btree (listing_request_id, sort_order) |
| listing_photos_pkey | CREATE UNIQUE INDEX listing_photos_pkey ON public.listing_photos USING btree (id) |

### listing_request_deletion_archive
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('listing_request_deletion_archive_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| request_snapshot | jsonb | jsonb | NO |  | NO |
| related_snapshot | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| deleted_by_admin_id | integer | int4 | YES |  | NO |
| deletion_source | character varying | varchar | NO |  | NO |
| deleted_at | timestamp without time zone | timestamp | NO | now() | NO |
| restored_at | timestamp without time zone | timestamp | YES |  | NO |
| restored_by_admin_id | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | listing_request_deletion_archive_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| ix_listing_request_deletion_archive_request | CREATE INDEX ix_listing_request_deletion_archive_request ON public.listing_request_deletion_archive USING btree (listing_request_id, deleted_at DESC) |
| listing_request_deletion_archive_pkey | CREATE UNIQUE INDEX listing_request_deletion_archive_pkey ON public.listing_request_deletion_archive USING btree (id) |

### listing_request_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listing_request_history_id_seq'::regclass) | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| action | character varying | varchar | NO |  | NO |
| before_data | jsonb | jsonb | YES |  | NO |
| after_data | jsonb | jsonb | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listing_request_history_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) |
| p | listing_request_history_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| listing_request_history_pkey | CREATE UNIQUE INDEX listing_request_history_pkey ON public.listing_request_history USING btree (id) |

### listing_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listing_requests_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| deal_type | text | text | NO |  | NO |
| desired_price | text | text | YES |  | NO |
| contact_phone | text | text | NO |  | NO |
| routed_agent_id | integer | int4 | YES |  | NO |
| routed_reason | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| admin_note | text | text | YES |  | NO |
| price_krw | integer | int4 | YES |  | NO |
| monthly_rent_krw | integer | int4 | YES |  | NO |
| deal_mode | text | text | YES | <literal-redacted>::text | NO |
| verified_phone | text | text | YES |  | NO |
| area_sqm | numeric | numeric | YES |  | NO |
| dong | character varying | varchar | YES |  | NO |
| ho | character varying | varchar | YES |  | NO |
| registrant_type | character varying | varchar | YES |  | NO |
| description | text | text | YES |  | NO |
| deposit_krw | integer | int4 | YES |  | NO |
| yield_rate | numeric | numeric | YES |  | NO |
| yield_rent_krw | integer | int4 | YES |  | NO |
| display_seq | integer | int4 | YES |  | NO |
| updated_at | timestamp without time zone | timestamp | YES |  | NO |
| price_krw_max | integer | int4 | YES |  | NO |
| room_count | integer | int4 | YES |  | NO |
| transaction_target | text | text | YES | <literal-redacted>::text | NO |
| succession_loan_krw | integer | int4 | YES |  | NO |
| key_money_krw | integer | int4 | YES |  | NO |
| monthly_revenue_krw | integer | int4 | YES |  | NO |
| annual_revenue_krw | integer | int4 | YES |  | NO |
| operation_status | text | text | YES |  | NO |
| closed_at | date | date | YES |  | NO |
| remodeling_info | text | text | YES |  | NO |
| is_urgent | boolean | bool | YES | false | NO |
| disclosure_scope | text | text | YES | <literal-redacted>::text | NO |
| building_info_overrides | jsonb | jsonb | YES | <literal-redacted>::jsonb | NO |
| matched_permit_number | text | text | YES |  | NO |
| short_stay_ratio | numeric | numeric | YES |  | NO |
| ota_revenue_ratio | numeric | numeric | YES |  | NO |
| business_rights_info | jsonb | jsonb | YES | <literal-redacted>::jsonb | NO |
| broker_agent_id | integer | int4 | YES |  | NO |
| publication_status | text | text | YES |  | NO |
| publication_reason | text | text | YES |  | NO |
| publication_verified_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listing_requests_broker_agent_id_fkey | agents | FOREIGN KEY (broker_agent_id) REFERENCES agents(id) |
| f | listing_requests_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | listing_requests_pkey | - | PRIMARY KEY (id) |
| f | listing_requests_routed_agent_id_fkey | agents | FOREIGN KEY (routed_agent_id) REFERENCES agents(id) |
| f | listing_requests_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| idx_listing_broker_publication | CREATE INDEX idx_listing_broker_publication ON public.listing_requests USING btree (broker_agent_id, publication_status) |
| idx_listing_requests_active_direct_building | CREATE INDEX idx_listing_requests_active_direct_building ON public.listing_requests USING btree (master_building_id) WHERE ((deal_mode = 'direct'::text) AND (COALESCE(status, ''::text) <> ALL (ARRAY['withdrawn'::text, '철회됨'::text]))) |
| ix_listing_requests_active_building | CREATE INDEX ix_listing_requests_active_building ON public.listing_requests USING btree (master_building_id) WHERE (status IS DISTINCT FROM 'withdrawn'::text) |
| listing_requests_pkey | CREATE UNIQUE INDEX listing_requests_pkey ON public.listing_requests USING btree (id) |
| ux_lr_dealmode_seq | CREATE UNIQUE INDEX ux_lr_dealmode_seq ON public.listing_requests USING btree (deal_mode, display_seq) WHERE (display_seq IS NOT NULL) |

### listings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('listings_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| agent_id | integer | int4 | YES |  | NO |
| deal_type | text | text | NO |  | NO |
| price | integer | int4 | YES |  | NO |
| monthly_rent | integer | int4 | YES |  | NO |
| floor | text | text | YES |  | NO |
| area | real | float4 | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | listings_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) |
| f | listings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | listings_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_listings_building | CREATE INDEX idx_listings_building ON public.listings USING btree (master_building_id) |
| listings_pkey | CREATE UNIQUE INDEX listings_pkey ON public.listings USING btree (id) |

### loan_consult_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('loan_consult_requests_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| message | text | text | YES |  | NO |
| contact_phone | text | text | NO |  | NO |
| routed_consultant_id | integer | int4 | YES |  | NO |
| routed_reason | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | loan_consult_requests_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | loan_consult_requests_pkey | - | PRIMARY KEY (id) |
| f | loan_consult_requests_routed_consultant_id_fkey | loan_consultants | FOREIGN KEY (routed_consultant_id) REFERENCES loan_consultants(id) |
| f | loan_consult_requests_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| loan_consult_requests_pkey | CREATE UNIQUE INDEX loan_consult_requests_pkey ON public.loan_consult_requests USING btree (id) |

### loan_consultant_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('loan_consultant_buildings_id_seq'::regclass) | NO |
| loan_consultant_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| has_priority_badge | boolean | bool | YES | false | NO |
| premium_granted_at | timestamp without time zone | timestamp | YES |  | NO |
| premium_expires_at | timestamp without time zone | timestamp | YES |  | NO |
| is_paid | boolean | bool | YES | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | loan_consultant_buildings_loan_consultant_id_fkey | loan_consultants | FOREIGN KEY (loan_consultant_id) REFERENCES loan_consultants(id) ON DELETE CASCADE |
| f | loan_consultant_buildings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | loan_consultant_buildings_pkey | - | PRIMARY KEY (id) |
| u | loan_consultant_buildings_unique | - | UNIQUE (loan_consultant_id, master_building_id) |
| indexname | indexdef |
| --- | --- |
| loan_consultant_buildings_pkey | CREATE UNIQUE INDEX loan_consultant_buildings_pkey ON public.loan_consultant_buildings USING btree (id) |
| loan_consultant_buildings_unique | CREATE UNIQUE INDEX loan_consultant_buildings_unique ON public.loan_consultant_buildings USING btree (loan_consultant_id, master_building_id) |

### loan_consultant_service_areas
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('loan_consultant_service_areas_id_seq'::regclass) | NO |
| loan_consultant_id | integer | int4 | NO |  | NO |
| region_name | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | loan_consultant_service_areas_loan_consultant_id_fkey | loan_consultants | FOREIGN KEY (loan_consultant_id) REFERENCES loan_consultants(id) ON DELETE CASCADE |
| p | loan_consultant_service_areas_pkey | - | PRIMARY KEY (id) |
| u | loan_consultant_service_areas_unique | - | UNIQUE (loan_consultant_id, region_name) |
| indexname | indexdef |
| --- | --- |
| loan_consultant_service_areas_pkey | CREATE UNIQUE INDEX loan_consultant_service_areas_pkey ON public.loan_consultant_service_areas USING btree (id) |
| loan_consultant_service_areas_unique | CREATE UNIQUE INDEX loan_consultant_service_areas_unique ON public.loan_consultant_service_areas USING btree (loan_consultant_id, region_name) |

### loan_consultants
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('loan_consultants_id_seq'::regclass) | NO |
| office_name | text | text | NO |  | NO |
| owner_name | text | text | NO |  | NO |
| license_number | text | text | NO |  | NO |
| biz_reg_number | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| email | text | text | NO |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| subdomain_slug | text | text | YES |  | NO |
| intro_text | text | text | YES |  | NO |
| password_hash | text | text | YES |  | NO |
| photo_url | text | text | YES |  | NO |
| admin_tag | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| approved_at | timestamp without time zone | timestamp | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| logo_url | text | text | YES |  | NO |
| is_visible | boolean | bool | YES | true | NO |
| consultant_products | text | text | YES |  | NO |
| kakao_chat_url | text | text | YES |  | NO |
| priority_score | integer | int4 | YES | 0 | NO |
| admin_memo | text | text | YES |  | NO |
| service_region | text | text | YES |  | NO |
| office_address | text | text | YES |  | NO |
| tax_invoice_email | text | text | YES |  | NO |
| rejection_reason | text | text | YES |  | NO |
| manager_name | text | text | YES |  | NO |
| desired_building | text | text | YES |  | NO |
| weekly_email_enabled | boolean | bool | NO | true | NO |
| weekly_email_opted_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_email_updated_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_unsubscribe_token | uuid | uuid | NO | gen_random_uuid() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | loan_consultants_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) |
| u | loan_consultants_email_unique | - | UNIQUE (email) |
| u | loan_consultants_license_number_unique | - | UNIQUE (license_number) |
| p | loan_consultants_pkey | - | PRIMARY KEY (id) |
| u | loan_consultants_subdomain_slug_unique | - | UNIQUE (subdomain_slug) |
| indexname | indexdef |
| --- | --- |
| loan_consultants_email_unique | CREATE UNIQUE INDEX loan_consultants_email_unique ON public.loan_consultants USING btree (email) |
| loan_consultants_license_number_unique | CREATE UNIQUE INDEX loan_consultants_license_number_unique ON public.loan_consultants USING btree (license_number) |
| loan_consultants_pkey | CREATE UNIQUE INDEX loan_consultants_pkey ON public.loan_consultants USING btree (id) |
| loan_consultants_subdomain_slug_unique | CREATE UNIQUE INDEX loan_consultants_subdomain_slug_unique ON public.loan_consultants USING btree (subdomain_slug) |
| uq_loan_consultants_weekly_unsubscribe_token | CREATE UNIQUE INDEX uq_loan_consultants_weekly_unsubscribe_token ON public.loan_consultants USING btree (weekly_unsubscribe_token) |

### lodging_approval_attempts
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_approval_attempts_id_seq'::regclass) | NO |
| approval_batch_id | bigint | int8 | NO |  | NO |
| run_id | text | text | NO |  | NO |
| attempt_number | integer | int4 | NO |  | NO |
| mode | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| result | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| error | text | text | YES |  | NO |
| started_at | timestamp without time zone | timestamp | NO | now() | NO |
| heartbeat_at | timestamp without time zone | timestamp | NO | now() | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | lodging_approval_attempts_approval_batch_id_attempt_number_key | - | UNIQUE (approval_batch_id, attempt_number) |
| f | lodging_approval_attempts_approval_batch_id_fkey | lodging_approval_batches | FOREIGN KEY (approval_batch_id) REFERENCES lodging_approval_batches(id) ON DELETE CASCADE |
| c | lodging_approval_attempts_mode_check | - | CHECK ((mode = ANY (ARRAY['dry_run'::text, 'apply'::text]))) |
| p | lodging_approval_attempts_pkey | - | PRIMARY KEY (id) |
| c | lodging_approval_attempts_status_check | - | CHECK ((status = ANY (ARRAY['running'::text, 'done'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_approval_attempts_run | CREATE INDEX idx_lodging_approval_attempts_run ON public.lodging_approval_attempts USING btree (run_id, attempt_number DESC) |
| lodging_approval_attempts_approval_batch_id_attempt_number_key | CREATE UNIQUE INDEX lodging_approval_attempts_approval_batch_id_attempt_number_key ON public.lodging_approval_attempts USING btree (approval_batch_id, attempt_number) |
| lodging_approval_attempts_pkey | CREATE UNIQUE INDEX lodging_approval_attempts_pkey ON public.lodging_approval_attempts USING btree (id) |

### lodging_approval_batches
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_approval_batches_id_seq'::regclass) | NO |
| approval_key | text | text | NO |  | NO |
| source_batch_id | bigint | int8 | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| row_count | integer | int4 | NO | 0 | NO |
| result | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| error | text | text | YES |  | NO |
| run_id | text | text | YES |  | NO |
| created_by | integer | int4 | NO |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| approved_at | timestamp without time zone | timestamp | YES |  | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| heartbeat_at | timestamp without time zone | timestamp | YES |  | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | lodging_approval_batches_approval_key_key | - | UNIQUE (approval_key) |
| f | lodging_approval_batches_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| f | lodging_approval_batches_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| p | lodging_approval_batches_pkey | - | PRIMARY KEY (id) |
| u | lodging_approval_batches_run_id_key | - | UNIQUE (run_id) |
| f | lodging_approval_batches_source_batch_id_fkey | lodging_source_batches | FOREIGN KEY (source_batch_id) REFERENCES lodging_source_batches(id) ON DELETE RESTRICT |
| c | lodging_approval_batches_status_check | - | CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'dry_run'::text, 'applied'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| lodging_approval_batches_approval_key_key | CREATE UNIQUE INDEX lodging_approval_batches_approval_key_key ON public.lodging_approval_batches USING btree (approval_key) |
| lodging_approval_batches_pkey | CREATE UNIQUE INDEX lodging_approval_batches_pkey ON public.lodging_approval_batches USING btree (id) |
| lodging_approval_batches_run_id_key | CREATE UNIQUE INDEX lodging_approval_batches_run_id_key ON public.lodging_approval_batches USING btree (run_id) |
| uq_lodging_approval_source_batch | CREATE UNIQUE INDEX uq_lodging_approval_source_batch ON public.lodging_approval_batches USING btree (source_batch_id) |

### lodging_approval_rows
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| approval_batch_id | bigint | int8 | NO |  | NO |
| source_row_id | bigint | int8 | NO |  | NO |
| action | text | text | NO |  | NO |
| payload | jsonb | jsonb | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | lodging_approval_rows_action_check | - | CHECK ((action = ANY (ARRAY['insert'::text, 'update'::text, 'status_change'::text]))) |
| f | lodging_approval_rows_approval_batch_id_fkey | lodging_approval_batches | FOREIGN KEY (approval_batch_id) REFERENCES lodging_approval_batches(id) ON DELETE CASCADE |
| p | lodging_approval_rows_pkey | - | PRIMARY KEY (approval_batch_id, source_row_id) |
| f | lodging_approval_rows_source_row_id_fkey | lodging_source_rows | FOREIGN KEY (source_row_id) REFERENCES lodging_source_rows(id) ON DELETE RESTRICT |
| indexname | indexdef |
| --- | --- |
| lodging_approval_rows_pkey | CREATE UNIQUE INDEX lodging_approval_rows_pkey ON public.lodging_approval_rows USING btree (approval_batch_id, source_row_id) |

### lodging_authority_contacts
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('lodging_authority_contacts_id_seq'::regclass) | NO |
| region_name_raw | text | text | NO |  | NO |
| dept | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | lodging_authority_contacts_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| lodging_authority_contacts_pkey | CREATE UNIQUE INDEX lodging_authority_contacts_pkey ON public.lodging_authority_contacts USING btree (id) |

### lodging_import_staging
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| token | text | text | NO |  | NO |
| source | text | text | NO |  | NO |
| filename | text | text | NO |  | NO |
| file_ext | text | text | NO |  | NO |
| file_data | bytea | bytea | NO |  | NO |
| preview | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| uploaded_by | integer | int4 | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| result | jsonb | jsonb | YES |  | NO |
| error | text | text | YES |  | NO |
| heartbeat_at | timestamp without time zone | timestamp | YES |  | NO |
| run_id | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | lodging_import_staging_pkey | - | PRIMARY KEY (token) |
| c | lodging_import_staging_source_check | - | CHECK ((source = ANY (ARRAY['airbnb'::text, 'rural'::text, 'hanok'::text]))) |
| c | lodging_import_staging_status_check | - | CHECK ((status = ANY (ARRAY['preview'::text, 'applying'::text, 'done'::text, 'failed'::text]))) |
| f | lodging_import_staging_uploaded_by_fkey | admin_users | FOREIGN KEY (uploaded_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| indexname | indexdef |
| --- | --- |
| idx_lodging_import_staging_recent | CREATE INDEX idx_lodging_import_staging_recent ON public.lodging_import_staging USING btree (source, created_at DESC) |
| lodging_import_staging_pkey | CREATE UNIQUE INDEX lodging_import_staging_pkey ON public.lodging_import_staging USING btree (token) |

### lodging_operator_phone_challenges
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | uuid | NO |  | NO |
| phone | text | text | NO |  | NO |
| otp_digest | text | text | NO |  | NO |
| ip_hash | text | text | NO |  | NO |
| expires_at | timestamp with time zone | timestamptz | NO |  | NO |
| attempt_count | integer | int4 | NO | 0 | NO |
| verified_at | timestamp with time zone | timestamptz | YES |  | NO |
| consumed_at | timestamp with time zone | timestamptz | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | lodging_operator_phone_challenges_attempt_count_check | - | CHECK (((attempt_count >= 0) AND (attempt_count <= 5))) |
| p | lodging_operator_phone_challenges_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_op_challenge_ip_created | CREATE INDEX idx_lodging_op_challenge_ip_created ON public.lodging_operator_phone_challenges USING btree (ip_hash, created_at DESC) |
| idx_lodging_op_challenge_phone_created | CREATE INDEX idx_lodging_op_challenge_phone_created ON public.lodging_operator_phone_challenges USING btree (phone, created_at DESC) |
| lodging_operator_phone_challenges_pkey | CREATE UNIQUE INDEX lodging_operator_phone_challenges_pkey ON public.lodging_operator_phone_challenges USING btree (id) |

### lodging_parallel_comparisons
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_parallel_comparisons_id_seq'::regclass) | NO |
| promotion_manifest_id | bigint | int8 | NO |  | NO |
| run_id | text | text | NO |  | NO |
| production_fingerprint | text | text | NO |  | NO |
| result | jsonb | jsonb | NO |  | NO |
| major_regression_count | integer | int4 | NO | 0 | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | lodging_parallel_comparisons_pkey | - | PRIMARY KEY (id) |
| f | lodging_parallel_comparisons_promotion_manifest_id_fkey | lodging_promotion_manifests | FOREIGN KEY (promotion_manifest_id) REFERENCES lodging_promotion_manifests(id) ON DELETE RESTRICT |
| u | lodging_parallel_comparisons_run_id_key | - | UNIQUE (run_id) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_parallel_comparisons_recent | CREATE INDEX idx_lodging_parallel_comparisons_recent ON public.lodging_parallel_comparisons USING btree (promotion_manifest_id, created_at DESC, id DESC) |
| lodging_parallel_comparisons_pkey | CREATE UNIQUE INDEX lodging_parallel_comparisons_pkey ON public.lodging_parallel_comparisons USING btree (id) |
| lodging_parallel_comparisons_run_id_key | CREATE UNIQUE INDEX lodging_parallel_comparisons_run_id_key ON public.lodging_parallel_comparisons USING btree (run_id) |

### lodging_promotion_manifests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_promotion_manifests_id_seq'::regclass) | NO |
| manifest_key | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| source_batch_ids | jsonb | jsonb | NO |  | NO |
| production_baseline_fingerprint | text | text | NO |  | NO |
| target_payload_sha256 | text | text | NO |  | NO |
| row_count | integer | int4 | NO | 0 | NO |
| result | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| error | text | text | YES |  | NO |
| run_id | text | text | NO |  | NO |
| created_by | integer | int4 | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| approved_at | timestamp without time zone | timestamp | YES |  | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| heartbeat_at | timestamp without time zone | timestamp | YES |  | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| parent_manifest_id | bigint | int8 | YES |  | NO |
| version_no | integer | int4 | NO | 1 | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | lodging_promotion_manifests_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) ON DELETE RESTRICT |
| f | lodging_promotion_manifests_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE RESTRICT |
| u | lodging_promotion_manifests_manifest_key_key | - | UNIQUE (manifest_key) |
| f | lodging_promotion_manifests_parent_manifest_id_fkey | lodging_promotion_manifests | FOREIGN KEY (parent_manifest_id) REFERENCES lodging_promotion_manifests(id) ON DELETE RESTRICT |
| p | lodging_promotion_manifests_pkey | - | PRIMARY KEY (id) |
| u | lodging_promotion_manifests_run_id_key | - | UNIQUE (run_id) |
| c | lodging_promotion_manifests_status_check | - | CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'dry_run'::text, 'applied'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_promotion_manifests_recent | CREATE INDEX idx_lodging_promotion_manifests_recent ON public.lodging_promotion_manifests USING btree (created_at DESC) |
| lodging_promotion_manifests_manifest_key_key | CREATE UNIQUE INDEX lodging_promotion_manifests_manifest_key_key ON public.lodging_promotion_manifests USING btree (manifest_key) |
| lodging_promotion_manifests_pkey | CREATE UNIQUE INDEX lodging_promotion_manifests_pkey ON public.lodging_promotion_manifests USING btree (id) |
| lodging_promotion_manifests_run_id_key | CREATE UNIQUE INDEX lodging_promotion_manifests_run_id_key ON public.lodging_promotion_manifests USING btree (run_id) |

### lodging_promotion_review_decisions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_promotion_review_decisions_id_seq'::regclass) | NO |
| source_row_id | bigint | int8 | NO |  | NO |
| base_manifest_id | bigint | int8 | NO |  | NO |
| resulting_manifest_id | bigint | int8 | NO |  | NO |
| decision | text | text | NO |  | NO |
| decision_note | text | text | YES |  | NO |
| decided_by | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | lodging_promotion_review_deci_base_manifest_id_source_row_i_key | - | UNIQUE (base_manifest_id, source_row_id) |
| f | lodging_promotion_review_decisions_base_manifest_id_fkey | lodging_promotion_manifests | FOREIGN KEY (base_manifest_id) REFERENCES lodging_promotion_manifests(id) ON DELETE RESTRICT |
| f | lodging_promotion_review_decisions_decided_by_fkey | admin_users | FOREIGN KEY (decided_by) REFERENCES admin_users(id) ON DELETE RESTRICT |
| c | lodging_promotion_review_decisions_decision_check | - | CHECK ((decision = ANY (ARRAY['exclude'::text, 'include_unclassified_history'::text]))) |
| p | lodging_promotion_review_decisions_pkey | - | PRIMARY KEY (id) |
| f | lodging_promotion_review_decisions_resulting_manifest_id_fkey | lodging_promotion_manifests | FOREIGN KEY (resulting_manifest_id) REFERENCES lodging_promotion_manifests(id) ON DELETE RESTRICT |
| f | lodging_promotion_review_decisions_source_row_id_fkey | lodging_source_rows | FOREIGN KEY (source_row_id) REFERENCES lodging_source_rows(id) ON DELETE RESTRICT |
| indexname | indexdef |
| --- | --- |
| idx_lodging_promotion_review_decisions_manifest | CREATE INDEX idx_lodging_promotion_review_decisions_manifest ON public.lodging_promotion_review_decisions USING btree (resulting_manifest_id, created_at DESC) |
| lodging_promotion_review_deci_base_manifest_id_source_row_i_key | CREATE UNIQUE INDEX lodging_promotion_review_deci_base_manifest_id_source_row_i_key ON public.lodging_promotion_review_decisions USING btree (base_manifest_id, source_row_id) |
| lodging_promotion_review_decisions_pkey | CREATE UNIQUE INDEX lodging_promotion_review_decisions_pkey ON public.lodging_promotion_review_decisions USING btree (id) |

### lodging_promotion_rows
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| promotion_manifest_id | bigint | int8 | NO |  | NO |
| source_row_id | bigint | int8 | NO |  | NO |
| action | text | text | NO |  | NO |
| production_match_state | text | text | YES |  | NO |
| production_building_id | integer | int4 | YES |  | NO |
| existing_applied_building_id | integer | int4 | YES |  | NO |
| payload | jsonb | jsonb | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | lodging_promotion_rows_action_check | - | CHECK ((action = ANY (ARRAY['insert'::text, 'update'::text, 'status_change'::text]))) |
| p | lodging_promotion_rows_pkey | - | PRIMARY KEY (promotion_manifest_id, source_row_id) |
| f | lodging_promotion_rows_promotion_manifest_id_fkey | lodging_promotion_manifests | FOREIGN KEY (promotion_manifest_id) REFERENCES lodging_promotion_manifests(id) ON DELETE CASCADE |
| f | lodging_promotion_rows_source_row_id_fkey | lodging_source_rows | FOREIGN KEY (source_row_id) REFERENCES lodging_source_rows(id) ON DELETE RESTRICT |
| indexname | indexdef |
| --- | --- |
| idx_lodging_promotion_rows_action | CREATE INDEX idx_lodging_promotion_rows_action ON public.lodging_promotion_rows USING btree (promotion_manifest_id, action) |
| lodging_promotion_rows_pkey | CREATE UNIQUE INDEX lodging_promotion_rows_pkey ON public.lodging_promotion_rows USING btree (promotion_manifest_id, source_row_id) |

### lodging_registry
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('lodging_registry_id_seq'::regclass) | NO |
| biz_name | text | text | NO |  | NO |
| permit_number | text | text | NO |  | NO |
| road_address | text | text | YES |  | NO |
| jibun_address | text | text | YES |  | NO |
| permit_date | text | text | YES |  | NO |
| biz_status_name | text | text | YES |  | NO |
| biz_status_detail | text | text | YES |  | NO |
| room_count | integer | int4 | YES |  | NO |
| hygiene_type | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| road_norm | text | text | YES |  | NO |
| source_updated_at | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| biz_name_norm | text | text | YES |  | NO |
| jibun_norm | text | text | YES |  | NO |
| applied_building_id | integer | int4 | YES |  | NO |
| dismissed_at | timestamp without time zone | timestamp | YES |  | NO |
| bld_use_nm | text | text | YES |  | NO |
| facility_area | numeric | numeric | YES |  | NO |
| region_name | text | text | YES |  | NO |
| camping_site_count | integer | int4 | YES |  | NO |
| camping_general_site_count | integer | int4 | YES |  | NO |
| camping_auto_site_count | integer | int4 | YES |  | NO |
| camping_glamping_site_count | integer | int4 | YES |  | NO |
| camping_caravan_site_count | integer | int4 | YES |  | NO |
| camping_classification | text | text | YES |  | NO |
| camping_location_types | text | text | YES |  | NO |
| camping_theme_types | text | text | YES |  | NO |
| camping_amenities | text | text | YES |  | NO |
| camping_toilet_count | integer | int4 | YES |  | NO |
| camping_shower_count | integer | int4 | YES |  | NO |
| camping_sink_count | integer | int4 | YES |  | NO |
| camping_operating_seasons | text | text | YES |  | NO |
| camping_animal_policy | text | text | YES |  | NO |
| camping_reservation_url | text | text | YES |  | NO |
| camping_first_image_url | text | text | YES |  | NO |
| camping_image_urls | jsonb | jsonb | YES |  | NO |
| gocamping_content_id | text | text | YES |  | NO |
| gocamping_detail | jsonb | jsonb | YES |  | NO |
| gocamping_detail_fetched_at | timestamp without time zone | timestamp | YES |  | NO |
| western_rooms | integer | int4 | YES |  | NO |
| korean_rooms | integer | int4 | YES |  | NO |
| toilet_count | integer | int4 | YES |  | NO |
| toilet_type | text | text | YES |  | NO |
| breakfast_yn | text | text | YES |  | NO |
| house_area | numeric | numeric | YES |  | NO |
| zone_type | text | text | YES |  | NO |
| surroundings | text | text | YES |  | NO |
| floors_above | integer | int4 | YES |  | NO |
| floors_below | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | lodging_registry_applied_building_id_fkey | master_buildings | FOREIGN KEY (applied_building_id) REFERENCES master_buildings(id) |
| u | lodging_registry_permit_number_key | - | UNIQUE (permit_number) |
| p | lodging_registry_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_registry_gocamping_content | CREATE INDEX idx_lodging_registry_gocamping_content ON public.lodging_registry USING btree (gocamping_content_id) WHERE (gocamping_content_id IS NOT NULL) |
| idx_lodging_registry_jibun_norm | CREATE INDEX idx_lodging_registry_jibun_norm ON public.lodging_registry USING btree (jibun_norm) |
| idx_lodging_registry_name_norm | CREATE INDEX idx_lodging_registry_name_norm ON public.lodging_registry USING btree (biz_name_norm) |
| idx_lodging_registry_road_norm | CREATE INDEX idx_lodging_registry_road_norm ON public.lodging_registry USING btree (road_norm) |
| idx_lodging_registry_status | CREATE INDEX idx_lodging_registry_status ON public.lodging_registry USING btree (biz_status_name) |
| lodging_registry_permit_number_key | CREATE UNIQUE INDEX lodging_registry_permit_number_key ON public.lodging_registry USING btree (permit_number) |
| lodging_registry_pkey | CREATE UNIQUE INDEX lodging_registry_pkey ON public.lodging_registry USING btree (id) |

### lodging_registry_alert_snapshots
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| permit_number | text | text | NO |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| biz_status_name | text | text | YES |  | NO |
| biz_status_detail | text | text | YES |  | NO |
| room_count | integer | int4 | YES |  | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | lodging_registry_alert_snapshots_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| p | lodging_registry_alert_snapshots_pkey | - | PRIMARY KEY (permit_number) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_alert_snapshots_building | CREATE INDEX idx_lodging_alert_snapshots_building ON public.lodging_registry_alert_snapshots USING btree (master_building_id) |
| lodging_registry_alert_snapshots_pkey | CREATE UNIQUE INDEX lodging_registry_alert_snapshots_pkey ON public.lodging_registry_alert_snapshots USING btree (permit_number) |

### lodging_source_batches
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_source_batches_id_seq'::regclass) | NO |
| batch_key | text | text | NO |  | NO |
| source_key | text | text | NO |  | NO |
| filename | text | text | NO |  | NO |
| file_ext | text | text | NO |  | NO |
| file_sha256 | text | text | NO |  | NO |
| reference_date | date | date | NO |  | NO |
| file_data | bytea | bytea | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| total_rows | integer | int4 | NO | 0 | NO |
| parsed_rows | integer | int4 | NO | 0 | NO |
| valid_rows | integer | int4 | NO | 0 | NO |
| review_rows | integer | int4 | NO | 0 | NO |
| result | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| error | text | text | YES |  | NO |
| uploaded_by | integer | int4 | YES |  | NO |
| run_id | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| heartbeat_at | timestamp without time zone | timestamp | YES |  | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | lodging_source_batches_batch_key_key | - | UNIQUE (batch_key) |
| p | lodging_source_batches_pkey | - | PRIMARY KEY (id) |
| c | lodging_source_batches_source_key_check | - | CHECK ((source_key = ANY (ARRAY['tourism_lodging'::text, 'tourism_pension'::text, 'rural_homestay'::text, 'lodging'::text, 'foreign_city_homestay'::text, 'general_camping'::text, 'auto_camping'::text, 'hanok'::text]))) |
| c | lodging_source_batches_status_check | - | CHECK ((status = ANY (ARRAY['uploaded'::text, 'parsed'::text, 'validating'::text, 'review_required'::text, 'validated'::text, 'approved'::text, 'dry_run'::text, 'applied'::text, 'failed'::text]))) |
| f | lodging_source_batches_uploaded_by_fkey | admin_users | FOREIGN KEY (uploaded_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| indexname | indexdef |
| --- | --- |
| idx_lodging_source_batches_recent | CREATE INDEX idx_lodging_source_batches_recent ON public.lodging_source_batches USING btree (source_key, created_at DESC) |
| lodging_source_batches_batch_key_key | CREATE UNIQUE INDEX lodging_source_batches_batch_key_key ON public.lodging_source_batches USING btree (batch_key) |
| lodging_source_batches_pkey | CREATE UNIQUE INDEX lodging_source_batches_pkey ON public.lodging_source_batches USING btree (id) |
| uq_lodging_source_batch_snapshot | CREATE UNIQUE INDEX uq_lodging_source_batch_snapshot ON public.lodging_source_batches USING btree (source_key, reference_date, file_sha256) |

### lodging_source_rows
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('lodging_source_rows_id_seq'::regclass) | NO |
| batch_id | bigint | int8 | NO |  | NO |
| row_number | integer | int4 | NO |  | NO |
| snapshot_key | text | text | NO |  | NO |
| authority_code | text | text | YES |  | NO |
| source_permit_number | text | text | YES |  | NO |
| permit_number | text | text | YES |  | NO |
| biz_name | text | text | YES |  | NO |
| raw_hygiene_type | text | text | YES |  | NO |
| service_category | text | text | YES |  | NO |
| legacy_lodging_type | text | text | YES |  | NO |
| raw_status | text | text | YES |  | NO |
| status_bucket | text | text | NO |  | NO |
| road_address | text | text | YES |  | NO |
| jibun_address | text | text | YES |  | NO |
| raw_record | jsonb | jsonb | NO |  | NO |
| row_state | text | text | NO | <literal-redacted>::text | NO |
| review_reason | text | text | YES |  | NO |
| diff_kind | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | lodging_source_rows_batch_id_fkey | lodging_source_batches | FOREIGN KEY (batch_id) REFERENCES lodging_source_batches(id) ON DELETE CASCADE |
| u | lodging_source_rows_batch_id_row_number_key | - | UNIQUE (batch_id, row_number) |
| u | lodging_source_rows_batch_id_row_number_snapshot_key_key | - | UNIQUE (batch_id, row_number, snapshot_key) |
| c | lodging_source_rows_diff_kind_check | - | CHECK ((diff_kind = ANY (ARRAY['new'::text, 'changed'::text, 'unchanged'::text, 'status_change'::text, 'review_required'::text]))) |
| p | lodging_source_rows_pkey | - | PRIMARY KEY (id) |
| c | lodging_source_rows_row_state_check | - | CHECK ((row_state = ANY (ARRAY['validated'::text, 'review_required'::text, 'invalid'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_lodging_source_rows_batch_state | CREATE INDEX idx_lodging_source_rows_batch_state ON public.lodging_source_rows USING btree (batch_id, row_state) |
| idx_lodging_source_rows_snapshot | CREATE INDEX idx_lodging_source_rows_snapshot ON public.lodging_source_rows USING btree (snapshot_key) |
| lodging_source_rows_batch_id_row_number_key | CREATE UNIQUE INDEX lodging_source_rows_batch_id_row_number_key ON public.lodging_source_rows USING btree (batch_id, row_number) |
| lodging_source_rows_batch_id_row_number_snapshot_key_key | CREATE UNIQUE INDEX lodging_source_rows_batch_id_row_number_snapshot_key_key ON public.lodging_source_rows USING btree (batch_id, row_number, snapshot_key) |
| lodging_source_rows_pkey | CREATE UNIQUE INDEX lodging_source_rows_pkey ON public.lodging_source_rows USING btree (id) |

### login_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('login_history_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| logged_in_at | timestamp with time zone | timestamptz | NO | now() | NO |
| ip_hash | text | text | YES |  | NO |
| user_agent | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | login_history_pkey | - | PRIMARY KEY (id) |
| f | login_history_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_login_history_user | CREATE INDEX idx_login_history_user ON public.login_history USING btree (user_id, logged_in_at DESC) |
| login_history_pkey | CREATE UNIQUE INDEX login_history_pkey ON public.login_history USING btree (id) |

### master_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('master_buildings_id_seq'::regclass) | NO |
| building_name | text | text | NO |  | NO |
| road_address | text | text | NO |  | NO |
| jibun_address | text | text | YES |  | NO |
| sgg_text | text | text | YES |  | NO |
| sgg_cd | text | text | YES |  | NO |
| umd_nm | text | text | YES |  | NO |
| jibun | text | text | YES |  | NO |
| units | integer | int4 | YES |  | NO |
| biz_units | integer | int4 | YES |  | NO |
| source | text | text | YES | <literal-redacted>::text | NO |
| verified_at | timestamp without time zone | timestamp | YES |  | NO |
| lodging_type | text | text | YES |  | NO |
| lodging_type_detail | text | text | YES |  | NO |
| lat | double precision | float8 | YES |  | NO |
| lng | double precision | float8 | YES |  | NO |
| slot_capacity | integer | int4 | YES | 3 | NO |
| use_apr_day | text | text | YES |  | NO |
| tot_pkng_cnt | integer | int4 | YES |  | NO |
| grnd_flr_cnt | integer | int4 | YES |  | NO |
| ugrnd_flr_cnt | integer | int4 | YES |  | NO |
| tot_area | double precision | float8 | YES |  | NO |
| plat_area | double precision | float8 | YES |  | NO |
| hhld_cnt | integer | int4 | YES |  | NO |
| strct_nm | text | text | YES |  | NO |
| title_backfilled_at | timestamp without time zone | timestamp | YES |  | NO |
| mgm_bldrgst_pk | text | text | YES |  | NO |
| name_pending | boolean | bool | YES | false | NO |
| building_status | text | text | YES | <literal-redacted>::text | NO |
| completion_expected_date | date | date | YES |  | NO |
| permit_day | text | text | YES |  | NO |
| actual_start_day | text | text | YES |  | NO |
| arch_area | double precision | float8 | YES |  | NO |
| bc_rat | double precision | float8 | YES |  | NO |
| vl_rat | double precision | float8 | YES |  | NO |
| source_key | text | text | YES |  | NO |
| realty_store_name | text | text | YES |  | NO |
| realty_checked_at | timestamp without time zone | timestamp | YES |  | NO |
| heit | double precision | float8 | YES |  | NO |
| ride_use_elvt_cnt | integer | int4 | YES |  | NO |
| emgen_use_elvt_cnt | integer | int4 | YES |  | NO |
| main_purps_nm | text | text | YES |  | NO |
| jiyuk_nm | text | text | YES |  | NO |
| jigu_nm | text | text | YES |  | NO |
| guyuk_nm | text | text | YES |  | NO |
| last_inspection_agency | text | text | YES |  | NO |
| last_inspection_start_day | text | text | YES |  | NO |
| last_inspection_submit_day | text | text | YES |  | NO |
| detail_fetched_at | timestamp without time zone | timestamp | YES |  | NO |
| indr_auto_utcnt | integer | int4 | YES |  | NO |
| oudr_auto_utcnt | integer | int4 | YES |  | NO |
| indr_mech_utcnt | integer | int4 | YES |  | NO |
| oudr_mech_utcnt | integer | int4 | YES |  | NO |
| lodging_subtype | text | text | YES |  | NO |
| booking_url | text | text | YES |  | NO |
| booking_url_source | text | text | YES |  | NO |
| booking_url_updated_at | timestamp without time zone | timestamp | YES |  | NO |
| booking_url_expires_at | timestamp without time zone | timestamp | YES |  | NO |
| zip_code | text | text | YES |  | NO |
| building_name_source | text | text | YES | <literal-redacted>::text | NO |
| building_name_candidate_count | integer | int4 | YES | 0 | NO |
| building_name_pending_base | text | text | YES |  | NO |
| kakao_promo_copy_count | integer | int4 | NO | 0 | NO |
| building_use_type | text | text | YES |  | NO |
| building_use_detail | text | text | YES |  | NO |
| lodging_classification_source | text | text | YES |  | NO |
| lodging_classification_confidence | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | master_buildings_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_mb_sgg_umd_jibun | CREATE INDEX idx_mb_sgg_umd_jibun ON public.master_buildings USING btree (sgg_cd, umd_nm, jibun) |
| master_buildings_lat_lng_idx | CREATE INDEX master_buildings_lat_lng_idx ON public.master_buildings USING btree (lat, lng) WHERE ((lat IS NOT NULL) AND (lng IS NOT NULL)) |
| master_buildings_pkey | CREATE UNIQUE INDEX master_buildings_pkey ON public.master_buildings USING btree (id) |
| master_buildings_source_key_uidx | CREATE UNIQUE INDEX master_buildings_source_key_uidx ON public.master_buildings USING btree (source_key) WHERE (source_key IS NOT NULL) |

### member_documents
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('member_documents_id_seq'::regclass) | NO |
| member_type | text | text | NO |  | NO |
| member_id | integer | int4 | NO |  | NO |
| doc_type | character varying | varchar | NO |  | NO |
| file_key | text | text | NO |  | NO |
| file_type | character varying | varchar | NO |  | NO |
| uploaded_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | member_documents_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_member_docs_member | CREATE INDEX idx_member_docs_member ON public.member_documents USING btree (member_type, member_id) |
| member_documents_pkey | CREATE UNIQUE INDEX member_documents_pkey ON public.member_documents USING btree (id) |

### member_notes
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('member_notes_id_seq'::regclass) | NO |
| member_type | text | text | NO |  | NO |
| member_id | integer | int4 | NO |  | NO |
| memo_date | date | date | NO | CURRENT_DATE | NO |
| content | text | text | NO |  | NO |
| author_name | character varying | varchar | NO | <literal-redacted>::character varying | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES |  | NO |
| is_deleted | boolean | bool | NO | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | member_notes_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_member_notes_member | CREATE INDEX idx_member_notes_member ON public.member_notes USING btree (member_type, member_id, created_at DESC) |
| member_notes_pkey | CREATE UNIQUE INDEX member_notes_pkey ON public.member_notes USING btree (id) |

### membership_checks
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('membership_checks_id_seq'::regclass) | NO |
| period_id | bigint | int8 | NO |  | NO |
| user_id | integer | int4 | NO |  | NO |
| request_no | text | text | NO |  | NO |
| request_token | text | text | NO |  | NO |
| building_id | integer | int4 | YES |  | NO |
| auction_id | bigint | int8 | YES |  | NO |
| title | text | text | NO |  | NO |
| address | text | text | NO |  | NO |
| memo | text | text | NO | <literal-redacted>::text | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| business_report | text | text | NO | <literal-redacted>::text | NO |
| operation_succession | text | text | NO | <literal-redacted>::text | NO |
| fee_arrears | text | text | NO | <literal-redacted>::text | NO |
| report | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | membership_checks_business_report_check | - | CHECK ((business_report = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| c | membership_checks_check | - | CHECK (((building_id IS NOT NULL) OR (auction_id IS NOT NULL))) |
| c | membership_checks_fee_arrears_check | - | CHECK ((fee_arrears = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| c | membership_checks_operation_succession_check | - | CHECK ((operation_succession = ANY (ARRAY['need_check'::text, 'ok'::text, 'issue'::text]))) |
| f | membership_checks_period_id_fkey | membership_periods | FOREIGN KEY (period_id) REFERENCES membership_periods(id) |
| u | membership_checks_period_id_key | - | UNIQUE (period_id) |
| p | membership_checks_pkey | - | PRIMARY KEY (id) |
| u | membership_checks_request_no_key | - | UNIQUE (request_no) |
| c | membership_checks_status_check | - | CHECK ((status = ANY (ARRAY['received'::text, 'investigating'::text, 'reported'::text]))) |
| f | membership_checks_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| u | membership_checks_user_id_request_token_key | - | UNIQUE (user_id, request_token) |
| indexname | indexdef |
| --- | --- |
| membership_checks_period_id_key | CREATE UNIQUE INDEX membership_checks_period_id_key ON public.membership_checks USING btree (period_id) |
| membership_checks_pkey | CREATE UNIQUE INDEX membership_checks_pkey ON public.membership_checks USING btree (id) |
| membership_checks_request_no_key | CREATE UNIQUE INDEX membership_checks_request_no_key ON public.membership_checks USING btree (request_no) |
| membership_checks_user_id_request_token_key | CREATE UNIQUE INDEX membership_checks_user_id_request_token_key ON public.membership_checks USING btree (user_id, request_token) |

### membership_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('membership_history_id_seq'::regclass) | NO |
| payment_id | bigint | int8 | YES |  | NO |
| check_id | bigint | int8 | YES |  | NO |
| actor | text | text | NO |  | NO |
| event | text | text | NO |  | NO |
| note | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | membership_history_check_id_fkey | membership_checks | FOREIGN KEY (check_id) REFERENCES membership_checks(id) |
| f | membership_history_payment_id_fkey | membership_payments | FOREIGN KEY (payment_id) REFERENCES membership_payments(id) |
| p | membership_history_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| membership_history_pkey | CREATE UNIQUE INDEX membership_history_pkey ON public.membership_history USING btree (id) |

### membership_payments
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('membership_payments_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| request_no | text | text | NO |  | NO |
| request_token | text | text | NO |  | NO |
| depositor_name | text | text | NO |  | NO |
| amount | integer | int4 | NO | 29000 | NO |
| bank | jsonb | jsonb | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| approved_by | integer | int4 | YES |  | NO |
| admin_note | text | text | NO | <literal-redacted>::text | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | membership_payments_amount_check | - | CHECK ((amount = 29000)) |
| p | membership_payments_pkey | - | PRIMARY KEY (id) |
| u | membership_payments_request_no_key | - | UNIQUE (request_no) |
| c | membership_payments_status_check | - | CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text, 'canceled'::text, 'revoked'::text]))) |
| f | membership_payments_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| u | membership_payments_user_id_request_token_key | - | UNIQUE (user_id, request_token) |
| indexname | indexdef |
| --- | --- |
| membership_one_pending | CREATE UNIQUE INDEX membership_one_pending ON public.membership_payments USING btree (user_id) WHERE (status = 'pending'::text) |
| membership_payment_queue | CREATE INDEX membership_payment_queue ON public.membership_payments USING btree (status, created_at DESC) |
| membership_payments_pkey | CREATE UNIQUE INDEX membership_payments_pkey ON public.membership_payments USING btree (id) |
| membership_payments_request_no_key | CREATE UNIQUE INDEX membership_payments_request_no_key ON public.membership_payments USING btree (request_no) |
| membership_payments_user_id_request_token_key | CREATE UNIQUE INDEX membership_payments_user_id_request_token_key ON public.membership_payments USING btree (user_id, request_token) |

### membership_periods
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('membership_periods_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| payment_id | bigint | int8 | NO |  | NO |
| starts_at | timestamp with time zone | timestamptz | NO |  | NO |
| ends_at | timestamp with time zone | timestamptz | NO |  | NO |
| revoked_at | timestamp with time zone | timestamptz | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | membership_periods_check | - | CHECK ((ends_at > starts_at)) |
| f | membership_periods_payment_id_fkey | membership_payments | FOREIGN KEY (payment_id) REFERENCES membership_payments(id) |
| u | membership_periods_payment_id_key | - | UNIQUE (payment_id) |
| p | membership_periods_pkey | - | PRIMARY KEY (id) |
| f | membership_periods_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| membership_period_user | CREATE INDEX membership_period_user ON public.membership_periods USING btree (user_id, ends_at) |
| membership_periods_payment_id_key | CREATE UNIQUE INDEX membership_periods_payment_id_key ON public.membership_periods USING btree (payment_id) |
| membership_periods_pkey | CREATE UNIQUE INDEX membership_periods_pkey ON public.membership_periods USING btree (id) |

### mileage_missions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('mileage_missions_id_seq'::regclass) | NO |
| code | text | text | NO |  | NO |
| title | text | text | NO |  | NO |
| points | integer | int4 | NO |  | NO |
| tier | text | text | YES | <literal-redacted>::text | NO |
| active | boolean | bool | YES | true | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | mileage_missions_code_unique | - | UNIQUE (code) |
| p | mileage_missions_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| mileage_missions_code_unique | CREATE UNIQUE INDEX mileage_missions_code_unique ON public.mileage_missions USING btree (code) |
| mileage_missions_pkey | CREATE UNIQUE INDEX mileage_missions_pkey ON public.mileage_missions USING btree (id) |

### mileage_submissions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('mileage_submissions_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| mission_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| photo_urls | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| points_awarded | integer | int4 | YES |  | NO |
| submitted_at | timestamp without time zone | timestamp | YES | now() | NO |
| reviewed_at | timestamp without time zone | timestamp | YES |  | NO |
| reviewed_by | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | mileage_submissions_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) |
| f | mileage_submissions_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| f | mileage_submissions_mission_id_fkey | mileage_missions | FOREIGN KEY (mission_id) REFERENCES mileage_missions(id) |
| p | mileage_submissions_pkey | - | PRIMARY KEY (id) |
| f | mileage_submissions_reviewed_by_fkey | admin_users | FOREIGN KEY (reviewed_by) REFERENCES admin_users(id) |
| indexname | indexdef |
| --- | --- |
| mileage_submissions_pkey | CREATE UNIQUE INDEX mileage_submissions_pkey ON public.mileage_submissions USING btree (id) |

### new_listing_alert_logs
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('new_listing_alert_logs_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| notification_id | integer | int4 | YES |  | NO |
| email_state | text | text | NO | <literal-redacted>::text | NO |
| email_attempted_at | timestamp without time zone | timestamp | YES |  | NO |
| email_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| email_error | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | new_listing_alert_logs_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| f | new_listing_alert_logs_notification_id_fkey | notifications | FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL |
| p | new_listing_alert_logs_pkey | - | PRIMARY KEY (id) |
| f | new_listing_alert_logs_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | new_listing_alert_logs_user_id_listing_request_id_key | - | UNIQUE (user_id, listing_request_id) |
| indexname | indexdef |
| --- | --- |
| idx_new_listing_alert_logs_listing | CREATE INDEX idx_new_listing_alert_logs_listing ON public.new_listing_alert_logs USING btree (listing_request_id) |
| new_listing_alert_logs_pkey | CREATE UNIQUE INDEX new_listing_alert_logs_pkey ON public.new_listing_alert_logs USING btree (id) |
| new_listing_alert_logs_user_id_listing_request_id_key | CREATE UNIQUE INDEX new_listing_alert_logs_user_id_listing_request_id_key ON public.new_listing_alert_logs USING btree (user_id, listing_request_id) |

### notices
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('notices_id_seq'::regclass) | NO |
| title | text | text | NO |  | NO |
| body | text | text | NO |  | NO |
| is_pinned | boolean | bool | YES | false | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| attachment_key | text | text | YES |  | NO |
| category | text | text | YES | <literal-redacted>::text | NO |
| external_url | text | text | YES |  | NO |
| summary | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | notices_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_notices_order | CREATE INDEX idx_notices_order ON public.notices USING btree (is_pinned DESC, created_at DESC) |
| notices_pkey | CREATE UNIQUE INDEX notices_pkey ON public.notices USING btree (id) |

### notifications
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('notifications_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| title | text | text | NO |  | NO |
| body | text | text | YES |  | NO |
| building_name | text | text | YES |  | NO |
| address | text | text | YES |  | NO |
| transaction_id | integer | int4 | YES |  | NO |
| is_read | boolean | bool | YES | false | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| listing_request_id | integer | int4 | YES |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | notifications_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| f | notifications_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| p | notifications_pkey | - | PRIMARY KEY (id) |
| f | notifications_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_notifications_user | CREATE INDEX idx_notifications_user ON public.notifications USING btree (user_id, is_read, created_at DESC) |
| notifications_pkey | CREATE UNIQUE INDEX notifications_pkey ON public.notifications USING btree (id) |
| uq_notifications_user_listing | CREATE UNIQUE INDEX uq_notifications_user_listing ON public.notifications USING btree (user_id, listing_request_id) |
| uq_notifications_user_tx | CREATE UNIQUE INDEX uq_notifications_user_tx ON public.notifications USING btree (user_id, transaction_id) |

### operator_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_buildings_id_seq'::regclass) | NO |
| operator_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| note | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| has_priority_badge | boolean | bool | YES | false | NO |
| premium_granted_at | timestamp without time zone | timestamp | YES |  | NO |
| premium_expires_at | timestamp without time zone | timestamp | YES |  | NO |
| is_paid | boolean | bool | YES | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_buildings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| u | operator_buildings_operator_building_unique | - | UNIQUE (operator_id, master_building_id) |
| f | operator_buildings_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | operator_buildings_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| operator_buildings_operator_building_unique | CREATE UNIQUE INDEX operator_buildings_operator_building_unique ON public.operator_buildings USING btree (operator_id, master_building_id) |
| operator_buildings_pkey | CREATE UNIQUE INDEX operator_buildings_pkey ON public.operator_buildings USING btree (id) |

### operator_consult_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_consult_requests_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| category | text | text | NO |  | NO |
| message | text | text | YES |  | NO |
| contact_phone | text | text | NO |  | NO |
| routed_operator_id | integer | int4 | YES |  | NO |
| routed_reason | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_consult_requests_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | operator_consult_requests_pkey | - | PRIMARY KEY (id) |
| f | operator_consult_requests_routed_operator_id_fkey | operators | FOREIGN KEY (routed_operator_id) REFERENCES operators(id) |
| f | operator_consult_requests_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| operator_consult_requests_pkey | CREATE UNIQUE INDEX operator_consult_requests_pkey ON public.operator_consult_requests USING btree (id) |

### operator_lodging
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_lodging_id_seq'::regclass) | NO |
| user_id | integer | int4 | YES |  | NO |
| lodging_reg_id | integer | int4 | YES |  | NO |
| master_building_id | integer | int4 | YES |  | NO |
| lodging_op_type | text | text | NO |  | NO |
| biz_name | text | text | NO |  | NO |
| rep_name | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| biz_no | text | text | YES |  | NO |
| permit_no | text | text | NO |  | NO |
| booking_url | text | text | YES |  | NO |
| airbnb_url | text | text | YES |  | NO |
| airbnb_urls | jsonb | jsonb | YES |  | NO |
| gocamping_url | text | text | YES |  | NO |
| intro_text | text | text | YES |  | NO |
| photo_url | text | text | YES |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| approved_at | timestamp with time zone | timestamptz | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| reject_reason | text | text | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | YES | now() | NO |
| updated_at | timestamp with time zone | timestamptz | YES | now() | NO |
| doc_biz_reg_url | text | text | YES |  | NO |
| doc_biz_license_url | text | text | YES |  | NO |
| facility_phone | text | text | YES |  | NO |
| homepage_url | text | text | YES |  | NO |
| amenities | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| badges | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_lodging_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) |
| c | operator_lodging_lodging_op_type_check | - | CHECK ((lodging_op_type = ANY (ARRAY['airbnb'::text, 'camping'::text, 'rural'::text, 'hanok'::text, 'living'::text]))) |
| f | operator_lodging_lodging_reg_id_fkey | lodging_registry | FOREIGN KEY (lodging_reg_id) REFERENCES lodging_registry(id) |
| f | operator_lodging_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| u | operator_lodging_permit_no_key | - | UNIQUE (permit_no) |
| p | operator_lodging_pkey | - | PRIMARY KEY (id) |
| c | operator_lodging_status_check | - | CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text]))) |
| f | operator_lodging_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) |
| indexname | indexdef |
| --- | --- |
| idx_op_lodging_building | CREATE INDEX idx_op_lodging_building ON public.operator_lodging USING btree (master_building_id) WHERE (status = 'approved'::text) |
| idx_op_lodging_permit_unique | CREATE UNIQUE INDEX idx_op_lodging_permit_unique ON public.operator_lodging USING btree (permit_no) |
| idx_op_lodging_registry_unique | CREATE UNIQUE INDEX idx_op_lodging_registry_unique ON public.operator_lodging USING btree (lodging_reg_id) WHERE (lodging_reg_id IS NOT NULL) |
| idx_op_lodging_type | CREATE INDEX idx_op_lodging_type ON public.operator_lodging USING btree (lodging_op_type, status) |
| operator_lodging_permit_no_key | CREATE UNIQUE INDEX operator_lodging_permit_no_key ON public.operator_lodging USING btree (permit_no) |
| operator_lodging_pkey | CREATE UNIQUE INDEX operator_lodging_pkey ON public.operator_lodging USING btree (id) |

### operator_lodging_photos
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_lodging_photos_id_seq'::regclass) | NO |
| operator_lodging_id | integer | int4 | NO |  | NO |
| object_key | text | text | NO |  | NO |
| sort_order | integer | int4 | NO | 0 | NO |
| is_primary | boolean | bool | NO | false | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | operator_lodging_photos_object_key_key | - | UNIQUE (object_key) |
| f | operator_lodging_photos_operator_lodging_id_fkey | operator_lodging | FOREIGN KEY (operator_lodging_id) REFERENCES operator_lodging(id) ON DELETE CASCADE |
| p | operator_lodging_photos_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_op_lodging_photos_one_primary | CREATE UNIQUE INDEX idx_op_lodging_photos_one_primary ON public.operator_lodging_photos USING btree (operator_lodging_id) WHERE is_primary |
| idx_op_lodging_photos_owner_order | CREATE INDEX idx_op_lodging_photos_owner_order ON public.operator_lodging_photos USING btree (operator_lodging_id, sort_order, id) |
| operator_lodging_photos_object_key_key | CREATE UNIQUE INDEX operator_lodging_photos_object_key_key ON public.operator_lodging_photos USING btree (object_key) |
| operator_lodging_photos_pkey | CREATE UNIQUE INDEX operator_lodging_photos_pkey ON public.operator_lodging_photos USING btree (id) |

### operator_region_buildings
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_region_buildings_id_seq'::regclass) | NO |
| operator_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| added_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_region_buildings_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| f | operator_region_buildings_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | operator_region_buildings_pkey | - | PRIMARY KEY (id) |
| u | operator_region_buildings_unique | - | UNIQUE (operator_id, master_building_id) |
| indexname | indexdef |
| --- | --- |
| operator_region_buildings_pkey | CREATE UNIQUE INDEX operator_region_buildings_pkey ON public.operator_region_buildings USING btree (id) |
| operator_region_buildings_unique | CREATE UNIQUE INDEX operator_region_buildings_unique ON public.operator_region_buildings USING btree (operator_id, master_building_id) |

### operator_service_areas
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_service_areas_id_seq'::regclass) | NO |
| operator_id | integer | int4 | NO |  | NO |
| region_name | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_service_areas_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | operator_service_areas_pkey | - | PRIMARY KEY (id) |
| u | operator_service_areas_unique | - | UNIQUE (operator_id, region_name) |
| indexname | indexdef |
| --- | --- |
| operator_service_areas_pkey | CREATE UNIQUE INDEX operator_service_areas_pkey ON public.operator_service_areas USING btree (id) |
| operator_service_areas_unique | CREATE UNIQUE INDEX operator_service_areas_unique ON public.operator_service_areas USING btree (operator_id, region_name) |

### operator_service_regions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operator_service_regions_id_seq'::regclass) | NO |
| operator_id | integer | int4 | NO |  | NO |
| sgg_text | text | text | NO |  | NO |
| granted_at | timestamp without time zone | timestamp | YES | now() | NO |
| expires_at | timestamp without time zone | timestamp | NO |  | NO |
| is_paid | boolean | bool | YES | false | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operator_service_regions_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | operator_service_regions_pkey | - | PRIMARY KEY (id) |
| u | operator_service_regions_unique | - | UNIQUE (operator_id, sgg_text) |
| indexname | indexdef |
| --- | --- |
| operator_service_regions_pkey | CREATE UNIQUE INDEX operator_service_regions_pkey ON public.operator_service_regions USING btree (id) |
| operator_service_regions_unique | CREATE UNIQUE INDEX operator_service_regions_unique ON public.operator_service_regions USING btree (operator_id, sgg_text) |

### operators
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('operators_id_seq'::regclass) | NO |
| company_name | text | text | NO |  | NO |
| owner_name | text | text | NO |  | NO |
| category | text | text | NO |  | NO |
| biz_reg_number | text | text | YES |  | NO |
| phone | text | text | YES |  | NO |
| email | text | text | NO |  | NO |
| website_url | text | text | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| approved_at | timestamp without time zone | timestamp | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| password_hash | text | text | YES |  | NO |
| photo_url | text | text | YES |  | NO |
| intro_text | text | text | YES |  | NO |
| subdomain_slug | text | text | YES |  | NO |
| admin_tag | text | text | YES |  | NO |
| logo_url | text | text | YES |  | NO |
| is_visible | boolean | bool | YES | true | NO |
| priority_score | integer | int4 | YES | 0 | NO |
| admin_memo | text | text | YES |  | NO |
| office_address | text | text | YES |  | NO |
| tax_invoice_email | text | text | YES |  | NO |
| rejection_reason | text | text | YES |  | NO |
| manager_name | text | text | YES |  | NO |
| desired_building | text | text | YES |  | NO |
| weekly_email_enabled | boolean | bool | NO | true | NO |
| weekly_email_opted_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_email_updated_at | timestamp without time zone | timestamp | YES |  | NO |
| weekly_unsubscribe_token | uuid | uuid | NO | gen_random_uuid() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | operators_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) |
| p | operators_pkey | - | PRIMARY KEY (id) |
| u | operators_subdomain_slug_unique | - | UNIQUE (subdomain_slug) |
| indexname | indexdef |
| --- | --- |
| operators_pkey | CREATE UNIQUE INDEX operators_pkey ON public.operators USING btree (id) |
| operators_subdomain_slug_unique | CREATE UNIQUE INDEX operators_subdomain_slug_unique ON public.operators USING btree (subdomain_slug) |
| uq_operators_weekly_unsubscribe_token | CREATE UNIQUE INDEX uq_operators_weekly_unsubscribe_token ON public.operators USING btree (weekly_unsubscribe_token) |

### page_views
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('page_views_id_seq'::regclass) | NO |
| path | text | text | NO |  | NO |
| ip_hash | text | text | YES |  | NO |
| user_agent | text | text | YES |  | NO |
| viewed_at | timestamp without time zone | timestamp | YES | now() | NO |
| listing_request_id | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | page_views_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_page_views_listing_recent | CREATE INDEX idx_page_views_listing_recent ON public.page_views USING btree (listing_request_id, viewed_at DESC) WHERE (listing_request_id IS NOT NULL) |
| idx_page_views_viewed_at | CREATE INDEX idx_page_views_viewed_at ON public.page_views USING btree (viewed_at) |
| page_views_pkey | CREATE UNIQUE INDEX page_views_pkey ON public.page_views USING btree (id) |

### partner_favorites
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('partner_favorites_id_seq'::regclass) | NO |
| agent_id | integer | int4 | YES |  | NO |
| operator_id | integer | int4 | YES |  | NO |
| loan_consultant_id | integer | int4 | YES |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | partner_favorites_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| f | partner_favorites_loan_consultant_id_fkey | loan_consultants | FOREIGN KEY (loan_consultant_id) REFERENCES loan_consultants(id) ON DELETE CASCADE |
| f | partner_favorites_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| c | partner_favorites_one_owner | - | CHECK ((num_nonnulls(agent_id, operator_id, loan_consultant_id) = 1)) |
| f | partner_favorites_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| p | partner_favorites_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_partner_favorites_agent | CREATE INDEX idx_partner_favorites_agent ON public.partner_favorites USING btree (agent_id, created_at DESC) WHERE (agent_id IS NOT NULL) |
| idx_partner_favorites_loan_consultant | CREATE INDEX idx_partner_favorites_loan_consultant ON public.partner_favorites USING btree (loan_consultant_id, created_at DESC) WHERE (loan_consultant_id IS NOT NULL) |
| idx_partner_favorites_operator | CREATE INDEX idx_partner_favorites_operator ON public.partner_favorites USING btree (operator_id, created_at DESC) WHERE (operator_id IS NOT NULL) |
| partner_favorites_pkey | CREATE UNIQUE INDEX partner_favorites_pkey ON public.partner_favorites USING btree (id) |
| uq_partner_favorites_agent_building | CREATE UNIQUE INDEX uq_partner_favorites_agent_building ON public.partner_favorites USING btree (agent_id, master_building_id) WHERE (agent_id IS NOT NULL) |
| uq_partner_favorites_loan_consultant_building | CREATE UNIQUE INDEX uq_partner_favorites_loan_consultant_building ON public.partner_favorites USING btree (loan_consultant_id, master_building_id) WHERE (loan_consultant_id IS NOT NULL) |
| uq_partner_favorites_operator_building | CREATE UNIQUE INDEX uq_partner_favorites_operator_building ON public.partner_favorites USING btree (operator_id, master_building_id) WHERE (operator_id IS NOT NULL) |

### password_reset_tokens
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('password_reset_tokens_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| token | text | text | NO |  | NO |
| expires_at | timestamp without time zone | timestamp | NO |  | NO |
| used_at | timestamp without time zone | timestamp | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| account_type | text | text | NO | <literal-redacted>::text | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | password_reset_tokens_pkey | - | PRIMARY KEY (id) |
| u | password_reset_tokens_token_key | - | UNIQUE (token) |
| indexname | indexdef |
| --- | --- |
| password_reset_tokens_pkey | CREATE UNIQUE INDEX password_reset_tokens_pkey ON public.password_reset_tokens USING btree (id) |
| password_reset_tokens_token_idx | CREATE INDEX password_reset_tokens_token_idx ON public.password_reset_tokens USING btree (token) |
| password_reset_tokens_token_key | CREATE UNIQUE INDEX password_reset_tokens_token_key ON public.password_reset_tokens USING btree (token) |
| password_reset_tokens_user_idx | CREATE INDEX password_reset_tokens_user_idx ON public.password_reset_tokens USING btree (user_id, created_at DESC) |

### permit_change_alert_deliveries
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('permit_change_alert_deliveries_id_seq'::regclass) | NO |
| permit_change_alert_log_id | integer | int4 | NO |  | NO |
| user_id | integer | int4 | NO |  | NO |
| notification_id | integer | int4 | YES |  | NO |
| email_state | text | text | NO | <literal-redacted>::text | NO |
| email_attempted_at | timestamp without time zone | timestamp | YES |  | NO |
| email_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| email_error | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | permit_change_alert_deliverie_permit_change_alert_log_id_us_key | - | UNIQUE (permit_change_alert_log_id, user_id) |
| f | permit_change_alert_deliveries_notification_id_fkey | notifications | FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL |
| f | permit_change_alert_deliveries_permit_change_alert_log_id_fkey | permit_change_alert_logs | FOREIGN KEY (permit_change_alert_log_id) REFERENCES permit_change_alert_logs(id) ON DELETE CASCADE |
| p | permit_change_alert_deliveries_pkey | - | PRIMARY KEY (id) |
| f | permit_change_alert_deliveries_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_permit_change_alert_deliveries_user | CREATE INDEX idx_permit_change_alert_deliveries_user ON public.permit_change_alert_deliveries USING btree (user_id, created_at DESC) |
| permit_change_alert_deliverie_permit_change_alert_log_id_us_key | CREATE UNIQUE INDEX permit_change_alert_deliverie_permit_change_alert_log_id_us_key ON public.permit_change_alert_deliveries USING btree (permit_change_alert_log_id, user_id) |
| permit_change_alert_deliveries_pkey | CREATE UNIQUE INDEX permit_change_alert_deliveries_pkey ON public.permit_change_alert_deliveries USING btree (id) |

### permit_change_alert_logs
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('permit_change_alert_logs_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| change_date | date | date | NO |  | NO |
| change_summary | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| delivery_queued_at | timestamp without time zone | timestamp | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | permit_change_alert_logs_master_building_id_change_date_key | - | UNIQUE (master_building_id, change_date) |
| f | permit_change_alert_logs_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | permit_change_alert_logs_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_permit_change_alert_logs_pending | CREATE INDEX idx_permit_change_alert_logs_pending ON public.permit_change_alert_logs USING btree (change_date, delivery_queued_at) |
| permit_change_alert_logs_master_building_id_change_date_key | CREATE UNIQUE INDEX permit_change_alert_logs_master_building_id_change_date_key ON public.permit_change_alert_logs USING btree (master_building_id, change_date) |
| permit_change_alert_logs_pkey | CREATE UNIQUE INDEX permit_change_alert_logs_pkey ON public.permit_change_alert_logs USING btree (id) |

### point_transactions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('point_transactions_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| amount | integer | int4 | NO |  | NO |
| reason | text | text | NO |  | NO |
| admin_id | integer | int4 | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | point_transactions_admin_id_fkey | admin_users | FOREIGN KEY (admin_id) REFERENCES admin_users(id) |
| p | point_transactions_pkey | - | PRIMARY KEY (id) |
| f | point_transactions_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_point_tx_user | CREATE INDEX idx_point_tx_user ON public.point_transactions USING btree (user_id, created_at DESC) |
| point_transactions_pkey | CREATE UNIQUE INDEX point_transactions_pkey ON public.point_transactions USING btree (id) |

### policy_document_revisions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('policy_document_revisions_id_seq'::regclass) | NO |
| policy_document_id | bigint | int8 | NO |  | NO |
| revision_number | integer | int4 | NO |  | NO |
| action | text | text | NO |  | NO |
| title | text | text | NO |  | NO |
| category | text | text | NO |  | NO |
| status | text | text | NO |  | NO |
| version | text | text | NO |  | NO |
| body_markdown | text | text | NO |  | NO |
| effective_date | date | date | YES |  | NO |
| change_note | text | text | NO | <literal-redacted>::text | NO |
| actor_id | integer | int4 | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | policy_document_revisions_action_check | - | CHECK ((action = ANY (ARRAY['created'::text, 'updated'::text, 'published'::text, 'archived'::text]))) |
| f | policy_document_revisions_actor_id_fkey | admin_users | FOREIGN KEY (actor_id) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | policy_document_revisions_change_note_check | - | CHECK ((char_length(change_note) <= 1000)) |
| p | policy_document_revisions_pkey | - | PRIMARY KEY (id) |
| f | policy_document_revisions_policy_document_id_fkey | policy_documents | FOREIGN KEY (policy_document_id) REFERENCES policy_documents(id) ON DELETE CASCADE |
| u | policy_document_revisions_policy_document_id_revision_numbe_key | - | UNIQUE (policy_document_id, revision_number) |
| c | policy_document_revisions_revision_number_check | - | CHECK ((revision_number >= 1)) |
| indexname | indexdef |
| --- | --- |
| idx_policy_revisions_document | CREATE INDEX idx_policy_revisions_document ON public.policy_document_revisions USING btree (policy_document_id, revision_number DESC) |
| policy_document_revisions_pkey | CREATE UNIQUE INDEX policy_document_revisions_pkey ON public.policy_document_revisions USING btree (id) |
| policy_document_revisions_policy_document_id_revision_numbe_key | CREATE UNIQUE INDEX policy_document_revisions_policy_document_id_revision_numbe_key ON public.policy_document_revisions USING btree (policy_document_id, revision_number) |

### policy_documents
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('policy_documents_id_seq'::regclass) | NO |
| document_code | text | text | NO |  | NO |
| title | text | text | NO |  | NO |
| category | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| version | text | text | NO |  | NO |
| body_markdown | text | text | NO |  | NO |
| effective_date | date | date | YES |  | NO |
| created_by | integer | int4 | YES |  | NO |
| updated_by | integer | int4 | YES |  | NO |
| published_by | integer | int4 | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| published_at | timestamp with time zone | timestamptz | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | policy_documents_body_markdown_check | - | CHECK (((char_length(body_markdown) >= 1) AND (char_length(body_markdown) <= 100000))) |
| c | policy_documents_category_check | - | CHECK ((category = ANY (ARRAY['operations'::text, 'data'::text, 'privacy'::text, 'product'::text, 'other'::text]))) |
| f | policy_documents_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | policy_documents_document_code_check | - | CHECK (((char_length(document_code) >= 1) AND (char_length(document_code) <= 80))) |
| u | policy_documents_document_code_key | - | UNIQUE (document_code) |
| p | policy_documents_pkey | - | PRIMARY KEY (id) |
| f | policy_documents_published_by_fkey | admin_users | FOREIGN KEY (published_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | policy_documents_status_check | - | CHECK ((status = ANY (ARRAY['draft'::text, 'published'::text, 'archived'::text]))) |
| c | policy_documents_title_check | - | CHECK (((char_length(title) >= 1) AND (char_length(title) <= 200))) |
| f | policy_documents_updated_by_fkey | admin_users | FOREIGN KEY (updated_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | policy_documents_version_check | - | CHECK (((char_length(version) >= 1) AND (char_length(version) <= 40))) |
| indexname | indexdef |
| --- | --- |
| idx_policy_documents_browse | CREATE INDEX idx_policy_documents_browse ON public.policy_documents USING btree (category, status, updated_at DESC) |
| policy_documents_document_code_key | CREATE UNIQUE INDEX policy_documents_document_code_key ON public.policy_documents USING btree (document_code) |
| policy_documents_pkey | CREATE UNIQUE INDEX policy_documents_pkey ON public.policy_documents USING btree (id) |

### premium_waitlist
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('premium_waitlist_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| master_building_id | integer | int4 | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| notified_at | timestamp without time zone | timestamp | YES |  | NO |
| confirmation_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | premium_waitlist_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| f | premium_waitlist_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | premium_waitlist_pkey | - | PRIMARY KEY (id) |
| u | premium_waitlist_unique | - | UNIQUE (agent_id, master_building_id) |
| indexname | indexdef |
| --- | --- |
| premium_waitlist_pkey | CREATE UNIQUE INDEX premium_waitlist_pkey ON public.premium_waitlist USING btree (id) |
| premium_waitlist_unique | CREATE UNIQUE INDEX premium_waitlist_unique ON public.premium_waitlist USING btree (agent_id, master_building_id) |

### presale_applications
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('presale_applications_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| project_id | bigint | int8 | YES |  | NO |
| title | text | text | NO |  | NO |
| project_status | text | text | NO |  | NO |
| project_type | text | text | NO |  | NO |
| summary | text | text | YES |  | NO |
| unit_count | integer | int4 | YES |  | NO |
| remaining_units | integer | int4 | YES |  | NO |
| price_min | bigint | int8 | YES |  | NO |
| price_max | bigint | int8 | YES |  | NO |
| sale_start_date | date | date | YES |  | NO |
| sale_end_date | date | date | YES |  | NO |
| move_in_date | date | date | YES |  | NO |
| company_name | text | text | NO |  | NO |
| applicant_role | text | text | YES |  | NO |
| contact_name | text | text | NO |  | NO |
| contact_phone | text | text | NO |  | NO |
| contact_email | text | text | NO |  | NO |
| homepage_url | text | text | YES |  | NO |
| evidence_object_key | text | text | NO |  | NO |
| evidence_filename | text | text | NO |  | NO |
| banner_object_key | text | text | YES |  | NO |
| banner_filename | text | text | YES |  | NO |
| consent_version | text | text | NO |  | NO |
| consented_at | timestamp with time zone | timestamptz | NO |  | NO |
| receipt_notification_status | text | text | NO | <literal-redacted>::text | NO |
| decision_notification_status | text | text | NO | <literal-redacted>::text | NO |
| notification_error | text | text | YES |  | NO |
| reject_reason | text | text | YES |  | NO |
| reviewed_at | timestamp with time zone | timestamptz | YES |  | NO |
| reviewed_by | integer | int4 | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| applyhome_status | text | text | NO | <literal-redacted>::text | NO |
| applyhome_notice_id | text | text | YES |  | NO |
| applyhome_notice_name | text | text | YES |  | NO |
| applyhome_checked_at | timestamp with time zone | timestamptz | YES |  | NO |
| applyhome_error_code | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | presale_applications_check | - | CHECK (((remaining_units IS NULL) OR ((remaining_units >= 0) AND ((unit_count IS NULL) OR (remaining_units <= unit_count))))) |
| c | presale_applications_check1 | - | CHECK (((price_max IS NULL) OR (price_min IS NULL) OR (price_max >= price_min))) |
| c | presale_applications_check2 | - | CHECK (((sale_end_date IS NULL) OR (sale_start_date IS NULL) OR (sale_end_date >= sale_start_date))) |
| c | presale_applications_decision_notification_status_check | - | CHECK ((decision_notification_status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text]))) |
| f | presale_applications_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE RESTRICT |
| p | presale_applications_pkey | - | PRIMARY KEY (id) |
| c | presale_applications_price_max_check | - | CHECK (((price_max IS NULL) OR (price_max >= 0))) |
| c | presale_applications_price_min_check | - | CHECK (((price_min IS NULL) OR (price_min >= 0))) |
| f | presale_applications_project_id_fkey | presale_projects | FOREIGN KEY (project_id) REFERENCES presale_projects(id) ON DELETE SET NULL |
| c | presale_applications_project_status_check | - | CHECK ((project_status = ANY (ARRAY['presale'::text, 'scheduled'::text, 'sold_out'::text]))) |
| c | presale_applications_project_type_check | - | CHECK ((project_type = ANY (ARRAY['living'::text, 'tourist'::text, 'officetel'::text, 'mixed'::text]))) |
| c | presale_applications_receipt_notification_status_check | - | CHECK ((receipt_notification_status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text]))) |
| f | presale_applications_reviewed_by_fkey | admin_users | FOREIGN KEY (reviewed_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | presale_applications_status_check | - | CHECK ((status = ANY (ARRAY['submitted'::text, 'reviewing'::text, 'approved'::text, 'rejected'::text]))) |
| c | presale_applications_unit_count_check | - | CHECK (((unit_count IS NULL) OR (unit_count > 0))) |
| indexname | indexdef |
| --- | --- |
| idx_presale_applications_review | CREATE INDEX idx_presale_applications_review ON public.presale_applications USING btree (status, created_at DESC) |
| presale_applications_pkey | CREATE UNIQUE INDEX presale_applications_pkey ON public.presale_applications USING btree (id) |
| uq_presale_applications_active_building | CREATE UNIQUE INDEX uq_presale_applications_active_building ON public.presale_applications USING btree (master_building_id) WHERE (status = ANY (ARRAY['submitted'::text, 'reviewing'::text])) |

### presale_audit_log
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('presale_audit_log_id_seq'::regclass) | NO |
| project_id | bigint | int8 | YES |  | NO |
| promotion_id | bigint | int8 | YES |  | NO |
| admin_id | integer | int4 | YES |  | NO |
| action | text | text | NO |  | NO |
| detail | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| application_id | bigint | int8 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | presale_audit_log_admin_id_fkey | admin_users | FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE SET NULL |
| f | presale_audit_log_application_id_fkey | presale_applications | FOREIGN KEY (application_id) REFERENCES presale_applications(id) ON DELETE SET NULL |
| p | presale_audit_log_pkey | - | PRIMARY KEY (id) |
| f | presale_audit_log_project_id_fkey | presale_projects | FOREIGN KEY (project_id) REFERENCES presale_projects(id) ON DELETE SET NULL |
| f | presale_audit_log_promotion_id_fkey | presale_promotions | FOREIGN KEY (promotion_id) REFERENCES presale_promotions(id) ON DELETE SET NULL |
| indexname | indexdef |
| --- | --- |
| idx_presale_audit_project | CREATE INDEX idx_presale_audit_project ON public.presale_audit_log USING btree (project_id, created_at DESC) |
| presale_audit_log_pkey | CREATE UNIQUE INDEX presale_audit_log_pkey ON public.presale_audit_log USING btree (id) |

### presale_projects
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('presale_projects_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| publication_start_at | timestamp with time zone | timestamptz | YES |  | NO |
| publication_end_at | timestamp with time zone | timestamptz | YES |  | NO |
| title | text | text | NO |  | NO |
| summary | text | text | YES |  | NO |
| unit_count | integer | int4 | YES |  | NO |
| price_min | bigint | int8 | YES |  | NO |
| price_max | bigint | int8 | YES |  | NO |
| sale_start_date | date | date | YES |  | NO |
| sale_end_date | date | date | YES |  | NO |
| contact_name | text | text | YES |  | NO |
| contact_phone | text | text | YES |  | NO |
| company_name | text | text | YES |  | NO |
| editorial_body | text | text | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| created_by | integer | int4 | YES |  | NO |
| updated_by | integer | int4 | YES |  | NO |
| withdrawn_at | timestamp with time zone | timestamptz | YES |  | NO |
| withdrawn_by | integer | int4 | YES |  | NO |
| project_status | text | text | NO | <literal-redacted>::text | NO |
| project_type | text | text | NO | <literal-redacted>::text | NO |
| remaining_units | integer | int4 | YES |  | NO |
| move_in_date | date | date | YES |  | NO |
| homepage_url | text | text | YES |  | NO |
| applyhome_status | text | text | NO | <literal-redacted>::text | NO |
| applyhome_notice_id | text | text | YES |  | NO |
| applyhome_notice_name | text | text | YES |  | NO |
| applyhome_checked_at | timestamp with time zone | timestamptz | YES |  | NO |
| applyhome_error_code | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | presale_projects_check | - | CHECK (((publication_end_at IS NULL) OR (publication_start_at IS NULL) OR (publication_end_at > publication_start_at))) |
| c | presale_projects_check1 | - | CHECK (((sale_end_date IS NULL) OR (sale_start_date IS NULL) OR (sale_end_date >= sale_start_date))) |
| c | presale_projects_check2 | - | CHECK (((price_max IS NULL) OR (price_min IS NULL) OR (price_max >= price_min))) |
| f | presale_projects_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| f | presale_projects_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE RESTRICT |
| u | presale_projects_master_building_id_key | - | UNIQUE (master_building_id) |
| p | presale_projects_pkey | - | PRIMARY KEY (id) |
| c | presale_projects_price_max_check | - | CHECK (((price_max IS NULL) OR (price_max >= 0))) |
| c | presale_projects_price_min_check | - | CHECK (((price_min IS NULL) OR (price_min >= 0))) |
| c | presale_projects_project_status_check | - | CHECK ((project_status = ANY (ARRAY['presale'::text, 'scheduled'::text, 'sold_out'::text]))) NOT VALID |
| c | presale_projects_project_type_check | - | CHECK ((project_type = ANY (ARRAY['living'::text, 'tourist'::text, 'officetel'::text, 'mixed'::text]))) NOT VALID |
| c | presale_projects_remaining_units_check | - | CHECK (((remaining_units IS NULL) OR ((remaining_units >= 0) AND ((unit_count IS NULL) OR (remaining_units <= unit_count))))) NOT VALID |
| c | presale_projects_status_check | - | CHECK ((status = ANY (ARRAY['draft'::text, 'scheduled'::text, 'published'::text, 'withdrawn'::text]))) |
| c | presale_projects_unit_count_check | - | CHECK (((unit_count IS NULL) OR (unit_count > 0))) |
| f | presale_projects_updated_by_fkey | admin_users | FOREIGN KEY (updated_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| f | presale_projects_withdrawn_by_fkey | admin_users | FOREIGN KEY (withdrawn_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| indexname | indexdef |
| --- | --- |
| idx_presale_projects_public | CREATE INDEX idx_presale_projects_public ON public.presale_projects USING btree (status, publication_start_at, publication_end_at) |
| presale_projects_master_building_id_key | CREATE UNIQUE INDEX presale_projects_master_building_id_key ON public.presale_projects USING btree (master_building_id) |
| presale_projects_pkey | CREATE UNIQUE INDEX presale_projects_pkey ON public.presale_projects USING btree (id) |

### presale_promotions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('presale_promotions_id_seq'::regclass) | NO |
| presale_project_id | bigint | int8 | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| starts_at | timestamp with time zone | timestamptz | NO |  | NO |
| ends_at | timestamp with time zone | timestamptz | NO |  | NO |
| slogan | text | text | NO |  | NO |
| cta_url | text | text | NO |  | NO |
| banner_object_key | text | text | NO |  | NO |
| priority | integer | int4 | NO | 0 | NO |
| approved_at | timestamp with time zone | timestamptz | YES |  | NO |
| approved_by | integer | int4 | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| created_by | integer | int4 | YES |  | NO |
| updated_by | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | presale_promotions_approved_by_fkey | admin_users | FOREIGN KEY (approved_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| c | presale_promotions_check | - | CHECK ((ends_at > starts_at)) |
| f | presale_promotions_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| p | presale_promotions_pkey | - | PRIMARY KEY (id) |
| f | presale_promotions_presale_project_id_fkey | presale_projects | FOREIGN KEY (presale_project_id) REFERENCES presale_projects(id) ON DELETE CASCADE |
| c | presale_promotions_priority_check | - | CHECK (((priority >= 0) AND (priority <= 10000))) |
| c | presale_promotions_status_check | - | CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'withdrawn'::text]))) |
| f | presale_promotions_updated_by_fkey | admin_users | FOREIGN KEY (updated_by) REFERENCES admin_users(id) ON DELETE SET NULL |
| indexname | indexdef |
| --- | --- |
| idx_presale_promotions_active | CREATE INDEX idx_presale_promotions_active ON public.presale_promotions USING btree (presale_project_id, status, starts_at, ends_at, priority DESC) |
| presale_promotions_pkey | CREATE UNIQUE INDEX presale_promotions_pkey ON public.presale_promotions USING btree (id) |

### region_badge_waitlist
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('region_badge_waitlist_id_seq'::regclass) | NO |
| agent_id | integer | int4 | NO |  | NO |
| sgg_text | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| confirmation_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| notified_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | region_badge_waitlist_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| p | region_badge_waitlist_pkey | - | PRIMARY KEY (id) |
| u | region_badge_waitlist_unique | - | UNIQUE (agent_id, sgg_text) |
| indexname | indexdef |
| --- | --- |
| idx_region_badge_waitlist_sgg_pending | CREATE INDEX idx_region_badge_waitlist_sgg_pending ON public.region_badge_waitlist USING btree (sgg_text, notified_at) |
| region_badge_waitlist_pkey | CREATE UNIQUE INDEX region_badge_waitlist_pkey ON public.region_badge_waitlist USING btree (id) |
| region_badge_waitlist_unique | CREATE UNIQUE INDEX region_badge_waitlist_unique ON public.region_badge_waitlist USING btree (agent_id, sgg_text) |

### revenue_records
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('revenue_records_id_seq'::regclass) | NO |
| partner_type | text | text | NO |  | NO |
| partner_id | integer | int4 | NO |  | NO |
| product_type | text | text | NO |  | NO |
| start_date | date | date | NO |  | NO |
| end_date | date | date | YES |  | NO |
| amount | integer | int4 | NO | 0 | NO |
| payment_status | text | text | NO | <literal-redacted>::text | NO |
| memo | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| created_by | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | revenue_records_created_by_fkey | admin_users | FOREIGN KEY (created_by) REFERENCES admin_users(id) |
| c | revenue_records_partner_type_check | - | CHECK ((partner_type = ANY (ARRAY['agent'::text, 'operator'::text, 'loan_consultant'::text]))) |
| c | revenue_records_payment_status_check | - | CHECK ((payment_status = ANY (ARRAY['대기'::text, '완료'::text, '만료'::text]))) |
| p | revenue_records_pkey | - | PRIMARY KEY (id) |
| c | revenue_records_product_type_check | - | CHECK ((product_type = ANY (ARRAY['building_slot'::text, 'priority_exposure'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_revenue_partner | CREATE INDEX idx_revenue_partner ON public.revenue_records USING btree (partner_type, partner_id) |
| idx_revenue_start | CREATE INDEX idx_revenue_start ON public.revenue_records USING btree (start_date) |
| revenue_records_pkey | CREATE UNIQUE INDEX revenue_records_pkey ON public.revenue_records USING btree (id) |

### rone_rental_benchmarks
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('rone_rental_benchmarks_id_seq'::regclass) | NO |
| period | date | date | NO |  | NO |
| region_code | text | text | NO |  | NO |
| region_name | text | text | NO |  | NO |
| region_level | text | text | NO |  | NO |
| property_type | text | text | NO |  | NO |
| property_type_name | text | text | NO |  | NO |
| income_yield | numeric | numeric | NO |  | NO |
| vacancy_rate | numeric | numeric | NO |  | NO |
| source_stat_income_id | text | text | NO |  | NO |
| source_stat_vacancy_id | text | text | NO |  | NO |
| source_item_income_id | text | text | NO |  | NO |
| source_item_vacancy_id | text | text | NO |  | NO |
| source_checked_at | timestamp with time zone | timestamptz | NO |  | NO |
| source_hash | text | text | NO |  | NO |
| collected_at | timestamp with time zone | timestamptz | NO | now() | NO |
| vacancy_period | date | date | NO |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | rone_rental_benchmarks_income_yield_check | - | CHECK (((income_yield > ('-100'::integer)::numeric) AND (income_yield < (100)::numeric))) |
| u | rone_rental_benchmarks_period_region_code_property_type_key | - | UNIQUE (period, region_code, property_type) |
| p | rone_rental_benchmarks_pkey | - | PRIMARY KEY (id) |
| c | rone_rental_benchmarks_region_level_check | - | CHECK ((region_level = ANY (ARRAY['sgg'::text, 'province'::text, 'market'::text, 'national'::text]))) |
| c | rone_rental_benchmarks_vacancy_rate_check | - | CHECK (((vacancy_rate >= (0)::numeric) AND (vacancy_rate <= (100)::numeric))) |
| indexname | indexdef |
| --- | --- |
| idx_rone_rental_benchmark_lookup | CREATE INDEX idx_rone_rental_benchmark_lookup ON public.rone_rental_benchmarks USING btree (property_type, region_code, period DESC) |
| rone_rental_benchmarks_period_region_code_property_type_key | CREATE UNIQUE INDEX rone_rental_benchmarks_period_region_code_property_type_key ON public.rone_rental_benchmarks USING btree (period, region_code, property_type) |
| rone_rental_benchmarks_pkey | CREATE UNIQUE INDEX rone_rental_benchmarks_pkey ON public.rone_rental_benchmarks USING btree (id) |

### room_expiry_alerts_sent
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('room_expiry_alerts_sent_id_seq'::regclass) | NO |
| room_id | integer | int4 | NO |  | NO |
| threshold | text | text | NO |  | NO |
| sent_at | timestamp without time zone | timestamp | YES | now() | NO |
| notification_id | integer | int4 | YES |  | NO |
| in_app_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| email_state | text | text | NO | <literal-redacted>::text | NO |
| email_attempted_at | timestamp without time zone | timestamp | YES |  | NO |
| email_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| email_error | text | text | YES |  | NO |
| email_idempotency_key | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | room_expiry_alerts_sent_notification_id_fkey | notifications | FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL |
| p | room_expiry_alerts_sent_pkey | - | PRIMARY KEY (id) |
| f | room_expiry_alerts_sent_room_id_fkey | business_room_inventory | FOREIGN KEY (room_id) REFERENCES business_room_inventory(id) ON DELETE CASCADE |
| u | room_expiry_alerts_sent_room_id_threshold_key | - | UNIQUE (room_id, threshold) |
| indexname | indexdef |
| --- | --- |
| ix_room_expiry_alerts_sent_room | CREATE INDEX ix_room_expiry_alerts_sent_room ON public.room_expiry_alerts_sent USING btree (room_id) |
| room_expiry_alerts_sent_pkey | CREATE UNIQUE INDEX room_expiry_alerts_sent_pkey ON public.room_expiry_alerts_sent USING btree (id) |
| room_expiry_alerts_sent_room_id_threshold_key | CREATE UNIQUE INDEX room_expiry_alerts_sent_room_id_threshold_key ON public.room_expiry_alerts_sent USING btree (room_id, threshold) |
| uq_room_expiry_alert_email_key | CREATE UNIQUE INDEX uq_room_expiry_alert_email_key ON public.room_expiry_alerts_sent USING btree (email_idempotency_key) WHERE (email_idempotency_key IS NOT NULL) |

### sgg_coords
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('sgg_coords_id_seq'::regclass) | NO |
| sido_name | text | text | NO |  | NO |
| sgg_name | text | text | NO |  | NO |
| lat | double precision | float8 | YES |  | NO |
| lng | double precision | float8 | YES |  | NO |
| building_count | integer | int4 | NO | 0 | NO |
| refreshed_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | sgg_coords_pkey | - | PRIMARY KEY (id) |
| u | sgg_coords_sido_name_sgg_name_key | - | UNIQUE (sido_name, sgg_name) |
| indexname | indexdef |
| --- | --- |
| sgg_coords_pkey | CREATE UNIQUE INDEX sgg_coords_pkey ON public.sgg_coords USING btree (id) |
| sgg_coords_sido_name_sgg_name_key | CREATE UNIQUE INDEX sgg_coords_sido_name_sgg_name_key ON public.sgg_coords USING btree (sido_name, sgg_name) |

### short_links
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| code | character varying | varchar | NO |  | NO |
| target_path | text | text | NO |  | NO |
| expires_at | timestamp without time zone | timestamp | NO |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | short_links_pkey | - | PRIMARY KEY (code) |
| c | short_links_target_path_check | - | CHECK (((target_path ~~ '/admin%'::text) OR (target_path ~~ '/agent/dashboard%'::text))) |
| indexname | indexdef |
| --- | --- |
| idx_short_links_expires_at | CREATE INDEX idx_short_links_expires_at ON public.short_links USING btree (expires_at) |
| short_links_pkey | CREATE UNIQUE INDEX short_links_pkey ON public.short_links USING btree (code) |

### site_popups
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('site_popups_id_seq'::regclass) | NO |
| title | text | text | NO |  | NO |
| start_at | timestamp without time zone | timestamp | YES |  | NO |
| end_at | timestamp without time zone | timestamp | YES |  | NO |
| show_desktop | boolean | bool | YES | true | NO |
| show_mobile | boolean | bool | YES | true | NO |
| scope | text | text | YES | <literal-redacted>::text | NO |
| audience | text | text | YES | <literal-redacted>::text | NO |
| display_type | text | text | YES | <literal-redacted>::text | NO |
| image_ref | text | text | YES |  | NO |
| link_url | text | text | YES |  | NO |
| open_new_tab | boolean | bool | YES | true | NO |
| width_px | integer | int4 | YES | 400 | NO |
| close_mode | text | text | YES | <literal-redacted>::text | NO |
| is_active | boolean | bool | YES | true | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | site_popups_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| site_popups_pkey | CREATE UNIQUE INDEX site_popups_pkey ON public.site_popups USING btree (id) |

### slots
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('slots_id_seq'::regclass) | NO |
| master_building_id | integer | int4 | NO |  | NO |
| agent_id | integer | int4 | NO |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| queue_position | integer | int4 | YES |  | NO |
| monthly_fee | integer | int4 | YES |  | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| expires_at | timestamp without time zone | timestamp | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | slots_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) |
| f | slots_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) |
| p | slots_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_slots_building | CREATE INDEX idx_slots_building ON public.slots USING btree (master_building_id) |
| slots_pkey | CREATE UNIQUE INDEX slots_pkey ON public.slots USING btree (id) |

### streetview_evaluation_metrics
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| metric_date | date | date | NO | CURRENT_DATE | NO |
| evaluations | integer | int4 | NO | 0 | NO |
| base_calls | integer | int4 | NO | 0 | NO |
| extra_calls | integer | int4 | NO | 0 | NO |
| accepted_from_base | integer | int4 | NO | 0 | NO |
| accepted_from_extra | integer | int4 | NO | 0 | NO |
| rejected | integer | int4 | NO | 0 | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | streetview_evaluation_metrics_pkey | - | PRIMARY KEY (metric_date) |
| indexname | indexdef |
| --- | --- |
| streetview_evaluation_metrics_pkey | CREATE UNIQUE INDEX streetview_evaluation_metrics_pkey ON public.streetview_evaluation_metrics USING btree (metric_date) |

### subway_stations
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('subway_stations_id_seq'::regclass) | NO |
| station_name | text | text | NO |  | NO |
| line_name | text | text | YES |  | NO |
| lat | double precision | float8 | NO |  | NO |
| lng | double precision | float8 | NO |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | subway_stations_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| subway_stations_dedupe_uidx | CREATE UNIQUE INDEX subway_stations_dedupe_uidx ON public.subway_stations USING btree (station_name, COALESCE(line_name, ''::text), lat, lng) |
| subway_stations_lat_lng_idx | CREATE INDEX subway_stations_lat_lng_idx ON public.subway_stations USING btree (lat, lng) |
| subway_stations_pkey | CREATE UNIQUE INDEX subway_stations_pkey ON public.subway_stations USING btree (id) |

### survey_request_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('survey_request_history_id_seq'::regclass) | NO |
| request_id | bigint | int8 | NO |  | NO |
| from_status | text | text | YES |  | NO |
| to_status | text | text | NO |  | NO |
| note | text | text | NO | <literal-redacted>::text | NO |
| changed_by | text | text | NO |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | survey_request_history_pkey | - | PRIMARY KEY (id) |
| f | survey_request_history_request_id_fkey | survey_requests | FOREIGN KEY (request_id) REFERENCES survey_requests(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_survey_history_request | CREATE INDEX idx_survey_history_request ON public.survey_request_history USING btree (request_id, id) |
| survey_request_history_pkey | CREATE UNIQUE INDEX survey_request_history_pkey ON public.survey_request_history USING btree (id) |

### survey_requests
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('survey_requests_id_seq'::regclass) | NO |
| request_no | text | text | NO |  | NO |
| auction_item_id | integer | int4 | NO |  | NO |
| building_id | integer | int4 | YES |  | NO |
| survey_type | text | text | NO |  | NO |
| base_fee | bigint | int8 | NO |  | NO |
| visit_fee | bigint | int8 | NO |  | NO |
| total_fee | bigint | int8 | NO |  | NO |
| applicant_name | text | text | NO |  | NO |
| phone | text | text | NO |  | NO |
| email | text | text | YES |  | NO |
| memo | text | text | NO | <literal-redacted>::text | NO |
| depositor_name | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| status_updated_at | timestamp with time zone | timestamptz | NO | now() | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| agreed_terms_at | timestamp with time zone | timestamptz | NO |  | NO |
| agreed_refund_at | timestamp with time zone | timestamptz | NO |  | NO |
| agreed_privacy_at | timestamp with time zone | timestamptz | NO |  | NO |
| payment_deadline | timestamp with time zone | timestamptz | NO |  | NO |
| settings_snapshot | jsonb | jsonb | NO |  | NO |
| terms_snapshot | text | text | NO |  | NO |
| auction_title | text | text | NO |  | NO |
| auction_address | text | text | NO |  | NO |
| admin_memo | text | text | NO | <literal-redacted>::text | NO |
| request_token_hash | text | text | YES |  | NO |
| submission_hash | text | text | NO |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | survey_requests_auction_item_id_fkey | auction_items | FOREIGN KEY (auction_item_id) REFERENCES auction_items(id) |
| f | survey_requests_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| c | survey_requests_check | - | CHECK (((base_fee >= 0) AND (visit_fee >= 0) AND (total_fee = (base_fee + visit_fee)))) |
| p | survey_requests_pkey | - | PRIMARY KEY (id) |
| u | survey_requests_request_no_key | - | UNIQUE (request_no) |
| u | survey_requests_request_token_hash_key | - | UNIQUE (request_token_hash) |
| c | survey_requests_status_check | - | CHECK ((status = ANY (ARRAY['received'::text, 'paid'::text, 'investigating'::text, 'reported'::text, 'canceled'::text, 'refunded'::text]))) |
| c | survey_requests_survey_type_check | - | CHECK ((survey_type = ANY (ARRAY['basic'::text, 'visit'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_survey_requests_created | CREATE INDEX idx_survey_requests_created ON public.survey_requests USING btree (created_at DESC, id DESC) |
| idx_survey_requests_status_deadline | CREATE INDEX idx_survey_requests_status_deadline ON public.survey_requests USING btree (status, payment_deadline) |
| survey_requests_pkey | CREATE UNIQUE INDEX survey_requests_pkey ON public.survey_requests USING btree (id) |
| survey_requests_request_no_key | CREATE UNIQUE INDEX survey_requests_request_no_key ON public.survey_requests USING btree (request_no) |
| survey_requests_request_token_hash_key | CREATE UNIQUE INDEX survey_requests_request_token_hash_key ON public.survey_requests USING btree (request_token_hash) |

### survey_settings_history
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('survey_settings_history_id_seq'::regclass) | NO |
| changed_by | text | text | NO |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| before | jsonb | jsonb | NO |  | NO |
| after | jsonb | jsonb | NO |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | survey_settings_history_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| survey_settings_history_pkey | CREATE UNIQUE INDEX survey_settings_history_pkey ON public.survey_settings_history USING btree (id) |

### sync_failures
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('sync_failures_id_seq'::regclass) | NO |
| sgg_cd | text | text | NO |  | NO |
| deal_ymd | text | text | NO |  | NO |
| reason | text | text | YES |  | NO |
| attempts | integer | int4 | YES | 0 | NO |
| last_attempt_at | timestamp without time zone | timestamp | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | sync_failures_pkey | - | PRIMARY KEY (id) |
| u | sync_failures_sgg_cd_deal_ymd_key | - | UNIQUE (sgg_cd, deal_ymd) |
| indexname | indexdef |
| --- | --- |
| sync_failures_pkey | CREATE UNIQUE INDEX sync_failures_pkey ON public.sync_failures USING btree (id) |
| sync_failures_sgg_cd_deal_ymd_key | CREATE UNIQUE INDEX sync_failures_sgg_cd_deal_ymd_key ON public.sync_failures USING btree (sgg_cd, deal_ymd) |

### sync_log
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('sync_log_id_seq'::regclass) | NO |
| started_at | timestamp without time zone | timestamp | YES |  | NO |
| finished_at | timestamp without time zone | timestamp | YES |  | NO |
| regions_processed | integer | int4 | YES |  | NO |
| rows_inserted | integer | int4 | YES |  | NO |
| rows_matched_master | integer | int4 | YES |  | NO |
| rows_matched_buildinghub | integer | int4 | YES |  | NO |
| rows_unmatched | integer | int4 | YES |  | NO |
| status | text | text | YES |  | NO |
| note | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | sync_log_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| sync_log_pkey | CREATE UNIQUE INDEX sync_log_pkey ON public.sync_log USING btree (id) |

### title_info_backfill_failures
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| building_id | integer | int4 | NO |  | NO |
| attempts | integer | int4 | NO | 1 | NO |
| last_error | text | text | NO | <literal-redacted>::text | NO |
| last_failed_at | timestamp with time zone | timestamptz | NO | now() | NO |
| retry_after | timestamp with time zone | timestamptz | NO |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | title_info_backfill_failures_attempts_check | - | CHECK ((attempts > 0)) |
| f | title_info_backfill_failures_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | title_info_backfill_failures_pkey | - | PRIMARY KEY (building_id) |
| indexname | indexdef |
| --- | --- |
| idx_title_info_backfill_failures_retry | CREATE INDEX idx_title_info_backfill_failures_retry ON public.title_info_backfill_failures USING btree (retry_after) |
| title_info_backfill_failures_pkey | CREATE UNIQUE INDEX title_info_backfill_failures_pkey ON public.title_info_backfill_failures USING btree (building_id) |

### tourism_building_dong_matches
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| building_id | integer | int4 | NO |  | NO |
| sido_name | text | text | NO |  | NO |
| sgg_name | text | text | NO |  | NO |
| legal_dong_name | text | text | NO |  | NO |
| admin_dong_name | text | text | NO |  | NO |
| building_lat | double precision | float8 | NO |  | NO |
| building_lng | double precision | float8 | NO |  | NO |
| verification_source | text | text | NO | <literal-redacted>::text | NO |
| verified_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | tourism_building_dong_matches_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| p | tourism_building_dong_matches_pkey | - | PRIMARY KEY (building_id) |
| indexname | indexdef |
| --- | --- |
| idx_tourism_building_dong_matches_region | CREATE INDEX idx_tourism_building_dong_matches_region ON public.tourism_building_dong_matches USING btree (sido_name, sgg_name, admin_dong_name) |
| tourism_building_dong_matches_pkey | CREATE UNIQUE INDEX tourism_building_dong_matches_pkey ON public.tourism_building_dong_matches USING btree (building_id) |

### tourism_datalab_stages
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| token | text | text | NO | md5((((random())::text \|\| (clock_timestamp())::text) \|\| (txid_current())::text)) | NO |
| admin_user_id | integer | int4 | NO |  | NO |
| manifest | jsonb | jsonb | NO |  | NO |
| manifest_hash | text | text | NO |  | NO |
| expires_at | timestamp with time zone | timestamptz | NO |  | NO |
| state | text | text | NO |  | NO |
| attempt_count | integer | int4 | NO | 0 | NO |
| error_message | text | text | YES |  | NO |
| created_at | timestamp with time zone | timestamptz | NO | now() | NO |
| applied_at | timestamp with time zone | timestamptz | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | tourism_datalab_stages_admin_user_id_fkey | admin_users | FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE |
| p | tourism_datalab_stages_pkey | - | PRIMARY KEY (token) |
| c | tourism_datalab_stages_state_check | - | CHECK ((state = ANY (ARRAY['previewed'::text, 'applying'::text, 'applied'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_tourism_datalab_stages_expiry | CREATE INDEX idx_tourism_datalab_stages_expiry ON public.tourism_datalab_stages USING btree (expires_at) WHERE (state = ANY (ARRAY['previewed'::text, 'failed'::text])) |
| tourism_datalab_stages_pkey | CREATE UNIQUE INDEX tourism_datalab_stages_pkey ON public.tourism_datalab_stages USING btree (token) |

### tourism_dong_coords
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('tourism_dong_coords_id_seq'::regclass) | NO |
| sido_name | text | text | NO |  | NO |
| sgg_name | text | text | NO |  | NO |
| dong_name | text | text | NO |  | NO |
| lat | double precision | float8 | YES |  | NO |
| lng | double precision | float8 | YES |  | NO |
| building_count | integer | int4 | NO | 0 | NO |
| refreshed_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | tourism_dong_coords_pkey | - | PRIMARY KEY (id) |
| u | tourism_dong_coords_sido_name_sgg_name_dong_name_key | - | UNIQUE (sido_name, sgg_name, dong_name) |
| indexname | indexdef |
| --- | --- |
| tourism_dong_coords_pkey | CREATE UNIQUE INDEX tourism_dong_coords_pkey ON public.tourism_dong_coords USING btree (id) |
| tourism_dong_coords_sido_name_sgg_name_dong_name_key | CREATE UNIQUE INDEX tourism_dong_coords_sido_name_sgg_name_dong_name_key ON public.tourism_dong_coords USING btree (sido_name, sgg_name, dong_name) |

### tourism_stats
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('tourism_stats_id_seq'::regclass) | NO |
| stat_type | text | text | NO |  | NO |
| sido_name | text | text | YES |  | NO |
| sgg_name | text | text | YES |  | NO |
| ref_yearmonth | text | text | YES |  | NO |
| metric_name | text | text | NO |  | NO |
| metric_value | numeric | numeric | YES |  | NO |
| unit | text | text | NO | <literal-redacted>::text | NO |
| source | text | text | NO | <literal-redacted>::text | NO |
| source_file | text | text | NO |  | NO |
| source_period | text | text | YES |  | NO |
| dimensions | jsonb | jsonb | NO | <literal-redacted>::jsonb | NO |
| row_hash | text | text | NO |  | NO |
| collected_at | timestamp with time zone | timestamptz | NO | now() | NO |
| master_building_id | integer | int4 | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | tourism_stats_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| p | tourism_stats_pkey | - | PRIMARY KEY (id) |
| u | tourism_stats_row_hash_key | - | UNIQUE (row_hash) |
| indexname | indexdef |
| --- | --- |
| idx_tourism_stats_lodging_rank_building | CREATE INDEX idx_tourism_stats_lodging_rank_building ON public.tourism_stats USING btree (master_building_id) WHERE ((stat_type = 'lodging_search_rank'::text) AND (master_building_id IS NOT NULL)) |
| idx_tourism_stats_lodging_rank_building_source | CREATE INDEX idx_tourism_stats_lodging_rank_building_source ON public.tourism_stats USING btree (master_building_id, source_file, metric_value) WHERE ((stat_type = 'lodging_search_rank'::text) AND (master_building_id IS NOT NULL)) |
| idx_tourism_stats_lodging_rank_latest | CREATE INDEX idx_tourism_stats_lodging_rank_latest ON public.tourism_stats USING btree (source_period DESC NULLS LAST, collected_at DESC, source_file DESC) WHERE (stat_type = 'lodging_search_rank'::text) |
| idx_tourism_stats_lodging_rank_source | CREATE INDEX idx_tourism_stats_lodging_rank_source ON public.tourism_stats USING btree (source_file, metric_value, id) WHERE (stat_type = 'lodging_search_rank'::text) |
| idx_tourism_stats_lookup | CREATE INDEX idx_tourism_stats_lookup ON public.tourism_stats USING btree (stat_type, sido_name, sgg_name, ref_yearmonth) |
| tourism_stats_pkey | CREATE UNIQUE INDEX tourism_stats_pkey ON public.tourism_stats USING btree (id) |
| tourism_stats_row_hash_key | CREATE UNIQUE INDEX tourism_stats_row_hash_key ON public.tourism_stats USING btree (row_hash) |

### transactions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('transactions_id_seq'::regclass) | NO |
| building_name | text | text | YES |  | NO |
| address | text | text | NO |  | NO |
| area | real | float4 | YES |  | NO |
| price | integer | int4 | YES |  | NO |
| deal_date | text | text | YES |  | NO |
| deal_type | text | text | YES |  | NO |
| sgg_cd | text | text | YES |  | NO |
| umd_nm | text | text | YES |  | NO |
| jibun | text | text | YES |  | NO |
| match_source | text | text | YES |  | NO |
| raw_key | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| si_do | text | text | YES |  | NO |
| sgg_nm | text | text | YES |  | NO |
| floor | text | text | YES |  | NO |
| lodging_type | text | text | YES |  | NO |
| lodging_type_detail | text | text | YES |  | NO |
| transaction_scope | text | text | NO | <literal-redacted>::text | NO |
| source_api | text | text | NO | <literal-redacted>::text | NO |
| source_building_type | text | text | YES |  | NO |
| total_floor_area | real | float4 | YES |  | NO |
| land_area | real | float4 | YES |  | NO |
| match_confidence | text | text | NO | <literal-redacted>::text | NO |
| master_building_id | integer | int4 | YES |  | NO |
| source_building_name | text | text | YES |  | NO |
| updated_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | transactions_master_building_id_fkey | master_buildings | FOREIGN KEY (master_building_id) REFERENCES master_buildings(id) ON DELETE SET NULL |
| c | transactions_match_confidence_check | - | CHECK ((match_confidence = ANY (ARRAY['exact'::text, 'unmatched'::text]))) |
| p | transactions_pkey | - | PRIMARY KEY (id) |
| u | transactions_raw_key_key | - | UNIQUE (raw_key) |
| c | transactions_scope_check | - | CHECK ((transaction_scope = ANY (ARRAY['unit'::text, 'whole_building'::text, 'land_or_site'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_transactions_building | CREATE INDEX idx_transactions_building ON public.transactions USING btree (building_name, address) |
| idx_transactions_deal_date | CREATE INDEX idx_transactions_deal_date ON public.transactions USING btree (deal_date DESC) |
| idx_tx_address | CREATE INDEX idx_tx_address ON public.transactions USING btree (address) |
| idx_tx_building_name | CREATE INDEX idx_tx_building_name ON public.transactions USING btree (building_name) |
| idx_tx_deal_date | CREATE INDEX idx_tx_deal_date ON public.transactions USING btree (deal_date DESC) |
| idx_tx_master_building | CREATE INDEX idx_tx_master_building ON public.transactions USING btree (master_building_id, transaction_scope, deal_date DESC) WHERE (master_building_id IS NOT NULL) |
| idx_tx_sgg_umd_jibun | CREATE INDEX idx_tx_sgg_umd_jibun ON public.transactions USING btree (sgg_cd, umd_nm, jibun, deal_date DESC) |
| transactions_pkey | CREATE UNIQUE INDEX transactions_pkey ON public.transactions USING btree (id) |
| transactions_raw_key_key | CREATE UNIQUE INDEX transactions_raw_key_key ON public.transactions USING btree (raw_key) |

### urgent_listing_alert_logs
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('urgent_listing_alert_logs_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| listing_request_id | integer | int4 | NO |  | NO |
| notification_id | integer | int4 | YES |  | NO |
| email_state | text | text | NO | <literal-redacted>::text | NO |
| email_attempted_at | timestamp without time zone | timestamp | YES |  | NO |
| email_sent_at | timestamp without time zone | timestamp | YES |  | NO |
| email_error | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| tier | text | text | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | urgent_listing_alert_logs_listing_request_id_fkey | listing_requests | FOREIGN KEY (listing_request_id) REFERENCES listing_requests(id) ON DELETE CASCADE |
| f | urgent_listing_alert_logs_notification_id_fkey | notifications | FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL |
| p | urgent_listing_alert_logs_pkey | - | PRIMARY KEY (id) |
| f | urgent_listing_alert_logs_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | urgent_listing_alert_logs_user_id_listing_request_id_key | - | UNIQUE (user_id, listing_request_id) |
| indexname | indexdef |
| --- | --- |
| idx_urgent_listing_alert_logs_listing | CREATE INDEX idx_urgent_listing_alert_logs_listing ON public.urgent_listing_alert_logs USING btree (listing_request_id) |
| urgent_listing_alert_logs_pkey | CREATE UNIQUE INDEX urgent_listing_alert_logs_pkey ON public.urgent_listing_alert_logs USING btree (id) |
| urgent_listing_alert_logs_user_id_listing_request_id_key | CREATE UNIQUE INDEX urgent_listing_alert_logs_user_id_listing_request_id_key ON public.urgent_listing_alert_logs USING btree (user_id, listing_request_id) |

### user_alert_subscriptions
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('user_alert_subscriptions_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| building_name | text | text | YES |  | NO |
| address | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | user_alert_subscriptions_pkey | - | PRIMARY KEY (id) |
| f | user_alert_subscriptions_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_user_alert_subs_match | CREATE INDEX idx_user_alert_subs_match ON public.user_alert_subscriptions USING btree (address) |
| idx_user_alert_subs_user | CREATE INDEX idx_user_alert_subs_user ON public.user_alert_subscriptions USING btree (user_id) |
| uq_user_alert_subs | CREATE UNIQUE INDEX uq_user_alert_subs ON public.user_alert_subscriptions USING btree (user_id, COALESCE(building_name, ''::text), address) |
| user_alert_subscriptions_pkey | CREATE UNIQUE INDEX user_alert_subscriptions_pkey ON public.user_alert_subscriptions USING btree (id) |

### user_favorites
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('user_favorites_id_seq'::regclass) | NO |
| user_id | integer | int4 | NO |  | NO |
| building_name | text | text | YES |  | NO |
| address | text | text | NO |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| master_building_id | integer | int4 | YES |  | NO |
| urgent_alert_enabled | boolean | bool | NO | false | NO |
| new_listing_alert_enabled | boolean | bool | NO | false | NO |
| permit_change_alert_enabled | boolean | bool | NO | false | NO |
| favorite_increase_alert_enabled | boolean | bool | NO | false | NO |
| nearby_change_alert_enabled | boolean | bool | NO | false | NO |
| deal_email_alert_enabled | boolean | bool | NO | true | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| p | user_favorites_pkey | - | PRIMARY KEY (id) |
| f | user_favorites_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_user_favorites_deal_email_match | CREATE INDEX idx_user_favorites_deal_email_match ON public.user_favorites USING btree (address, building_name) WHERE (deal_email_alert_enabled = true) |
| idx_user_favorites_new_listing_alert | CREATE INDEX idx_user_favorites_new_listing_alert ON public.user_favorites USING btree (master_building_id) WHERE ((new_listing_alert_enabled = true) AND (master_building_id IS NOT NULL)) |
| idx_user_favorites_permit_change_alert | CREATE INDEX idx_user_favorites_permit_change_alert ON public.user_favorites USING btree (master_building_id) WHERE ((permit_change_alert_enabled = true) AND (master_building_id IS NOT NULL)) |
| idx_user_favorites_urgent_alert | CREATE INDEX idx_user_favorites_urgent_alert ON public.user_favorites USING btree (master_building_id) WHERE ((urgent_alert_enabled = true) AND (master_building_id IS NOT NULL)) |
| idx_user_favorites_user | CREATE INDEX idx_user_favorites_user ON public.user_favorites USING btree (user_id) |
| uq_user_favorites | CREATE UNIQUE INDEX uq_user_favorites ON public.user_favorites USING btree (user_id, COALESCE(building_name, ''::text), address) |
| user_favorites_pkey | CREATE UNIQUE INDEX user_favorites_pkey ON public.user_favorites USING btree (id) |

### user_recent_analysis
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| user_id | integer | int4 | NO |  | NO |
| building_id | integer | int4 | NO |  | NO |
| last_mode | text | text | NO |  | NO |
| analyzed_at | timestamp with time zone | timestamptz | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | user_recent_analysis_building_id_fkey | master_buildings | FOREIGN KEY (building_id) REFERENCES master_buildings(id) ON DELETE CASCADE |
| c | user_recent_analysis_last_mode_check | - | CHECK ((last_mode = ANY (ARRAY['property'::text, 'rental'::text, 'operation'::text]))) |
| p | user_recent_analysis_pkey | - | PRIMARY KEY (user_id, building_id) |
| f | user_recent_analysis_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| indexname | indexdef |
| --- | --- |
| idx_user_recent_analysis_recent | CREATE INDEX idx_user_recent_analysis_recent ON public.user_recent_analysis USING btree (user_id, analyzed_at DESC, building_id DESC) |
| user_recent_analysis_pkey | CREATE UNIQUE INDEX user_recent_analysis_pkey ON public.user_recent_analysis USING btree (user_id, building_id) |

### users
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('users_id_seq'::regclass) | NO |
| email | text | text | YES |  | NO |
| password_hash | text | text | YES |  | NO |
| name | text | text | YES |  | NO |
| provider | text | text | YES | <literal-redacted>::text | NO |
| kakao_id | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| last_login_at | timestamp without time zone | timestamp | YES |  | NO |
| status | text | text | YES | <literal-redacted>::text | NO |
| terms_agreed_at | timestamp without time zone | timestamp | YES |  | NO |
| privacy_agreed_at | timestamp without time zone | timestamp | YES |  | NO |
| marketing_agreed_at | timestamp without time zone | timestamp | YES |  | NO |
| points | integer | int4 | YES | 0 | NO |
| admin_tag | text | text | YES |  | NO |
| email_alert_enabled | boolean | bool | YES | true | NO |
| admin_memo | text | text | YES |  | NO |
| business_reg_number | text | text | YES |  | NO |
| tax_invoice_email | text | text | YES |  | NO |
| rejection_reason | text | text | YES |  | NO |
| weekly_email_enabled | boolean | bool | YES | true | NO |
| unsubscribe_token | uuid | uuid | YES |  | NO |
| phone | text | text | YES |  | NO |
| phone_verified | boolean | bool | YES | false | NO |
| phone_code | text | text | YES |  | NO |
| phone_code_expires_at | timestamp without time zone | timestamp | YES |  | NO |
| phone_code_target | text | text | YES |  | NO |
| user_type | text | text | NO | <literal-redacted>::text | NO |
| updated_weekly_email_at | timestamp without time zone | timestamp | YES |  | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| u | users_email_unique | - | UNIQUE (email) |
| u | users_kakao_id_unique | - | UNIQUE (kakao_id) |
| p | users_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| users_email_unique | CREATE UNIQUE INDEX users_email_unique ON public.users USING btree (email) |
| users_kakao_id_unique | CREATE UNIQUE INDEX users_kakao_id_unique ON public.users USING btree (kakao_id) |
| users_pkey | CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id) |

### weekly_email_deliveries
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('weekly_email_deliveries_id_seq'::regclass) | NO |
| user_id | integer | int4 | YES |  | NO |
| agent_id | integer | int4 | YES |  | NO |
| operator_id | integer | int4 | YES |  | NO |
| loan_consultant_id | integer | int4 | YES |  | NO |
| recipient_type | text | text | NO | <literal-redacted>::text | NO |
| week_start | date | date | NO |  | NO |
| cohort | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| attempts | integer | int4 | NO | 0 | NO |
| claimed_at | timestamp without time zone | timestamp | YES |  | NO |
| sent_at | timestamp without time zone | timestamp | YES |  | NO |
| failed_at | timestamp without time zone | timestamp | YES |  | NO |
| error_message | text | text | YES |  | NO |
| subject | text | text | YES |  | NO |
| tracking_token | uuid | uuid | NO | gen_random_uuid() | NO |
| claim_token | uuid | uuid | NO | gen_random_uuid() | NO |
| open_count | integer | int4 | NO | 0 | NO |
| first_opened_at | timestamp without time zone | timestamp | YES |  | NO |
| last_opened_at | timestamp without time zone | timestamp | YES |  | NO |
| click_count | integer | int4 | NO | 0 | NO |
| first_clicked_at | timestamp without time zone | timestamp | YES |  | NO |
| last_clicked_at | timestamp without time zone | timestamp | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| f | weekly_email_deliveries_agent_id_fkey | agents | FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE |
| c | weekly_email_deliveries_attempts_check | - | CHECK (((attempts >= 0) AND (attempts <= 3))) |
| c | weekly_email_deliveries_click_count_check | - | CHECK ((click_count >= 0)) |
| c | weekly_email_deliveries_cohort_check | - | CHECK ((cohort = ANY (ARRAY['tue'::text, 'thu'::text]))) |
| f | weekly_email_deliveries_loan_consultant_id_fkey | loan_consultants | FOREIGN KEY (loan_consultant_id) REFERENCES loan_consultants(id) ON DELETE CASCADE |
| c | weekly_email_deliveries_open_count_check | - | CHECK ((open_count >= 0)) |
| f | weekly_email_deliveries_operator_id_fkey | operators | FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE |
| c | weekly_email_deliveries_owner_check | - | CHECK ((((recipient_type = 'user'::text) AND (user_id IS NOT NULL) AND (num_nonnulls(user_id, agent_id, operator_id, loan_consultant_id) = 1)) OR ((recipient_type = 'agent'::text) AND (agent_id IS NOT NULL) AND (num_nonnulls(user_id, agent_id, operator_id, loan_consultant_id) = 1)) OR ((recipient_type = 'operator'::text) AND (operator_id IS NOT NULL) AND (num_nonnulls(user_id, agent_id, operator_id, loan_consultant_id) = 1)) OR ((recipient_type = 'loan_consultant'::text) AND (loan_consultant_id IS NOT NULL) AND (num_nonnulls(user_id, agent_id, operator_id, loan_consultant_id) = 1)))) |
| p | weekly_email_deliveries_pkey | - | PRIMARY KEY (id) |
| c | weekly_email_deliveries_status_check | - | CHECK ((status = ANY (ARRAY['sending'::text, 'sent'::text, 'failed'::text]))) |
| u | weekly_email_deliveries_tracking_token_key | - | UNIQUE (tracking_token) |
| f | weekly_email_deliveries_user_id_fkey | users | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| u | weekly_email_deliveries_user_id_week_start_key | - | UNIQUE (user_id, week_start) |
| indexname | indexdef |
| --- | --- |
| idx_weekly_email_deliveries_agent | CREATE INDEX idx_weekly_email_deliveries_agent ON public.weekly_email_deliveries USING btree (agent_id, week_start) WHERE (agent_id IS NOT NULL) |
| idx_weekly_email_deliveries_loan_consultant | CREATE INDEX idx_weekly_email_deliveries_loan_consultant ON public.weekly_email_deliveries USING btree (loan_consultant_id, week_start) WHERE (loan_consultant_id IS NOT NULL) |
| idx_weekly_email_deliveries_operator | CREATE INDEX idx_weekly_email_deliveries_operator ON public.weekly_email_deliveries USING btree (operator_id, week_start) WHERE (operator_id IS NOT NULL) |
| idx_weekly_email_deliveries_tracking | CREATE INDEX idx_weekly_email_deliveries_tracking ON public.weekly_email_deliveries USING btree (tracking_token) |
| idx_weekly_email_deliveries_week_cohort | CREATE INDEX idx_weekly_email_deliveries_week_cohort ON public.weekly_email_deliveries USING btree (week_start, cohort, status) |
| uq_weekly_email_deliveries_agent_week | CREATE UNIQUE INDEX uq_weekly_email_deliveries_agent_week ON public.weekly_email_deliveries USING btree (agent_id, week_start) WHERE ((recipient_type = 'agent'::text) AND (agent_id IS NOT NULL)) |
| uq_weekly_email_deliveries_loan_consultant_week | CREATE UNIQUE INDEX uq_weekly_email_deliveries_loan_consultant_week ON public.weekly_email_deliveries USING btree (loan_consultant_id, week_start) WHERE ((recipient_type = 'loan_consultant'::text) AND (loan_consultant_id IS NOT NULL)) |
| uq_weekly_email_deliveries_operator_week | CREATE UNIQUE INDEX uq_weekly_email_deliveries_operator_week ON public.weekly_email_deliveries USING btree (operator_id, week_start) WHERE ((recipient_type = 'operator'::text) AND (operator_id IS NOT NULL)) |
| uq_weekly_email_deliveries_user_week | CREATE UNIQUE INDEX uq_weekly_email_deliveries_user_week ON public.weekly_email_deliveries USING btree (user_id, week_start) WHERE ((recipient_type = 'user'::text) AND (user_id IS NOT NULL)) |
| weekly_email_deliveries_pkey | CREATE UNIQUE INDEX weekly_email_deliveries_pkey ON public.weekly_email_deliveries USING btree (id) |
| weekly_email_deliveries_tracking_token_key | CREATE UNIQUE INDEX weekly_email_deliveries_tracking_token_key ON public.weekly_email_deliveries USING btree (tracking_token) |
| weekly_email_deliveries_user_id_week_start_key | CREATE UNIQUE INDEX weekly_email_deliveries_user_id_week_start_key ON public.weekly_email_deliveries USING btree (user_id, week_start) |

### weekly_email_reports
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | bigint | int8 | NO | nextval('weekly_email_reports_id_seq'::regclass) | NO |
| experiment_start | date | date | NO |  | NO |
| report_key | text | text | NO |  | NO |
| status | text | text | NO | <literal-redacted>::text | NO |
| attempts | integer | int4 | NO | 0 | NO |
| claimed_at | timestamp without time zone | timestamp | YES |  | NO |
| claim_token | uuid | uuid | NO | gen_random_uuid() | NO |
| sent_at | timestamp without time zone | timestamp | YES |  | NO |
| error_message | text | text | YES |  | NO |
| created_at | timestamp without time zone | timestamp | NO | now() | NO |
| updated_at | timestamp without time zone | timestamp | NO | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | weekly_email_reports_attempts_check | - | CHECK ((attempts >= 0)) |
| p | weekly_email_reports_pkey | - | PRIMARY KEY (id) |
| u | weekly_email_reports_report_key_key | - | UNIQUE (report_key) |
| c | weekly_email_reports_status_check | - | CHECK ((status = ANY (ARRAY['sending'::text, 'sent'::text, 'failed'::text]))) |
| indexname | indexdef |
| --- | --- |
| idx_weekly_email_reports_retry | CREATE INDEX idx_weekly_email_reports_retry ON public.weekly_email_reports USING btree (experiment_start, status, claimed_at) |
| weekly_email_reports_pkey | CREATE UNIQUE INDEX weekly_email_reports_pkey ON public.weekly_email_reports USING btree (id) |
| weekly_email_reports_report_key_key | CREATE UNIQUE INDEX weekly_email_reports_report_key_key ON public.weekly_email_reports USING btree (report_key) |

### weekly_feature_tips
| column_name | data_type | udt_name | is_nullable | column_default | is_identity |
| --- | --- | --- | --- | --- | --- |
| id | integer | int4 | NO | nextval('weekly_feature_tips_id_seq'::regclass) | NO |
| episode | integer | int4 | NO |  | NO |
| title | text | text | NO |  | NO |
| body | text | text | NO |  | NO |
| cta_label | text | text | NO | <literal-redacted>::text | NO |
| cta_url | text | text | NO |  | NO |
| is_active | boolean | bool | NO | true | NO |
| created_at | timestamp without time zone | timestamp | YES | now() | NO |
| updated_at | timestamp without time zone | timestamp | YES | now() | NO |
| type | name | referenced_table | definition |
| --- | --- | --- | --- |
| c | weekly_feature_tips_episode_check | - | CHECK (((episode >= 1) AND (episode <= 8))) |
| u | weekly_feature_tips_episode_key | - | UNIQUE (episode) |
| p | weekly_feature_tips_pkey | - | PRIMARY KEY (id) |
| indexname | indexdef |
| --- | --- |
| idx_weekly_feature_tips_active_episode | CREATE INDEX idx_weekly_feature_tips_active_episode ON public.weekly_feature_tips USING btree (is_active, episode) |
| weekly_feature_tips_episode_key | CREATE UNIQUE INDEX weekly_feature_tips_episode_key ON public.weekly_feature_tips USING btree (episode) |
| weekly_feature_tips_pkey | CREATE UNIQUE INDEX weekly_feature_tips_pkey ON public.weekly_feature_tips USING btree (id) |

## Sequence metadata (no setval/nextval or last_value query executed)
| sequence_name | data_type | start_value | increment | minimum_value | maximum_value | cycle_option |
| --- | --- | --- | --- | --- | --- | --- |
| account_business_memberships_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| account_role_memberships_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| admin_edit_log_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| admin_notification_deliveries_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| admin_notification_email_attempt_history_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| admin_notification_email_attempts_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| admin_notifications_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| admin_users_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| agency_links_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| agent_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| agent_region_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| agent_service_regions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| agents_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| annual_tourism_roster_entries_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| annual_tourism_roster_versions_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| applications_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| auction_items_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| auction_photos_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| auction_rounds_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| booking_url_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| broker_registry_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| broker_registry_members_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| bug_reports_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| building_photos_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| building_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| building_stores_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| building_unit_areas_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| business_building_verifications_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| business_room_inventory_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| buy_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| chat_messages_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| chat_rooms_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| deal_alert_logs_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| email_ad_banners_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| hotel_operation_metrics_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| hotel_operation_source_versions_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| legal_documents_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_checklist_progress_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_likes_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_photos_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_request_deletion_archive_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| listing_request_history_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| listing_seq_broker | bigint | 1001 | 1 | 1 | 9223372036854775807 | NO |
| listing_seq_direct | bigint | 1001 | 1 | 1 | 9223372036854775807 | NO |
| listings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| loan_consult_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| loan_consultant_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| loan_consultant_service_areas_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| loan_consultants_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| lodging_approval_attempts_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_approval_batches_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_authority_contacts_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| lodging_parallel_comparisons_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_promotion_manifests_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_promotion_review_decisions_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_registry_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| lodging_source_batches_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| lodging_source_rows_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| login_history_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| master_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| member_documents_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| member_notes_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| membership_checks_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| membership_history_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| membership_payments_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| membership_periods_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| mileage_missions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| mileage_submissions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| new_listing_alert_logs_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| notices_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| notifications_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_consult_requests_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_lodging_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_lodging_photos_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_region_buildings_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_service_areas_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operator_service_regions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| operators_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| page_views_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| partner_favorites_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| password_reset_tokens_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| permit_change_alert_deliveries_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| permit_change_alert_logs_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| point_transactions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| policy_document_revisions_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| policy_documents_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| premium_waitlist_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| presale_applications_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| presale_audit_log_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| presale_projects_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| presale_promotions_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| region_badge_waitlist_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| revenue_records_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| rone_rental_benchmarks_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| room_expiry_alerts_sent_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| sgg_coords_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| site_popups_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| slots_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| subway_stations_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| survey_request_history_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| survey_requests_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| survey_settings_history_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| sync_failures_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| sync_log_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| tourism_dong_coords_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| tourism_stats_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| transactions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| urgent_listing_alert_logs_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| user_alert_subscriptions_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| user_favorites_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| users_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |
| weekly_email_deliveries_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| weekly_email_reports_id_seq | bigint | 1 | 1 | 1 | 9223372036854775807 | NO |
| weekly_feature_tips_id_seq | integer | 1 | 1 | 1 | 2147483647 | NO |


---

<!-- 04_EXISTING_LODGING_DATA.md -->

# 기존 숙박시설 데이터 자산

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 실제 원장 분류·규모
| classification | buildings | master_units | master_reported_units | geocoded | title_identified | detail_fetched |
| --- | --- | --- | --- | --- | --- | --- |
| 관광 | 1397 | 66634 | 5503 | 1370 | 1260 | 67 |
| 기타 | 6 | 138 | 0 | 6 | 2 | 0 |
| 농어촌민박 | 34506 | 93786 | 0 | 34465 | 25165 | 0 |
| 미분류 | 193 | 0 | 0 | 190 | 173 | 0 |
| 복합 | 1193 | 14057 | 0 | 1179 | 1139 | 43 |
| 생숙 | 6 | 2 | 0 | 6 | 6 | 0 |
| 생활 | 4260 | 144509 | 31575 | 4234 | 3067 | 514 |
| 에어비앤비 | 8423 | 8563 | 53 | 8412 | 8310 | 18 |
| 일반 | 28696 | 284547 | 1405 | 28374 | 26313 | 173 |
| 캠핑 | 4080 | 0 | 0 | 3964 | 2534 | 0 |
| 한옥 | 2387 | 2300 | 0 | 2348 | 2209 | 0 |
| <NULL/blank> | 470 | 6490 | 791 | 465 | 90 | 19 |

- CONFIRMED 위 표는 저장값 그대로의 raw 분류입니다. `생숙` 6행, `기타` 6행 및 NULL/빈 값이 남아 있습니다. 개편을 이유로 정규화/재분류하지 않았습니다.
- CONFIRMED `준공전`은 단순 lodging_type가 아니라 `building_status IN (허가,착공)` 및 use_apr_day NULL/빈값으로 파생됩니다. 공개 geo/cluster의 status gate는 API별로 차이가 있어 실제 WHERE도 확인해야 합니다. UI `미분류`는 NULL/빈 분류와 상태 필터를 결합합니다. 복합은 `복합` 및 병기 문자열을 고려합니다. `get_building_count()`는 생활/생숙 alias를 합치므로 raw 표를 화면 총계로 읽으면 안 됩니다.
- CONFIRMED 좌표 보유율 99.29%; 좌표 존재는 실제 위치 정확도의 보증이 아닙니다. 상세 보강 완료·PK 존재·모든 건축정보 확보는 서로 다릅니다.

## 영업신고 원장
| hygiene_type | rows | distinct_permits | active_status_rows | raw_room_sum | explicit_building_links |
| --- | --- | --- | --- | --- | --- |
| 관광숙박업 | 4329 | 4329 | 3452 | 206270 | 3445 |
| 관광펜션업 | 1663 | 1663 | 1329 | 0 | 1329 |
| 관광호텔 | 1992 | 1992 | 1454 | 187757 | 1454 |
| 농어촌민박업 | 55419 | 55419 | 36618 | 155007 | 36614 |
| 숙박업 기타 | 2403 | 2403 | 1721 | 46907 | 1720 |
| 숙박업(생활) | 8366 | 8366 | 7222 | 196525 | 7222 |
| 여관업 | 33824 | 33824 | 16262 | 674057 | 16267 |
| 여인숙업 | 8221 | 8221 | 1479 | 62768 | 1480 |
| 외국인관광 도시민박업 | 21 | 21 | 19 | 18 | 20 |
| 외국인관광도시민박업 | 14500 | 14500 | 11190 | 13249 | 11190 |
| 일반야영장업 | 6870 | 6870 | 5491 | 0 | 4121 |
| 일반호텔 | 3639 | 3639 | 2852 | 176432 | 2852 |
| 자동차야영장업 | 969 | 969 | 805 | 0 | 804 |
| 한옥체험업 | 3164 | 3164 | 2590 | 2603 | 2585 |
| 휴양콘도미니엄업 | 247 | 247 | 188 | 37053 | 185 |
|  | 4 | 4 | 3 | 383 | 3 |

`active_status_rows`는 코드와 동일하게 `biz_status_name='영업/정상'`로 계산했습니다. raw_room_sum은 전체 원장 합으로 폐업/중복을 포함하므로 공개 신고 호실수로 사용하면 안 됩니다. 업태별 신고번호 중복 제거와 전국 전체 신고번호 중복 제거는 다릅니다. `applied_building_id`는 명시 연결이고 서비스는 도로명 우선·지번 보조 주소 매칭도 사용합니다.

## 분류별 매물·관심·실거래 ID 연결
| lodging_type | listing_rows | general_favorites | partner_favorites | explicitly_linked_transactions |
| --- | --- | --- | --- | --- |
| 관광 | 0 | 2 | 1 | 320 |
| 복합 | 0 | 0 | 0 | 1 |
| 생활 | 27 | 38 | 3 | 561 |
| 에어비앤비 | 0 | 0 | 0 | 4 |
| 일반 | 1 | 8 | 1 | 397 |
| 캠핑 | 0 | 3 | 0 | 0 |
| 한옥 | 0 | 1 | 0 | 0 |

표에 없는 raw 분류는 이 INNER-activity filtered 조회에서 해당 연결 행이 관측되지 않은 것입니다. ID가 NULL인 주소 기반 거래는 제외했습니다. 관심 저장은 회원·파트너를 분리해 세었습니다.

## 출처/업데이트
- 건축대장: `sync_brhub.py` 전국 표제부, `building_registry.py` 상세 API, `backfill_building_details.py` 보강.
- 숙박 신고: `sync_lodgings.py` 행안부, `import_*_lodging.py`/정부 8종 CSV staging/검증/승격; legacy 수집 경로가 병존하며 허용/차단 상태는 gate에 의존.
- 농어촌/한옥/도시민박/캠핑: 독립 허가 원장과 법정분류 mapping. Airbnb는 UI legacy label이고 법적 도시민박과 예약 채널은 다른 의미.
- 관광: `annual_tourism_roster.py`/관광원본 적용 등 별도 보강. `gocamping_records`는 웹 보강·원본 계보를 보유.

## 관리자 표시 산식
`app.py:5245` · `get_building_count()`; `app.py:23360` · `_rebuild_master_stats()`; `app.py:23833` · `_lodging_full_stats_payload()`; `app.py:36539` · `_master_stats_admin_snapshot()`.
`_rebuild_master_stats`는 숙박/지역매칭/거래/수집 section을 병렬 집계하고 연동 section은 같은 세대를 보존합니다. 관리자/공개 총계는 건물 status·분류 alias·활성 신고·주소매칭·중복 제거·캐시에 의존합니다. 원장 COUNT와 UI 총계는 다릅니다. 실제 관리자 화면/API는 방문하지 않아 지금 렌더된 수치와의 대조는 UNKNOWN입니다.


---

<!-- 05_BUILDING_API_PIPELINE.md -->

# 건축물대장 수집·가공·저장

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 확인된 흐름
```text
HOME & STAY sync_brhub / building_registry
  → public_api_get (HUB relay switch ON: YES24 /v1/fetch; OFF: direct)
  → 국토부 BldRgstHubService 표제부 XML
  → ElementTree parsing / resultCode / pagination
  → 집합·일반 대장 + 숙박·호텔·콘도 문자 filter
  → 주소/지번/법정동 정규화 + 기존 키 dedup
  → lodging_type / 원본 용도 / 명칭 metadata
  → master_buildings (existing ID stable)
  → Kakao/VWorld 등 별도 주소 좌표 보강
  → buildings-geo / buildings-cluster → Kakao map
```
CONFIRMED: `sync_brhub.py:300 _process_items`는 regstrGbCdNm이 집합/일반인 것만 대상, mainPurpsCdNm+etcPurps에 숙박/호텔/콘도 키워드를 요구합니다. 주용도 gate를 통과하지 않고 숙박 부용도만 있으면 복합, 생활형숙박/생활숙박은 생활, 미상 세부는 일반으로 처리합니다. `units`는 hoCnt, 출처는 brhub_bulk. 코드의 dry-run도 API 요청 자체는 할 수 있어 실행하지 않았습니다.

## 세부 판별·보강
- `building_registry.py:244` · `fetch_building_title()`: 같은 지번 여러 동 중 숙박 용도 및 최대 hoCnt 대표를 선택.
- `building_registry.py:450` · `classify_lodging_type()`: 표제부 → 필요한 경우 층별개요, 생활/관광/일반 동시 존재는 복합. 관광 subtype 별도.
- `building_registry.py:324` · `fetch_expos_area_strict()`: 전유부 호실별 면적. `building_unit_areas`는 별도 캐시/호실 면적 자산.
- `lodging_classification.py:239` · `classify_building_use()`: 건축물 용도를 영업분류와 분리.
- `lodging_classification.py:198` · `should_protect_from_active_permit_reclassification()`: 검증된 대장 용도/기존 고신뢰 분류 보호.
- 상세 예산·lease/checkpoint는 `building_detail_budget.py`·`building_detail_enrichment.py`; 실패 원장은 `title_info_backfill_failures`.
- 건축물 관리 PK(`mgm_bldrgst_pk`)와 상가 bldMngNo 25자리, PNU 19자리 및 내부 master ID는 서로 다른 식별자.

## 확장 의견 (INFERRED)
현재 전국 collector의 숙박 필터를 완화하는 것은 기존 자산 의미·통계 범위를 바꿉니다. 신규 매물 등록용 주소/건물 조회 경로는 별도 등록 근거로 검토할 수 있지만 기존 수집기 조건을 변경하거나 전 건축물로 마스터를 덮어쓰면 안 됩니다. 구현은 하지 않았습니다.


---

<!-- 06_MAP_GEO_SYSTEM.md -->

# 지도·좌표 시스템

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 지도 UI 및 검색
- CONFIRMED 주 지도: Kakao Maps JS SDK (`static/js/main.js`, `static/index.html`, KAKAO_JS_KEY). Map·Marker·CustomOverlay·Roadview 보조 지도·지도 bounds를 사용.
- `app.py:4804` · `get_buildings_geo()`: viewport/bounds·지역·키워드·lodging_type 검색, 유효 좌표 건물 목록, 거래/매물 관련 지표.
- `app.py:4427` · `get_buildings_cluster()`: 시도/시군구/읍면동 등의 서버 SQL 그룹 집계. 이름이 cluster라고 해서 반드시 Kakao MarkerClusterer 구현은 아닙니다. 실제 grouping 기반 coarse marker 및 상세 overlay 전환을 확인.
- `app.py:2233` · `get_building()`: 내부 건물 ID로 상세 조회; 관심·파트너·운영·매물·표제부 연결.
- 좌표 필드: master_buildings.lat/lng, auction_items.lat/lng, sgg_coords 및 tourism_dong_coords. 사용자·매물·거래 각각 같은 좌표 범위를 갖는 것은 아닙니다.
- 주소 검색/좌표: Kakao REST, Juso 주소 lookup, VWorld 좌표 보조; Google/StreetView는 사진·참고영상 용도도 병존. 실제 활성 key/공급자 호출 가능 여부는 UNKNOWN.

## 표시·비공개·반경
`main.js`는 bounds 조회, CustomOverlay 생성, 관광 열지도/공매/선택 단지·Roadview 연동을 수행합니다. 공개 매물과 제한공개 매물의 정확한 주소·건물 자동값 접근은 `disclosure_scope` 및 서버 public payload에 의해 제한됩니다. 단순 JS에서 위치를 숨기는 방식만으로 충분하지 않습니다. 반경 검색/지도 거리 영역 관련 code를 확인했지만 실시간 렌더링·정확한 미터 환산은 UI를 실행하지 않아 UNKNOWN입니다.

## 신규 등록 시점 marker 방식 (INFERRED)
기존 주소검색/대장 확인/지오코딩·매물 ID/이미지 구조를 활용해 등록 완료된 매물만 별도 레이어에서 표시하는 확장 가능성이 있습니다. 신규 레이어의 source/query를 기존 숙박 master 레이어 및 관광/공매 aggregate와 분리해야 합니다. 현재 숙박 collector/건물통계는 보존 대상이며 미숙박용 건축물 등록이 기존 lodging_type 변경을 요구해서는 안 됩니다.


---

<!-- 07_RTMS_REALTRADE.md -->

# 국토부 실거래 데이터

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 수집/중계/저장
- RTMS_SERVICE_KEY → `sync_batch.py` 및 `sync_rural_hanok_trades.py`/관련 app 호출; `public_api_get`의 rtms bucket으로 조건부 relay. NrgTrade/RHTrade/SHTrade/LandTrade 서비스 prefix를 허용.
- `sync_batch.py:277` · `fetch_nrg_trade()`: 업무·상업용 중심 기존 조회; `sync_rural_hanok_trades.py`는 토지/단독/연립 등 scope를 구분하는 추가 경로.
- `transactions`: raw_key·deal_date·deal_type·price·area·sgg_cd·umd_nm·jibun·주소·건물명·source_api·source_building_type·transaction_scope·match_confidence·master_building_id 보유. 가격 단위는 API parsing/화면 변환을 그대로 따라야 하며 매물 field 이름만으로 KRW 원 단위라고 가정하면 안 됩니다. 현재 listing_requests.price_krw는 레거시 이름과 달리 만원 단위로 처리합니다(app.py:13082,13118; main.js:7279). 온비드 price_minimum_krw 등 실제 원 단위와의 혼합이 별도 위험입니다.
- raw_key 관련 UNIQUE/중복방지는 schema 인덱스와 ON CONFLICT 경로로 확인; `sync_failures`·quota/checkpoint·월별 재처리·run_id fence 등의 collector 체계를 보존해야 합니다.

## 건물 연결
`sync_batch.py:312` · `transaction_scope_for_trade()`; `sync_batch.py:317` · `whole_building_match_reason()`; `sync_batch.py:341` · `exact_master_for_unit_trade()`.
일반 건물 거래는 whole_building, 그 외는 unit 분기. 전체 건물 자동연결은 정확히 한 일반숙박 master 조건, 호실은 유일 후보 또는 정확한 원천 건물명 대조를 사용. 시군구/읍면동/지번·도로명 정규화가 연결에 관여하고 ambiguous는 임의 연결하지 않습니다. 토지 거래는 건물 거래와 합치지 않습니다.

## 운영 규모 (CONFIRMED COUNT)
| asset | rows | linked_buildings |
| --- | --- | --- |
| transactions | 19094 | 1283 |

여기 연결 건수는 master_building_id가 NULL이 아닌 거래 행 수이며 서로 다른 건물 수가 아닙니다. 주소/이름 기반 조회 후보는 이 계수에 포함되지 않습니다.

## 노출·분석·관리
`app.py` 거래 API/랭킹/건물 상세, `main.js` 실거래 표시, 자산분석은 최신·유일 매칭·범위 조건의 거래 기준치를 사용합니다. `sync_runner.py`/`scheduled_sync.py` 및 관리자 수동 collector가 존재합니다. 실제 신규 수집·사용자 API·관리자 버튼은 실행하지 않았습니다. DataLab 및 투자/운영 추이의 모든 화면별 숫자 재현은 UNKNOWN이며 static route/함수 근거는 routes.csv에 포함됩니다.


---

<!-- 08_STORE_COMMERCIAL_DATA.md -->

# 상가·상권 데이터

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 제공기관/요청
- CONFIRMED 소상공인시장진흥공단 상가(상권)정보 API 계열, STORE_INFO_SERVICE_KEY, `store_info_util.py`의 storeListInPnu/storeListInBuilding XML 요청.
- `store_info_util.py:71` · `build_pnu()`: PNU 19자리 생성. 표제부 mgmBldrgstPk를 25자리 bldMngNo로 오인해서는 안 됨.
- `store_info_util.py:79` · `_fetch_stores()`: XML 지정·pagination·ConnectTimeout budget. 이 계열은 relay allowlist에 없어 direct 경로.
- `sync_stores.py`·`sync_realty_stores.py`: 일반 상가와 입점 부동산 보강. `quota_policy.py`의 공유 요청 예산을 존중.
- `building_stores(master_building_id,store_name,category,floor,ho_no,inds_mcls_nm,inds_scls_nm)` 저장; 건물의 realty_store_name/realty_checked_at cache와 broker_registry 계열은 독립 원장입니다.

## 규모/화면
| asset | rows | linked_buildings |
| --- | --- | --- |
| building_stores | 10603 | 10603 |

`app.py:3825` · `get_building_nearby_stores()`: 건물 인근/입점정보 조회와 캐시. 관리자 후보·입점 부동산 조회에는 broker 표준원장 우선/상가 cache 보조가 병존합니다. 전체 row의 실제 UI 이용/조회 빈도는 페이지·접근 로그를 조회하지 않아 UNKNOWN; 저장만 되는 행이 있다고 단정하지 않았습니다.

## 재활용 의견 (INFERRED)
신규 단기임대 인근 편의시설 레이어/상권 참고정보로 재사용 가능하나 건물 입점 vs 주변시설은 범위를 분리해야 합니다. 데이터 업데이트 시점·폐업/이전 정보·업종 정확도를 보증하지 않습니다. 기존 예산과 master 연결을 변경하지 않았습니다.


---

<!-- 09_TOURISM_DATA.md -->

# 관광 데이터·데이터랩·운영분석

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 서로 다른 원천
1. CONFIRMED TourAPI/KorService2: 관광 숙박 장소·사진·메타데이터. `backfill_tourapi_images.py`, `sync_building_photos.py`, `prewarm_tourapi_metadata.py`, app 사진 endpoint.
2. CONFIRMED GoCamping: basedList/imageList 시설·사이트·이미지, `sync_lodgings.py` 및 웹 보강 `backfill_gocamping_web.py`, `gocamping_records`.
3. CONFIRMED 한국관광 데이터랩 CSV/ZIP 원본: `import_tourism_stats.py TYPE_RULES`의 visitor_sido/visitor_sgg/foreign/consumption/search/lodging_search_rank/surge_dong/camping 유형. `tourism_datalab_admin.py` staging·검증·원본 보존.
4. CONFIRMED 월간 자동 경로 `sync_tourism_monthly.py.fetch_approved_source`: 승인 manifest URL 또는 App Storage content-addressed archive, SHA-256·동일 origin·크기·redirect 금지 확인 후 import. 인증된 DataLab 사이트에서 임의 자동 scrape한다고 확인된 것이 아님.
5. `annual_tourism_roster*` 관광숙박 원장·evidence와 `hotel_operation_metrics` 업로드 운영실적은 또 다른 데이터 자산.

## 저장·표시
| asset | rows | linked_buildings |
| --- | --- | --- |
| tourism_stats | 3599 | 26 |

대부분은 행정지역·기간·지표 단위이고 개별 건물 연결은 선택적입니다. source/source_file/source_period/ref_yearmonth/dimensions/row_hash/collected_at 등 계보 필드를 보유. 개인 원본 파일명이나 실제 지표 샘플값은 보고서에 추출하지 않았습니다.

## 분석 연결
관광수요·급등동네·검색순위·지도 heatmap·자산/운영분석 및 HS-OI 참고값과 연결됩니다. 월간 비교는 최신 source/region/month·기간 완전성 검증 코드가 존재하며, 실제 현재 coverage/원본 누락은 aggregate metadata만으로 증명할 수 없어 UNKNOWN입니다. 관광 수요 지표를 실제 예약·매출·점유율로 단정하면 안 됩니다. ADR/RevPAR/객실매출 등 운영 업로드 지표는 동기간 원칙과 parser 검증이 별도입니다.

## 재사용 의견 (INFERRED)
수요 참고 layer·지역 설명·운영분석 근거로 재사용하되 신규 단기임대 성과 예측으로 확정 표시하지 않습니다. 관광/캠핑 원본을 기존 숙박 건물/호실 총계로 합쳐 계산하지 않습니다.


---

<!-- 10_ONBID_AUCTION.md -->

# 온비드 공매 수집·연결·업무 흐름

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 출처·전송
- CONFIRMED 온비드 공공 API B010003 계열; URL은 external_api_inventory.csv. `sync_onbid.py` → `public_api_get(...purpose="batch",timeout=(15,30))` → 조건부 RELAY_USE_ONBID.
- `sync_onbid.py:46` · `_onbid_get()`: RELAY_QUOTA는 BudgetExceeded, RELAY_AUTH/FORBIDDEN은 PermissionError, 그 외 RelayError는 execution failure. direct 우회 없음 (switch OFF는 원래 direct).
- `sync_onbid.py:130` · `reserve()`: API 요청 전 DB 예산 예약. claim/own/heartbeat/run_id에 따른 배치 소유권; list→detail·작은 commit·checkpoint.

## 데이터·좌표·연결
| asset | rows | linked_buildings |
| --- | --- | --- |
| auction_items | 8883 | 598 |

auction_items는 source/source_item_id/pbct_cdtn_no/가격/기간/status/usage/좌표/master ID/raw/detail_fingerprint와 확인 항목을 보유. 회차 auction_rounds·사진 auction_photos·관심 auction_watches는 별도 테이블. source+item 같은 물건과 회차를 혼동하지 않습니다. `auction_building_matching.py`/`auction_building_enrichment.py`의 주소·지번·대장 증거로 연결; 미연결도 공매 자체 및 조사 신청과 분리합니다.

## 화면·관리
`auction_service.py.register_auction_routes` → 목록/상세/관심/건물별 공매. `main.js` 지도 공매 overlay, 공개 숙박 총계에 공매 물건 수를 더하지 않는 별도 표시. `survey_service.py`·survey_requests·membership_checks는 현황조사/멤버십 업무 경로. 법원경매 자동조회·중개/입찰대행·최종 낙찰 결과는 온비드 metadata만으로 보장되지 않습니다. 기존 공매 상세 3탭과 status 이력은 보존 대상입니다.

## 실행 상태
워크플로/관리자 수동 수집 경로는 확인했으나 이번 작업에서는 어떤 수집도 시작·정지·재시작하지 않았습니다. YES24 및 upstream 실제 응답/이미지/최근 공매 갱신 상태는 UNKNOWN입니다.


---

<!-- 11_YES24_RELAY.md -->

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


---

<!-- 12_ADMIN_SYSTEM.md -->

# 관리자 메뉴·API·DB 연결

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 메뉴 전수 목록
| menu | menu_key | page_route | ui_function | ui_code_location | api_candidates | db_tables_candidates | external_api_candidates | mutating_capability | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 통계 대시보드 | stats | /admin | showStats | static/admin.html:1413 | /api/admin/action-center;/api/admin/partner-building-counts;/api/admin/stats;/api/admin/stats/overview;/api/admin/sync-progress-summary | agent_buildings;agents;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;applications;booking_url_requests;broker_registry;bug_reports;building_requests;building_stores;buy_requests;listing_requests;lodging_registry;master_buildings;operator_buildings;operators;page_views;presale_applications;revenue_records;streetview_evaluation_metrics;survey_requests;sync_log;transactions;user_favorites;users | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 매출관리 | revenue | /admin | showRevenue | static/admin.html:9200 | /api/admin/revenue-summary | revenue_records | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 건물마스터 | buildings | /admin | showBuildings | static/admin.html:9380 | /api/admin/buildings;/api/admin/buildings/<dynamic>/kakao-promo-copy;/api/admin/buildings/bulk-delete;/api/admin/buildings/bulk-update;/api/admin/buildings/export.xlsx;/api/admin/buildings/full-stats;/api/admin/buildings/region-options;/api/v1/r/4c2/<dynamic>;/api/v1/r/8a1/<dynamic> | agent_buildings;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;broker_registry;building_stores;listing_requests;lodging_registry;master_buildings;slots;transactions;user_favorites;users | NONE statically reached / indirect UNKNOWN | DELETE;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 이용자 현황 | user-stats | /admin | showUserStats | static/admin.html:2017 | /api/admin/user-stats | agents;listing_requests;listings;operators;page_views;user_favorites;users | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 데이터 원본 창고 | warehouse | /admin | showWarehouse | static/admin.html:2031 | /api/admin/feature-tips;/api/admin/feature-tips/<dynamic>;/api/admin/stats/master | agent_buildings;app_meta;building_stores;listing_requests;lodging_registry;master_buildings;user_favorites;weekly_feature_tips | NONE statically reached / indirect UNKNOWN | PATCH;POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 관광 데이터랩 원본 | tourism-datalab | /admin | showTourismDatalab | static/admin.html:2367 | /api/admin/policies;/api/admin/tourism-datalab/apply;/api/admin/tourism-datalab/collections;/api/admin/tourism-datalab/preview | master_buildings;policy_document_revisions;policy_documents;sgg_coords;tourism_datalab_stages;tourism_dong_coords;tourism_stats | NONE statically reached / indirect UNKNOWN | POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 데이터 동기화 | datasync | /admin | showDataSync | static/admin.html:6221 | /api/admin/backfill-lodging-status;/api/admin/backfill-log;/api/admin/backfill-status;/api/admin/brhub-rescan-status;/api/admin/brhub-sync-status;/api/admin/broker-sync-status;/api/admin/buildings/<dynamic>;/api/admin/camping-image-backfill-status;/api/admin/datasync-board;/api/admin/datasync-overview;/api/admin/geocode-brokers-status;/api/admin/geocode-status;/api/admin/gocamping-web-backfill-status;/api/admin/lodging-classification-provenance;/api/admin/lodging-source-overview;/api/admin/lodging-staging/overview;/api/admin/lodging-sync-status;/api/admin/pending-completion;/api/admin/permits-sync-status;/api/admin/public-api-relay/status;/api/admin/realty-sync-status;/api/admin/reclassify-unclassified-status;/api/admin/stores-sync-status;/api/admin/sync-photos-status;/api/admin/sync-status;/api/admin/title-info-status;/api/admin/tourapi-image-backfill-status;/api/admin/weekly-digest-status | agent_buildings;agents;annual_tourism_roster_building_evidence;annual_tourism_roster_entries;annual_tourism_roster_versions;app_meta;broker_registry;building_photo_fetches;building_photos;building_stores;listing_requests;loan_consultants;lodging_approval_batches;lodging_import_staging;lodging_parallel_comparisons;lodging_promotion_manifests;lodging_promotion_review_decisions;lodging_promotion_rows;lodging_registry;lodging_source_batches;lodging_source_rows;master_buildings;operators;slots;transactions;user_favorites;users;weekly_email_deliveries | NONE statically reached / indirect UNKNOWN | DELETE;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 공매 현황조사 | admin-survey | /admin | activateSurvey | static/js/admin-survey.js:66 | /api/admin/survey/requests;/api/admin/survey/requests/<dynamic>;/api/admin/survey/requests/<dynamic>/status;/api/admin/survey/settings | app_meta;survey_request_history;survey_requests;survey_settings_history | NONE statically reached / indirect UNKNOWN | POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 멤버십 운영 | admin-membership | /admin | activate | static/js/admin-membership.js:11 | /api/admin/membership/checks/<dynamic>/status;/api/admin/membership/payments/<dynamic>/status;/api/admin/membership/requests | membership_checks;membership_history;membership_payments;membership_periods;users | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 회원관리 | members | /admin | showMembers | static/admin.html:9264 | /api/admin/applications;/api/admin/applications/export.xlsx;/api/admin/members;/api/admin/operators/<dynamic>/logo | account_business_memberships;account_role_memberships;admin_users;agent_buildings;agent_region_buildings;agent_service_regions;agents;app_meta;applications;booking_url_requests;bug_reports;buy_requests;chat_messages;chat_rooms;listing_likes;listing_photos;listing_request_deletion_archive;listing_request_history;listing_requests;listings;loan_consult_requests;loan_consultant_buildings;loan_consultant_service_areas;loan_consultants;lodging_registry;login_history;master_buildings;member_notes;mileage_submissions;notifications;operator_buildings;operator_consult_requests;operator_lodging;operator_region_buildings;operator_service_regions;operators;point_transactions;revenue_records;slots;user_favorites;users | https://homenstay.com;https://www.gocamping.or.kr/bsite/camp/info/read.do | DELETE;PATCH;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 매물관리 | listings | /admin | showListings | static/admin.html:3077 | /api/admin/buy-requests;/api/admin/buy-requests/bulk-delete;/api/admin/buy-requests/export.xlsx;/api/admin/listing-requests;/api/admin/listing-requests/bulk-delete;/api/admin/listing-requests/export.xlsx | agent_buildings;agents;buy_requests;chat_messages;chat_rooms;listing_likes;listing_photos;listing_request_deletion_archive;listing_request_history;listing_requests;master_buildings;users | NONE statically reached / indirect UNKNOWN | POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 중개 매물 검수 | /admin/broker-listings | /admin/broker-listings | UNKNOWN / link / disabled | static/admin.html:272 | /api/admin/broker-listings | account_business_memberships;agents;listing_photos;listing_request_history;listing_requests;master_buildings;users | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 실거래관리 | transactions | /admin | UNKNOWN / link / disabled | static/admin.html:273 | /api/admin/transactions;/api/admin/transactions/export.xlsx | admin_edit_log;app_meta;master_buildings;transactions | NONE statically reached / indirect UNKNOWN | PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 공지사항 관리 | notices | /admin | showNotices | static/admin.html:2903 | /api/admin/agency-links;/api/admin/agency-links/<dynamic>;/api/admin/agency-links/<dynamic>/logo;/api/admin/agency-links/reorder;/api/admin/notices;/api/admin/notices/upload-attachment;/api/admin/policies | agency_links;notices;policy_document_revisions;policy_documents | NONE statically reached / indirect UNKNOWN | DELETE;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 팝업관리 | popups | /admin | showPopups | static/admin.html:8225 | /api/admin/popups;/api/admin/popups/<dynamic> | site_popups | NONE statically reached / indirect UNKNOWN | DELETE;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 약관 관리 | legal | /admin | showLegal | static/admin.html:3301 | UNKNOWN | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 매뉴얼(정책) 관리 | policies | /admin | showPolicies | static/admin.html:9979 | /api/admin/policies;/api/admin/policies/;/api/admin/policies/<dynamic>/<dynamic> | policy_document_revisions;policy_documents | NONE statically reached / indirect UNKNOWN | POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 수정요청 이력 | requests | /admin | UNKNOWN / link / disabled | static/admin.html:278 | /api/admin/building-requests | app_meta;building_requests;master_buildings | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 인근 중개업소 후보 | brokers | /admin | showBrokers | static/admin.html:7033 | /api/admin/broker-sync-status | app_meta;broker_registry | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 미등록 위탁운영 후보 | lodgings | /admin | showLodgings | static/admin.html:7403 | /api/admin/lodging-sync-status;/api/admin/unregistered-lodging-candidates | app_meta;lodging_registry;master_buildings;operators | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 단지뱃지(골드)·지역뱃지(실버) 현황 | premium-status | /admin | showPremiumStatus | static/admin.html:7539 | /api/admin/premium-status | agent_buildings;agent_service_regions;agents;loan_consultant_buildings;loan_consultants;master_buildings;operator_buildings;operator_service_regions;operators | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| OTA 링크 신청 심사 | ota-requests | /admin | showOtaRequests | static/admin.html:7563 | /api/admin/booking-url-requests;/api/admin/booking-url-requests/summary | admin_users;booking_url_requests;master_buildings;operators | NONE statically reached / indirect UNKNOWN | POST | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 오류신고 관리 | bug-reports | /admin | showBugReports | static/admin.html:7772 | /api/admin/bug-reports;/api/admin/bug-reports/summary | bug_reports | NONE statically reached / indirect UNKNOWN | PATCH | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 이메일 배너 관리 | emailbanners | /admin | UNKNOWN / link / disabled | static/admin.html:284 | /api/admin/email-banners;/api/admin/email-banners/<dynamic>;/api/admin/email-banners/upload-image | email_ad_banners | NONE statically reached / indirect UNKNOWN | DELETE;PATCH;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 분양 관리 | presale | /admin | showPresale | static/admin.html:9996 | /api/admin/presale/applications;/api/admin/presale/applications/<dynamic>/applyhome-check;/api/admin/presale/applications/<dynamic>/document;/api/admin/presale/applications/<dynamic>/notify;/api/admin/presale/applications/<dynamic>/review;/api/admin/presale/banners;/api/admin/presale/banners/;/api/admin/presale/eligible-buildings;/api/admin/presale/projects;/api/admin/presale/projects/;/api/admin/presale/promotions;/api/admin/presale/promotions/ | master_buildings;presale_applications;presale_audit_log;presale_projects;presale_promotions | https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/{operation} | DELETE;POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 알림 센터 | admin-notifications | /admin | showAdminNotifications | static/admin.html:9940 | /api/admin/notification-email-attempts;/api/admin/notification-subscriptions;/api/admin/notifications;/api/admin/notifications/<dynamic>/read;/api/admin/notifications/unread-count | admin_event_subscriptions;admin_notification_email_attempt_history;admin_notification_email_attempts;admin_notifications;admin_users | NONE statically reached / indirect UNKNOWN | POST;PUT | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 마일리지 준비 중 |  | /admin | UNKNOWN / link / disabled | static/admin.html:287 | NONE (disabled) | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | NONE (disabled) | DISABLED/준비 중 (CONFIRMED UI) |
| 위탁운영사DB 준비 중 |  | /admin | UNKNOWN / link / disabled | static/admin.html:288 | NONE (disabled) | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | NONE (disabled) | DISABLED/준비 중 (CONFIRMED UI) |
| 광고상품 안내 | /admin/ad-products | /admin/ad-products | UNKNOWN / link / disabled | static/admin.html:289 | /api/admin/ad-products | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |
| 권한로그 준비 중 |  | /admin | UNKNOWN / link / disabled | static/admin.html:290 | NONE (disabled) | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | NONE (disabled) | DISABLED/준비 중 (CONFIRMED UI) |
| 회원·슬롯 준비 중 |  | /admin | UNKNOWN / link / disabled | static/admin.html:291 | NONE (disabled) | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | NONE (disabled) | DISABLED/준비 중 (CONFIRMED UI) |
| 비밀번호 변경 | changePwBtn | /admin | UNKNOWN / link / disabled | static/admin.html:295 | /api/admin/change-password | UNKNOWN / see route direct SQL | NONE statically reached / indirect UNKNOWN | UNKNOWN / see generic grid handlers | CONFIRMED menu; AST-scoped function/config mapping; helper reachability INFERRED; NOT EXECUTED |

총 32개 sidebar/비밀번호 항목. inline JS와 로드된 관리자 JS를 실행하지 않고 AST로 읽어 함수 경계를 분리했습니다. generic DataGrid·동적 URL·callback 호출의 실제 권한/효과는 UNKNOWN; table/API 후보는 INFERRED입니다. 전체 관리자 API는 routes.csv의 audience=ADMIN에 있습니다.

## 권한/업무
`app.py:8012` · `require_admin()` 관리자 guard, admin_users 세션과 일반 users 세션은 별도. 서버 작업 실행 API는 승인/원장·프로세스 lock/lease·상태 app_meta·알림 outbox와 연결되는 경우가 있으며 단순 조회도 cache rebuild/telemetry side effect가 있을 수 있습니다. 그래서 관리자 페이지/GET API조차 조사에서 호출하지 않았습니다.

## 수집/변경 위험 분리
건물명/분류/좌표 수정, 회원/파트너 승인·거절, 매물 검수/삭제, 거래 수집, 관광 ZIP import, 공매·멤버십 처리, 정책·약관 CMS, SMS/이메일 발송·동기화 API가 존재합니다. 이번 작업은 HTML/코드만 읽었고 실행 버튼·API·메일·SMS를 호출하지 않았습니다.


---

<!-- 13_LISTING_SYSTEM.md -->

# 기존 매물·의뢰·영업권·채팅 시스템

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 서로 다른 엔티티
- CONFIRMED `listing_requests`는 user_id/master_building_id/deal_mode·deal_type·transaction_target·publication_status/disclosure_scope를 보유한 의뢰/직거래/중개 매물 업무 원장.
- deal_mode(게시 방식)와 transaction_target(개별 호실/건물전체/영업권 등 거래 대상)은 독립. 중개의뢰를 자동 공개 매물로 바꾸면 안 됩니다.
- CONFIRMED `listings`는 별도 legacy/general table이므로 이름만으로 핵심 공개 매물 원장으로 판단하면 안 됩니다.
- CONFIRMED `auction_items`는 public source 공매 원장, 일반 판매자 listing ID가 아님. source item/회차/master ID를 분리.

## ID·연락·이미지·가격·주소
listing_requests.id/user_id/master_building_id/routed_agent_id/broker_agent_id, 가격 price_krw/monthly_rent_krw/deposit_krw 등, area_sqm/dong/ho 및 description, verified_phone, 공개 상태·범위·등급. 이미지 listing_photos → 저장소 key; 건물 주소·좌표는 master join. 제한공개는 자동 건물 값도 익명화 우회를 만들지 않아야 합니다. CONFIRMED listing_requests.price_krw는 이름과 달리 만원 단위입니다(app.py:13082/13118/13833; main.js:7279). 각 가격/deposit/rent/권리금 및 공매 원 단위는 개별 파서·UI 계약에 따라 검토하며 컬럼명만으로 자동 환산하면 안 됩니다.
영업권은 key_money/운영 매출/대출 승계/객실/OTA·단기 비율/business_rights_info 등 별도 값; 부동산 소유권 거래와 혼합하지 않습니다.

## 관계·상태·작업
등록/수정/삭제·초안·검수·비공개·철회·배정·매물 이력·문의/채팅·관심 listing_likes·알림 경로가 있습니다. 상태 변환은 role/소유권·검수 조건을 갖습니다. 철회 상태는 기록·채팅·배정을 지우는 작업과 다르며 삭제 archive가 존재합니다. UI/API의 exact 계약은 routes.csv 및 schema의 CHECK/columns 참조. 본 조사에서는 개별 매물/전화/채팅 내용을 읽지 않았습니다.

## 원장 규모/테이블
| table_name | row_count | row_count_basis |
| --- | --- | --- |
| business_room_inventory | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| buy_requests | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| chat_messages | 11 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| chat_rooms | 6 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_checklist_progress | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_likes | 7 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_photos | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_request_deletion_archive | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_request_history | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_requests | 28 | CONFIRMED COUNT(*) at query time |
| listings | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| slots | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |


## 신규 단기임대 확장 의견 (INFERRED)
기존 매물/관심/문의/사진 UI를 재사용할 여지는 있으나 기간 예약·재고·가격/보증금/관리비·취소 환불·결제 정산·단기 사용 계약의 완성 여부는 UNKNOWN입니다. `slots`/운영 객실 표가 있다고 예약엔진이 있다고 단정하지 않았습니다. 기존 매물을 지우거나 schema를 새 모델로 덮어쓰지 않았습니다.


---

<!-- 14_AUTH_USER_SYSTEM.md -->

# 인증·회원·파트너 및 2.0 충돌 분석

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 현재 실제 모델 (CONFIRMED)
- canonical `users`: 이메일 password_hash + Kakao ID/provider, 상태/동의/전화 인증.
- `account_role_memberships` + `account_business_memberships`: general/agent/operator/loan_consultant/lodging_operator와 승인된 사업장 context. 기존 agents/operators/loan_consultants는 업무·사업장 데이터이고 연결 계정의 로그인/재설정 자격증명은 users 단일 소유.
- `app.py:9526` · `_unified_role_login()`: 명시 role 선택, users password, approved context, 복수면 선택. 아직 연결 안 된 legacy business는 본래 password proof 후에만 최초 전환하며 기존 users 이메일 자동 병합을 하지 않습니다.
- `app.py:8987` · `_get_account_contexts()`; `app.py:9087` · `auth_switch_context()`: 활성 멤버십+승인 사업장·소유권 확인, 전용 dashboard로 전환.
- 중개사, 위탁/청소/세탁/용품/소독/세무/인테리어 운영지원, 대출상담사, 숙박운영자 지원. 분양은 현재 신청/프로젝트/승인 기능이며 이 네 역할과 같은 독립 로그인 dashboard가 있다고 확인되지 않았습니다.
- admin_users/session admin은 별도 관리자 인증. 일반 회원 session user_id/active_role/business와 혼동하지 않음.
- Flask signed cookie는 FLASK_SECRET_KEY, HttpOnly/Secure/SameSite=Lax. provider와 role은 다른 의미입니다.

## Kakao OAuth
`app.py:10018` · `kakao_start()`; `app.py:10035` · `kakao_callback()`.
KAKAO_REST_API_KEY/KAKAO_CLIENT_SECRET과 redirect URI/state 흐름 존재. Kakao 기존 ID로 users를 찾고 신규 가입은 카카오 password 없이 생성. 기존 이메일 충돌은 임의 account takeover 병합이 아닌 별도 처리 코드. 카카오 callback 후 general context를 시작합니다. token/실제 사용자 profile은 조회하지 않았습니다.

## 비밀번호/전화/세션
`app.py:9262` · `auth_request_password_reset()`; `app.py:9930` · `auth_change_password()`.
통합 password 변경·재설정, reset token digest/TTL/used_at, per-IP/per-email throttle, 비동기 메일; role/business session guard. 전화 OTP·본인 확인은 직거래 공개와 operator 신청 등 별도 목적. 새로 PW 바뀐 뒤 이미 발급된 모든 쿠키를 즉시 폐기하는 보장은 runtime/browser 확인을 하지 않아 UNKNOWN입니다.

## 미래 general=Kakao-only / partner=email 정책 충돌 (INFERRED)
1. 한 사람이 general과 여러 partner 역할을 함께 보유할 수 있으므로 general 로그인 버튼 정책과 users provider/password 소유권을 동일하게 취급하면 파트너 자격증명을 끊을 수 있습니다.
2. 이메일/비밀번호를 가진 기존 일반회원·Kakao+email 동시 계정의 이전/계정 연결·개인정보 동의·재설정·관심/채팅 이력 보존 정책이 필요합니다. 이번 단계에서는 결정·변경하지 않음.
3. 카카오 제공 이메일이 없거나 기존 이메일과 충돌하면 기존 계정 소유권 증명 문제가 남습니다. 이메일 문자열만으로 자동 연결하면 안 됨.
4. 파트너 role access는 Kakao 자체가 아니라 approved membership과 선택 context로 통제해야 합니다.
5. 신규 일반 이용자와 임대인/운영자/중개사의 역할 전환·동일 계정의 UI 분리가 필요하며 현재 역할/사업장 연결을 재사용할 수 있습니다. 구현 없음.


---

<!-- 15_DEPLOYMENT_INFRA.md -->

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


---

<!-- 16_REUSE_CLASSIFICATION.md -->

# HOME & STAY 2.0 자산 재활용 분류

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 분류 원칙
A 절대 보존 / B 그대로 재사용 / C 확장하여 사용 / D 신규 구축 필요. **아래는 모두 INFERRED 설계 의견이며 현재 변경 지시/확정 계획이 아닙니다.** A 자산의 읽기 API/UI는 재사용할 수 있어도 원장 대체/재구축은 허용되지 않습니다.

| asset | classification | reason |
| --- | --- | --- |
| 건물마스터 | A | 현재 숙박 원장·ID/sequence·계보 절대 보존, 신규 등록은 별도 참조 계층 검토 |
| 숙박시설 분류 | A | 법정 영업분류/건축 용도/플랫폼 분리 의미 보존 |
| 영업신고 | A | 활성·폐업·복수 인허가 원장 보존 |
| 좌표 | B | 기존 좌표는 재사용; 신규 등록 좌표·정확성/공개범위 확장은 C |
| 지도 | C | 기존 레이어 보존, 단기임대 등록 매물 overlay 추가 검토 |
| 주소검색 | C | 기존 Juso/Kakao·정규화 재사용, 숙박 필터 독립 등록조회 검토 |
| 실거래 | B | 범위·주소매칭·기간·원천 단위 계약 유지 |
| 상가정보 | C | 입점/주변시설·갱신시점 구분 확장 |
| 관광데이터 | B | 지표/기간/source version 보존, 예약 성과로 단정 금지 |
| 공매 | B | 공매 원장·회차·현황조사 기존 업무 유지 |
| 기존 매물 | A | 기존 의뢰/직거래/중개/영업권 데이터 보존, 재사용 UI는 C |
| 회원 | C | 단일 사용자 복수 역할 유지하며 general Kakao 정책 영향 검토 |
| 카카오 로그인 | C | 기존 OAuth 유지, provider/role 및 계정 연결 정책 검토 |
| 채팅 | C | 이력 보존; 신규 임차/운영 상대방·예약 연결 정책 필요 |
| 알림 | C | 기존 outbox/동의/멱등 전달, 예약 트리거 별도 검토 |
| 이미지 | B | 객체 key·소유권·서명/공개 proxy 유지 |
| 자산분석 | C | 기존 숙박 모델은 보존, 다양한 건물/단기 운영 가정 분리 |
| 데이터랩 | B | 기존 지역 통계·수요 layer 원본/기간 보존 |
| 관리자 | C | 기존 원본/배치/메뉴 유지, 신규 단기 업무 분리 확장 |
| Relay | B | 서비스 allowlist·오류 마스킹·fail-closed 유지 |
| 단기임대 일정·예약·정산 | D | 신규 정책·업무 모델·정합성 검증 필요; 기존 완성 여부 UNKNOWN |


---

<!-- 17_RISK_REGISTER.md -->

# 주요 위험 등록부

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

총 20개 위험. 기존 시스템 취약점이 실증됐다는 의미가 아니라, 확인된 의존성·미확인 영역에 대한 개편 위험입니다.

| id | priority | risk | evidence_status | evidence | analysis_only |
| --- | --- | --- | --- | --- | --- |
| R01 | CRITICAL | 기존 건물마스터를 전 건축물 원장으로 덮어쓰는 개편 | INFERRED impact; CONFIRMED dependency | master_buildings에 연결된 FK 및 기존 통계 분류 | 기존 원장·ID·sequence 보존; 신규 등록 건물 참조 계층은 별도 설계 의견만 제시 |
| R02 | CRITICAL | master_buildings 삭제/ID 재할당의 연쇄 영향 | CONFIRMED schema | ON DELETE CASCADE/SET NULL/RESTRICT 혼재, 다수 직접 FK | 삭제·재번호·sequence 초기화 금지; 링크 계보 유지 |
| R03 | HIGH | 숙박 영업분류와 건축물 용도 및 Airbnb 채널 혼동 | CONFIRMED code/data | lodging_classification.py; building_use_type; 운영에 생숙/기타/NULL 잔존 | 업종·용도·플랫폼 3개 의미를 분리; 데이터 재분류 금지 |
| R04 | HIGH | DB row count/공개 통계/관리자 통계의 불일치 오판 | CONFIRMED code | 분류 alias, 준공전 status, 주소매칭, distinct 신고, 별도 캐시 | 화면 수치를 원장 단순합으로 대체하지 않음; 각 산식 명시 |
| R05 | HIGH | 실거래 연결 범위·가격 단위 오판 | CONFIRMED code/data | transaction_scope; master_building_id; raw_key; 직접 ID 연결률·price_krw 레거시 만원 단위 | 호실/건물전체/토지 분리; 미연결 거래를 임의 연결 금지 |
| R06 | HIGH | 일반 카카오 전용 변경과 단일 계정 복수 역할 충돌 | CONFIRMED architecture; INFERRED change risk | users + role/business memberships; email/Kakao dual identity | 일반 화면 로그인 정책과 파트너 자격증명/역할 권한을 분리해 검토 |
| R07 | HIGH | 지도 참고 레이어가 기존 숙박 합계에 편입되는 위험 | CONFIRMED separate pipelines; INFERRED future risk | 관광 heatmap/공매/신규 단기임대 | 새 레이어와 기존 숙박 통계를 별도 집계 |
| R08 | HIGH | 제한공개 매물의 주소·좌표·건물정보 역추적 | CONFIRMED fields/guards; INFERRED regression risk | disclosure_scope; building_info_overrides; 지도 overlay | 신규 지도/주소검색에서 기존 익명화 계약을 유지 |
| R09 | HIGH | Relay 장애 시 우회 호출과 인증정보 로그 유출 | CONFIRMED fail-closed client; server UNKNOWN | public_api_client.py; secret_redaction.py | 클라이언트 fail-closed·오류 마스킹을 보존; 서버 실사는 별도 승인 필요 |
| R10 | HIGH | YES24 내부 allowlist/quota/TLS/서버 코드 미확인 | UNKNOWN | 현재 repo는 클라이언트이며 서버 접속/호출 없음 | 운영 서버 구성 증거 없이는 서버 보안/가용성을 확정하지 않음 |
| R11 | HIGH | 개발·운영 DB 선택 및 Publish DDL 영향 | CONFIRMED config; runtime DSN values UNKNOWN | DATABASE_URL/PROD_DATABASE_URL/DEV_DATABASE_URL; db.py init_db | 실제 DB 지문 확인과 schema diff 확인; 조사 단계 변경 금지 |
| R12 | HIGH | staging 승인 원본·manifest·legacy cutoff 손상 | CONFIRMED source modules | lodging_promotion/legacy_lodging_gate/quota_policy | 기존 원장·수동 검토 계보·중복 키·fence 정책 보존 |
| R13 | MEDIUM | 통계 캐시와 수집 중 집계의 시점 차이 | CONFIRMED code; work running | app_meta 신호; process cache; pooled DB priority | 집계 시각·캐시 세대 표시; 본 보고서 SELECT는 비원자 스냅샷 |
| R14 | HIGH | 예전 API·deprecated 경로를 새 수집기로 잘못 실행 | CONFIRMED multiple collectors | import_*/sync_*/reclassify_*/legacy gate | 코드 존재와 현재 허용된 운영 경로를 구분; 일괄 재실행 금지 |
| R15 | MEDIUM | FK 없는 논리 건물 ID 연결 누락·오연결 | CONFIRMED metadata | user_favorites 등 논리 참조 목록 | 주소/소유권/존재 검증 계약을 별도 분석; 데이터 변경 없음 |
| R16 | HIGH | 개인정보·서류·전화·채팅·토큰의 신규 공개 노출 | CONFIRMED columns; INFERRED future risk | users/operator_lodging/chat/member_documents/password_reset_tokens | 공개/비공개 객체 경로·소유권 검증과 digest-at-rest 유지 |
| R17 | MEDIUM | 관광 원본 기간·지표 불일치 및 공개/인증 원본 혼동 | CONFIRMED validation code | tourism_stats.source_period; monthly manifest; TYPE_RULES | 관광 수요·HS-OI 등을 다른 기간 매출 지표로 단정하지 않음 |
| R18 | HIGH | 예약/달력/재고/정산 시스템을 기존 listings 존재만으로 완성 처리 | INFERRED readiness gap | listing_requests/slots/business_room_inventory는 기존 업무 모델 | 신규 단기임대의 일정·예약·취소·정산 정책은 현재 미검증/새 설계 필요 |
| R19 | MEDIUM | 대형 단일 파일의 영향 범위와 정적 조사 한계 | CONFIRMED file size/static inventory | app.py/main.js/admin inline JS; dynamic dependencies | routes.csv에서 INFERRED/UNKNOWN 구분; 런타임/권한 실증은 별도 단계 |
| R20 | MEDIUM | 워크스페이스 조사와 현재 배포 버전의 차이 | CONFIRMED separate source/build context | deployment metadata does not prove exact source SHA | 본 보고서는 코드 snapshot+운영 schema 조사이지 배포 코드 diff 검증이 아님 |


---

<!-- 18_HOME_STAY_2_READINESS.md -->

# HOME & STAY 2.0 준비도·변경 없는 분석

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 최종 분석 의견 (INFERRED)
**기존 숙박 데이터 자산을 그대로 유지하면서 단기임대 등록 범위를 넓히는 방향은 가능성이 있으나, 현재 코드가 이미 완성된 단기임대 플랫폼이라는 뜻은 아닙니다.**

```text
기존 숙박 원장 + master_buildings (기존 ID/분류/통계/수집 유지)
          ↑ optional verified link (새 건물과 자동 동일시 금지)
신규 등록용 건물 참조/증거 [향후 설계]
          ↑
주소검색 → 건물 선택 → 대장 확인 → 좌표 확인
          → 단기임대 매물 [향후 설계]
          → 매물별 지도 marker [별도 layer]
          → 일정/예약/정산 [현재 완성 UNKNOWN, 별도 신규 설계]
```

## 보존 경계
- 원룸/오피스텔/아파트/빌라/연립/다세대/다가구/단독/도시형생활주택/상가/창고/숙박/캠핑/기타 등록 후보는 기존 숙박 원장 선정 조건과 독립되어야 합니다.
- 건축물대장 용도로 등록 자체를 사전 제한하지 않는 플랫폼 정책은 사용자가 제시한 미래 방향(USER-STATED)입니다. 사용 가능 법령·운영허가·안전·전대 동의까지 자동 허용되는 의미는 아니며 법률 검증은 UNKNOWN입니다.
- 내부 ID·기존 관심·거래·매물·파트너·공매·수집 계보를 보존. 대장명/주소 유사성만으로 기존 숙박 master에 신규 건물을 강제 병합하지 않음.
- 기존 데이터층(숙박/법정 신고/공매/관광)과 신규 매물 재고층(일정·유형·공개 위치)을 별도 집계.

## 준비도
CONFIRMED 기반: 주소/좌표·대장 API·숙박 원장·지도·매물/사진·계정/파트너 context·관심/채팅·알림·분석·관리자·Relay client.
INFERRED 확장 영역: 숙박 필터와 독립적인 등록 조회/등록 건물 참조·단기 유형/조건·임대인 승인/등록·검색/지도·운영 도구.
UNKNOWN 신규 업무: 정확한 일정/중복 예약/재고 잠금/요금/보증금/관리비/계약/취소·환불/결제·정산/분쟁·보호/일반 Kakao-only 이전 정책.

## 0단계 종료 경계
보고서·CSV·ZIP 작성까지만 수행. 코드/DB/SCHEMA_VERSION/Secrets/Relay/워크플로/운영 배포 변경 없음, 수집/테스트/운영 API 호출 없음, commit/push 없음. 다음 단계 개발/설정 변경은 이번 요청에 포함하지 않았습니다.

---

# 0단계 자체검증

CONFIRMED: 시작 시 기록한 기존 추적 파일 852개 SHA-256 원문 비교 결과 변경/삭제 0건.

- 소스/db.py/SCHEMA_VERSION/기존 파일명/설정: 변경 안 함.
- DB: 명시 production 경로의 schema metadata 및 SELECT aggregate만 호출. INSERT/UPDATE/DELETE/DDL/migration/sequence 조작 안 함. 기존 실행 배치는 조사와 별개로 계속 실행될 수 있으므로 DB 전체 불변을 주장하지 않음.
- API 신규 수집/동기화/관리자 실행 버튼/테스트용 운영 API: 호출 안 함. 앱/관리자 HTTP GET도 호출 안 함.
- Secret 값/연결 문자열/Relay token: 읽거나 기록 안 함. 이름과 존재만 확인.
- 개별 회원·신고 업체·연락처·채팅·문서·계좌·실거래 행: 추출 안 함. schema 정의/집계만 사용.
- 보고서 privacy 형식 검사: 실제 이메일·credentialed DB URL·JWT·private key·대표 provider key·긴 인증 query 패턴 없음. 실제 Secret 값을 읽어 비교하는 방식은 사용 안 함.
- Git commit/push: 실행 안 함. 소스 hash 검사는 git 외부 원문 기준도 포함.
- 배포/워크플로/Relay/YES24 설정·시작/정지/재시작: 안 함.
- CONFIRMED/INFERRED/UNKNOWN 구분, runtime/source snapshot 차이, row estimate -1 UNKNOWN, 활성신고 정확한 상태값, 금액의 레거시 만원 단위 기록.
- ZIP 허용 확장자: .md 및 .csv만. source/.env/DB dump/업로드 원본/조사 스크립트/AUDIT_COUNTS.json 제외.

Git status에서 신규 보고서 폴더 외 사전 존재 변경 여부는 시작 baseline과 hash로 검증했습니다. 플랫폼 자동 체크포인트는 본 작업이 git commit 명령을 실행했다는 의미가 아닙니다.
