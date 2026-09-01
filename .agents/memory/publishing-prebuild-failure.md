---
name: Publish 사전 실패 구분
description: Republish 실패 화면과 실제 빌드·프로모트·런타임 실패를 구분하는 기준
---

Republish 화면에 `Failed`가 표시되어도 `listDeploymentBuilds`에 새 failed/building 항목이 없고, `getDeploymentInfo`가 이전 성공 빌드를 계속 가리키면 배포 산출물 단계에 도달하기 전 요청이 실패한 것으로 판단한다.

**Why:** 빌드 단계 실패는 항상 빌드 ID와 빌드 로그가 남지만, 배포 요청·Publishing 제어 단계에서 실패하면 화면만 실패로 바뀌고 이전 성공 배포가 계속 서비스될 수 있다.

**How to apply:** 먼저 빌드 목록의 최신 시각·상태와 현재 배포의 `hasSuccessfulBuild`를 함께 확인한다. 새 빌드가 없으면 코드·DB 런타임 로그를 새 배포 실패 원인으로 단정하지 말고, 새 빌드 생성 여부를 확인한 뒤 재시도 또는 Publishing 인프라 문제로 분류한다.