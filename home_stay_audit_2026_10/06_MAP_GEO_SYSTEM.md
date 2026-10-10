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
