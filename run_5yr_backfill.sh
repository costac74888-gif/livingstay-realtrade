#!/bin/bash
# 5년치(60개월) 백필 파이프라인: 건물 발굴 → 거래내역 채우기 → 완료 마커
# 모든 단계는 재실행 안전(idempotent): progress 테이블 + ON CONFLICT DO NOTHING.
cd /home/runner/workspace

rm -f /tmp/backfill_5yr_DONE

echo "==================== STEP 1: 건물 발굴 (전국 256개, 60개월) START $(date '+%F %T') ===================="
python -u discover_new_buildings.py --region-offset 0 --region-limit 256 --months 60
echo "==================== STEP 1 DONE $(date '+%F %T') ===================="

echo "==================== STEP 2: 거래내역 채우기 (60개월) START $(date '+%F %T') ===================="
python -u sync_batch.py --months 60
echo "==================== STEP 2 DONE $(date '+%F %T') ===================="

echo "ALL DONE $(date '+%F %T')" | tee /tmp/backfill_5yr_DONE

# 배치 워크플로우가 계속 running 상태로 남지 않도록 종료
