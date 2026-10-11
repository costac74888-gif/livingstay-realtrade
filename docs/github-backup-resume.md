# GitHub 이력 보존 백업과 재개

이 도구는 Git push 인증이 실패해도 **기존 GitHub 연결의 proxyFetch**를 사용한다.
토큰을 꺼내거나 파일에 저장하지 않는다. 앱 실행·운영 DB·게시·main 병합과 무관하며
자동 실행 워크플로에는 연결하지 않았다. 이 작업에서는 실제 원격 전송을 실행하지 않았다.

## 구성

- `scripts/github_backup_export.py`: 기존 비공개 cat-file 내보내기 방식을 재사용해
  원본 바이트와 API 요청을 내보낸다. 메시지 마지막 LF, 부모 순서, 작성자·커미터
  시간과 시간대, 빈 커밋을 그대로 유지한다.
- `scripts/github_backup_objects.mjs`: SHA를 로컬에서 재계산하고 원격 응답 SHA를 대조하는
  배치 전송기. 네트워크·저장 함수는 주입한다.
- `scripts/github_backup_runner.mjs`: 기존 연결을 사용하고 객체별 진행 파일을 원자적으로 저장한다.
- `tests/github_backup_test.mjs`: 임시 Git 저장소와 가상 GitHub만 사용하는 오프라인 검사.

## 1. 내보내기 (네트워크 변경 없음)

원격 개발 ref와 main의 현재 SHA를 **기존 GitHub 연결의 읽기 요청으로 확인한 후**
그 값을 고정한다. 개발 브랜치 이름은 `development/`로 시작해야 한다.
아래 대문자 변수는 확인된 값으로 치환하며 인증값은 넣지 않는다.

```sh
python scripts/github_backup_export.py \
  --base EXPECTED_REMOTE_DEVELOPMENT_SHA \
  --tip LOCAL_TIP_SHA \
  --owner REPOSITORY_OWNER \
  --repository REPOSITORY_NAME \
  --branch development/BRANCH_NAME \
  --expected-main EXPECTED_REMOTE_MAIN_SHA \
  --output generated-artifacts/github-backup/export.json
```

내보내기 파일은 원본 코드와 커밋 작성자 정보를 포함하므로 공개 자산으로 전달하지 않는다.
내보내기와 진행 기록은 Git·배포 제외 디렉터리에 저장하고 권한은 0600이다.
이미 존재하는 내보내기는 덮어쓰지 않는다. 진행 중인 내보내기를 바꾸면 지문 검사로 중단된다.
브랜치를 바꾸거나 tip을 새로 잡을 때에는 새 내보내기·진행 파일 쌍을 사용한다.

완전한 트리를 자식부터 전송하므로 삭제·실행 권한·심볼릭 링크·gitlink와 병합 커밋도
보존한다. 같은 트리의 빈 커밋은 생략하지 않는다. 비 UTF-8 파일명·메시지,
추가 commit 헤더(서명, encoding, mergetag 등), SHA-256 저장소 등 Git Data API로
그대로 재현하지 못하는 입력은 명시적으로 중단한다. 이 경우 해시를 바꿔 우회하지 않는다.
빈 트리는 GitHub에서 조회해 재사용하며, 원격에 없으면 POST []로 우회하지 않고 중단한다.

## 2. 기존 연결로 한 배치 전송

Replit Agent의 CodeExecution에서 **impure 함수 안에만** 연결과 모듈을 둔다.
새 통합을 설치하거나 토큰을 요청하지 않는다. 아래는 반복해서 쓸 수 있는 실행 예시다.
모듈 경로는 해당 작업공간의 절대 경로로 지정한다.
연결이 여러 개면 원하는 기존 연결 ID를 먼저 선택하고, 임의로 첫 계정을 쓰지 않는다.

```javascript
const backupSummary = await (async function() {
  "use impure";
  const connections = await listConnections('github');
  if (connections.length !== 1) {
    throw new Error('Choose the existing GitHub connection explicitly');
  }
  const { runConnectedBatch } =
    await import('/home/runner/workspace/scripts/github_backup_runner.mjs');
  return await runConnectedBatch({
    connection: connections[0],
    manifestPath: '/home/runner/workspace/generated-artifacts/github-backup/export.json',
    progressPath: '/home/runner/workspace/generated-artifacts/github-backup/progress.json',
    maxObjects: 20,
    maxRequestBytes: 262144,
    maxBatchBytes: 524288,
    attempts: 3,
    updateRef: false
  });
})();
console.log(backupSummary);
```

