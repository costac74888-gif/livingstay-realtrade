---
name: Publish 사전 실패 구분
description: Republish 실패 화면과 실제 빌드·프로모트·런타임 실패를 구분하는 기준
---

Republish 화면에 `Failed`가 표시되어도 `listDeploymentBuilds`에 새 failed/building 항목이 없고, `getDeploymentInfo`가 이전 성공 빌드를 계속 가리키면 배포 산출물 단계에 도달하기 전 요청이 실패한 것으로 판단한다.

**Why:** 빌드 단계 실패는 항상 빌드 ID와 빌드 로그가 남지만, 배포 요청·Publishing 제어 단계에서 실패하면 화면만 실패로 바뀌고 이전 성공 배포가 계속 서비스될 수 있다.

**How to apply:** 먼저 빌드 목록의 최신 시각·상태와 현재 배포의 `hasSuccessfulBuild`를 함께 확인한다. 새 빌드가 없으면 코드·DB 런타임 로그를 새 배포 실패 원인으로 단정하지 말고, 새 빌드 생성 여부를 확인한 뒤 재시도 또는 Publishing 인프라 문제로 분류한다.

빌드·보안검사는 성공했지만 로그가 `Pushing nix-0 layer...`에서 장시간 끊기고 실패하면 앱 코드나 DB Secret보다 Nix 이미지 레이어 구성을 먼저 의심한다.

**Why:** 사용하지 않는 Nix 패키지 하나만 추가되어도 캐시되지 않은 별도 레이어 업로드가 생기며, Publishing이 명시적 오류 없이 시간 초과할 수 있다.

**How to apply:** Python wheel이 필요한 네이티브 라이브러리를 자체 포함하는지 실제 기능으로 확인한 뒤 중복 시스템 패키지를 제거한다. 남은 Nix 패키지도 코드·런타임에서 쓰지 않으면 비워 레이어 자체를 없앤다.