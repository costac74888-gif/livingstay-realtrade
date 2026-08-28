# -*- coding: utf-8 -*-
"""회원관리 열 순서와 대출상담사 신청 필드의 정적 계약 검사."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def run():
    failures = []
    admin = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
    form = (ROOT / "static" / "apply_loan_consultant.html").read_text(encoding="utf-8")
    edit_form = (ROOT / "static" / "apply_edit.html").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    member_start = admin.find('<table class="dg-table">', admin.find("async function loadMembers"))
    member_end = admin.find("</table>", member_start)
    member_table = admin[member_start:member_end]
    ordered_headers = ["작업", "태그", "메모", "포인트", "광고", "가입일시", "가입경로", "승인일", "오픈링크"]
    positions = [member_table.find(f">{label}<") for label in ordered_headers]
    if member_start < 0 or any(pos < 0 for pos in positions) or positions != sorted(positions):
        failures.append("회원관리의 관리열·가입정보·오픈링크 순서가 잘못됨")
    if "memberApplicationDetail(${r.id})" not in admin:
        failures.append("승인대기 행에 유형별 신청 상세 버튼이 없음")
    if "지역뱃지 ${Number(r.region_badge_count)||0}/${Number(r.region_badge_limit)||1}" not in admin:
        failures.append("파트너 지역뱃지가 1인당 숫자 한도로 표시되지 않음")

    if 'id="kakao_chat_url"' not in form:
        failures.append("대출상담사 신청서에 카카오톡 상담 링크 입력란이 없음")
    for removed_id in ('id="biz_reg_number"', 'id="office_address"', 'id="office_address_detail"'):
        if removed_id in form:
            failures.append(f"대출상담사 신청서에 제거 대상 필드가 남아 있음: {removed_id}")
    if "openAddressSearch" in form:
        failures.append("대출상담사 신청서에 제거된 주소검색 코드가 남아 있음")
    if 'id="kakao_chat_url"' not in edit_form or 'id="biz_reg_number_loan"' in edit_form:
        failures.append("대출상담사 신청 수정 화면이 카카오톡 링크 필드와 일치하지 않음")

    required_server_fragments = (
        "parsed.hostname == \"open.kakao.com\"",
        "preferred_region, kakao_chat_url, edit_token, password_hash",
        "service_region, office_address, kakao_chat_url",
        "region_badge_limit",
    )
    for fragment in required_server_fragments:
        if fragment not in app_source:
            failures.append(f"서버 신청·승인 계약 누락: {fragment}")

    if failures:
        print("회원관리·대출상담사 계약 검사 실패:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("OK  회원관리 열 순서·지역뱃지·대출상담사 신청 필드")
    return 0


if __name__ == "__main__":
    sys.exit(run())