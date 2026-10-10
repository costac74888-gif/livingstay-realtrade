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
