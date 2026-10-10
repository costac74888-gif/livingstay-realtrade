# Work → Replit: 사용자 Phase 8 — 검색/Filter/Super Map

Phase 7 전체 30개·내부 검토·immutable checkpoint·개발 원격 commit/tag·main
불변을 확인한 뒤 시작한다. 원문 8~12절과 Native S11~S14의 actual 검사를 연결한다.

PC 좌측 목록/유형별 선택 패널, 우측 지도. 1행 위치/입퇴실/검색, 2행 기간총액/
방 수/유형/면적/인원/옵션/즉시입주/할인 필터를 유지·보강한다. 원래 가격 엔진의
실제 기간 총액만 비교하고 주소·건물명·사진 등 제한공개 정보를 검색 경로로도
유출하지 않는다. 공개 요약에 명시적으로 동의한 운영자 입력의 방/면적/인원/옵션
등만 공개 filter에 사용하며 자동 건물정보를 승격하지 않는다.

단기임대 기본 ON; 우측 세로 매매/영업권양도/공매 토글은 독립이다. 다른 종류
선택/토글이 나머지 ON 레이어를 끄거나 기존 통계 총계를 바꾸지 않는다.
가격 pin/bubble·매매·영업권·원래 공매 네모 스타일을 구분하고 동일좌표에는
고정 pixel slot/count 목록을 사용한다. 좌표 자체를 바꾸지 않는다.
좌측 패널의 종류+ID를 묶고 늦은 검색/bounds/상세 응답·빠른 선택·OFF·뒤로가기가
다른 종류의 정보를 덮어쓰지 않도록 generation/abort를 검증한다.

현재 원래 위치보호는 app.py의 _limited_whole_listing_approx_location:
동 좌표 평균은 5개 이상·소수 3자리, 시군구 fallback은 10개 이상·소수 2자리다.
제한공개는 이 신뢰할 수 있는 집계 기준과 약 500m 범위를 표시하고 정확 좌표/
주소/건물명/사진/자동 checklist를 출력하지 않는다. 안전한 집계가 없으면 marker를
숨기되 목록과 ‘위치 비공개’ 상태를 유지한다. 실제 위치 fallback은 없다.

기존 공개 매매/영업권/공매 조회를 trusted read adapter로 재사용하고 native 데이터/
통계·숙박 총계를 변경하지 않는다. owned fixture는 합성 원장·SDK double을 실제 SQL/
HTTP/DOM으로 검증하되 실제 카카오 SDK나 실제 공개 데이터 연동 완료로 주장하지 않는다.
실제 SDK·live read adapter는 별도 host composition에서 연결한다. 운영 승인 Gate는 닫힌다.
