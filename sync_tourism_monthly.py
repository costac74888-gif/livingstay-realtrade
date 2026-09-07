#!/usr/bin/env python3
"""Fetch and atomically import the approved monthly Data Lab visitor ledger."""
import hashlib
import json
import os
import urllib.parse
import urllib.request

from db import get_conn
import storage_util
import tourism_datalab_admin as admin

MANIFEST_ENV = "TOURISM_DATALAB_MONTHLY_MANIFEST_URL"
STATUS_KEY = "tourism_monthly_sync_status"
MAX_MANIFEST_BYTES = 64 * 1024
OBJECT_MANIFEST_KEY = "tourism/monthly/manifest.json"
OBJECT_ARCHIVE_PREFIX = "tourism/monthly/archives/"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _https_url(value, label):
    parsed = urllib.parse.urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label}은 인증정보가 없는 HTTPS URL이어야 합니다.")
    return parsed


def _download(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "LivingStay-Tourism-Sync/1.0"})
    # The configured manifest URL is the approval boundary. Following redirects
    # would let that origin silently delegate trust to an unapproved host.
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > limit:
            raise ValueError("승인 원본 다운로드 크기 한도를 초과했습니다.")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("승인 원본 다운로드 크기 한도를 초과했습니다.")
    return data


def _parse_manifest(raw_manifest):
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("승인 manifest가 올바른 UTF-8 JSON이 아닙니다.") from exc
    filename = str(manifest.get("filename") or "").strip()
    expected_hash = str(manifest.get("sha256") or "").strip().lower()
    if not admin._safe_name(filename):
        raise ValueError("승인 manifest의 파일명이 안전하지 않습니다.")
    if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        raise ValueError("승인 manifest의 SHA-256이 올바르지 않습니다.")
    return manifest, filename, expected_hash


def fetch_approved_source(manifest_url=None):
    if manifest_url:
        manifest_origin = _https_url(manifest_url, "승인 manifest URL")
        raw_manifest = _download(manifest_url, MAX_MANIFEST_BYTES)
        manifest, filename, expected_hash = _parse_manifest(raw_manifest)
        source_url = str(manifest.get("url") or "").strip()
        source = _https_url(source_url, "승인 원본 URL")
        if (source.scheme, source.netloc) != (manifest_origin.scheme, manifest_origin.netloc):
            raise ValueError("승인 원본 URL은 manifest와 같은 HTTPS origin이어야 합니다.")
        raw = _download(source_url, admin.MAX_FILE_BYTES)
    else:
        raw_manifest = storage_util.download_bytes(OBJECT_MANIFEST_KEY)
        if len(raw_manifest) > MAX_MANIFEST_BYTES:
            raise ValueError("승인 manifest 크기 한도를 초과했습니다.")
        manifest, filename, expected_hash = _parse_manifest(raw_manifest)
        object_key = str(manifest.get("object_key") or "").strip()
        expected_key = f"{OBJECT_ARCHIVE_PREFIX}{expected_hash}.zip"
        if object_key != expected_key:
            raise ValueError("승인 원본 object key가 content-addressed 경로와 일치하지 않습니다.")
        raw = storage_util.download_bytes(object_key)
        if len(raw) > admin.MAX_FILE_BYTES:
            raise ValueError("승인 원본 다운로드 크기 한도를 초과했습니다.")
    if not hashlib.sha256(raw).hexdigest() == expected_hash:
        raise ValueError("승인 원본 SHA-256이 manifest와 일치하지 않습니다.")
    return filename, raw, expected_hash


def _write_status(state, **details):
    conn = get_conn()
    cur = conn.cursor()
    try:
        payload = {"state": state, **details}
        cur.execute("""INSERT INTO app_meta (key,value,updated_at) VALUES (%s,%s,NOW())
          ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",
          (STATUS_KEY, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def run():
    manifest_url = os.environ.get(MANIFEST_ENV, "").strip()
    filename, raw, source_hash = fetch_approved_source(manifest_url or None)
    manifest = admin.validated_monthly_visitor_manifest(filename, raw)
    conn = get_conn()
    try:
        result = admin.apply_validated_monthly_manifest(conn, manifest)
    finally:
        conn.close()
    _write_status("done", source_file=result["source_file"],
                  source_sha256=source_hash, applied_rows=result["applied_rows"])
    print(f"월간 관광 원본 반영 완료: {result['source_file']} ({result['applied_rows']:,}행)")
    return result


def main():
    try:
        run()
    except Exception as exc:
        try:
            _write_status("failed", error=str(exc)[:500])
        finally:
            print(f"월간 관광 원본 수집 실패: {exc}")
        raise


if __name__ == "__main__":
    main()