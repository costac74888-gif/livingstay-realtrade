# livingstay (생숙 실거래)

전국 생활숙박시설·분양형호텔·콘도 실거래가 조회 서비스. 브랜드: **홈앤스테이 (HOME & STAY)**.

## 프로젝트 개요
- 스택: Flask + PostgreSQL, 프런트는 정적 HTML/CSS/JS (`static/`), 지도는 Kakao Maps JS SDK.
- 데이터: 국토교통부 RTMS 실거래가(매매) + 건축물대장(master_buildings). `sync_batch.py`로 시군구별 배치 수집.
- 배포: https://livingstay-realtrade.replit.app
- 브랜드 컬러: 액센트는 brass `#B4863F`(변수 `--brass`), ink `#16202E`.
- **로고 기본: 화이트 배경 · 검정 글자(B&W on white)**. 상단/모달/법적 페이지 로고 모두 흑백 기준. 골드 로고는 사용하지 않음(`static/home_stay_logo.png`가 흑백 버전, 골드 원본은 `home_stay_logo_gold_backup.png`).
- 주요 파일: `app.py`(라우트/API), `static/index.html`(메인 지도), `static/js/main.js`, `static/css/main.css`, `db.py`(RealDictCursor).
- **주의: `static/building.html`은 레거시(실서비스 미사용)**. 실제 건물상세(B화면)는 `/building/<id>` 진입 시 index의 `main.js`가 그리는 좌측패널 — B화면 작업은 반드시 `main.js`의 `renderBuildingPanel()`/`renderBuildingAgent()` 쪽을 수정해야 반영됨.
- 중개사 계정: 신청 승인 시 subdomain_slug(전화번호 기반)+임시비밀번호 발급, 알리고 SMS 안내(`sms_util.py`, ALIGO_API_KEY/ALIGO_USER_ID/ALIGO_SENDER). 로그인 `/agent/login` → `POST /api/agent/login`(approved만), `require_agent`, `PUT /api/agent/password`.
- 관리자 실거래 동기화: `/admin` "실거래 동기화" 버튼 → `POST /api/admin/sync-transactions`가 `sync_runner.py`를 독립 프로세스로 실행(`sync_batch.py --master-only`), 상태는 `app_meta('tx_sync_status')` + `GET /api/admin/sync-status`. 중복 실행/30분 재실행 제한은 DB에서 전역 강제.

- **스키마 변경 규칙**: `db.py`의 테이블/컬럼/제약/시드를 바꾸면 반드시 `db.py`의 `SCHEMA_VERSION` 상수를 함께 올려야 함. (부팅 시 app_meta의 schema_version이 같으면 DDL 전체를 건너뛰는 빠른 경로가 있어, 버전을 안 올리면 새 스키마가 DB에 반영되지 않음.)

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
