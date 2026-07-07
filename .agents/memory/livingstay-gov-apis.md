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

## JUSO addrLinkApi (도로명→지번)
- `business.juso.go.kr/addrlink/addrLinkApi.do`, `confmKey`=JUSO_API_KEY.
- 응답 `admCd`(10자리)의 **앞 5자리 = 시군구코드(LAWD_CD)** = RTMS `sggCd`와 일치.
  → **법정동코드 CSV 없이도 JUSO만으로 sgg_cd 확보 가능** (master 매칭 경로엔 CSV 불필요).
- `emdNm`(면/동) + `liNm`(리)가 분리 반환됨.

## 매칭 키 (경험적 검증 결과)
- master↔RTMS 매칭 키 = `sgg_cd` + `umdNm` + `jibun`.
- **`umdNm`은 공백 제거 후 비교**하고, 면/리 지역은 master를 `emdNm+liNm`으로 만들어야 매칭됨.
  emd만 쓰면(원본 코드 방식) 면/리 지역에서 매칭 누락 → `emdNm+liNm`이 매칭률 더 높음.
- 법정동코드 CSV(`법정동코드 전체자료.csv`, cp949)는 **buildinghub 표제부 보완(마스터에 없는 신축)** 경로에서만 필요.

**Why:** 이 필드명/코드 규칙은 응답을 실제로 찍어봐야만 알 수 있고 정부 문서 표기와 다름. 매칭률 손실의 주원인이 umdNm 형식 차이였음.
