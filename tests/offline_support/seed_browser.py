"""Synthetic nonempty lists for legacy UI tests (never copied from live DB)."""
from datetime import date
import psycopg2
import os
from auction_schema import ensure_auction_schema


def main():
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        ensure_auction_schema(cur)
        cur.execute("UPDATE master_buildings SET lodging_type_detail='생활숙박시설'")
        cur.execute("SELECT id,road_address,jibun_address FROM master_buildings ORDER BY id LIMIT 25")
        buildings = cur.fetchall()
        for i, (building_id, road, jibun) in enumerate(buildings):
            if 20 <= i < 23:
                road = f"경기도 의정부시 미등록가상로 {i}"
                jibun = f"경기도 의정부시 의정부동 {99900+i}"
            cur.execute("""
                INSERT INTO auction_items(source_item_id,pbct_cdtn_no,title,sale_kind,
                    usage_name,lodging_category,address_road,address_jibun,area_m2,
                    appraisal_price,min_bid_price,min_bid_ratio,round_no,failed_count,
                    bid_start_at,bid_end_at,status,disposal_method,detail_url,
                    master_building_id,lat,lng,raw)
                VALUES(%s,'fixture-round',%s,'압류재산','생활숙박시설','생활숙박',
                    %s,%s,%s,%s,%s,50,2,%s,NOW()-INTERVAL '1 day',
                    NOW()+INTERVAL '14 days'+(%s * INTERVAL '1 day'),
                    'bidding','매각','https://www.onbid.co.kr/fixture',
                    %s,37.5,127.05,
                    jsonb_build_object('list',jsonb_build_object(
                        'cltrMngNo',%s,'prptDivNm','압류재산')))
                RETURNING id
            """, (f"owned-{i}", f"가상 검증 공매 {i}", road, jibun,
                  20 + i, 100000000 + i * 10000000, 50000000 + i * 5000000,
                  i % 4, i, building_id if not 20 <= i < 23 else None, f"FIXTURE-{i:04}"))
            auction_id = cur.fetchone()[0]
            cur.execute("UPDATE auction_items SET detail_fingerprint='owned-synthetic-detail' WHERE id=%s",
                        (auction_id,))
            cur.execute("""INSERT INTO auction_rounds(auction_item_id,round_no,
                bid_start_at,bid_end_at,min_bid_price,result,source_round_key)
                VALUES(%s,2,NOW()-INTERVAL '1 day',NOW()+INTERVAL '14 days',
                    %s,'bidding','current')""", (auction_id, 50000000 + i * 5000000))
            cur.execute("INSERT INTO auction_photos(auction_item_id,url) VALUES(%s,%s)",
                        (auction_id, "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='9'%3E%3Crect width='16' height='9' fill='%23888'/%3E%3C/svg%3E"))
        # A list-only, initially unlinked item exercises the same real address
        # resolver as historical data, using an entirely synthetic property.
        cur.execute("""UPDATE auction_items SET source_item_id='owned-list-only',
            master_building_id=NULL,detail_fingerprint=NULL,
            raw=jsonb_set(raw,'{list,thnlImgUrlAdr}',to_jsonb('https://images.example.invalid/owned.jpg'::text))
            WHERE id=(SELECT min(id) FROM auction_items) RETURNING id""")
        list_only_id = cur.fetchone()[0]
        cur.execute("DELETE FROM auction_photos WHERE auction_item_id=%s", (list_only_id,))
        cur.execute("""INSERT INTO auction_items(source_item_id,pbct_cdtn_no,title,
            sale_kind,usage_name,lodging_category,address_road,address_jibun,area_m2,
            appraisal_price,min_bid_price,min_bid_ratio,round_no,failed_count,
            bid_start_at,bid_end_at,status,disposal_method,detail_url,
            master_building_id,lat,lng,raw,detail_fingerprint)
            SELECT 'owned-scheduled-'||id,'fixture-scheduled',title,
            sale_kind,usage_name,lodging_category,address_road,address_jibun,area_m2,
            appraisal_price,min_bid_price,min_bid_ratio,round_no,failed_count,
            NOW()+INTERVAL '14 days',NOW()+INTERVAL '21 days',
            'scheduled',disposal_method,detail_url,
            master_building_id,lat,lng,raw,'owned-synthetic-detail'
            FROM auction_items""")
        cur.execute("""INSERT INTO auction_photos(auction_item_id,url,sort_order)
            SELECT scheduled.id,photo.url,photo.sort_order
            FROM auction_items original
            JOIN auction_items scheduled
              ON scheduled.source_item_id='owned-scheduled-'||original.id
            JOIN auction_photos photo ON photo.auction_item_id=original.id""")
        cur.executemany("""
            INSERT INTO transactions(master_building_id,building_name,address,
                si_do,sgg_nm,area,price,deal_date,deal_type,sgg_cd,umd_nm,jibun,
                lodging_type,match_source,raw_key)
            VALUES(%s,%s,%s,'경기도','의정부시',25,15000,%s,
                '직거래','41150','의정부동',%s,'생활','master',%s)
        """, [(row[0], f"가상 검증 건물 {i}", row[2], date.today().isoformat(),
               str(9000 + i), f"owned-transaction-{i}") for i, row in enumerate(buildings)])
    print("Nonempty synthetic auctions/transactions ready; no live rows.")


if __name__ == "__main__":
    main()
