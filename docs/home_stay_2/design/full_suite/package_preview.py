"""Package actual running-preview captures; no screenshots synthesized here."""
import csv
import html
import json
import zipfile
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "generated-artifacts/hs2-integrated-preview"
BUNDLE = OUT / "bundle"


def main():
    registry = json.loads((ROOT/"scripts/hs2_design_registry.json").read_text())
    report = json.loads((OUT/"capture-report.json").read_text())
    records = {(r["id"],r["width"]):r for r in report["records"]}
    assert len(records) == 492, "All 246 items need both viewport records"
    rows=[]
    for s in registry["screens"]:
        variants=[records[s["id"],w] for w in (1440,390)]
        passed=all(v["status"]=="기본 화면 검사 통과" for v in variants)
        rows.append(dict(id=s["id"],role=s["role"],title=s["title"],kind=s["kind"],
            page_group=s["page_group"],alias_of=s["alias_of"] or "",
            preview_url=report["origin"]+s["preview_path"],
            reflection_status="프리뷰 반영됨",
            visual_status="화면 검수 통과 · 자동 기본검사" if passed else "프리뷰 반영됨 · 보완/미검수",
            functional_scope="기존 개발 API/가상 원장 연결" if s["native"] else "디자인·로컬 UI만; 실제 계정/운영 원장 미연결",
            web=variants[0]["capture"],mobile=variants[1]["capture"],
            web_status=variants[0]["status"],mobile_status=variants[1]["status"]))
    with (BUNDLE/"screen-status.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (BUNDLE/"mapping.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    (BUNDLE/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary={
        "mapped_items":246,"independent_page_route_groups":registry["independent_page_groups"],
        "page_definitions":119,"tabs":70,"popups":46,"states":11,"aliases":registry["alias_count"],
        "reflected":246,"visual_basic_pass":sum("검수 통과" in r["visual_status"] for r in rows),
        "visual_unverified_or_issues":sum("검수 통과" not in r["visual_status"] for r in rows),
        "native_api_connected_items_including_aliases":sum(s["native"] for s in registry["screens"]),
        "design_local_only_items_including_aliases":sum(not s["native"] for s in registry["screens"]),
        "admin_capture_authenticated":report["admin_verified"],
        "runtime_errors":len(report["runtimeErrors"]),
        "actual_account_and_toss_completed":False,"published":False,
    }
    (BUNDLE/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    wb=Workbook();overview=wb.active;overview.title="진입·검수 요약"
    for k,v in summary.items():overview.append([k,str(v)])
    overview.append(["소비자",report["origin"]+"/hs2/consumer"])
    overview.append(["임대인",report["origin"]+"/hs2/owner-map/"])
    overview.append(["관리자",report["origin"]+"/hs2/admin/login · preview-admin · 설정된 비밀번호"])
    overview.append(["주의","개발 재시작 시 가상 예약/대화 초기화. 시설은 공개 스냅샷. 실제 계정·토스 검증·운영 승인 완료 아님."])
    overview.column_dimensions["A"].width=50;overview.column_dimensions["B"].width=100
    for role,title in [("사용자","사용자"),("임대인","임대인"),("관리자","관리자")]:
        ws=wb.create_sheet(title)
        ws.append(["ID","화면","종류·별칭·페이지군","상태","실제 프리뷰 URL","기능 연결 범위","Desktop 1440","Mobile 390"])
        ws.freeze_panes="G2"
        for i,key in enumerate("ABCDEFGH"):
            ws.column_dimensions[key].width=[12,28,36,38,70,60,84,50][i]
        for row in [r for r in rows if r["role"]==role]:
            n=ws.max_row+1
            ws.append([row["id"],row["title"],f'{row["kind"]} / {row["alias_of"] or "-"} / {row["page_group"]}',
                       row["visual_status"],row["preview_url"],row["functional_scope"]])
            ws.cell(n,5).hyperlink=row["preview_url"]
            heights=[]
            for col,key,width in [("G","web",580),("H","mobile",330)]:
                p=BUNDLE/row[key]
                if p.exists():
                    image=Image(p);scale=width/image.width
                    image.width=width;image.height*=scale
                    # Excel row limit is 409.5 points; display scaled full
                    # image, while ZIP keeps unscaled full-height capture.
                    if image.height>500:
                        scale=500/image.height;image.width*=scale;image.height=500
                    ws.add_image(image,f"{col}{n}");heights.append(image.height)
                else:ws[f"{col}{n}"]="캡처 미확인"
            ws.row_dimensions[n].height=min(409.5,max(heights or [120])*.75+12)
        for cell in ws[1]:
            cell.fill=PatternFill("solid",fgColor="EDEEDF");cell.font=Font(bold=True,color="000000")
        for row in ws:
            for c in row:c.alignment=Alignment(vertical="top",wrap_text=True)
    xlsx=OUT/"homenstay-running-preview-comparison.xlsx";wb.save(xlsx)
    # Confirm actual embedded image count, not just worksheet row count.
    with zipfile.ZipFile(xlsx) as z:
        image_count=sum(n.startswith("xl/media/") for n in z.namelist())
    cards=[]
    for r in rows:
        cards.append(f'<article id="{r["id"]}"><h2>{r["id"]} · {html.escape(r["title"])}</h2>'
            f'<p>{html.escape(r["role"])} · {r["kind"]} · {html.escape(r["visual_status"])}</p>'
            f'<p>{html.escape(r["functional_scope"])}</p><p><a href="{html.escape(r["preview_url"],quote=True)}">실제 개발 프리뷰 열기</a></p>'
            f'<div class="images"><a href="{r["web"]}"><img src="{r["web"]}" loading="lazy" alt="Desktop 전체 캡처"></a>'
            f'<a href="{r["mobile"]}"><img src="{r["mobile"]}" loading="lazy" alt="Mobile 전체 캡처"></a></div></article>')
    BUNDLE.joinpath("index.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>실제 개발 프리뷰 화면 확인</title><style>body{font:16px/1.7 sans-serif;color:#000;background:white;margin:32px}article{border-top:1px solid #ddd;padding:24px 0}.images{display:grid;grid-template-columns:2fr 1fr;gap:24px}img{width:100%;height:auto}a{color:#000}@media(max-width:650px){.images{grid-template-columns:1fr}}</style>'
        '<h1>HOME &amp; STAY · 실제 개발 프리뷰 캡처</h1>'
        f'<p>246개 대응 항목 · 독립 페이지 경로군 {registry["independent_page_groups"]} · 492개 전체 높이 캡처.</p>'
        '<p>시안 갤러리 캡처가 아닙니다. 링크는 현재 개발 서버의 실제 경로입니다. 기본 자동 화면 검사와 전체 기능 완료는 다릅니다. 사용자 수동 디자인 승인은 별도입니다.</p>'
        '<p>Excel은 별도 제공. CSV/JSON은 각 항목의 반영 상태·화면 검사·기능 범위를 기록합니다. 관리자 실제 페이지는 로그인해야 열립니다.</p>'
        +''.join(cards)+'</html>')
    BUNDLE.joinpath("README.txt").write_text(
        "현재 실행 중인 owned 개발 Preview 캡처입니다. index.html은 캡처 확인용이며 실행 앱은 preview_url로 엽니다.\n"
        "246은 독립 페이지 수가 아닙니다. 별칭/탭/팝업/상태는 CSV와 mapping.json 참조.\n"
        "모든 화면은 프리뷰 반영, 자동 기본검사 통과/보완은 별도입니다. 실제 계정/실결제/운영 승인은 완료로 판정하지 않습니다.\n"
        "각 JPG는 전체 높이 캡처. Excel에는 전체 이미지가 축소 삽입되며 원본 JPG는 ZIP에 있습니다.\n"
        "관리자: /hs2/admin/login, 계정 preview-admin, 기존 설정된 비밀번호. 비밀번호/세션은 패키지에 없습니다.\n"
        "운영 게시·운영 DB 변경·실제 결제·외부 발송은 하지 않았습니다.\n")
    archive=OUT/"homenstay-running-preview-captures.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(BUNDLE.rglob("*")):
            if p.is_file():z.write(p,p.relative_to(BUNDLE))
    print(json.dumps({**summary,"excel_embedded_images":image_count,"xlsx_bytes":xlsx.stat().st_size,
                      "zip_bytes":archive.stat().st_size},ensure_ascii=False))


if __name__=="__main__":
    main()
