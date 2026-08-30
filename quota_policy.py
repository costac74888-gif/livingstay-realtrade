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

# A provider's total is deliberately below its published ceiling.  The
# difference is retained for safe request-path/realtime work and operator
# recovery.  Values are passed to the existing collectors as their daily cap.
PROVIDER_QUOTAS = {
    "rtms": {"total": 10000, "regular": 7000, "realtime": 2000, "manual": 0},
    # Registry and permits have incompatible legacy counters.  They share the
    # provider limit, so manual launch is disabled until request-level shared
    # quota claiming is available.
    "building_hub": {"total": 8000, "regular": 7800, "realtime": 0, "manual": 0},
    "store_info": {"total": 10000, "regular": 6000, "realtime": 4000, "manual": 0},
    "realty_store": {"total": 1000, "regular": 300, "realtime": 500, "manual": 200},
    "lodging": {"total": 10000, "regular": 8000, "realtime": 0, "manual": 2000},
    "camping": {"total": 1000, "regular": 800, "realtime": 0, "manual": 0},
    "broker": {"total": 1000, "regular": 900, "realtime": 0, "manual": 100},
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
    "lodging": (("lodging", "lodging_daily_calls", "--max-calls"),
                # include-camping currently has no separate CLI cap; expose
                # its real counter but never pretend manual reserve is used.
                ("camping", "camping_daily_calls", "--unsupported")),
    "brokers": (("broker", "broker_daily_calls", "--max-calls"),),
    "realty": (("realty_store", "realty_stores_progress", "--daily-cap"),),
    "stores": (("store_info", "stores_progress", "--daily-cap"),),
}


def regular_cap(provider: str) -> int:
    return int(PROVIDER_QUOTAS[provider]["regular"])


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
    if source == "manual":
        return int(policy["total"])
    return int(policy["regular"])