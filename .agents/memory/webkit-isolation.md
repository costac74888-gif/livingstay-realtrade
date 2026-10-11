---
name: 격리 WebKit 검사 경계
description: Nix 그래픽 런타임 보존과 Safari 엔진 자동화 증거의 한계
---

격리 브라우저 환경에서 서비스 자격증명과 그래픽 런타임 설정을 구분한다.
Nix WPE WebKit은 EGL 공급자 라이브러리 설정이 빠지면 실행은 되지만
페이지 생성이 멈출 수 있다. 네트워크·DB 권한을 넓혀서 해결하지 않는다.

**Why:** 일반 환경에서 성공했던 페이지 생성이 자격증명을 제거한 환경에서
멈췄으며, 그래픽 라이브러리 경로만 보존했을 때 정상 작동했다.

**How to apply:** 필요한 비민감 런타임 경로만 개별 허용하고, Chromium과
WebKit 각각 외부 요청 탐지 서버의 수신 0건을 확인한다.

WebKit의 네이티브 탭 증거와 DOM으로 재현한 길게 누르기·취소 증거를
구별한다. Safari 엔진 통과를 물리 iPhone 검증으로 표현하지 않는다.
Safari는 TouchEvent 생성자를 지원하지 않을 수 있으며, capture listener의
microtask는 이후 버튼 listener보다 먼저 실행될 수 있다.

**Why:** 자동화 API는 탭만 제공하고, 클릭 전용 버튼은 pointerup 뒤의
click handler에서 값이 바뀐다. 해제 기준선의 기록 순서가 틀리면 정상
증가를 해제 후 반복으로 오판한다.

**How to apply:** 반복 버튼은 해제 capture 시점, 클릭 전용 버튼은
handler 이후 bubbling 시점을 기준선으로 삼는다. 증거에 입력 방식과
isTrusted를 남기며 실제 장치 제스처가 필요한 검증은 별도로 수행한다.
