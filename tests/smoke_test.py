# -*- coding: utf-8 -*-
"""
smoke_test.py — 홈페이지가 빈/무스타일 화면으로 뜨는 것을 배포 전에 잡아내는 스모크 체크.

홈페이지는 이제 두 정적 파일에 의존한다:
  - /static/css/main.css  (스타일)
  - /static/js/main.js    (데이터 + 상호작용)
둘 중 하나라도 로드에 실패하면(경로 이동/정적 서빙 변경 등) 화면이 통째로 깨진다.
이 체크는 세 경로가 각각 HTTP 200 + 기대 content-type을 돌려주는지 검증한다.
하나라도 어긋나면 즉시 실패(exit 1)한다.

두 가지 모드:
  1) 로컬(기본): Flask 테스트 클라이언트로 앱을 in-process로 검사.
       실행: python tests/smoke_test.py
  2) 라이브: 실제 배포/개발 URL을 HTTP로 직접 호출해 프로덕션 서버·프록시·기동
       명령까지 포함한 실제 렌더 경로를 검증. 로컬 통과해도 라이브가 깨질 수 있으므로
       배포 직후 이 모드로 확인한다.
       라이브 모드는 명시적으로 켜야 한다(로컬 검증이 실수로 라이브를 때리지 않도록):
         - SMOKE_BASE_URL 을 지정하면 그 URL을 대상으로 라이브 모드 진입, 또는
         - SMOKE_LIVE=1 을 지정하면 REPLIT_DEV_DOMAIN 을 대상으로 라이브 모드 진입.
       base URL 해석 순서: SMOKE_BASE_URL → REPLIT_DEV_DOMAIN (https 자동 접두).
       실행 예: SMOKE_BASE_URL=https://your-app.replit.app python tests/smoke_test.py
                SMOKE_LIVE=1 python tests/smoke_test.py

참고: REPLIT_DEV_DOMAIN 은 개발 컨테이너에 항상 존재하므로, 라이브 진입을 반드시
명시 플래그(SMOKE_BASE_URL/SMOKE_LIVE)로 게이트한다. 그래야 기본 `smoke` 검증이
로컬 모드로 유지된다.
"""

import os
import sys

# (경로, 기대하는 content-type 부분문자열)
CHECKS = [
    ("/", "text/html"),
    ("/static/css/main.css", "text/css"),
    ("/static/js/main.js", "javascript"),
]


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _resolve_base_url():
    """라이브 모드 base URL을 해석한다. 라이브가 아니면 None(→로컬 모드).

    라이브는 명시 플래그로만 진입한다:
      - SMOKE_BASE_URL 이 있으면 그것을 사용.
      - 없고 SMOKE_LIVE 가 truthy 면 REPLIT_DEV_DOMAIN 사용.
    """
    base = os.environ.get("SMOKE_BASE_URL", "").strip()
    if not base and _truthy(os.environ.get("SMOKE_LIVE", "")):
        base = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if not base:
        return None
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base.rstrip("/")


def _ca_bundle():
    """라이브 HTTPS 검증에 쓸 CA 번들. 시스템 번들 우선(certifi 는 Replit 프록시
    체인을 못 가질 수 있음). 없으면 requests 기본값(True)."""
    for path in ("/etc/ssl/certs/ca-certificates.crt",):
        if os.path.exists(path):
            return path
    return True


def run_local():
    """Flask 테스트 클라이언트로 in-process 검사."""
    # app.py를 import할 수 있도록 프로젝트 루트를 경로에 추가
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from app import app  # noqa: E402

    print("모드: 로컬 (Flask 테스트 클라이언트)")
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

    return failures


def run_live(base_url):
    """실제 URL을 HTTP로 호출해 라이브 렌더 경로를 검사."""
    import requests  # noqa: E402

    verify = _ca_bundle()
    print(f"모드: 라이브 (HTTP) — base: {base_url}")
    failures = []
    for path, expected_ct in CHECKS:
        url = base_url + path
        try:
            resp = requests.get(url, timeout=15, verify=verify)
        except requests.RequestException as e:
            failures.append(f"{path}: 요청 실패 ({e})")
            continue

        content_type = resp.headers.get("Content-Type", "")

        if resp.status_code != 200:
            failures.append(f"{path}: HTTP {resp.status_code} (기대: 200)")
            continue
        if expected_ct not in content_type:
            failures.append(
                f"{path}: content-type '{content_type}' 에 '{expected_ct}' 없음"
            )
            continue
        if not resp.content:
            failures.append(f"{path}: 본문이 비어 있음")
            continue

        print(f"OK  {path}  ({resp.status_code}, {content_type})")

    return failures


def run():
    base_url = _resolve_base_url()
    if base_url:
        failures = run_live(base_url)
    else:
        failures = run_local()

    if failures:
        print("\n스모크 체크 실패:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\n모든 스모크 체크 통과 (/, main.css, main.js)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
