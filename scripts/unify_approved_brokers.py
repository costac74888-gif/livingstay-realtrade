"""Explicit administrator-approved DATA cutover. No schema changes or email delivery.

Dry-run by default. Never infer consent to merge an existing users identity:
--approve-existing-users is required in addition to --apply for that case.
"""
import argparse
import json
import os

import psycopg2
from psycopg2.extras import RealDictCursor


def unify(conn, agent_ids, approve_existing=False, apply=False):
    result = {"agents": len(agent_ids), "created_users": 0, "existing_users": 0, "already_linked": 0}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SET LOCAL lock_timeout='5s'")
        cur.execute("SET LOCAL statement_timeout='30s'")
        cur.execute("SELECT pg_advisory_xact_lock(19641010, 1)")
        cur.execute("SELECT * FROM agents WHERE id=ANY(%s) ORDER BY id FOR UPDATE", (agent_ids,))
        agents = cur.fetchall()
        if len(agents) != len(set(agent_ids)):
            raise ValueError("Target account set changed; nothing applied")
        cur.execute("""SELECT md5(jsonb_agg(to_jsonb(a)-'password_hash' ORDER BY a.id)::text) AS checksum
            FROM agents a WHERE id=ANY(%s)""", (agent_ids,))
        profile_checksum = cur.fetchone()["checksum"]
        for a in agents:
            if a["status"] != "approved" or not (a.get("email") or "").strip():
                raise ValueError("Every target must be an approved broker with an email")
            cur.execute("""SELECT user_id,status FROM account_business_memberships
                WHERE business_table='agents' AND business_id=%s FOR UPDATE""", (a["id"],))
            owners = cur.fetchall()
            cur.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(%s) FOR UPDATE", (a["email"],))
            users = cur.fetchall()
            if len(users) > 1:
                raise ValueError("Ambiguous email ownership")
            user = users[0] if users else None
            if owners and (not user or any(o["user_id"] != user["id"] or o["status"] != "active" for o in owners)):
                raise ValueError("Conflicting or withdrawn business ownership")
            if user:
                if user["status"] != "active":
                    raise ValueError("Existing identity is inactive")
                if not owners and not approve_existing:
                    raise ValueError("Explicit administrator approval required to merge existing identity")
                if user["provider"] == "kakao" and not user["password_hash"]:
                    if not approve_existing or not a.get("password_hash"):
                        raise ValueError("Enabling social account password requires explicit approval and a credential")
                    # Keep kakao_id: OAuth resolves that ID irrespective of provider label.
                    cur.execute("UPDATE users SET password_hash=%s,provider='email' WHERE id=%s",
                                (a["password_hash"], user["id"]))
                elif user["provider"] != "email" or not user["password_hash"]:
                    raise ValueError("Unsupported credential owner")
                result["existing_users"] += 1
                result["already_linked"] += bool(owners)
                uid = user["id"]
            else:
                if not a.get("password_hash"):
                    raise ValueError("Cannot preserve missing broker credential")
                cur.execute("""INSERT INTO users
                    (email,password_hash,name,provider,status,phone,phone_verified,
                     email_alert_enabled,weekly_email_enabled)
                    VALUES (LOWER(%s),%s,%s,'email','active',%s,FALSE,FALSE,%s) RETURNING id""",
                    (a["email"].strip(), a["password_hash"], a.get("owner_name") or a["office_name"],
                     a.get("phone"), bool(a.get("weekly_email_enabled"))))
                uid = cur.fetchone()["id"]
                result["created_users"] += 1
            cur.execute("UPDATE account_role_memberships SET status='active' WHERE user_id=%s AND role='general'", (uid,))
            cur.execute("""INSERT INTO account_role_memberships(user_id,role,status,legacy_account_id)
                SELECT %s,'general','active',NULL WHERE NOT EXISTS(
                    SELECT 1 FROM account_role_memberships WHERE user_id=%s AND role='general')""", (uid,uid))
            cur.execute("""INSERT INTO account_role_memberships
                    (user_id,role,status,legacy_account_id) VALUES (%s,%s,'active',%s)
                    ON CONFLICT (user_id,role,legacy_account_id) DO UPDATE SET status='active'""",
                    (uid, "agent", a["id"]))
            cur.execute("""INSERT INTO account_business_memberships
                (user_id,role,business_table,business_id,status)
                VALUES (%s,'agent','agents',%s,'active')
                ON CONFLICT (user_id,role,business_table,business_id) DO UPDATE SET status='active'""",
                (uid, a["id"]))
            cur.execute("UPDATE agents SET password_hash=NULL WHERE id=%s", (a["id"],))
        cur.execute("""SELECT md5(jsonb_agg(to_jsonb(a)-'password_hash' ORDER BY a.id)::text) AS checksum
            FROM agents a WHERE id=ANY(%s)""", (agent_ids,))
        if cur.fetchone()["checksum"] != profile_checksum:
            raise ValueError("Broker business/profile data changed; refusing cutover")
        result["business_data_preserved"] = True
        # Preserve only non-sensitive counts as the administrator audit marker.
        cur.execute("""INSERT INTO app_meta(key,value) VALUES (%s,%s)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
            ("account_broker_unification", json.dumps(result)))
    conn.commit() if apply else conn.rollback()
    return dict(result, applied=apply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-ids", required=True, type=int, nargs="+")
    parser.add_argument("--expected-fingerprint", required=True)
    parser.add_argument("--approve-existing-users", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    # Use the explicit production connection, never silently fall back to dev.
    conn = psycopg2.connect(os.environ["PROD_DATABASE_URL"], connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT md5(system_identifier::text || '|' || current_database()) FROM pg_control_system()")
            if cur.fetchone()[0] != args.expected_fingerprint:
                raise ValueError("Production fingerprint mismatch")
        print(json.dumps(unify(conn, args.agent_ids, args.approve_existing_users, args.apply)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
