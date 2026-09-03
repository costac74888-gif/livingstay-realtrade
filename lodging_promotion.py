"""정부 숙박 8종의 운영 기준 승격 manifest를 개발 DB에 고정한다."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from copy import deepcopy
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extras

from addr_norm import get_building_jibun_key, normalize_jibun_prefix, normalize_road_prefix
from db import get_conn
from lodging_data_contract import (
    GOVERNMENT_LODGING_SOURCES,
    STATUS_CLOSED,
    STATUS_TEMPORARILY_CLOSED,
)
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
_COMPARISON_FIELDS = (
    ("biz_name", "biz_name"),
    ("road_address", "road_address"),
    ("jibun_address", "jibun_address"),
    ("raw_status", "biz_status_name"),
    ("raw_hygiene_type", "hygiene_type"),
)
_HISTORICAL_STATUS_BUCKETS = {
    STATUS_TEMPORARILY_CLOSED,
    STATUS_CLOSED,
    "unknown",
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

def _expected_target_link(target):
    payload = target.get("payload") or {}
    if target.get("existing_applied_building_id") is not None:
        return target.get("existing_applied_building_id")
    if (
        payload.get("status_bucket") == "active"
        and target.get("production_match_state") == "existing_building"
    ):
        return target.get("production_building_id")
    return None
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
        action = classify_registry_action(row, existing)
        if action == "unchanged":
            continue
        if (
            existing
            and action != "status_change"
            and row.get("diff_kind") not in {"changed", "status_change"}
        ):
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
            "screen_baseline": _surface_snapshot(registry_rows, building_rows),
            "screen_expected_after_apply": _surface_snapshot(
                _project_registry_after_apply(registry_rows, targets),
                building_rows,
            ),
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
        (
            baseline_registry_rows,
            baseline_building_rows,
            current_baseline_fingerprint,
            _production_fingerprint,
        ) = _fetch_production_snapshot()
        if current_baseline_fingerprint != base["production_baseline_fingerprint"]:
            raise RuntimeError(
                "운영 기준선이 변경되어 수동검토 manifest를 다시 생성해야 합니다."
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
            "screen_baseline": _surface_snapshot(
                baseline_registry_rows,
                baseline_building_rows,
            ),
            "screen_expected_after_apply": _surface_snapshot(
                _project_registry_after_apply(
                    baseline_registry_rows,
                    resolved_targets,
                ),
                baseline_building_rows,
            ),
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

def compare_production_manifest(manifest_id=None):
    """최근 적용 manifest를 운영·기존 직접 동기화 결과와 읽기 전용 비교한다."""
    assert_development_staging()
    dev_conn = _get_development_connection()
    cur = dev_conn.cursor()
    try:
        if manifest_id is None:
            cur.execute(
                """
                SELECT id, manifest_key, status, source_batch_ids, result,
                       production_baseline_fingerprint
                  FROM lodging_promotion_manifests
                 WHERE status='applied'
                 ORDER BY finished_at DESC NULLS LAST, id DESC
                 LIMIT 1
                """
            )
        else:
            cur.execute(
                """
                SELECT id, manifest_key, status, source_batch_ids, result,
                       production_baseline_fingerprint
                  FROM lodging_promotion_manifests
                 WHERE id=%s
                """,
                (manifest_id,),
            )
        manifest = cur.fetchone()
        if not manifest:
            return {
                "skipped": True,
                "reason": "비교할 적용 완료 숙박 manifest가 없습니다.",
                "production_writes": 0,
            }
        if manifest["status"] != "applied":
            raise ValueError("적용 완료된 manifest만 병행 비교할 수 있습니다.")
        cur.execute(
            """
            SELECT source_row_id, action, production_match_state,
                   production_building_id, existing_applied_building_id, payload
              FROM lodging_promotion_rows
             WHERE promotion_manifest_id=%s
             ORDER BY source_row_id
            """,
            (manifest["id"],),
        )
        targets = [
            {
                **dict(row),
                "payload": dict(row["payload"] or {}),
            }
            for row in cur.fetchall()
        ]
        batch_ids = [
            int(value) for value in dict(manifest["source_batch_ids"] or {}).values()
        ]
        cur.execute(
            """
            SELECT sr.permit_number, sr.biz_name, sr.raw_status,
                   sr.status_bucket, sr.raw_hygiene_type, sr.service_category,
                   sr.road_address, sr.jibun_address, sb.source_key
              FROM lodging_source_rows sr
              JOIN lodging_source_batches sb ON sb.id=sr.batch_id
             WHERE sr.batch_id = ANY(%s)
               AND sr.permit_number IS NOT NULL
            """,
            (batch_ids,),
        )
        staging_rows = [dict(row) for row in cur.fetchall()]
        permits = sorted({
            target["payload"].get("permit_number")
            for target in targets
            if target["payload"].get("permit_number")
        })
        cur.execute(
            """
            SELECT permit_number, biz_name, biz_status_name, room_count,
                   hygiene_type, applied_building_id, road_address, jibun_address
              FROM lodging_registry
             WHERE permit_number = ANY(%s)
            """,
            (permits,),
        )
        legacy_rows = [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        dev_conn.close()

    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        raise RuntimeError("PROD_DATABASE_URL이 없어 병행 비교를 실행할 수 없습니다.")
    prod_conn = psycopg2.connect(production_url, connect_timeout=10)
    prod_conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    try:
        (
            production_rows,
            production_buildings,
            production_snapshot_fingerprint,
            production_fingerprint,
        ) = _fetch_production_snapshot(prod_conn)
        prod_cur = prod_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            prod_cur.execute(
                """
                SELECT permit_number
                  FROM lodging_registry
                 WHERE permit_number IS NOT NULL
                 GROUP BY permit_number
                HAVING COUNT(*) > 1
                """
            )
            production_duplicates = [
                row["permit_number"] for row in prod_cur.fetchall()
            ]
        finally:
            prod_cur.close()
    finally:
        prod_conn.close()

    result = compare_parallel_results(
        targets,
        staging_rows,
        legacy_rows,
        production_rows,
        production_duplicate_permits=production_duplicates,
        screen_baseline=dict(manifest["result"] or {}).get("screen_baseline"),
        screen_expected_after_apply=dict(manifest["result"] or {}).get(
            "screen_expected_after_apply"
        ),
        production_buildings=production_buildings,
    )
    result.update({
        "manifest_id": manifest["id"],
        "manifest_key": manifest["manifest_key"],
        "observed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "production_fingerprint": production_fingerprint,
        "production_snapshot_fingerprint": production_snapshot_fingerprint,
        "manifest_baseline_fingerprint": manifest["production_baseline_fingerprint"],
    })
    major_regression_count = len({
        row["permit_number"]
        for row in result["permit_diffs"]
        if row["outcome"] != "matched"
    })
    if result["screen_comparison"]["status"] == "regression":
        major_regression_count += 1
    result["major_regression_count"] = major_regression_count
    run_id = secrets.token_hex(16)

    write_conn = _get_development_connection()
    write_cur = write_conn.cursor()
    try:
        write_cur.execute(
            """
            INSERT INTO lodging_parallel_comparisons (
                promotion_manifest_id, run_id, production_fingerprint,
                result, major_regression_count
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                manifest["id"],
                run_id,
                production_fingerprint,
                psycopg2.extras.Json(result),
                major_regression_count,
            ),
        )
        recorded = write_cur.fetchone()
        write_conn.commit()
    except Exception:
        write_conn.rollback()
        raise
    finally:
        write_cur.close()
        write_conn.close()
    result["comparison_id"] = recorded["id"]
    result["run_id"] = run_id
    return result

