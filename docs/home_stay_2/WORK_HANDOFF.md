# HOME & STAY 2.0 — Work 인계

## 현재 상태와 진입점

- 현재 완료 범위: **0.5단계 개발·검증 Harness**. 제품 기능 구현 완료가 아니다.
- 다음 개발 단계: **1 — 도메인 계약·보존 경계 확정**.
- 기계 기준: `state.json`. `bootstrap.phase="0.5"`의 PASS와
  `handoff.status="READY_FOR_WORK"`를 확인한다.
- `current_stage=0`은 제품 1~18단계를 아직 시작하지 않았다는 뜻이다.
  1~18단계 모두 PENDING. 이번 인계 작업에서 1단계를 시작하지 않는다.
- 순서대로 읽기: 이 문서 → `MASTER_SPEC.md` → `STAGE_PLAN.md` →
  `stages.json` → `README.md` → `state.json` / `SELF_CHECK.md`.
- 전체 진행은 단계별이다. 18단계 자동 연속 실행, 자동 commit/push/배포는 없다.

## Git 인계 기준과 변경 범위

- 감사 기준 커밋: `c326ef8cb733b5a0d6eecb1889c8eb6020d6f28b`.
- Harness 원본 커밋: `a424b3b1f13efbee73b96a093a43c20a412c1358`.
- 이번 작업 최초 조회에서 원격 main과 로컬 HEAD 모두 Harness 원본 커밋이었다.
  이전의 GitHub 미반영 상태와 구분한다.
- 인계 브랜치: **`handoff/home-stay-2-phase-0-5`**.
- 시작 체크포인트: **`hs2/phase-0-5/handoff-start`** (Harness 원본 커밋).
- 최종 체크포인트: **`hs2/phase-0-5/handoff`** (검증·인계 기록 포함).
- 이번 작업은 main을 push/merge하거나 강제 갱신하지 않는다. 인계 브랜치와
  위 두 체크포인트만 원격에 반영하며, 원격 브랜치/최종 태그가 같은 커밋인지 확인한다.
- 감사 기준 이후 변경은 Harness·검사·문서·메모, npm 검사 명령 두 개,
  생성 로그의 Git/배포 제외 규칙뿐이다. 앱/기존 서비스/DB schema/수집기/
  기존 테스트/워크플로/의존성/Secrets/Relay 설정/운영 배포 변경 없음.
- 이번 인계 추가 변경은 인계 문서·README 진입점·검증/진행 상태 기록뿐이다.
- 최종 Git SHA는 태그가 기준이다. 자기 자신의 commit SHA를 파일 안에
  넣는 대신 `git rev-parse 'hs2/phase-0-5/handoff^{commit}'`으로 확인한다.
- `bootstrap.head`는 검사 시점의 소스 HEAD이지 최종 기록 commit을 의미하지 않는다.
  PASS 당시 검증 파일 지문과 최종 체크포인트를 함께 확인한다.
- clean 작업 트리만으로 원격 반영을 추정하지 않는다.

원격 확인:

```sh
git ls-remote origin refs/heads/handoff/home-stay-2-phase-0-5 \
  refs/tags/hs2/phase-0-5/handoff 'refs/tags/hs2/phase-0-5/handoff^{}'
```

annotated tag의 자체 SHA가 아니라 `^{}`로 해석한 commit SHA를 브랜치 SHA와 비교한다.
최종 태그는 검증 성공 후 생성하며, 기존 태그/브랜치가 다르면 덮어쓰지 않는다.
main만 내려받았다면 인계 브랜치나 최종 체크포인트를 명시적으로 선택해야 한다.

## 18단계 순서

1. 도메인 계약·보존 경계 확정
2. 계정·로그인·복수 역할
3. 주소·건물 등록 후보·대장 확인
4. 단기임대 등록·소유권·임시저장
5. 사진·편의시설·공개범위
6. 최소 체류·날짜 입력
7. 숙박 날짜별 요금·연휴
8. 비숙박 주·월 가격표
9. 예약 가능일·재고·동시성
10. 예약 확인·가격 스냅샷
11. 검색·목록·소비자 상세
12. Super Map 독립 레이어
13. 마커 형태·동일좌표 겹침 방지
14. 마커별 좌측 상세패널
15. 문의·채팅·관심·예약 알림
16. 운영자·관리자·신고/검수
17. 취소·결제·정산 **모의** 계약
18. 전체 회귀·접근성·릴리스 **준비** (운영 배포가 아님)

## 새 Work 환경에서 1단계를 시작하는 방법

Python 3.11 / Node 20에서 검증한 하네스다. 기존 `requirements.txt`의 Python
의존성과 Node 런타임이 필요하다. 실제 DB URL, API key, Relay token은 필요 없다.
운영 환경변수나 운영 `.env`를 복사하지 않는다. 앱/수집기/기존 전체 검사
워크플로를 시작하지 말고 아래의 격리된 검사만 실행한다.

