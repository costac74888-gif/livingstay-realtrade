---
name: header/auth shared architecture
description: How the site-wide header, login modal, and auth state sync work across all pages.
---

# Shared header + auth wiring

The header is rendered from ONE place: `static/js/header.js`. Every page has only a
`<header id="siteHeader"></header>` shell plus a `<script>window.PAGE_TITLE="…"</script>`.
header.js injects the header markup (logo, page-title, 🔔 alert dropdown, #authArea),
injects the login modal `#authModal` (idempotently, only if absent), owns the notif
polling (`window.startNotifPolling/stopNotifPolling`) and the `--header-h` calc.

**Load order rule:** header.js MUST load before auth.js (auth.js is an IIFE that
early-returns if `#authArea`/`#authModal` are missing). On index.html header.js must
also load before main.js (main.js does `getElementById("brandHome")` with NO null check).

**Logo behavior:** index sets `window.HEADER_BRAND_INPLACE=true` → logo is a `<div>` so
main.js `resetToHome` (which does NOT preventDefault) resets in place. All other pages
render the logo as `<a href="/">` (navigate home).

**Auth state = single source of truth in auth.js.** `refreshMe()` fetches
`/api/auth/me` ({logged_in,name,email,provider}) and broadcasts
`window.dispatchEvent(new CustomEvent("livingstay:auth",{detail:{loggedIn,user}}))`.
`window.livingstayRefreshAuth = refreshMe` lets non-header UI force a re-sync.
**Why:** mypage has its OWN body auth UI (`#myBody`); without the event, header
logout/login and the body would desync. mypage now renders its body only from the
`livingstay:auth` event and routes its body logout through `window.livingstayRefreshAuth`.