def _get_development_connection():
    """운영 스케줄러 자식에서도 PG* 기반 개발 DB를 명시적으로 선택한다.

    운영 정기 워크플로는 DATABASE_URL만 PROD_DATABASE_URL로 덮어쓰지만,
    Replit 개발 DB의 PGHOST/PGDATABASE 자격정보는 그대로 제공한다. 이
    비교 전용 프로세스에서만 우선순위가 높은 운영 URL을 제외한 뒤 개발
    연결을 만들고, fingerprint 안전 게이트로 운영 연결이 아님을 확인한다.
    """
    configured_url = os.environ.get("DATABASE_URL")
    production_url = os.environ.get("PROD_DATABASE_URL")
    remove_override = bool(
        configured_url and production_url and configured_url == production_url
    )
    if remove_override:
        development_url = os.environ.get("DEV_DATABASE_URL")
        if development_url:
            os.environ["DATABASE_URL"] = development_url
        else:
            required = ("PGUSER", "PGPASSWORD", "PGHOST", "PGPORT", "PGDATABASE")
            if any(not os.environ.get(key) for key in required):
                raise RuntimeError(
                    "운영 스케줄러에서 개발 DB 연결 정보가 없어 병행 비교를 중단했습니다."
                )
            os.environ["DATABASE_URL"] = (
                "postgresql://"
                f"{quote_plus(os.environ['PGUSER'])}:"
                f"{quote_plus(os.environ['PGPASSWORD'])}@"
                f"{os.environ['PGHOST']}:{os.environ['PGPORT']}/"
                f"{quote_plus(os.environ['PGDATABASE'])}"
            )
    try:
        conn = get_conn()
    finally:
        if remove_override:
            os.environ["DATABASE_URL"] = configured_url
    try:
        assert_development_connection(conn)
    except Exception:
        conn.close()
        raise
    return conn

