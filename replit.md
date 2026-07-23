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
- 파트너 노출 토글: agents/operators/loan_consultants에 `is_visible`(기본 TRUE). 각 대시보드에서 노출중지/재개 (`PUT /api/{agent|operator|loan-consultant}/visibility`). FALSE면 B화면 카드·/api/loan-consultants 목록에서 숨김 + 매물의뢰 라우팅(전속/지역) 제외(하우스 폴백은 항상 배정).
- 대출상담사 계정: 승인 시 임시비밀번호 생성+SMS 안내(로그인 ID=이메일), 로그인 `/loan-consultant/login` → `POST /api/loan-consultant/login`(approved만), 대시보드 `/loan-consultant/dashboard`(프로필/비밀번호/노출 토글).
- 중개사 계정: 신청 승인 시 subdomain_slug(전화번호 기반)+임시비밀번호 발급, 알리고 SMS 안내(`sms_util.py`, ALIGO_API_KEY/ALIGO_USER_ID/ALIGO_SENDER). 로그인 `/agent/login` → `POST /api/agent/login`(approved만), `require_agent`, `PUT /api/agent/password`.
- 숙박업 영업신고 데이터: 행안부 숙박업 조회서비스(`STORE_INFO_SERVICE_KEY`) → `sync_lodgings.py`(페이지당 실제 100행, 일일 캡 8,000호출, app_meta 체크포인트로 이어받기)로 `lodging_registry` 수집(위생업태 '숙박업(생활)'만). 매칭은 `addr_norm.py` 도로명 prefix 정규화(1차, lodging_registry.road_norm) → 0건이면 지번 정규화 키(2차, jibun_norm, `get_building_jibun_key`: 건물 jibun_address 우선·지번형 road_address 폴백)로 매칭. B화면 행정 카드(신고율=객실수합/units, 영업 중 신고업소 목록, 등록 운영업체 최상단), 관리자 `/admin`에 동기화 버튼+"미등록 위탁운영 후보"(엑셀, /operators?company= 링크복사).
- 건축HUB 전국 건물 발견: `sync_brhub.py`(표제부 getBrTitleInfo 전수 스캔, bjdong_codes.json 20,276개 법정동 순회, app_meta 'brhub_progress' 체크포인트, 일일캡 8,000호출, source='brhub_bulk', 집합+숙박 필터 후 생활/호텔/콘도 분류·판정불가는 lodging_type NULL) → 미분류는 `reclassify_brhub.py`(층별개요 2차 판정, 영구 판정불가는 detail에 '[재분류불가]' 마커). 주의: 건축HUB는 2026 행정개편 신코드(전남광주 12*)를 몰라 구코드(29*/46*)로 치환 조회(bjdong_codes.json에 반영됨). 실행: `BRHUB Sync` 워크플로우. **복합용도 1차 게이트(2026-07-22)**: 주용도(mainPurpsCdNm)에 숙박/호텔/콘도가 없으면(주용도 공백은 '생활숙박' 명시 시만 통과) `lodging_type='mixed_use_excluded'` + detail '[복합용도-자동제외] '+원문 — 자동분류·화면노출(지도/건물마스터 목록/신고율 통계) 전부 제외, DB에는 보존. 수동 복원은 DB에서 lodging_type을 실제 값으로 직접 갱신. reclassify_brhub.py는 법정동코드 조회에 bjdong_codes.json 폴백(구코드 저장분 대응).
- 대출상담사 건물 연결(2026-07-22): `loan_consultant_buildings`(agent_buildings 동일 패턴). B화면 금융 카드는 건물 연결 상담사만 최대 3명 표시(main.js `renderBuildingLoanConsultants`), 없으면 "이 건물에 대출상담사로 신청하기" 모집 카드(`/apply/loan?building_id=`). 신청서 preferred_building_id 수용 → 승인 시 자동 담당건물 등록. 로고는 `/api/partners/loan-consultant-logo/<id>` 프록시(외부 URL만 redirect). 전역 `/loan-partners`·`/api/loan-consultants`는 유지. dev DB에 아라트라움 아리스타(id 2858) 샘플 파트너(중개3·위탁3·청소3·대출3, SAMPLE-* 번호) 있음 — 확인 후 삭제 예정.
- 파트너 정보수정 재승인(2026-07-22): 등록번호류(agents reg/biz, operators biz, LC license/biz) 변경 시 `_reapply_if_license_changed`가 status='pending'+admin_memo '[본인수정]…' 전환(재승인 전 로그인·노출 중단). 회원관리 목록에 pending 파트너 노출, "정보변경 재검토" 배지+인라인 재승인(`POST /api/admin/members/<type>/<id>/re-approve`). 대시보드 3종 프로필 모달에서 명칭/대표자/이메일/등록번호/로고 수정 가능. 신청서(중개사·운영업체) 서류 첨부는 드래그앤드롭 지원(`static/js/doc_dropzone.js`).
- 관리자 실거래 동기화: `/admin` "실거래 동기화" 버튼 → `POST /api/admin/sync-transactions`가 `sync_runner.py`를 독립 프로세스로 실행(`sync_batch.py --master-only`), 상태는 `app_meta('tx_sync_status')` + `GET /api/admin/sync-status`. 중복 실행/30분 재실행 제한은 DB에서 전역 강제.
- 관리자 "데이터 동기화" 통합 페이지(`/admin` datasync 메뉴): ①건물수집(건축HUB) ②좌표 ③건축정보 ④실거래 ⑤백필 재시도 ⑥중개업소 ⑦숙박업 카드 통합. 기존 geocode/txsync 메뉴 삭제, 중개업소/숙박업 페이지에는 최근 동기화 한 줄만 표시(loadLastSyncLine). **(2026-07-22) ②좌표·③건축정보는 실시간 API 러너로 전환** — data/*.json 주입 방식 완전 제거. `POST /api/admin/geocode-buildings`(6/hour, `geocode_buildings.py --status-key geocode_sync_status`, lat NULL만 카카오 지오코딩) + `GET /api/admin/geocode-status`, `POST /api/admin/backfill-title-info`(6/hour, `backfill_title_info.py --status-key title_info_sync_status`, 미백필만 건축HUB 표제부 조회) + `GET /api/admin/title-info-status` — 실거래와 동일한 DB 잠금+run_id 펜싱+하트비트, done 쿨다운 5분. 페이지 상단 배너: `GET /api/admin/datasync-overview`(좌표/표제부 대기 건수 + 각 동기화 app_meta updated_at이 워커 부팅시각보다 오래되면 노란 경고·클릭 시 해당 섹션 스크롤, 모두 최신이면 초록). 주의: 건축HUB 표제부는 건물수집과 일일쿼터 공유 — 쿼터 소진 시 오류(429)로 끝나며 다음날 재실행. 건축HUB 버튼: `POST /api/admin/sync-brhub`(2/hour, DB 잠금+30분 재실행 제한, `sync_brhub.py --status-key brhub_sync_status` detached 실행, run_id 펜싱+30초 하트비트) + `GET /api/admin/brhub-sync-status`. 주의: `BRHUB Sync` 워크플로우 실행은 상태키를 안 쓰므로 버튼 실행과 동시에 돌리면 중복 수집 가능 — 둘 중 하나만 사용. **⑧ 준공전 건물수집(인허가, 2026-07-23)**: `POST /api/admin/sync-permits`(2/hour, brhub와 동일 잠금/러너 패턴, `sync_permits.py --status-key permits_sync_status`) + `GET /api/admin/permits-sync-status`(permit_pipeline 총계/상태별·체크포인트 permits_progress·오늘 호출량). 인허가 API(ArchPmsHubService)는 간헐 500 잦음 — 재시도 3회 후 해당 동 건너뛰고 계속, 체크포인트로 이어받기. ⑧ 다음에 '완공 대기 중' 카드(/api/admin/pending-completion, 완공 전환 버튼).

- **스키마 변경 규칙**: `db.py`의 테이블/컬럼/제약/시드를 바꾸면 반드시 `db.py`의 `SCHEMA_VERSION` 상수를 함께 올려야 함. (부팅 시 app_meta의 schema_version이 같으면 DDL 전체를 건너뛰는 빠른 경로가 있어, 버전을 안 올리면 새 스키마가 DB에 반영되지 않음.)

- **의존성 규칙**: `requirements.txt`는 배포(프로덕션) 전용 — pandas는 넣지 않음(배포 번들 ~150MB 증가·부팅 지연). pandas는 개발환경에만 설치되어 있고 오프라인 스크립트(`load_master.py`, `verify_units.py`, `load_authority_contacts.py`)에서만 사용. 환경 재설치 시 `pip install pandas`로 별도 설치.

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
