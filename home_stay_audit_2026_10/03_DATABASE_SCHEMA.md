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
