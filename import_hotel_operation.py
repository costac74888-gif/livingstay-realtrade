"""2024 호텔업 운영현황 지역별 XLSX ZIP을 중복 없이 적재한다."""

import argparse
import hashlib
import io
import os
import re
import zipfile

from openpyxl import load_workbook
from psycopg2.extras import execute_values

from address_utils import sido_core
SOURCE_NAME = "한국호텔업협회 호텔업 운영현황"
DEFAULT_YEAR = 2024
EXPECTED_REGION_FILE_COUNT = 16
EXPECTED_SIDOS = frozenset({
    "서울", "부산", "대구", "인천", "광주", "대전", "울산",
    "경기", "강원", "충청북", "충청남", "전라북", "전라남",
    "경상북", "경상남", "제주",
})
MAX_ARCHIVE_BYTES = 25 * 1024**2
MAX_ARCHIVE_MEMBERS = 100
MAX_EXTRACTED_XLSX_BYTES = 10 * 1024**2
MAX_TOTAL_EXTRACTED_BYTES = 25 * 1024**2


def _decoded_member_name(name):
    """오래된 한국어 ZIP의 CP437로 잘못 해석된 파일명을 복원한다."""
    if "지역" in name or "전국" in name:
        return name
    try:
        return name.encode("cp437").decode("euc-kr")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _number(value, integer=False):
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "").strip())
        return int(number) if integer else number
    except (TypeError, ValueError):
        return None


