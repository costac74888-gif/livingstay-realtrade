# 사용자 Phase 3 — 건물·주소·좌표 등록 기반

이번 승인 범위는 여기까지다. Phase 2의 종료 제한을 이번 Phase 3 진입에 한해
해제하며, PASS 후 재질문하지 않지만 Phase 4나 운영 승인 Gate를 넘지 않는다.
현재 상태는 상위 `state.json`의 `user_phases.3`, `STATUS.md` 첫 구간이 기준이다.
과거 영수증과 상태 문단은 당시 기록으로 보존한다.

## 번호와 실제 기능

사용자 Phase 2는 데이터 확장이었고 저장소 2단계 인증과 다르다. 이번 Phase 3는
저장소 S03-A01/A02의 주소/건물 요구를 참고한다. 저장소 2단계 인증을 구현하지
않았으므로 원래 18단계 계획과 모든 2~18단계 PENDING을 변경하지 않는다.
인증/CSRF는 신뢰 경계를 주입하는 미장착 Blueprint 계약으로 검증한다.
개발 fixture의 actor=1은 실제 로그인이나 계정/권리 승인 수단이 아니다.

- `hs2_registration.service`: 주소 입력 → 원본 주소 선택 → 건물 후보 선택 →
  대장 정보 확인 → 좌표 확인 → 비공개 후보 참조 저장의 실제 서버 상태 전이.
- `api`: 직접 실행 가능한 private HTTP handlers, actor·CSRF·만료·입력 검증.
  운영 `app.py`에는 장착하지 않는다. 새 공개 API/지도 레이어를 만들지 않는다.
- `web`: 실행 가능한 한국어 UI. 명시적 선택, busy/오류/미확인, 오래된 응답 폐기,
  조회 완료 좌표만 표시. 공개 매물/소유권/예약 등록 버튼이 아니다.
- `store`: 기존 Phase 2 `hs2_dev.candidates/master_links`에만 쓰는 실제
  PostgreSQL adapter. 일반 건물은 숙박 master 없이 별도 참조. 정확하고 유일한
  기존 identity만 optional 연결한다. 기존 원장·분류·ID·sequence는 쓰지 않는다.
- 대장 용도로 차단/숙박 분류하지 않는다. 후보 확인은 운영 적법성이나 권리 승인이 아니다.

## 조사와 재사용

| 기존 경로 | 판단 / 이번 사용 |
|---|---|
| `address_utils.road_to_jibun` | JUSO Relay 경로와 응답 필드 조사. countPerPage=1/첫 결과 선택은 모호성 은폐 위험이 있어 직접 호출하지 않음. JUSO `results/common/juso` 계약을 받아 전체 건수 일치와 명시적 선택 검증 |
| `building_registry._fetch_title_rows` | 지번 내 모든 동/페이지와 에러 처리 경로 조사. 실제 호출하지 않고 완료된 mock raw rows를 받음 |
| `building_registry._title_row_to_dict` | 기존 실제 공통 필드 변환기를 직접 재사용. 생숙 판정/방수 필터를 적용하지 않음 |
| `geocode_buildings.geocode_address` | Kakao 주소 API x=경도/y=위도 조사. DB/수집기 import 및 첫 document fallback 경로는 재사용하지 않음. 같은 응답 계약으로 전체·유일·정확한 주소·유효 좌표를 검증 |
| `app.py /api/buildings/search`, submit-building | 기존 숙박 master 검색/추가 경로 보존. 전체 용도 후보를 여기에 강제 INSERT하지 않음 |
| 기존 제한공개/공매 마커/Relay | 수정·호출하지 않음. 비공개 참조는 공개 DTO에 주소·좌표·ID·join을 제공하지 않음 |

bdMgtSn/bldMngNo와 mgmBldrgstPk는 다른 식별자다. 두 번호를 혼용하지 않는다.
주소 비교는 공백 정리만 하며 지역/번지/주소 별칭/좌표를 추정하지 않는다.
좌표 근거는 **공식 주소 응답 수준**이다. 여러 동의 중심이나 호실의 정확한 위치를
뜻하지 않는다. 마커 이동/좌표 보간/타일 위의 추정 표시를 하지 않는다.

## 검증·안전

`python -B scripts/hs2_phase3.py verify`는 이전 13개 그대로와 새 4개 acceptance를
모두 실행한다. FAIL/미구현/부분/과거 지문은 완료를 막는다. 새 DB 권한은 정확한
Phase 3 fixture suite에만, 브라우저는 검토된 suite의 owned loopback/Chromium에만
제한한다. 기존 일반 검사 guard를 완화하지 않는다.

PostgreSQL DB는 TCP 없는 `/tmp` UNIX socket, synthetic legacy로 매번 새로 만들고
삭제한다. UI는 owned loopback WSGI의 synthetic providers/memory store로 검증하며,
외부 요청은 차단한다. Node/Chromium/fixture server에 운영 DSN·토큰·키를 전달하지 않는다.
실제 DB 적용, 라이브 공급자 인증 연결, 공개 지도/실제 로그인 연결은 범위 밖이다.

## 복구

새 운영 migration 없음. 기존 Phase 2 migration bytes는 보존한다. fixture 저장은
SAVEPOINT로 전체 원자적 rollback; 충돌 시 정상 참조를 덮어쓰지 않는다. 반복 확인은
같은 참조를 반환한다. fixture 전체 down/up은 Phase 2 복구 규칙을 재사용한다.
UI HTTP 프로세스·Chromium·fixture DB는 검사 종료 때 종료/삭제한다.
Phase 3 모듈은 운영 앱에 미장착이므로 운영 데이터 복구 작업은 발생하지 않는다.

실제 계정 승인/매물/예약/결제/운영 공개/정책 확정은 수행하지 않는다. 이전 정책
OPEN과 세 운영 approval gate NOT_APPROVED를 그대로 유지한다.
