---
name: header.js modal ID collisions on static pages
description: Any page loading header.js also gets the login modal's DOM IDs — page-local widgets must namespace their IDs.
---
Rule: header.js injects the login/signup modal (IDs like agreeTerms, agreePrivacy, privacyToggle, privacyDetail, authSubmit) into EVERY page that loads it. Page-local scripts using duplicate IDs get double event bindings (auth.js binds to the first match) — e.g. an accordion toggled twice appears dead.
**Why:** apply_agent/apply_operator consent accordion silently failed until IDs were renamed to applyAgree*/applyPrivacy*.
**How to apply:** when adding interactive elements to any static page, prefix IDs uniquely and check header.js/auth.js for name clashes; test via an iframe harness page + screenshot.
