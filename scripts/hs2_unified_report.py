"""Generate a self-contained, development-only evidence report (ignored output)."""
import base64
import html
import json
from io import BytesIO
from pathlib import Path
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts/unified-preview"


def main():
    visual = json.loads((OUT / "visual-checks.json").read_text())
    flow = json.loads((OUT / "auth-registration.json").read_text())
    assets = json.loads((OUT / "original-assets.json").read_text())
    assert visual["status"] == flow["status"] == assets["status"] == "PASS"
    changed = subprocess.check_output(
        ["git", "diff", "aded9453046d4bd5b701fb168408231752731b46", "--name-only"],
        cwd=ROOT, text=True).splitlines()
    assert not any(p.endswith(".sql") or p in {"db.py", "app.py", "hs2_calendar/engine.py"} for p in changed)
    sections = [
        ("consumer-1440.png", "소비자 PC 1440px", "사진 카드 2열 · 목록 44% / 실제 카카오 지도 56% · 원본 로고 · 추가 필터/기간 버튼 숨김"),
        ("consumer-390.png", "소비자 모바일 390px", "넓은 사진 카드 · 16px 이상 검은 글자 · 문서 가로 넘침 없음 · 기존 지도 도구 유지"),
        ("detail-1440.png", "숙소 상세 PC", "갤러리·기본정보·예약 패널 · 숙박 실제 기준요금 /일 · 유형/개발 상태 박스 숨김"),
        ("detail-390.png", "숙소 상세 모바일", "갤러리와 예약 정보의 단일 열 구성 · 최신 승인 캘린더 기준요금 · 기존 견적 계산 유지"),
        ("owner-1440.png", "임대인 운영 지도", "시설 지도와 숙박·매매·영업권·공매 레이어 유지 · 소비자 숙박 지도와 분리"),
        ("admin-isolated-1440.png", "관리자 화면 — 격리 테스트 계정", "비밀번호 로그인 후 확인한 화면 상단 2,400px. 긴 감사 이력은 원본 PNG에 보존. 운영 관리자 계정 연결이나 운영 권한 부여를 의미하지 않음"),
        ("chat-roundtrip-isolated-390.png", "새 예약의 채팅 왕복 — 격리 테스트", "새 가상 매물에서 예약자 질문 → 임대인 답변 → 예약자 재조회까지 확인. 실제 회원 연결은 별도 미완료"),
    ]
    images = []
    for name, title, description in sections:
        buffer = BytesIO()
        with Image.open(OUT / name) as image:
            if name.startswith("admin-isolated"):
                image = image.crop((0, 0, image.width, min(image.height, 2400)))
            image.convert("RGB").save(buffer, "JPEG", quality=82, optimize=True)
        (OUT / name.replace(".png", ".jpg")).write_bytes(buffer.getvalue())
        data = base64.b64encode(buffer.getvalue()).decode()
        images.append(f'<section><h2>{html.escape(title)}</h2><p>{html.escape(description)}</p>'
                      f'<img alt="{html.escape(title)}" src="data:image/jpeg;base64,{data}"></section>')
    evidence = html.escape(json.dumps({"visual": visual, "flow": flow, "assets": assets}, ensure_ascii=False, indent=2))
    document = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HOME &amp; STAY 통합 Preview 검증</title><style>
