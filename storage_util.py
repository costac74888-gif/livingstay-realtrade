"""Replit Object Storage 연동 유틸.

신청서(C/D 화면) 서류 업로드 전용.
- 버킷: DEFAULT_OBJECT_STORAGE_BUCKET_ID 환경변수의 기본 버킷 사용.
- 저장 키 형식: applications/{agent|operator}/{uuid32}/{doc_type}.{ext}
  (URL이 아니라 내부 참조 키. 외부에 서명 없이 노출되지 않는다.)
- 관리자 화면에서만 사이드카로 5분짜리 서명 GET URL을 발급해 열람한다.
"""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import requests as _requests
from replit.object_storage import Client

# Replit 사이드카(서명 URL 발급 등 스토리지 보조 API). 컨테이너 내부 전용 주소.
_SIDECAR = "http://127.0.0.1:1106"

# 업로드 허용 확장자와 매직 바이트(파일 시그니처).
# 선언한 확장자와 실제 파일 내용이 일치하는지 검사해 위장 업로드를 막는다.
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
_MAGIC = {
    "pdf": [b"%PDF"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
}

MAX_FILE_BYTES = 5 * 1024 * 1024  # 파일당 5MB

# 신청 유형별 허용 doc_type (applications 테이블의 doc_* 컬럼과 1:1 매핑)
AGENT_DOC_TYPES = {"license", "office_reg", "biz_reg"}
OPERATOR_DOC_TYPES = {"business_card", "biz_license"}

# 신청서 제출 시 넘어오는 참조 키가 우리가 발급한 형식인지 검증하는 정규식.
DOC_REF_RE = re.compile(
    r"^applications/(agent|operator)/[0-9a-f]{32}/"
    r"(license|office_reg|biz_reg|business_card|biz_license)\.(pdf|jpg|jpeg|png)$"
)


def _bucket_id():
    bid = os.environ.get("DEFAULT_OBJECT_STORAGE_BUCKET_ID")
    if not bid:
        raise RuntimeError("DEFAULT_OBJECT_STORAGE_BUCKET_ID가 설정되어 있지 않습니다.")
    return bid


def get_client():
    """매 호출마다 새 클라이언트를 만든다(토큰 만료 대비, 캐시 금지)."""
    return Client(bucket_id=_bucket_id())


def check_magic_bytes(data, ext):
    """파일 앞부분 시그니처가 선언한 확장자와 일치하는지 확인."""
    sigs = _MAGIC.get(ext)
    if not sigs:
        return False
    return any(data[: len(s)] == s for s in sigs)


def build_doc_key(applicant_type, doc_type, ext):
    """업로드 목적을 알 수 있는 저장 키를 생성한다."""
    return f"applications/{applicant_type}/{uuid.uuid4().hex}/{doc_type}.{ext}"


def is_valid_doc_ref(ref, applicant_type=None, allowed_doc_types=None):
    """제출된 참조 키가 우리가 발급한 형식인지 검증한다."""
    if not ref:
        return False
    m = DOC_REF_RE.match(ref)
    if not m:
        return False
    if applicant_type and m.group(1) != applicant_type:
        return False
    if allowed_doc_types and m.group(2) not in allowed_doc_types:
        return False
    return True


def upload_doc(key, data):
    get_client().upload_from_bytes(key, data)


def doc_exists(key):
    try:
        return get_client().exists(key)
    except Exception:
        return False


def signed_get_url(key, ttl_sec=300):
    """관리자 열람용 서명 GET URL(기본 5분) 발급. require_admin 뒤에서만 호출할 것."""
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()
    resp = _requests.post(
        f"{_SIDECAR}/object-storage/signed-object-url",
        json={
            "bucket_name": _bucket_id(),
            "object_name": key,
            "method": "GET",
            "expires_at": expires_at,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["signed_url"]
