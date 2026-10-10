# 0.5단계 자동 개발·검증 Harness

이 하네스는 제품 기능 개발이나 운영 실행기를 대신하지 않는다.
`MASTER_SPEC.md`(고정 요구사항), `stages.json`(18단계 및 acceptance 기준),
`checks.json`(검토한 실행 검사), `preservation_baseline.json`(보존 기준),
`state.json`/`STATUS.md`(현재 단계·결과·Git 상태)가 저장소의 기준이다.

## 명령

```sh
python scripts/hs2_harness.py status
python scripts/hs2_harness.py self-check
python scripts/hs2_harness.py start 1
python scripts/hs2_harness.py verify 1 --note "변경사항 및 검토 근거"
python scripts/hs2_harness.py finish 1
python scripts/hs2_harness.py request-approval production_migration --note "대상·범위·복구계획"
```

같은 명령을 다른 작업 디렉터리에서 호출해도 저장소 기준으로 실행한다.
`start`/`finish`는 깨끗한 Git 작업 트리와 현재 단계 조건을 요구한다.
검토한 변경을 사용자가/개발자가 먼저 commit하면 **local Git tag**
`hs2/stage-NN/start`, `hs2/stage-NN/complete`를 만들고 HEAD를 기록한다.
하네스는 `git add`, commit, push, force tag, reset, checkout을 하지 않는다.
완료 이후 생긴 상태 기록을 다음 단계 전에 별도 commit한다.

## 테스트 추가/진행 순서

1. 현재 단계 acceptance 기준에 대응하는 실제 기능 검사를 구현한다.
2. 검토 후 `checks.json`에 tests 아래 파일/kind/role=acceptance/SHA-256을 등록하고
   `stages.json`의 해당 acceptance.check에 검사 ID를 연결한다.
   미구현(null)은 **BLOCKED**. 문서 존재만 검증하는 검사는 실제 기능 검사가 아니다.
3. `verify`가 모든 acceptance와 공통 regression을 실행한다. 실패/시간초과는 FAIL.
4. 변화 메모·결과·회귀검사·파일 지문·Git 변경 파일/커밋 상태가 state에 남는다.
5. 검토·commit 후 `finish`. 코드/검사/spec가 바뀌면 이전 PASS는 무효이며 재검사 필요.
6. COMPLETE 이후에만 다음 단계 start 가능. 자동 18단계 연속 실행 없음.

## 안전 범위

- 앱을 import하거나 preview/관리자/운영 URL을 호출하지 않는다.
- 새 테스트 환경에는 운영 환경을 복사하지 않는다. DSN/Secrets/Relay token 없음.
- Python network/socket/DB 연결/app import/자식프로세스, Node network/자식/worker 차단.
- 기존 전체 pytest·smoke·browser workflow에는 DB/앱 접근 검사가 섞여 있어 실행 안 함.
  이번에 검토한 순수 함수/모의 HTTP/정적 UI 검사만 등록한다.
- 기존 `test_public_api_client.py`의 관리자 runtime 검사는 app import가 필요해
  엄격 가드에서 차단된 FAIL을 기록했다. 검사를 삭제/수정하거나 운영 앱 접근을
  허용하지 않고, 하네스용 모의 Relay+관리자 decorator 정적 계약 검사를 분리했다.
  기존 관리자 runtime 인증 동작은 이번 0.5단계에서 실증하지 않았다.
- 가드는 **검토된 검사에 대한 실수 방지책**이지 악성 코드 OS sandbox가 아니다.
  native driver/직접 syscall/환경 우회가 필요한 검사는 자동 등록 금지.
  browser/integration은 별도 승인된 mock server/격리 DB 설계 후 추가 검토 필요.
- 운영 DB 데이터는 조회도 변경도 하지 않는다. schema/DB 보존은 감사 기준·코드 계약
  검사이며 살아있는 운영 DB 전체 불변을 실증했다는 주장이 아니다.
- 고정 수집·분류·Relay·schema 코드는 해시 보호. app/API는 기존 route/함수/메서드 및
  화면 파일 존재와 회귀검사로 보호하며 새 기능 추가는 허용.
  보존 기준 갱신은 자동 제공하지 않는다. 별도 영향 검토/승인/코드 리뷰 필요.
- 승인 요청은 `AWAITING_OWNER_APPROVAL` 기록뿐. 승인·배포·과금·migration 실행 명령 없음.
  소유자가 별도 채널에서 승인하고 수동 실행한 증거를 기록해야 한다.

## 저장·증거

작은 결과/이력/Git SHA는 `state.json`에 추적. 원시 로그는 `.local/hs2-harness/`에
생성하고 Git/배포에서 제외. 결과에는 로그 SHA-256을 보관한다.
문제 로그를 공유하기 전 추가 개인정보 점검을 한다. 메모에도 PII/Secret을 넣지 않는다.
원시 로그 보존이 필요한 CI는 별도 비공개 artifact 저장소에 보관한다.
`STATUS.md`는 사람이 읽는 요약, `state.json`이 기계 기준. 두 파일 갱신은
동시 하네스 실행 lock으로 보호. 실패로 진행을 막는 로컬 개발 거버넌스이며
파일을 악의적으로 수정하는 관리자에 대한 권한 통제는 아니다.
