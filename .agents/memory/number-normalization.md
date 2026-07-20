---
name: phone/biz-reg number normalization
description: how phone & 사업자등록번호 are stored/displayed across livingstay
---

# 번호 저장·표시 규칙 (전화번호 / 사업자등록번호)

DB에는 **숫자만** 저장한다 (하이픈·공백 제거). 표시할 때만 하이픈 포맷으로 재조립.

**Why:** 입력 폼마다 하이픈 유무가 제각각이라 매칭/검색/엑셀 앞자리 0 손실 문제가 생겼음. 저장을 숫자로 통일하고 표시를 함수로 분리하면 일관성이 유지됨.

**How to apply:**
- 서버: `_digits_only()`로 정규화, `_validate_phone_digits()`(10~11자리)·`_validate_biz_reg_digits()`(10자리)로 검증. 신청 API 3종(agent/operator/loan)과 프로필 PUT(agent/operator/loan me_update) 및 승인 시 본테이블 INSERT 모두 정규화.
- 서버 표시/엑셀: `format_phone()` / `format_biz_reg_number()`. 엑셀은 문자열+`number_format="@"` 로 앞자리 0 보존.
- 프런트: `static/js/format_util.js`의 `window.formatPhone` / `window.formatBizRegNumber` — 표시 지점(admin 그리드, 프로필, 대시보드 fPhone, main.js B화면 카드)에서 재사용. format_util.js는 렌더 스크립트보다 먼저 로드.
- 신청 폼: 제출 전 JS에서 숫자만 남기고 자릿수 검증. 사업자등록번호는 agent/operator 필수, loan은 선택.
- 첨부 필수: agent = 사업자등록증+중개사무소등록증, operator = 사업자등록증. loan은 첨부 없음.
