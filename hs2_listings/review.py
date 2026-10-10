"""Admin rights/public-data review, NOT building-use legal eligibility judgment."""
from uuid import uuid4
from hs2_design.domain import ContractError
from .validation import payload, revision


def review(repo, key, admin_id, expected, decision, note, *, rights=False, disclosure=False):
    if type(admin_id) is not int or admin_id <= 0:
        raise ContractError("ADMIN_REQUIRED")
    revision(expected)
    if decision not in {"approve", "reject"} or not isinstance(note, str) or not 1 <= len(note.strip()) <= 1000:
        raise ContractError("REVIEW_NOTE_REQUIRED")
    if decision == "approve" and (rights is not True or disclosure is not True):
        raise ContractError("EXPLICIT_REVIEW_REQUIRED")
    with repo.transaction() as c:
        row = repo.row(c, key)
        if row["revision"] != expected:
            raise ContractError("STALE_REVISION")
        if row["status"] != "submitted":
            raise ContractError("SUBMITTED_APPLICATION_REQUIRED")
        if repo.context_is_active(row["user_id"], row["context_id"]) is not True:
            raise ContractError("APPROVED_BUSINESS_REQUIRED")
        c.execute("SELECT active FROM hs2_fixture_legacy.users WHERE id=%s FOR SHARE", (row["user_id"],))
        user = c.fetchone()
        if not user or user[0] is not True:
            raise ContractError("ACTIVE_MEMBER_REQUIRED")
        if decision == "reject":
            c.execute("UPDATE hs2_dev.registration_applications SET status='rejected',reviewer_id=%s,review_note=%s,updated_at=clock_timestamp() WHERE id=%s",
                      (admin_id, note.strip(), key))
        else:
            data = payload(row["payload"], complete=True)
            c.execute("SELECT building_use FROM hs2_dev.candidates WHERE id=%s FOR UPDATE", (row["candidate_id"],))
            building_use = c.fetchone()[0]
            c.execute("""SELECT payload->>'space_scope',payload->>'space_label' FROM hs2_dev.registration_applications
                WHERE candidate_id=%s AND status='approved' AND approved_until>clock_timestamp() AND id<>%s""",
                (row["candidate_id"], key))
            for scope, label in c.fetchall():
                if scope == "whole" or data["space_scope"] == "whole" or label.casefold() == data["space_label"].casefold():
                    raise ContractError("ACTIVE_SPACE_CONFLICT")
            c.execute("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s) ON CONFLICT(candidate_id) DO NOTHING",
                      (str(uuid4()), row["candidate_id"]))
            c.execute("SELECT id FROM hs2_dev.registered_buildings WHERE candidate_id=%s", (row["candidate_id"],))
            building = str(c.fetchone()[0])
            unit_key = "whole" if data["space_scope"] == "whole" else "unit:" + data["space_label"].casefold()
            c.execute("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,%s) ON CONFLICT(registered_building_id,unit_key) DO NOTHING",
                      (str(uuid4()), building, unit_key))
            c.execute("SELECT id FROM hs2_dev.inventory_pools WHERE registered_building_id=%s AND unit_key=%s", (building, unit_key))
            pool = str(c.fetchone()[0])
            # Evidence is a review receipt, never a claim of government permission.
            evidence = f"operator-declaration/admin-review:{key}:{expected}:{admin_id}"
            c.execute("""INSERT INTO hs2_dev.registration_grants VALUES(%s,%s,%s,'operator',%s,true)
                ON CONFLICT(registered_building_id,user_id,role)
                DO UPDATE SET approved=true,rights_evidence=EXCLUDED.rights_evidence RETURNING id""",
                (str(uuid4()), building, row["user_id"], evidence))
            grant = str(c.fetchone()[0])
            c.execute("INSERT INTO hs2_dev.grant_units VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (grant, pool, building))
            listing, public, classification = (str(uuid4()) for _ in range(3))
            c.execute("SELECT set_config('hs2.actor_user',%s,true)", (str(row["user_id"]),))
            c.execute("""INSERT INTO hs2_dev.stay_listings(id,public_id,registered_building_id,creator_user_id,pool_id,grant_id)
                VALUES(%s,%s,%s,%s,%s,%s)""", (listing, public, building, row["user_id"], pool, grant))
            c.execute("INSERT INTO hs2_dev.classification_decisions VALUES(%s,%s,%s,%s,%s,%s,'operator-declared')",
                      (classification, listing, data["stay_kind"], evidence, f"application-revision:{expected}", building_use))
            c.execute("UPDATE hs2_dev.stay_listings SET classification_id=%s,status='published' WHERE id=%s", (classification, listing))
            c.execute("""UPDATE hs2_dev.registration_applications SET status='approved',listing_id=%s,public_id=%s,
                reviewed_revision=revision,reviewer_id=%s,review_note=%s,approved_until=clock_timestamp()+interval '365 days',
                updated_at=clock_timestamp() WHERE id=%s""", (listing, public, admin_id, note.strip(), key))
        result = repo.row(c, key)
        repo.event(c, result, admin_id, "admin", decision)
        return result


def public_rows(repo):
    with repo.transaction() as c:
        c.execute("""SELECT v.public_id,v.stay_kind,a.user_id,a.context_id
            FROM hs2_dev.limited_stay_listings v JOIN hs2_dev.registration_applications a ON a.public_id=v.public_id
            JOIN hs2_dev.stay_listings l ON l.id=a.listing_id
            JOIN hs2_dev.registration_grants g ON g.id=l.grant_id
            JOIN hs2_fixture_legacy.users u ON u.id=a.user_id
            WHERE a.status='approved' AND a.reviewed_revision=a.revision
              AND a.approved_until>clock_timestamp() AND l.status='published' AND g.approved AND u.active""")
        return [dict(public_id=str(r[0]), stay_kind=r[1], location_precision="withheld")
                for r in c.fetchall() if repo.context_is_active(r[2], r[3]) is True]