```sh
python scripts/hs2_harness.py status
python scripts/hs2_harness.py self-check
```

1. 새 환경의 자체검증 PASS를 확인한다. 실패하면 복구 전까지 start하지 않는다.
2. 검증이 `state.json` / `STATUS.md` / `SELF_CHECK.md`를 갱신하므로 결과를
   검토하고 별도 개발 브랜치에 commit해 **clean 작업 트리**를 만든다.
3. 다음 명령으로 제품 1단계의 시작 태그를 생성한다.

```sh
python scripts/hs2_harness.py start 1
```

4. `S01-A01`/`S01-A02`의 실제 도메인 계약 검사를 구현하고 검토 후
   `checks.json`에 role=acceptance/SHA-256을 등록한다.
   `stages.json`에서 두 기준의 `check:null`을 실제 검사 ID로 연결한다.
5. `verify 1 --note "변경·검사 근거"` → 결과 검토·commit →
   `finish 1` 순서로 진행한다. COMPLETE 기록도 다음 단계 전에 commit한다.

현재 36개 acceptance는 모두 미구현(null)이다. 제품 기능에 대한 PASS가 아니다.
실제 검사 연결 없이 완료할 수 없으며, 문서 존재 검사로 대체하지 않는다.

## PASS/FAIL 및 진행 차단

- 전체 공통 회귀 + 하네스 + 이전 완료 단계 acceptance + 현재 acceptance를 실행.
- 검사 실패·timeout·보존 위반·검증 중 파일 변경은 FAIL.
- acceptance 미구현은 BLOCKED. 0개 Python 검사·skip·expected failure는 PASS 아님.
- 등록 검사의 해시가 다르거나 파일이 누락되면 미검토 검사로 차단.
- 소스·검사·명세가 변경되면 검증 파일 지문이 달라져 과거 PASS로 진행 불가.
- 이전 단계 COMPLETE 없이는 다음 단계 start 불가. 동시에 여러 단계 진행 불가.
- clean tree와 현재 지문 PASS가 있어야 start/finish 및 local Git checkpoint 생성.
- 검사 원시 로그는 `.local/hs2-harness/`에 생성하며 Git/배포에서 제외.
  저장소에는 결과/로그 해시/변경 메모/검사 시점 Git 정보가 남는다.
  원시 로그는 새 환경에서 재생성한다.
- 기존 검사 결과: Python 65개 + Node 계약 스크립트 3개, 9개 묶음 PASS.
  최신 실제 결과와 지문은 `SELF_CHECK.md`와 `state.json`이 기준.
- 실제 운영 UI/관리자 HTTP 인증/DB/브라우저 통합검사는 미실행이다.
  순수 함수·정적 계약·모의 요청 검사이며 운영 전체 불변 실증이 아니다.
  가드는 검토된 검사에 대한 실수 방지책이지 악성 코드 OS sandbox가 아니다.

## 기존 자산 보존

기존 숙박 master ID/sequence/분류/연결을 덮어쓰거나 재구축/재번호/재분류하지 않는다.
영업신고와 복수 허가·폐업 이력, 실거래, 공매/회차/현황조사, 기존 지도·관리자,
매물·관심·채팅·알림 이력을 보존한다. 등록 후보층과 기존 숙박 원장을 분리한다.
수집·쿼터·승격 계보·Relay allowlist/인증/fail-closed를 변경하지 않는다.
제한공개 매물의 주소·좌표·건물 join을 통한 위치 역추적을 허용하지 않는다.

13개 핵심 파일 해시, 기존 616 route 조합, 10개 필수 기능 파일과
분류/신고/공매/Relay/지도/관리자 범위/제한공개 회귀가 보호 기준이다.
보존 기준의 자동 갱신·무시·검사 삭제로 통과시키지 않는다. 영향 검토·별도 승인 필요.
요구사항의 세부 정책은 `MASTER_SPEC.md`를 따르며, 미확정 정책을 임의 확정하지 않는다.

## 별도 owner approval 게이트

| 대상 | 초기 승인 | 허용된 이번/자동 개발 범위 |
| --- | --- | --- |
| 운영 DB migration | NOT_APPROVED | diff·복구·승인 준비만. 실제 DB 조회/쓰기/migration 실행 금지 |
| 실제 PG·결제·정산 | NOT_APPROVED | test double만. 실제 청구/환불/정산/활성화 금지 |
| 운영 배포 | NOT_APPROVED | 준비·검사만. Publish/운영 릴리스 금지 |

`request-approval`은 AWAITING_OWNER_APPROVAL 요청을 기록할 뿐이며 승인이나
실행이 아니다. owner의 별도 승인과 범위·복구/법적 정책 검토가 필요하다.
GitHub 인계 브랜치 push는 운영 배포 승인이 아니다.
