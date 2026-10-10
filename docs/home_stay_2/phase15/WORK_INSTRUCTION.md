# Phase15 내부 Work 실행 지시

Phase14 COMPLETE·전체49개 PASS·개발 원격 해시 확인 뒤 진행한다.
기존 admin_users 로그인/session["admin"]·admin_user_id 및 관리자 메뉴를
대체하지 않는다. 신규 관리자 API는 같은 trusted admin resolver와 CSRF를
사용하며 client user/admin ID를 권한으로 받지 않는다.

등록 승인/거절은 기존 검토 엔진을 호출한다. 등록/가격·예약/결제·환불/
보증금/지급 원장을 실제 SQL로 조회하고 원장을 수정하거나 실제 돈을
실행하지 않는다. 프로모션/신고/리뷰 검토 기록·FAQ·금융 정책을
draft→approve/archive·차수 검증·감사 이력으로 관리한다.
FAQ는 stable topic 범위를 지키며 승인본만 개발 공개 안내에 반영한다.
초기 플랫폼0% 유지, PG/보증금/반환기간은 명시 확인한 개발 조건만
적용하며 기존 계약 조건은 불변이다. production/live gate는 닫는다.

SQL/API·실제 desktop/mobile CRUD/검토/오류/인증·전체 registry·검토·GitHub
순서로 확인하고 Phase16으로 간다.
