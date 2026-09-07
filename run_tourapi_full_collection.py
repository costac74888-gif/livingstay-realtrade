#!/usr/bin/env python3
"""TourAPI 숙박 카탈로그 매칭 후 사진을 재개 가능하게 일괄 수집한다."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime

from backfill_tourapi_images import run as backfill_images
from db import get_conn
from prewarm_tourapi_metadata import run as prewarm_metadata
from sync_building_photos import _read_status, _redact, _write_status


METADATA_STATUS_KEY = "building_photos_sync_status"
IMAGE_STATUS_KEY = "admin:tourapi_image_backfill:status"
MAX_ATTEMPTS = 4
RETRY_DELAYS = (60, 180, 600)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def start_status(status_key, run_id, source):
    payload = {
        "run_id": run_id,
        "state": "running",
        "source": source,
        "started_at": now_text(),
        "heartbeat_at": now_text(),
        "processed": 0,
        "saved": 0,
        "failed": 0,
        "error": None,
    }
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO app_meta(key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value=EXCLUDED.value, updated_at=NOW()
            """,
            (status_key, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def finish_status(status_key, run_id, stats, error=None):
    status = _read_status(status_key) or {}
    if status.get("run_id") != run_id:
        raise RuntimeError(f"{status_key} 실행 소유권을 상실했습니다.")
    status.update(stats or {})
    status.update({
        "state": "failed" if error else (
            "partial" if (stats or {}).get("capped") else "done"
        ),
        "finished_at": now_text(),
        "heartbeat_at": now_text(),
        "error": _redact(error)[:500] if error else None,
    })
    _write_status(status_key, status, run_id)


def run_with_retries(status_key, run_id, operation):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            stats = operation()
            finish_status(status_key, run_id, stats)
            return stats
        except Exception as exc:
            if attempt >= MAX_ATTEMPTS:
                finish_status(status_key, run_id, {}, exc)
                raise
            delay = RETRY_DELAYS[attempt - 1]
            status = _read_status(status_key) or {}
            status.update({
                "retry_attempt": attempt,
                "retry_wait_seconds": delay,
                "last_provider_error": _redact(exc)[:300],
                "heartbeat_at": now_text(),
            })
            _write_status(status_key, status, run_id)
            print(
                f"[TourAPI 전체수집] {attempt}차 실패, {delay}초 후 재시도: "
                f"{_redact(exc)[:180]}",
                flush=True,
            )
            time.sleep(delay)


def main():
    metadata_run_id = f"full-metadata-{uuid.uuid4().hex}"
    start_status(METADATA_STATUS_KEY, metadata_run_id, "tourapi_metadata")
    print("[TourAPI 전체수집] 전국 숙박 카탈로그 주소 매칭 시작", flush=True)
    metadata = run_with_retries(
        METADATA_STATUS_KEY,
        metadata_run_id,
        lambda: prewarm_metadata(METADATA_STATUS_KEY, metadata_run_id, 0.15),
    )
    if metadata.get("capped"):
        print("[TourAPI 전체수집] 일일 한도 도달로 카탈로그 단계 부분완료", flush=True)
        return

    image_run_id = f"full-images-{uuid.uuid4().hex}"
    start_status(IMAGE_STATUS_KEY, image_run_id, "tourapi_images")
    print(
        f"[TourAPI 전체수집] 주소 매칭 {metadata.get('matched_buildings', 0)}건 "
        "대표·다중사진 수집 시작",
        flush=True,
    )
    images = run_with_retries(
        IMAGE_STATUS_KEY,
        image_run_id,
        lambda: backfill_images(IMAGE_STATUS_KEY, image_run_id, 0.2),
    )
    print(
        f"[TourAPI 전체수집] 완료: 처리 {images.get('processed', 0)}건, "
        f"건물 갱신 {images.get('updated', 0)}건, "
        f"사진 저장 {images.get('saved', 0)}장",
        flush=True,
    )


if __name__ == "__main__":
    main()