#!/usr/bin/env python3
"""행안부 농어촌민박업·한옥체험업 공식 API를 신고 및 건물마스터에 반영한다."""

import argparse
import json
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from requests.exceptions import ConnectTimeout

import import_airbnb_lodging as common
from db import get_conn
from quota_policy import PROVIDER_QUOTAS, QuotaExhausted, korea_today
from lodging_classification import (
    ACTIVE_STATUS,
    choose_primary_lodging_type,
    classify_building_use,
    should_protect_from_active_permit_reclassification,
)
from stats_cache import mark_master_stats_invalidated_in_transaction


SERVICE_KEY_ENV = "LODGING_SERVICE_KEY"
SERVICE_KEY_ENV2 = "DATA_GO_KR_BROKER_API_KEY"
API_ROOT = "https://apis.data.go.kr/1741000"
PAGE_SIZE = 1000
REPORT_PATH = Path("reports/rural_hanok_classification_conflicts.json")
LODGING_SYNC_LOCK_ID = 918273
RURAL_HANOK_SOURCE_LOCK_BASE = 9_183_000
STATUS_META_KEY = "rural_hanok_sync_status"
LAST_SYNC_META_KEY = "rural_hanok_last_sync"
HEARTBEAT_SEC = 30


class EndpointUnavailableError(RuntimeError):
    """API endpoint connection failure that should not be retried."""

SOURCES = {
    "rural": {
        "quota_provider": "rural",
        "endpoint": "rural_homestays",
        "prefix": "RURAL",
        "hygiene_type": "농어촌민박업",
        "lodging_type": "농어촌민박",
        "master_source": "rural_lodging_import",
        "room_field": "GSRM_CNT",
        "building_use_field": "BLDG_SHP_SE_NM",
        "facility_area_fields": ("HSAR", "LCTN_AREA"),
        "region_field": "USG_RGN",
    },
    "hanok": {
        "quota_provider": "hanok",
        "endpoint": "hanok_experience",
        "prefix": "HANOK",
        "hygiene_type": "한옥체험업",
        "lodging_type": "한옥",
        "master_source": "hanok_experience_import",
        "room_field": "GSRM_CNT",
        "building_use_field": "BLDG_USG_NM",
        "facility_area_fields": ("FCLT_SCL", "FCAR", "ARCH_TFA"),
        "region_field": "RGN_SE_NM",
    },
}


def _source_lock_ids(source_names):
    return [
        RURAL_HANOK_SOURCE_LOCK_BASE + list(SOURCES).index(source_name)
        for source_name in sorted(source_names)
    ]


def _first_value(item, fields):
    for field in fields:
        value = common._text(item.get(field))
        if value is not None:
            return value
    return None


def _permit_number(config, authority_code, source_permit_number):
    authority = common._identity_text(authority_code)
    permit = common._identity_text(source_permit_number)
    if not authority or not permit:
        return None
    return f"{config['prefix']}:{authority}:{permit}"


def parse_item(item, config):
    """API 응답 한 건을 lodging_registry 공통 형태로 바꾼다."""
    permit_number = _permit_number(
        config,
        item.get("OPN_ATMY_GRP_CD"),
        item.get("MNG_NO"),
    )
    biz_name = common._text(item.get("BPLC_NM"))
    if not permit_number or not biz_name:
        return None
    road_address = common._text(item.get("ROAD_NM_ADDR"))
    jibun_address = common._text(item.get("LOTNO_ADDR"))
    return {
        "permit_number": permit_number,
        "permit_date": common._date_text(item.get("LCPMT_YMD")),
        "biz_name": biz_name,
        "room_count": common._integer(item.get(config["room_field"])),
        "bld_use_nm": common._text(item.get(config["building_use_field"])),
        "source_updated_at": common._date_text(
            item.get("DAT_UPDT_PNT") or item.get("LAST_MDFCN_PNT")
        ),
        "road_address": road_address,
        "hygiene_type": config["hygiene_type"],
        "biz_status_name": common._text(item.get("SALS_STTS_NM")),
        "biz_status_detail": common._text(item.get("DTL_SALS_STTS_NM")),
        "facility_area": common._decimal(
            _first_value(item, config["facility_area_fields"])
        ),
        "phone": common._phone(item.get("TELNO")),
        "jibun_address": jibun_address,
        "region_name": common._text(item.get(config["region_field"])),
        "road_norm": common.normalize_road_prefix(road_address),
        "jibun_norm": common.normalize_jibun_prefix(jibun_address),
        "biz_name_norm": common.normalize_name(biz_name),
        "lodging_type": config["lodging_type"],
        "master_source": config["master_source"],
    }


