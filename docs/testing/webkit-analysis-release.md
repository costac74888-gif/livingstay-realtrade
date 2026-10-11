# 분석 버튼 WebKit 해제 검사

실행: `npm run test:analysis-webkit`

이 명령은 기존 격리 실행기로 임시 DB·HTTP 서버와 모의 API를 준비한다.
직접 Node 실행은 owned origin과 필수 전송 가드가 없으면 실패한다.
실제 서비스 DB와 발송 공급자는 사용하지 않는다.

## 실행 환경

Nix WPE WebKit 2158 / Safari 엔진 18.4와 정확히 고정한
playwright-webkit-compat 1.51.1을 사용한다. 주 Chromium 도구는 교체하지
않는다. tests/offline_support/webkit_runtime.cjs의 Nix 빌드가 필요하며
없는 환경에서 Chromium으로 대체하지 않는다. 격리 환경은 EGL 공급자
라이브러리 경로만 추가로 보존하며 서비스 자격증명은 보존하지 않는다.

## 검사 및 증거

실제 /analysis 화면의 운영 OCC, 임대 월세, 투자 매수가를 검사한다.

- 네이티브 탭: 정확히 한 단계 이동하고 해제 뒤 더 이동하지 않음.
- 짧은 누름과 detail=0 호환 클릭: 중복 증가 없음.
- 길게 누름: 원래 400ms 지연·120ms 반복과 최소 3단계 이동 확인.
- 버튼 밖 pointerup/touchend, 취소, pointerleave/lostpointercapture,
  blur/pagehide/visibilitychange 뒤 즉시값·720ms 뒤 값이 기준선과 정확히 같음.
- 투자 버튼은 기존 클릭 전용 동작 유지. 기준선은 클릭 handler 뒤 기록.
- 이후 Enter/Space와 소수·눈금 사이 직접입력 보존.
- 예상하지 않은 모의 API 쓰기와 pageerror가 없어야 함.

기존 Chromium 운영·임대 assertion과 Harness 원본 기준선은 유지한다.
tests/test_owned_offline_runtime.py는 Chromium과 WebKit 각각 프록시가
route.continue·redirect·APIRequestContext의 외부 접근을 막는지 확인하며
외부 탐지 서버 수신 0건을 요구한다.

기본 증거 위치:
.local/suite-audit/after/artifacts/analysis_webkit_release_browser_test.js/

세 모드 PNG, 이벤트별 JSON, Playwright trace ZIP을 저장하며 Git·배포에서
제외한다. JSON은 버전, 입력 방식, isTrusted, 해제 기준값과 이후 값을 명시한다.

## 검증 한계

390×844 모바일 viewport와 iPhone UA, deviceScaleFactor=1인 Safari 엔진
검사이지 물리 iPhone 인증이 아니다. WebKit 자동화 API는 네이티브 탭만
제공한다. 길게 누름·버튼 밖 해제·취소·화면 이탈은 WebKit 안에서 DOM
이벤트로 재현하며 visibilitychange는 hidden을 일시 설정한다.
실제 iOS의 스크롤 취소·앱 전환 제스처는 별도 장치 검증이 필요하다.
