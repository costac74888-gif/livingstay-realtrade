---
name: Kakao map initial-view tuning without live SDK
description: How to tune map center/level visually when the headless screenshot browser can't load the Kakao SDK
---
The headless screenshot browser blocks the external Kakao SDK script (dapi.kakao.com script tag fires onerror; curl from shell returns 200), so live-map screenshots are impossible in dev preview.

**How to apply:** Build a temp self-contained static HTML that draws the South Korea coastline (southkorea-maps provinces GeoJSON, includes Jeju) on a canvas using the Kakao scale approximation **1px ≈ 2^(level-3) meters** (equirectangular: m/lng = 111320·cos(lat), m/lat = 110540). Validated: PC 36.35/126.9 level 12 reproduces the real "속초~완도" fit. Add reference markers (속초 128.5918/38.207, 제주 남단 126.27/33.115), take screenshots at candidate values, then delete the temp file.

**Why:** Sokcho~Jeju span ≈ 566 km; level 13 shows ~605 m/px·height. Level 12 clips Jeju on mobile; level 13 fits even at map height ~604px (small phones). Mobile defaults chosen: lat 35.8, lng 127.6, level 13 (mobile has no side panel, so true center lng; lat slightly north to clear the top search toggle).

동명 검색 결과가 서로 먼 지역에 2곳 이상이면 `setBounds`가 정한 줌을 고정 레벨로 다시 덮어쓰지 않는다.

**Why:** 화성과 구리의 동명 건물 범위를 맞춘 직후 2건 이하라는 이유로 레벨 3을 강제하면, 두 지역의 중간인 판교만 확대되어 검색 위치처럼 보인다.

**How to apply:** 단일 결과만 상세 수준으로 확대하고, 복수 결과는 카카오 `setBounds`가 모든 좌표를 포함하도록 계산한 중심·레벨을 유지한다. 상세 선택 후에는 선택 건물 좌표로 별도 재중심화한다.

복수 건물명 검색은 `setBounds` 맞춤 결과보다 한 단계 더 축소하고, 넓은 줌에서는 검색어가 적용된 시군구 카드를 표시한다.

**Why:** 구리·화성처럼 떨어진 동명 건물은 넓은 줌에서 개별 숫자 마커가 숨겨진다. 범위만 한 단계 축소해도 강제 개별마커 모드라면 화면에는 아무 표시가 남지 않는다.

**How to apply:** 건물명 검색 결과가 2건 이상일 때만 맞춤 레벨에 1을 더하고, 시군구 줌 이상이면 검색어를 유지한 시군구 카드로 전환한다. 단일 결과 확대와 일반 지도 탐색에는 적용하지 않는다.

상세페이지의 `지도위치`로 돌아온 선택 건물은 실거래 유무와 관계없이 실거래 숫자 원형과 같은 34px 크기로 점멸한다. 실거래가 없으면 숫자 없이 빈 원형으로 표시한다.

**Why:** 14px 기본 점을 점멸만 하면 주변 점 사이에서 선택 위치를 알아보기 어렵다. 사용자는 점을 줄이는 것이 아니라 실거래 원형만큼 키우는 의도를 확인했다.

**How to apply:** 선택 상태 CSS가 0건 점과 숫자 배지 모두 34px로 통일하되, 0건에는 숫자를 만들지 않고 기존 건물 유형 색상과 점멸 효과를 유지한다.
