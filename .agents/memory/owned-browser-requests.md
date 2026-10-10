---
name: 격리 브라우저의 HTTP 요청
description: 격리검사의 Node 통신 차단과 브라우저 내부 요청의 차이.
---

격리 브라우저 검사의 준비·조회 요청도 고정된 owned origin의 브라우저
내부 fetch로 수행한다. Playwright의 APIRequestContext가 같은 loopback
주소를 사용해도 허용된 브라우저 통신으로 취급되지 않는다.

**Why:** Node 프로세스의 HTTP 통신은 브라우저 요청 차단과 다른 경로라서
격리 가드가 전체 차단한다. 같은 주소의 준비 요청에서 환경 오류처럼
보이는 통신 차단이 발생했다.

**How to apply:** 실제 APIRequestContext 통신이 필요하면 권한을 넓히기
전에 별도 격리 설계를 검토한다. 일반 UI 검사는 브라우저 내부 요청과
동일 출처의 서명된 검사 세션을 사용하며 가드를 비활성화하지 않는다.

전체 legacy 브라우저 검사에도 브라우저 route 가드만으로는 충분하지 않다.
Node fetch·HTTP와 Playwright APIRequestContext는 별도의 전송 경로이며,
각 경로를 명시적으로 고정 owned origin에 제한해야 한다.

**Why:** 일부 기존 검사는 기본 주소로 기존 앱의 5000번 포트를 사용했다.
페이지 이동을 차단해도 준비용 API 요청까지 차단했다는 보장은 없다.

**How to apply:** 검사 기본 URL을 owned 서버로 명시하고, URL 문자열뿐
아니라 Request 객체 및 API context의 baseURL도 검증한다. 기존 앱으로
폴백하지 않는다. Node API가 필요한 legacy 검사는 별도 검토된 가드를
사용하며 기존 HS2 private-browser 가드의 권한은 넓히지 않는다.