def parse_operation_archive(archive_bytes, reference_year=DEFAULT_YEAR):
    """업로드 ZIP을 자동 해제해 지역별 시군구 전체행과 등급행을 반환한다."""
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("호텔업 운영현황 ZIP은 25MB 이하만 업로드할 수 있습니다.")
    source_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    records = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("유효한 ZIP 압축파일이 아닙니다.") from exc
    with archive:
        if len(archive.infolist()) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("ZIP 내부 파일 수가 허용 범위를 초과했습니다.")
        members = []
        extracted_bytes = 0
        for info in archive.infolist():
            decoded = _decoded_member_name(info.filename).replace("\\", "/")
            if info.is_dir() or not decoded.lower().endswith(".xlsx"):
                continue
            if "지역 원데이터" not in decoded:
                continue
            if decoded.startswith("/") or ".." in decoded.split("/"):
                raise ValueError("ZIP 내부에 안전하지 않은 파일 경로가 있습니다.")
            if "/전국/" in f"/{decoded}":
                continue
            if info.file_size > MAX_EXTRACTED_XLSX_BYTES:
                raise ValueError("ZIP 내부 XLSX 한 개의 크기가 10MB를 초과했습니다.")
            extracted_bytes += info.file_size
            if extracted_bytes > MAX_TOTAL_EXTRACTED_BYTES:
                raise ValueError("ZIP을 푼 XLSX 전체 크기가 25MB를 초과했습니다.")
            members.append((decoded, info))
        for decoded_name, info in sorted(members, key=lambda item: item[0]):
            path_parts = decoded_name.split("/")
            if len(path_parts) < 2:
                continue
            sido_name = sido_core(path_parts[-2])
            workbook = load_workbook(
                io.BytesIO(archive.read(info)), read_only=True, data_only=True
            )
            worksheet = workbook["Sheet1"]
            current_sgg = None
            for row_number, row in enumerate(
                worksheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                label = str(row[0] or "")
                grade = str(row[16] or "").strip()
                stripped = re.sub(r"\s+", "", label)
                if not stripped or not grade:
                    continue
                if "/전체" in stripped:
                    current_sgg = None
                elif label[:1].isspace():
                    # 들여쓴 등급행은 직전 시군구(또는 시도 합계)에 속한다.
                    pass
                else:
                    current_sgg = stripped
                records.append((
                    decoded_name, row_number, sido_name, current_sgg, grade,
                    _number(row[8]), _number(row[9]), _number(row[10]),
                    _number(row[11]), _number(row[12], True),
                    _number(row[13], True), _number(row[14], True),
                    _number(row[15], True),
                ))
            workbook.close()
    return source_sha256, records


def parse_operation_zip(zip_path, reference_year=DEFAULT_YEAR):
    with open(zip_path, "rb") as source:
        return parse_operation_archive(source.read(), reference_year)


def validate_operation_records(records):
    source_files = {row[0] for row in records}
    sidos = {row[2] for row in records}
    sgg_overall = {
        row[2] for row in records if row[3] is not None and row[4] == "전체"
    }
    if (
        len(source_files) != EXPECTED_REGION_FILE_COUNT
        or sidos != EXPECTED_SIDOS
        or sgg_overall != sidos
    ):
        raise ValueError(
            "지역별 원본이 완전하지 않습니다: "
            f"파일 {len(source_files)}개, 시도 {len(sidos)}개, "
            f"시군구 전체행 보유 시도 {len(sgg_overall)}개, "
            f"누락 {sorted(EXPECTED_SIDOS - sidos)}, "
            f"예상 외 {sorted(sidos - EXPECTED_SIDOS)}"
        )


def _upload_year(value, records):
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValueError("기준연도를 네 자리 숫자로 입력하세요.") from None
    if not 2000 <= year <= 2100:
        raise ValueError("기준연도는 2000~2100년 범위여야 합니다.")
    member_years = {
        int(match.group(1))
        for row in records
        if (match := re.search(r"(?<!\d)(20\d{2})년", row[0]))
    }
    if member_years != {year}:
        raise ValueError(
            f"입력한 기준연도와 ZIP 내부 파일 연도가 다릅니다: {sorted(member_years)}"
        )
    return year


def latest_operation_status(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            WITH latest AS (
                SELECT id, reference_year, source_name, source_file, imported_at
                FROM hotel_operation_source_versions
                ORDER BY reference_year DESC, imported_at DESC, id DESC LIMIT 1
            )
            SELECT latest.reference_year, latest.source_name, latest.source_file,
                   latest.imported_at,
                   count(*) AS total_rows,
                   count(*) FILTER (
                       WHERE m.sgg_name IS NOT NULL AND m.grade='전체'
                   ) AS region_rows
            FROM latest JOIN hotel_operation_metrics m ON m.version_id=latest.id
            GROUP BY latest.id, latest.reference_year, latest.source_name,
                     latest.source_file, latest.imported_at
        """)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()


def import_uploaded_operation_zip(file, reference_year, conn):
    if file is None or not (file.filename or "").lower().endswith(".zip"):
        raise ValueError("호텔업 운영현황 ZIP 파일을 선택하세요.")
    raw = file.read(MAX_ARCHIVE_BYTES + 1)
    source_sha256, records = parse_operation_archive(raw, reference_year)
    validate_operation_records(records)
    reference_year = _upload_year(reference_year, records)
    current = latest_operation_status(conn)
    if current and reference_year < int(current["reference_year"]):
        raise ValueError(
            f"현재 적용 연도({current['reference_year']})보다 과거 자료는 적용할 수 없습니다."
        )
    source_file = os.path.basename(file.filename)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO hotel_operation_source_versions
                (reference_year, source_name, source_file, source_sha256)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_sha256) DO NOTHING
            RETURNING id
        """, (reference_year, SOURCE_NAME, source_file, source_sha256))
        inserted = cur.fetchone()
        if inserted:
            execute_values(cur, """
                INSERT INTO hotel_operation_metrics
                    (version_id, source_file, source_row_number, sido_name,
                     sgg_name, grade, occupancy_rate, adr, revpar,
                     foreign_guest_rate, available_room_nights, sold_room_nights,
                     room_count, business_count)
                VALUES %s
            """, [(inserted["id"], *record) for record in records])
            conn.commit()
        else:
            conn.rollback()
        status = latest_operation_status(conn) or {}
        return {
            **status,
            "inserted": bool(inserted),
            "uploaded_rows": len(records),
            "message": (
                "새 운영현황을 저장하고 서비스에 적용했습니다."
                if inserted else
                "이미 적용된 동일한 ZIP입니다. 중복 저장하지 않았습니다."
            ),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def import_operation_zip(zip_path, reference_year=DEFAULT_YEAR, conn=None):
    from db import get_conn

    source_sha256, records = parse_operation_zip(zip_path, reference_year)
    validate_operation_records(records)
    owned_connection = conn is None
    conn = conn or get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO hotel_operation_source_versions
                (reference_year, source_name, source_file, source_sha256)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_sha256) DO NOTHING
            RETURNING id
        """, (reference_year, SOURCE_NAME, os.path.basename(zip_path), source_sha256))
        inserted = cur.fetchone()
        if not inserted:
            conn.rollback()
            return {"inserted": False, "rows": 0, "sha256": source_sha256}
        version_id = inserted["id"]
        execute_values(cur, """
            INSERT INTO hotel_operation_metrics
                (version_id, source_file, source_row_number, sido_name, sgg_name,
                 grade, occupancy_rate, adr, revpar, foreign_guest_rate,
                 available_room_nights, sold_room_nights, room_count, business_count)
            VALUES %s
        """, [(version_id, *record) for record in records])
        conn.commit()
        return {"inserted": True, "rows": len(records), "sha256": source_sha256}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        if owned_connection:
            conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    args = parser.parse_args()
    result = import_operation_zip(args.zip_path, args.year)
    print(("적재 완료" if result["inserted"] else "이미 적재된 원본"), result["rows"])


if __name__ == "__main__":
    main()