연결 객체는 impure 함수 밖으로 반환하지 않는다. 출력은 상태·건수·바이트 수뿐이다.
`uploading`이면 같은 파일 쌍으로 다음 배치를 실행한다. `ready`이면 모든 객체가 확인됐지만
개발 ref는 아직 바뀌지 않았다. **실제 개발 ref 변경을 승인받았을 때만**
`updateRef: true`로 같은 배치를 한 번 더 실행한다.
`verified`가 원격 tip 확인과 마지막 main 불변 확인을 모두 마쳤다는 뜻이다.

각 배치는 최대 객체 수와 JSON 요청 바이트 합으로 제한한다. 단일 객체가 요청 한도를 넘으면
전송 전 중단한다. blob 바이트를 쪼개서 별도 Git 객체로 바꾸지 않는다.
필요 시 승인된 한도를 조정한다. 재시도까지 포함한 객체 요청 본문량 상한은
`maxBatchBytes × attempts`이다. ref·조회 요청은 별도이며 객체 업로드는 순차 실행한다.
전송 중인 배치는 새 프로세스가 아니라 한 번의 제한된 호출이므로 긴 단일 실행을 피한다.

## 3. 실패와 재개

- 진행 기록은 SHA 확인 뒤 **객체마다** 저장한다. 성공 SHA·내보내기 지문·단계만 기록한다.
- 기록 전 중단된 객체는 원격 GET 후 다시 사용한다. 동일 내용 POST 재시도도
  content-addressed이므로 다른 Git 객체나 커밋을 만들지 않는다.
- 연결 중단, 429, 5xx는 제한된 횟수만 대기 후 재시도한다. Retry-After는 최대 30초를 기다린다.
  비 JSON 403·기타 영구 오류는 원문 응답을 저장·출력하지 않고 상태 코드만 남긴다.
- 잘못된 JSON 성공 응답, SHA 불일치, 내보내기 지문 불일치는 ref 변경 없이 중단한다.
- PATCH는 무조건 `force:false`이며 자동 반복하지 않는다. 변경 의도를 먼저 저장한다.
  응답 유실 시 다음 실행에서 개발 ref가 목표 SHA인지 읽어 최종 검증만 수행한다.
  여전히 예상 시작 SHA이면 명시적 승인 후 PATCH를 다시 할 수 있다.
- 예상 개발 ref/main과 다르면 즉시 중단한다. 새 예상값으로 자동 덮어쓰지 않는다.
  마지막 main 확인이 실패하면 `verified`를 기록하지 않고 main을 되돌리려 하지 않는다.
- 진행 파일의 `.lock`은 동시 실행을 차단한다. 정상 종료·처리된 예외에서는 해제한다.
  강제 종료로 남은 lock은 **해당 실행이 더 이상 없는지 확인한 뒤에만** 수동 제거한다.
  같은 대상은 같은 진행 파일로 작업하고 병렬 작업이나 별도 진행 파일을 사용하지 않는다.

### 원격 ref 경합의 한계

GitHub Git Data API PATCH에는 expected-old-SHA 원자 비교 옵션이 없다.
이 도구는 시작 시 및 PATCH 직전 예상 ref를 확인하고, non-fast-forward 경합은
`force:false`로 거부하며, PATCH 뒤 목표 ref와 main을 다시 확인한다.
하지만 마지막 GET과 PATCH 사이에 다른 작업자가 목표 tip의 조상으로 ref를 바꾸면
GitHub가 fast-forward를 허용할 수 있다. **정확한 동시 쓰기 배제까지 보장하지 않는다.**
다른 작업자의 push를 멈춘 승인된 백업 시간에만 ref 갱신을 수행한다.
경합이 발견되면 이력을 덮어쓰거나 main을 수정하는 대신 중단하고 사람이 판단한다.

## 오프라인 회귀 검사

```sh
node --test tests/github_backup_test.mjs
```

GitHub·메일·SMS·DB에는 접속하지 않는다. 중단/재개, 비 JSON 오류, 제한 재시도,
SHA 불일치, 메시지 LF 변경, 원격 ref 경합, PATCH 응답 유실 및 마지막 main 변경을 검사한다.
이는 실제 GitHub 인증·쓰기 성공을 확인한 결과가 아니다.
