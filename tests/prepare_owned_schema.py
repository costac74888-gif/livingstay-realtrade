"""Bootstrap a fresh legacy test database; refuse all real DSNs via startup guard."""
import ast
import os
from pathlib import Path
import psycopg2
from legacy_sample_fixture import seed


def prepare():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "db.py").read_text())
    remaining = [
        n.args[0].value for n in ast.walk(tree)
        if isinstance(n, ast.Call) and n.args
        and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)
        and n.args[0].value.lstrip().startswith("CREATE TABLE IF NOT EXISTS ")
    ]
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            while remaining:
                pending = []
                for sql in remaining:
                    cur.execute("SAVEPOINT prerequisite")
                    try:
                        cur.execute(sql)
                    except psycopg2.errors.UndefinedTable:
                        cur.execute("ROLLBACK TO SAVEPOINT prerequisite")
                        pending.append(sql)
                    cur.execute("RELEASE SAVEPOINT prerequisite")
                if len(pending) == len(remaining):
                    raise RuntimeError("Owned schema dependency cycle")
                remaining = pending
    import db
    db.init_db()
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO master_buildings(building_name,road_address,jibun_address,"
                "sgg_text,sgg_cd,umd_nm,jibun,units,lodging_type,lat,lng) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,20,'생활',%s,%s)",
                [(f"가상 검증 건물 {i}", f"경기도 의정부시 가상검증로 {i}",
                  f"경기도 의정부시 의정부동 {9000+i}", "경기도 의정부시",
                  "41150", "의정부동", str(9000+i),
                  37.5 if i < 35 else 35.16, 127.05 if i < 35 else 129.05)
                 for i in range(40)])
        seed(conn)


if __name__ == "__main__":
    prepare()
