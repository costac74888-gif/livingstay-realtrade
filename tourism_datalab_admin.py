"""Validation and PostgreSQL-backed one-time staging for Data Lab uploads."""
import csv, hashlib, hmac, io, json, os, re, stat, zipfile, secrets
from datetime import timedelta

import import_tourism_stats as importer
from psycopg2.extras import execute_values

MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 10, 20 * 1024**2, 80 * 1024**2
MAX_MEMBERS, MAX_MEMBER_BYTES, MAX_EXPANDED_BYTES, MAX_RATIO = 100, 12 * 1024**2, 60 * 1024**2, 100
HEADER_CONTRACTS = {
 "visitor_sgg":("광역지자체명","기초지자체명","기초지자체 방문자 수","기초지자체 방문자 비율"),
 "foreign_sgg":("광역지자체명","기초지자체명","기초지자체 방문자 수","기초지자체 방문자 비율"),
 "visitor_sido":("광역지자체명","광역지자체 방문자 수","광역지자체 방문자 비율"),
 "foreign_sido":("광역지자체명","광역지자체 방문자 수","광역지자체 방문자 비율"),
 "visitor_trend":("기준년월","광역지자체","방문자 수"), "foreign_trend":("날짜","지역","외국인 방문자수"),
 "foreign_country":("국가명","비율(%)"), "consumption_region":("광역지자체 명","기초지자체 명","기초지자체 지출액 비율(%)","광역지자체 지출액 비율(%)"),
 "consumption_trend":("기준년월","광역지자체","지출액(천원)"), "consumption_sector":("대분류","중분류","대분류 지출액 비율","중분류 지출액 비율"),
 "search_sgg":("광역지자체","기초지자체","기초지자체 검색건수","기초지자체 검색건수 비율"), "search_trend":("기준년월","광역지자체","광역지자체 검색건수"),
 "search_ranking":("광역시/도","시/군/구","관광지ID","관광지명","중분류 카테고리","순위","검색건수"),
 "surge_domestic_dong":("시도명","시군구명","행정동명","기준년월","관광객수","전년동기관광객수","증감율"),
 "surge_foreign_dong":("시도명","시군구명","행정동명","기준년월","관광객수","전년동기관광객수","증감율"),
 "lodging_sector":("업종명","기준년도","숙박영업현황수","분포율"), "camping_sector":("업종명","기준년도","현황수","분포율"),
 "camping_site_type":("업종명","기준년도","현황수"),
}

def _owner(owner):
    if isinstance(owner, bool) or not isinstance(owner, int) or owner <= 0:
        raise ValueError("유효한 정수 admin_user_id가 필요합니다.")
    return owner

def _safe_name(name):
    return bool(name and os.path.basename(name) == name and re.fullmatch(r"[^/\\\x00-\x1f]{1,180}\.(zip|csv)", name, re.I))

def source_lock_key(source_file):
    """Stable signed bigint key for PostgreSQL transaction advisory locks."""
    return int.from_bytes(hashlib.sha256(source_file.encode()).digest()[:8], "big", signed=True)

def _csv_rows(name, raw):
    for encoding in ("utf-8-sig", "cp949"):
        try: text = raw.decode(encoding); break
        except UnicodeDecodeError: text = None
    if text is None: raise ValueError("CSV는 UTF-8-sig 또는 CP949여야 합니다.")
    if "\x00" in text or any(ord(x) < 32 and x not in "\t\r\n" for x in text):
        raise ValueError("CSV 제어 문자는 허용되지 않습니다.")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, None)
        if not headers or any(not h.strip() for h in headers) or len(headers) != len(set(headers)):
            raise ValueError("CSV 헤더가 비어 있거나 중복되었습니다.")
        rows = []
        for n, values in enumerate(reader, 2):
            if len(values) != len(headers): raise ValueError(f"{name} {n}행 열 수 오류")
            rows.append(dict(zip(headers, values)))
        return rows
    except csv.Error as exc: raise ValueError(f"{name} CSV 형식 오류: {exc}") from exc

def _members(filename, raw):
    if filename.lower().endswith(".csv"): return [(filename, raw)]
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            if len(infos) > MAX_MEMBERS: raise ValueError("ZIP 구성원 수 한도 초과")
            result, total = [], 0
            for info in infos:
                name, mode = importer.clean_archive_name(info.filename), info.external_attr >> 16
                if (info.flag_bits & 1 or name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/")
                    or stat.S_ISLNK(mode)): raise ValueError("안전하지 않은 ZIP 항목")
                # A normal directory is harmless only after its path was validated.
                if info.is_dir(): continue
                if os.path.basename(name) != name or (stat.S_IFMT(mode) and not stat.S_ISREG(mode)):
                    raise ValueError("안전하지 않은 ZIP 항목")
                if name.lower().endswith(".zip"): raise ValueError("중첩 ZIP은 허용되지 않습니다.")
                if info.file_size > MAX_MEMBER_BYTES or (info.compress_size and info.file_size / info.compress_size > MAX_RATIO):
                    raise ValueError("ZIP 크기 또는 압축비 한도 초과")
                total += info.file_size
                if total > MAX_EXPANDED_BYTES: raise ValueError("ZIP 전체 압축 해제 크기 한도 초과")
                if name.lower().endswith(".csv"): result.append((name, z.read(info)))
            return result
    except zipfile.BadZipFile as exc: raise ValueError("손상된 ZIP입니다.") from exc

