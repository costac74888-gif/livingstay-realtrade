---
name: LivingStay 공공데이터 API 매칭
description: 생숙 실거래(RTMS)·주소변환(JUSO) 정부 API의 응답 필드 및 매칭 키에 관한 비자명한 사실
---

# 생숙(생활숙박시설) 실거래 파이프라인 — 정부 API 사실

프로젝트: livingstay (Flask + PostgreSQL). 마스터 엑셀(전국 생숙 현황)과 RTMS 실거래를 매칭해 게시.

## RTMS NrgTrade (상업업무용 매매) 응답
- 엔드포인트: `apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade` (XML)
- 유형 필드는 **`buildingType`** 이며 값은 `'일반'` / `'집합'`. (문서/추측상 자주 쓰이는 `houseType`/`regstrGbCdNm`/`bldGbCdNm`는 이 응답에 **없음**.)
- **생활숙박시설은 `buildingType == '집합'`** 로 필터. 그중 `buildingUse == '숙박'`이 실제 생숙.
- 주요 필드: `sggCd`, `umdNm`, `jibun`, `dealAmount`(콤마 포함), `buildingAr`, `dealYear/dealMonth/dealDay`, `dealingGbn`(중개/직거래).
- **`umdNm`은 면/리 지역에서 `'설악면 방일리'`처럼 "면 리" 형태**(공백 포함), 동 지역은 `'금학동'` 단일 토큰.
- **용도 필드는 `buildingUse`** (raw 확인), 값 예: `판매`/`제1종근린생활`/`제2종근린생활`/`기타`/`숙박`. 생숙은 `buildingUse`에 `'숙박'` 포함. 필드가 비면 통과시켜(매칭에서 걸러짐) 필드누락 사고 방지.

## 건축HUB 건축물대장 (호수 검증)
- 생숙(집합) 호실수 정답 필드 = **표제부 `getBrTitleInfo`의 `hoCnt`(호수)**. `hhldCnt`/`fmlyCnt`는 생숙에선 **항상 0**.
- **총괄표제부 `getBrRecapTitleInfo`로는 단일 집합건물이 안 잡힘**(totalCount=0). 반드시 표제부(getBrTitleInfo) 사용.
- 한 지번에 여러 동이면 표제부가 여러 건 → `mainPurpsCdNm`에 '숙박' 있는 동 우선, 그중 `hoCnt` 최댓값.
- 표제부 조회 코드(sigunguCd/bjdongCd/platGbCd/bun/ji)는 **JUSO `bdMgtSn`(건물관리번호) 앞 10자리=법정동코드**에서 추출 → CSV 불필요.
- v3 zip의 sync_batch/verify_units는 하드코딩 키·잘못된 집합필드(houseType/regstrGbCdNm)로 **회귀**시킴 → 그대로 덮지 말 것.

## JUSO addrLinkApi (도로명→지번)
- `business.juso.go.kr/addrlink/addrLinkApi.do`, `confmKey`=JUSO_API_KEY.
- 응답 `admCd`(10자리)의 **앞 5자리 = 시군구코드(LAWD_CD)** = RTMS `sggCd`와 일치.
  → **법정동코드 CSV 없이도 JUSO만으로 sgg_cd 확보 가능** (master 매칭 경로엔 CSV 불필요).
- `emdNm`(면/동) + `liNm`(리)가 분리 반환됨.
- **JUSO는 도로명 뒤 꼬리표(층수/동/`(법정동)`, 쉼표 또는 괄호로 시작)가 붙으면 `totalCount=0`으로 실패**. 쉼표 앞부분만 취하고 끝의 `(…)`도 제거해 순수 도로명만 질의할 것. 마스터 주소 상당수가 이 꼬리표를 포함하므로 변환율에 큰 영향.

## 매칭 키 (경험적 검증 결과)
- master↔RTMS 매칭 키 = `sgg_cd` + `umdNm` + `jibun`.
- **`umdNm`은 공백 제거 후 비교**하고, 면/리 지역은 master를 `emdNm+liNm`으로 만들어야 매칭됨.
  emd만 쓰면(원본 코드 방식) 면/리 지역에서 매칭 누락 → `emdNm+liNm`이 매칭률 더 높음.
- 법정동코드 CSV(`법정동코드 전체자료.csv`, cp949)는 **buildinghub 표제부 보완(마스터에 없는 신축)** 경로에서만 필요.

