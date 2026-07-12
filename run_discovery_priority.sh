#!/bin/bash
# 전국 신규건물 발굴 — 관광지(생숙 밀집) 우선 처리 후 전국 나머지.
# 저우선순위(nice 19)로 실행해 다른 작업(빠른 sync 등)에 자원 양보.
# progress 테이블 기록으로 중간에 끊겨도 재실행 시 이어서 진행(재실행 안전).
cd /home/runner/workspace

# 관광지(생숙·리조트 밀집): 부산 해운대/기장, 경기 가평/양평, 충남 태안,
# 경남 통영/거제, 제주 제주/서귀포, 강원 강릉/속초/양양
PRIORITY="26350,26710,41820,41830,44825,48220,48310,50110,50130,51150,51210,51830"

echo "========== 발굴 1순위: 관광지 12개 시군구 START $(date '+%F %T') =========="
nice -n 19 python -u discover_new_buildings.py --sgg "$PRIORITY" --months 60
echo "========== 관광지 우선 발굴 완료 $(date '+%F %T') =========="

echo "========== 발굴 2순위: 전국 나머지 START $(date '+%F %T') =========="
nice -n 19 python -u discover_new_buildings.py --region-offset 0 --region-limit 256 --months 60
echo "========== 전국 발굴 완료 $(date '+%F %T') =========="

echo "DISCOVERY ALL DONE $(date '+%F %T')" | tee /tmp/discovery_ALL_DONE
