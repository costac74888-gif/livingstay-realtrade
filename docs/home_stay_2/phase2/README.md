# 사용자 Phase 2 — 격리 개발 데이터 확장

## 범위와 단계 대응

이번 지시의 Phase 2는 **데이터 확장**이다. 저장소 18단계 중 2단계는
계정·로그인으로 다른 범위다. stages.json과 1단계 COMPLETE 영수증은 변경하지
않는다. 원장 분리/등록 관계(3~5), 재고 관계(9), 가격 보존(10)의 **데이터 기반만**
이번에 만들며, 해당 제품 기능·화면·서버 단계는 시작하거나 완료하지 않는다.
사용자 Phase 2는 phases.json의 P02-A01/A02와 state.json의 user_phases["2"]로
별도 관리한다. Phase 3와 저장소 2~18단계는 미시작이다.

## 실제 구현

- PostgreSQL 16 로컬 임시 클러스터에 hs2_dev schema를 생성한다.
- hs2_fixture_legacy의 합성 사용자/숙박 원장만 연결한다. 실제 원장은 조회하지 않는다.
- 후보/다중 식별자/등록 건물/선택적 정확한 master 연결, 물리 재고/중첩 관계,
  등록권한/허용 호실/독립 매물/append-only 분류, 버전 요금/불변 가격 fixture를
  실제 FK/unique/check/trigger/SQL role로 구현한다.
- 일반 후보는 숙박 master 연결 없이도 등록할 수 있다. 주소만으로 병합하지 않는다.
- 동의/영업신고/건물 용도/채널을 소유권이나 운영 적법성으로 자동 승격하지 않는다.
- 합성 writer는 원장·sequence·승인 근거를 수정할 수 없고, 허용 호실에만 매물을 쓴다.
  합성 public role은 limited view만 조회한다. view는 public UUID/kind/withheld뿐이다.
- 확정예약 엔진/결제/취소/월 계산은 구현하지 않는다. 저장되는 price snapshot은
  승인된 **인메모리 설계 fixture**이며 실제 예약 확정/사업정책 승인과 다르다.
- 기존 app/db/운영 import, route, UI, 권한, 원장, 수집, Relay, Secrets를 바꾸지 않는다.

## 실행·기록

진입 시 Phase 1 fingerprint/완료 태그/11개 로그 SHA가 일치했음을 확인했다.
Phase 0.5 기존 PASS 기록은 보존하며 Phase 2에서 원래 9개 등록 검사와 Phase 1
acceptance를 포함한 **현재 registry 전체**를 실행한다.

```text
python -B scripts/hs2_phase2.py verify
# PASS 결과와 fingerprint, 로그 SHA 저장 후 reviewed source/evidence commit
python -B scripts/hs2_phase2.py finish
```

개별 확인도 core.run_check의 phase2-data-contracts 등록으로만 실행한다.
테스트 capability는 해당 파일에만 부여한다. 다른 검사에 DB 접근을 허용하지 않는다.
기존 guard는 변경하지 않았으며 원래 앱 import/네트워크/child process 차단은 유지한다.

DB는 매 검사마다 /tmp/hs2-pg-*에 새로 생성되고 TCP listen은 비활성이다.
부모가 소유한 UNIX socket의 고정 db/user/port만 허용하며 URL/DSN/운영 env를
복사하지 않는다. 별도 클러스터는 suite 끝에 종료·삭제하고 로그만 기존 ignored
.local/hs2-harness에 남긴다. 앱·수집 workflow를 시작/재시작하지 않는다.

현재 단계/RUNNING·PASS·FAIL·BLOCKED·COMPLETE, 검사/차단 사유/원격 저장/
다음 동작은 docs/home_stay_2/STATUS.md와 state.json에 기록한다.
미해결 FAIL은 BLOCKED로 명시하고 후속 진행을 금지한다. 빈 suite/skip/오래된
지문/검사 누락은 완료가 아니다.

Phase 1과 Phase 2 commit은 동일 독립 개발 브랜치의 이력에 남긴다.
main/인계 브랜치 병합·push, force push, 운영 DB/PG/Publish를 수행하지 않는다.
원격은 개발 브랜치만 non-force push하고 ls-remote로 SHA를 비교한다.
완료 태그는 로컬이다. 원격에는 해당 commit 이력이 개발 브랜치로 포함된다.

## 검증 한계

실제 PostgreSQL 제약과 합성 DB 역할의 효과는 검증하지만 실제 사용자 인증,
HTTP API/브라우저 UI, 기존 운영 DB의 실측 무결성, 예약 동시성/서비스 적법성은
검증하지 않는다. fixture actor 설정은 서버가 정한 신뢰 컨텍스트의 모의값이지
클라이언트가 보내는 boolean/ID를 신뢰하는 인증 설계가 아니다.
복합 재고 관계의 데이터 무결성은 예약 가용성·hold·이중 청구 방지 구현이 아니다.
미확정 정책은 phase1/POLICY_REGISTER.md의 OPEN을 그대로 유지한다.
