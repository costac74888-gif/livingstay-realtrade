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
