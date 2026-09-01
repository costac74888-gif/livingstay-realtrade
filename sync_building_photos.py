#!/usr/bin/env python3
"""건물 상세 사진 자동 수집 배치.

기본 실행:
    env DATABASE_URL="$PROD_DATABASE_URL" python sync_building_photos.py

사진을 내려받아 저장하지 않고, 공개 이미지 URL과 출처만
building_photos에 저장한다. 각 공급자는 독립적으로 재실행할 수 있으며,
공급자별 체크포인트와 일일 처리 캡을 사용한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, quote_plus, urlencode

import requests
from pyproj import Transformer

from db import get_conn
from quota_policy import korea_today


BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_FILE = BASE_DIR / "sync_building_photos_checkpoint.json"

# TourAPI 4.0. 기존 KorService1은 2026년 현재 폐기되어 KorService2를 사용한다.
TOURAPI_URL = "https://apis.data.go.kr/B551011/KorService2"
TOURAPI_KEY_ENV = "TOUR_API_SERVICE_KEY"
GOOGLE_KEY_ENV = "GOOGLE_MAPS_API_KEY"
VWORLD_KEY_ENV = "VWORLD_API_KEY"

TOURAPI_DAILY_CAP = 3000
STREETVIEW_DAILY_CAP = 20000
VWORLD_DAILY_CAP = 50000
DEFAULT_LIMIT = 500
DEFAULT_SLEEP = 0.5
HEARTBEAT_SEC = 30

PHOTO_SOURCES = ("tourapi", "streetview", "vworld")
LODGING_TYPES = ("생활", "관광", "일반", "전체")
_TM_TO_WGS84 = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


class ProviderFatalError(RuntimeError):
    """키·권한·서비스 장애처럼 다음 건에서도 반복될 공급자 오류."""


class DailyCapReached(RuntimeError):
    pass


def tm_to_latlng(x, y):
    """EPSG:5174 TM 좌표를 검증된 WGS84 (lat, lng)로 변환한다."""
    try:
        lng, lat = _TM_TO_WGS84.transform(float(x), float(y))
        if 33 < lat < 39 and 124 < lng < 132:
            return round(lat, 6), round(lng, 6)
    except (TypeError, ValueError, OverflowError):
        pass
    return None, None


def _redact(text: str) -> str:
    result = str(text)
    for key_name in (TOURAPI_KEY_ENV, GOOGLE_KEY_ENV, VWORLD_KEY_ENV):
        key = os.environ.get(key_name, "")
        if key:
            for candidate in (key, quote(key, safe=""), quote_plus(key)):
                result = result.replace(candidate, "***")
    return result


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


def _write_status(status_key, payload, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta SET value=%s, updated_at=NOW()
            WHERE key=%s AND (value::jsonb ->> 'run_id')=%s
            """,
            (json.dumps(payload, ensure_ascii=False), status_key, run_id),
        )
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


def _publish_progress(args, stats):
    if not args.status_key or not args.run_id:
        return
    status = _read_status(args.status_key) or {}
    if status.get("run_id") != args.run_id or status.get("state") != "running":
        return
    status.update({
        "source": args.source,
        "processed": stats.get("processed", 0),
        "saved": stats.get("saved", 0),
        "skipped": stats.get("skipped", 0),
        "errors": stats.get("errors", 0),
        "tour_no_match": stats.get("tour_no_match", 0),
        "capped": stats.get("capped", False),
    })
    _write_status(args.status_key, status, args.run_id)


