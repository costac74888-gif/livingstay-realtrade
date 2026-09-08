#!/usr/bin/env python3
"""관리자 영구삭제 전 매물 원본과 연관 이력이 보존되는지 확인한다."""

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import _archive_listing_requests_before_delete
from db import get_conn


def main():
    conn = get_conn()
    cur = conn.cursor()
    user_id = listing_id = archive_id = None
    try:
        suffix = uuid.uuid4().hex
        cur.execute(
            """
            INSERT INTO users (email, password_hash, name, phone, phone_verified)
            VALUES (%s, 'test-only', '삭제보관검사', '01000000000', TRUE)
            RETURNING id
            """,
            [f"listing-archive-{suffix}@example.invalid"],
        )
        user_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO listing_requests
                (user_id, master_building_id, deal_type, desired_price,
                 contact_phone, deal_mode, status, description)
            SELECT %s, id, '매매', '테스트 희망가', '01000000000',
                   'broker', 'submitted', '삭제 전 원본'
              FROM master_buildings
             ORDER BY id
             LIMIT 1
            RETURNING id
            """,
            [user_id],
        )
        listing_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO listing_request_history
                (listing_request_id, action, after_data)
            VALUES (%s, 'created', '{"test": true}'::jsonb)
            """,
            [listing_id],
        )

        archived = _archive_listing_requests_before_delete(
            cur, [listing_id], "automated_test", None
        )
        assert archived == 1
        cur.execute(
            """
            SELECT id,
                   request_snapshot->>'description' AS description,
                   jsonb_array_length(related_snapshot->'history') AS history_count,
                   deletion_source
              FROM listing_request_deletion_archive
             WHERE listing_request_id = %s
             ORDER BY id DESC
             LIMIT 1
            """,
            [listing_id],
        )
        row = cur.fetchone()
        assert row and row["description"] == "삭제 전 원본", row
        assert row["history_count"] == 1, row
        assert row["deletion_source"] == "automated_test", row
        archive_id = row["id"]
        conn.rollback()
        print("OK  관리자 삭제 전 매물 원본·이력 복구 보관")
    finally:
        conn.rollback()
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()