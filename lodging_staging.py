"""정부 숙박 원본을 개발 DB staging에 저장하는 순수 검증·적재 서비스."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import secrets
from collections import Counter
from pathlib import Path

import psycopg2
import psycopg2.extras

from db import get_conn
from lodging_data_contract import (
    GOVERNMENT_LODGING_SOURCES,
    STATUS_REVIEW,
    build_registry_permit_identity,
    build_source_snapshot_identity,
    classify_operation_status,
    legacy_lodging_type_for_hygiene,
    normalize_reference_date,
    normalize_text,
    service_category_for_hygiene,
    source_is_supported,
)


STAGING_STATUSES = (
    "uploaded",
    "parsed",
    "validating",
    "review_required",
    "validated",
    "approved",
    "dry_run",
    "applied",
    "failed",
)

APPROVAL_STATUSES = ("draft", "approved", "dry_run", "applied", "failed")

# 기존 importer의 source 이름을 새 8종 계약에 연결한다. 기존 관리자
# 경로는 계속 기존 테이블을 사용하고, 새 staging API는 canonical key를 쓴다.
SOURCE_ALIASES = {
    "airbnb": "foreign_city_homestay",
    "rural": "rural_homestay",
    "hanok": "hanok",
}

_FIELD_ALIASES = {
    "authority_code": (
        "개방자치단체코드",
        "OPN_ATMY_GRP_CD",
        "관할기관코드",
        "시군구코드",
    ),
    "permit_number": ("관리번호", "MNG_NO", "permit_number"),
    "biz_name": ("사업장명", "BPLC_NM", "상호명", "업소명"),
    "hygiene_type": (
        "위생업태명",
        "업태구분명",
        "문화체육업종명",
        "업종명",
        "업태명",
        "SNTTN_BZSTAT_NM",
    ),
    "status": (
        "영업상태명",
        "영업상태",
        "운영상태",
        "관리상태",
        "SALS_STTS_NM",
        "manageSttus",
    ),
    "road_address": ("도로명주소", "ROAD_NM_ADDR", "도로명"),
    "jibun_address": ("지번주소", "LOTNO_ADDR", "지번"),
}

_SOURCE_DEFAULT_RAW_TYPE = {
    key: next(iter(config["raw_types"]))
    for key, config in GOVERNMENT_LODGING_SOURCES.items()
    if len(config["raw_types"]) == 1
}


def canonical_source_key(source_key):
    source = normalize_text(source_key)
    source = SOURCE_ALIASES.get(source, source)
    if not source_is_supported(source):
        raise ValueError("지원하지 않는 숙박 원본입니다.")
    return source


def assert_development_staging():
    """호출자가 개발 staging 경로를 명시적으로 거치게 하는 계약 지점."""
    return None


def _database_fingerprint(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT current_database() AS db,
                   inet_server_addr()::text AS host,
                   inet_server_port() AS port
            """
        )
        row = cur.fetchone()
        if isinstance(row, dict):
            return row["db"], row["host"], row["port"]
        return tuple(row)
    finally:
        cur.close()


def assert_development_connection(conn):
    """실제 연결 대상이 운영 DB와 같으면 쓰기 전에 차단한다."""
    assert_development_staging()
    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        raise RuntimeError("운영 DB 식별 정보가 없어 staging 쓰기를 차단했습니다.")
    production_conn = psycopg2.connect(production_url, connect_timeout=5)
    try:
        if _database_fingerprint(conn) == _database_fingerprint(production_conn):
            raise RuntimeError("숙박 staging은 운영 DB에 쓸 수 없습니다.")
    finally:
        production_conn.close()


def _require_admin_actor(value, label):
    try:
        actor_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 관리자 정보가 필요합니다.") from None
    if actor_id <= 0:
        raise ValueError(f"{label} 관리자 정보가 필요합니다.")
    return actor_id


def _first_value(row, aliases):
    for field in aliases:
        if field in row and normalize_text(row.get(field)):
            return normalize_text(row.get(field))
    return ""


def _read_csv(filepath):
    path = Path(filepath)
    if path.suffix.lower() != ".csv":
        raise ValueError("3단계 staging은 CSV만 지원합니다.")
    raw = path.read_bytes()
    decoded = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("CSV 인코딩을 확인할 수 없습니다.")
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("CSV 헤더가 없습니다.")
    return raw, [dict(row) for row in reader]


