---
name: 전역 rate limit & 봇 트래픽 관측
description: flask-limiter 전역 기본 제한 구조, 제외 경로, 봇 트래픽 조사 시 데이터 소스
---

- 전역 default_limits(IP당 200/min)가 걸려 있고 `/static/*`, `/api/health`는 `@limiter.request_filter`로 제외됨. 개별 `@limiter.limit` 데코레이터는 전역과 **별개 카운터**로 함께 적용된다.
- **Why:** 뭄바이발 봇 트래픽(GA4 활성사용자의 ~50%)이 GET만 대량 반복 — 쓰기 API 제한만으로는 무방비였음. 정적 자산은 첫 로드에 수십 건이라 NAT 공유 IP 오차단 방지 위해 제외.
- **How to apply:** 값 조정은 Limiter의 default_limits만 변경. 429 관측은 `[rate-limit]` 로그(원본 IP 대신 salted hash 10자리, UA·경로는 제어문자 제거).
- 요청 access log가 없으므로 봇 조사 데이터 소스는 `page_views` 테이블(viewed_at·path·ip_hash·user_agent)이 유일 — 운영 DB(PROD_DATABASE_URL)를 별도 집계해야 함. 확인된 봇 UA: `undici`, `Go-http-client/1.1`, 동일 "moto g power (2022)" UA 대량, 253개 IP가 공유하는 iPhone OS 13_2_3 UA(분산 봇), MJ12bot(robots.txt로 차단 선언).
