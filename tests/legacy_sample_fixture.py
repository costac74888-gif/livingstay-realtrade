"""Public specimen names on fabricated addresses, exclusively in owned test PG."""
import os
from pathlib import Path
from addr_norm import normalize_road_prefix


def seed(conn):
    socket = os.environ.get("HOMENSTAY_LEGACY_SOCKET", "")
    if not socket.startswith("/tmp/homenstay-legacy-pg-") or not Path(socket, ".owned").is_file():
        raise RuntimeError("Specimen fixture requires owned ephemeral database")
    with conn.cursor() as cur:
        # Two eligible regions, not rows copied from a real environment.
        cur.execute(
            "UPDATE master_buildings SET sgg_text=%s,sgg_cd=%s "
            "WHERE building_name LIKE %s AND id>20",
            ("경기도 고양시 덕양구", "41281", "가상 검증 건물 %"))
        for i, (name, kind) in enumerate([
            ("라군 센트럴 스테이", "생활"), ("아이리스모텔", "일반"),
            ("라마다인천호텔", "일반"), ("THE TRINY HOTEL", "일반"),
            ("빌리브패러그라프해운대", "생활"),
        ]):
            road = f"경기도 의정부시 가상표본로 {100 + i}"
            cur.execute(
                "INSERT INTO master_buildings(building_name,road_address,jibun_address,"
                "sgg_text,sgg_cd,umd_nm,jibun,units,lodging_type,lat,lng) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,20,%s,37.5,127.05)",
                (name, road, f"경기도 의정부시 의정부동 {9900+i}",
                 "경기도 의정부시", "41150", "의정부동", str(9900+i), kind))
            rooms = 153 if i == 4 else 20
            cur.execute(
                "INSERT INTO lodging_registry(biz_name,permit_number,road_address,"
                "road_norm,biz_status_name,room_count,hygiene_type) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (name, f"owned-synthetic-permit-{i}", road,
                 normalize_road_prefix(road), "영업/정상", rooms,
                 "숙박업(생활)" if kind == "생활" else
                 "여관업" if i == 1 else "일반호텔"))
            if i == 4:
                cur.execute("UPDATE master_buildings SET units=286 WHERE building_name=%s",
                            (name,))
            if i == 0:
                cur.execute(
                    "INSERT INTO broker_registry(office_name,reg_number,road_address,"
                    "road_norm,biz_status) VALUES(%s,%s,%s,%s,%s)",
                    ("라군부동산중개법인 (가상 표본)", "owned-synthetic-lagoon",
                     road, normalize_road_prefix(road), "영업중"))
    conn.commit()
