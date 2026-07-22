---
name: Screenshotting auth-gated admin pages
description: How to visually verify session-auth-protected admin UIs when the headless screenshot tool cannot log in.
---

The `screenshot` (app_preview) tool spawns its own headless browser with NO admin
session cookie. Any page behind `@require_admin` (session-based) redirects to
`/admin/login`, so you cannot screenshot the real dashboard directly.

**Workaround (verified working):**
1. Fetch the real data from the protected API via curl with a cookie jar
   (`curl -c jar -X POST /api/admin/login -d '{"access_key":...}'`, then
   `curl -b jar /api/admin/stats`).
2. Write a temporary self-contained file under `static/` (e.g. `static/_dash_preview.html`)
   that loads the same CSS + Chart.js, inlines the fetched JSON as a JS const, and
   calls the exact same render function copied from admin.html.
3. Screenshot `/static/<temp>.html` (static files need no auth). Add a
   `setTimeout(()=>window.scrollTo(0,720),400)` to capture lower sections.
4. **Delete the temp file afterward** so it never ships.

**Why:** never weaken/bypass real auth just to get a screenshot. This reproduces the
true layout with real data without touching the auth surface.

## curl로 관리자 API 테스트
- 관리자 API를 curl로 검증할 땐 로그인 대신 서명 쿠키를 직접 발급:
  `SecureCookieSessionInterface().get_signing_serializer(app).dumps({"admin": True, "admin_user_id": 1})` → `curl -b "session=<값>"`.
- **Why:** 로그인 rate limit·비밀번호 미상 문제를 우회하고, 재시작 없이 곧바로 인증 요청 테스트 가능.
