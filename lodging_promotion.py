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
from legacy_lodging_gate import CUTOVER_LOCK_ID, CONTROL_META_KEY
from lodging_stats_dedup import deduplicate_cross_source_lodgings
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
LEGACY_LODGING_SYNC_CONTROL_KEY = CONTROL_META_KEY
LEGACY_LODGING_SYNC_STAGES = ("lodging", "camping", "rural", "hanok", "pension")
CUTOVER_MINIMUM_OBSERVATIONS = 3
CUTOVER_MINIMUM_CONSECUTIVE_CLEAN = 3
MANIFEST_CUTOVER_FENCE_LOCK_ID = 9_182_992
_SCHEDULED_SYNC_STALE_SECONDS = 5 * 60
_SURFACE_NAMES = ("search", "detail", "stats", "admin")
_SURFACE_GUARD_METRICS = {
    "search": ("building_count", "mapped_building_count"),
    "detail": ("link_count", "active_count", "room_count"),
    "stats": ("active_count", "room_count"),
    "admin": ("building_count", "registry_count", "link_count"),
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


def _source_snapshot_sha256(batches, staging_rows):
    """manifest가 근거로 삼은 최신 staging 배치와 유효 원본 행을 고정한다."""
    batch_snapshot = {
        key: {
            "id": int(batches[key]["id"]),
            "source_key": key,
            "reference_date": str(batches[key]["reference_date"]),
            "file_sha256": batches[key]["file_sha256"],
            "status": batches[key]["status"],
            "total_rows": int(batches[key]["total_rows"] or 0),
            "valid_rows": int(batches[key]["valid_rows"] or 0),
            "review_rows": int(batches[key]["review_rows"] or 0),
        }
        for key in GOVERNMENT_LODGING_SOURCES
    }
    return _canonical_hash({
        "batches": batch_snapshot,
        "rows": staging_rows,
    })


def _lock_staging_sources(cur):
    """검증부터 운영 커밋까지 원본 배치·행의 변경을 차단한다."""
    cur.execute(
        "LOCK TABLE lodging_source_batches, lodging_source_rows IN SHARE MODE"
    )


def _unresolved_source_review_count(cur, batch_id, source_key):
    """Count review rows not covered by the lineage of an applied manifest."""
    cur.execute(
        """
        WITH RECURSIVE applied_lineage AS (
            SELECT id, parent_manifest_id
              FROM lodging_promotion_manifests
             WHERE status='applied'
               AND source_batch_ids->>%s=%s
            UNION
            SELECT parent.id, parent.parent_manifest_id
              FROM lodging_promotion_manifests parent
              JOIN applied_lineage child
                ON child.parent_manifest_id=parent.id
        )
        SELECT COUNT(*) AS count
          FROM lodging_source_rows sr
         WHERE sr.batch_id=%s
           AND sr.row_state='review_required'
           AND NOT EXISTS (
               SELECT 1
                 FROM lodging_promotion_review_decisions decision
                 JOIN applied_lineage lineage
                   ON lineage.id=decision.resulting_manifest_id
                WHERE decision.source_row_id=sr.id
           )
        """,
        (source_key, str(batch_id), batch_id),
    )
    return int(cur.fetchone()["count"] or 0)


def _verify_manifest_source_snapshot(cur, manifest):
    """manifest 생성 뒤 최신 승인 원본이나 그 행이 바뀌지 않았는지 확인한다."""
    result = dict(manifest.get("result") or {})
    expected_sha256 = result.get("source_snapshot_sha256")
    if not expected_sha256:
        raise RuntimeError(
            "manifest에 승인 원본 지문이 없어 다시 생성해야 합니다."
        )
    expected_batch_ids = {
        key: int(value)
        for key, value in dict(manifest.get("source_batch_ids") or {}).items()
    }
    if set(expected_batch_ids) != set(GOVERNMENT_LODGING_SOURCES):
        raise RuntimeError("manifest의 정부 숙박 8종 batch 구성이 완전하지 않습니다.")
    batches, staging_rows = _fetch_latest_staging(cur.connection)
    current_batch_ids = {
        key: int(batches[key]["id"]) for key in GOVERNMENT_LODGING_SOURCES
    }
    if current_batch_ids != expected_batch_ids:
        raise RuntimeError(
            "최신 승인 원본 batch가 manifest 생성 이후 변경되어 다시 생성해야 합니다."
        )
    current_sha256 = _source_snapshot_sha256(batches, staging_rows)
    if current_sha256 != expected_sha256:
        raise RuntimeError(
            "승인 원본 행이 manifest 생성 이후 변경되어 다시 생성해야 합니다."
        )
    return current_sha256


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
                   jibun_address, road_norm, jibun_norm, updated_at
              FROM lodging_registry
             ORDER BY permit_number
            """
        )
        registry_rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, road_address, jibun_address, sgg_cd, umd_nm, jibun,
                   lat, lng, lodging_type, building_status, use_apr_day, units
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
        registry_rows, building_rows, baseline_fingerprint, production_fingerprint = (
            _fetch_production_snapshot()
        )
        if _database_fingerprint(dev_conn) == production_fingerprint:
            raise RuntimeError("개발 DB와 운영 DB가 같아 manifest 생성을 중단했습니다.")
        lock_cur = dev_conn.cursor()
        try:
            _lock_staging_sources(lock_cur)
        finally:
            lock_cur.close()
        batches, staging_rows = _fetch_latest_staging(dev_conn)
        source_snapshot_sha256 = _source_snapshot_sha256(batches, staging_rows)
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
                "source_snapshot_sha256": source_snapshot_sha256,
                "production_baseline_fingerprint": baseline_fingerprint,
                "target_payload_sha256": target_payload_sha256,
            }
        )
        screen_baseline = _surface_snapshot(registry_rows, building_rows)
        screen_expected_after_apply = _surface_snapshot(
            _project_registry_after_apply(registry_rows, targets),
            building_rows,
        )
        result = {
            **summary,
            "production_registry_rows": len(registry_rows),
            "production_master_buildings": len(building_rows),
            "staging_valid_rows": len(staging_rows),
            "target_rows": len(targets),
            "new_permits": int(summary["action_counts"].get("insert", 0)),
            "source_files": source_files,
            "source_snapshot_sha256": source_snapshot_sha256,
            "screen_baseline": screen_baseline,
            "screen_expected_after_apply": screen_expected_after_apply,
            "screen_expected_ranges": _surface_expected_ranges(
                screen_expected_after_apply
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
        screen_baseline = _surface_snapshot(
            baseline_registry_rows,
            baseline_building_rows,
        )
        screen_expected_after_apply = _surface_snapshot(
            _project_registry_after_apply(
                baseline_registry_rows,
                resolved_targets,
            ),
            baseline_building_rows,
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
            "screen_baseline": screen_baseline,
            "screen_expected_after_apply": screen_expected_after_apply,
            "screen_expected_ranges": _surface_expected_ranges(
                screen_expected_after_apply
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
        _lock_staging_sources(cur)
        cur.execute(
            """
            SELECT source_batch_ids, result
              FROM lodging_promotion_manifests
             WHERE id=%s AND status='draft'
             FOR UPDATE
            """,
            (manifest_id,),
        )
        manifest = cur.fetchone()
        if not manifest:
            raise ValueError("승인 초안이 아니거나 이미 처리된 manifest입니다.")
        _verify_manifest_source_snapshot(cur, manifest)
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


def approve_production_manifest_automated(manifest_id):
    """승인된 staging을 근거로 정기 실행자가 manifest 승인을 기록한다.

    사람의 관리자 승인과 구분하기 위해 approved_by는 비워 두고 result에
    실행 주체를 남긴다. 수동 검토 행이 하나라도 있으면 자동 승인을 하지
    않는다.
    """
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        _lock_staging_sources(cur)
        cur.execute(
            """
            SELECT result, source_batch_ids
              FROM lodging_promotion_manifests
             WHERE id=%s AND status='draft'
             FOR UPDATE
            """,
            (manifest_id,),
        )
        manifest = cur.fetchone()
        if not manifest:
            raise ValueError("자동 승인할 draft manifest를 찾을 수 없습니다.")
        source_batch_ids = {
            key: int(value)
            for key, value in dict(manifest["source_batch_ids"] or {}).items()
        }
        if set(source_batch_ids) != set(GOVERNMENT_LODGING_SOURCES):
            raise ValueError("manifest의 정부 숙박 8종 batch 구성이 완전하지 않습니다.")
        _verify_manifest_source_snapshot(cur, manifest)
        for source_key, batch_id in source_batch_ids.items():
            cur.execute(
                """
                SELECT status, review_rows
                  FROM lodging_source_batches
                 WHERE id=%s AND source_key=%s
                 FOR SHARE
                """,
                (batch_id, source_key),
            )
            batch = cur.fetchone()
            unresolved_review_rows = (
                _unresolved_source_review_count(cur, batch_id, source_key)
                if batch else 0
            )
            status_allowed = batch and (
                batch["status"] in {
                    "validated", "approved", "dry_run", "applied",
                }
                or (
                    batch["status"] == "review_required"
                    and unresolved_review_rows == 0
                )
            )
            if not status_allowed:
                raise ValueError(f"{source_key} 고정 staging batch가 검증 상태가 아닙니다.")
            if unresolved_review_rows:
                raise ValueError(f"{source_key} 고정 staging batch에 미해결 검토행이 있습니다.")
            cur.execute(
                """
                SELECT COUNT(*) AS count
                  FROM lodging_source_rows
                 WHERE batch_id=%s
                   AND row_state='validated'
                   AND diff_kind <> 'unchanged'
                """,
                (batch_id,),
            )
            changed_count = int(cur.fetchone()["count"] or 0)
            if changed_count:
                cur.execute(
                    """
                    SELECT status
                      FROM lodging_approval_batches
                     WHERE source_batch_id=%s
                     FOR SHARE
                    """,
                    (batch_id,),
                )
                approval = cur.fetchone()
                if not approval or approval["status"] not in {"dry_run", "applied"}:
                    raise ValueError(f"{source_key} 고정 staging 변경분이 승인 dry-run 상태가 아닙니다.")
        cur.execute(
            """
            SELECT COUNT(*) AS count
              FROM lodging_promotion_rows
             WHERE promotion_manifest_id=%s
               AND payload->>'row_state'='review_required'
            """,
            (manifest_id,),
        )
        unresolved = int(cur.fetchone()["count"] or 0)
        if unresolved:
            raise ValueError(f"수동 검토 미해결 행 {unresolved}건이 있어 자동 승인할 수 없습니다.")
        result = dict(manifest["result"] or {})
        result["promotion_approval"] = {
            "mode": "scheduled",
            "actor": "scheduled_lodging_promotion",
        }
        cur.execute(
            """
            UPDATE lodging_promotion_manifests
               SET status='approved', approved_by=NULL, approved_at=NOW(),
                   result=%s, error=NULL
             WHERE id=%s AND status='draft'
             RETURNING id, status, row_count, run_id, result
            """,
            (psycopg2.extras.Json(result), manifest_id),
        )
        updated = cur.fetchone()
        if not updated:
            raise RuntimeError("자동 승인 중 manifest 상태가 변경되었습니다.")
        conn.commit()
        return dict(updated)
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
        _lock_staging_sources(cur)
        cur.execute(
            """
            SELECT id, status, production_baseline_fingerprint,
                   target_payload_sha256, row_count, result, run_id,
                   source_batch_ids
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
        _verify_manifest_source_snapshot(cur, manifest)
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
                "source_snapshot_verified": True,
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
        screen_expected_ranges=dict(manifest["result"] or {}).get(
            "screen_expected_ranges"
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
    if result["screen_comparison"]["blocking"]:
        major_regression_count += 1
    result["major_regression_count"] = major_regression_count
    run_id = secrets.token_hex(16)

    write_conn = _get_development_connection()
    write_cur = write_conn.cursor()
    try:
        write_cur.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (MANIFEST_CUTOVER_FENCE_LOCK_ID,),
        )
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
    """실제 검색·상세·통계·관리자 주소 매칭 규칙으로 화면 집계를 계산한다."""
    visible_buildings = [
        row for row in building_rows
        if row.get("lodging_type") != "mixed_use_excluded"
    ]
    road_registry = defaultdict(dict)
    jibun_registry = defaultdict(dict)
    for row in registry_rows:
        permit = row.get("permit_number")
        if not permit:
            continue
        road_norm = (
            row.get("road_norm")
            if "road_norm" in row
            else normalize_road_prefix(row.get("road_address"))
        )
        jibun_norm = (
            row.get("jibun_norm")
            if "jibun_norm" in row
            else normalize_jibun_prefix(row.get("jibun_address"))
        )
        if road_norm:
            road_registry[road_norm][permit] = row
        if jibun_norm:
            jibun_registry[jibun_norm][permit] = row

    detail_link_count = 0
    detail_room_count = 0
    detail_permits = set()
    admin_link_count = 0
    admin_permits = set()
    stats_permits = {}
    active_buildings = 0
    for building in visible_buildings:
        road_key = normalize_road_prefix(building.get("road_address"))
        jibun_key = get_building_jibun_key(building)

        admin_matches = road_registry.get(road_key, {}) if road_key else {}
        if not admin_matches and jibun_key:
            admin_matches = jibun_registry.get(jibun_key, {})
        admin_link_count += len(admin_matches)
        admin_permits.update(admin_matches)
        stats_permits.update(admin_matches)

        active_road_matches = {
            permit: row
            for permit, row in (
                road_registry.get(road_key, {}).items() if road_key else ()
            )
            if row.get("biz_status_name") == "영업/정상"
        }
        active_matches = active_road_matches
        if not active_matches and jibun_key:
            active_matches = {
                permit: row
                for permit, row in jibun_registry.get(jibun_key, {}).items()
                if row.get("biz_status_name") == "영업/정상"
            }
        if active_matches:
            active_buildings += 1
        detail_link_count += len(active_matches)
        detail_permits.update(active_matches)
        detail_room_count += sum(
            int(row.get("room_count") or 0)
            for row in active_matches.values()
        )

    active_stats_rows = deduplicate_cross_source_lodgings([
        row for row in stats_permits.values()
        if row.get("biz_status_name") == "영업/정상"
    ])
    stats_room_count = sum(
        int(row.get("room_count") or 0)
        for row in active_stats_rows
    )
    status_counts = Counter(
        row.get("biz_status_name") or "미분류"
        for row in stats_permits.values()
    )
    visible_building_count = len(visible_buildings)
    mapped_building_count = sum(
        row.get("lat") is not None and row.get("lng") is not None
        for row in visible_buildings
    )
    return {
        "search": {
            "master_buildings": visible_building_count,
            "mapped_buildings": mapped_building_count,
            "building_count": visible_building_count,
            "mapped_building_count": mapped_building_count,
        },
        "detail": {
            "lodging_registry_rows": len(detail_permits),
            "linked_permits": detail_link_count,
            "link_count": detail_link_count,
            "active_count": len(detail_permits),
            "room_count": detail_room_count,
            "building_count": active_buildings,
        },
        "stats": {
            "status_counts": dict(sorted(status_counts.items())),
            "active_permits": len(active_stats_rows),
            "active_rooms": stats_room_count,
            "active_count": len(active_stats_rows),
            "room_count": stats_room_count,
            "registry_count": len(stats_permits),
        },
        "admin": {
            "building_count": visible_building_count,
            "lodging_registry_rows": len(admin_permits),
            "linked_permits": admin_link_count,
            "unlinked_permits": max(0, len(registry_rows) - len(admin_permits)),
            "registry_count": len(admin_permits),
            "link_count": admin_link_count,
        },
    }


def _surface_expected_ranges(expected_after):
    """핵심 사용자 노출 지표의 허용 범위를 manifest에 명시적으로 고정한다."""
    ranges = {}
    for surface, metrics in _SURFACE_GUARD_METRICS.items():
        values = (expected_after or {}).get(surface) or {}
        ranges[surface] = {}
        for metric in metrics:
            value = values.get(metric)
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            ranges[surface][metric] = {
                "expected": value,
                "min": value,
                "max": value,
            }
    return ranges


def _surface_snapshot_available(snapshot):
    if not isinstance(snapshot, dict):
        return False
    return all(
        isinstance(snapshot.get(surface), dict)
        for surface in _SURFACE_NAMES
    )


def _surface_ranges_available(ranges):
    if not isinstance(ranges, dict):
        return False
    for surface, metrics in _SURFACE_GUARD_METRICS.items():
        surface_ranges = ranges.get(surface)
        if not isinstance(surface_ranges, dict):
            return False
        for metric in metrics:
            bounds = surface_ranges.get(metric)
            if (
                not isinstance(bounds, dict)
                or isinstance(bounds.get("min"), bool)
                or not isinstance(bounds.get("min"), int)
                or isinstance(bounds.get("max"), bool)
                or not isinstance(bounds.get("max"), int)
            ):
                return False
    return True


def _surface_range_differences(expected_ranges, actual):
    differences = {}
    for surface, metrics in (expected_ranges or {}).items():
        actual_surface = (actual or {}).get(surface) or {}
        for metric, bounds in (metrics or {}).items():
            value = actual_surface.get(metric)
            minimum = bounds.get("min")
            maximum = bounds.get("max")
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
                or value > maximum
            ):
                differences[f"{surface}.{metric}"] = {
                    "expected": bounds.get("expected"),
                    "min": minimum,
                    "max": maximum,
                    "actual": value,
                }
    return differences


