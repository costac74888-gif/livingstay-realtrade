# -*- coding: utf-8 -*-
"""
report_authority_match.py
──────────────────────────────────────────────────────────────
lodging_authority_contacts(엑셀 적재본) ↔ master_buildings.sgg_text 매칭을
**DB 반영 없이** 시뮬레이션해서 텍스트 리포트만 출력한다.

- 총 지자체 행 수 / 매칭에 쓰인 서로 다른 시군구 수
- master 476건(고유 sgg_text 기준) 중 몇 개 sgg_text / 몇 건 건물이 매칭됐는지
- 매칭 안 된 master sgg_text 목록(+건물수)
- 매칭에 한 번도 안 쓰인 엑셀 지자체명 목록
- "광주" 특수처리 결과(경기 광주시 vs 광주광역시 각각 몇 건)
"""

from collections import defaultdict

from db import get_conn
from address_utils import (
    build_authority_index,
    match_authority_contact,
    parse_authority_region,
)


def main():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT region_name_raw, dept, phone FROM lodging_authority_contacts ORDER BY id")
    contacts = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT sgg_text, COUNT(*) AS c FROM master_buildings GROUP BY sgg_text ORDER BY sgg_text")
    master = [(r["sgg_text"], r["c"]) for r in cur.fetchall()]
    total_buildings = sum(c for _, c in master)

    cur.close()
    conn.close()

    index = build_authority_index(contacts)

    matched_sgg, unmatched_sgg = [], []
    matched_buildings = 0
    used_raw = set()  # 실제 매칭에 채택된 (dept,phone)

    # 광주 특수처리 추적
    gwangju = {"경기광주시": 0, "광주광역시": 0}

    for sgg, cnt in master:
        dept, phone, how = match_authority_contact(sgg, index)
        if dept is not None:
            matched_sgg.append((sgg, cnt, dept, phone, how))
            matched_buildings += cnt
            used_raw.add((dept, phone))
        else:
            unmatched_sgg.append((sgg, cnt, how))
        # 광주 집계
        if "광주" in sgg:
            if sgg.startswith("경기"):
                gwangju["경기광주시"] += cnt
            else:
                gwangju["광주광역시"] += cnt

    # 매칭에 한 번도 안 쓰인 엑셀 지자체명
    unused_contacts = []
    for c in contacts:
        if (c["dept"], c["phone"]) not in used_raw:
            unused_contacts.append(c["region_name_raw"])

    # ── 출력 ──────────────────────────────────────────────────
    print("=" * 70)
    print("지자체 담당부서 매칭 검증 리포트 (DB 반영 전, 시뮬레이션)")
    print("=" * 70)
    print(f"엑셀 지자체 행: {len(contacts)}개")
    print(f"master 고유 sgg_text: {len(master)}개 / 건물 총 {total_buildings}건")
    print(f"매칭 성공 sgg_text: {len(matched_sgg)}개 / 건물 {matched_buildings}건")
    print(f"매칭 실패 sgg_text: {len(unmatched_sgg)}개 / 건물 {total_buildings - matched_buildings}건")
    print()

    print("── [광주 특수처리 검증] ──")
    print(f"  경기도 광주시  : {gwangju['경기광주시']}건")
    print(f"  광주광역시     : {gwangju['광주광역시']}건  (섞이면 안 됨)")
    for sgg, cnt, dept, phone, how in matched_sgg:
        if "광주" in sgg:
            print(f"    · {sgg!r} ({cnt}건) → {dept} / {phone}  [{how}]")
    for sgg, cnt, how in unmatched_sgg:
        if "광주" in sgg:
            print(f"    · {sgg!r} ({cnt}건) → 확인중 [{how}]")
    print()

    print("── [매칭 실패 = '확인중' 처리될 sgg_text] ──")
    for sgg, cnt, how in sorted(unmatched_sgg, key=lambda x: -x[1]):
        print(f"  {sgg!r} ({cnt}건)  [{how}]")
    print()

    print("── [폴백(시도 대표행)으로 매칭된 sgg_text] ──")
    for sgg, cnt, dept, phone, how in matched_sgg:
        if how.startswith("fallback"):
            print(f"  {sgg!r} ({cnt}건) → {dept} / {phone}  [{how}]")
    print()

    print(f"── [엑셀에 있으나 매칭에 안 쓰인 지자체명: {len(unused_contacts)}개] ──")
    print("  (해당 지역에 등록된 생숙 건물이 없거나, 이름이 안 맞은 경우)")
    for name in unused_contacts:
        s, l = parse_authority_region(name)
        print(f"  {name!r}  → 파싱(시도={s}, 로컬={l!r})")
    print()

    print("── [매칭 성공 전체 목록] ──")
    for sgg, cnt, dept, phone, how in matched_sgg:
        print(f"  {sgg!r} ({cnt}건) → {dept} / {phone}  [{how}]")


if __name__ == "__main__":
    main()
