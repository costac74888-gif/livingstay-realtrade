---
name: 숙박 승격 원본 경합 방지
description: 승인된 staging 원본과 운영 승격 사이의 변경 경합 및 커밋 후 재시도 규칙
---

새 숙박 운영 승격은 manifest 생성 당시의 최신 8종 batch와 유효·검토 원본 행 전체를 지문화하고, 승인·dry-run·apply 경계마다 같은 원본인지 확인한다. 실제 운영 쓰기 중에는 staging batch와 row 테이블을 공유 잠금으로 고정해 검증 직후 변경되는 경합도 막는다.

**Why:** manifest payload만 고정하면 승인 뒤 새 batch가 생기거나 기존 source row가 바뀌어도 오래된 승인 내용을 운영에 쓸 수 있다. 반대로 운영 커밋 후 개발 manifest 상태 기록만 실패한 재시도까지 현재 원본 지문으로 막으면 이미 완료된 커밋을 복구할 수 없다.

**How to apply:** 운영 감사 표식이 없는 새 쓰기만 원본 지문 검증과 공유잠금을 요구한다. 같은 manifest key와 run_id의 운영 감사 표식이 이미 있으면 운영 원장을 다시 쓰지 말고 그 기록으로 개발 manifest 상태만 복구한다.