def _parallel_comparison_is_clean(row):
    result = dict(row.get("result") or {})
    screen = dict(result.get("screen_comparison") or {})
    return (
        int(row.get("major_regression_count") or 0) == 0
        and screen.get("status") == "expected_match"
        and screen.get("blocking") is False
    )


def get_parallel_comparison_overview(limit=10):
    """관리자 화면용 최근 관측·연속 무회귀 배치 요약."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, manifest_key, finished_at
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
                "consecutive_clean_met": False,
                "eligible_for_cutover": False,
                "policy": {
                    "minimum_observations": CUTOVER_MINIMUM_OBSERVATIONS,
                    "minimum_consecutive_clean": CUTOVER_MINIMUM_CONSECUTIVE_CLEAN,
                },
                "observation_period": None,
                "latest": None,
                "recent": [],
            }
        manifest_id = current_manifest["id"]
        cur.execute(
            """
            SELECT COUNT(*) AS count,
                   MIN(created_at) AS first_observed_at,
                   MAX(created_at) AS last_observed_at
              FROM lodging_parallel_comparisons
             WHERE promotion_manifest_id=%s
            """,
            (manifest_id,),
        )
        observation_summary = cur.fetchone()
        observation_count = int(observation_summary["count"] or 0)
        cur.execute(
            """
            SELECT id, promotion_manifest_id, run_id, production_fingerprint,
                   result, major_regression_count, created_at
              FROM lodging_parallel_comparisons
             WHERE promotion_manifest_id=%s
             ORDER BY created_at DESC, id DESC
             LIMIT %s
            """,
            (manifest_id, max(1, min(int(limit), 500))),
        )
        rows = [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    consecutive_clean = 0
    for row in rows:
        if not _parallel_comparison_is_clean(row):
            break
        consecutive_clean += 1
    minimum_observations_met = observation_count >= CUTOVER_MINIMUM_OBSERVATIONS
    consecutive_clean_met = (
        consecutive_clean >= CUTOVER_MINIMUM_CONSECUTIVE_CLEAN
    )
    latest_clean = bool(rows and _parallel_comparison_is_clean(rows[0]))
    first_observed_at = observation_summary["first_observed_at"]
    last_observed_at = observation_summary["last_observed_at"]
    elapsed_hours = None
    if first_observed_at and last_observed_at:
        elapsed_hours = round(
            max(0.0, (last_observed_at - first_observed_at).total_seconds() / 3600),
            1,
        )
    return {
        "manifest_id": manifest_id,
        "manifest_key": current_manifest["manifest_key"],
        "manifest_applied_at": current_manifest["finished_at"],
        "observations": observation_count,
        "consecutive_clean_observations": consecutive_clean,
        "minimum_observations_met": minimum_observations_met,
        "consecutive_clean_met": consecutive_clean_met,
        "latest_clean": latest_clean,
        "eligible_for_cutover": (
            minimum_observations_met and consecutive_clean_met and latest_clean
        ),
        "policy": {
            "minimum_observations": CUTOVER_MINIMUM_OBSERVATIONS,
            "minimum_consecutive_clean": CUTOVER_MINIMUM_CONSECUTIVE_CLEAN,
        },
        "observation_period": {
            "first_observed_at": first_observed_at,
            "last_observed_at": last_observed_at,
            "elapsed_hours": elapsed_hours,
        } if first_observed_at else None,
        "latest": rows[0] if rows else None,
        "recent": rows[:max(1, min(int(limit), 50))],
    }


def _production_write_connection():
    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        raise RuntimeError("PROD_DATABASE_URL이 없어 기존 동기화 설정을 변경할 수 없습니다.")
    return psycopg2.connect(
        production_url,
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _default_legacy_sync_control():
    return {
        "enabled": True,
        "state": "enabled",
        "manifest_id": None,
        "updated_at": None,
        "updated_by": None,
        "reason": None,
        "history": [],
    }


def _decode_legacy_sync_control(value):
    if not value:
        return _default_legacy_sync_control()
    try:
        control = json.loads(value) if isinstance(value, str) else dict(value)
    except (TypeError, ValueError):
        return _default_legacy_sync_control()
    if not isinstance(control, dict) or control.get("enabled") is not False:
        control = {**_default_legacy_sync_control(), **(
            control if isinstance(control, dict) else {}
        )}
        control["enabled"] = True
        control["state"] = "enabled"
    control.setdefault("history", [])
    return control


def _running_legacy_sync_stages(cur):
    keys = [
        "scheduled_sync_status",
        "lodging_sync_status",
        "rural_hanok_sync_status:rural",
        "rural_hanok_sync_status:hanok",
        "rural_hanok_sync_status:pension",
        *(
            f"scheduled_sync_status:{stage}"
            for stage in LEGACY_LODGING_SYNC_STAGES
        ),
    ]
    cur.execute(
        """
        SELECT key, value,
               EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age_seconds
          FROM app_meta
         WHERE key = ANY(%s)
        """,
        (keys,),
    )
    running = set()
    for row in cur.fetchall():
        if float(row["age_seconds"] or 0) > _SCHEDULED_SYNC_STALE_SECONDS:
            continue
        try:
            status = json.loads(row["value"] or "{}")
        except (TypeError, ValueError):
            continue
        if status.get("state") != "running":
            continue
        selected = status.get("selected_stage")
        current = status.get("current_stage")
        candidates = {
            selected,
            current,
            *(status.get("running_stages") or []),
        }
        for stage in candidates:
            if stage in LEGACY_LODGING_SYNC_STAGES:
                running.add(stage)
        if row["key"] != "scheduled_sync_status":
            stage = {
                "lodging_sync_status": "lodging",
                "rural_hanok_sync_status:rural": "rural",
                "rural_hanok_sync_status:hanok": "hanok",
                "rural_hanok_sync_status:pension": "pension",
            }.get(row["key"], row["key"].rsplit(":", 1)[-1])
            if stage in LEGACY_LODGING_SYNC_STAGES:
                running.add(stage)
    return sorted(running)


def get_legacy_lodging_sync_control():
    """운영 DB의 기존 직접 동기화 설정과 감사 이력을 읽는다.

    설정이 없거나 손상되면 반드시 enabled=True로 해석한다. 관리자 승인 기록
    없이는 기존 수집이 중단되지 않아야 하기 때문이다.
    """
    conn = _production_write_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT value FROM app_meta WHERE key=%s",
            (LEGACY_LODGING_SYNC_CONTROL_KEY,),
        )
        row = cur.fetchone()
        control = _decode_legacy_sync_control(row["value"] if row else None)
        control["running_legacy_stages"] = _running_legacy_sync_stages(cur)
        return control
    finally:
        cur.close()
        conn.close()


def _set_legacy_lodging_sync_enabled_unfenced(
    manifest_id,
    *,
    enabled,
    actor_id,
    reason,
):
    """관찰 게이트를 재검증한 뒤 기존 직접 동기화를 종료하거나 복구한다."""
    actor_id = _require_admin_actor(actor_id, "기존 숙박 동기화 설정 변경")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ValueError("변경 사유를 5자 이상 입력해 주세요.")
    if len(reason) > 500:
        raise ValueError("변경 사유는 500자 이하여야 합니다.")
    enabled = bool(enabled)
    comparison = get_parallel_comparison_overview(limit=50)
    if not enabled:
        if comparison.get("manifest_id") != int(manifest_id):
            raise ValueError("최신 적용 manifest만 기존 동기화 종료 기준으로 사용할 수 있습니다.")
        if not comparison.get("eligible_for_cutover"):
            raise ValueError(
                "최소 관찰 횟수와 연속 무회귀 조건을 모두 충족한 뒤 종료할 수 있습니다."
            )
        latest_result = dict((comparison.get("latest") or {}).get("result") or {})
        screen_status = (
            latest_result.get("screen_comparison") or {}
        ).get("status")
        if screen_status != "expected_match":
            raise ValueError(
                "검색·상세·통계·관리자 화면 기준선 검증이 완료되지 않아 종료할 수 없습니다."
            )

    conn = _production_write_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (CUTOVER_LOCK_ID,))
        cur.execute(
            "SELECT value FROM app_meta WHERE key=%s FOR UPDATE",
            (LEGACY_LODGING_SYNC_CONTROL_KEY,),
        )
        row = cur.fetchone()
        previous = _decode_legacy_sync_control(row["value"] if row else None)
        if previous["enabled"] == enabled:
            previous["changed"] = False
            previous["running_legacy_stages"] = _running_legacy_sync_stages(cur)
            conn.commit()
            return previous
        running = _running_legacy_sync_stages(cur)
        if not enabled and running:
            raise RuntimeError(
                "실행 중인 기존 숙박 동기화가 있습니다: "
                + ", ".join(running)
                + ". 완료 후 다시 승인해 주세요."
            )
        changed_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        event = {
            "event_id": secrets.token_hex(8),
            "action": "restore" if enabled else "cutover",
            "previous_enabled": previous["enabled"],
            "enabled": enabled,
            "manifest_id": int(manifest_id),
            "actor_id": actor_id,
            "reason": reason,
            "created_at": changed_at,
            "verification": {
                "observations": comparison.get("observations"),
                "consecutive_clean_observations": comparison.get(
                    "consecutive_clean_observations"
                ),
                "latest_comparison_id": (
                    (comparison.get("latest") or {}).get("id")
                ),
                "public_surfaces": (
                    ((comparison.get("latest") or {}).get("result") or {}).get(
                        "screen_comparison"
                    )
                ),
            },
        }
        history = list(previous.get("history") or [])
        history.append(event)
        control = {
            "enabled": enabled,
            "state": "enabled" if enabled else "disabled",
            "manifest_id": int(manifest_id),
            "updated_at": changed_at,
            "updated_by": actor_id,
            "reason": reason,
            "history": history[-100:],
        }
        cur.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value=EXCLUDED.value, updated_at=NOW()
            """,
            (
                LEGACY_LODGING_SYNC_CONTROL_KEY,
                json.dumps(control, ensure_ascii=False),
            ),
        )
        conn.commit()
        control["changed"] = True
        control["running_legacy_stages"] = []
        return control
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def set_legacy_lodging_sync_enabled(
    manifest_id,
    *,
    enabled,
    actor_id,
    reason,
):
    """Serialize latest-manifest verification with applies and observations."""
    fence_conn = _get_development_connection()
    fence_cur = fence_conn.cursor()
    try:
        fence_cur.execute(
            "SELECT pg_advisory_lock(%s)",
            (MANIFEST_CUTOVER_FENCE_LOCK_ID,),
        )
        fence_cur.fetchone()
        return _set_legacy_lodging_sync_enabled_unfenced(
            manifest_id,
            enabled=enabled,
            actor_id=actor_id,
            reason=reason,
        )
    finally:
        try:
            fence_cur.execute(
                "SELECT pg_advisory_unlock(%s)",
                (MANIFEST_CUTOVER_FENCE_LOCK_ID,),
            )
            fence_cur.fetchone()
        except Exception:
            pass
        fence_cur.close()
        fence_conn.close()


