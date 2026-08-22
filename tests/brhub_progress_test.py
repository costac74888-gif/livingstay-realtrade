"""기존 bjdong_codes.json 기반 BRHUB 시도별 진행률 회귀 테스트."""
import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
with (ROOT / "bjdong_codes.json").open(encoding="utf-8") as f:
    CODE_DATA = json.load(f)


# app.py import 시 DB 스키마 초기화만 막고, 파일 기반 헬퍼를 실제로 호출한다.
with patch("db.init_db"):
    from app import _brhub_progress_by_sido


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


start = _brhub_progress_by_sido(0)
all_done = _brhub_progress_by_sido(len(CODE_DATA["dongs"]))
expect(len(start) == 17, f"시도별 그룹 수가 17개가 아닙니다: {len(start)}")
expect(sum(row["total"] for row in start) == len(CODE_DATA["dongs"]),
       "시도별 total 합계가 bjdong_codes.json의 법정동 수와 다릅니다.")
expect(all(row["processed"] == 0 for row in start),
       "체크포인트 0에서 처리된 법정동이 표시됩니다.")
expect(all(row["processed"] == row["total"] and row["percent"] == 100
           for row in all_done),
       "전체 법정동 체크포인트에서 시도별 완료율이 100%가 아닙니다.")

first_sido = CODE_DATA["sgg"][CODE_DATA["dongs"][0][0][:5]].split()[0]
at_one = _brhub_progress_by_sido(1)
first_row = next(row for row in at_one if row["sido"] == first_sido)
expect(first_row["processed"] == 1,
       "첫 번째 체크포인트가 해당 시도에 반영되지 않았습니다.")
expect(sum(row["processed"] for row in at_one) == 1,
       "체크포인트 1에서 처리 건수 합계가 1이 아닙니다.")

print("OK  BRHUB bjdong_codes.json 기반 시도별 진행률")