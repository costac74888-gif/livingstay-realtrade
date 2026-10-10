# Phase 1 — Master Spec + 데이터 확장 설계

이번 지시의 Phase 1까지만 진행한다. 기존 브랜드 자산은 그대로 유지한다.
운영 UI/API/schema/수집기/외부 연동을 구현하거나 변경하지 않는다.

## 단계 대응: 순서 변경 또는 후속 단계 완료가 아님

| 이번 지시 | 저장소 단계 | 이번 작업에서의 의미 |
| --- | --- | --- |
| Phase 1 Master Spec·데이터 확장 설계 | 1 도메인 계약·보존 경계 확정 | S01-A01/A02의 실제 독립 계약 검사로 검증·완료 |
| 계정·후보·등록·공개범위 관계 설계 | 2~5 | 관계·권한 경계의 설계만. 로그인/등록 서비스·화면 구현 또는 단계 시작 아님 |
| 체류·요금·재고·가격 스냅샷 설계 | 6~10 | 값 계약과 데이터 설계만. 예약/재고/가격 서비스 구현 또는 단계 시작 아님 |
| 독립 지도 레이어·위치보호 경계 | 12~14 | 기존 URL·지도 보존 원칙만. 지도 구현 아님 |
| 결제·정산·릴리스 경계 | 17~18 | 미승인·미실행 유지. 구현·운영 반영 아님 |

첨부에서 확인 가능한 새 지시는 Phase 1의 제목과 범위뿐이다. 나머지 새
17단계의 순서/제목을 추정하지 않는다. 기존 stages.json의 1~18 번호·순서,
acceptance 원문과 기존 전체 9개 검사 등록을 유지한다.
다음 단계는 사용자의 별도 지시 전까지 시작하지 않는다.

## 읽기 순서

1. [기존 사용 조사](EXISTING_DATA_REVIEW.md)
2. [데이터 확장 설계](DATA_EXTENSION_DESIGN.md)
3. [미확정 정책·실행 차단](POLICY_REGISTER.md)
4. MASTER_SPEC.md, stages.json, checks.json
5. state.json의 stages["1"].verification 및 end

## 검증과 체크포인트

- 진입 기준: 지정 인계 branch/tag의 peeled commit
  f84265dbf2272f00e65f7042aa2c6c56119fcb97 일치, 초기 clean tree,
  현재 환경의 Phase 0.5 self-check 9개 묶음 PASS.
- 독립 브랜치: development/home-stay-2-phase-1-design.
- S01-A01 → phase1-use-contracts:
  검증된 숙박 영업근거/용도/채널 구분, 미확인·충돌 차단,
  0박/1박·6일/7일 경계, 날짜별·주월 가격, 누락·기간 겹침·불변 스냅샷.
- S01-A02 → phase1-graph-contracts:
  후보/등록/매물 관계, 별도 ID, 정확·유일·읽기전용 legacy 연결,
  건물·호실 범위 권한, 공유 재고의 동일성, 제한공개 allowlist DTO.
  기존 SQL 관계를 정적으로 대조하되, 문서 존재만으로 PASS를 판정하지 않는다.
- 기존 9개 공통 검사 모두 포함하여 verify 1을 실행한다. 등록 파일 SHA,
  소스 지문, 결과/exit code/로그 SHA는 state.json에 기록한다.
- 검사 실패·충돌·보존 위반은 중단한다. skip/빈 검사/기준 완화는 허용하지 않는다.
- 검토 가능한 소스·검증 근거 commit 뒤 finish 1의 완료 태그를 생성하고,
  완료 상태만 별도 commit한다. 태그 commit과 이후 상태 기록 commit은 구분한다.
- 상태 조회는 hs2_harness status, 검증 근거는 stages["1"].verification,
  완료 체크포인트는 hs2/stage-01/complete가 기준이다.
  handoff 객체는 과거 0.5 인계 영수증이며 현재 개발 상태는 stages가 기준이다.

## 증거의 한계

hs2_design은 애플리케이션에 연결하지 않은 표준 라이브러리 기반 값 계약이다.
DB·HTTP·UI·실제 provider·법적 운영 가능성 검증이나 기능 배포가 아니다.
동시 예약/DB 제약/인증 세션의 실효성은 이후 승인된 격리 환경에서 검증해야 한다.
운영 파일 무변경은 원본 인계 commit 대비 Git 변경 범위로 별도 확인한다.
운영 DB 자체의 상태/불변을 접속해 증명한 것으로 해석하지 않는다.
