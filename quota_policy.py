"""One place for the public-data daily budgets used by sync runners.

The counters remain in their established ``app_meta`` checkpoint records; this
module intentionally does not introduce a second, disconnected usage counter.
"""

from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

KOREA_TZ = ZoneInfo("Asia/Seoul")
BUILDING_HUB_DAILY_COUNTER_KEY = "building_hub_daily_calls"


def korea_today() -> str:
    """Counter day boundary shared by every quota-aware collector."""
    return datetime.now(KOREA_TZ).strftime("%Y-%m-%d")


class QuotaExhausted(RuntimeError):
    """Raised before an outbound request when a provider hard cap is full."""


def claim_building_hub_request() -> int:
    """Atomically reserve one Building HUB request across registry/permits.

    Legacy per-collector progress counters are deliberately retained; this is
    the provider-wide hard gate immediately before each outbound request.
    """
    from db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    try:
        today = korea_today()
        cap = int(PROVIDER_QUOTAS["building_hub"]["total"])
        fresh = f'{{"date":"{today}","count":1}}'
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET
              value = CASE
                WHEN app_meta.value::jsonb ->> 'date' = %s
                THEN jsonb_build_object('date', %s, 'count',
                  COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) + 1)::text
                ELSE EXCLUDED.value
              END,
              updated_at = NOW()
            WHERE (app_meta.value::jsonb ->> 'date') IS DISTINCT FROM %s
               OR COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) < %s
            RETURNING (value::jsonb ->> 'count')::int AS count
        """, (BUILDING_HUB_DAILY_COUNTER_KEY, fresh, today, today, today, cap))
        row = cur.fetchone()
        conn.commit()
        if not row:
            raise QuotaExhausted(f"Building HUB daily cap ({cap}) reached")
        return int(row["count"])
    finally:
        cur.close()
        conn.close()

# API별 기준 한도의 80%만 정기 동기화에 사용한다. 나머지 20%는
# 실시간 조회·수동 복구·재시도 여유로 남긴다. 공식 한도를 확인하지 못한
# API는 total=None으로 두어 관리자 화면이 임의 숫자를 표시하지 않게 한다.
PROVIDER_QUOTAS = {
    "rtms": {
        "label": "국토부 실거래가 API", "total": 10000, "regular": 8000,
        "realtime": 2000, "manual": 0, "basis": "기준 한도의 80%",
    },
    # 건축물대장·인허가·표제부 보완은 같은 Building HUB 서비스키와
    # 요청단위 하드캡을 공유하므로 하나의 버킷에서 직렬 실행한다.
    "building_hub": {
        "label": "국토부 건축HUB API", "total": 10000, "regular": 8000,
        "realtime": 0, "manual": 2000, "basis": "기준 한도의 80%·서비스키 공유",
    },
    "store_info": {
        "label": "소상공인 상가정보 API", "total": 10000, "regular": 8000,
        "realtime": 1500, "manual": 500, "basis": "기준 한도의 80%",
    },
    "realty_store": {
        "label": "중개업소 상가정보 API", "total": 1000, "regular": 800,
        "realtime": 0, "manual": 200, "basis": "기준 한도의 80%",
    },
    "lodging": {
        "label": "행안부 숙박업 API", "total": 10000, "regular": 8000,
        "realtime": 0, "manual": 2000, "basis": "기준 한도의 80%",
    },
    "camping": {
        "label": "한국관광공사 고캠핑 API", "total": 1000, "regular": 800,
        "realtime": 0, "manual": 200, "basis": "기준 한도의 80%",
    },
    "broker": {
        "label": "전국 공인중개사 표준데이터 API", "total": 1000, "regular": 800,
        "realtime": 0, "manual": 200, "basis": "기준 한도의 80%",
    },
    "rural": {
        "label": "행안부 농어촌민박 API", "total": 5000,
        "regular": 4000, "realtime": 0, "manual": 1000,
        "basis": "공유 1일 10,000회 중 1/2 배정·정기 80%",
    },
    "hanok": {
        "label": "행안부 한옥체험업 API", "total": 5000,
        "regular": 4000, "realtime": 0, "manual": 1000,
        "basis": "공유 1일 10,000회 중 1/2 배정·정기 80%",
    },
    "kakao_building": {
        "label": "카카오 주소검색 API(건물)", "total": None,
        "regular": None, "realtime": 0, "manual": 0,
        "basis": "앱별 쿼터 확인 필요",
    },
    "kakao_broker": {
        "label": "카카오 주소검색 API(중개업소)", "total": None,
        "regular": None, "realtime": 0, "manual": 0,
        "basis": "앱별 쿼터 확인 필요",
    },
}

PROVIDER_COUNTER_KEYS = {
    "building_hub": ("brhub_progress", "brhub_rescan_progress", "permits_progress"),
}

# stage -> provider and existing checkpoint/counter key.  The app status API
# reads exactly these existing records.
STAGE_QUOTAS = {
    "transactions": (("rtms", "rtms_daily_calls", "--unsupported"),),
    "building_registry": (("building_hub", "brhub_progress", "--daily-cap"),),
    "building_permits": (("building_hub", "permits_progress", "--daily-cap"),),
    "building_geocode": (("kakao_building", "geocode_sync_status", "--unsupported"),),
    "title_info": (("building_hub", "building_hub_daily_calls", "--unsupported"),),
    "lodging": (("lodging", "lodging_daily_calls", "--max-calls"),),
    "camping": (("camping", "camping_daily_calls", "--unsupported"),),
    "rural": (("rural", "rural_hanok_daily_calls:rural", "--daily-cap"),),
    "hanok": (("hanok", "rural_hanok_daily_calls:hanok", "--daily-cap"),),
    "brokers": (("broker", "broker_daily_calls", "--max-calls"),),
    "broker_geocode": (("kakao_broker", "geocode_brokers_status", "--unsupported"),),
    "realty": (("realty_store", "realty_stores_progress", "--daily-cap"),),
    "stores": (("store_info", "stores_progress", "--daily-cap"),),
}


def regular_cap(provider: str) -> int:
    value = PROVIDER_QUOTAS[provider]["regular"]
    if value is None:
        raise ValueError(f"{provider} API의 기준 한도가 확인되지 않았습니다.")
    return int(value)


def quota_for_stage(stage: str) -> dict | None:
    policies = quotas_for_stage(stage)
    return policies[0] if policies else None


def quotas_for_stage(stage: str) -> list[dict]:
    specs = STAGE_QUOTAS.get(stage)
    if not specs:
        return []
    result = []
    for provider, counter_key, cli_option in specs:
        policy = dict(PROVIDER_QUOTAS[provider])
        policy.update(provider=provider, counter_key=counter_key, cli_option=cli_option)
        result.append(policy)
    return result


def cap_for_source(policy: dict, source: str) -> int:
    """Manual recovery may consume its reserved tail; normal runs may not."""
    if policy.get("total") is None or policy.get("regular") is None:
        raise ValueError(f"{policy['provider']} API의 기준 한도가 확인되지 않았습니다.")
    if source == "manual":
        return int(policy["total"])
    return int(policy["regular"])


def quota_bucket_for_stage(stage: str) -> str:
    """Return the API/service-key bucket that must not run concurrently."""
    policies = quotas_for_stage(stage)
    return policies[0]["provider"] if policies else stage


def execution_bucket_for_stage(stage: str) -> str:
    """Serialize only stages known to deadlock on shared DB resources."""
    if stage in {
        "transactions",
        "building_registry",
        "building_permits",
        "building_geocode",
        "title_info",
        "realty",
    }:
        return "master-transactions-writer"
    return stage