def normalize_source_row(source_key, raw_row, reference_date, row_number):
    """원본 한 행을 staging 저장 형태로 바꾸며 보류 사유를 계산한다."""
    source = canonical_source_key(source_key)
    snapshot_date = normalize_reference_date(reference_date)
    if not snapshot_date:
        raise ValueError("원본 기준일이 올바르지 않습니다.")

    authority_code = _first_value(raw_row, _FIELD_ALIASES["authority_code"])
    source_permit_number = _first_value(raw_row, _FIELD_ALIASES["permit_number"])
    biz_name = _first_value(raw_row, _FIELD_ALIASES["biz_name"])
    raw_type = _first_value(raw_row, _FIELD_ALIASES["hygiene_type"])
    raw_status = _first_value(raw_row, _FIELD_ALIASES["status"])
    road_address = _first_value(raw_row, _FIELD_ALIASES["road_address"])
    jibun_address = _first_value(raw_row, _FIELD_ALIASES["jibun_address"])

    # 고정 원본은 파일 종류가 원문 업태를 알려주므로, 업태 컬럼이 없는
    # 파일에서도 서비스 분류를 판정한다. 숙박업의 공백 업태는 보류한다.
    classification_type = raw_type or _SOURCE_DEFAULT_RAW_TYPE.get(source, "")
    service_category = service_category_for_hygiene(classification_type)
    status_bucket = classify_operation_status(raw_status)
    snapshot_key = build_source_snapshot_identity(
        source,
        snapshot_date,
        authority_code,
        source_permit_number,
    )

    reasons = []
    if not source_permit_number:
        reasons.append("관리번호 없음")
    if not authority_code:
        reasons.append("관할기관 코드 없음")
    if not biz_name:
        reasons.append("사업장명 없음")
    if not snapshot_key:
        reasons.append("원본 기준일·식별키 부족")
    if service_category is None:
        reasons.append("알 수 없는 업태")
    if status_bucket == STATUS_REVIEW:
        reasons.append("알 수 없는 영업상태")

    if service_category == "미분류":
        reasons.append("업태 공백·관리자 확인")
    row_state = "validated" if not reasons else "review_required"
    return {
        "row_number": int(row_number),
        "snapshot_key": snapshot_key or (
            f"{source.upper()}:{snapshot_date}:_:{row_number}"
        ),
        "authority_code": authority_code or None,
        "source_permit_number": source_permit_number or None,
        "permit_number": (
            build_registry_permit_identity(
                source, authority_code, source_permit_number
            )
            if source_permit_number and authority_code
            else None
        ),
        "biz_name": biz_name or None,
        "raw_hygiene_type": raw_type or None,
        "service_category": service_category,
        "legacy_lodging_type": legacy_lodging_type_for_hygiene(classification_type),
        "raw_status": raw_status or None,
        "status_bucket": status_bucket,
        "road_address": road_address or None,
        "jibun_address": jibun_address or None,
        "raw_record": raw_row,
        "row_state": row_state,
        "review_reason": "; ".join(reasons) or None,
        "diff_kind": "review_required" if reasons else "new",
    }


def inspect_csv(source_key, filepath, reference_date):
    """DB에 쓰지 않고 파일과 정규화 결과를 검사한다."""
    source = canonical_source_key(source_key)
    raw, rows = _read_csv(filepath)
    normalized = [
        normalize_source_row(source, row, reference_date, index)
        for index, row in enumerate(rows, start=2)
    ]
    key_counts = Counter(row["snapshot_key"] for row in normalized)
    for row in normalized:
        if key_counts[row["snapshot_key"]] > 1:
            row["row_state"] = "review_required"
            duplicate_reason = "원본 기준일 내 snapshot key 중복"
            row["review_reason"] = (
                f"{row['review_reason']}; {duplicate_reason}"
                if row["review_reason"]
                else duplicate_reason
            )
            row["diff_kind"] = "review_required"
    valid_rows = sum(row["row_state"] == "validated" for row in normalized)
    review_rows = len(normalized) - valid_rows
    return {
        "source_key": source,
        "filename": os.path.basename(filepath),
        "file_ext": "csv",
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "reference_date": normalize_reference_date(reference_date),
        "total_rows": len(rows),
        "parsed_rows": len(normalized),
        "valid_rows": valid_rows,
        "review_rows": review_rows,
        "status": "validated" if review_rows == 0 else "review_required",
        "rows": normalized,
    }


