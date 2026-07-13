---
name: Kakao Maps JS SDK on Replit
description: Why the Kakao Maps JS SDK fails to load in the browser even with a valid JS key.
---

- The Kakao Maps JS SDK (`dapi.kakao.com/v2/maps/sdk.js?appkey=...`) validates the request's
  **Referer against the app's registered Web platform domains**. If the domain isn't registered,
  the sdk.js request returns **401 `{"errorType":"AccessDeniedError","message":"domain mismatched!"}`**
  and `window.kakao` is NEVER defined — so any `window.kakao && kakao.maps.load(...)` guard falls to
  the else branch. A blank map + "SDK not loaded" console warning = domain not registered, NOT a bad key.
- **Verification trick:** `curl` of sdk.js WITHOUT a Referer returns 200 (key is fine); adding
  `-H "Referer: https://<domain>/"` reproduces the 401. Use this to prove key-vs-domain issues.
- **Fix (user-only, external):** Kakao Developers → 내 애플리케이션 → 앱 설정 → 플랫폼 → Web →
  사이트 도메인 에 both the Replit dev domain (`$REPLIT_DEV_DOMAIN`, stable per repl) and the prod
  domain (`*.replit.app`) must be added. The agent cannot do this.
- The JS appkey is a **client-exposed** key (visible in the rendered SDK URL). Storing it in Secrets
  only keeps it out of committed source; it is not hidden from the browser. Domain registration is
  the actual access control, not secrecy of the key.
