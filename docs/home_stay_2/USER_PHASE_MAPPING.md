# 사용자 총괄지시서와 저장소 단계 대응

원문: `attached_assets/0_붙여넣은_텍스트(1)_1791638904988.txt`의
20절(18단계 실행 순서). 2026-10-10 사용자가 이 원문을 Phase 4~18 기준으로
지정하고 **Replit 내부에서 Work 역할까지 수행**하도록 선택했다.
별도 외부 Work 통신 서비스는 사용하지 않는다.

아래 대응은 요구사항의 연결이지 기존 native 단계 COMPLETE 선언이 아니다.
완료된 사용자 Phase 1~3, 과거 native 계획, 검사·보존 기준과 영수증은 보존한다.
원문의 Phase 0.5 “현재 상태”는 과거 시작점이다. 완료된 Phase를 다시 시작하거나
기존 완료 태그를 재생성하지 않는다.

| 사용자 Phase | 원문 범위 | 저장소 요구/추가 범위 |
|---|---|---|
| 1 | Master Spec + 데이터 확장 설계 | native 1; 기존 완료 |
| 2 | DB 확장 + 기존 데이터 연결 | native와 별도 데이터 기반; 기존 완료 |
| 3 | 전체 건물/주소/지도 기반 | native 3 참고; 기존 비공개 등록 기반 완료 |
| 4 | 로그인/사용자·운영자 Mode 분리 | AUTH-01; S02-A01/A02 |
| 5 | PC 소비자 Main | PRODUCT-01, 검색 2행·좌측 목록/우측 지도; native 11 일부 |
| 6 | 단기임대 매물등록 | native 4~6; 등록·사진·공개범위·최소 체류 |
| 7 | 가격/Calendar Engine | native 6~10의 체류·요금·가용일; 확정 snapshot 경계 |
| 8 | 검색/Filter/Super Map | native 11~14; 독립 레이어·마커/겹침·선택 패널 |
| 9 | 매물 Detail + 예약 Panel | native 10~11 일부; 상세/예약 요청 UI |
| 10 | Booking Engine | native 9~10; 승인·재고·동시성·확정 snapshot |
| 11 | Payment/Deposit/Settlement 기반 | native 17 모의; 수수료 엔진 0%; 실제 PG Gate B |
| 12 | 운영자 Dashboard | native 16 일부; 등록/방/예약/계약/매출/정산/채팅 |
| 13 | 관심/Chat/Notification/My Booking | native 15 + 내 예약 |
| 14 | FAQ/이용 Guide/Policy | 원문 17절 고유 콘텐츠; 미확정 정책 임의 확정 금지 |
| 15 | Admin 확장 | native 16; 기존 관리자 보존 |
| 16 | Mobile | 원문 19절; PC와 동일 규칙·리스트/지도 전환 |
| 17 | 통합 Regression/Security/Payment Validation | native 18 검사 + native 17 모의 결제 검증 |
| 18 | Cutover/Open | 준비까지만 자동 진행; 실제 DB Gate A·PG Gate B·배포 Gate C |

18은 원문상 실제 운영 전환 목표이며 저장소 native 18의 “준비”와 다르다.
승인 없이 Cutover/Open을 COMPLETE로 기록하지 않는다. 모의 결제 검증은
실제 PG 성공을 의미하지 않으며, 비공개 fixture 검사는 운영 통합 검증이 아니다.

## 내부 Work ↔ Replit 전달

별도 채팅 서비스 대신 저장소에 Phase별 작업 지시와 결과 검토를 기록한다.
Work는 원문·대응·선행 조건·actual acceptance·보존/정책 경계를 확인한다.
Replit은 구현·전체 등록 검사·소스 지문·원시 로그 해시·Git 개발 체크포인트를
제출한다. Work는 실제 결과와 원격 SHA를 대조한 뒤 다음 Phase를 지시한다.
같은 에이전트의 역할 분리이며 독립된 외부 검토자가 검토했다고 주장하지 않는다.