def _batch_key(source_key, reference_date, file_sha256):
    source = canonical_source_key(source_key)
    snapshot_date = normalize_reference_date(reference_date)
    if not snapshot_date:
        raise ValueError("원본 기준일이 올바르지 않습니다.")
    return f"{source}:{snapshot_date}:{file_sha256}"


def _diff_kind(item, existing):
    if item["row_state"] != "validated":
        return "review_required"
    if not existing:
        return "new"
    status_changed = normalize_text(existing.get("biz_status_name")) != normalize_text(
        item.get("raw_status")
    )
    other_changed = any(
        normalize_text(existing.get(current_field))
        != normalize_text(item.get(staged_field))
        for current_field, staged_field in (
            ("biz_name", "biz_name"),
            ("road_address", "road_address"),
            ("jibun_address", "jibun_address"),
            ("hygiene_type", "raw_hygiene_type"),
        )
    )
    if status_changed and not other_changed:
        return "status_change"
    if status_changed or other_changed:
        return "changed"
    return "unchanged"


def stage_csv_file(
    source_key,
    filepath,
    reference_date,
    *,
    uploaded_by=None,
):
    """파일·정규화 행을 개발 staging에 원자적으로 저장한다.

    동일 원본·기준일·해시를 다시 올리면 기존 배치를 반환하며 새 행을
    만들지 않는다. lodging_registry와 master_buildings에는 쓰지 않는다.
    """
    assert_development_staging()
    inspected = inspect_csv(source_key, filepath, reference_date)
    batch_key = _batch_key(
        inspected["source_key"],
        inspected["reference_date"],
        inspected["file_sha256"],
    )
    raw = Path(filepath).read_bytes()
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO lodging_source_batches (
                batch_key, source_key, filename, file_ext, file_sha256,
                reference_date, file_data, status, total_rows, parsed_rows,
                valid_rows, review_rows, result, uploaded_by
            ) VALUES (
                %s, %s, %s, 'csv', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (batch_key) DO NOTHING
            RETURNING id
            """,
            (
                batch_key,
                inspected["source_key"],
                inspected["filename"],
                inspected["file_sha256"],
                inspected["reference_date"],
                raw,
                inspected["status"],
                inspected["total_rows"],
                inspected["parsed_rows"],
                inspected["valid_rows"],
                inspected["review_rows"],
                psycopg2.extras.Json({
                    "file_sha256": inspected["file_sha256"],
                    "reference_date": inspected["reference_date"],
                }),
                uploaded_by,
            ),
        )
        inserted = cur.fetchone()
        if not inserted:
            cur.execute(
                "SELECT id, status FROM lodging_source_batches WHERE batch_key=%s",
                (batch_key,),
            )
            existing = cur.fetchone()
            conn.commit()
            return {
                "batch_id": existing["id"],
                "batch_key": batch_key,
                "created": False,
                "status": existing["status"],
            }
        batch_id = inserted["id"]
        permit_numbers = [
            item["permit_number"]
            for item in inspected["rows"]
            if item.get("permit_number")
        ]
        existing_by_permit = {}
        for offset in range(0, len(permit_numbers), 5000):
            cur.execute(
                """
                SELECT permit_number, biz_name, road_address, jibun_address,
                       biz_status_name, hygiene_type
                  FROM lodging_registry
                 WHERE permit_number = ANY(%s)
                """,
                (permit_numbers[offset:offset + 5000],),
            )
            existing_by_permit.update({
                row["permit_number"]: row
                for row in cur.fetchall()
            })
        for item in inspected["rows"]:
            item["diff_kind"] = _diff_kind(
                item,
                existing_by_permit.get(item.get("permit_number")),
            )
            cur.execute(
                """
                INSERT INTO lodging_source_rows (
                    batch_id, row_number, snapshot_key, authority_code,
                    source_permit_number, permit_number, biz_name,
                    raw_hygiene_type, service_category, legacy_lodging_type,
                    raw_status, status_bucket, road_address, jibun_address,
                    raw_record, row_state, review_reason, diff_kind
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    batch_id,
                    item["row_number"],
                    item["snapshot_key"],
                    item["authority_code"],
                    item["source_permit_number"],
                    item["permit_number"],
                    item["biz_name"],
                    item["raw_hygiene_type"],
                    item["service_category"],
                    item["legacy_lodging_type"],
                    item["raw_status"],
                    item["status_bucket"],
                    item["road_address"],
                    item["jibun_address"],
                    psycopg2.extras.Json(item["raw_record"]),
                    item["row_state"],
                    item["review_reason"],
                    item["diff_kind"],
                ),
            )
        conn.commit()
        return {
            "batch_id": batch_id,
            "batch_key": batch_key,
            "created": True,
            "status": inspected["status"],
            "total_rows": inspected["total_rows"],
            "valid_rows": inspected["valid_rows"],
            "review_rows": inspected["review_rows"],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def create_approval_batch(batch_id, *, created_by=None):
    """검증 통과 행만 별도 승인 배치 초안으로 고정한다."""
    assert_development_staging()
    created_by = _require_admin_actor(created_by, "생성")
    approval_key = f"LODGING-APPROVAL:{secrets.token_hex(12)}"
    run_id = secrets.token_hex(16)
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, status
              FROM lodging_source_batches
             WHERE id=%s
            """,
            (batch_id,),
        )
        source_batch = cur.fetchone()
        if not source_batch:
            raise ValueError("staging 배치를 찾을 수 없습니다.")
        if source_batch["status"] not in {"validated", "review_required"}:
            raise ValueError("승인 배치를 만들 수 없는 staging 상태입니다.")
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
        if not cur.fetchone()["count"]:
            raise ValueError("승인 가능한 검증 통과 행이 없습니다.")
        cur.execute(
            """
            INSERT INTO lodging_approval_batches (
                approval_key, source_batch_id, status, created_by, run_id
            ) VALUES (%s, %s, 'draft', %s, %s)
            ON CONFLICT (source_batch_id) DO NOTHING
            RETURNING id
            """,
            (approval_key, batch_id, created_by, run_id),
        )
        inserted = cur.fetchone()
        if not inserted:
            cur.execute(
                """
                SELECT id, approval_key, status, row_count, run_id
                  FROM lodging_approval_batches
                 WHERE source_batch_id=%s
                """,
                (batch_id,),
            )
            existing = cur.fetchone()
            conn.commit()
            return dict(existing)
        approval_id = inserted["id"]
        cur.execute(
            """
            INSERT INTO lodging_approval_rows (
                approval_batch_id, source_row_id, action, payload
            )
            SELECT %s, id,
                   CASE
                     WHEN diff_kind='status_change' THEN 'status_change'
                     WHEN diff_kind='changed' THEN 'update'
                     ELSE 'insert'
                   END,
                   jsonb_build_object(
                     'snapshot_key', snapshot_key,
                     'permit_number', permit_number,
                     'authority_code', authority_code,
                     'source_permit_number', source_permit_number,
                     'biz_name', biz_name,
                     'raw_hygiene_type', raw_hygiene_type,
                     'service_category', service_category,
                     'legacy_lodging_type', legacy_lodging_type,
                     'raw_status', raw_status,
                     'status_bucket', status_bucket,
                     'road_address', road_address,
                     'jibun_address', jibun_address,
                     'raw_record', raw_record,
                     'diff_kind', diff_kind
                   )
              FROM lodging_source_rows
             WHERE batch_id=%s
               AND row_state='validated'
               AND diff_kind <> 'unchanged'
            """,
            (approval_id, batch_id),
        )
        row_count = cur.rowcount
        cur.execute(
            """
            UPDATE lodging_approval_batches
               SET row_count=%s
             WHERE id=%s
            """,
            (row_count, approval_id),
        )
        conn.commit()
        return {
            "id": approval_id,
            "approval_key": approval_key,
            "status": "draft",
            "row_count": row_count,
            "run_id": run_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def approve_batch(approval_batch_id, *, approved_by):
    """사람의 승인만 기록하고 운영 원장은 변경하지 않는다."""
    assert_development_staging()
    approved_by = _require_admin_actor(approved_by, "승인")
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE lodging_approval_batches
               SET status='approved', approved_by=%s, approved_at=NOW()
             WHERE id=%s AND status='draft'
            RETURNING id, status, row_count, run_id
            """,
            (approved_by, approval_batch_id),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("승인 초안이 아니거나 이미 처리된 배치입니다.")
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _finish_approval_attempt(
    approval_batch_id,
    attempt_id,
    run_id,
    status,
    *,
    result=None,
    error=None,
):
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE lodging_approval_attempts
               SET status=%s, result=%s, error=%s,
                   heartbeat_at=NOW(), finished_at=NOW()
             WHERE id=%s
               AND approval_batch_id=%s
               AND run_id=%s
               AND status='running'
            """,
            (
                status,
                psycopg2.extras.Json(result or {}),
                error,
                attempt_id,
                approval_batch_id,
                run_id,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("승인 배치 실행 소유권이 변경되었습니다.")
        cur.execute(
            """
            UPDATE lodging_approval_batches
               SET status=%s, result=%s, error=%s,
                   heartbeat_at=NOW(), finished_at=NOW()
             WHERE id=%s AND run_id=%s
            """,
            (
                "dry_run" if status == "done" else "failed",
                psycopg2.extras.Json(result or {}),
                error,
                approval_batch_id,
                run_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def run_approval_dry_run(approval_batch_id):
    """승인 payload 건수만 검증하며 lodging_registry에는 쓰지 않는다.

    재시도는 같은 승인 run_id 아래 attempt_number만 증가시켜 감사 이력을
    보존한다.
    """
    assert_development_staging()
    conn = get_conn()
    assert_development_connection(conn)
    cur = conn.cursor()
    attempt_id = None
    run_id = None
    try:
        cur.execute(
            """
            SELECT id, status, run_id
              FROM lodging_approval_batches
             WHERE id=%s
             FOR UPDATE
            """,
            (approval_batch_id,),
        )
        batch = cur.fetchone()
        if not batch:
            raise ValueError("승인 배치를 찾을 수 없습니다.")
        if batch["status"] not in {"approved", "dry_run", "failed"}:
            raise ValueError("승인 완료된 배치만 dry-run할 수 있습니다.")
        run_id = batch["run_id"]
        cur.execute(
            """
            SELECT id
              FROM lodging_approval_attempts
             WHERE approval_batch_id=%s
               AND status='running'
               AND heartbeat_at >= NOW() - INTERVAL '5 minutes'
             LIMIT 1
            """,
            (approval_batch_id,),
        )
        if cur.fetchone():
            raise RuntimeError("같은 승인 배치의 dry-run이 이미 실행 중입니다.")
        cur.execute(
            """
            UPDATE lodging_approval_attempts
               SET status='failed',
                   error='stale dry-run recovered before retry',
                   finished_at=NOW()
             WHERE approval_batch_id=%s
               AND status='running'
               AND heartbeat_at < NOW() - INTERVAL '5 minutes'
            """,
            (approval_batch_id,),
        )
        cur.execute(
            """
            SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt
              FROM lodging_approval_attempts
             WHERE approval_batch_id=%s
            """,
            (approval_batch_id,),
        )
        attempt_number = int(cur.fetchone()["next_attempt"])
        cur.execute(
            """
            INSERT INTO lodging_approval_attempts (
                approval_batch_id, run_id, attempt_number, mode, status
            ) VALUES (%s, %s, %s, 'dry_run', 'running')
            RETURNING id
            """,
            (approval_batch_id, run_id, attempt_number),
        )
        attempt_id = cur.fetchone()["id"]
        cur.execute(
            """
            UPDATE lodging_approval_batches
               SET status='dry_run', started_at=NOW(), heartbeat_at=NOW(),
                   finished_at=NULL, error=NULL
             WHERE id=%s AND run_id=%s
            """,
            (approval_batch_id, run_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    try:
        conn = get_conn()
        assert_development_connection(conn)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT action, COUNT(*) AS count
                  FROM lodging_approval_rows
                 WHERE approval_batch_id=%s
                 GROUP BY action
                """,
                (approval_batch_id,),
            )
            action_counts = {
                row["action"]: int(row["count"])
                for row in cur.fetchall()
            }
            cur.execute("SELECT COUNT(*) AS count FROM lodging_registry")
            registry_count = int(cur.fetchone()["count"])
        finally:
            cur.close()
            conn.close()
        result = {
            "run_id": run_id,
            "attempt_number": attempt_number,
            "action_counts": action_counts,
            "total_changes": sum(action_counts.values()),
            "registry_count_before_apply": registry_count,
            "applied": False,
        }
        _finish_approval_attempt(
            approval_batch_id,
            attempt_id,
            run_id,
            "done",
            result=result,
        )
        return result
    except Exception as exc:
        _finish_approval_attempt(
            approval_batch_id,
            attempt_id,
            run_id,
            "failed",
            error=str(exc)[:1000],
        )
        raise