# livingstay (생숙 실거래)

전국 생활숙박시설·분양형호텔·콘도 실거래가 조회 서비스. 브랜드: **홈앤스테이 (HOME & STAY)**.

## 프로젝트 개요
- 스택: Flask + PostgreSQL, 프런트는 정적 HTML/CSS/JS (`static/`), 지도는 Kakao Maps JS SDK.
- 데이터: 국토교통부 RTMS 실거래가(매매) + 건축물대장(master_buildings). `sync_batch.py`로 시군구별 배치 수집.
- 배포: https://livingstay-realtrade.replit.app
- 브랜드 컬러: GOLD/BLACK 계열 — brass `#B4863F`(변수 `--brass`), ink `#16202E`.
- 주요 파일: `app.py`(라우트/API), `static/index.html`(메인 지도), `static/building.html`(건물 상세), `static/js/main.js`, `static/css/main.css`, `db.py`(RealDictCursor).

## 실행/검증
- 앱: `Start application` 워크플로우 (gunicorn, 자동 리로드 없음 → `app.py` 수정 시 재시작 필요).
- 테스트: `python tests/smoke_test.py`, `python tests/api_test.py`.

## 사용자 선호 (User preferences)
- 언어: **항상 한국어로 응답** (비개발자 사용자).
- 작업 속도/승인 방식 (2026-07-13부터 적용):
  - 텍스트 문구·CSS 스타일·레이아웃 등 **데이터/로직에 영향 없는 작업**은 체크포인트만 남기고 중간 확인 없이 끝까지 진행 후 결과만 보고.
  - **DB 스키마 변경, 매칭/필터 로직, 결제·가격 등 데이터 정확성에 영향 주는 작업**만 단계별 검증하며 신중히 진행.
  - 여러 작은 수정은 한 번에 몰아서 처리 가능. 단 서로 다른 파일/기능이 섞이면 커밋 메시지에 각각 구분해서 기재.
  - 스크린샷은 **레이아웃이 크게 바뀔 때만** 첨부. 사소한 문구 변경은 텍스트 보고로 충분.
- 체크포인트: 에이전트는 커밋을 직접 만들 수 없음 → 작업 시작 시 "직전 자동 커밋 HEAD가 롤백 지점"임을 사용자에게 안내.
- GitHub push (2026-07-13 업데이트 — 사용자가 직접 push):
  - 에이전트는 **git push를 직접 실행하지 않음**. 작업 완료 시 마지막 줄에 "이제 Git 패널에서 Push 해주세요"라고만 안내.
  - remote: origin = https://github.com/costac74888-gif/livingstay-realtrade (branch: main).
