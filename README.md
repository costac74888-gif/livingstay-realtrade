# 생숙실거래 — Replit 설치/실행 가이드

## 1. 파일 배치
이 폴더(`app.py`, `db.py`, `load_master.py`, `sync_batch.py`, `address_utils.py`,
`requirements.txt`, `static/index.html`)를 Replit 프로젝트 루트에 그대로 올립니다.

## 2. 사전 준비물 (반드시 필요)
| 항목 | 발급처 | 넣을 곳 |
|---|---|---|
| RTMS 상업업무용 실거래가 서비스키 | data.go.kr | `sync_batch.py` → `RTMS_SERVICE_KEY` |
| 건축HUB_건축물대장정보서비스 키 | data.go.kr | `sync_batch.py` → `BLD_SERVICE_KEY` |
| 도로명주소 API 승인키 | juso.go.kr | `address_utils.py` → `JUSO_API_KEY` |
| 법정동코드 전체자료 CSV | code.go.kr (무료, 키 불필요) | 프로젝트 루트에 저장, `sync_batch.py` → `BJDONG_CODE_CSV` 경로 지정 |

Replit에서는 이 키들을 코드에 직접 쓰지 말고 **Secrets(환경변수)** 에 등록한 뒤
`os.environ["RTMS_SERVICE_KEY"]` 형태로 불러오는 걸 권장합니다. (지금 코드는 우선 빠르게
동작 확인할 수 있도록 상수로 넣게 되어 있습니다 — 실제 배포 전에 Secrets로 옮기세요.)

## 3. 설치
```bash
pip install -r requirements.txt --break-system-packages
```

## 4. 초기 데이터 적재 (최초 1회)
```bash
# 1) 마스터파일(생숙 현황 1,787건) 적재
python load_master.py "생활숙박시설현황_전국통합_가나다순_최종본20260707_1_.xlsx"

# 2) 최근 3년치 백필 (시간 꽤 걸림 — 57개 시군구 × 36개월 = 약 2,000회 API 호출)
python sync_batch.py --months 36
```

## 5. 서버 실행
```bash
python app.py
```
Replit이 붙여주는 URL로 접속하면 `static/index.html`이 뜹니다.

## 6. 매일 자동 갱신 걸기
Replit **Scheduled Deployments**(또는 자체 cron)에 아래 명령을 하루 1회(예: 새벽 6시) 등록:
```bash
python sync_batch.py --months 3
```
최근 3개월만 다시 훑으면 신규/정정 거래를 충분히 잡으면서 API 호출량도 절약됩니다.

## 7. 동작 확인
- `GET /api/health` → 마지막 배치 실행 시각과 적재 건수 확인
- `GET /api/transactions?q=오션마크레지던스` → 검색 결과 확인
- `GET /api/regions` → 지역 탭 집계 확인

## 8. 실제 서비스 전 꼭 확인할 것
1. `sync_batch.py`의 `fetch_nrg_trade()` 필터 조건(`houseType`/`regstrGbCdNm`/`bldGbCdNm`) —
   실제 RTMS 응답을 한 번 raw로 찍어서 정확한 태그명으로 맞춰야 합니다.
2. `juso.go.kr` API의 무료 호출 한도 확인 — 최초 백필 시 마스터 1,787건을 한 번에 변환하므로
   하루 한도를 넘지 않는지 체크.
3. `--months 36` 백필은 트래픽이 크므로, 개발계정 한도(1만 건/일)에 걸리면 며칠에 나눠 실행.
