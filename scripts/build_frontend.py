#!/usr/bin/env python3
"""모든 정적 HTML/JS에서 원자적으로 교체 가능한 배포 릴리스를 생성한다."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
JS_SOURCE = STATIC / "js"
DIST = STATIC / "dist"
GENERATED = STATIC / "generated"
MARKER = GENERATED / ".frontend-build.json"
TERSER = ROOT / "node_modules" / ".bin" / "terser"
RELEASE_TOKEN = "__FRONTEND_RELEASE__"
SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.I | re.S)
SOURCE_JS_RE = re.compile(r"/static/js/(?P<name>[A-Za-z0-9_.-]+)\.js(?P<query>\?[^\"']*)?")


def minify(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(TERSER),
            str(source),
            "--compress",
            "passes=2",
            "--mangle",
            "--format",
            "comments=false,ascii_only=true",
            "--output",
            str(target),
        ],
        cwd=ROOT,
        check=True,
    )


def build_external_scripts(stage: Path) -> list[Path]:
    outputs = []
    for source in sorted(JS_SOURCE.glob("*.js")):
        if source.name.endswith(".min.js") or source.name.startswith("__inline_"):
            continue
        target = stage / "js" / f"{source.stem}.min.js"
        minify(source, target)
        outputs.append(target)
    return outputs


def build_html(stage: Path, source_html: Path) -> list[Path]:
    html = source_html.read_text(encoding="utf-8")
    outputs = []
    counter = 0

    def extract_inline(match: re.Match[str]) -> str:
        nonlocal counter
        attrs = match.group("attrs")
        body = match.group("body")
        if re.search(r"\bsrc\s*=", attrs, re.I) or not body.strip():
            return match.group(0)
        if re.search(r'\btype\s*=\s*["\']application/(?:ld\+json|json)["\']', attrs, re.I):
            return match.group(0)
        counter += 1
        stem = source_html.stem.replace("-", "_")
        target = stage / "js" / f"inline-{stem}-{counter}.min.js"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", encoding="utf-8", dir=ROOT, delete=False
        ) as temp:
            temp.write(body)
            temp_path = Path(temp.name)
        try:
            minify(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)
        outputs.append(target)
        safe_attrs = re.sub(r"\s+", " ", attrs).strip()
        attrs_text = f" {safe_attrs}" if safe_attrs else ""
        return (
            f'<script{attrs_text} src="/static/dist/{RELEASE_TOKEN}/js/{target.name}">'
            "</script>"
        )

    html = SCRIPT_RE.sub(extract_inline, html)
    html = SOURCE_JS_RE.sub(
        lambda match: (
            f"/static/dist/{RELEASE_TOKEN}/js/{match.group('name')}.min.js"
            f"{match.group('query') or ''}"
        ),
        html,
    )
    target_html = stage / "html" / source_html.name
    target_html.parent.mkdir(parents=True, exist_ok=True)
    target_html.write_text(html, encoding="utf-8")
    outputs.append(target_html)
    return outputs


def release_digest(outputs: list[Path], stage: Path) -> str:
    digest = hashlib.sha256()
    for output in sorted(outputs):
        digest.update(str(output.relative_to(stage)).encode("utf-8"))
        digest.update(output.read_bytes())
    return digest.hexdigest()[:16]


def promote(stage: Path, outputs: list[Path]) -> tuple[str, Path]:
    release_id = release_digest(outputs, stage)
    for html_path in (stage / "html").glob("*.html"):
        html = html_path.read_text(encoding="utf-8").replace(RELEASE_TOKEN, release_id)
        html_path.write_text(html, encoding="utf-8")

    DIST.mkdir(parents=True, exist_ok=True)
    release_dir = DIST / release_id
    if release_dir.exists():
        shutil.rmtree(stage)
    else:
        os.replace(stage, release_dir)

    GENERATED.mkdir(parents=True, exist_ok=True)
    marker_temp = GENERATED / ".frontend-build.json.tmp"
    marker_temp.write_text(
        json.dumps(
            {
                "version": 2,
                "release": release_id,
                "files": len(outputs),
                "sha256": release_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.replace(marker_temp, MARKER)
    return release_id, release_dir


def cleanup_old_releases(current_release: str) -> None:
    releases = sorted(
        (path for path in DIST.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    retained = {current_release, *(path.name for path in releases[:2])}
    for path in releases:
        if path.name not in retained:
            shutil.rmtree(path, ignore_errors=True)
    for legacy in JS_SOURCE.glob("*.min.js"):
        legacy.unlink(missing_ok=True)
    for legacy in GENERATED.glob("*.html"):
        legacy.unlink(missing_ok=True)


def main() -> None:
    if not TERSER.is_file():
        raise SystemExit("Terser가 없습니다. 먼저 npm ci를 실행하세요.")

    STATIC.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".frontend-stage-", dir=STATIC))
    try:
        outputs = build_external_scripts(stage)
        for source_html in sorted(STATIC.glob("*.html")):
            outputs.extend(build_html(stage, source_html))
        release_id, release_dir = promote(stage, outputs)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    cleanup_old_releases(release_id)
    print(
        f"frontend build complete: release={release_id} "
        f"files={len(outputs)} path={release_dir.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()