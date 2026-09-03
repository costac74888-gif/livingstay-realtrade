"""운영 permit_number 기준의 정부 숙박 승격 manifest를 개발 DB에 만든다."""

import argparse
import json

from lodging_promotion import create_production_baseline_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--created-by", type=int)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = create_production_baseline_manifest(created_by=args.created_by)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()