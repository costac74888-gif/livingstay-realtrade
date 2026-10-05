---
name: 브라우저 검사와 봇 차단 식별값
description: 기본 HeadlessChrome 방문의 204 응답이 Chromium에서는 내비게이션 오류로 보이는 검사 환경 특성
---

일반 방문자 UI 검사는 실제 방문자 형태의 User-Agent를 사용한다. 봇 차단 검사는 명시적으로 봇 UA를 지정한다.

**Why:** 앱이 HeadlessChrome을 204로 거부하면 Playwright의 page.goto는 HTTP 상태를 반환하지 않고 `net::ERR_ABORTED`로 실패할 수 있다. 이를 서버 다운·라우팅 오류로 오인해 제품 봇 차단을 제거하면 안 된다.

**How to apply:** 자동화에서 홈 진입만 실패할 때는 UA와 204 여부를 먼저 확인한다. 모바일 기기 UA 및 의도적인 봇 테스트의 명시값은 덮어쓰지 않는다.
