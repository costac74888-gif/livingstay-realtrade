---
name: LivingStay lodging_type 분류(생활/호텔/콘도) 불변식
description: v9 방향 — 비생숙을 삭제하지 말고 lodging_type으로 재분류. 적재 경로가 라벨을 안 채우면 기본 필터에서 사라지는 함정과 wrapper 계약.
---

## 핵심 방향 (v9~)
- 예전: 비생숙(호텔/콘도)을 DELETE. 지금: **삭제하지 않고** `lodging_type`(생활/호텔/콘도) + `lodging_type_detail`(대장 원문)로 분류해 보존.
- 기본 UI 필터는 "생숙만" = `lodging_type='생활'`. "전체"는 빈 파라미터 → WHERE 미적용 → NULL/미확인 포함 전부 노출.
- 분류는 `building_registry.classify_lodging_type()` 담당 → `(label, detail, title, reason)`. label은 '생활'|'호텔'|'콘도'|None.

## 불변식 (이걸 어기면 거래가 조용히 사라짐)
**transactions/master_buildings에 INSERT하는 모든 적재 경로는 lodging_type을 채워야 한다.**
- 안 채우면 그 행은 NULL → 기본 '생숙만' 필터에서 **숨겨져** 사용자가 "데이터가 사라졌다"고 느낀다.
- **Why:** 기능 코드만 머지하고 sync_batch/discover의 적재부를 안 고치면, 신규 동기화되는 생숙이 계속 NULL로 들어와 안 보인다 (아키텍트 리뷰에서 실제 지적됨).
- **How to apply:** master 매칭 경로는 매칭된 master 행의 lodging_type/detail을 거래로 복사. 신규검증 경로(sync verified_new)는 classify로 label='생활'만 편입하며 label+detail을 master/거래 양쪽에 저장. discover는 verdict True=생활 확정이므로 '생활'로 태깅.

## is_living_stay wrapper 계약 (레거시 호출자 보존)
`is_living_stay`는 classify를 감싸 레거시 3-튜플 `(verdict, title, reason)` 유지. label None일 때 3분기:
- title None → `(None, None)`: 집합 표제부 자체 없음. 재시도 아님.
- title 있고 reason에 "재시도" 포함 → `(None, title)`: 층별개요 조회 실패 = 일시적 → 호출측 재시도 대상.
- title 있고 판정불가 → `(False, title)`: 표제부는 받았으나 생활/호텔/콘도 키워드 전무 = 생숙 아님 확정.
- **Why:** discover/verify가 `verdict is None and title is not None`을 일시 실패로 보고 재시도한다. 판정불가를 None으로 두면 무한 재시도.

## 용도 병기(복합) — 여러 동/여러 용도
- '혼재' 개념 폐기. 한 지번에 용도가 여러 개면 `·`로 병기하고 **항상 생활→호텔→콘도 순**으로 정렬(`_combine_labels`). 예: `호텔·콘도`, `생활·호텔`.
- 판정은 **지번(sgg_cd+umd_nm+jibun) 내 전체 동을 집계**해야 정확하다. 아난티 앳 부산(733)=관광호텔 동 + 휴양콘도 동 → 호텔·콘도. 대표 동 1개만 보면 틀린다.
- UI 필터 `lodging_type=복합` → 백엔드 `LIKE '%·%'`.
- **"관광숙박시설"은 호텔업+휴양콘도미니엄업을 다 포함하는 상위 분류명이다.** `_find_categories`에서 이 단어만 보고 호텔로 잡으면 `관광숙박시설(휴양콘도미니엄)`(순수 콘도)이 '호텔·콘도'로 오분류된다. 호텔은 `관광호텔`/`일반숙박시설`이 있거나, 콘도 표기(`휴양콘도미니엄`) 없이 `관광숙박시설`만 있을 때만 인정. — **Why:** 표본 재검증서 아폴리스/골드훼미리/스카이콘도 등 다수가 이 버그로 가짜 병기였음(호텔·콘도 202→138건으로 정정). **How:** 병기는 여러 동에 실제로 다른 용도가 있을 때만 나와야 함; 한 동 문자열 안의 상위명+세부용도를 각각 다른 용도로 세지 말 것.
- **표제부/층별개요 API는 반드시 페이징할 것(totalCount까지).** `numOfRows` 한 페이지 고정이면 동 50~100+ 대단지가 잘려 집계가 깨진다. 실제 아난티 콘도(732)는 동이 100개라 예전 50 고정에선 잘렸다(다만 전부 콘도라 라벨은 우연히 동일). — **Why:** 아키텍트 리뷰에서 '치명적 정확성 공백'으로 지적됨. **How:** `_fetch_title_rows`/`fetch_floor_outline`가 items 소진·`len>=totalCount`·page>=20까지 루프.

## 미매칭 실거래 라벨링
- 마스터에 없는 실거래(약 110곳)는 `reclassify_unmatched()`가 `(sgg_cd,umd_nm,jibun)`로 그룹핑해 건축물대장으로 분류.
- **UPDATE는 `lodging_type IS NULL`인 행만** 갱신 → 이미 매칭된 거래를 절대 덮어쓰지 않는다(데이터 안전). 아난티 거래는 `match_source='buildinghub'`라 lodging_type NULL이었음.
- `reclassify_buildings.py` 플래그: 기본=마스터 재분류, `--unmatched`=미매칭만, `--force --unmatched`=둘 다, `--export`=신마스터 엑셀(`신마스터_..._YYYYMMDD.xlsx`, DB 읽기만, write-back 없음).

## 백필(기존 데이터 재분류)
- `reclassify_buildings.py`가 master를 재분류하고 거래를 `building_name+sgg_cd+jibun`(parcel 아님)으로 UPDATE.
- **오래 걸린다(수백 건 × 정부 API).** nohup 백그라운드는 샌드박스가 턴 사이에 죽인다 → **워크플로(console)로 돌려 완주**시킬 것. 완료 후 워크플로 제거.
- 미확인(label None: 여관/호스텔/표제부없음)은 NULL로 남는 게 정상. 레거시 `buildinghub` 거래도 NULL로 남음(폐기된 흐름) — 전체 필터에선 여전히 보임.