def _surface_snapshot(registry_rows, building_rows):
    """숙박 관련 공개·관리 화면이 읽는 최소 집계의 기준선."""
    status_counts = Counter(row.get("biz_status_name") or "미분류" for row in registry_rows)
    linked_permits = sum(
        row.get("applied_building_id") is not None for row in registry_rows
    )
    active_rooms = sum(
        int(row.get("room_count") or 0)
        for row in registry_rows
        if row.get("biz_status_name") == "영업/정상"
    )
    return {
        "search": {
            "master_buildings": len(building_rows),
            "mapped_buildings": sum(
                row.get("lat") is not None and row.get("lng") is not None
                for row in building_rows
            ),
            "lodging_registry_rows": len(registry_rows),
        },
        "detail": {
            "lodging_registry_rows": len(registry_rows),
            "linked_permits": linked_permits,
        },
        "stats": {
            "status_counts": dict(sorted(status_counts.items())),
            "active_permits": status_counts.get("영업/정상", 0),
            "active_rooms": active_rooms,
        },
        "admin": {
            "lodging_registry_rows": len(registry_rows),
            "linked_permits": linked_permits,
            "unlinked_permits": len(registry_rows) - linked_permits,
        },
    }

def get_parallel_comparison_overview(limit=10):
    """관리자 화면용 최근 관측·연속 무회귀 배치 요약."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id
              FROM lodging_promotion_manifests
             WHERE status='applied'
             ORDER BY finished_at DESC NULLS LAST, id DESC
             LIMIT 1
            """
        )
        current_manifest = cur.fetchone()
        if not current_manifest:
            return {
                "manifest_id": None,
                "observations": 0,
                "consecutive_clean_observations": 0,
                "minimum_observations_met": False,
                "latest": None,
                "recent": [],
            }
        manifest_id = current_manifest["id"]
        cur.execute(
            """
            SELECT COUNT(*) AS count
              FROM lodging_parallel_comparisons
             WHERE promotion_manifest_id=%s
            """,
            (manifest_id,),
        )
        observation_count = int(cur.fetchone()["count"] or 0)
        cur.execute(
            """
            SELECT id, promotion_manifest_id, run_id, production_fingerprint,
                   result, major_regression_count, created_at
              FROM lodging_parallel_comparisons
             WHERE promotion_manifest_id=%s
             ORDER BY created_at DESC, id DESC
             LIMIT %s
            """,
            (manifest_id, max(1, min(int(limit), 50))),
        )
        rows = [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    consecutive_clean = 0
    for row in rows:
        if int(row["major_regression_count"] or 0):
            break
        consecutive_clean += 1
    return {
        "manifest_id": manifest_id,
        "observations": observation_count,
        "consecutive_clean_observations": consecutive_clean,
        "minimum_observations_met": consecutive_clean >= 3,
        "latest": rows[0] if rows else None,
        "recent": rows,
    }

def compare_parallel_results(
    targets,
    staging_rows,
    legacy_registry_rows,
    production_registry_rows,
    *,
    production_duplicate_permits=(),
    screen_baseline=None,
    screen_expected_after_apply=None,
    production_buildings=(),
):
    """승인 대상과 기존 직접 동기화·운영 결과를 permit별로 비교한다.

    이 함수는 DB에 접근하지 않는 순수 비교 계층이다. 따라서 운영 조회
    실패나 재실행과 무관하게 동일 입력이면 동일한 판정이 나오며, 실제
    관측 실행은 그 결과를 개발 DB의 비교 이력으로 보존한다.
    """
    legacy = {
        row.get("permit_number"): row
        for row in legacy_registry_rows
        if row.get("permit_number")
    }
    production = {
        row.get("permit_number"): row
        for row in production_registry_rows
        if row.get("permit_number")
    }
    duplicate_permits = set(production_duplicate_permits)
    staging_by_permit = {}
    staging_permit_counts = Counter()
    for row in staging_rows:
        permit = row.get("permit_number")
        if permit:
            staging_by_permit.setdefault(permit, row)
            staging_permit_counts[permit] += 1
    staging_duplicates = {
        permit for permit, count in staging_permit_counts.items() if count > 1
    }

    action_counts = Counter()
    outcome_counts = Counter()
    legacy_production_counts = Counter()
    history_status_counts = Counter()
    history_status_diffs = []
    building_link_counts = Counter()
    permit_diffs = []

    for target in targets:
        payload = target.get("payload") or {}
        permit = payload.get("permit_number")
        action = target.get("action") or "unknown"
        action_counts[action] += 1
        current = production.get(permit)
        old = legacy.get(permit)
        differences = {}
        if current is None:
            outcome = "missing"
        else:
            # build_registry_record is the single source for raw CSV→registry
            # conversion. Import lazily to avoid the promotion/apply cycle.
            from apply_lodging_promotion import build_registry_record

            expected = build_registry_record(payload)
            for payload_key, registry_key in _COMPARISON_FIELDS:
                expected_value = expected.get(registry_key)
                if expected_value is None:
                    continue  # UPSERT의 COALESCE 보존 규칙
                actual_value = current.get(registry_key)
                if str(actual_value or "") != str(expected_value or ""):
                    differences[registry_key] = {
                        "expected": expected_value,
                        "actual": actual_value,
                    }
            expected_room = expected.get("room_count")
            if expected_room is not None and expected_room != current.get("room_count"):
                differences["room_count"] = {
                    "expected": expected_room,
                    "actual": current.get("room_count"),
                }
            expected_link = _expected_target_link(target)
            actual_link = current.get("applied_building_id")
            if expected_link != actual_link:
                differences["applied_building_id"] = {
                    "expected": expected_link,
                    "actual": actual_link,
                }
            if differences:
                outcome = (
                    "building_link_difference"
                    if set(differences) == {"applied_building_id"}
                    else "field_difference"
                )
            else:
                outcome = "matched"
        if permit in duplicate_permits or permit in staging_duplicates:
            outcome = "duplicate"
        outcome_counts[outcome] += 1

        if old is None and current is None:
            legacy_production_counts["both_missing"] += 1
        elif old is None:
            legacy_production_counts["production_only"] += 1
        elif current is None:
            legacy_production_counts["legacy_only"] += 1
        else:
            common_keys = [
                key for _payload_key, key in _COMPARISON_FIELDS
            ] + ["room_count", "applied_building_id"]
            common_difference = {
                key: {
                    "legacy": old.get(key),
                    "production": current.get(key),
                }
                for key in common_keys
                if str(old.get(key) or "") != str(current.get(key) or "")
            }
            legacy_production_counts[
                "different" if common_difference else "same"
            ] += 1

        status_bucket = payload.get("status_bucket") or "unknown"
        if status_bucket in _HISTORICAL_STATUS_BUCKETS or (
            payload.get("service_category") == "미분류"
        ):
            history_status_counts[status_bucket] += 1
            expected_status = payload.get("raw_status")
            actual_status = current.get("biz_status_name") if current else None
            legacy_status = old.get("biz_status_name") if old else None
            if (
                expected_status != actual_status
                or expected_status != legacy_status
                or legacy_status != actual_status
            ):
                history_status_diffs.append({
                    "permit_number": permit,
                    "status_bucket": status_bucket,
                    "expected_status": expected_status,
                    "legacy_status": legacy_status,
                    "production_status": actual_status,
                })

        expected_link = _expected_target_link(target)
        actual_link = current.get("applied_building_id") if current else None
        building_link_counts[
            "matched" if expected_link == actual_link else "different"
        ] += 1
        if outcome != "matched":
            permit_diffs.append({
                "permit_number": permit,
                "source_key": payload.get("source_key"),
                "action": action,
                "outcome": outcome,
                "differences": differences,
                "staging_present": permit in staging_by_permit,
                "legacy_present": old is not None,
                "production_present": current is not None,
                "expected_building_id": expected_link,
                "legacy_building_id": old.get("applied_building_id") if old else None,
                "production_building_id": actual_link,
            })
        if permit not in staging_by_permit:
            permit_diffs.append({
                "permit_number": permit,
                "source_key": payload.get("source_key"),
                "action": action,
                "outcome": "staging_missing",
                "differences": {},
                "staging_present": False,
                "legacy_present": old is not None,
                "production_present": current is not None,
                "expected_building_id": expected_link,
                "legacy_building_id": old.get("applied_building_id") if old else None,
                "production_building_id": actual_link,
            })

    before = screen_baseline or {}
    after = _surface_snapshot(production_registry_rows, production_buildings)
    expected_after = screen_expected_after_apply or {}
    screen_differences = (
        _surface_differences(expected_after, after) if expected_after else {}
    )
    return {
        "read_only": True,
        "production_writes": 0,
        "declared_action_counts": dict(action_counts),
        "outcome_counts": dict(outcome_counts),
        "legacy_vs_production_counts": dict(legacy_production_counts),
        "duplicate_permits": {
            "staging": sorted(staging_duplicates),
            "production": sorted(duplicate_permits),
        },
        "history_status_counts": dict(history_status_counts),
        "history_status_diffs": history_status_diffs,
        "building_link_counts": dict(building_link_counts),
        "permit_diffs": permit_diffs,
        "screen_comparison": {
            "baseline_available": bool(before),
            "expected_after_available": bool(expected_after),
            "status": (
                "expected_match"
                if expected_after and not screen_differences
                else "regression"
                if expected_after
                else "expected_baseline_unavailable"
            ),
            "before": before or None,
            "expected_after": expected_after or None,
            "after": after,
            "differences": screen_differences,
        },
    }

def _project_registry_after_apply(registry_rows, targets):
    """manifest UPSERT 뒤 화면 집계에 필요한 원장 상태를 미리 계산한다."""
    from apply_lodging_promotion import build_registry_record

    projected = {
        row.get("permit_number"): dict(row)
        for row in registry_rows
        if row.get("permit_number")
    }
    for target in targets:
        payload = target.get("payload") or {}
        permit = payload.get("permit_number")
        existing = projected.get(permit)
        record = build_registry_record(payload, existing)
        if existing:
            merged = dict(existing)
            for key, value in record.items():
                if value is not None:
                    merged[key] = value
            # 운영 UPSERT는 기존 연결을 항상 보존한다.
            merged["applied_building_id"] = existing.get("applied_building_id")
            projected[permit] = merged
        else:
            projected[permit] = record
    return list(projected.values())

def _surface_differences(before, after, prefix=""):
    differences = {}
    keys = sorted(set((before or {}).keys()) | set((after or {}).keys()))
    for key in keys:
        path = f"{prefix}.{key}" if prefix else key
        old_value = (before or {}).get(key)
        new_value = (after or {}).get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            differences.update(_surface_differences(old_value, new_value, path))
        elif old_value != new_value:
            differences[path] = {"before": old_value, "after": new_value}
    return differences
