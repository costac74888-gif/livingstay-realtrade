#!/usr/bin/env python3
"""배포용 프론트 릴리스·경로 노출·원자적 실패 회귀 검사."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
MARKER = STATIC / "generated" / ".frontend-build.json"
FORBIDDEN_VISIBLE_TERMS = (
    "전국공인중개사사무소",
    "브로커 표준데이터",
    "건축HUB",
    "행안부",
    "국토교통부 실거래",
    "국토부 실거래",
)
REMOVED_PATHS = (
    "/api/map/poi",
    "/api/stats/lodging-full-table",
    "/api/admin/buildings/999999999/brokers",
    "/api/admin/buildings/999999999/stores",
)
EXECUTABLE_INLINE_RE = re.compile(
    r"<script(?![^>]*\bsrc\s*=)(?![^>]*\btype\s*=\s*[\"']application/(?:ld\+json|json))"
    r"[^>]*>\s*\S",
    re.I | re.S,
)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def current_release() -> tuple[str, Path]:
    marker = json.loads(MARKER.read_text(encoding="utf-8"))
    release_id = str(marker.get("release") or "")
    release_dir = STATIC / "dist" / release_id
    if not re.fullmatch(r"[0-9a-f]{16}", release_id) or not release_dir.is_dir():
        fail("현재 릴리스 마커 또는 디렉터리가 유효하지 않음")
    return release_id, release_dir


def check_failed_build_keeps_release() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_frontend_for_test", ROOT / "scripts" / "build_frontend.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    before = MARKER.read_bytes()
    original_minify = module.minify

    def planned_failure(_source, _target):
        raise RuntimeError("planned build failure")

    module.minify = planned_failure
    try:
        try:
            module.main()
        except RuntimeError as exc:
            if str(exc) != "planned build failure":
                raise
        else:
            fail("계획된 빌드 실패가 성공으로 처리됨")
    finally:
        module.minify = original_minify
    if MARKER.read_bytes() != before:
        fail("실패한 빌드가 현재 릴리스 마커를 변경함")
    _release_id, release_dir = current_release()
    if not release_dir.is_dir():
        fail("실패한 빌드가 기존 릴리스를 삭제함")


def main() -> None:
    subprocess.run(["npm", "run", "build:frontend"], cwd=ROOT, check=True)
    release_id, release_dir = current_release()
    minified = sorted((release_dir / "js").glob("*.min.js"))
    html_files = sorted((release_dir / "html").glob("*.html"))
    source_html = sorted(STATIC.glob("*.html"))
    if not minified:
        fail("압축 JS가 생성되지 않음")
    if len(html_files) != len(source_html):
        fail(f"HTML 릴리스 누락: 원본 {len(source_html)}개, 생성 {len(html_files)}개")

    for path in minified:
        text = path.read_text(encoding="utf-8")
        if "sourceMappingURL" in text or "\n//#" in text:
            fail(f"소스맵 지시문 포함: {path.name}")
        if path.stat().st_size == 0:
            fail(f"빈 압축 파일: {path.name}")

    for path in html_files:
        text = path.read_text(encoding="utf-8")
        if "/static/js/" in text:
            fail(f"원본 JS 참조 잔존: {path.name}")
        if EXECUTABLE_INLINE_RE.search(text):
            fail(f"실행 가능한 인라인 JS 잔존: {path.name}")
        for term in FORBIDDEN_VISIBLE_TERMS:
            if term in text:
                fail(f"배포 HTML에 금지 문구 잔존: {path.name} / {term}")

    check_failed_build_keeps_release()

    os.environ["SERVE_MINIFIED_ASSETS"] = "1"
    sys.path.insert(0, str(ROOT))
    from app import app  # noqa: E402

    client = app.test_client()
    home = client.get("/")
    html = home.get_data(as_text=True)
    main_asset = f"/static/dist/{release_id}/js/main.min.js"
    if home.status_code != 200 or main_asset not in html:
        fail("배포 모드 홈페이지가 현재 main.min.js 릴리스를 참조하지 않음")
    admin_html = (release_dir / "html" / "admin.html").read_text(encoding="utf-8")
    if f"/static/dist/{release_id}/js/inline-admin-" not in admin_html:
        fail("관리자 인라인 JS가 압축 릴리스 파일로 추출되지 않음")

    if client.get("/static/js/main.js").status_code != 404:
        fail("배포 모드에서 원본 main.js가 404가 아님")
    if client.get("/static/admin.html").status_code != 404:
        fail("배포 모드에서 raw admin.html이 404가 아님")
    if client.get(main_asset).status_code != 200:
        fail("배포 모드에서 현재 main.min.js를 읽을 수 없음")
    for path in REMOVED_PATHS:
        if client.get(path).status_code != 404:
            fail(f"기존 경로가 404가 아님: {path}")

    print(
        f"OK  원자적 릴리스 {release_id} · 압축 JS {len(minified)}개 · "
        f"HTML {len(html_files)}개 인라인 추출 · 원본/구 경로 차단"
    )


if __name__ == "__main__":
    main()