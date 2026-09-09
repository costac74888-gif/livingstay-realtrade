from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    admin = (ROOT / "static/admin.html").read_text(encoding="utf-8")
    required_app = [
        "'presale'::text AS applicant_type",
        "FROM presale_applications pa",
        "WHERE pa.status IN ('submitted', 'reviewing')",
        '"presale": 0',
    ]
    required_admin = [
        "분양사 ${Number(pc.presale) || 0}",
        'r.applicant_type === "presale"',
        "memberPresaleDocument",
        "memberPresaleApprove",
        "memberPresaleReject",
        "분양사 신청은 개별 승인해주세요.",
    ]
    missing = [x for x in required_app if x not in app]
    missing += [x for x in required_admin if x not in admin]
    if missing:
        raise AssertionError(f"분양사 승인대기 통합 누락: {missing}")
    print("presale pending member checks passed")


if __name__ == "__main__":
    main()