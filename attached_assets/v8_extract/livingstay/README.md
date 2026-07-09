# 생숙실거래 — 검증 통일 + 오염데이터 정리 + 건물 추가 요청 기능

## ⚠️ Replit Agent에게 그대로 전달할 프롬프트

```
첨부한 파일들을 지금 프로젝트와 비교해서 반영해줘.

배경: sync_batch.py의 "건축HUB 보완" 경로가 검증 없이 이름만 붙이고 있어서,
휴양콘도미니엄인 '한화호텔앤드리조트/평창'(실제로는 휘닉스파크레드앤핑크콘도미니엄)이
생숙으로 잘못 사이트에 노출된 걸 건축물대장 원본으로 확인했어. discover_new_buildings.py와
verify_units.py는 이미 building_registry.py 공용 모듈로 정리해뒀다고 했는데,
sync_batch.py만 검증 없이 예전 방식 그대로였던 거야.

1. building_registry.py — 이미 있는 우리 프로젝트의 버전과 diff 비교해줘.
   함수 시그니처(is_living_stay가 (판정, 건물정보, 사유) 튜플을 반환)가 같은지 확인하고,
   다르면 우리 기존 버전(이미 검증된 로직)을 기준으로 맞춰줘.

2. sync_batch.py — "건축HUB 보완" 경로를 building_registry.is_living_stay()로
   검증하도록 고쳤어. 검증 통과 못 하면(호텔/콘도 등) 그 거래는 아예 저장 안 하고
   건너뛰도록 바뀌었으니 반영해줘. 통과하면 master_buildings에 자동 편입돼서
   (source='sync_verified', verified_at=NOW()) 다음부턴 'master' 경로로 바로 매칭돼.

3. db.py — master_buildings에 verified_at 컬럼과 building_requests 테이블 추가.
   ALTER TABLE IF NOT EXISTS라 기존 데이터 안전해.

4. app.py — POST /api/submit-building 신규 엔드포인트. 사용자가 주소 제출하면
   실시간으로 is_living_stay() 검증해서 통과시 즉시 마스터 편입, 실패시 사유 반환.

5. static/index.html — 화면의 "건축물대장 보완" 배지를 제거했어(내부 이력일 뿐
   사용자에게 불필요). 대신 "+ 내 건물 추가 요청" 버튼과 모달을 추가했어.

6. cleanup_unverified.py (신규) — 기존에 검증 없이 들어간 건물들을 재검증해서
   생숙 아닌 것(한화리조트 등)을 제거하는 1회성 스크립트.

반영 후 순서:
  python db.py                          # 컬럼/테이블 추가
  python cleanup_unverified.py --dry-run   # 뭐가 제거될지 먼저 확인
  python cleanup_unverified.py             # 문제없으면 실제 정리 실행
  python app.py

cleanup_unverified.py --dry-run 결과에서 "한화호텔앤드리조트/평창"이
제거 대상으로 뜨는지 확인하고 알려줘.
```

## 이번에 정리한 개념 — "출처 라벨" 대신 "검증 시점"

- `source` 컬럼(원본/발굴/구제/사용자제출 등)은 내부 이력용으로 유지하되, **화면엔 노출 안 함**
- 대신 `verified_at`(검증 시각)을 기준으로 통일 — 화면에 보이는 모든 건물은
  "언제 검증됐든 상관없이 지금 시점에 생활숙박시설로 확인된 것"이라는 동일한 자격을 가짐
- 마스터파일은 더 이상 "한 번 고정된 원본"이 아니라, **discover/verify/sync/사용자제출 네 경로로
  계속 검증되며 자라나는 데이터**로 개념이 바뀜 — 필요하시면 이걸 "신마스터데이터"라고
  안내 문구에 그대로 쓰셔도 됩니다.

## 신규 기능 — 내 건물 추가 요청

검색창 아래 **"+ 내 건물 추가 요청"** 버튼 → 도로명주소 입력 → 실시간으로
`building_registry.is_living_stay()` 검증 → 통과하면 즉시 마스터에 반영되고
다음 갱신부터 그 건물의 실거래가 표시됩니다. 실패하면 사유(예: "휴양콘도미니엄으로 확인됨")를
바로 안내합니다. 모든 요청 이력은 `building_requests` 테이블에 남아 나중에 검토 가능합니다.

## 데이터 정리 우선순위

1. `python db.py` (컬럼 추가)
2. `python cleanup_unverified.py --dry-run` — 제거될 목록 먼저 확인
3. 문제없으면 `python cleanup_unverified.py` 실제 실행
4. 이후 `sync_batch.py`, `discover_new_buildings.py`가 도는 한 같은 오염은 재발하지 않음
   (둘 다 이제 검증 게이트를 통과해야만 저장됨)


