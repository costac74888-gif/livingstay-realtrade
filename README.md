# 생숙실거래 — Replit 설치/실행 가이드 (PostgreSQL 버전)

## 1. Replit에서 PostgreSQL 데이터베이스 먼저 생성
왼쪽 메뉴에서 **"Database"** 탭 클릭 → **"Create a database"** → **PostgreSQL** 선택.
생성되면 `DATABASE_URL` 이라는 Secret이 **자동으로** 프로젝트에 등록됩니다. (직접 입력할 필요 없음)

이게 되어 있어야 `db.py`가 정상 동작합니다. (환경변수 `DATABASE_URL`을 그대로 읽어서 접속)

## 2. 그 외 필요한 Secrets 등록
왼쪽 메뉴 🔒 **Secrets** 에 아래 키들을 등록합니다.

| Key | Value | 발급처 |
|---|---|---|
| `RTMS_SERVICE_KEY` | data.go.kr 발급키 (Decoding 키) | data.go.kr |
| `BLD_SERVICE_KEY` | 위와 동일한 키 (같은 계정 키 재사용) | data.go.kr |
| `JUSO_API_KEY` | 주소 API 승인키 | juso.go.kr |

> 현재 `sync_batch.py` / `address_utils.py` 상단에는 이 키들이 상수(플레이스홀더 문자열)로
> 적혀 있습니다. Secrets 등록 후에는 아래처럼 `os.environ`으로 바꿔서 쓰는 걸 권장합니다:
> ```python
> RTMS_SERVICE_KEY = os.environ["RTMS_SERVICE_KEY"]
> ```
> (원하시면 이 부분도 바로 고쳐드릴 수 있습니다 — 말씀해주세요.)

## 3. 법정동코드 CSV 파일 준비
code.go.kr에서 "법정동코드 전체자료" 다운로드 → 프로젝트 루트에 저장
→ `sync_batch.py`의 `BJDONG_CODE_CSV` 경로를 그 파일명으로 맞추기 (키 불필요, 무료 다운로드)

## 4. 설치
Replit Shell에서:
```bash
pip install -r requirements.txt --break-system-packages
```

## 5. 초기 데이터 적재 (최초 1회, Shell에서 실행)
```bash
# 1) DB 테이블 생성
python db.py

# 2) 마스터파일(생숙 현황 1,787건) 적재
python load_master.py "생활숙박시설현황_전국통합_가나다순_최종본20260707_1_.xlsx"

# 3) 최근 3년치 백필 (시간 꽤 걸림 — 57개 시군구 × 36개월 = 약 2,000회 API 호출)
python sync_batch.py --months 36
```

## 6. 서버 실행
```bash
python app.py
```
Replit이 부여한 URL(`https://livingstay-realtrade.replit.app` 등)로 접속하면 화면이 뜹니다.

## 7. 매일 자동 갱신 걸기
Replit **Scheduled Deployments**에 아래 명령을 하루 1회(예: 새벽 6시) 등록:
```bash
python sync_batch.py --months 3
```
최근 3개월만 다시 훑으면 신규/정정 거래를 충분히 잡으면서 API 호출량도 절약됩니다.

## 8. 동작 확인
- `GET /api/health` → 마지막 배치 실행 시각과 적재 건수 확인
- `GET /api/transactions?q=오션마크레지던스` → 검색 결과 확인
- `GET /api/regions` → 지역 탭 집계 확인

## 9. PostgreSQL로 바꾸면서 달라진 점 (참고)
- 로컬 SQLite 파일(`livingstay.db`) 대신 Replit이 관리하는 PostgreSQL을 씁니다.
- **재배포해도 데이터가 유지됩니다.** (SQLite 방식의 가장 큰 리스크였던 부분 해결)
- 쿼리 문법이 `?` → `%s`, `INSERT OR IGNORE` → `ON CONFLICT ... DO NOTHING` 으로 바뀌었습니다.
  (이미 반영 완료, 별도 조치 불필요)

## 10. 실제 서비스 전 꼭 확인할 것
1. `sync_batch.py`의 `fetch_nrg_trade()` 필터 조건(`houseType`/`regstrGbCdNm`/`bldGbCdNm`) —
   실제 RTMS 응답을 한 번 raw로 찍어서 정확한 태그명으로 맞춰야 합니다.
2. `juso.go.kr` API의 무료 호출 한도 확인 — 최초 백필 시 마스터 1,787건을 한 번에 변환하므로
   하루 한도를 넘지 않는지 체크.
3. `--months 36` 백필은 트래픽이 크므로, 개발계정 한도(1만 건/일)에 걸리면 며칠에 나눠 실행.

