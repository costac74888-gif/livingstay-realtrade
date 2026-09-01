#!/usr/bin/env python3
"""Collect only attributable rural-homestay/hanok RTMS sales.

This is deliberately separate from ``sync_batch``: it neither discovers
buildings nor changes lodging classifications.  RTMS parcel data is only a
safe building identity when its legal-dong and lot number are complete.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import time
from collections import Counter, defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from address_utils import normalize_umd_nm
from db import get_conn
from quota_policy import QuotaExhausted, claim_rtms_request

RTMS_ROOT = "https://apis.data.go.kr/1613000"
API_ENDPOINTS = {
    "SHTrade": f"{RTMS_ROOT}/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
    "RHTrade": f"{RTMS_ROOT}/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "NrgTrade": f"{RTMS_ROOT}/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade",
    "LandTrade": f"{RTMS_ROOT}/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade",
}
STATUS_KEY = "rural_hanok_trade_sync_status"
CHECKPOINT_KEY = "rural_hanok_trade_sync_checkpoint"
LAST_SUCCESS_KEY = "rural_hanok_trade_last_success"
QUOTA_KEY = "rtms_daily_calls"
# Collector-specific lock.  The scheduler separately holds its exclusive
# master/transaction gate; reusing that lock here would deadlock the child.
SYNC_LOCK_ID = 9_183_245


def target_kind(building: dict) -> str | None:
    """Return the permit-backed lodging target; never infer ownership from it."""
    lodging_type = str(building.get("lodging_type") or "")
    if lodging_type == "한옥":
        return "hanok"
    if lodging_type == "농어촌민박":
        return "rural"
    return None


def source_apis_for_use(building: dict) -> tuple[str, ...]:
    """Return RTMS property APIs compatible with the official use wording."""
    text = " ".join(str(building.get(k) or "") for k in
                    ("building_use_type", "building_use_detail"))
    # SHTrade is 단독/다가구, RHTrade is 연립/다세대.  The lodging permit
    # selects the target set only; this routing relies exclusively on the
    # building register's public use fields.
    result = []
    if any(x in text for x in ("단독", "다가구", "한옥")):
        result.append("SHTrade")
    if any(x in text for x in ("숙박", "근린", "상업", "업무")):
        result.append("NrgTrade")
    if any(x in text for x in ("공동주택", "연립", "다세대", "집합")):
        result.append("RHTrade")
    return tuple(dict.fromkeys(result))


def transaction_scope(source_api: str, item: dict) -> str:
    if source_api == "LandTrade":
        return "land_or_site"
    if source_api == "RHTrade" or (item.get("buildingType") or "").strip() == "집합":
        return "unit"
    return "whole_building"


def is_complete_identity(item: dict) -> bool:
    umd, jibun = (item.get("umdNm") or "").strip(), (item.get("jibun") or "").strip()
    return bool(
        umd
        and re.fullmatch(r"(?:산\s*)?\d{1,4}(?:-\d{1,4})?", jibun)
        and not re.search(r"[*Xx?]", umd + jibun)
    )


def normalize_trade(source_api: str, sgg_cd: str, item: dict) -> dict:
    """Normalize the four official XML shapes into the existing schema."""
    scope = transaction_scope(source_api, item)
    amount = re.sub(r"[^0-9]", "", str(item.get("dealAmount") or "0"))
    day = str(item.get("dealDay") or "").zfill(2)
    month = str(item.get("dealMonth") or "").zfill(2)
    return {
        "source_api": source_api, "transaction_scope": scope, "sgg_cd": str(sgg_cd),
        "umd_nm": normalize_umd_nm(item.get("umdNm") or ""),
        "jibun": (item.get("jibun") or "").strip(),
        "address": f"{(item.get('umdNm') or '').strip()} {(item.get('jibun') or '').strip()}".strip(),
        "deal_date": f"{item.get('dealYear') or ''}-{month}-{day}",
        "price": int(amount or 0),
        "area": _number(
            item.get("buildingAr")
            or item.get("excluUseAr")
            or item.get("totalFloorAr")
            or item.get("dealArea")
        ),
        "floor": str(item.get("floor") or item.get("flrNo") or "").strip(),
        "deal_type": (item.get("dealingGbn") or "").strip(),
        "source_building_type": (item.get("buildingType") or "").strip() or None,
        "total_floor_area": _number(item.get("totalFloorAr")),
        "land_area": _number(
            item.get("landAr")
            or item.get("landArea")
            or item.get("plottageAr")
            or (item.get("dealArea") if source_api == "LandTrade" else None)
        ),
    }


def raw_key_for_trade(trade: dict, occurrence: int = 1) -> str:
    """Source and scope are part of identity: APIs can report same parcel sale."""
    return "|".join(str(x) for x in (
        trade["source_api"], trade["transaction_scope"], trade["sgg_cd"],
        trade["umd_nm"], trade["jibun"], trade["deal_date"], trade["price"],
        trade.get("floor") or "", occurrence,
    ))


def match_trade(trade: dict, targets: dict[tuple[str, str, str], list[dict]]):
    """Return (master-or-None, reason); no parcel-only land association."""
    if trade["transaction_scope"] == "land_or_site":
        return None, "land_has_no_public_building_identity"
    if not is_complete_identity({"umdNm": trade["umd_nm"], "jibun": trade["jibun"]}):
        return None, "masked_or_incomplete_identity"
    candidates = targets.get((trade["sgg_cd"], trade["umd_nm"], trade["jibun"]), [])
    if not candidates:
        return None, "no_target_master"
    # A parcel can contain multiple target masters.  Even when only one happens
    # to fit this endpoint, the RTMS row cannot identify which building it is.
    if len(candidates) != 1:
        return None, "ambiguous_exact_master"
    if not target_kind(candidates[0]):
        return None, "no_target_master"
    compatible = [b for b in candidates if trade["source_api"] in source_apis_for_use(b)]
    if not compatible:
        return None, "incompatible_property_kind"
    return compatible[0], None


def _number(value):
    try:
        return float(str(value).replace(",", "")) if value not in (None, "") else None
    except ValueError:
        return None


def _claim_call():
    return claim_rtms_request(QUOTA_KEY)


def fetch_trade(source_api, sgg_cd, ymd, key, page_size=1000):
    """Fetch every XML page, charging the shared RTMS budget per request."""
    rows = []
    page = 1
    while True:
        _claim_call()
        response = requests.get(
            API_ENDPOINTS[source_api],
            params={
                "serviceKey": key,
                "LAWD_CD": sgg_cd,
                "DEAL_YMD": ymd,
                "numOfRows": page_size,
                "pageNo": page,
            },
            timeout=(15, 60),
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        code = (root.findtext(".//resultCode") or "").strip()
        if code not in {"", "0", "00"}:
            message = (root.findtext(".//resultMsg") or "unknown error").strip()
            raise RuntimeError(f"{source_api} API error {code}: {message}")
        page_rows = [
            {child.tag: (child.text or "").strip() for child in item}
            for item in root.iter("item")
        ]
        rows.extend(page_rows)
        total = int((root.findtext(".//totalCount") or len(rows)) or 0)
        if len(rows) >= total:
            return rows
        if not page_rows:
            raise RuntimeError(
                f"{source_api} returned an empty middle page ({len(rows)}/{total})"
            )
        page += 1


def _months(count):
    now = datetime.now()
    return [f"{now.year if now.month-i > 0 else now.year-1}{(now.month-i-1)%12+1:02d}" for i in range(count)]


def sync(months=3, sleep_sec=.5, include_land=False):
    key = os.environ.get("RTMS_SERVICE_KEY") or os.environ.get("DATA_GO_KR_BROKER_API_KEY")
    if not key: raise RuntimeError("RTMS_SERVICE_KEY is required")
    conn = get_conn(); cur = conn.cursor(); counters = Counter(); run_id = secrets.token_hex(8)
    try:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (SYNC_LOCK_ID,))
        if not cur.fetchone()["acquired"]:
            raise RuntimeError("rural/hanok transaction sync is already running")
        cur.execute(
            """
            SELECT key
              FROM app_meta
             WHERE key = ANY(%s)
               AND value::jsonb ->> 'state' = 'running'
               AND updated_at >= NOW() - INTERVAL '2 hours'
             LIMIT 1
            """,
            (["tx_sync_status", "tx_backfill_status"],),
        )
        blocker = cur.fetchone()
        if blocker:
            raise RuntimeError(f"transaction writer is running: {blocker['key']}")
        cur.execute("""SELECT id,building_name,sgg_cd,umd_nm,jibun,building_use_type,building_use_detail,
                       lodging_type,lodging_type_detail FROM master_buildings
                       WHERE sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL""")
        targets = defaultdict(list)
        for row in cur.fetchall():
            row["umd_nm"] = normalize_umd_nm(row["umd_nm"])
            targets[(row["sgg_cd"],row["umd_nm"],row["jibun"])].append(row)
        routes = defaultdict(set)
        for rows in targets.values():
            for row in rows:
                if not target_kind(row):
                    continue
                apis = source_apis_for_use(row)
                if not apis:
                    counters["target_unknown_public_use"] += 1
                for api in apis:
                    routes[api].add(row["sgg_cd"])
        # The public land API has no building identity, so scheduled collection
        # does not spend quota on rows that can never be linked.  A diagnostic
        # run may opt in; even then match_trade always leaves them unlinked.
        all_sgg = sorted({
            row["sgg_cd"]
            for rows in targets.values()
            for row in rows
            if target_kind(row)
        })
        if include_land:
            routes["LandTrade"].update(all_sgg)
        else:
            counters["land_regions_skipped_no_public_building_identity"] = len(all_sgg)
        requested_months = _months(months)
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (STATUS_KEY,))
        prior_status_row = cur.fetchone()
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (CHECKPOINT_KEY,))
        checkpoint_row = cur.fetchone()
        completed_months = set()
        try:
            prior_status = json.loads(prior_status_row["value"]) if prior_status_row else {}
            checkpoint = json.loads(checkpoint_row["value"]) if checkpoint_row else {}
            if (
                prior_status.get("state") == "failed"
                and checkpoint.get("requested_months") == requested_months
            ):
                completed_months = set(checkpoint.get("completed_months") or ())
        except (TypeError, ValueError):
            completed_months = set()
        status = {"run_id":run_id,"state":"running","started_at":datetime.now().isoformat(),"counters":{}}
        cur.execute("INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",
                    (STATUS_KEY,json.dumps(status,ensure_ascii=False))); conn.commit()
        for ymd in requested_months:
            if ymd in completed_months:
                counters["resumed_months_skipped"] += 1
                continue
            occurrence = Counter()
            for api in sorted(routes):
                for sgg in sorted(routes[api]):
                    for item in fetch_trade(api, sgg, ymd, key):
                        counters["fetched"] += 1
                        counters[f"fetched:{api}"] += 1
                        trade = normalize_trade(api, sgg, item)
                        # The existing Nrg collector owns 집합(unit) rows.  This
                        # focused collector only adds Nrg whole-building rows,
                        # avoiding a second raw-key namespace for the same sale.
                        if api == "NrgTrade" and trade["transaction_scope"] == "unit":
                            counters["skipped_existing_nrg_unit_path"] += 1
                            continue
                        occurrence[(api, trade["transaction_scope"], trade["sgg_cd"], trade["umd_nm"], trade["jibun"], trade["deal_date"], trade["price"], trade["floor"])] += 1
                        master, reason = match_trade(trade, targets)
                        counters["matched" if master else "unmatched"] += 1
                        if master:
                            counters[f"matched:{api}"] += 1
                            counters[f"matched_target:{target_kind(master)}"] += 1
                        if reason: counters[f"reason:{reason}"] += 1
                        # Uncertain rows are deliberately not put in the public
                        # transactions table.  Their reason remains in status
                        # counters, so a permit address can never be mistaken
                        # for proof that the property itself was sold.
                        if not master:
                            continue
                        trade["raw_key"] = raw_key_for_trade(trade, occurrence[tuple(trade[k] for k in ("source_api","transaction_scope","sgg_cd","umd_nm","jibun","deal_date","price","floor"))])
                        cur.execute("""INSERT INTO transactions(building_name,address,area,price,deal_date,deal_type,floor,sgg_cd,umd_nm,jibun,lodging_type,lodging_type_detail,match_source,transaction_scope,source_api,source_building_type,total_floor_area,land_area,match_confidence,raw_key)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          ON CONFLICT(raw_key) DO NOTHING""",
                          (master["building_name"] if master else None,trade["address"],trade["area"],trade["price"],trade["deal_date"],trade["deal_type"],trade["floor"],trade["sgg_cd"],trade["umd_nm"],trade["jibun"],master.get("lodging_type") if master else None,master.get("lodging_type_detail") if master else None,"master" if master else "unmatched",trade["transaction_scope"],api,trade["source_building_type"],trade["total_floor_area"],trade["land_area"],"exact" if master else "unmatched",trade["raw_key"]))
                        counters["inserted"] += cur.rowcount
                    time.sleep(sleep_sec)
            # Transaction rows and checkpoint are one atomic monthly apply.
            completed_months.add(ymd)
            cur.execute("INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",
                        (CHECKPOINT_KEY,json.dumps({"last_completed_ymd":ymd,"run_id":run_id,"requested_months":requested_months,"completed_months":sorted(completed_months)},ensure_ascii=False)))
            status["checkpoint"] = ymd
            status["counters"] = dict(counters)
            cur.execute("UPDATE app_meta SET value=%s,updated_at=NOW() WHERE key=%s AND value::jsonb->>'run_id'=%s",
                        (json.dumps(status, ensure_ascii=False), STATUS_KEY, run_id))
            conn.commit()
        status.update(state="done",finished_at=datetime.now().isoformat(),counters=dict(counters),last_success_at=datetime.now().isoformat())
        cur.execute("INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()", (STATUS_KEY,json.dumps(status,ensure_ascii=False)))
        cur.execute("INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()", (LAST_SUCCESS_KEY,json.dumps(status,ensure_ascii=False))); conn.commit()
        cur.execute("DELETE FROM app_meta WHERE key=%s", (CHECKPOINT_KEY,))
        conn.commit()
        return dict(counters)
    except Exception as exc:
        conn.rollback()
        failed = {
            "run_id": run_id,
            "state": "failed",
            "finished_at": datetime.now().isoformat(),
            "counters": dict(counters),
            "error": str(exc)[:300],
            "retryable": True,
        }
        try:
            cur.execute(
                """INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
                   ON CONFLICT(key) DO UPDATE
                   SET value=EXCLUDED.value,updated_at=NOW()""",
                (STATUS_KEY, json.dumps(failed, ensure_ascii=False)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_ID,)); conn.commit()
        except Exception: pass
        cur.close(); conn.close()


if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--months",type=int,default=3); p.add_argument("--sleep",type=float,default=.5)
    p.add_argument("--include-land", action="store_true",
                   help="진단용: 건물 식별자가 없어 자동 연결하지 않는 토지 응답도 조회")
    args=p.parse_args(); print(json.dumps(sync(args.months,args.sleep,args.include_land),ensure_ascii=False))