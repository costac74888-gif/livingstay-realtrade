"""Contact-safe diagnostics, without modifying delivery inputs or stored records."""
import re
from urllib.parse import unquote
from pathlib import Path
from contextlib import contextmanager
import os

_EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[\w-]+", re.UNICODE)
_PHONE = re.compile(
    r"(?<!\d)(?:\+82[\s().-]*(?:0)?|0)"
    r"(?:2[\s().-]*\d{3,4}|(?:1[016789]|[3-6]\d|70|80)[\s().-]*\d{3,4})"
    r"[\s().-]*\d{4}(?!\d)"
)
_INTERNATIONAL_PHONE = re.compile(r"(?<!\w)\+\d{1,3}(?:[\s().-]*\d){7,13}(?!\d)")
_SERVICE_PHONE = re.compile(r"(?<!\d)(?:15|16|18)\d{2}[\s.-]?\d{4}(?!\d)")
PRIVATE_REPORT_DIR = Path(__file__).resolve().parent / ".local" / "private-reports"


def redact_contact_data(value):
    """Mask contacts in free-form errors, including twice URL-encoded values."""
    text = str(value)
    for _ in range(2):
        text = unquote(text)
    text = _EMAIL.sub("[이메일 숨김]", text)
    for pattern in (_PHONE, _INTERNATIONAL_PHONE, _SERVICE_PHONE):
        text = pattern.sub("[연락처 숨김]", text)
    return text


def diagnostic_sample(value):
    """Retain sample structure but never emit a contact field's original value."""
    if isinstance(value, dict):
        return {
            key: "[연락처 숨김]" if any(token in str(key).lower()
                for token in ("email", "phone", "tel", "contact"))
            else diagnostic_sample(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [diagnostic_sample(item) for item in value]
    return redact_contact_data(value) if isinstance(value, str) else value


@contextmanager
def private_contact_report(filename):
    """Explicit CLI-only export; private folder, exclusive file, no symlink overwrite."""
    base = PRIVATE_REPORT_DIR
    if base.is_symlink() or base.parent.is_symlink():
        raise ValueError("비공개 보고서 폴더의 심볼릭 링크는 허용하지 않습니다.")
    target = Path(filename)
    if target.name != str(target) or target.name in {"", ".", ".."}:
        raise ValueError("보고서는 경로 없이 파일명만 지정해주세요.")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    fd = os.open(base / target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        yield output
