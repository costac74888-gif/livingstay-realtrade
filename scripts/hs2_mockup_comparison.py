"""Build a self-contained comparison from existing synthetic Preview captures."""
import base64
from html import escape
from pathlib import Path
import hashlib
import io
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts/mockup-comparison"
REFERENCE = ROOT / "attached_assets/ChatGPT_Image_2026년_10월_10일_오전_11_47_32_(2)_1791600929106.png"


def data_uri(filename):
    buffer = io.BytesIO()
    with Image.open(filename) as image:
        image.convert("RGB").save(buffer, "JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def figure(title, filename, note=""):
    return (f'<figure><figcaption>{escape(title)}</figcaption>'
            f'<p>{escape(note)}</p><a href="{data_uri(filename)}">'
            f'<img src="{data_uri(filename)}" alt="{escape(title)}"></a></figure>')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sections = [
        "<h2>확인된 참고 이미지 — 최종 승인본 여부 미확인</h2>",
        figure("초기 매물 통합 설계안", REFERENCE,
               "매물 통합 화면의 디자인 방향을 2.0 단기임대 소비자 화면에 적용했습니다."),
        "<h2>소비자 메인 PC · 변경 전/후</h2><div class='pair'>",
        figure("이전 PC — 보관된 역사적 캡처", ROOT / "generated-artifacts/final-preview/desktop.jpg",
               "현재 작업 시작 이전 캡처이며 새 캡처와 화면 크기가 다릅니다. 픽셀 차이율의 기준이 아닙니다."),
        figure("현재 PC — 1440px", OUT / "consumer-desktop.jpg"), "</div>",
        "<h2>소비자 메인 모바일 · 변경 전/후</h2><div class='pair phone'>",
        figure("이전 모바일 — 보관된 역사적 캡처", ROOT / "generated-artifacts/final-preview/mobile.jpg"),
        figure("현재 모바일 — 390px", OUT / "consumer-mobile.jpg"), "</div>",
        "<h2>지도 검색과 상세 화면</h2><div class='pair'>",
        figure("지도 검색 PC — 1440px", OUT / "map-desktop.jpg"),
        figure("상세 PC — 1440px", OUT / "detail-desktop.jpg"), "</div><div class='pair phone'>",
        figure("목록↔지도 검색 모바일 — 390px", OUT / "map-mobile.jpg"),
        figure("상세 모바일 — 390px", OUT / "detail-mobile.jpg"), "</div>",
    ]
    source_sha = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    report = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HOME & STAY 목업 반영 비교</title><style>
body{margin:0;background:#eef4fc;color:#18365f;font:16px/1.7 system-ui,sans-serif}
main{max-width:1300px;margin:auto;padding:28px}h1{font-size:30px}
.notice{padding:18px;border:1px solid #cadbed;background:white;border-radius:8px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}
figure{margin:0 0 24px;padding:14px;background:white;border:1px solid #d4e0ee;border-radius:8px}
figcaption{font-weight:700}img{width:100%;height:auto;display:block}
.phone img{max-width:390px;margin:auto}p{font-size:14px}
code{overflow-wrap:anywhere}@media(max-width:700px){.pair{grid-template-columns:1fr}main{padding:12px}}
</style><main><h1>HOME & STAY 목업 반영 비교</h1>
<p>검수일: 2026-10-11 · 개발용 가상 데이터 Preview · 운영 반영 아님</p>
<div class="notice"><b>기능 검사와 디자인 판정은 별개입니다.</b>
<ul><li>기능 회귀검사: 19/19 PASS, skip 없음. 원본 소스 보존 검사 통과.</li>
<li>디자인 항목 검사: PC 1440px/모바일 390px, 8개 경로·폭 조합 통과.
파란 제목·금색 검색·흰 카드·로고 문구·가로 잘림·상세 3개 이동 링크·모바일 전환 확인.</li>
<li>완전한 목업 일치: 미확인/미완료. 기준 이미지는 화면 설계 보드이며 최종 승인본·정확한 글꼴·사진 원본이 미확인입니다.</li>
<li>사진: 공개 계약에 사진 필드가 없어 비공개 표시를 유지했습니다. 임의 사진·가짜 가격·리뷰를 넣지 않았습니다.</li>
<li>조정: 직거래·중개·공매 상단 탭 대신 2.0 단기임대 중심 및 독립 지도 레이어를 유지.
기간 총액·숙박 1박/비숙박 7일·예약 조건·위치 보호 유지.</li>
<li>지도는 기존 owned SDK 모의 연결입니다. 실제 카카오 지도·토스·발송을 검증한 결과가 아닙니다.</li>
<li>추가 운영 경계 검사: 120초 실행 한도 초과로 미완료, PASS에 포함하지 않았습니다.</li>
<li>아래 JPG는 한글이 표시되는 캡처입니다. 별도 Nix Chromium 자동검사 PNG에는 한글 글꼴이 없는 환경 제약이 있습니다.</li>
</ul></div>"""
    report += f"<p>참고 원본 SHA-256: <code>{source_sha}</code></p>"
    report += "".join(sections) + "</main></html>"
    target = OUT / "mockup-comparison.html"
    target.write_text(report, encoding="utf-8")
    print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
