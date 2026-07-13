# -*- coding: utf-8 -*-
"""
load_authority_contacts.py
──────────────────────────────────────────────────────────────
엑셀 "행정_지자체_담당부서_전화번호.xlsx" (시트 컬럼: 지자체 / 담당부서 / 전화번호)
을 읽어서 lodging_authority_contacts 테이블에 **원본 그대로** 적재한다.

원칙
- 가공하지 않는다. "진주시(중복)" 같은 값도 region_name_raw 에 그대로 넣는다.
- 매칭/정규화는 조회 시점(address_utils)에서만 하고, 저장은 원본 보존.
- 재실행해도 중복이 쌓이지 않도록 적재 전 테이블을 비우고(TRUNCATE) 다시 넣는다.

사용:
    python load_authority_contacts.py [엑셀경로]
경로를 생략하면 attached_assets 안의 "행정_지자체_담당부서_전화번호" 파일을 자동으로 찾는다.
"""

import sys
import glob
import pandas as pd

from db import init_db, get_conn


def find_default_xlsx() -> str:
    hits = sorted(glob.glob("attached_assets/*행정_지자체_담당부서_전화번호*.xlsx"))
    if not hits:
        raise FileNotFoundError(
            "attached_assets 안에서 '행정_지자체_담당부서_전화번호' 엑셀을 찾지 못했습니다. "
            "경로를 직접 인자로 넣어주세요."
        )
    return hits[-1]


def load(xlsx_path: str) -> int:
    df = pd.read_excel(xlsx_path, dtype=str)
    cols = list(df.columns)
    need = ["지자체", "담당부서", "전화번호"]
    for c in need:
        if c not in cols:
            raise ValueError(f"엑셀에 '{c}' 컬럼이 없습니다. 실제 컬럼: {cols}")

    # 원본 보존: strip 정도만(앞뒤 공백/개행), 내부 값은 그대로 둔다.
    rows = []
    for _, r in df.iterrows():
        raw = r["지자체"]
        if raw is None or (isinstance(raw, float)) or str(raw).strip() == "":
            continue  # 지자체명이 빈 행은 건너뜀
        rows.append((
            str(raw).strip(),
            (str(r["담당부서"]).strip() if r["담당부서"] is not None else None),
            (str(r["전화번호"]).strip() if r["전화번호"] is not None else None),
        ))

    init_db()  # 테이블 없으면 생성
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE lodging_authority_contacts RESTART IDENTITY")
    cur.executemany(
        "INSERT INTO lodging_authority_contacts (region_name_raw, dept, phone) VALUES (%s, %s, %s)",
        rows,
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) AS c FROM lodging_authority_contacts")
    total = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return total


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else find_default_xlsx()
    print(f"[load] 엑셀: {path}")
    n = load(path)
    print(f"[load] lodging_authority_contacts 적재 완료: {n}행")
