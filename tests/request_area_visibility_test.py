from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(source, tokens, label):
    missing = [token for token in tokens if token not in source]
    if missing:
        raise AssertionError(f"{label} 누락: {missing}")


def main():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    main_js = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    agent = (ROOT / "static/agent_dashboard.html").read_text(encoding="utf-8")
    admin = (ROOT / "static/admin.html").read_text(encoding="utf-8")

    require(db, [
        "ALTER TABLE buy_requests ADD COLUMN IF NOT EXISTS area_sqm NUMERIC",
        'SCHEMA_VERSION = "2026-09-09-03"',
    ], "매수의뢰 면적 스키마")
    require(main_js, [
        'id="brAreaSqm"',
        "required placeholder=",
        "전유면적을 ㎡ 단위 숫자로 입력해주세요.",
        "area_sqm: areaSqm",
    ], "매수의뢰 면적 입력")
    require(app, [
        "lr.desired_price, lr.area_sqm, lr.contact_phone",
        "br.desired_price, br.area_sqm, br.contact_phone",
        "monthly_rent_krw, area_sqm)",
        '"전유면적(㎡)"',
    ], "면적 API·엑셀")
    if agent.count("전유면적: <b>") < 2:
        raise AssertionError("중개사 받은 매물·매수의뢰 양쪽에 전유면적이 표시되지 않습니다.")
    if admin.count('{ key: "area_sqm", label: "전유면적"') < 2:
        raise AssertionError("관리자 매물·매수의뢰 양쪽에 전유면적 열이 없습니다.")
    print("request area visibility checks passed")


if __name__ == "__main__":
    main()