def _claim_api_call(provider, daily_cap):
    counter_key = f"rural_hanok_daily_calls:{provider}"
    today = korea_today()
    cap = int(daily_cap or PROVIDER_QUOTAS[provider]["total"])
    conn = get_conn()
    cur = conn.cursor()
    try:
        fresh = json.dumps({"date": today, "count": 1})
        cur.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET
              value = CASE
                WHEN app_meta.value::jsonb ->> 'date' = %s
                THEN jsonb_build_object(
                  'date', %s,
                  'count', COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) + 1
                )::text
                ELSE EXCLUDED.value
              END,
              updated_at = NOW()
            WHERE (app_meta.value::jsonb ->> 'date') IS DISTINCT FROM %s
               OR COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) < %s
            RETURNING (value::jsonb ->> 'count')::int AS count
            """,
            (counter_key, fresh, today, today, today, cap),
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            raise QuotaExhausted(
                f"{provider} API 일일 배정 한도({cap})에 도달했습니다."
            )
        return int(row["count"])
    finally:
        cur.close()
        conn.close()


def _fetch_page(config, key, page, page_size=PAGE_SIZE, daily_cap=None):
    _claim_api_call(config["quota_provider"], daily_cap)
    endpoint_url = f"{API_ROOT}/{config['endpoint']}/info"
    try:
        response = requests.get(
            endpoint_url,
            params={
                "serviceKey": key,
                "pageNo": str(page),
                "numOfRows": str(page_size),
                "type": "json",
            },
            timeout=(15, 60),
        )
    except ConnectTimeout as exc:
        raise EndpointUnavailableError(
            f"[{config['endpoint']}] API 엔드포인트가 응답하지 않습니다. "
            f"URL이 올바른지 확인하세요: {endpoint_url}\n"
            "농어촌민박업·한옥체험업은 localdata.go.kr API 경로 확인 필요."
        ) from exc
    response.raise_for_status()
    data = response.json()
    envelope = data.get("response") or {}
    header = envelope.get("header") or {}
    code = str(header.get("resultCode", "")).strip()
    if code == "03":
        return [], 0
    if code not in {"", "0", "00"}:
        raise RuntimeError(
            f"{config['endpoint']} API 오류: {code} {header.get('resultMsg')}"
        )
    body = envelope.get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount") or 0)


def _fetch_page_retry(config, key, page, page_size=PAGE_SIZE, daily_cap=None):
    for attempt in range(3):
        try:
            return _fetch_page(config, key, page, page_size, daily_cap)
        except QuotaExhausted:
            raise
        except EndpointUnavailableError:
            raise
        except (requests.RequestException, ValueError, RuntimeError):
            if attempt == 2:
                raise
            time.sleep(15 if attempt == 0 else 30)


def _page_is_complete(fetched_before, item_count, expected_total):
    """API 총건수와 실제 페이지 누적이 정확히 일치할 때만 완료로 판정한다."""
    fetched_after = fetched_before + item_count
    if fetched_after > expected_total:
        raise RuntimeError(
            f"API 응답이 총건수보다 많습니다: {fetched_after}/{expected_total}"
        )
    if item_count == 0 and fetched_after < expected_total:
        raise RuntimeError(
            f"API가 중간 빈 페이지를 반환했습니다: {fetched_after}/{expected_total}"
        )
    return fetched_after == expected_total


def _create_master(cur, data, location):
    address = data.get("road_address") or data.get("jibun_address")
    cur.execute(
        """
        INSERT INTO master_buildings (
            building_name, sgg_cd, sgg_text, umd_nm, jibun,
            road_address, jibun_address, lodging_type, lodging_type_detail,
            units, source, name_pending, building_use_type, building_use_detail,
            lodging_classification_source, lodging_classification_confidence
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, TRUE, %s, %s, 'active_permit', 'high'
        )
        RETURNING id
        """,
        (
            data["biz_name"],
            location["sgg_cd"],
            location["sgg_text"],
            location["umd_nm"],
            location["jibun"],
            address,
            data.get("jibun_address"),
            data["lodging_type"],
            data["hygiene_type"],
            data.get("room_count") or 0,
            data["master_source"],
            classify_building_use(data.get("bld_use_nm")),
            data.get("bld_use_nm"),
        ),
    )
    return cur.fetchone()["id"]


def _classification_action(row):
    target = choose_primary_lodging_type(row.get("hygiene_types") or ())
    current = row.get("lodging_type")
    if not target:
        if row.get("lodging_classification_source") == "active_permit":
            return "clear", "미분류"
        return "keep", None
    if target == current:
        return "keep", target
    if should_protect_from_active_permit_reclassification(
        current,
        target,
        row.get("lodging_type_detail"),
        row.get("source"),
        row.get("lodging_classification_source"),
    ):
        return "protected", target
    return "update", target


def _classify_connected(cur, building_ids):
    if not building_ids:
        return 0, []
    cur.execute(
        """
        SELECT mb.id, mb.building_name, mb.lodging_type, mb.lodging_type_detail,
               mb.source, mb.lodging_classification_source,
               ARRAY_AGG(DISTINCT lr.hygiene_type ORDER BY lr.hygiene_type)
                   AS hygiene_types
          FROM master_buildings mb
          LEFT JOIN lodging_registry lr
            ON lr.applied_building_id = mb.id
           AND lr.biz_status_name = %s
         WHERE mb.id = ANY(%s)
         GROUP BY mb.id
         ORDER BY mb.id
        """,
        (ACTIVE_STATUS, sorted(building_ids)),
    )
    updated = 0
    conflicts = []
    for row in cur.fetchall():
        action, target = _classification_action(row)
        if action == "protected":
            conflicts.append({
                "building_id": row["id"],
                "building_name": row["building_name"],
                "current_type": row["lodging_type"],
                "target_type": target,
                "active_hygiene_types": list(row["hygiene_types"] or ()),
                "reason": "protected_classification",
            })
        elif action in {"update", "clear"}:
            cur.execute(
                """
                UPDATE master_buildings
                   SET lodging_type=%s,
                       lodging_classification_source=%s,
                       lodging_classification_confidence=%s,
                       verified_at=NOW()
                 WHERE id=%s
                """,
                (
                    target,
                    "active_permit" if action == "update" else None,
                    "high" if action == "update" else None,
                    row["id"],
                ),
            )
            updated += cur.rowcount
    return updated, conflicts


def _write_conflict_report(conflicts, affected_buildings):
    existing = []
    if REPORT_PATH.exists():
        try:
            existing = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            existing = []
    affected = set(affected_buildings)
    merged = [
        item for item in existing
        if item.get("building_id") not in affected
    ]
    merged.extend(conflicts)
    merged.sort(key=lambda item: item.get("building_id") or 0)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_status(status_key):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (status_key,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return None
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return None


def _claim_status(status_key, run_id, started_at, source_names):
    payload = {
        "run_id": run_id,
        "state": "running",
        "started_at": started_at,
        "finished_at": None,
        "sources": list(source_names),
        "counters": None,
        "error": None,
        "retryable": False,
    }
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value, updated_at = NOW()
            WHERE (app_meta.value::jsonb ->> 'state') IS DISTINCT FROM 'running'
               OR app_meta.updated_at < NOW() - INTERVAL '2 hours'
            """,
            (status_key, json.dumps(payload, ensure_ascii=False)),
        )
        acquired = cur.rowcount > 0
        conn.commit()
        return acquired
    finally:
        cur.close()
        conn.close()


