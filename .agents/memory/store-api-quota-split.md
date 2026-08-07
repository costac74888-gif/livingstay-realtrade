---
name: 상가정보 API 한도 분리 (배치 vs 실시간)
description: STORE_INFO_SERVICE_KEY 일일 10,000건을 배치/실시간으로 분리 관리하는 패턴
---

# 상가정보 API 한도 분리

## 규칙
STORE_INFO_SERVICE_KEY는 배치(sync_stores.py)와 실시간(_bg_fetch)이 동일한 일일 10,000건 한도를 공유한다.
배치가 한도를 소진하면 실시간 조회도 막히므로 반드시 분리 카운터로 관리해야 한다.

**분리 기준 (app.py 상수):**
- `_STORE_REALTIME_DAILY_CAP = 4,000` — 실시간 전용 예약 쿼터
- `_STORE_BATCH_DAILY_CAP = 6,000` — 배치 최대 쿼터
- `STORE_DAILY_CALLS_REALTIME_KEY = "store_daily_calls_realtime"` — app_meta 키
- `STORE_DAILY_CALLS_BATCH_KEY = "store_daily_calls_batch"` — app_meta 키

## 원자적 카운터 패턴 (PostgreSQL)
실시간 경로에서 API 호출 직전 카운터를 원자적으로 1 증가시키고 한도 초과 여부를 반환:
```sql
INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
ON CONFLICT (key) DO UPDATE
  SET value = CASE
        WHEN (app_meta.value::jsonb ->> 'date') = %s
        THEN jsonb_set(app_meta.value::jsonb, '{count}',
                       to_jsonb((COALESCE(app_meta.value::jsonb->>'count','0'))::int + 1))
        ELSE %s::jsonb
      END,
      updated_at = NOW()
RETURNING value
```
카운터 형식: `{"date": "YYYY-MM-DD", "count": N}`

## Why
2026-08-07: 배치를 여러 번 실행해 STORE_INFO_SERVICE_KEY 10,000건 소진 →
실시간 조회(건물상세 상가정보 카드)가 완전 차단됨. 실시간은 사용자 노출 핵심 기능이므로
배치보다 우선순위가 높아야 한다.

## How to apply
- `_bg_fetch()`: API 호출 전 `_store_rt_check_and_count()` → over_limit이면 즉시 반환
- `sync_stores.py`: `--daily-cap` 기본값 500 유지(admin UI); 절대 6,000 이상 넘기지 말 것
- DB 오류 시 실시간 카운터 실패 → `over_limit=False` (통과 허용) — DB 장애로 사용자 차단보다 허용 우선
- admin_stores_sync_status(): `batch_calls_today`, `realtime_calls_today` 필드로 두 카운터 모두 노출
