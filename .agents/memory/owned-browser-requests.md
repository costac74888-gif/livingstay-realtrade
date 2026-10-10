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