## 배치 실행 운영 (이 repl 환경)
- **긴 배치/verify는 환경이 강제 종료(exit -1, 무출력)** 시킴. 반드시 **작은 청크(--offset/--limit)** 로 나누고 **행마다 증분 commit** 할 것. 루프 끝 단일 commit이면 종료 시 전량 유실됨.
- 증분 commit + (건물명+주소) 중복 INSERT 가드가 있으면, 강제 종료된 청크의 구제분도 DB에 보존되고 재실행 시 "이미등록됨"으로 안전하게 스킵됨. → verify_result CSV 합계는 재실행 중복으로 부풀므로 **신뢰 기준은 DB의 master_buildings 카운트**.
- '호수 미기재'로 제외된 건의 대부분은 시골 펜션/빌라(표제부 totalCount=0)로 정당 제외이나, 일부는 엑셀 호수 누락으로 잘못 제외된 대형 생숙 타워 → verify로 구제해야 함. 신뢰 기준은 DB `master_buildings` 카운트(CSV 합계 아님).

**Why:** 이 필드명/코드 규칙은 응답을 실제로 찍어봐야만 알 수 있고 정부 문서 표기와 다름. 매칭률 손실의 주원인이 umdNm 형식 차이였음.

## 전국 발굴 배치 (discover_new_buildings.py)
- **전국 신규 생숙 발굴은 법정동코드 CSV(`법정동코드 전체자료.csv`, cp949)가 필수** — `BjdongMap.all_sgg_codes()`로 순회할 전국 시군구 목록의 유일한 출처. CSV 없으면 `--list-only`부터 `FileNotFoundError`. (지역 한정 `sync_batch.py`만 CSV-free)
- 등록 판정: RTMS `buildingType=='집합' & buildingUse=='숙박'` → 생숙 후보. 호수(hoCnt)는 필터 아닌 정보용. **30실 게이트 폐기**(discover·verify_units·개념상 load_master 모두 해당).
- **⚠️ 생숙 판별은 표제부(getBrTitleInfo)만으로는 불안정**: 표제부 `mainPurpsCdNm`/`etcPurps` 표기가 건물마다 들쭉날쭉하다. 일부 생숙은 `etcPurps='숙박시설(생활숙박시설...)'`로 명시(예: 경희마크329)되지만, 많은 실제 생숙은 그냥 `'숙박시설'`로만 나와(예: 휴스테이·수아하우스) 표제부에서 '생활숙박' 문자열로만 거르면 그 건들을 **조용히 전량 거부**한다.
- **신뢰 가능한 판별 기준은 층별개요(getBrFlrOulnInfo)**: 층마다 `mainPurpsCdNm`=`'생활숙박시설'`(또는 `etcPurps='숙박시설(생활숙박시설(N호))'`)로 일관되게 찍힌다. → 하이브리드: 표제부에 '생활숙박' 있으면 통과(호출 절약), 없으면 그때만 층별개요 1건 추가 조회해 판정.
- **판별 로직은 `building_registry.py`(fetch_building_title + is_living_stay) 한 곳에만** 둔다. discover·verify_units가 각자 따로 구현하다 한쪽만 고쳐지는 드리프트가 이 프로젝트에서 반복됐음 → 반드시 공용 모듈 import로 통일.
- **Why:** 표제부는 '숙박시설' 대분류를 담되 생숙/일반/관광 세분류 표기가 일관되지 않고, 세분류는 층별 세부용도에 일관되게 존재. 실제 마스터 생숙(휴스테이·경희마크329 등) 표제부를 직접 찍어 확인함.
- 진행상황은 `discover_progress(sgg_cd, deal_ymd)` 테이블로 재실행 스킵, 건별 즉시 commit(환경 강제종료 대비).
- `master_buildings.source`: 'original'(엑셀) vs 'api_discovered'(발굴). raw_key DB UNIQUE 제약은 db.py `_ensure_raw_key_unique_constraint()`가 중복정리 후 부여.

## umdNm → bjdongCd 매칭 (BjdongMap.find_bjdong_cd)
- RTMS `umdNm`은 면/리 지역에서 `'사천면 사천진리'`처럼 면+리가 공백으로 합쳐진 형태 → **마지막 토큰 하나만 비교하면 실패**.
- 그렇다고 **문자열 그대로 `endswith(umd_nm)` 하면 `'교동'`이 `'서교동'`에도 걸리는 접미사 오매칭** 발생(현 데이터 기준 시군구 109곳, 단일토큰 읍면동의 약 2.68%가 충돌). 반드시 **토큰 단위 tail 비교**(`법정동명.split()[-n:] == umd_nm.split()`)로 할 것.
- **Why:** 문자열 접미사 매칭은 조용히 잘못된 bjdongCd를 반환하고 첫 행을 임의로 선택 → 건축물대장 조회가 엉뚱한 동으로 감. 토큰 tail 비교는 동/면+리 둘 다 정확히 잡으면서 오매칭을 막음.
