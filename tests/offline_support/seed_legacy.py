"""Compatibility labels from old assertions, with synthetic addresses/contacts.

Names alone are not live data: no property/provider/customer rows are copied.
"""
import os
import psycopg2
from psycopg2.extras import Json
from addr_norm import normalize_road_prefix, normalize_jibun_prefix


def seed():
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        # No real settlement details: manual-payment UI tests need only a
        # syntactically complete virtual account. Delivery remains disabled.
        cur.execute("""INSERT INTO app_meta(key,value) VALUES('survey_settings',%s)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""", (Json({
                "bank_name": "가상은행", "bank_account": "00000000000000",
                "bank_holder": "가상검사계좌", "provider_name": "가상검사업체",
                "business_registration": "0000000000",
                "provider_contact": "01000000000", "provider_address": "가상 검증 주소",
            }),))
        # Partner badge tests need two distinct districts with >=12 buildings.
        cur.execute("""UPDATE master_buildings SET sgg_text='부산광역시 해운대구',
            sgg_cd='26350',umd_nm='우동',
            road_address='부산광역시 해운대구 가상검증로 '||id,
            jibun_address='부산광역시 해운대구 우동 '||(9000+id)
            WHERE id>20""")
        for building_id, name, lodging_type in [
            (1, "라군 센트럴 스테이", "생활"),
            (2, "아이리스모텔", "일반"),
            (3, "라마다인천호텔", "일반"),
            (4, "THE TRINY HOTEL", "일반"),
            (5, "빌리브패러그라프해운대", "생활"),
        ]:
            cur.execute("UPDATE master_buildings SET building_name=%s,lodging_type=%s WHERE id=%s",
                        (name, lodging_type, building_id))
        cur.execute("UPDATE master_buildings SET units=286 WHERE id=5")
        for building_id, rooms, hygiene in [
            (2, 12, "여관업"), (3, 50, "관광호텔업"), (4, 40, "관광호텔업"),
            (5, 153, "숙박업(생활)"),
        ]:
            cur.execute("SELECT building_name,road_address,jibun_address FROM master_buildings WHERE id=%s",
                        (building_id,))
            name, road, jibun = cur.fetchone()
            cur.execute("""INSERT INTO lodging_registry(biz_name,permit_number,
                road_address,jibun_address,road_norm,jibun_norm,
                room_count,hygiene_type,biz_status_name,phone)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'영업/정상','01000000000')""",
                        (name, f"OWNED-SYNTHETIC-PERMIT-{building_id}", road, jibun,
                         normalize_road_prefix(road), normalize_jibun_prefix(jibun),
                         rooms, hygiene))
        cur.execute("SELECT road_address FROM master_buildings WHERE id=1")
        road = cur.fetchone()[0]
        cur.execute("""INSERT INTO broker_registry(office_name,reg_number,
            road_address,road_norm,phone,biz_status,source_name)
            VALUES('라군부동산중개법인','owned-compatibility-broker',
                %s,%s,'01000000000','영업중','owned-synthetic-fixture')""",
                    (road, normalize_road_prefix(road)))
    print("Synthetic legacy references: two districts, virtual broker/contact, no live rows.")
