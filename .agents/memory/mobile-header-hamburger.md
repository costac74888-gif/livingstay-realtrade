---
name: mobile header hamburger + list toggle
description: how the shared header collapses on mobile (livingstay) — bell always shown, rest behind hamburger, index-only map list toggle
---

Shared header is rendered by `static/js/header.js` into `<header id="siteHeader">` on every page.

**Layout contract (durable):**
- The notification bell `#alertMenu` (dropdown) is a **direct child of `.header-actions`** so it stays visible on mobile. Do NOT put it back inside `.header-nav`, or the ≤520px hamburger collapse would hide it.
- Nav links + `#authArea` live inside `.header-menu`. Desktop: inline flex. ≤520px: hidden dropdown toggled by `#hamburgerBtn` (`.header-menu.open`). Labels (`.hnav-label`) are re-shown inside the dropdown even though the ≤720px rule hides them in the inline bar.
- The map page's "목록" toggle (`#btnTogglePanel`, toggles `.side-panel.open`) is rendered by header.js **only when `window.HEADER_LEFT_TOGGLE` is true** (set in index.html). It sits left of the logo, shown ≤980px. The old floating `.panel-toggle` button + its inline handler were removed from index.html — the single click binding now lives in header.js (avoid re-adding an index-side handler → double toggle).
- `.hnav-panel-notif` becomes `position:fixed; left:12px; right:12px` at ≤520px so it can't slide off-screen (its `.hnav-dropdown` relative ancestor is irrelevant once fixed).

**Verify on changes:** at 360/390px — hamburger open/close, bell open/close, list-toggle present on index only.

**Note:** production separate DB may show 0 map markers regardless of header CSS — see prod-geo-empty.md.
