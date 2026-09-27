"""관리자 방문자 추이의 일·월·연도 집계 기간과 합계를 확인한다."""

from datetime import date, timedelta

from app import app


def test_admin_visit_trends():
    client = app.test_client()
    assert client.get("/api/admin/stats").status_code == 401
    with client.session_transaction() as session:
        session["admin"] = True

    response = client.get("/api/admin/stats")
    assert response.status_code == 200
    views = response.get_json()["views"]
    daily, monthly, yearly = (views[key] for key in ("daily", "monthly", "yearly"))

    today = date.fromisoformat(daily[-1]["day"])
    assert len(daily) == today.day
    assert [date.fromisoformat(row["day"]) for row in daily] == [
        today.replace(day=1) + timedelta(days=offset) for offset in range(today.day)
    ]
    assert monthly[0]["month"] == min(views["collect_start"][:7], today.strftime("%Y-%m"))
    assert monthly[-1]["month"] == today.strftime("%Y-%m")
    assert [row["month"] for row in monthly] == [
        f"{year}-{month:02d}"
        for year in range(int(monthly[0]["month"][:4]), today.year + 1)
        for month in range(1, 13)
        if monthly[0]["month"] <= f"{year}-{month:02d}" <= monthly[-1]["month"]
    ]
    assert [row["year"] for row in yearly] == [
        str(year) for year in range(int(monthly[0]["month"][:4]), today.year + 1)
    ]
    assert all(isinstance(row["count"], int) and row["count"] >= 0
               for rows in (daily, monthly, yearly) for row in rows)
    assert sum(row["count"] for row in monthly) == sum(row["count"] for row in yearly)
    assert daily[-1]["count"] <= monthly[-1]["count"]


if __name__ == "__main__":
    test_admin_visit_trends()
    print("OK  관리자 방문자 추이 일별·월별·연도별 집계")