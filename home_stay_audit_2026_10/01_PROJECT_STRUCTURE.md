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
