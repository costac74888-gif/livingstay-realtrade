---
name: static HTML served through Flask routes (not raw static)
description: how index/admin/etc HTML is served with server-side injection; where cache-busting for JS/CSS assets lives
---

The user-facing HTML pages are NOT served as raw `/static/*.html`. They go through Flask route handlers that read the file and do server-side string injection before responding:
- `_serve_app_shell()` → `/` and `/building/<id>` (index.html; injects Kakao JS key + SDK version)
- `_serve_static_html(filename)` → notices/mypage/transactions/terms/privacy/admin_login/admin
- `apply_agent_page()` / `apply_operator_page()` → apply forms

**Cache-busting for JS/CSS:** `SERVER_BOOT_V = str(int(time.time()))` is set once at process boot (each deploy restarts the app → value changes per deploy). `_inject_asset_version(html)` uses regex `(src|href)="(/static/(?:js|css)/[^"?]+\.(?:js|css))"` to append `?v=SERVER_BOOT_V` at serve time, so HTML files stay clean (no hardcoded version) and every deploy forces browsers to refetch JS/CSS. Same `SERVER_BOOT_V` also versions the Kakao SDK URL.

**Why serve-time injection (not editing each HTML):** avoids touching ~9 HTML files and prevents drift when new pages are added — but new page routes MUST route through one of the serving helpers, or their assets won't get versioned. Raw `/static/index.html` direct access bypasses all injection (not the official entry path).

**How to apply:** when adding a new HTML page, serve it via `_serve_static_html` (or an equivalent that calls `_inject_asset_version`), never link it as `/static/foo.html`. Trade-off accepted: boot-time (not per-file-hash) versioning re-downloads even unchanged assets each deploy — intended, since the goal is "force fresh on every deploy".
