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
   instead via the registered HTTPS dev origin in a normal browser session, the completed Maps
   initialization, marker count and successfully loaded tile images. A manual Chromium capture
   through that HTTPS origin can render real tiles even when the Screenshot tool's localhost
   capture cannot. Do not ask the user to perform checks the owned browser can complete.

## 컨트롤 위치 이동 시 offsetParent 함정
Kakao 컨트롤(ZoomControl 등)의 absolute 래퍼는 offsetParent가 높이 0인 요소일 수 있어
`style.bottom`을 주면 지도 기준이 아니라 그 0높이 요소 기준으로 적용돼 화면 위 밖(y<0)으로 날아간다.
**How to apply:** 위치 조정은 `bottom` 대신 지도 `getBoundingClientRect()` 기준으로 `top`을 직접 계산하고,
적용 후 `getBoundingClientRect()` 실측을 콘솔에 남겨 화면 안인지 확인한다. 스크린샷 도구 환경은
카카오 타일/스프라이트 CDN을 못 불러와 지도가 회백색으로 나오므로 시각 확인 대신 rect 로그로 검증.

## 캐시된 SDK 초기화 순서

이미 로드된 SDK의 maps.load 콜백은 동기 실행될 수 있으므로 지도 초기화는
현재 스크립트 평가가 끝난 뒤로 미룬다.

**Why:** 동기 콜백이 뒤쪽 let/const 상태 선언보다 먼저 실행되면 초기화 전
접근 오류가 발생한다. 네트워크 로드가 느린 경우에는 이 오류가 숨겨진다.

**How to apply:** 초기화 콜백을 microtask로 예약하고 동기·비동기 SDK 두
경우를 모두 검사한다. 기다리는 시간만 늘려서 해결하지 않는다.

## SDK 응답과 하위 리소스 완료 구분

SDK 진입 스크립트의 HTTP 200은 실제 지도 초기화 완료가 아니다. SDK가 추가로
불러오는 현재 CDN과 프로토콜이 CSP에 허용되어야 하며, 지도 생성과 타일 로드를
별도로 확인한다.

**Why:** 개발 도메인 SDK는 200인데 CSP가 현재 Kakao CDN의 하위 스크립트를
차단해 초기화 콜백이 끝나지 않았다. 또 HTTPS 개발 화면은 정상인 반면 HTTP
localhost 캡처에서는 SDK가 HTTP 리소스를 선택해 HTTPS-only CSP에 막혔다.

**How to apply:** SDK 실패를 키·도메인 문제로 단정하거나 무작정 대기하지
말고 브라우저의 CSP·실패 요청 호스트를 확인한다. 허용 범위는 지도 전용으로
제한하며, HTTPS에서 얻은 실제 지도 증거와 localhost 캡처 실패를 구분한다.
