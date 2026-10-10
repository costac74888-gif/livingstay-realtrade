# 인증·회원·파트너 및 2.0 충돌 분석

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 현재 실제 모델 (CONFIRMED)
- canonical `users`: 이메일 password_hash + Kakao ID/provider, 상태/동의/전화 인증.
- `account_role_memberships` + `account_business_memberships`: general/agent/operator/loan_consultant/lodging_operator와 승인된 사업장 context. 기존 agents/operators/loan_consultants는 업무·사업장 데이터이고 연결 계정의 로그인/재설정 자격증명은 users 단일 소유.
- `app.py:9526` · `_unified_role_login()`: 명시 role 선택, users password, approved context, 복수면 선택. 아직 연결 안 된 legacy business는 본래 password proof 후에만 최초 전환하며 기존 users 이메일 자동 병합을 하지 않습니다.
- `app.py:8987` · `_get_account_contexts()`; `app.py:9087` · `auth_switch_context()`: 활성 멤버십+승인 사업장·소유권 확인, 전용 dashboard로 전환.
- 중개사, 위탁/청소/세탁/용품/소독/세무/인테리어 운영지원, 대출상담사, 숙박운영자 지원. 분양은 현재 신청/프로젝트/승인 기능이며 이 네 역할과 같은 독립 로그인 dashboard가 있다고 확인되지 않았습니다.
- admin_users/session admin은 별도 관리자 인증. 일반 회원 session user_id/active_role/business와 혼동하지 않음.
- Flask signed cookie는 FLASK_SECRET_KEY, HttpOnly/Secure/SameSite=Lax. provider와 role은 다른 의미입니다.

## Kakao OAuth
`app.py:10018` · `kakao_start()`; `app.py:10035` · `kakao_callback()`.
KAKAO_REST_API_KEY/KAKAO_CLIENT_SECRET과 redirect URI/state 흐름 존재. Kakao 기존 ID로 users를 찾고 신규 가입은 카카오 password 없이 생성. 기존 이메일 충돌은 임의 account takeover 병합이 아닌 별도 처리 코드. 카카오 callback 후 general context를 시작합니다. token/실제 사용자 profile은 조회하지 않았습니다.

## 비밀번호/전화/세션
`app.py:9262` · `auth_request_password_reset()`; `app.py:9930` · `auth_change_password()`.
통합 password 변경·재설정, reset token digest/TTL/used_at, per-IP/per-email throttle, 비동기 메일; role/business session guard. 전화 OTP·본인 확인은 직거래 공개와 operator 신청 등 별도 목적. 새로 PW 바뀐 뒤 이미 발급된 모든 쿠키를 즉시 폐기하는 보장은 runtime/browser 확인을 하지 않아 UNKNOWN입니다.

## 미래 general=Kakao-only / partner=email 정책 충돌 (INFERRED)
1. 한 사람이 general과 여러 partner 역할을 함께 보유할 수 있으므로 general 로그인 버튼 정책과 users provider/password 소유권을 동일하게 취급하면 파트너 자격증명을 끊을 수 있습니다.
2. 이메일/비밀번호를 가진 기존 일반회원·Kakao+email 동시 계정의 이전/계정 연결·개인정보 동의·재설정·관심/채팅 이력 보존 정책이 필요합니다. 이번 단계에서는 결정·변경하지 않음.
3. 카카오 제공 이메일이 없거나 기존 이메일과 충돌하면 기존 계정 소유권 증명 문제가 남습니다. 이메일 문자열만으로 자동 연결하면 안 됨.
4. 파트너 role access는 Kakao 자체가 아니라 approved membership과 선택 context로 통제해야 합니다.
5. 신규 일반 이용자와 임대인/운영자/중개사의 역할 전환·동일 계정의 UI 분리가 필요하며 현재 역할/사업장 연결을 재사용할 수 있습니다. 구현 없음.
