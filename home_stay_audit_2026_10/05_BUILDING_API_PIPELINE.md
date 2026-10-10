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
