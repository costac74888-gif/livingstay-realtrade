# 보안 스캔과 검토 범위

2026-10-10 UTC 개발 코드에서 dependency/SAST/privacy 스캐너3종을 실행했다.
최초 의존성 high2·SAST68·privacy23. 보강 뒤 의존성0·SAST3·privacy21.
원문 경고는 ignored .local/hs2-harness/phase17-security-{scans,final}.json에 보관한다.
이 문서는 내부 Work 검토이며 독립 외부 보안감사 또는 운영 승인서가 아니다.

## 해결
- additive13 API의 CSP/Permissions/HSTS/frame/cross-domain/referrer/nosniff 보강.
  원래 더 엄격한 CSP와 private/no-store는 보존한다. 실제 복합 HTML/API 응답
  검사가 모든 헤더를 확인한다. 스캔의 기존65 header finding은 제거됐다.
- 목업 도구 source-map-js1.2.2와 compatible Vite/PostCSS 업데이트.
  braces 최신판에도 high가 남아 fast-glob discovery를 동일 .tsx·_ 제외·
  sorted output의 내장 디렉터리 순회로 교체했다. 심볼릭 링크는 따라가지 않는다.
  npm audit0, managed port/base를 준 Vite build PASS, 목업 workflow 정상.
- 두 geocode 배치의 예외 메시지는 공통 원문/URL-인코딩 인증값 마스킹을 사용한다.
  실제 키를 읽어 확인하지 않고 synthetic sentinel 검사로 검증했다.

## 남은 SAST3: 근거 있는 false positive 검토
- CRITICAL hs2_consumer/api.py 필터 query(): 실제로는 datetime/UUID/숫자
  범위만 파싱하는 hs2_consumer/search.py의 pure function이다.
  SQL/DB 실행기가 없고 public_catalog 콜백의 결과를 Python에서 필터한다.
  SQL 모양 입력도 단순 문자열로 남는 것을 자동검사한다. API 이름 alias 변경
  자체를 취약점 해결 근거로 삼지 않으며 스캐너 결과도 숨기지 않는다.
- MEDIUM2 static/js/auctions.js: rowHtml 데이터는 esc() HTML 특수문자 처리,
  숫자 형식은 numeric() 검사 후 출력하고 지역 option 이름도 esc()를 거친다.
  innerHTML sink 자체는 존재하며 검토한 escaped 출처와 고정 태그 이외를
  추가하면 재검토해야 한다. 이번 작업은 legacy 공매 렌더러를 바꾸지 않았다.

## 해결되지 않은 legacy privacy21
LOW16 수신 이메일 로깅, MEDIUM5 연락처 진단/보고서 표준출력 경고다.
기존 app.py, weekly/deal digest, sync와 report_authority_match의 경고는
HOME & STAY 새 원장·새 API에서 발생하지 않는다. 하지만 전체 프로젝트
‘경고0’ 또는 개인정보 검사 전체 PASS로 표현하지 않는다.
알림 수신자 마스킹 및 진단/보고서의 권한별 PII 출력 정비는 별도 범위다.
운영 전환 판단 때 이 잔여 경고를 함께 검토해야 한다.

## 운영 검증 제한
owned signed payment adapter/SDK·SQL fixture를 검증했으며 실제 PG webhook,
provider 환불/지급, 실제 host session mount, 운영 SDK/도메인, 실제 발송을
검증하거나 활성화하지 않았다. shared CSP의 frame-ancestors 'self'와 실제
preview/provider 요구도 host 통합에서 별도 확인해야 한다.
기존 smoke/api workflow는 작업 시작 전 실패 상태였고 이 registry에 포함되지
않는다. 새55그룹 PASS를 기존 프로젝트 전체 검사 PASS와 혼동하지 않는다.
