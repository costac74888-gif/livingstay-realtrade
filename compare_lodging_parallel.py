#!/usr/bin/env python3
"""적용 완료 숙박 manifest와 기존 직접 동기화 결과를 병행 비교한다."""

import argparse
import json

from lodging_promotion import compare_production_manifest


def main():
    parser = argparse.ArgumentParser(description="숙박 운영 병행 비교")
    parser.add_argument("--manifest-id", type=int)
    args = parser.parse_args()
    result = compare_production_manifest(args.manifest_id)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())