def _write_status(status_key, payload, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta
               SET value=%s, updated_at=NOW()
             WHERE key=%s
               AND (value::jsonb ->> 'run_id')=%s
            """,
            (json.dumps(payload, ensure_ascii=False), status_key, run_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError("동기화 최종 상태 소유권을 확인하지 못했습니다.")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _touch_status(status_key, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta SET updated_at=NOW()
             WHERE key=%s AND (value::jsonb ->> 'run_id')=%s
            """,
            (status_key, run_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _still_owner(cur, status_key, run_id):
    if not status_key or not run_id:
        return True
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (status_key,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return False
    try:
        return json.loads(row["value"]).get("run_id") == run_id
    except (TypeError, ValueError):
        return False


def _mark_last_sync(cur, source_names, counters):
    payload = json.dumps(
        {
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources": list(source_names),
            "counters": counters,
        },
        ensure_ascii=False,
    )
    cur.execute(
        """
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE
          SET value=EXCLUDED.value, updated_at=NOW()
        """,
        (LAST_SYNC_META_KEY, payload),
    )


def _mark_success_status(cur, status_key, run_id, source_names, counters):
    if not status_key or not run_id:
        return
    patch = json.dumps(
        {
            "state": "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources": list(source_names),
            "counters": counters,
            "error": None,
            "retryable": False,
            "dry_run": False,
        },
        ensure_ascii=False,
    )
    cur.execute(
        """
        UPDATE app_meta
           SET value=(value::jsonb || %s::jsonb)::text,
               updated_at=NOW()
         WHERE key=%s
           AND (value::jsonb ->> 'run_id')=%s
           AND (value::jsonb ->> 'state')='running'
        """,
        (patch, status_key, run_id),
    )
    if cur.rowcount != 1:
        raise RuntimeError("완료 상태 기록 전 동기화 소유권을 상실했습니다.")


def _redact(text):
    key = (
        os.environ.get(SERVICE_KEY_ENV)
        or os.environ.get(SERVICE_KEY_ENV2, "")
    )
    if not key:
        return text
    return text.replace(key, "***").replace(quote_plus(key), "***")


def sync(
    source_names,
    *,
    max_pages=None,
    sleep_sec=0.3,
    dry_run=False,
    status_key=None,
    run_id=None,
    daily_cap=None,
):
    key = (
        os.environ.get(SERVICE_KEY_ENV)
        or os.environ.get(SERVICE_KEY_ENV2, "")
    )
    if not key:
        raise RuntimeError(
            f"환경변수 {SERVICE_KEY_ENV} 또는 {SERVICE_KEY_ENV2}가 필요합니다."
        )
    counters = {
        "fetched": 0, "valid": 0, "inserted": 0, "updated": 0,
        "matched": 0, "created": 0, "inactive": 0, "unmatched": 0,
        "classified": 0, "protected": 0, "failed": 0,
    }
    conn = get_conn()
    cur = conn.cursor()
    acquired_lock_ids = []
    committed_mutations = False
    affected_buildings = set()
    conflicts = []
    try:
        for lock_id in _source_lock_ids(source_names):
            cur.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (lock_id,),
            )
            if not bool(cur.fetchone()["acquired"]):
                raise RuntimeError(
                    "같은 숙박업 원천의 다른 수집이 실행 중입니다."
                )
            acquired_lock_ids.append(lock_id)
        if not _still_owner(cur, status_key, run_id):
            raise RuntimeError("동기화 상태 소유권을 확인하지 못했습니다.")
        common._assert_schema(cur)
        road_index, jibun_index = common._load_master_indexes(cur)
        bjdong = common.BjdongMap(common.BJDONG_CODE_CSV)
        for source_name in source_names:
            config = SOURCES[source_name]
            page = 1
            source_fetched = 0
            expected_total = None
            while True:
                if not _still_owner(cur, status_key, run_id):
                    raise RuntimeError("동기화 소유권 상실(다른 실행이 시작됨)")
                items, total = _fetch_page_retry(
                    config, key, page, daily_cap=daily_cap
                )
                if expected_total is None:
                    expected_total = total
                elif total != expected_total:
                    raise RuntimeError(
                        f"{source_name} API 총건수가 실행 중 변경됐습니다: "
                        f"{expected_total} → {total}"
                    )
                page_complete = _page_is_complete(
                    source_fetched, len(items), expected_total
                )
                source_fetched += len(items)
                if not items:
                    break
                counters["fetched"] += len(items)
                print(
                    f"[{source_name}] {page}페이지 {len(items):,}건 "
                    f"(누적 원본 {counters['fetched']:,} / API {total:,})"
                )
                for item in items:
                    data = parse_item(item, config)
                    if data is None:
                        continue
                    counters["valid"] += 1
                    if dry_run:
                        continue
                    try:
                        cur.execute(
                            "SELECT applied_building_id FROM lodging_registry "
                            "WHERE permit_number=%s",
                            (data["permit_number"],),
                        )
                        previous = cur.fetchone()
                        if previous and previous.get("applied_building_id"):
                            affected_buildings.add(previous["applied_building_id"])
                        registry = common._upsert_registry(cur, data)
                        counters["inserted" if registry["is_new"] else "updated"] += 1
                        building_id = None
                        if data["biz_status_name"] != ACTIVE_STATUS:
                            counters["inactive"] += 1
                        elif not data.get("road_norm") and not data.get("jibun_norm"):
                            counters["unmatched"] += 1
                        else:
                            building_id, reason = common._match_master(
                                data, road_index, jibun_index
                            )
                            if building_id:
                                counters["matched"] += 1
                            elif reason:
                                counters["unmatched"] += 1
                            else:
                                location = common._location_from_addresses(
                                    bjdong,
                                    data.get("road_address"),
                                    data.get("jibun_address"),
                                )
                                if location:
                                    building_id = _create_master(cur, data, location)
                                    counters["created"] += 1
                                    common._register_new_master_in_indexes(
                                        building_id, data, road_index, jibun_index
                                    )
                                else:
                                    counters["unmatched"] += 1
                        if building_id:
                            cur.execute(
                                "UPDATE lodging_registry SET applied_building_id=%s WHERE id=%s",
                                (building_id, registry["id"]),
                            )
                            affected_buildings.add(building_id)
                        conn.commit()
                        committed_mutations = True
                    except Exception as exc:
                        conn.rollback()
                        counters["failed"] += 1
                        print(f"  [실패] {data['biz_name']}: {exc}")
                if max_pages and page >= max_pages:
                    if not dry_run and not page_complete:
                        raise RuntimeError(
                            f"{source_name} API 전체 수집 전 최대 페이지에 도달했습니다: "
                            f"{source_fetched}/{expected_total}"
                        )
                    break
                if page_complete:
                    break
                page += 1
                time.sleep(sleep_sec)

        if not dry_run:
            if counters["failed"]:
                raise RuntimeError(
                    f"공식 신고 {counters['failed']}건 처리 실패 — 재실행이 필요합니다."
                )
            if not _still_owner(cur, status_key, run_id):
                raise RuntimeError("완료 처리 전 동기화 소유권을 상실했습니다.")
            classified, conflicts = _classify_connected(cur, affected_buildings)
            counters["classified"] = classified
            counters["protected"] = len(conflicts)
            if not _still_owner(cur, status_key, run_id):
                raise RuntimeError("완료 커밋 전 동기화 소유권을 상실했습니다.")
            _mark_last_sync(cur, source_names, counters)
            mark_master_stats_invalidated_in_transaction(
                cur,
                "rural_hanok_sync",
            )
            _mark_success_status(
                cur,
                status_key,
                run_id,
                source_names,
                counters,
            )
            conn.commit()
            try:
                _write_conflict_report(conflicts, affected_buildings)
            except Exception as exc:
                print(
                    f"[rural-hanok] 분류 충돌 보고서 저장 실패: "
                    f"{_redact(str(exc))[:300]}"
                )
    except Exception:
        conn.rollback()
        if not dry_run and committed_mutations:
            mark_master_stats_invalidated_in_transaction(
                cur,
                "rural_hanok_sync_partial",
            )
            conn.commit()
        raise
    finally:
        for lock_id in reversed(acquired_lock_ids):
            try:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s) AS released",
                    (lock_id,),
                )
                cur.fetchone()
            except Exception:
                pass
        cur.close()
        conn.close()
    print(json.dumps(counters, ensure_ascii=False))
    return counters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=("all", *SOURCES),
        default="all",
    )
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--daily-cap", type=int)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status-key", default=STATUS_META_KEY)
    args = parser.parse_args()
    source_names = list(SOURCES) if args.source == "all" else [args.source]
    run_id = secrets.token_hex(8)
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not _claim_status(args.status_key, run_id, started_at, source_names):
        print("[rural-hanok] 이미 다른 실행이 진행 중입니다 — 이번 실행을 건너뜁니다.")
        return

    stop_beat = threading.Event()

    def _beat():
        while not stop_beat.wait(HEARTBEAT_SEC):
            try:
                _touch_status(args.status_key, run_id)
            except Exception:
                pass

    threading.Thread(target=_beat, daemon=True).start()
    error = None
    counters = None
    try:
        counters = sync(
            source_names,
            max_pages=args.max_pages,
            sleep_sec=args.sleep,
            dry_run=args.dry_run,
            status_key=args.status_key,
            run_id=run_id,
            daily_cap=args.daily_cap,
        )
    except Exception as exc:
        error = _redact(str(exc))[:500]
        print(f"[rural-hanok] 실패: {error}")
    finally:
        stop_beat.set()

    if error or args.dry_run:
        status = _read_status(args.status_key) or {}
        status.update(
            {
                "state": "failed" if error else "done",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sources": source_names,
                "counters": counters,
                "error": error,
                "retryable": bool(error),
                "dry_run": bool(args.dry_run),
            }
        )
        try:
            _write_status(args.status_key, status, run_id)
        except Exception as exc:
            status_error = _redact(str(exc))[:300]
            print(f"[rural-hanok] 최종 상태 저장 실패: {status_error}")
            if not error:
                error = f"최종 상태 저장 실패: {status_error}"
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()