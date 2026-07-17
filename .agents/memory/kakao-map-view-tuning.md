---
name: Kakao map initial-view tuning without live SDK
description: How to tune map center/level visually when the headless screenshot browser can't load the Kakao SDK
---
The headless screenshot browser blocks the external Kakao SDK script (dapi.kakao.com script tag fires onerror; curl from shell returns 200), so live-map screenshots are impossible in dev preview.

**How to apply:** Build a temp self-contained static HTML that draws the South Korea coastline (southkorea-maps provinces GeoJSON, includes Jeju) on a canvas using the Kakao scale approximation **1px ≈ 2^(level-3) meters** (equirectangular: m/lng = 111320·cos(lat), m/lat = 110540). Validated: PC 36.35/126.9 level 12 reproduces the real "속초~완도" fit. Add reference markers (속초 128.5918/38.207, 제주 남단 126.27/33.115), take screenshots at candidate values, then delete the temp file.

**Why:** Sokcho~Jeju span ≈ 566 km; level 13 shows ~605 m/px·height. Level 12 clips Jeju on mobile; level 13 fits even at map height ~604px (small phones). Mobile defaults chosen: lat 35.8, lng 127.6, level 13 (mobile has no side panel, so true center lng; lat slightly north to clear the top search toggle).
