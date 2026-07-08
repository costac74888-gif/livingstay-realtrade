# -*- coding: utf-8 -*-
"""
migrate_regions.py — 이미 적재된 transactions(76건 등)에 si_do/sgg_nm이 비어있는 경우
                      master_buildings의 sgg_text("경기도 수원시" 형태)로 역채움한다.

DB 스키마에 si_do/sgg_nm 컬럼을 이번에 추가했기 때문에, 이미 쌓인 실거래 데이터는
이 스크립트를 한 번 돌려서 채워줘야 시/군/구 계층 검색이 과거 데이터에도 적용된다.

사용법
------------------------------------------------------------
python db.py               # 컬럼 추가(ALTER TABLE)까지 먼저 실행
python migrate_regions.py  # 그 다음 기존 행 채우기
"""

from db import get_conn


def migrate():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE transactions t
        SET si_do = split_part(m.sgg_text, ' ', 1),
            sgg_nm = split_part(m.sgg_text, ' ', 2)
        FROM master_buildings m
        WHERE t.si_do IS NULL
          AND t.sgg_cd = m.sgg_cd
          AND t.umd_nm = m.umd_nm
          AND t.jibun = m.jibun
    """)
    updated = cur.rowcount
    conn.commit()

    cur.execute("SELECT COUNT(*) c FROM transactions WHERE si_do IS NULL")
    remaining = cur.fetchone()["c"]

    cur.close()
    conn.close()

    print(f"백필 완료: {updated}건 채움 / 여전히 비어있는 행: {remaining}건 (건축HUB 보완 매칭 건 등)")


if __name__ == "__main__":
    migrate()