```
첨부한 파일들은 Claude가 만든 업데이트본이야. 아래 순서로 진행해줘.

1. 각 파일을 지금 프로젝트의 같은 파일과 diff 비교해줘.
2. 이미 우리가 고쳐둔 게 있으면 그건 유지해줘 (os.environ 읽기, buildingType/buildingUse
   필드명, JUSO 괄호 제거, verify_units의 청크+증분커밋 구조, /api/health ISO 날짜 처리,
   관심단지 NULL 매칭 버그 수정 등).
3. 이번에 새로 추가/변경된 것들을 반영해줘:
   - transactions 테이블에 floor(층) 컬럼 추가 (ALTER TABLE IF NOT EXISTS)
   - sync_batch.py / discover_new_buildings.py가 층 정보도 같이 저장하도록 변경
     (RTMS 응답의 층 필드명이 정말 'floor'인지 raw로 한 번 확인 필요 — 다를 수 있음)
   - /api/transactions, /api/favorites 응답에 floor 포함
   - /api/years: 실제 데이터 연도 + 항상 최근 3년(현재-2~현재)을 합쳐서 반환,
     과거 연도가 데이터 존재하는 한 목록에서 안 사라지게 함
   - static/index.html: 표에 '층' 컬럼 추가, 거래금액 표시를 '(만원)' 헤더 + 3자리 콤마
     숫자로 변경(예: 15,000), 실제 로고 이미지(static/logo.png)로 교체,
     관심단지 저장 개수 제한(일반 5개 / ?admin=1 파라미터 시 50개) + 관심단지 칩 표시 추가
4. python db.py 실행해서 새 컬럼 적용 + 기존 데이터(마스터/실거래) 안 없어졌는지 확인해줘.
5. 끝나면 요약해줘.
```

## 1. 이번 업데이트 요약

| 항목 | 내용 |
|---|---|
| 로고 | `static/logo.png`(실제 홈스퀘어 로고 파일)로 교체, 헤더에 `<img>`로 표시 |
| 층 컬럼 | 표에 "층" 컬럼 추가(면적과 거래금액 사이), 숫자만 표시 |
| 거래금액 표기 | 헤더에 "(만원)" 단위 표기 + 값은 3자리 콤마 숫자(예: 15,000) — 억/만원 혼합 표기 제거 |
| 검색기간 | 실제 데이터 존재 연도 + 항상 최근 3년 기본 포함, 과거 연도가 목록에서 사라지지 않음. 미래 연도는 데이터 생기면 자동 추가 |
| 관심단지 | 검색창 아래 칩(★건물명)으로 상시 표시, 개별 X로 삭제 가능. 기본 5개 제한, `?admin=1`로 접속 시 50개까지 |

## 2. 관심단지 개수 제한 관련 참고

지금은 로그인 계정이 없어서, "일반 사용자 5개 / 관리자 50개"를 **URL 파라미터(`?admin=1`)로 임시 구분**했습니다.
예) `https://livingstay-realtrade.replit.app/?admin=1`로 접속하면 50개까지 저장 가능.
나중에 실제 로그인을 붙이게 되면 이 부분을 서버 쪽 권한 체크로 바꾸는 게 안전합니다
(지금 방식은 URL만 알면 누구나 관리자 모드로 접속 가능한 임시 방편입니다).

## 3. 층(floor) 필드 관련 주의

RTMS 응답에서 층 정보 필드명이 정확히 `floor`인지 아직 raw로 확인 안 됐습니다.
지금까지 계속 그래왔듯(`houseType`→`buildingType` 사례) 필드명이 다를 수 있으니,
Replit Agent한테 실제 응답 한 번 찍어서 정확한 필드명으로 맞춰달라고 요청하세요.

## 4. 실행 순서

```bash
pip install -r requirements.txt --break-system-packages
python db.py                    # 컬럼/제약 보강 (기존 데이터 보존)
python migrate_regions.py       # 이미 했으면 자동 스킵
python app.py
```

## 5. 전국 발굴 배치 (준비물 필요)

`discover_new_buildings.py`는 전국 시군구 목록을 얻기 위해
**법정동코드 전체자료.csv**(code.go.kr, 무료, 키 불필요)가 프로젝트 루트에 있어야 합니다.

```bash
python discover_new_buildings.py --list-only     # 전국 시군구 개수 확인
python discover_new_buildings.py --region-offset 0  --region-limit 30 --months 3
python discover_new_buildings.py --region-offset 30 --region-limit 30 --months 3
# ... 이하 반복
```
중간에 끊겨도 `discover_progress` 테이블에 처리 이력이 남아 재실행 시 이어서 진행됩니다.

## 6. Secrets
| Key | 발급처 |
|---|---|
| `RTMS_SERVICE_KEY` | data.go.kr |
| `BLD_SERVICE_KEY` | data.go.kr (동일 키) |
| `JUSO_API_KEY` | juso.go.kr |




