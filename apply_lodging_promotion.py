"""승인된 정부 숙박 운영 기준 manifest를 운영 원장에 안전하게 반영한다."""

from __future__ import annotations

import argparse
import json
import os
import re
from decimal import Decimal, InvalidOperation

import psycopg2
import psycopg2.extras

from addr_norm import normalize_jibun_prefix, normalize_name, normalize_road_prefix
from db import get_conn
from lodging_promotion import (
    _canonical_hash,
    _fetch_production_snapshot,
    _validate_target_admission,
    run_production_manifest_dry_run,
)
from lodging_staging import _database_fingerprint, assert_development_connection
from stats_cache import mark_master_stats_invalidated_in_transaction


_PROMOTION_LOCK_KEY = 719_240_392
_AUDIT_KEY_PREFIX = "lodging_promotion_applied:"


def _text(value):
    if value is None:
        return None
    result = str(value).strip()
    return result if result and result.lower() not in {"none", "nan"} else None


def _first(raw, *keys):
    for key in keys:
        value = _text((raw or {}).get(key))
        if value is not None:
            return value
    return None


def _integer(value):
    value = _text(value)
    if value is None:
        return None
    try:
        number = Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return int(number) if number == number.to_integral_value() else None


def _decimal(value):
    value = _text(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _phone(value):
    value = _text(value)
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def _room_count(payload):
    if payload.get("source_key") in {"general_camping", "auto_camping"}:
        return None
    raw = payload.get("raw_record") or {}
    direct = _first(raw, "객실수", "room_count")
    if direct is not None:
        return _integer(direct)
    korean = [_first(raw, "한실수"), _first(raw, "양실수")]
    api = [_first(raw, "KSRM_CNT"), _first(raw, "WSRM_CNT")]
    values = korean if any(value is not None for value in korean) else api
    if not any(value is not None for value in values):
        return None
    return sum(_integer(value) or 0 for value in values)


def _camping_site_count(payload):
    if payload.get("source_key") not in {"general_camping", "auto_camping"}:
        return None
    raw = payload.get("raw_record") or {}
    value = _first(
        raw,
        "야영사이트수",
        "야영사이트 수",
        "사이트수",
        "사이트 수",
        "캠핑사이트수",
        "캠핑사이트 수",
    )
    return _integer(value)


def build_registry_record(payload, existing=None):
    """승격 payload를 운영 lodging_registry 컬럼으로 변환한다."""
    raw = payload.get("raw_record") or {}
    room_count = _room_count(payload)
    camping_site_count = _camping_site_count(payload)
    if existing:
        if room_count is None:
            room_count = existing.get("room_count")
        if camping_site_count is None:
            camping_site_count = existing.get("camping_site_count")
    road_address = _text(payload.get("road_address"))
    jibun_address = _text(payload.get("jibun_address"))
    biz_name = _text(payload.get("biz_name"))
    if not payload.get("permit_number") or not biz_name:
        raise ValueError("permit_number 또는 사업장명이 없는 승인 payload입니다.")
    is_active = payload.get("status_bucket") == "active"
    new_building_id = (
        payload.get("production_building_id")
        if is_active and payload.get("production_match_state") == "existing_building"
        else None
    )
    return {
        "permit_number": payload["permit_number"],
        "biz_name": biz_name,
        "road_address": road_address,
        "jibun_address": jibun_address,
        "permit_date": _first(raw, "인허가일자", "LCPMT_YMD", "허가일자"),
        "biz_status_name": _text(payload.get("raw_status")),
        "biz_status_detail": _first(
            raw, "상세영업상태명", "DTL_SALS_STTS_NM", "상세영업상태"
        ),
        "room_count": room_count,
        "camping_site_count": camping_site_count,
        "hygiene_type": _text(payload.get("raw_hygiene_type")),
        "phone": _phone(_first(raw, "전화번호", "TELNO", "전화")),
        "road_norm": normalize_road_prefix(road_address),
        "jibun_norm": normalize_jibun_prefix(jibun_address),
        "biz_name_norm": normalize_name(biz_name),
        "source_updated_at": _first(
            raw, "데이터갱신시점", "DAT_UPDT_PNT", "최종수정시점"
        ),
        "bld_use_nm": _first(raw, "건물용도명", "건물형태구분명"),
        "facility_area": _decimal(
            _first(raw, "시설규모", "주택면적", "소재지면적")
        ),
        "region_name": _first(raw, "지역구분명", "지역명"),
        "applied_building_id": (
            existing.get("applied_building_id") if existing else new_building_id
        ),
    }


def _load_manifest(manifest_id):
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, manifest_key, status, source_batch_ids,
                   production_baseline_fingerprint, target_payload_sha256,
                   row_count, result, run_id
              FROM lodging_promotion_manifests
             WHERE id=%s
            """,
            (manifest_id,),
        )
        manifest = cur.fetchone()
        if not manifest:
            raise ValueError("운영 기준 manifest를 찾을 수 없습니다.")
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
        if len(targets) != int(manifest["row_count"]):
            raise RuntimeError("manifest 행 수가 변경되었습니다.")
        _validate_target_admission(targets, allow_manual_review=False)
        if _canonical_hash(targets) != manifest["target_payload_sha256"]:
            raise RuntimeError("manifest payload가 생성 이후 변경되었습니다.")
        return dict(manifest), targets
    finally:
        cur.close()
        conn.close()


def _mark_development_applied(manifest, result):
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE lodging_promotion_manifests
               SET status='applied', result=%s, error=NULL,
                   heartbeat_at=NOW(), finished_at=NOW()
             WHERE id=%s AND run_id=%s
             RETURNING id
            """,
            (
                psycopg2.extras.Json(result),
                manifest["id"],
                manifest["run_id"],
            ),
        )
        if not cur.fetchone():
            raise RuntimeError("개발 manifest 실행 소유권이 변경되었습니다.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def apply_manifest(manifest_id, *, confirm_run_id):
    """승인·dry-run 완료 manifest를 운영 DB에 한 트랜잭션으로 반영한다."""
    manifest, targets = _load_manifest(manifest_id)
    if manifest["status"] != "dry_run":
        raise ValueError("관리자 승인 후 dry-run이 완료된 manifest만 반영할 수 있습니다.")
    if confirm_run_id != manifest["run_id"]:
        raise ValueError("확인용 run_id가 manifest와 일치하지 않습니다.")
    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        raise RuntimeError("PROD_DATABASE_URL이 없습니다.")
    prod_conn = psycopg2.connect(
        production_url,
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    prod_conn.set_session(isolation_level="SERIALIZABLE")
    cur = prod_conn.cursor()
    audit_key = _AUDIT_KEY_PREFIX + manifest["manifest_key"]
    try:
        cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", (_PROMOTION_LOCK_KEY,))
        if not cur.fetchone()["acquired"]:
            raise RuntimeError("다른 숙박 승격 작업이 실행 중입니다.")
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (audit_key,))
        audit = cur.fetchone()
        if audit:
            previous = json.loads(audit["value"])
            if previous.get("run_id") != manifest["run_id"]:
                raise RuntimeError("같은 manifest key에 다른 run_id 반영 기록이 있습니다.")
            _mark_development_applied(manifest, previous)
            return {**previous, "already_applied": True}

        current_registry, _buildings, current_fingerprint, production_fingerprint = (
            _fetch_production_snapshot(prod_conn)
        )
        if _database_fingerprint(prod_conn) != production_fingerprint:
            raise RuntimeError("운영 DB 기준선 연결이 일치하지 않습니다.")
        if current_fingerprint != manifest["production_baseline_fingerprint"]:
            raise RuntimeError("운영 기준선이 변경되어 manifest를 다시 생성해야 합니다.")
        registry_by_permit = {
            row["permit_number"]: row
            for row in current_registry
            if row.get("permit_number")
        }
        records = [
            build_registry_record(
                target["payload"],
                registry_by_permit.get(target["payload"]["permit_number"]),
            )
            for target in targets
        ]
        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO lodging_registry (
                permit_number, biz_name, road_address, jibun_address,
                permit_date, biz_status_name, biz_status_detail,
                room_count, camping_site_count, hygiene_type, phone,
                road_norm, jibun_norm, biz_name_norm, source_updated_at,
                bld_use_nm, facility_area, region_name, applied_building_id
            ) VALUES (
                %(permit_number)s, %(biz_name)s, %(road_address)s, %(jibun_address)s,
                %(permit_date)s, %(biz_status_name)s, %(biz_status_detail)s,
                %(room_count)s, %(camping_site_count)s, %(hygiene_type)s, %(phone)s,
                %(road_norm)s, %(jibun_norm)s, %(biz_name_norm)s,
                %(source_updated_at)s, %(bld_use_nm)s, %(facility_area)s,
                %(region_name)s, %(applied_building_id)s
            )
            ON CONFLICT (permit_number) DO UPDATE SET
                biz_name=EXCLUDED.biz_name,
                road_address=COALESCE(EXCLUDED.road_address, lodging_registry.road_address),
                jibun_address=COALESCE(EXCLUDED.jibun_address, lodging_registry.jibun_address),
                permit_date=COALESCE(EXCLUDED.permit_date, lodging_registry.permit_date),
                biz_status_name=EXCLUDED.biz_status_name,
                biz_status_detail=COALESCE(EXCLUDED.biz_status_detail, lodging_registry.biz_status_detail),
                room_count=COALESCE(EXCLUDED.room_count, lodging_registry.room_count),
                camping_site_count=COALESCE(EXCLUDED.camping_site_count, lodging_registry.camping_site_count),
                hygiene_type=COALESCE(EXCLUDED.hygiene_type, lodging_registry.hygiene_type),
                phone=COALESCE(EXCLUDED.phone, lodging_registry.phone),
                road_norm=COALESCE(EXCLUDED.road_norm, lodging_registry.road_norm),
                jibun_norm=COALESCE(EXCLUDED.jibun_norm, lodging_registry.jibun_norm),
                biz_name_norm=EXCLUDED.biz_name_norm,
                source_updated_at=COALESCE(EXCLUDED.source_updated_at, lodging_registry.source_updated_at),
                bld_use_nm=COALESCE(EXCLUDED.bld_use_nm, lodging_registry.bld_use_nm),
                facility_area=COALESCE(EXCLUDED.facility_area, lodging_registry.facility_area),
                region_name=COALESCE(EXCLUDED.region_name, lodging_registry.region_name),
                applied_building_id=lodging_registry.applied_building_id,
                updated_at=NOW()
            """,
            records,
            page_size=500,
        )
        action_counts = dict((manifest.get("result") or {}).get("action_counts") or {})
        result = {
            "manifest_id": manifest["id"],
            "manifest_key": manifest["manifest_key"],
            "run_id": manifest["run_id"],
            "row_count": len(records),
            "action_counts": action_counts,
            "new_permits": int(action_counts.get("insert", 0)),
            "production_writes": len(records),
            "applied": True,
            "already_applied": False,
        }
        cur.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO NOTHING
            """,
            (audit_key, json.dumps(result, ensure_ascii=False)),
        )
        if cur.rowcount != 1:
            raise RuntimeError("운영 승격 감사 표식을 선점하지 못했습니다.")
        mark_master_stats_invalidated_in_transaction(cur, "lodging_promotion")
        prod_conn.commit()
    except Exception:
        prod_conn.rollback()
        raise
    finally:
        cur.close()
        prod_conn.close()
    _mark_development_applied(manifest, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_id", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-run-id")
    args = parser.parse_args()
    if args.apply:
        if not args.confirm_run_id:
            parser.error("--apply에는 --confirm-run-id가 필요합니다.")
        result = apply_manifest(
            args.manifest_id,
            confirm_run_id=args.confirm_run_id,
        )
    else:
        result = run_production_manifest_dry_run(args.manifest_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()