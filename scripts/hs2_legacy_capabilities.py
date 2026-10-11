"""Honest legacy-vs-Preview inventory. No production adapters or credentials."""
from pathlib import Path
from flask import jsonify, Response
from html import escape

ROOT = Path(__file__).resolve().parents[1]
# "Source retained" never means the production account/data is wired to fixtures.
FEATURES = [
    ("실거래가 조회·목록", "/transactions", "app.py", "기존 원본 유지 · Preview 미연결", None),
    ("숙박시설 정보·공적 업종 분류·통계", "/", "static/js/main.js", "기존 원본 유지 · Preview 미연결", None),
    ("기존 건물 지도 검색·지역·업종 필터", "/", "static/js/main.js", "기존 원본 유지 · 실제 건물 원장 미연결", None),
    ("지도전환·확대축소·로드뷰·거리 측정", "/", "static/js/main.js", "기존 도구 재사용 · 실제 SDK", "/hs2/consumer"),
    ("학교·학원·편의시설", "/", "static/js/main.js", "기존 도구 재사용 · 실제 Places 조회", "/hs2/consumer"),
    ("관광 데이터랩·관광지 순위", "/", "static/js/main.js", "기존 원본 유지 · Preview 미연결", None),
    ("기존 직거래·중개 매물·영업권 양도", "/listings", "app.py", "기존 원본 유지 · 기존 원장 미연결", None),
    ("기존 온비드 공매·세부정보", "/auctions", "static/js/main.js", "기존 원본 유지 · 실제 공매 원장 미연결", None),
    ("관심단지·거래동향·새 거래 알림", "/mypage", "app.py", "기존 원본 유지 · 계정/원장 미연결", None),
    ("숙박자산·운영·투자 분석", "/analysis", "app.py", "기존 원본 유지 · Preview 미연결", None),
    ("중개·대출·운영 상담·매수/매물 의뢰", "/partner", "app.py", "기존 원본 유지 · 실제 접수 미연결", None),
    ("기존 운영자·파트너·관리자 기능", "/admin", "app.py", "기존 원본 유지 · 운영 계정 미연결", None),
    ("기존 로그인·전화 인증·카카오 로그인", "/mypage", "static/js/auth.js", "기존 원본 유지 · 실제 인증 미연결", None),
    ("2.0 단기임대·매매·양도·공매 탐색", "/hs2/consumer", "scripts/hs2_real_map.js", "확장 · 가상 23개/실제 지도", "/hs2/consumer"),
    ("2.0 매물 등록·검토", "/hs2/listings/", "hs2_listings/api.py", "확장 · 격리 가상 원장", "/hs2/listings/?new=1"),
    ("2.0 상세·달력·예약", "/hs2/calendar/", "hs2_details/web/detail.js", "확장 · 격리 가상 원장", "/hs2/calendar/"),
    ("2.0 관심 숙소·문의·채팅·알림", "/hs2/workspace/", "hs2_workspace/api.py", "확장 · 격리 가상 원장 (관심단지 대체 아님)", "/hs2/workspace/"),
    ("2.0 내 예약·운영 대시보드", "/hs2/dashboard/", "hs2_dashboard/web/dashboard.html", "확장 · 격리 가상 원장", "/hs2/dashboard/"),
    ("2.0 결제·금융 검토", "/hs2/finance/", "scripts/hs2_seongsu_preview.py", "모의 결제만 · 실제 토스 테스트 미연결", "/hs2/finance/"),
]


def install(app):
    from scripts.hs2_seongsu_seed import require_owned
    require_owned(app)

    def records():
        return [dict(name=name, original_route=route, source=source,
                     source_exists=(ROOT / source).is_file(), status=status,
                     preview_route=preview)
                for name, route, source, status, preview in FEATURES]

    @app.get("/__development__/legacy-capabilities.json")
    def capabilities_json():
        return jsonify(ok=True, overall="INCOMPLETE",
                       production_accounts_connected=False, actual_toss=False,
                       source_retention_is_not_integration=True, items=records())

    @app.get("/__development__/legacy-capabilities/")
    def capabilities_page():
        rows = []
        for row in records():
            link = (f'<a href="{escape(row["preview_route"], quote=True)}">개발 체험</a>'
                    if row["preview_route"] else "미연결 — 운영 계정/원장 연결 필요")
            rows.append(f'<tr><th>{escape(row["name"])}</th><td>{escape(row["status"])}</td>'
                        f'<td>{link}</td><td><code>{escape(row["original_route"])}</code></td></tr>')
        return Response("""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>기존 기능 보존·연결표</title>
<style>body{background:white;color:#173e72;font:16px/1.65 "Noto Sans KR",sans-serif;margin:0}
main{max-width:1200px;margin:auto;padding:24px}a{color:#075bff}h1{font-size:28px}
.scroll{overflow:auto}table{border-collapse:collapse;min-width:760px;width:100%}
th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #dce5ef}
th{width:26%}.notice{padding:16px;border:1px solid #cddcec;font-weight:600}code{font-size:14px}</style>
</head><body><main><a href="/hs2/consumer">← 실제 지도 메인</a>
<h1>기존 기능 보존·Preview 연결표</h1>
<p class="notice">전체 통합은 미완료입니다. 기존 소스가 남아 있다는 사실과 개발 Preview 연결은 다릅니다.
가상 단기임대·관심 숙소·문의는 기존 실거래·관심단지·상담 기능의 대체물이 아닙니다.</p>
<p>운영 공개 화면·실거래 API는 익명 GET으로 확인했습니다. 운영 로그인·등록·상담·결제·저장 동작은 실행하지 않았습니다.
개발 원장은 가상 계정 101을 공유하며 비밀번호 입력 없이 접속합니다. 운영 인증이 아닙니다.</p>
<div class="scroll"><table><thead><tr><th>기능</th><th>유지/확장/미연결</th><th>Preview 연결</th><th>기존/확장 경로</th></tr></thead><tbody>
""" + "".join(rows) + """</tbody></table></div>
<h2>직접 체험 순서</h2><ol>
<li>지도 메인에서 성수동 가상 물건 선택 → 상세·기간 견적 확인.</li>
<li><a href="/hs2/listings/?new=1">가상 등록 신청</a>: 가상 정보를 입력하고 저장·제출.
관리자 검토 전에는 검색 공개/예약 대상이 되지 않습니다.
<a href="/__development__/seongsu/admin-role">가상 관리자 역할 선택</a> 후 가상 신청을 검토할 수 있습니다.</li>
<li><a href="/hs2/calendar/">달력</a>에서 기존 승인 가상 매물의 요금·마감일 확인.</li>
<li>메인에 있는 승인된 가상 매물로 돌아가 기간 선택 → 예약 신청.</li>
<li><a href="/hs2/bookings/">운영자 예약 화면</a>에서 승인 → 금융 화면에서 약관 확인.</li>
<li>모의 결제 동의 체크 → 모의 결제 → 내 예약/운영 대시보드 확인.
실제 토스 테스트·실제 돈·발송·운영 계정과 무관합니다.</li></ol>
<p>운영 서비스의 비공개 계정/권한·원장과 이 fixture 앱을 안전하게 연결하는 경계가 아직 없습니다.
이를 확인하지 않고 운영 앱을 이 격리 실행기에 import하거나 운영 인증을 가상 로그인으로 대체하지 않습니다.</p>
</main></body></html>""", mimetype="text/html")
