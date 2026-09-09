from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "agent_dashboard.html").read_text(encoding="utf-8")
    lead_api = app[
        app.index("def agent_lead_update_status"):
        app.index("def _agent_buy_requests_data")
    ]

    required_page = [
        '["submitted", "신규"]',
        '["in_progress", "처리중"]',
        '["done", "완료"]',
        'data-lead-act="${status}"',
        'disabled aria-current=\\"true\\"',
    ]
    required_app = [
        '_LEAD_EDITABLE_STATUSES = {"submitted", "in_progress", "done"}',
    ]
    required_api = [
        'old_status != "in_progress" and new_status == "in_progress"',
        'old_status == "in_progress" and new_status != "in_progress"',
        'if row["status"] == "철회됨"',
        "updated_at = NOW()",
    ]
    missing = [token for token in required_page if token not in page]
    missing += [token for token in required_app if token not in app]
    missing += [token for token in required_api if token not in lead_api]
    if missing:
        raise AssertionError(f"중개사 매물의뢰 상태 수정 계약 누락: {missing}")
    if "상태는 순방향(신규→처리중→완료)으로만 변경할 수 있습니다." in lead_api:
        raise AssertionError("매물의뢰 API에 순방향 전용 제한이 남아 있습니다.")
    print("agent listing status edit checks passed")


if __name__ == "__main__":
    main()