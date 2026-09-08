"""매물의뢰 철회가 원본과 이력을 보존하는지 확인한다."""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, get_conn


def main():
    tag = str(time.time_ns())
    conn = get_conn()
    cur = conn.cursor()
    user_id = listing_id = None
    try:
        cur.execute("SELECT id FROM master_buildings ORDER BY id LIMIT 1")
        building = cur.fetchone()
        assert building, "검사에 사용할 건물이 없습니다."
        cur.execute(
            """
            INSERT INTO users (email, password_hash, name, provider, status)
            VALUES (%s, 'test', '철회 상태 검사', 'local', 'active')
            RETURNING id
            """,
            [f"withdraw-state-{tag}@example.invalid"],
        )
        user_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO listing_requests
                (user_id, master_building_id, deal_type, contact_phone, deal_mode, status)
            VALUES (%s, %s, '매매', '01000000000', 'broker', 'submitted')
            RETURNING id
            """,
            [user_id, building["id"]],
        )
        listing_id = cur.fetchone()["id"]
        conn.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = user_id
            response = client.post(f"/api/listing-requests/{listing_id}/withdraw")
            payload = response.get_json() or {}
            assert response.status_code == 200
            assert payload.get("status") == "철회됨"

        cur.execute(
            "SELECT status FROM listing_requests WHERE id = %s",
            [listing_id],
        )
        assert cur.fetchone()["status"] == "철회됨"
        cur.execute(
            """
            SELECT action, before_data, after_data
            FROM listing_request_history
            WHERE listing_request_id = %s
            ORDER BY id DESC LIMIT 1
            """,
            [listing_id],
        )
        history = cur.fetchone()
        assert history and history["action"] == "withdrawn"
        assert history["before_data"]["status"] == "submitted"
        assert history["after_data"]["status"] == "철회됨"
        print("OK  매물의뢰 철회 상태·원본·이력 보존")
    finally:
        conn.rollback()
        if listing_id:
            cur.execute(
                "DELETE FROM listing_request_history WHERE listing_request_id = %s",
                [listing_id],
            )
            cur.execute("DELETE FROM listing_requests WHERE id = %s", [listing_id])
        if user_id:
            cur.execute("DELETE FROM users WHERE id = %s", [user_id])
        conn.commit()
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()