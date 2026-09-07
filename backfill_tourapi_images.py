#!/usr/bin/env python3
"""TourAPI 숙박 대표사진·다중사진을 재개 가능한 배치로 보강한다."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

import requests

from db import get_conn
from prewarm_tourapi_metadata import PAGE_SIZE
from sync_building_photos import (
    TOURAPI_CONNECT_TIMEOUT,
    TOURAPI_DAILY_CAP,
    TOURAPI_READ_TIMEOUT,
    TOURAPI_URL,
    DailyCapReached,
    ProviderFatalError,
    _assert_tourapi_success,
    _claim_daily_slot,
    _extract_items,
    _insert_photos,
    _read_status,
    _redact,
    _tour_photo_type,
    _tour_service_key,
    _write_status,
)


PROGRESS_KEY = "building_photos_tourapi_images_progress"
CALLS_KEY = "building_photos_tourapi_calls"
MAX_PHOTOS = 20


class ProviderReferenceChanged(RuntimeError):
    """사진 조회 중 정확 주소의 TourAPI 콘텐츠 ID가 변경됨."""


def _load_progress(cur):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (PROGRESS_KEY,))
    row = cur.fetchone()
    try:
        value = json.loads(row["value"]) if row and row["value"] else {}
        return max(0, int(value.get("last_building_id") or 0))
    except (TypeError, ValueError):
        return 0


def _save_progress(cur, conn, building_id):
    value = json.dumps({
        "last_building_id": int(building_id),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    cur.execute(
        """
        INSERT INTO app_meta(key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value=EXCLUDED.value, updated_at=NOW()
        """,
        (PROGRESS_KEY, value),
    )
    conn.commit()


def _clear_progress(cur, conn):
    cur.execute("DELETE FROM app_meta WHERE key=%s", (PROGRESS_KEY,))
    conn.commit()


def _catalog_first_images(session, api_key, status_key, run_id, stats):
    """전국 숙박 목록을 읽어 contentId별 대표사진 URL을 반환한다."""
    try:
        first = _tour_request(session, "areaBasedList2", {
            "arrange": "A", "numOfRows": PAGE_SIZE, "pageNo": 1,
            "contentTypeId": 32,
        }, api_key)
    except DailyCapReached:
        stats["capped"] = True
        return {}
    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
    stats.update({"catalog_total": total, "catalog_page_count": page_count})
    result = {}
    for page_no in range(1, page_count + 1):
        if page_no == 1:
            data = first
        else:
            try:
                data = _tour_request(session, "areaBasedList2", {
                    "arrange": "A", "numOfRows": PAGE_SIZE,
                    "pageNo": page_no, "contentTypeId": 32,
                }, api_key)
            except DailyCapReached:
                stats["capped"] = True
                break
        items = _extract_items(data)
        for item in items:
            content_id = str(
                item.get("contentid") or item.get("contentId") or ""
            ).strip()
            first_image = str(
                item.get("firstimage") or item.get("firstImage")
                or item.get("firstimage2") or item.get("firstImage2") or ""
            ).strip()
            if content_id:
                result[content_id] = first_image
        stats["catalog_items"] += len(items)
        stats["catalog_pages"] = page_no
        _publish(status_key, run_id, stats)
    return result


def _tour_request(session, path, params, api_key):
    """실제 HTTP 시도 한 번마다 공유 일일 슬롯을 먼저 예약한다."""
    if _claim_daily_slot(CALLS_KEY, TOURAPI_DAILY_CAP) is None:
        raise DailyCapReached
    query = {
        "serviceKey": api_key,
        "MobileOS": "ETC",
        "MobileApp": "homenstay",
        "_type": "json",
        **params,
    }
    try:
        response = session.get(
            f"{TOURAPI_URL}/{path}",
            params=query,
            timeout=(TOURAPI_CONNECT_TIMEOUT, TOURAPI_READ_TIMEOUT),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise ProviderFatalError(
            f"TourAPI HTTP 오류 {status or '연결 실패'}"
        ) from exc
    except ValueError as exc:
        raise ProviderFatalError(
            "TourAPI JSON 응답을 해석하지 못했습니다."
        ) from exc
    _assert_tourapi_success(data)
    return data


def _tour_detail_images(session, content_id, api_key):
    return _extract_items(_tour_request(session, "detailImage2", {
        "contentId": content_id,
        "numOfRows": 100,
        "pageNo": 1,
        "imageYN": "Y",
        "subImageYN": "Y",
    }, api_key))


def _photo_rows(first_image, image_items, existing_urls=(), max_new=MAX_PHOTOS):
    """대표사진과 detailImage2 원본을 최대 20장까지 중복 없이 정리한다."""
    photos = []
    seen = {str(value) for value in existing_urls if value}
    max_new = max(0, min(int(max_new), MAX_PHOTOS))

    def add(url, photo_type="exterior"):
        value = str(url or "").strip()
        try:
            parsed = urlparse(value)
            hostname = (parsed.hostname or "").lower().rstrip(".")
        except Exception:
            return
        if (
            len(photos) >= max_new
            or parsed.scheme != "https"
            or not (
                hostname == "visitkorea.or.kr"
                or hostname.endswith(".visitkorea.or.kr")
                or hostname == "kakaocdn.net"
                or hostname.endswith(".kakaocdn.net")
            )
            or value in seen
        ):
            return
        seen.add(value)
        photos.append({"url": value, "photo_type": photo_type})

    add(first_image)
    for image in image_items:
        if not isinstance(image, dict):
            continue
        add(
            image.get("originimgurl") or image.get("originImgUrl"),
            _tour_photo_type(image.get("imgname") or image.get("imgName")),
        )
    return photos


def _publish(status_key, run_id, stats):
    status = _read_status(status_key) or {}
    if status.get("run_id") != run_id or status.get("state") != "running":
        raise RuntimeError("TourAPI 사진 수집 소유권을 상실했습니다.")
    status.update(stats)
    status["heartbeat_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_status(status_key, status, run_id)


def run(status_key, run_id, sleep_seconds=0.2):
    api_key = _tour_service_key()
    if not api_key:
        raise RuntimeError("TOUR_API_SERVICE_KEY 시크릿이 없습니다.")
    session = requests.Session()
    session.headers.update({"User-Agent": "homenstay-tourapi-images/1.0"})
    stats = {
        "source": "tourapi_images",
        "processed": 0,
        "updated": 0,
        "saved": 0,
        "skipped": 0,
        "failed": 0,
        "catalog_items": 0,
        "catalog_pages": 0,
        "catalog_total": 0,
        "catalog_page_count": 0,
        "capped": False,
    }
    first_images = _catalog_first_images(
        session, api_key, status_key, run_id, stats
    )
    if stats["capped"]:
        return stats
    conn = get_conn()
    cur = conn.cursor()
    try:
        last_id = _load_progress(cur)
        cur.execute(
            """
            SELECT f.building_id, f.provider_ref
            FROM building_photo_fetches f
            WHERE f.source='tourapi'
              AND f.provider_ref IS NOT NULL
              AND f.building_id > %s
              AND f.status IS DISTINCT FROM 'images_backfilled'
            ORDER BY f.building_id
            """,
            (last_id,),
        )
        targets = cur.fetchall()
        stats["eligible_total"] = len(targets)
        _publish(status_key, run_id, stats)
        for row in targets:
            content_id = str(row["provider_ref"] or "").strip()
            try:
                images = _tour_detail_images(session, content_id, api_key)
                # 공개 온디맨드 저장과 같은 건물별 트랜잭션 잠금을 사용한다.
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (7421, row["building_id"]),
                )
                cur.execute(
                    """
                    SELECT provider_ref
                    FROM building_photo_fetches
                    WHERE building_id=%s AND source='tourapi'
                    FOR UPDATE
                    """,
                    (row["building_id"],),
                )
                current_fetch = cur.fetchone()
                if (
                    not current_fetch
                    or str(current_fetch["provider_ref"] or "").strip()
                    != content_id
                ):
                    raise ProviderReferenceChanged(
                        "TourAPI 콘텐츠 ID가 수집 중 변경되었습니다. "
                        "새 ID로 다시 실행합니다."
                    )
                cur.execute(
                    """
                    SELECT photo_url FROM building_photos
                    WHERE building_id=%s AND source='tourapi'
                    ORDER BY id
                    """,
                    (row["building_id"],),
                )
                existing_urls = [item["photo_url"] for item in cur.fetchall()]
                photos = _photo_rows(
                    first_images.get(content_id),
                    images,
                    existing_urls=existing_urls,
                    max_new=MAX_PHOTOS - len(existing_urls),
                )
                if photos:
                    inserted = _insert_photos(
                        cur, row["building_id"], photos, "tourapi"
                    )
                    stats["updated"] += 1
                    stats["saved"] += inserted
                else:
                    # 정상 빈 응답은 기존 사진을 삭제하거나 빈 값으로 덮지 않는다.
                    stats["skipped"] += 1
                cur.execute(
                    """
                    UPDATE building_photo_fetches
                    SET status='images_backfilled',
                        last_attempt_at=NOW(),
                        error_message=NULL,
                        photo_available=%s
                    WHERE building_id=%s AND source='tourapi'
                    """,
                    (bool(existing_urls or photos), row["building_id"]),
                )
                conn.commit()
            except DailyCapReached:
                conn.rollback()
                stats["capped"] = True
                break
            except ProviderFatalError:
                conn.rollback()
                raise
            except ProviderReferenceChanged:
                conn.rollback()
                raise
            except Exception as exc:
                conn.rollback()
                stats["failed"] += 1
                cur.execute(
                    """
                    UPDATE building_photo_fetches
                    SET error_message=%s, last_attempt_at=NOW()
                    WHERE building_id=%s AND source='tourapi'
                    """,
                    (_redact(exc)[:300], row["building_id"]),
                )
                conn.commit()
                print(
                    f"[TourAPI 사진] building_id={row['building_id']} 실패: "
                    f"{_redact(exc)[:180]}",
                    flush=True,
                )
            stats["processed"] += 1
            _save_progress(cur, conn, row["building_id"])
            _publish(status_key, run_id, stats)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if not stats["capped"]:
            _clear_progress(cur, conn)
        return stats
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args()
    status = _read_status(args.status_key) or {}
    if (
        status.get("run_id") != args.run_id
        or status.get("state") != "running"
    ):
        raise SystemExit(75)
    error = None
    stats = None
    try:
        stats = run(args.status_key, args.run_id, max(0, args.sleep))
    except DailyCapReached:
        stats = {"source": "tourapi_images", "capped": True}
    except Exception as exc:
        error = _redact(exc)[:500]
        print(f"[TourAPI 사진] 실패: {error}", flush=True)
    status = _read_status(args.status_key) or {}
    if status.get("run_id") == args.run_id:
        status.update(stats or {})
        status.update({
            "state": "failed" if error else (
                "partial" if (stats or {}).get("capped") else "done"
            ),
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": error,
        })
        _write_status(args.status_key, status, args.run_id)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()