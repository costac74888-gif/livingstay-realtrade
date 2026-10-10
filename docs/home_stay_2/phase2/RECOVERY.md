# 개발 migration / 복구 계획 — 운영 적용 금지

## 대상 확인

대상은 테스트 부모가 생성한 /tmp/hs2-pg-*의 UNIX socket뿐이다.
hs2_data.repository의 connect_fixture/require_fixture는 고정 socket/marker를
확인한다. 환경 DSN, host flag, URL, 기존 개발·운영 DB fallback을 제공하지 않는다.
SQL은 hs2_fixture_legacy를 참조하므로 현재 app schema용 migration이 아니다.
운영 schema version/init_db, migration workflow, Publish hook에 연결하지 않는다.

## 적용과 사전 기록

001_up.sql은 새 hs2_dev만 생성하고 기존 합성 legacy를 FK로 읽는다.
별도 트랜잭션에서 fixture marker, 현 schema 유무, migration SHA 영수증을 확인한다.
이미 같은 version/SHA가 있으면 ALREADY_APPLIED; 다른 지문은 차단한다.
실제 앱 DB에 연결하려는 시도는 이 모듈의 승인 범위 밖이며 실행하지 않는다.

SQL role은 임시 클러스터 fixture bootstrap에서만 생성한다.
합성 legacy 행/분류/좌표/연결 ID와 sequence(last_value,is_called)의 사전 이미지를
비교한다. runtime 계정·grant 또는 원장에 역할/trigger를 설치하지 않는다.

## 실패 시

1. BEGIN 단위 적용 실패 → ROLLBACK. 새 schema와 부분 DDL이 모두 취소됨을 검사한다.
2. 제약/정책/전체 registry FAIL → 상태 FAIL, 정확한 check/exit code/log SHA 기록.
   범위 내 원인을 해결한 뒤 registry 전체를 재실행한다. 해결 불가면 BLOCKED.
3. 예상 밖 객체·receipt SHA가 있으면 자동 drop/cascade/복구 강행 없이 중단한다.
4. 테스트 프로세스는 시간 제한, 임시 서버는 별도 process group 종료·directory 삭제.
   운영 workflow/다른 postgres process는 중지하지 않는다.

## 완료된 개발 적용을 되돌리는 경우

001_down.sql은 명시적 역순 DROP이며 CASCADE가 없다. 같은 fixture marker/SHA
게이트에서만 실행한다. 합성 legacy tables/sequence는 DROP/UPDATE하지 않는다.
다시 up 적용이 가능하고 legacy 이미지가 같음을 실제 PostgreSQL 검사로 확인한다.
**down은 새 hs2_dev 데이터도 삭제한다.** 개발자가 보존할 fixture가 있으면 반드시
내보내기/백업·복원 계획을 먼저 검토한다. 실제 승인된 개발 환경으로 넓히기 전에는
독립 백업·복원 리허설과 그 환경 전용 schema mapping을 추가로 승인받아야 한다.
지금은 매 suite 새 클러스터를 만드는 임시 합성 데이터만 삭제하도록 한정한다.

가격 fixture/분류 이력은 정상 데이터 작업에서는 append-only다.
취소·가격 수정으로 원본을 고치거나 기존 master를 재번호하는 복구는 허용하지 않는다.
월 계산·취소/환불/정산의 미확정 정책을 migration default로 채우지 않는다.

## 사용자 승인 경계

새 데이터 구조를 기존 앱 개발 DB로 이관하는 migration, 실제 운영 데이터 매핑,
운영 migration, PG/정산, 배포는 모두 이번에 수행하지 않는다.
Phase 2 PASS는 이 승인을 대체하지 않는다.
