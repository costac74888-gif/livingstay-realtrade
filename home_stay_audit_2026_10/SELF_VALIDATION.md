# 0단계 자체검증

CONFIRMED: 시작 시 기록한 기존 추적 파일 852개 SHA-256 원문 비교 결과 변경/삭제 0건.

- 소스/db.py/SCHEMA_VERSION/기존 파일명/설정: 변경 안 함.
- DB: 명시 production 경로의 schema metadata 및 SELECT aggregate만 호출. INSERT/UPDATE/DELETE/DDL/migration/sequence 조작 안 함. 기존 실행 배치는 조사와 별개로 계속 실행될 수 있으므로 DB 전체 불변을 주장하지 않음.
- API 신규 수집/동기화/관리자 실행 버튼/테스트용 운영 API: 호출 안 함. 앱/관리자 HTTP GET도 호출 안 함.
- Secret 값/연결 문자열/Relay token: 읽거나 기록 안 함. 이름과 존재만 확인.
- 개별 회원·신고 업체·연락처·채팅·문서·계좌·실거래 행: 추출 안 함. schema 정의/집계만 사용.
- 보고서 privacy 형식 검사: 실제 이메일·credentialed DB URL·JWT·private key·대표 provider key·긴 인증 query 패턴 없음. 실제 Secret 값을 읽어 비교하는 방식은 사용 안 함.
- Git commit/push: 실행 안 함. 소스 hash 검사는 git 외부 원문 기준도 포함.
- 배포/워크플로/Relay/YES24 설정·시작/정지/재시작: 안 함.
- CONFIRMED/INFERRED/UNKNOWN 구분, runtime/source snapshot 차이, row estimate -1 UNKNOWN, 활성신고 정확한 상태값, 금액의 레거시 만원 단위 기록.
- ZIP 허용 확장자: .md 및 .csv만. source/.env/DB dump/업로드 원본/조사 스크립트/AUDIT_COUNTS.json 제외.

Git status에서 신규 보고서 폴더 외 사전 존재 변경 여부는 시작 baseline과 hash로 검증했습니다. 플랫폼 자동 체크포인트는 본 작업이 git commit 명령을 실행했다는 의미가 아닙니다.
