"""Build a self-contained, factual Preview preservation/visual review."""
from pathlib import Path
import base64
import json
from html import escape
from io import BytesIO
from PIL import Image
from scripts.hs2_legacy_capabilities import FEATURES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts/seongsu-preview"


def picture(path, crop=None):
    image = Image.open(path).convert("RGB")
    if crop:
        image = image.crop(crop)
    image.thumbnail((1440, 3600))
    data = BytesIO()
    image.save(data, "JPEG", quality=83)
    return "data:image/jpeg;base64," + base64.b64encode(data.getvalue()).decode()


def main():
    reference = ROOT / "attached_assets/ChatGPT_Image_2026년_10월_10일_오후_04_27_31_1791717689116.png"
    sections = []
    for title, crop, pc, phone, difference in [
        ("지도 메인", (0, 0, 420, 683), "review-map-1440.png", "review-map-390.png",
         "유지: 지도 바탕, 사진 목록, 검색창, 우측 단일 도구열, 유형별 가격표식. "
         "수정: 흰색 바탕·검정 글자, 사용자 원본 흑백 로고, 장식 카드 축소, 잘리던 측정/로드뷰 패널 분리. "
         "차이: 실제 성수 지도와 가상 값, 판독 가능한 글자, 기존 기능 미연결표 링크. 실제 기존 건물 원장/실거래는 아직 미연결."),
        ("매물 상세", (426, 0, 735, 683), "review-detail-1440.png", "review-detail-390.png",
         "유지: 사진 왼쪽/예약 오른쪽, 상세 항목과 주변 미니지도. 수정: 실제 SDK 미니지도 연결. "
         "차이: 실제 후기·평점·임대인/카카오톡은 연결하지 않아 가짜로 채우지 않았다. "
         "달력·권리/요금 안내 때문에 세로 길이가 원본보다 길다. 사진 아래 썸네일 배치와 추천매물 열은 원본과 다르다."),
        ("운영자 대시보드", (741, 0, 1024, 683), "review-dashboard-1440.png", "review-dashboard-390.png",
         "유지: 좌측 업무 메뉴와 흰색 본문, 운영 요약·등록·예약 경로. 수정: 기존 핸들러/ID를 보존한 메뉴 재배치와 검정 글자를 위한 밝은 사이드바. "
         "차이: 원본의 30일 매출 그래프/가동률/공지 카드와 메인 등록 프로모션 배치는 미구현. "
         "가상 금융 증빙/권리 안내는 숨기지 않았다. 기존 운영자·파트너·관리자 계정은 연결하지 않았다."),
    ]:
        figures = [
            ("기준 목업", picture(reference, crop)),
            ("현재 개발 PC 1440×1000", picture(OUT / pc)),
            ("현재 개발 모바일 390×874", picture(OUT / phone)),
        ]
        sections.append(f"<section><h2>{title}</h2><p>{difference}</p><div class='comparison'>" +
                        "".join(f"<figure><figcaption>{name}</figcaption><img src='{src}' alt='{name}: {title}'></figure>"
                                for name, src in figures) + "</div></section>")
    rows = "".join(f"<tr><th>{escape(name)}</th><td>{escape(status)}</td><td><code>{escape(route)}</code></td></tr>"
                   for name, route, _, status, _ in FEATURES)
    public = json.loads((OUT / "legacy-public-read-audit.json").read_text())
    audit = "".join(f"<li><code>{escape(r['path'])}</code>: HTTP {r['status']}" +
                    (f", → {escape(r['redirected_path'])}" if r.get("redirected_path") else "") +
                    (f", 반환 {r['returned_records']}건" if "returned_records" in r else "") + "</li>"
                    for r in public["results"])
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HOME & STAY Preview 보존·목업 비교</title>
<style>body{margin:0;background:#fff;color:#171717;font:16px/1.7 sans-serif}
main{max-width:1500px;margin:auto;padding:30px}h1{font-size:30px}h2{font-size:24px;margin-top:40px}
.notice{border:1px solid #ccdaed;background:#f6f9ff;padding:18px;font-weight:600}
.comparison{display:grid;grid-template-columns:.8fr 1.5fr .7fr;gap:18px;align-items:start}
figure{margin:0;border:1px solid #cddcec;padding:12px}figcaption{font-weight:700;margin-bottom:12px}
img{width:100%;height:auto;display:block}table{border-collapse:collapse;width:100%;min-width:750px}
td,th{text-align:left;vertical-align:top;border-bottom:1px solid #dae3ef;padding:12px}
.scroll{overflow:auto}code{font-size:14px}a{color:#171717}
@media(max-width:760px){main{padding:16px}.comparison{grid-template-columns:1fr}}</style></head><body><main>
<h1>HOME & STAY: 기존 기능 보존·원본 목업 비교</h1><p>2026-10-11 · 개발 Preview만 수정</p>
<p>후속 디자인 지시: 사용자 원본 로고 두 종을 사용하고 파란 글자를 검정으로 변경했다.
승인된 딥 올리브 #596044를 주요 버튼·선택 상태에 적용했다.
흑백 로고·검정 글자·경고색·지도 공급자 표기는 유지하며, 입력 기준 목업 이미지 자체는 변경하지 않는다.</p>
<p class="notice">전체 통합은 미완료입니다. 소스 보존 ≠ 기존 기능 연결.
이번 확인은 지도/가상 등록·예약·모의 결제의 개발 동작 검증이며, 실제 계정/원장/토스 연결의 완료 판정이 아닙니다.</p>
<h2>기준 이미지와 이전 누락 원인</h2><p>기준은 지도 검색·매물 상세·운영자 대시보드가 함께 있는
ChatGPT_Image_2026년_10월_10일_오후_04_27_31_1791717689116.png입니다.
로고 3종은 화면 목업으로 취급하지 않았습니다. 이 파일이 최초 승인 원본과 동일한지는 독립적으로 확인하지 못했습니다.</p>
<p>이전 작업은 색상·일부 HTML/CSS 변경을 디자인 복원으로 판단하고, 지도 중심 진입·기존 기능 연결·
세 화면 나란히 검수를 완료 조건으로 적용하지 못했습니다. 따라서 당시 배포 가능한 완전 복제 또는 기능 통합이라고 할 근거는 없습니다.
사용자 요구가 없었던 것이 아니라 작업 범위와 완료 판정의 오류였습니다.</p>
<h2>현재 검증한 범위</h2><ul>
<li>초기 성수동 숙박 7개+비숙박 단기임대 7개, 매매·영업권·공매 각 3개: 23개 가상 좌표/AI 이미지.</li>
<li>실제 카카오 SDK·타일·학교/학원·편의시설·주변 지하철, 원본 지도 전환·거리 초기화.</li>
<li>실제 로드뷰 파노라마 열림(이미지 7개)·기존 로드뷰 미니지도 확인. 물리 iPhone 검증은 아님.</li>
<li>지역/인원/면적/옵션 필터, 마감일 차단, 숙박 1박·비숙박 7일, 주/달력 월 가격.</li>
<li>상세→견적→예약 저장→운영자 승인→금융 조건→동의된 모의 결제→확정 예약: 현재 11개 검사 PASS.</li>
<li>가상 등록 초안→제출→명시적 가상 관리자 선택→승인→새 공개 매물 검색 반영 확인.
신규 등록은 달력 설정이 필요하며 자동 예약 가능 상태로 만들지 않음.</li>
<li>PC/모바일 상세·운영자 화면 실제 SDK 미니지도와 가로 넘침 없음·JS 오류 없음 확인.</li>
</ul><p>전체 과거 19개 검사는 이번에 재실행하지 않았습니다. 픽셀 단위 동일성/실제 토스/운영 로그인·비공개 UI 검증은 하지 않았습니다.</p>
""" + "".join(sections) + """<h2>기존 기능 보존·확장·미연결</h2>
<p>app.py·db.py·기존 static 및 기존 hs2 모듈은 이번 작업 기준 커밋 대비 변경이 없음을 확인했습니다.
새 개발 어댑터의 재사용은 지도 도구/SDK에 국한되며, 아래 미연결 항목의 동작 완료를 의미하지 않습니다.</p>
<div class="scroll"><table><thead><tr><th>기능</th><th>상태</th><th>경로</th></tr></thead><tbody>""" + rows + """</tbody></table></div>
<h2>운영 서비스 읽기 확인</h2><p>공식 배포 정보로 확인한 https://homenstay.com에 익명 GET만 사용했습니다.
로그인·회원 생성·신청·상담·저장·결제·DB 수정·배포 요청은 실행하지 않았습니다.
HTTP 200은 전체 UI/저장 동작 성공의 증거가 아닙니다.</p><ul>""" + audit + """</ul>
<h2>직접 체험</h2><ol><li>Preview /hs2/consumer 또는 /hs2/search/mobile/에서 가상 매물 선택.</li>
<li>/hs2/listings/?new=1에서 가상 정보로 등록. /__development__/seongsu/admin-role에서 확인 후 가상 관리자 700 선택/검토.</li>
<li>기존 승인 매물은 날짜/견적 확인 후 예약 신청→/hs2/bookings/에서 운영자 승인→/hs2/finance/에서 조건 동의/모의 결제.</li>
<li>소비자·운영자 가상 계정 101은 자동 연결, 비밀번호 입력 없음. 다른 체험자와 원장을 공유하고 재시작 시 초기화.</li></ol>
<h2>중단 조건과 미완료</h2><p>현재 임시 fixture 앱에는 기존 서비스의 계정·사업장·건물 원장이 없습니다.
이를 실제 서비스와 동일하다고 표시하거나 운영 앱/자격정보를 격리 실행기에 그대로 넣지 않습니다.
기존 원본 앱 기반의 격리 통합 개발 환경 또는 공개 조회만 연결하는 범위를 확정해야 다음 단계가 가능합니다.</p>
<p>실제 토스 테스트 API/SDK는 미연결이며 OwnedSandbox 모의 처리만 사용합니다.
운영 데이터 쓰기·실제 돈·정산·문자/이메일·운영 배포는 하지 않았습니다.</p></main></body></html>"""
    (OUT / "preservation-review.html").write_text(html)
    print(OUT / "preservation-review.html")


if __name__ == "__main__":
    main()
