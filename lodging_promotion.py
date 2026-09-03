"""정부 숙박 8종의 운영 기준 승격 manifest를 개발 DB에 고정한다."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from copy import deepcopy
from collections import Counter, defaultdict

import psycopg2
import psycopg2.extras

from addr_norm import get_building_jibun_key, normalize_jibun_prefix, normalize_road_prefix
from db import get_conn
from lodging_data_contract import GOVERNMENT_LODGING_SOURCES
from lodging_staging import (
    _database_fingerprint,
    _require_admin_actor,
    assert_development_connection,
    assert_development_staging,
)
from validate_lodging_all_production_delta import classify_production_match
from validate_lodging_approval_promotion import classify_registry_action


REVIEW_DECISIONS = {
    "exclude": "제외",
    "include_unclassified_history": "미분류 역사 원장 포함",
}


def _canonical_hash(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_target_admission(targets, *, allow_manual_review):
    permits = []
    manual_review_count = 0
    for target in targets:
        payload = target.get("payload") or {}
        permit_number = payload.get("permit_number")
        if not permit_number:
            raise RuntimeError("manifest 대상에 permit_number가 없습니다.")
        permits.append(permit_number)
        if payload.get("row_state") == "review_required":
            manual_review_count += 1
    if len(permits) != len(set(permits)):
        duplicates = [
            permit
            for permit, count in Counter(permits).items()
            if count > 1
        ]
        raise RuntimeError(
            "manifest 대상에 중복 permit_number가 있습니다: "
            + ", ".join(sorted(duplicates)[:5])
        )
    if manual_review_count and not allow_manual_review:
        raise RuntimeError(
            f"수동 검토 미해결 행 {manual_review_count}건이 있어 진행할 수 없습니다."
        )
    return manual_review_count


def _apply_review_decision(target, decision, *, note=None):
    """수동검토 대상의 새 manifest용 payload를 만든다.

    기존 target/payload를 변경하지 않고, 포함 결정인 경우에만 검토 상태를
    해소한 복사본을 반환한다. 제외 결정은 None을 반환해 새 manifest에서
    대상 행 자체를 제거한다.
    """
    if decision not in REVIEW_DECISIONS:
        raise ValueError("수동검토 결정은 제외 또는 미분류 역사 원장 포함이어야 합니다.")
    if target.get("payload", {}).get("row_state") != "review_required":
        raise ValueError("이미 해결된 수동검토 행입니다.")
    if decision == "exclude":
        return None
    payload = target["payload"]
    if (
        payload.get("service_category") != "미분류"
        or payload.get("status_bucket") != "closed"
        or payload.get("raw_hygiene_type")
    ):
        raise ValueError(
            "미분류 역사 원장 포함은 업태가 비어 있는 폐업 원장에만 사용할 수 있습니다."
        )
    resolved = deepcopy(target)
    payload = resolved["payload"]
    payload["original_row_state"] = payload.get("row_state")
    payload["original_review_reason"] = payload.get("review_reason")
    payload["row_state"] = "validated"
    payload["review_reason"] = None
    payload["review_resolution"] = {
        "decision": decision,
        "decision_label": REVIEW_DECISIONS[decision],
        "note": note or None,
    }
    return resolved


def _fetch_latest_staging(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (source_key)
                   id, source_key, reference_date, file_sha256, status,
                   total_rows, valid_rows, review_rows
              FROM lodging_source_batches
             ORDER BY source_key, reference_date DESC, created_at DESC, id DESC
            """
        )
        batches = {row["source_key"]: dict(row) for row in cur.fetchall()}
        missing = set(GOVERNMENT_LODGING_SOURCES) - set(batches)
        if missing:
            raise RuntimeError(
                "최신 staging 배치가 없는 원본: " + ", ".join(sorted(missing))
            )
        batch_ids = [batches[key]["id"] for key in GOVERNMENT_LODGING_SOURCES]
        cur.execute(
            """
            SELECT sr.id AS source_row_id, sr.batch_id, sb.source_key,
                   snapshot_key,
                   permit_number, authority_code, source_permit_number,
                   biz_name, raw_hygiene_type, service_category,
                   legacy_lodging_type, raw_status, status_bucket,
                   road_address, jibun_address, raw_record,
                   row_state, review_reason, diff_kind
              FROM lodging_source_rows sr
              JOIN lodging_source_batches sb ON sb.id=sr.batch_id
             WHERE sr.batch_id = ANY(%s)
               AND row_state IN ('validated', 'review_required')
             ORDER BY sr.batch_id, row_number
            """,
            (batch_ids,),
        )
        return batches, [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()


def _fetch_production_snapshot(conn=None):
    owns_connection = conn is None
    if owns_connection:
        production_url = os.environ.get("PROD_DATABASE_URL")
        if not production_url:
            raise RuntimeError(
                "PROD_DATABASE_URL이 없어 운영 기준 manifest를 만들 수 없습니다."
            )
        conn = psycopg2.connect(production_url, connect_timeout=10)
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        fingerprint = _database_fingerprint(conn)
        cur.execute(
            """
            SELECT permit_number, biz_name, biz_status_name, room_count,
                   hygiene_type, applied_building_id, road_address,
                   jibun_address, updated_at
              FROM lodging_registry
             ORDER BY permit_number
            """
        )
        registry_rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, road_address, jibun_address, sgg_cd, umd_nm, jibun,
                   lat, lng, lodging_type
              FROM master_buildings
             ORDER BY id
            """
        )
        building_rows = [dict(row) for row in cur.fetchall()]
        baseline_fingerprint = _canonical_hash(
            {
                "database": fingerprint,
                "registry": registry_rows,
                "buildings": building_rows,
            }
        )
        return registry_rows, building_rows, baseline_fingerprint, fingerprint
    finally:
        cur.close()
        if owns_connection:
            conn.close()


def _build_targets(staging_rows, registry_rows, building_rows):
    registry = {
        row["permit_number"]: row
        for row in registry_rows
        if row.get("permit_number")
    }
    road_index = defaultdict(set)
    jibun_index = defaultdict(set)
    for building in building_rows:
        road_key = normalize_road_prefix(building.get("road_address"))
        jibun_key = get_building_jibun_key(building)
        if road_key:
            road_index[road_key].add(building["id"])
        if jibun_key:
            jibun_index[jibun_key].add(building["id"])

    targets = []
    actions = Counter()
    match_counts = Counter()
    status_counts = Counter()
    existing_links_preserved = 0
    manual_review_targets = 0
    for row in staging_rows:
        permit_number = row.get("permit_number")
        if not permit_number:
            continue
        existing = registry.get(permit_number)
        if existing and row.get("diff_kind") not in {"changed", "status_change"}:
            continue
        action = classify_registry_action(row, existing)
        if action == "unchanged":
            continue
        match_state = None
        production_building_id = None
        existing_applied_building_id = None
        if existing:
            existing_applied_building_id = existing.get("applied_building_id")
            if existing_applied_building_id:
                existing_links_preserved += 1
        else:
            match_state, _candidate_ids, production_building_id = (
                classify_production_match(
                    normalize_road_prefix(row.get("road_address")),
                    normalize_jibun_prefix(row.get("jibun_address")),
                    road_index,
                    jibun_index,
                )
            )
            match_counts[match_state] += 1
        payload = {
            key: value
            for key, value in row.items()
            if key not in {"source_row_id", "batch_id"}
        }
        payload["production_match_state"] = match_state
        payload["production_building_id"] = production_building_id
        payload["existing_applied_building_id"] = existing_applied_building_id
        targets.append(
            {
                "source_row_id": row["source_row_id"],
                "action": action,
                "production_match_state": match_state,
                "production_building_id": production_building_id,
                "existing_applied_building_id": existing_applied_building_id,
                "payload": payload,
            }
        )
        actions[action] += 1
        status_counts[row.get("status_bucket") or "unknown"] += 1
        if row.get("row_state") == "review_required":
            manual_review_targets += 1
    return targets, {
        "action_counts": dict(actions),
        "new_match_counts": dict(match_counts),
        "status_counts": dict(status_counts),
        "existing_links_preserved": existing_links_preserved,
        "manual_review_targets": manual_review_targets,
        "would_auto_create_master_buildings": 0,
    }


def create_production_baseline_manifest(*, created_by=None):
    """운영 기준 승격 대상을 계산해 개발 DB draft로 고정한다."""
    assert_development_staging()
    if created_by is not None:
        created_by = _require_admin_actor(created_by, "생성")
    dev_conn = get_conn()
    assert_development_connection(dev_conn)
    try:
        batches, staging_rows = _fetch_latest_staging(dev_conn)
        registry_rows, building_rows, baseline_fingerprint, production_fingerprint = (
            _fetch_production_snapshot()
        )
        if _database_fingerprint(dev_conn) == production_fingerprint:
            raise RuntimeError("개발 DB와 운영 DB가 같아 manifest 생성을 중단했습니다.")
        targets, summary = _build_targets(
            staging_rows,
            registry_rows,
            building_rows,
        )
        _validate_target_admission(targets, allow_manual_review=True)
        source_batch_ids = {
            key: int(batches[key]["id"]) for key in GOVERNMENT_LODGING_SOURCES
        }
        source_files = {
            key: {
                "reference_date": str(batches[key]["reference_date"]),
                "file_sha256": batches[key]["file_sha256"],
                "status": batches[key]["status"],
                "total_rows": int(batches[key]["total_rows"] or 0),
                "valid_rows": int(batches[key]["valid_rows"] or 0),
                "review_rows": int(batches[key]["review_rows"] or 0),
            }
            for key in GOVERNMENT_LODGING_SOURCES
        }
        target_payload_sha256 = _canonical_hash(targets)
        manifest_key = "LODGING-PROMOTION:" + _canonical_hash(
            {
                "source_batch_ids": source_batch_ids,
                "production_baseline_fingerprint": baseline_fingerprint,
                "target_payload_sha256": target_payload_sha256,
            }
        )
        result = {
            **summary,
            "production_registry_rows": len(registry_rows),
            "production_master_buildings": len(building_rows),
            "staging_valid_rows": len(staging_rows),
            "target_rows": len(targets),
            "new_permits": int(summary["action_counts"].get("insert", 0)),
            "source_files": source_files,
            "production_writes": 0,
        }
        run_id = secrets.token_hex(16)
        cur = dev_conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO lodging_promotion_manifests (
                    manifest_key, status, source_batch_ids,
                    production_baseline_fingerprint, target_payload_sha256,
                    row_count, result, run_id, created_by
                ) VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (manifest_key) DO NOTHING
                RETURNING id
                """,
                (
                    manifest_key,
                    psycopg2.extras.Json(source_batch_ids),
                    baseline_fingerprint,
                    target_payload_sha256,
                    len(targets),
                    psycopg2.extras.Json(result),
                    run_id,
                    created_by,
                ),
            )
            inserted = cur.fetchone()
            if not inserted:
                cur.execute(
                    """
                    SELECT id, manifest_key, status, row_count, result, run_id
                      FROM lodging_promotion_manifests
                     WHERE manifest_key=%s
                    """,
                    (manifest_key,),
                )
                existing = dict(cur.fetchone())
                dev_conn.commit()
                existing["created"] = False
                return existing
            manifest_id = inserted["id"]
            values = [
                (
                    manifest_id,
                    target["source_row_id"],
                    target["action"],
                    target["production_match_state"],
                    target["production_building_id"],
                    target["existing_applied_building_id"],
                    psycopg2.extras.Json(target["payload"]),
                )
                for target in targets
            ]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO lodging_promotion_rows (
                    promotion_manifest_id, source_row_id, action,
                    production_match_state, production_building_id,
                    existing_applied_building_id, payload
                ) VALUES %s
                """,
                values,
                page_size=1000,
            )
            dev_conn.commit()
            return {
                "id": manifest_id,
                "manifest_key": manifest_key,
                "status": "draft",
                "row_count": len(targets),
                "result": result,
                "run_id": run_id,
                "created": True,
            }
        except Exception:
            dev_conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        dev_conn.close()


def create_resolved_production_manifest(
    manifest_id,
    source_row_id,
    *,
    decision,
    decided_by,
    note=None,
):
    """수동검토 결정을 기존 manifest와 분리된 새 버전으로 고정한다."""
    assert_development_staging()
    if decision not in REVIEW_DECISIONS:
        raise ValueError("수동검토 결정은 제외 또는 미분류 역사 원장 포함이어야 합니다.")
    decided_by = _require_admin_actor(decided_by, "수동검토 해결")
    note = (str(note).strip() if note is not None else "") or None
    if note and len(note) > 500:
        raise ValueError("수동검토 메모는 500자 이내여야 합니다.")

    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, manifest_key, status, source_batch_ids,
                   production_baseline_fingerprint, target_payload_sha256,
                   row_count, result, run_id, version_no
              FROM lodging_promotion_manifests
             WHERE id=%s
             FOR UPDATE
            """,
            (manifest_id,),
        )
        base = cur.fetchone()
        if not base:
            raise ValueError("운영 기준 manifest를 찾을 수 없습니다.")
        if base["status"] != "draft":
            raise ValueError("수동검토 해결은 승인 전 draft manifest에서만 할 수 있습니다.")

        cur.execute(
            """
            SELECT id
              FROM lodging_promotion_review_decisions
             WHERE base_manifest_id=%s AND source_row_id=%s
            """,
            (manifest_id, source_row_id),
        )
        if cur.fetchone():
            raise ValueError("이 manifest의 수동검토 행은 이미 해결 기록이 있습니다.")

        cur.execute(
            """
            SELECT id
              FROM lodging_promotion_manifests
             WHERE parent_manifest_id=%s
             LIMIT 1
            """,
            (manifest_id,),
        )
        if cur.fetchone():
            raise ValueError(
                "새 버전이 이미 생성된 오래된 manifest입니다. 최신 manifest에서 계속 처리하세요."
            )

        cur.execute(
            """
            SELECT source_row_id, action, production_match_state,
                   production_building_id, existing_applied_building_id, payload
              FROM lodging_promotion_rows
             WHERE promotion_manifest_id=%s
             ORDER BY source_row_id
            """,
            (manifest_id,),
        )
        targets = [
            {
                "source_row_id": row["source_row_id"],
                "action": row["action"],
                "production_match_state": row["production_match_state"],
                "production_building_id": row["production_building_id"],
                "existing_applied_building_id": row["existing_applied_building_id"],
                "payload": dict(row["payload"]),
            }
            for row in cur.fetchall()
        ]
        _validate_target_admission(targets, allow_manual_review=True)
        if len(targets) != int(base["row_count"]):
            raise RuntimeError("기존 manifest 행 수가 변경되었습니다.")
        if _canonical_hash(targets) != base["target_payload_sha256"]:
            raise RuntimeError("기존 manifest payload가 생성 이후 변경되었습니다.")

        target = next(
            (item for item in targets if int(item["source_row_id"]) == int(source_row_id)),
            None,
        )
        if not target:
            raise ValueError("manifest에서 수동검토 대상 행을 찾을 수 없습니다.")
        resolved = _apply_review_decision(target, decision, note=note)
        resolved_targets = [
            item
            for item in targets
            if int(item["source_row_id"]) != int(source_row_id)
        ]
        if resolved is not None:
            resolved_targets.append(resolved)
        resolved_targets.sort(key=lambda item: int(item["source_row_id"]))
        remaining_manual_reviews = _validate_target_admission(
            resolved_targets,
            allow_manual_review=True,
        )

        base_result = dict(base["result"] or {})
        base_resolutions = list(base_result.get("review_resolutions") or [])
        resolution = {
            "source_row_id": int(source_row_id),
            "permit_number": target["payload"].get("permit_number"),
            "decision": decision,
            "decision_label": REVIEW_DECISIONS[decision],
            "note": note,
        }
        action_counts = Counter(item["action"] for item in resolved_targets)
        match_counts = Counter(
            item["production_match_state"]
            for item in resolved_targets
            if item["production_match_state"]
        )
        status_counts = Counter(
            item["payload"].get("status_bucket") or "unknown"
            for item in resolved_targets
        )
        result = {
            **base_result,
            "manifest_version": int(base["version_no"] or 1) + 1,
            "parent_manifest_id": int(manifest_id),
            "target_rows": len(resolved_targets),
            "action_counts": dict(action_counts),
            "new_match_counts": dict(match_counts),
            "status_counts": dict(status_counts),
            "existing_links_preserved": sum(
                bool(item["existing_applied_building_id"])
                for item in resolved_targets
            ),
            "new_permits": int(action_counts.get("insert", 0)),
            "manual_review_targets": remaining_manual_reviews,
            "review_resolutions": [*base_resolutions, resolution],
            "production_writes": 0,
        }
        target_payload_sha256 = _canonical_hash(resolved_targets)
        manifest_key = "LODGING-PROMOTION:" + _canonical_hash(
            {
                "parent_manifest_id": int(manifest_id),
                "production_baseline_fingerprint": base[
                    "production_baseline_fingerprint"
                ],
                "target_payload_sha256": target_payload_sha256,
            }
        )
        run_id = secrets.token_hex(16)
        cur.execute(
            """
            INSERT INTO lodging_promotion_manifests (
                manifest_key, status, source_batch_ids,
                production_baseline_fingerprint, target_payload_sha256,
                row_count, result, run_id, created_by,
                parent_manifest_id, version_no
            ) VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                manifest_key,
                psycopg2.extras.Json(base["source_batch_ids"]),
                base["production_baseline_fingerprint"],
                target_payload_sha256,
                len(resolved_targets),
                psycopg2.extras.Json(result),
                run_id,
                decided_by,
                manifest_id,
                int(base["version_no"] or 1) + 1,
            ),
        )
        new_manifest_id = cur.fetchone()["id"]
        values = [
            (
                new_manifest_id,
                item["source_row_id"],
                item["action"],
                item["production_match_state"],
                item["production_building_id"],
                item["existing_applied_building_id"],
                psycopg2.extras.Json(item["payload"]),
            )
            for item in resolved_targets
        ]
        if values:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO lodging_promotion_rows (
                    promotion_manifest_id, source_row_id, action,
                    production_match_state, production_building_id,
                    existing_applied_building_id, payload
                ) VALUES %s
                """,
                values,
                page_size=1000,
            )
        cur.execute(
            """
            INSERT INTO lodging_promotion_review_decisions (
                source_row_id, base_manifest_id, resulting_manifest_id,
                decision, decision_note, decided_by
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                source_row_id,
                manifest_id,
                new_manifest_id,
                decision,
                note,
                decided_by,
            ),
        )
        conn.commit()
        return {
            "id": new_manifest_id,
            "manifest_key": manifest_key,
            "status": "draft",
            "row_count": len(resolved_targets),
            "result": result,
            "run_id": run_id,
            "parent_manifest_id": manifest_id,
            "version_no": int(base["version_no"] or 1) + 1,
            "review_resolution": resolution,
            "created": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def approve_production_manifest(manifest_id, *, approved_by):
    """운영 기준 manifest에 사람의 승인만 기록한다."""
    approved_by = _require_admin_actor(approved_by, "승인")
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS count
              FROM lodging_promotion_rows
             WHERE promotion_manifest_id=%s
               AND payload->>'row_state'='review_required'
            """,
            (manifest_id,),
        )
        unresolved = int(cur.fetchone()["count"])
        if unresolved:
            raise ValueError(
                f"수동 검토 미해결 행 {unresolved}건을 먼저 처리해야 합니다."
            )
        cur.execute(
            """
            UPDATE lodging_promotion_manifests
               SET status='approved', approved_by=%s, approved_at=NOW()
             WHERE id=%s AND status='draft'
             RETURNING id, status, row_count, run_id, result
            """,
            (approved_by, manifest_id),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("승인 초안이 아니거나 이미 처리된 manifest입니다.")
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def run_production_manifest_dry_run(manifest_id):
    """고정 payload와 운영 기준선이 그대로인지 확인하고 운영에는 쓰지 않는다."""
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, status, production_baseline_fingerprint,
                   target_payload_sha256, row_count, result, run_id
              FROM lodging_promotion_manifests
             WHERE id=%s
             FOR UPDATE
            """,
            (manifest_id,),
        )
        manifest = cur.fetchone()
        if not manifest:
            raise ValueError("운영 기준 manifest를 찾을 수 없습니다.")
        if manifest["status"] not in {"approved", "dry_run", "failed"}:
            raise ValueError("관리자 승인 완료된 manifest만 dry-run할 수 있습니다.")
        cur.execute(
            """
            SELECT source_row_id, action, production_match_state,
                   production_building_id, existing_applied_building_id, payload
              FROM lodging_promotion_rows
             WHERE promotion_manifest_id=%s
             ORDER BY source_row_id
            """,
            (manifest_id,),
        )
        targets = [
            {
                "source_row_id": row["source_row_id"],
                "action": row["action"],
                "production_match_state": row["production_match_state"],
                "production_building_id": row["production_building_id"],
                "existing_applied_building_id": row["existing_applied_building_id"],
                "payload": dict(row["payload"]),
            }
            for row in cur.fetchall()
        ]
        _validate_target_admission(targets, allow_manual_review=False)
        if len(targets) != int(manifest["row_count"]):
            raise RuntimeError("manifest 고정 행 수가 변경되었습니다.")
        if _canonical_hash(targets) != manifest["target_payload_sha256"]:
            raise RuntimeError("manifest payload가 생성 이후 변경되었습니다.")
        result = dict(manifest["result"] or {})
        actual_new_permits = sum(target["action"] == "insert" for target in targets)
        try:
            expected_new_permits = int(result["new_permits"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("manifest 신규 permit 기대 수가 올바르지 않습니다.") from None
        if actual_new_permits != expected_new_permits:
            raise RuntimeError(
                "manifest 신규 permit 기대 수가 고정 payload와 일치하지 않습니다."
            )
        _registry, _buildings, current_fingerprint, _db_fingerprint = (
            _fetch_production_snapshot()
        )
        if current_fingerprint != manifest["production_baseline_fingerprint"]:
            raise RuntimeError(
                "운영 기준선이 manifest 생성 이후 변경되어 다시 생성해야 합니다."
            )
        result.update(
            {
                "dry_run_verified": True,
                "payload_hash_verified": True,
                "production_baseline_unchanged": True,
                "production_writes": 0,
                "applied": False,
            }
        )
        cur.execute(
            """
            UPDATE lodging_promotion_manifests
               SET status='dry_run', result=%s, error=NULL,
                   started_at=NOW(), heartbeat_at=NOW(), finished_at=NOW()
             WHERE id=%s AND run_id=%s
             RETURNING id, status, row_count, result, run_id
            """,
            (
                psycopg2.extras.Json(result),
                manifest_id,
                manifest["run_id"],
            ),
        )
        updated = cur.fetchone()
        if not updated:
            raise RuntimeError("manifest 실행 소유권이 변경되었습니다.")
        conn.commit()
        return dict(updated)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
