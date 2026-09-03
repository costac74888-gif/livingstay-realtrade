#!/usr/bin/env python3
"""TourAPI 숙박 콘텐츠 목록을 한 번 조회해 사진 메타데이터만 건물에 연결한다.

사진 파일이나 사진 URL은 저장하지 않는다. 전국 숙박 목록(areaBasedList2)을
페이지 단위로 가져온 뒤 도로명·지번 주소를 master_buildings와 매칭하고,
contentId와 대표사진 존재 여부만 building_photo_fetches에 기록한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import unquote

import requests

from addr_norm import normalize_jibun_prefix, normalize_road_prefix
from db import get_conn
from sync_building_photos import (
    TOURAPI_CONNECT_RETRIES,
    TOURAPI_CONNECT_TIMEOUT,
    TOURAPI_DAILY_CAP,
    TOURAPI_READ_TIMEOUT,
    TOURAPI_RETRY_SLEEP,
    TOURAPI_URL,
    _assert_tourapi_success,
    _claim_daily_slot,
    _extract_items,
    _read_status,
    _redact,
    _tour_service_key,
    _write_status,
)

TOURAPI_META_KEY = "building_photos_tourapi_catalog"
PAGE_SIZE = 100


def _tour_catalog_page(session, api_key, page_no):
    params = {
        "serviceKey": unquote(api_key),
        "MobileOS": "ETC",
        "MobileApp": "homenstay",
        "arrange": "A",
        "numOfRows": PAGE_SIZE,
        "pageNo": page_no,
        "contentTypeId": 32,
        "_type": "json",
    }
    last_error = None
    for attempt in range(TOURAPI_CONNECT_RETRIES + 1):
        try:
            response = session.get(
                f"{TOURAPI_URL}/areaBasedList2",
                params=params,
                timeout=(TOURAPI_CONNECT_TIMEOUT, TOURAPI_READ_TIMEOUT),
            )
            response.raise_for_status()
            data = response.json()
            _assert_tourapi_success(data)
            return data
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < TOURAPI_CONNECT_RETRIES:
                time.sleep(TOURAPI_RETRY_SLEEP * (attempt + 1))
    raise RuntimeError(f"TourAPI 숙박 목록 조회 실패: {_redact(last_error)}")


def _catalog_item_address(item):
    return " ".join(
        str(value).strip()
        for value in (item.get("addr1"), item.get("addr2"))
        if str(value or "").strip()
    )


def _build_address_maps(cur):
    cur.execute("""
        SELECT id, road_address, jibun_address
        FROM master_buildings
        WHERE building_name IS NOT NULL
          AND building_name <> ''
          AND road_address IS NOT NULL
          AND road_address <> ''
    """)
    road_map = {}
    jibun_map = {}
    for row in cur.fetchall():
        road_key = normalize_road_prefix(row["road_address"])
        jibun_key = normalize_jibun_prefix(row["jibun_address"] or row["road_address"])
        if road_key:
            road_map.setdefault(road_key, []).append(row["id"])
        if jibun_key:
            jibun_map.setdefault(jibun_key, []).append(row["id"])
    return road_map, jibun_map


def _catalog_matches(item, road_map, jibun_map):
    address = _catalog_item_address(item)
    road_key = normalize_road_prefix(address)
    if road_key and road_key in road_map:
        return road_map[road_key]
    jibun_key = normalize_jibun_prefix(address)
    if jibun_key and jibun_key in jibun_map:
        return jibun_map[jibun_key]
    return []


def _upsert_catalog_metadata(cur, items, road_map, jibun_map):
    matched_buildings = 0
    with_image_buildings = 0
    without_image_buildings = 0
    content_ids = set()
    for item in items:
        content_id = str(item.get("contentid") or item.get("contentId") or "").strip()
        if not content_id or content_id in content_ids:
            continue
        content_ids.add(content_id)
        building_ids = _catalog_matches(item, road_map, jibun_map)
        if not building_ids:
            continue
        has_image = bool(
            str(item.get("firstimage") or "").strip()
            or str(item.get("firstimage2") or "").strip()
        )
        status = "catalog_matched" if has_image else "catalog_no_photo"
        for building_id in building_ids:
            cur.execute("""
                INSERT INTO building_photo_fetches
                    (building_id, source, status, last_attempt_at,
                     error_message, provider_ref, photo_available)
                VALUES (%s, 'tourapi', %s, NOW(), NULL, %s, %s)
                ON CONFLICT (building_id, source) DO UPDATE SET
                    status=CASE
                        WHEN building_photo_fetches.status='success'
                            THEN building_photo_fetches.status
                        WHEN building_photo_fetches.photo_available IS TRUE
                             AND EXCLUDED.photo_available IS FALSE
                            THEN 'catalog_matched'
                        ELSE EXCLUDED.status
                    END,
                    last_attempt_at=EXCLUDED.last_attempt_at,
                    error_message=NULL,
                    provider_ref=CASE
                        WHEN building_photo_fetches.photo_available IS TRUE
                             AND EXCLUDED.photo_available IS FALSE
                             AND building_photo_fetches.provider_ref IS NOT NULL
                            THEN building_photo_fetches.provider_ref
                        ELSE EXCLUDED.provider_ref
                    END,
                    photo_available=(
                        COALESCE(building_photo_fetches.photo_available, FALSE)
                        OR EXCLUDED.photo_available
                    )
            """, [building_id, status, content_id, has_image])
            matched_buildings += 1
            if has_image:
                with_image_buildings += 1
            else:
                without_image_buildings += 1
    return {
        "matched_buildings": matched_buildings,
        "with_image_buildings": with_image_buildings,
        "without_image_buildings": without_image_buildings,
    }


def run(status_key, run_id, sleep_seconds):
    api_key = _tour_service_key()
    if not api_key:
        raise RuntimeError("TOUR_API_SERVICE_KEY 시크릿이 없습니다.")
    session = requests.Session()
    session.headers.update({"User-Agent": "homenstay-tourapi-metadata/1.0"})
    stats = {
        "processed": 0,
        "saved": 0,
        "skipped": 0,
        "errors": 0,
        "catalog_items": 0,
        "catalog_pages": 0,
        "matched_buildings": 0,
        "with_image_buildings": 0,
        "without_image_buildings": 0,
        "capped": False,
    }
    conn = get_conn()
    cur = conn.cursor()
    try:
        road_map, jibun_map = _build_address_maps(cur)
        if _claim_daily_slot(
            "building_photos_tourapi_calls", TOURAPI_DAILY_CAP
        ) is None:
            stats["capped"] = True
            return stats
        first = _tour_catalog_page(session, api_key, 1)
        first_body = first.get("response", {}).get("body", {})
        total = int(first_body.get("totalCount") or 0)
        page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
        for page_no in range(1, page_count + 1):
            if page_no == 1:
                data = first
            else:
                if _claim_daily_slot(
                    "building_photos_tourapi_calls", TOURAPI_DAILY_CAP
                ) is None:
                    stats["capped"] = True
                    break
                data = _tour_catalog_page(session, api_key, page_no)
            items = _extract_items(data)
            page_stats = _upsert_catalog_metadata(cur, items, road_map, jibun_map)
            conn.commit()
            stats["processed"] += len(items)
            stats["catalog_items"] += len(items)
            stats["catalog_pages"] = page_no
            stats["matched_buildings"] += page_stats["matched_buildings"]
            stats["with_image_buildings"] += page_stats["with_image_buildings"]
            stats["without_image_buildings"] += page_stats["without_image_buildings"]
            stats["saved"] += (
                page_stats["with_image_buildings"]
                + page_stats["without_image_buildings"]
            )
            if status_key:
                current = _read_status(status_key) or {}
                if current.get("run_id") != run_id or current.get("state") != "running":
                    break
                current.update({
                    "source": "tourapi_metadata",
                    "processed": stats["processed"],
                    "saved": stats["saved"],
                    "skipped": stats["skipped"],
                    "errors": stats["errors"],
                    "catalog_items": stats["catalog_items"],
                    "catalog_pages": stats["catalog_pages"],
                    "matched_buildings": stats["matched_buildings"],
                    "with_image_buildings": stats["with_image_buildings"],
                    "without_image_buildings": stats["without_image_buildings"],
                    "capped": stats["capped"],
                })
                _write_status(status_key, current, run_id)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        cur.execute("""
            SELECT
              COUNT(*) FILTER (WHERE provider_ref IS NOT NULL) AS matched,
              COUNT(*) FILTER (
                WHERE provider_ref IS NOT NULL AND photo_available IS TRUE
              ) AS with_image,
              COUNT(*) FILTER (
                WHERE provider_ref IS NOT NULL AND photo_available IS FALSE
              ) AS without_image
            FROM building_photo_fetches
            WHERE source='tourapi'
        """)
        final_counts = cur.fetchone()
        stats["matched_buildings"] = int(final_counts["matched"] or 0)
        stats["with_image_buildings"] = int(final_counts["with_image"] or 0)
        stats["without_image_buildings"] = int(final_counts["without_image"] or 0)
        stats["saved"] = stats["matched_buildings"]
    finally:
        cur.close()
        conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-key", default="building_photos_sync_status")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()
    status = _read_status(args.status_key) or {}
    run_id = status.get("run_id") or args.run_id
    if not run_id or status.get("state") != "running":
        print("[TourAPI 메타데이터] running 상태가 아니므로 종료합니다.", flush=True)
        return
    error = None
    stats = None
    try:
        stats = run(args.status_key, run_id, max(0.0, args.sleep))
    except Exception as exc:
        error = _redact(exc)[:500]
        print(f"[TourAPI 메타데이터] 실패: {error}", flush=True)
    status = _read_status(args.status_key) or {}
    if status.get("run_id") == run_id:
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "tourapi_metadata",
            "processed": (stats or {}).get("processed", 0),
            "saved": (stats or {}).get("saved", 0),
            "skipped": (stats or {}).get("skipped", 0),
            "errors": (stats or {}).get("errors", 0),
            "catalog_items": (stats or {}).get("catalog_items", 0),
            "catalog_pages": (stats or {}).get("catalog_pages", 0),
            "matched_buildings": (stats or {}).get("matched_buildings", 0),
            "with_image_buildings": (stats or {}).get("with_image_buildings", 0),
            "without_image_buildings": (stats or {}).get("without_image_buildings", 0),
            "capped": (stats or {}).get("capped", False),
            "error": error,
        })
        _write_status(args.status_key, status, run_id)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()