body{margin:0;background:#fff;color:#000;font:16px/1.65 system-ui,sans-serif}
main{max-width:1200px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:24px}
section{border-top:1px solid #c8cbbd;padding:24px 0}img{display:block;max-width:100%;height:auto;margin:auto}
.notice{padding:20px;background:#eef0e7;border-left:5px solid #596044}
.gap{background:#f5f0e2;padding:20px;border-left:5px solid #80611f}
table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border:1px solid #d9dbd1}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:16px;background:#f7f8f3;padding:18px}
@media(max-width:600px){main{padding:14px}td,th{padding:7px}}
</style><main><h1>HOME &amp; STAY 통합 Preview 검증</h1>
<p>2026-10-11 · 개발 Preview 전용 · 운영 공개/결제/발송 없음</p>
<div class="notice"><strong>시각·격리 회귀 검사 PASS</strong><br>
실제 카카오 SDK를 HTTPS 개발 주소에서 확인했습니다. 가상 위치/매물이며 실제 숙소·소유자 정보가 아닙니다.
아래 관리·채팅 화면은 운영 계정이 아닌 소유한 임시 DB 테스트에서 촬영했습니다.</div>
<h2>목업 구성 원칙과 구현 비교</h2><table>
<tr><th>기준</th><th>구현/확인</th></tr>
<tr><td>원본 로고·목업의 사진/지도 구조</td><td>원본 로고·아이콘 바이트 동일. PC 사진 2열과 지도 구성 유지, 더 넓은 지도를 위해 44:56 조정.</td></tr>
<tr><td>흰 바탕·검은 글자·올리브/머스타드</td><td>올리브 #596044, 연한 올리브, 숙박 머스타드. 지도 제공자 화면 외 앱 글자 16px 이상·검은색 확인.</td></tr>
<tr><td>요금 표시와 가격 엔진 분리</td><td>비숙박 /주, 숙박 실제 일별 기준요금 /일, 월 요금만 있으면 /월. 없는 요금은 비공개. 박수·달력 월·견적 엔진/DB 스키마 변경 없음.</td></tr>
<tr><td>검색·상세 단순화</td><td>지역·입퇴실일·인원·검색 유지. 추가 필터/유형/기간 버튼은 DOM·기능을 삭제하지 않고 숨김.</td></tr>
<tr><td>관리자 계정 전용</td><td>공개 역할 전환 차단, 익명 직접 접근 403, 비밀번호·CSRF·실패 제한·8시간 만료·로그아웃 확인.</td></tr>
</table><h2>이번 검사 범위</h2><ul>
<li>라이브 개발 Preview: 10개 화면 × 1440px/390px = 20개 화면, 로고/글자/가로 넘침 확인.</li>
<li>원본 로고·아이콘 바이트 동일 검사 PASS. 요금 표시 Node 검사 5건 PASS. 관리자 인증 단위 검사 4건 PASS.</li>
<li>별도 임시 PostgreSQL 통합 회귀 2건 PASS. 운영 DB/토스/이메일/SMS 인증값 없이 실행.</li>
<li>같은 새 가상 매물의 등록→검토 승인→공개→7요일 요금 설정→2박 견적 160,000원→예약→임대인 승인→서명된 모의 결제→채팅 왕복 PASS.</li>
</ul><div class="gap"><strong>미완료/별도 설정</strong><ul>
<li>라이브 Preview 전용 관리자 비밀번호 미설정: 임의 기본 비밀번호나 공개 관리자 역할은 제공하지 않습니다.</li>
<li>기존 운영 회원·사업자·관리자 계정 연결은 완료되지 않았습니다.</li>
<li>실제 토스 상점 승인·취소·환불: <strong>NOT_RUN</strong>. 모의 결제 성공을 실제 토스 검증으로 표시하지 않았습니다.</li>
<li>현재 검사는 Chromium 1440/390 기준이며 물리 iPhone·태블릿·키보드 전용 흐름 전체 검증은 포함하지 않습니다.</li>
<li>로컬 HTTP 스크린샷 도구는 카카오 HTTP 의존 스크립트가 HTTPS-only CSP로 차단됩니다. 아래 지도 증빙은 실제 HTTPS Preview에서 촬영한 것입니다.</li>
</ul></div>""" + "".join(images) + f"<section><h2>기계 판독 증빙</h2><pre>{evidence}</pre></section></main></html>"
    (OUT / "home-stay-unified-report.html").write_text(document, encoding="utf-8")
    print("Self-contained report written:", OUT / "home-stay-unified-report.html")


if __name__ == "__main__":
    main()
