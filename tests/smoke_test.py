# -*- coding: utf-8 -*-
"""
smoke_test.py — 홈페이지가 빈/무스타일 화면으로 뜨는 것을 배포 전에 잡아내는 스모크 체크.

홈페이지는 이제 두 정적 파일에 의존한다:
  - /static/css/main.css  (스타일)
  - /static/js/main.js    (데이터 + 상호작용)
둘 중 하나라도 로드에 실패하면(경로 이동/정적 서빙 변경 등) 화면이 통째로 깨진다.
이 체크는 Flask 테스트 클라이언트로 세 경로가 각각 HTTP 200 + 기대 content-type을
돌려주는지 검증한다. 하나라도 어긋나면 즉시 실패(exit 1)한다.

실행: python tests/smoke_test.py
"""

import os
import sys

# app.py를 import할 수 있도록 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app  # noqa: E402

# (경로, 기대하는 content-type 부분문자열)
CHECKS = [
    ("/", "text/html"),
    ("/static/css/main.css", "text/css"),
    ("/static/js/main.js", "javascript"),
]


def run():
    failures = []
    client = app.test_client()
    for path, expected_ct in CHECKS:
        resp = client.get(path)
        content_type = resp.headers.get("Content-Type", "")

        if resp.status_code != 200:
            failures.append(f"{path}: HTTP {resp.status_code} (기대: 200)")
            continue
        if expected_ct not in content_type:
            failures.append(
                f"{path}: content-type '{content_type}' 에 '{expected_ct}' 없음"
            )
            continue
        if not resp.get_data():
            failures.append(f"{path}: 본문이 비어 있음")
            continue

        print(f"OK  {path}  ({resp.status_code}, {content_type})")

    if failures:
        print("\n스모크 체크 실패:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\n모든 스모크 체크 통과 (/, main.css, main.js)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