def _still_owner(cur, status_key, run_id):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (status_key,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return False
    try:
        status = json.loads(row["value"])
    except (TypeError, ValueError):
        return False
    return status.get("run_id") == run_id and status.get("state") == "running"


def _read_checkpoint():
    try:
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {"date": korea_today(), "sources": {}}


def _write_checkpoint(checkpoint):
    checkpoint = dict(checkpoint)
    checkpoint["date"] = korea_today()
    temp = CHECKPOINT_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(CHECKPOINT_FILE)


def _source_checkpoint(checkpoint, source):
    sources = checkpoint.setdefault("sources", {})
    if checkpoint.get("date") != korea_today():
        checkpoint.clear()
        checkpoint.update({"date": korea_today(), "sources": {}})
        sources = checkpoint["sources"]
    return sources.setdefault(
        source,
        {"last_building_id": 0, "total_processed": 0, "date": korea_today()},
    )


def _read_source_progress(source):
    key = f"building_photos_progress:{source}"
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (key,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return {"last_building_id": 0, "total_processed": 0}
    try:
        value = json.loads(row["value"])
        return {
            "last_building_id": int(value.get("last_building_id") or 0),
            "total_processed": int(value.get("total_processed") or 0),
        }
    except (TypeError, ValueError):
        return {"last_building_id": 0, "total_processed": 0}


def _write_source_progress(source, progress):
    key = f"building_photos_progress:{source}"
    payload = {
        "last_building_id": int(progress.get("last_building_id") or 0),
        "total_processed": int(progress.get("total_processed") or 0),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO app_meta(key, value, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
            """,
            (key, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _today_count(meta_key):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (meta_key,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return 0
    try:
        value = json.loads(row["value"])
        return int(value["count"]) if value.get("date") == korea_today() else 0
    except (TypeError, ValueError, KeyError):
        return 0


def _claim_daily_slot(meta_key, cap):
    """처리 시작 전에 원자적으로 일일 캡 한 건을 예약한다."""
    today = korea_today()
    fresh = json.dumps({"date": today, "count": 1})
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO app_meta(key, value, updated_at)
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
            WHERE app_meta.value::jsonb ->> 'date' IS DISTINCT FROM %s
               OR COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) < %s
            RETURNING (value::jsonb ->> 'count')::int AS count
            """,
            (meta_key, fresh, today, today, today, int(cap)),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None
        conn.commit()
        return int(row["count"])
    finally:
        cur.close()
        conn.close()


def _extract_items(data):
    """TourAPI 응답의 item/list가 배열·단일 객체 어느 쪽이어도 처리한다."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    response = data.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, dict):
                item = items.get("item")
                if isinstance(item, list):
                    return item
                if isinstance(item, dict):
                    return [item]
            if isinstance(items, list):
                return items
    for value in data.values():
        if isinstance(value, (dict, list)):
            found = _extract_items(value)
            if found:
                return found
    return []


def _assert_tourapi_success(data):
    try:
        header = data["response"]["header"]
    except (KeyError, TypeError):
        return
    code = str(header.get("resultCode") or "").strip()
    if code and code not in {"0000", "000"}:
        message = str(header.get("resultMsg") or "응답 오류").strip()
        raise ProviderFatalError(f"TourAPI 오류 {code}: {message}")


_SPACE_RE = re.compile(r"\s+")
_NON_ADDRESS_RE = re.compile(r"[^0-9A-Za-z가-힣]")
_ROAD_RE = re.compile(r"[0-9A-Za-z가-힣]+(?:대로|로|길)")
_CITY_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "제주특별자치도": "제주",
}


def _normalize_address(address):
    text = _SPACE_RE.sub(" ", str(address or "").strip())
    for old, new in _CITY_ALIASES.items():
        text = text.replace(old, new)
    text = re.sub(r"\([^)]*\)", " ", text)
    return _NON_ADDRESS_RE.sub("", text)


def address_similarity(left, right):
    """시·군·구와 도로명이 포함된 주소 유사도(0~1)를 계산한다."""
    left_key = _normalize_address(left)
    right_key = _normalize_address(right)
    if not left_key or not right_key:
        return 0.0
    left_road = _ROAD_RE.search(left_key)
    right_road = _ROAD_RE.search(right_key)
    if left_road and right_road:
        left_road_text = left_road.group(0)
        right_road_text = right_road.group(0)
        if left_road_text != right_road_text:
            return 0.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def make_streetview_url(lat, lng, api_key, heading=0):
    params = {
        "size": "640x480",
        "location": f"{float(lat)},{float(lng)}",
        "heading": int(heading),
        "fov": 90,
        "pitch": 0,
        "key": api_key,
    }
    return "https://maps.googleapis.com/maps/api/streetview?" + urlencode(params)


def make_vworld_url(lat, lng, api_key, size=200):
    half = float(size) / 111320
    bbox = f"{float(lng) - half},{float(lat) - half},{float(lng) + half},{float(lat) + half}"
    params = {
        "key": api_key,
        "LAYERS": "Satellite",
        "BBOX": bbox,
        "WIDTH": 640,
        "HEIGHT": 480,
        "FORMAT": "image/png",
        "CRS": "EPSG:4326",
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
    }
    return "https://api.vworld.kr/req/wms?" + urlencode(params)


def _tour_search(session, name, api_key):
    try:
        response = session.get(
            f"{TOURAPI_URL}/searchKeyword2",
            params={
                "serviceKey": api_key,
                "MobileOS": "ETC",
                "MobileApp": "homenstay",
                "arrange": "A",
                "numOfRows": 10,
                "pageNo": 1,
                "keyword": name,
                "contentTypeId": 32,
                "_type": "json",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise ProviderFatalError(f"TourAPI HTTP 오류 {status or '연결 실패'}") from exc
    except ValueError as exc:
        raise ProviderFatalError("TourAPI JSON 응답을 해석하지 못했습니다.") from exc
    _assert_tourapi_success(data)
    return _extract_items(data)


def _tour_images(session, content_id, api_key):
    try:
        response = session.get(
            f"{TOURAPI_URL}/detailImage2",
            params={
                "serviceKey": api_key,
                "MobileOS": "ETC",
                "MobileApp": "homenstay",
                "contentId": content_id,
                "numOfRows": 100,
                "pageNo": 1,
                "imageYN": "Y",
                "subImageYN": "Y",
                "_type": "json",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise ProviderFatalError(f"TourAPI 이미지 HTTP 오류 {status or '연결 실패'}") from exc
    except ValueError as exc:
        raise ProviderFatalError("TourAPI 이미지 JSON 응답을 해석하지 못했습니다.") from exc
    _assert_tourapi_success(data)
    return _extract_items(data)


def _tour_photo_type(image_name):
    name = str(image_name or "").lower()
    if "객실" in name or "room" in name:
        return "room"
    if "로비" in name or "입구" in name or "lobby" in name:
        return "lobby"
    if "외관" in name or "건물" in name or "exterior" in name:
        return "exterior"
    return "exterior"


def _find_tour_match(items, road_address):
    candidates = []
    for item in items:
        content_id = item.get("contentid") or item.get("contentId")
        address = item.get("addr1") or item.get("addr") or ""
        if not content_id or not address:
            continue
        score = address_similarity(address, road_address)
        if score >= 0.70:
            candidates.append((score, str(content_id), item))
    return max(candidates, key=lambda value: value[0]) if candidates else None


def _insert_photos(cur, building_id, photos, source, force=False):
    if force:
        cur.execute("DELETE FROM building_photos WHERE building_id=%s AND source=%s", (building_id, source))
    if not photos:
        return 0
    cur.execute(
        "SELECT COALESCE(MAX(display_order), -1) AS max_order FROM building_photos WHERE building_id=%s",
        (building_id,),
    )
    next_order = int(cur.fetchone()["max_order"]) + 1
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM building_photos WHERE building_id=%s)",
        (building_id,),
    )
    had_photos = bool(cur.fetchone()["exists"])
    inserted = 0
    for index, photo in enumerate(photos):
        url = str(photo.get("url") or "").strip()
        if not url:
            continue
        is_primary = bool(photo.get("is_primary")) and not had_photos
        cur.execute(
            """
            INSERT INTO building_photos
                (building_id, photo_url, source, photo_type, is_primary, display_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (building_id, photo_url) DO NOTHING
            """,
            (
                building_id,
                url,
                source,
                photo.get("photo_type") or "exterior",
                is_primary,
                next_order + index,
            ),
        )
        if cur.rowcount:
            inserted += cur.rowcount
            had_photos = True
    return inserted


def _targets(cur, source, lodging_type, last_id, limit, force):
    params = []
    where = ["b.id > %s"]
    params.append(last_id)
    if source == "tourapi":
        where.extend([
            "b.building_name IS NOT NULL",
            "b.building_name <> ''",
            "b.road_address IS NOT NULL",
            "b.road_address <> ''",
        ])
        if lodging_type != "전체":
            where.append("b.lodging_type = %s")
            params.append(lodging_type)
        else:
            where.append("b.lodging_type IN ('생활', '관광', '일반')")
        if not force:
            where.append(
                "NOT EXISTS (SELECT 1 FROM building_photos p "
                "WHERE p.building_id=b.id AND p.source='tourapi')"
            )
    else:
        where.extend(["b.lat IS NOT NULL", "b.lng IS NOT NULL"])
        if not force:
            where.append(
                f"NOT EXISTS (SELECT 1 FROM building_photos p "
                f"WHERE p.building_id=b.id AND p.source='{source}')"
            )
    params.append(limit)
    cur.execute(
        f"""
        SELECT b.id, b.building_name, b.road_address, b.lat, b.lng
        FROM master_buildings b
        WHERE {' AND '.join(where)}
        ORDER BY b.id
        LIMIT %s
        """,
        params,
    )
    return cur.fetchall()


def _validate_url(session, url):
    try:
        response = session.get(url, allow_redirects=True, timeout=20, stream=True)
        content_type = str(response.headers.get("Content-Type") or "").lower()
        return 200 <= response.status_code < 400 and content_type.startswith("image/")
    except requests.RequestException:
        return False


def _streetview_available(session, lat, lng, api_key):
    """사진 본문이 아닌 무료 Metadata API로 실제 파노라마 존재 여부를 확인한다."""
    try:
        response = session.get(
            "https://maps.googleapis.com/maps/api/streetview/metadata",
            params={
                "location": f"{float(lat)},{float(lng)}",
                "key": api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
        status = str(response.json().get("status") or "").upper()
    except (requests.RequestException, ValueError) as exc:
        raise ProviderFatalError("Street View Metadata 조회에 실패했습니다.") from exc
    if status == "OK":
        return True
    if status == "ZERO_RESULTS":
        return False
    raise ProviderFatalError(f"Street View Metadata 오류: {status or 'UNKNOWN'}")


def _run_tourapi(args, session, checkpoint, stats):
    api_key = os.environ.get(TOURAPI_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"{TOURAPI_KEY_ENV} 시크릿이 없습니다.")
    progress = _read_source_progress("tourapi")
    cp = _source_checkpoint(checkpoint, "tourapi")
    cp.update(progress)
    conn = get_conn()
    cur = conn.cursor()
    try:
        targets = _targets(
            cur, "tourapi", args.lodging_type,
            int(cp.get("last_building_id") or 0), args.limit, args.force,
        )
        for index, row in enumerate(targets, start=1):
            if args.status_key and index % 10 == 0 and not _still_owner(cur, args.status_key, args.run_id):
                break
            if _claim_daily_slot("building_photos_tourapi_calls", TOURAPI_DAILY_CAP) is None:
                stats["capped"] = True
                break
            stats["processed"] += 1
            try:
                items = _tour_search(session, row["building_name"], api_key)
                match = _find_tour_match(items, row["road_address"])
                if not match:
                    stats["skipped"] += 1
                    stats["tour_no_match"] += 1
                else:
                    if _claim_daily_slot(
                        "building_photos_tourapi_calls", TOURAPI_DAILY_CAP
                    ) is None:
                        raise DailyCapReached
                    images = _tour_images(session, match[1], api_key)
                    photos = [
                        {
                            "url": image.get("originimgurl") or image.get("originImgUrl"),
                            "photo_type": _tour_photo_type(image.get("imgname")),
                            "is_primary": image_index == 0,
                        }
                        for image_index, image in enumerate(images)
                    ]
                    saved = _insert_photos(cur, row["id"], photos, "tourapi", args.force)
                    conn.commit()
                    stats["saved"] += saved
                    if not saved:
                        stats["skipped"] += 1
            except DailyCapReached:
                conn.rollback()
                stats["capped"] = True
                break
            except ProviderFatalError:
                conn.rollback()
                raise
            except Exception as exc:
                conn.rollback()
                stats["errors"] += 1
                raise RuntimeError(
                    f"TourAPI 사진 저장 실패(building_id={row['id']}): {_redact(exc)}"
                ) from exc
            progress["last_building_id"] = row["id"]
            progress["total_processed"] = int(progress.get("total_processed") or 0) + 1
            _write_source_progress("tourapi", progress)
            cp.update(progress)
            _write_checkpoint(checkpoint)
            if args.status_key:
                if stats["processed"] % 10 == 0:
                    _publish_progress(args, stats)
                else:
                    _touch_status(args.status_key, args.run_id)
            time.sleep(max(args.sleep, 0))
    finally:
        cur.close()
        conn.close()


def _run_url_source(source, args, session, checkpoint, stats):
    env_name = GOOGLE_KEY_ENV if source == "streetview" else VWORLD_KEY_ENV
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(f"{env_name} 시크릿이 없습니다.")
    cap = STREETVIEW_DAILY_CAP if source == "streetview" else VWORLD_DAILY_CAP
    progress = _read_source_progress(source)
    cp = _source_checkpoint(checkpoint, source)
    cp.update(progress)
    conn = get_conn()
    cur = conn.cursor()
    try:
        targets = _targets(
            cur, source, args.lodging_type,
            int(cp.get("last_building_id") or 0), args.limit, args.force,
        )
        if targets:
            first = targets[0]
            preflight_url = (
                # 키·API 권한 확인은 파노라마가 확실한 서울 좌표로 한다.
                make_streetview_url(37.5665, 126.9780, api_key)
                if source == "streetview"
                else make_vworld_url(first["lat"], first["lng"], api_key)
            )
            if not _validate_url(session, preflight_url):
                raise ProviderFatalError(
                    f"{source} 공급자 사전검증이 실패했습니다. 키 권한·도메인·공급자 상태를 확인하세요."
                )
        for index, row in enumerate(targets, start=1):
            if args.status_key and index % 25 == 0 and not _still_owner(cur, args.status_key, args.run_id):
                break
            if _claim_daily_slot(f"building_photos_{source}_calls", cap) is None:
                stats["capped"] = True
                break
            stats["processed"] += 1
            if source == "streetview" and not _streetview_available(
                session, row["lat"], row["lng"], api_key
            ):
                stats["skipped"] += 1
                progress["last_building_id"] = row["id"]
                progress["total_processed"] = int(progress.get("total_processed") or 0) + 1
                _write_source_progress(source, progress)
                cp.update(progress)
                _write_checkpoint(checkpoint)
                continue
            provider_url = (
                make_streetview_url(row["lat"], row["lng"], api_key)
                if source == "streetview"
                else make_vworld_url(row["lat"], row["lng"], api_key)
            )
            if args.validate and not _validate_url(session, provider_url):
                raise ProviderFatalError(
                    f"{source} 이미지 검증 실패(building_id={row['id']})"
                )
            try:
                saved = _insert_photos(
                    cur,
                    row["id"],
                    [{
                        "url": f"/api/building-photo/{row['id']}/{source}",
                        "photo_type": "exterior" if source == "streetview" else "aerial",
                        "is_primary": False,
                    }],
                    source,
                    args.force,
                )
                conn.commit()
                stats["saved"] += saved
                if not saved:
                    stats["skipped"] += 1
            except Exception as exc:
                conn.rollback()
                stats["errors"] += 1
                raise RuntimeError(
                    f"{source} 사진 저장 실패(building_id={row['id']}): {_redact(exc)}"
                ) from exc
            progress["last_building_id"] = row["id"]
            progress["total_processed"] = int(progress.get("total_processed") or 0) + 1
            _write_source_progress(source, progress)
            cp.update(progress)
            _write_checkpoint(checkpoint)
            if args.status_key:
                if stats["processed"] % 25 == 0:
                    _publish_progress(args, stats)
                else:
                    _touch_status(args.status_key, args.run_id)
            time.sleep(max(args.sleep, 0))
    finally:
        cur.close()
        conn.close()


def run(args):
    checkpoint = _read_checkpoint()
    session = requests.Session()
    session.headers.update({"User-Agent": "homenstay-building-photos/1.0"})
    stats = {
        "processed": 0,
        "saved": 0,
        "skipped": 0,
        "errors": 0,
        "tour_no_match": 0,
        "capped": False,
        "source": args.source,
    }
    sources = PHOTO_SOURCES if args.source == "all" else (args.source,)
    for source in sources:
        if source == "tourapi":
            _run_tourapi(args, session, checkpoint, stats)
        elif source in ("streetview", "vworld"):
            if not os.environ.get(GOOGLE_KEY_ENV if source == "streetview" else VWORLD_KEY_ENV):
                message = f"{source} 건너뜀: 필요한 시크릿이 없습니다."
                stats.setdefault("warnings", []).append(message)
                print(f"[사진] {message}", flush=True)
                continue
            _run_url_source(source, args, session, checkpoint, stats)
    _write_checkpoint(checkpoint)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("tourapi", "streetview", "vworld", "all"), default="all")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--lodging-type", choices=LODGING_TYPES, default="전체")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--status-key", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    args.limit = max(1, min(int(args.limit), 5000))

    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[사진] running 상태가 아니므로 종료합니다.")
            return
        args.run_id = status.get("run_id") or args.run_id or ""
        status.update({
            "source": args.source,
            "processed": 0,
            "saved": 0,
            "skipped": 0,
            "errors": 0,
            "capped": False,
        })
        _write_status(args.status_key, status, args.run_id)

        def beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch_status(args.status_key, args.run_id)
                except Exception:
                    pass

        threading.Thread(target=beat, daemon=True).start()

    error = None
    stats = None
    try:
        stats = run(args)
        print(
            f"[DONE] source={args.source} 처리 {stats['processed']}건 / "
            f"저장 {stats['saved']}장 / 건너뜀 {stats['skipped']}건 / 오류 {stats['errors']}건",
            flush=True,
        )
    except Exception as exc:
        error = _redact(exc)[:500]
        print(f"[사진] 실패: {error}", flush=True)
    finally:
        stop_beat.set()

    if args.status_key and args.run_id is not None:
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "processed": (stats or {}).get("processed"),
            "saved": (stats or {}).get("saved"),
            "skipped": (stats or {}).get("skipped"),
            "errors": (stats or {}).get("errors"),
            "tour_no_match": (stats or {}).get("tour_no_match"),
            "capped": (stats or {}).get("capped", False),
            "warnings": (stats or {}).get("warnings", []),
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, args.run_id)
                break
            except Exception as exc:
                print(f"[사진] 상태 저장 실패({attempt + 1}/3): {_redact(exc)}", flush=True)
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()