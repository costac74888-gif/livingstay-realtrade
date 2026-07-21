---
name: 소상공인 상가업소 API (B553077 sdsc2)
description: 건물 단위 상가업소 조회의 키/포맷 함정 — mgmBldrgstPk 불일치, json 403, PNU 사용
---

- storeListInBuilding의 key(건물관리번호)는 도로명주소 25자리 bldMngNo(PNU 19 + 일련 6). 건축HUB 표제부의 mgmBldrgstPk와 **다른 번호** — 넣으면 NODATA(03). 일련 6자리는 자체 산출 불가.
- **How to apply:** 건물 단위 조회는 storeListInPnu(key=PNU 19자리: sgg_cd5+법정동5+토지구분1(대지=1,산=2)+본번4+부번4) 사용. 우리 데이터(sgg_cd/umd_nm/jibun+BjdongMap)로 산출 가능.
- 이 API는 `type=json` 지정 시 게이트웨이가 403 Forbidden(같은 키로 XML은 200). storeListInRadius도 403. 반드시 XML 파싱.
- 강원도는 신코드(51xxx)로 조회해야 함(42xxx는 NODATA). resultCode 03=NODATA_ERROR.
- 헬퍼: store_info_util.py (실패 시 빈 리스트 — 화면은 "준비 중" 유지).

## 전국공인중개사사무소표준데이터 (data.go.kr)
- 신규 발급 키는 resultCode=30(SERVICE KEY IS NOT REGISTERED)이 최대 ~1시간 지속될 수 있음 — 코드 문제 아님, 대기 후 재시도.
- 실제 응답 필드: medOfficeNm, estblRegNo, estblRegYmd, lctnRoadNmAddr, lctnLotnoAddr, telno, hmpgAddr, rprsvNm, latitude, longitude, crtrYmd.
- 전체 약 6.8만건 = 68회 호출(1,000행/호출)로 하루 안에 전량 수집 가능(일일 한도 1,000회). 좌표(lat/lng)는 약 40%만 존재.
