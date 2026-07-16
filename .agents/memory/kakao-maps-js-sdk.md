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
- **Screenshot tool cannot prove map UI — even with the domain registered.** Originally assumed the
  blank capture was just the screenshot host not being in Kakao's domain list. DISPROVEN: after the user
  registered the dev domain (`$REPLIT_DEV_DOMAIN` sdk.js now 200, console logs "[MAP] 마커 N개 표시" =
  SDK loaded + markers placed end-to-end), the headless `screenshot(app_preview)` STILL captured the map
  area as **plain white** across multiple restarts/retries. So the map area rendering blank in the agent
  screenshot is a **headless-capture limitation** (tiles/overlays don't paint in time), NOT proof the map
  is broken. Do NOT keep retrying screenshots to verify map framing/overlays; it wastes turns. Verify
  instead via: sdk.js returns 200 for the dev Referer + the marker-count log firing, then ask the USER
  to confirm framing in their own browser (they see tiles fine). For pure map-framing/visual-tuning tasks
  the user is the only reliable visual verifier here.

## 컨트롤 위치 이동 시 offsetParent 함정
Kakao 컨트롤(ZoomControl 등)의 absolute 래퍼는 offsetParent가 높이 0인 요소일 수 있어
`style.bottom`을 주면 지도 기준이 아니라 그 0높이 요소 기준으로 적용돼 화면 위 밖(y<0)으로 날아간다.
**How to apply:** 위치 조정은 `bottom` 대신 지도 `getBoundingClientRect()` 기준으로 `top`을 직접 계산하고,
적용 후 `getBoundingClientRect()` 실측을 콘솔에 남겨 화면 안인지 확인한다. 스크린샷 도구 환경은
카카오 타일/스프라이트 CDN을 못 불러와 지도가 회백색으로 나오므로 시각 확인 대신 rect 로그로 검증.
