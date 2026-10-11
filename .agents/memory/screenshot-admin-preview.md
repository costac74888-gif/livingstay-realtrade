---
name: Screenshotting auth-gated admin pages
description: Preserve administrator authorization while checking signed-in UI; separate isolated screenshots from operating-account verification.
---

The app-preview screenshot browser has no authenticated session. A login page
capture does not verify the signed-in administrator UI.

Do not publish protected API data in temporary public HTML or manufacture real
administrator cookies to get a screenshot. Those old workarounds are not allowed.

**Why:** authentication and protected-data boundaries must remain in place.
An isolated synthetic login also does not prove that operating accounts are connected.

**How to apply:** use normal password login in a credential-free, owned temporary
database/browser fixture for synthetic visual checks. Label that evidence as
isolated. For real signed-in routes without an authorized testing session, use
allowed tests/API checks and explicitly report that signed-in UI was not verified.

Prefer a viewport screenshot for long administrator audit/history pages.

**Why:** full-page screenshots can be extremely tall despite a correct viewport;
that makes reports unreadable and can exceed image encoder limits.

**How to apply:** keep original generated evidence ignored, label any report crop
explicitly, and do not disable image safety limits just to make conversion succeed.