def preview(conn, files, owner):
    owner = _owner(owner)
    if not files or len(files) > MAX_FILES: raise ValueError("파일은 1~10개만 허용됩니다.")
    total, names, contents, members, unsupported, all_rows = 0, set(), set(), [], [], []
    for file in files:
        name, raw = file.filename or "", file.read()
        if not _safe_name(name) or name in names or len(raw) > MAX_FILE_BYTES: raise ValueError("중복 또는 안전하지 않은 업로드 파일입니다.")
        names.add(name); total += len(raw)
        if total > MAX_TOTAL_BYTES: raise ValueError("전체 업로드 크기 한도 초과")
        for member, content in _members(name, raw):
            source = f"{name}::{member}"
            if any(m["source_file"] == source for m in members): raise ValueError("중복 원본 구성원입니다.")
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash in contents: raise ValueError("동일한 CSV 내용이 중복 업로드되었습니다.")
            contents.add(content_hash)
            physical = _csv_rows(member, content)
            rows, kind, skipped = importer.build_member_metric_rows(source, member, physical, importer.source_period_name(name))
            record = {"source_file": source, "name": member, "sha256": content_hash,
                      "physical_rows": len(physical), "metric_rows": len(rows), "skipped_rows": skipped, "stat_type": kind}
            if not kind: unsupported.append(member)
            else:
                if not rows: raise ValueError(f"{member}: 지원 유형에 유효 지표가 없습니다.")
                if kind == "lodging_search_rank":
                    required = ["rank", "place_name", "mid_category"]
                    missing = [x for x in required if not importer.lodging_rank_value(physical[0], x)]
                else:
                    missing = [x for x in HEADER_CONTRACTS[kind] if x not in physical[0]]
                if missing:
                    raise ValueError(f"{member}: 필수 헤더 누락: {', '.join(missing)}")
                if skipped:
                    raise ValueError(f"{member}: 지표 없는 물리 행 {skipped}개가 있습니다.")
                members.append(record); all_rows.extend(rows)
    hashes = [row[10] for row in all_rows]
    if len(hashes) != len(set(hashes)): raise ValueError("중복 행 해시 원본은 허용되지 않습니다.")
    if not all_rows:
        raise ValueError("지원되는 정규 지표 행이 없는 업로드입니다.")
    manifest = {"members": members, "rows": all_rows, "unsupported_members": unsupported}
    digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()
    cur = conn.cursor()
    try:
        token = secrets.token_urlsafe(32)
        cur.execute("""INSERT INTO tourism_datalab_stages (token,admin_user_id,manifest,manifest_hash,expires_at,state)
          VALUES (%s,%s,%s::jsonb,%s,NOW() + interval '10 minutes','previewed') RETURNING token""",
          (token, owner, json.dumps(manifest, ensure_ascii=False), digest))
        token = cur.fetchone()["token"]
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: cur.close()
    counts = {}
    for m in members: counts[m["stat_type"]] = counts.get(m["stat_type"], 0) + m["metric_rows"]
    return {"token": str(token), "expires_in_seconds": 600, "supported_rows": len(all_rows), "types": counts,
            "unsupported_members": unsupported, "files": members, "manifest_hash": digest}

def apply(conn, token, owner):
    owner = _owner(owner)
    cur = conn.cursor()
    try:
        # UPDATE claim is global/atomic; expired/other-owner/applied rows cannot be claimed.
        cur.execute("""UPDATE tourism_datalab_stages SET state='applying', attempt_count=attempt_count+1
          WHERE token=%s AND admin_user_id=%s AND state IN ('previewed','failed') AND expires_at > NOW()
          RETURNING manifest, manifest_hash""", (token, owner))
        stage = cur.fetchone()
        if not stage: raise ValueError("미리보기 토큰이 없거나 이미 적용·만료되었습니다.")
        manifest = stage["manifest"]
        actual_hash = hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        if not hmac.compare_digest(str(stage["manifest_hash"]), actual_hash):
            raise ValueError("미리보기 무결성 검증에 실패했습니다.")
        rows = manifest["rows"]; sources = sorted({x[7] for x in rows})
        for source in sources:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (source_lock_key(source),))
        cur.execute("DELETE FROM tourism_stats WHERE source_file = ANY(%s)", (sources,))
        execute_values(cur, """INSERT INTO tourism_stats (stat_type,sido_name,sgg_name,ref_yearmonth,metric_name,metric_value,unit,source_file,source_period,dimensions,row_hash)
          VALUES %s ON CONFLICT (row_hash) DO UPDATE SET metric_value=EXCLUDED.metric_value,dimensions=EXCLUDED.dimensions""", rows, page_size=1000)
        importer.match_lodging_rank_to_buildings(cur, sources); importer.refresh_coords(cur); importer.refresh_dong_coords(cur)
        cur.execute("UPDATE tourism_datalab_stages SET state='applied', applied_at=NOW(), error_message=NULL WHERE token=%s", (token,))
        conn.commit(); return {"applied_rows": len(rows), "source_files": len(sources)}
    except Exception as exc:
        conn.rollback()
        # Separate tiny transaction records failure and makes retry possible; it cannot mark an applied claim.
        cur.execute("""UPDATE tourism_datalab_stages SET state='failed', error_message=%s
                       WHERE token=%s AND admin_user_id=%s AND state IN ('previewed','failed')""", (str(exc)[:500], token, owner))
        conn.commit()
        raise
    finally: cur.close()