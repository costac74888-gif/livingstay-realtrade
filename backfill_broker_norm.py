# -*- coding: utf-8 -*-
"""기존 broker_registry의 road_norm/jibun_norm을 일괄 채우는 일회성 스크립트."""
from db import get_conn
from addr_norm import normalize_road_prefix, normalize_jibun_prefix


def run():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, road_address, jibun_address FROM broker_registry WHERE road_norm IS NULL")
    rows = cur.fetchall()
    print(f"대상 {len(rows)}건")
    updated = 0
    for r in rows:
        rn = normalize_road_prefix(r["road_address"])
        jn = normalize_jibun_prefix(r["jibun_address"] or r["road_address"])
        if rn or jn:
            cur.execute("UPDATE broker_registry SET road_norm=%s, jibun_norm=%s WHERE id=%s",
                        (rn, jn, r["id"]))
            updated += 1
        if updated % 2000 == 0 and updated:
            conn.commit()
            print(f"  {updated}건 처리...")
    conn.commit()
    print(f"완료: {updated}건 갱신")
    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
