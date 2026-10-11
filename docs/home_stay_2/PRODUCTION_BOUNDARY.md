# 운영 배포 경계 검사

`python scripts/hs2_production_preflight.py`는 실제 `scripts/start-prod.sh`를
격리된 작업공간에서 실행하고, 선택된 `app:app`의 등록 경계를 검사한다.
Gunicorn 대신 검사 실행기를 사용하므로 HTTP 서버와 운영 워커는 시작하지 않는다.
운영 명령·`app.py`·운영 활성화 상태는 바꾸지 않는다.

현재 `.replit`의 `npm run build:frontend` → `scripts/build_frontend.py`는
이 검사를 **다른 빌드 작업과 릴리스/마커 생성 전에** 수행한다. 운영 명령 또는
게시 빌드 명령이 승인된 경로에서 달라지면 검사를 통과시키기 전에 별도 검토가
필요하다.

## 실패하는 연결

- 실제 호출된 HS2 fixture factory, `seed_paid`, fixture DB 연결 함수
- 등록된 라우트·훅에서 도달하는 fixture 함수(별칭·클로저·기본 인수 포함)
- 연결된 금융 repository/provider의 `OwnedSandbox` 또는 `sandbox=True`
- 익명 요청이나 개발용 session flag만으로 신원을 제공하는 역할 resolver
- 운영 시작 명령 또는 앱 import가 선택하는 HS2 임시 DB 환경과 DSN 변경
- `app:app`이 아닌 Preview/fixture WSGI 실행 대상

저장소의 fixture 파일 존재 또는 사용하지 않는 import만으로는 실패하지 않는다.
동적 검사이므로 악의적인 코드가 검사 실행을 인식해 숨기는 경우까지 증명하는
보안 sandbox는 아니다. 등록된 콜백의 실행 연결, 객체 구성과 생성 호출을
검사하며 네트워크/DB 격리는 별도의 하위 전송 가드가 담당한다.

## 실행과 안전 범위

```sh
python tests/test_hs2_production_boundary.py -v
python scripts/hs2_production_preflight.py
```

각 검사는 새 소유 PostgreSQL 클러스터(UNIX socket만, TCP listener 없음)를
만들고 삭제한다. 환경은 허용된 런타임 항목만 전달한다. 운영 DB·실제 API 키를
전달하지 않고 앱 초기 스키마/백그라운드 작업과 외부 알림을 끈다.
DB 드라이버는 소유 UNIX socket 외 연결을 거부하며 DNS/TCP/외부 전송도
차단한다. 원본 소스·Preview 자산은 덮어쓰지 않는다.

검사는 정상 경로 통과뿐 아니라 잘못된 fixture factory, 가상 신원, 모의 결제,
임시 DB와 게시 경로를 의도적으로 주입한 실패도 확인한다. 프런트 릴리스 검사는
별도 소유 작업공간에서 계속 실행한다.

**통과는 실제 토스 PG 결제·정산이나 Phase18 검증 완료를 뜻하지 않는다.**
운영 DB 쓰기, 실제 알림/결제 호출, main 병합 또는 게시는 수행하지 않는다.
