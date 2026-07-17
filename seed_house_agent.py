# -*- coding: utf-8 -*-
"""
seed_house_agent.py — 하우스 계정(홈스퀘어부동산중개법인)을 agents에 1회 시드.

매물의뢰 라우팅 3순위(전속 없음 + 지역 중개사 없음)일 때 의뢰를 받아줄
회사 자체 계정. agent_buildings에는 절대 등록하지 않는다 —
전속 관계가 없으므로 B화면 "전속중개사" 카드에는 자동으로 노출되지 않는다.

같은 phone 또는 office_name의 approved/pending 계정이 이미 있으면 아무것도 하지 않는다(재실행 안전).
실행: python seed_house_agent.py
"""
import re
import secrets

from werkzeug.security import generate_password_hash

from db import get_conn

OFFICE_NAME = "홈스퀘어부동산중개법인"
OWNER_NAME = "홈스퀘어"
PHONE = "010-8946-3305"
EMAIL = "housesquare@example.com"
REG_NUMBER = "HOUSE-ACCOUNT-001"  # 하우스 계정 전용 내부 식별자 (실제 중개등록번호 아님)


def main():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, subdomain_slug FROM agents
               WHERE (phone = %s OR office_name = %s) AND status IN ('approved', 'pending')""",
            [PHONE, OFFICE_NAME],
        )
        row = cur.fetchone()
        if row:
            print(f"이미 존재 — agents.id={row['id']}, slug={row['subdomain_slug']} (생성 건너뜀)")
            return

        # subdomain_slug: 승인 플로우와 동일 규칙(전화번호 숫자, 중복 시 -2, -3 …)
        base_slug = re.sub(r"\D", "", PHONE)
        slug = base_slug
        n = 2
        while True:
            cur.execute("SELECT 1 FROM agents WHERE subdomain_slug = %s", [slug])
            if not cur.fetchone():
                break
            slug = f"{base_slug}-{n}"
            n += 1

        alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
        temp_pw = "".join(secrets.choice(alphabet) for _ in range(8))

        cur.execute(
            """
            INSERT INTO agents (office_name, owner_name, reg_number, phone, email,
                                status, subdomain_slug, password_hash, approved_at)
            VALUES (%s, %s, %s, %s, %s, 'approved', %s, %s, NOW())
            RETURNING id
            """,
            [OFFICE_NAME, OWNER_NAME, REG_NUMBER, PHONE, EMAIL, slug,
             generate_password_hash(temp_pw)],
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        print(f"하우스 계정 생성 완료 — agents.id={new_id}")
        print(f"  office_name : {OFFICE_NAME}")
        print(f"  로그인 이메일: {EMAIL}")
        print(f"  임시비밀번호 : {temp_pw}  (최초 로그인 후 변경 권장)")
        print(f"  slug        : {slug}  (/agent/{slug})")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
