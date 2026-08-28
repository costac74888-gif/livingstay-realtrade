"""V-World 부동산중개업 D171/D172 ZIP 일괄 가져오기.

D171은 중개업소 기본정보·영업상태, D172는 소속 인력 정보다.
원본 등록번호는 지역 또는 과거 체계에 따라 중복될 수 있으므로
broker_registry.reg_number에는 결정적 내부키를 넣고 source_reg_number에 원문을 보존한다.

사용 예:
  python import_vworld_brokers.py \
    --d171 attached_assets/AL_D171_00_20260827_1787901325566.zip \
    --d172 attached_assets/AL_D172_00_20260827_1787901294381.zip
"""

import argparse
import csv
import hashlib
import io
import re
import zipfile

from psycopg2.extras import execute_values

from addr_norm import normalize_jibun_prefix, normalize_road_prefix
from db import get_conn, init_db


SOURCE_D171 = "VWORLD_AL_D171"
SOURCE_D172 = "VWORLD_AL_D172"
DEFAULT_BATCH_SIZE = 1000


def _clean(value):
    return (value or "").strip() or None


def _digits(value):
    return re.sub(r"\D", "", value or "")


def parse_phone_numbers(value):
    """전화번호 셀에 여러 값이 있으면 순서대로 모두 숫자형 문자열로 반환한다."""
    found = []
    for token in re.split(r"[,;/|\n\r]+", value or ""):
        number = _digits(token)
        if 8 <= len(number) <= 11 and number not in found:
            found.append(number)
    return found


def _office_identity(region_code, reg_number, office_name, road_address, jibun_address):
    identity = "|".join(
        value or ""
        for value in (region_code, reg_number, office_name, road_address, jibun_address)
    )
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"VWORLD:{region_code or '-'}:{reg_number or '-'}:{suffix}"