def compare_parallel_results(
    targets,
    staging_rows,
    legacy_registry_rows,
    production_registry_rows,
    *,
    production_duplicate_permits=(),
    screen_baseline=None,
    screen_expected_after_apply=None,
    screen_expected_ranges=None,
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
    expected_ranges = (
        screen_expected_ranges
        or (_surface_expected_ranges(expected_after) if expected_after else {})
    )
    baseline_available = _surface_snapshot_available(before)
    expected_after_available = _surface_snapshot_available(expected_after)
    expected_ranges_available = _surface_ranges_available(expected_ranges)
    screen_differences = (
        _surface_differences(expected_after, after) if expected_after else {}
    )
    out_of_range = (
        _surface_range_differences(expected_ranges, after)
        if expected_ranges_available
        else {}
    )
    if (
        not baseline_available
        or not expected_after_available
        or not expected_ranges_available
    ):
        screen_status = "expected_baseline_unavailable"
        verification_status = "pending"
    elif screen_differences or out_of_range:
        screen_status = "regression"
        verification_status = "regression"
    else:
        screen_status = "expected_match"
        verification_status = "clean"
    blocking_reasons = []
    if not baseline_available:
        blocking_reasons.append("전환 전 화면 기준선이 없습니다.")
    if not expected_after_available:
        blocking_reasons.append("반영 후 화면 기대 결과가 없습니다.")
    if not expected_ranges_available:
        blocking_reasons.append("핵심 화면 지표의 허용 범위가 없습니다.")
    if screen_differences:
        blocking_reasons.append(
            f"화면 기대 결과와 다른 항목이 {len(screen_differences)}개입니다."
        )
    if out_of_range:
        blocking_reasons.append(
            f"핵심 지표 허용 범위를 벗어난 항목이 {len(out_of_range)}개입니다."
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
            "baseline_available": baseline_available,
            "expected_after_available": expected_after_available,
            "expected_ranges_available": expected_ranges_available,
            "status": screen_status,
            "verification_status": verification_status,
            "blocking": screen_status != "expected_match",
            "blocking_reasons": blocking_reasons,
            "before": before or None,
            "expected_after": expected_after or None,
            "expected_ranges": expected_ranges or None,
            "after": after,
            "differences": screen_differences,
            "out_of_range": out_of_range,
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
