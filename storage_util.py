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
AGENT_DOC_TYPES = {"license", "office_reg", "biz_reg", "photo"}
OPERATOR_DOC_TYPES = {"biz_reg", "business_card", "biz_license", "logo"}

# 로고는 화면에 <img>로 노출되므로 이미지 확장자만 허용한다 (PDF 불가).
LOGO_EXTENSIONS = {"jpg", "jpeg", "png"}

# 신청서 제출 시 넘어오는 참조 키가 우리가 발급한 형식인지 검증하는 정규식.
DOC_REF_RE = re.compile(
    r"^applications/(agent|operator|loan_consultant)/[0-9a-f]{32}/"
    r"(license|office_reg|biz_reg|business_card|biz_license|logo|photo|intro_img)\.(pdf|jpg|jpeg|png)$"
)

# 소개글 이미지 공개 서빙용 검증
INTRO_IMG_REF_RE = re.compile(
    r"^applications/(operator|agent|loan_consultant)/[0-9a-f]{32}/intro_img\.(jpg|jpeg|png)$"
)


def is_valid_intro_img_ref(ref):
    return bool(ref) and bool(INTRO_IMG_REF_RE.match(ref))


# ---- 직거래 매물 사진 (등록자 업로드, 공개 서빙) ----
LISTING_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png"}
LISTING_PHOTO_REF_RE = re.compile(r"^listing_photos/\d+/[0-9a-f]{32}\.(jpg|jpeg|png)$")


def build_listing_photo_key(listing_request_id, ext):
    """직거래 매물 사진 저장 키 생성."""
    return f"listing_photos/{listing_request_id}/{uuid.uuid4().hex}.{ext}"


def is_valid_listing_photo_ref(ref):
    return bool(ref) and bool(LISTING_PHOTO_REF_RE.match(ref))


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


# ---- 사이트 팝업 이미지 (관리자 업로드, 공개 서빙) ----
# 서류(applications/…)와 달리 사이트 방문자 모두에게 보여야 하므로
# 앱의 공개 프록시 라우트(/api/popups/image/<key>)로 서빙한다.
POPUP_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
POPUP_REF_RE = re.compile(r"^popups/[0-9a-f]{32}\.(jpg|jpeg|png)$")


def build_popup_key(ext):
    return f"popups/{uuid.uuid4().hex}.{ext}"


def is_valid_popup_ref(ref):
    return bool(ref) and bool(POPUP_REF_RE.match(ref))


# ---- 이메일 광고배너 이미지 (공개 서빙, 이메일 img src 직접 사용) ----
EMAIL_BANNER_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
EMAIL_BANNER_REF_RE = re.compile(r"^email_banners/[0-9a-f]{32}\.(jpg|jpeg|png)$")


def build_email_banner_key(ext):
    return f"email_banners/{uuid.uuid4().hex}.{ext}"


def is_valid_email_banner_ref(ref):
    return bool(ref) and bool(EMAIL_BANNER_REF_RE.match(ref))


# ---- 공지사항 첨부파일 (관리자 업로드, 공개 서빙) ----
NOTICE_ATTACHMENT_EXTENSIONS = {"pdf"}
NOTICE_ATTACHMENT_REF_RE = re.compile(r"^notices/[0-9a-f]{32}\.pdf$")


def build_notice_attachment_key(ext):
    return f"notices/{uuid.uuid4().hex}.{ext}"


def is_valid_notice_attachment_ref(ref):
    return bool(ref) and bool(NOTICE_ATTACHMENT_REF_RE.match(ref))


# ---- 오류신고 스크린샷 (비공개, 관리자 서명 URL로만 열람) ----
BUG_SCREENSHOT_EXTENSIONS = {"jpg", "jpeg", "png"}
BUG_SCREENSHOT_REF_RE = re.compile(r"^bug_reports/[0-9a-f]{32}\.(jpg|jpeg|png)$")


def build_bug_screenshot_key(ext):
    return f"bug_reports/{uuid.uuid4().hex}.{ext}"


def is_valid_bug_screenshot_ref(ref):
    return bool(ref) and bool(BUG_SCREENSHOT_REF_RE.match(ref))


# ---- 채팅 첨부파일 (참여자만 열람, 비공개) ----
CHAT_ATTACHMENT_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
CHAT_ATTACHMENT_REF_RE = re.compile(r"^chat_attachments/[0-9a-f]{32}\.(jpg|jpeg|png|pdf)$")


def build_chat_attachment_key(ext):
    return f"chat_attachments/{uuid.uuid4().hex}.{ext}"


def is_valid_chat_attachment_ref(ref):
    return bool(ref) and bool(CHAT_ATTACHMENT_REF_RE.match(ref))


def download_bytes(key):
    """Object Storage에서 객체 바이트를 내려받는다(팝업 이미지 공개 프록시용)."""
    return get_client().download_as_bytes(key)


_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def upload_doc(key, data):
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    # Replit Client.upload_from_bytes()는 content_type 인자를 노출하지 않으므로
    # 내부 GCS Blob(_Client__object)의 upload_from_string()을 직접 호출해 지정한다.
    client = get_client()
    client._Client__object(key).upload_from_string(data, content_type=content_type)


def delete_object(key):
    """Object Storage 객체 삭제. DB 레코드 삭제 뒤의 정리 작업에만 사용한다."""
    get_client()._Client__object(key).delete()


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