def _member_identity(row):
    identity = "|".join(
        row.get(name, "")
        for name in (
            "법정동코드", "등록번호", "사업자상호", "중개업자명",
            "중개업자종별코드", "자격증번호", "직위구분코드",
        )
    )
    return "VWORLD:D172:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _csv_rows_from_zip(path, expected_prefix):
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name for name in archive.namelist()
            if name.upper().startswith(expected_prefix) and name.lower().endswith(".csv")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{path}: {expected_prefix} CSV가 정확히 1개여야 합니다 "
                f"(발견 {len(candidates)}개)"
            )
        with archive.open(candidates[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="cp949", newline="")
            yield from csv.DictReader(text)


def _flush_offices(cur, rows):
    if not rows:
        return 0
    # 원본에 완전히 같은 업소 행이 중복될 수 있다. 같은 INSERT 문 안에서 동일
    # 유일키를 두 번 갱신하면 PostgreSQL이 거부하므로 내부키 기준 마지막 행만 남긴다.
    rows = list({row[1]: row for row in rows}.values())
    execute_values(cur, """
        INSERT INTO broker_registry (
            office_name, reg_number, source_reg_number, source_region_code, source_name,
            road_address, jibun_address, phone, phone_numbers, reg_date, owner_name,
            biz_status, source_updated_at, road_norm, jibun_norm
        ) VALUES %s
        ON CONFLICT (reg_number) DO UPDATE SET
            office_name = EXCLUDED.office_name,
            source_reg_number = EXCLUDED.source_reg_number,
            source_region_code = EXCLUDED.source_region_code,
            source_name = EXCLUDED.source_name,
            road_address = EXCLUDED.road_address,
            jibun_address = EXCLUDED.jibun_address,
            phone = EXCLUDED.phone,
            phone_numbers = EXCLUDED.phone_numbers,
            reg_date = EXCLUDED.reg_date,
            owner_name = EXCLUDED.owner_name,
            biz_status = EXCLUDED.biz_status,
            source_updated_at = EXCLUDED.source_updated_at,
            road_norm = EXCLUDED.road_norm,
            jibun_norm = EXCLUDED.jibun_norm,
            updated_at = NOW()
    """, rows, page_size=len(rows))
    return len(rows)


def import_d171(cur, path, batch_size=DEFAULT_BATCH_SIZE):
    total = 0
    batch = []
    for row in _csv_rows_from_zip(path, "AL_D171"):
        office_name = _clean(row.get("사업자상호"))
        reg_number = _clean(row.get("등록번호"))
        region_code = _clean(row.get("법정동코드"))
        road_address = _clean(row.get("도로명주소"))
        jibun_address = _clean(row.get("지번주소"))
        if not office_name or not reg_number:
            continue
        phones = parse_phone_numbers(row.get("전화번호"))
        batch.append((
            office_name,
            _office_identity(region_code, reg_number, office_name, road_address, jibun_address),
            reg_number,
            region_code,
            SOURCE_D171,
            road_address,
            jibun_address,
            phones[0] if phones else None,
            phones,
            _clean(row.get("등록일자")),
            _clean(row.get("중개업자명")),
            _clean(row.get("상태구분명")),
            _clean(row.get("데이터기준일자")),
            normalize_road_prefix(road_address),
            normalize_jibun_prefix(jibun_address or road_address),
        ))
        if len(batch) >= batch_size:
            total += _flush_offices(cur, batch)
            batch.clear()
    total += _flush_offices(cur, batch)
    return total


def _flush_members(cur, rows):
    if not rows:
        return 0
    rows = list({row[0]: row for row in rows}.values())
    execute_values(cur, """
        INSERT INTO broker_registry_members (
            source_row_key, source_name, region_code, region_name, reg_number,
            office_name, member_name, member_type_code, member_type_name,
            license_number, license_date, position_code, position_name,
            source_updated_at
        ) VALUES %s
        ON CONFLICT (source_row_key) DO UPDATE SET
            source_name = EXCLUDED.source_name,
            region_code = EXCLUDED.region_code,
            region_name = EXCLUDED.region_name,
            reg_number = EXCLUDED.reg_number,
            office_name = EXCLUDED.office_name,
            member_name = EXCLUDED.member_name,
            member_type_code = EXCLUDED.member_type_code,
            member_type_name = EXCLUDED.member_type_name,
            license_number = EXCLUDED.license_number,
            license_date = EXCLUDED.license_date,
            position_code = EXCLUDED.position_code,
            position_name = EXCLUDED.position_name,
            source_updated_at = EXCLUDED.source_updated_at,
            updated_at = NOW()
    """, rows, page_size=len(rows))
    return len(rows)


def import_d172(cur, path, batch_size=DEFAULT_BATCH_SIZE):
    total = 0
    batch = []
    for row in _csv_rows_from_zip(path, "AL_D172"):
        reg_number = _clean(row.get("등록번호"))
        if not reg_number:
            continue
        batch.append((
            _member_identity(row),
            SOURCE_D172,
            _clean(row.get("법정동코드")),
            _clean(row.get("법정동명")),
            reg_number,
            _clean(row.get("사업자상호")),
            _clean(row.get("중개업자명")),
            _clean(row.get("중개업자종별코드")),
            _clean(row.get("중개업자종별명")),
            _clean(row.get("자격증번호")),
            _clean(row.get("자격증취득일")),
            _clean(row.get("직위구분코드")),
            _clean(row.get("직위구분명")),
            _clean(row.get("데이터기준일자")),
        ))
        if len(batch) >= batch_size:
            total += _flush_members(cur, batch)
            batch.clear()
    total += _flush_members(cur, batch)
    return total


def refresh_member_counts(cur):
    cur.execute("""
        UPDATE broker_registry
        SET member_count = 0, updated_at = NOW()
        WHERE source_name = %s AND member_count <> 0
    """, (SOURCE_D171,))
    cur.execute("""
        UPDATE broker_registry br
        SET member_count = counts.member_count,
            updated_at = NOW()
        FROM (
            SELECT region_code, reg_number, office_name, COUNT(*)::int AS member_count
            FROM broker_registry_members
            WHERE source_name = %s
            GROUP BY region_code, reg_number, office_name
        ) counts
        WHERE br.source_name = %s
          AND br.source_region_code = counts.region_code
          AND br.source_reg_number = counts.reg_number
          AND br.office_name = counts.office_name
    """, (SOURCE_D172, SOURCE_D171))
    return cur.rowcount


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--d171", help="AL_D171 ZIP 경로")
    parser.add_argument("--d172", help="AL_D172 ZIP 경로")
    parser.add_argument(
        "--only", choices=("all", "d171", "d172", "counts"), default="all",
        help="대용량 적재를 단계별로 실행할 때 사용할 단계",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size는 1 이상이어야 합니다")
    if args.only in ("all", "d171") and not args.d171:
        parser.error("--d171이 필요합니다")
    if args.only in ("all", "d172") and not args.d172:
        parser.error("--d172가 필요합니다")

    init_db()
    conn = get_conn()
    cur = conn.cursor()
    try:
        if args.only in ("all", "d171"):
            import_d171(cur, args.d171, args.batch_size)
            conn.commit()
            cur.execute(
                "SELECT COUNT(*) AS c FROM broker_registry WHERE source_name = %s",
                (SOURCE_D171,),
            )
            offices = cur.fetchone()["c"]
            print(f"D171 업소 {offices:,}건 적재 완료")
        if args.only in ("all", "d172"):
            import_d172(cur, args.d172, args.batch_size)
            conn.commit()
            cur.execute(
                "SELECT COUNT(*) AS c FROM broker_registry_members WHERE source_name = %s",
                (SOURCE_D172,),
            )
            members = cur.fetchone()["c"]
            print(f"D172 인력 {members:,}건 적재 완료")
        if args.only in ("all", "counts"):
            counted = refresh_member_counts(cur)
            conn.commit()
            print(f"업소 {counted:,}건의 인원 수 갱신 완료")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()