---
name: legal docs (terms/privacy) DB-backed CMS
description: How 이용약관/개인정보처리방침 are stored, edited by admin, and served publicly.
---

# 약관/개인정보처리방침 = DB 기반 (관리자 직접 수정)

이용약관·개인정보처리방침은 정적 HTML이 아니라 `legal_documents` 테이블에서 온다.
`doc_type`은 'terms' | 'privacy' 두 값만 사용(앱 레이어 화이트리스트 `_LEGAL_DOC_TYPES`로 검증).

- 공개 조회: `GET /api/legal/<doc_type>` (인증 불필요). `static/terms.html`/`privacy.html`은
  뼈대(헤더/스타일)만 있고 본문은 이 API로 fetch → `#legalBody`에 innerHTML로 주입.
- 관리자: `GET/PUT /api/admin/legal/<doc_type>` (require_admin). PUT은 upsert
  (ON CONFLICT(doc_type) DO UPDATE). admin.html '약관 관리' 메뉴 = 커스텀 섹션
  (DataGrid 아님, showView의 legal 분기 → showLegal). 저장 시 별도 배포 없이 공개 페이지 즉시 반영.
- 시드: `_seed_legal_documents()`가 ON CONFLICT DO NOTHING → **이미 있으면 절대 덮어쓰지 않음**
  (관리자 수정본 보존). 회사명=빌드리머스, 대표=조혜성, "이 약관은 2026년부터 시행합니다."

**신뢰 경계:** 공개 페이지가 content를 innerHTML로 렌더 → 저장 본문은 관리자 신뢰 입력으로 간주.
관리자 계정 탈취까지 방어하려면 저장 시 HTML allowlist sanitizer가 후속 하드닝 포인트(현재 미적용).
