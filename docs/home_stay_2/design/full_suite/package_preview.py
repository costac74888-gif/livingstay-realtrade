"""Package actual running-preview captures; no screenshots synthesized here."""
import csv
import html
import json
import zipfile
import shutil
import re
import ast
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "generated-artifacts/hs2-integrated-preview"
BUNDLE = OUT / "bundle"

def design_review(screen):
    view,kind=screen["view"],screen["kind"]
    if "search" in view or "map" in view:
        return ("사진·요금 목록과 지도 기능을 함께 유지",
                "모바일은 목록/지도 전환이 필요하며 지도는 온라인 SDK에 의존",
                "승인 시안의 검색→목록→상세 흐름을 유지하면서 조작 버튼 겹침을 제거")
    if view in {"detail","detail-month","gallery","property-detail","property-gallery"}:
        return ("사진·기본정보·예약 조건을 단계적으로 확인",
                "긴 상세는 세로 스크롤 필요; 모의 매물의 사진·요금임",
                "승인된 사진 중심 정보 위계를 유지하고 모바일에서는 한 열로 배치")
    if kind in {"popup","state"}:
        return ("주요 흐름에서 세부 입력·결과를 분리해 표시",
                "별도 경로로 표현한 팝업/상태는 독립 페이지나 실제 공급자 결과가 아님",
                "승인된 팝업 구성 유지; 닫기 버튼이 공통 메뉴에 가려지지 않게 조정")
    if any(k in view for k in ("booking","payment","receipt","finance","refund","settlement")):
        return ("예약·금액·처리 상태를 구분해 다음 행동을 찾기 쉽게 표시",
                "개발 가상 원장 또는 로컬 UI이며 실제 토스 승인·취소·환불 검증은 별도",
                "승인된 금액·상태·작업 위계 유지; 넓은 원장은 화면 내부에서 스크롤")
    if any(k in view for k in ("chat","workspace","notification","message")):
        return ("대화·알림과 해당 업무의 이동 링크를 함께 확인",
                "가상 대화·알림이며 실제 회원 계정 연결 및 외부 발송 완료가 아님",
                "승인된 목록/내용 구분을 유지하고 모바일에서는 한 열로 배치")
    if "calendar" in view or "pricing" in view:
        return ("날짜별 요금과 조건을 한 업무 화면에서 확인",
                "일자 표는 작은 화면에서 내부 스크롤 필요; 실제 운영 요금은 아님",
                "승인된 날짜·요금 구성을 유지하며 읽기 가능한 글자 크기 확보")
    if screen["role"]=="관리자":
        return ("역할별 업무 접근과 긴 원장 데이터를 보존",
                "원장은 개발 가상 원장; 넓은 표는 내부 스크롤 필요",
                "서버 인증을 유지하며 정보·원장·작업 순서를 승인 시안 기준으로 구분")
    if screen["role"]=="임대인":
        return ("등록·요금·예약·운영 메뉴를 한 역할 안에서 연결",
                "실제 계정·운영 원장과 연결되지 않은 로컬 UI는 저장 완료가 아님",
                "승인된 업무 구성을 유지하고 작은 화면에서는 조건과 결과를 한 열로 재배치")
    return ("이용자 목적에 맞춘 짧은 정보·입력 흐름",
            "실계정·실결제·운영 저장은 별도 미완료; 자동검수는 최종 사용자 승인이 아님",
            "기존 승인 컴포넌트를 사용하고 공통 메뉴·문자·터치 영역을 실제 Preview에 적용")

def portable_snapshots():
    """Rendered HTML evidence only; never ship executable auth/API controllers."""
    assets=BUNDLE/"page-assets";assets.mkdir(exist_ok=True)
    map_targets={}
    for node in ast.walk(ast.parse((ROOT/"scripts/hs2_real_map_preview.py").read_text())):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="targets" for t in node.targets):
            map_targets=ast.literal_eval(node.value)
    for f in (ROOT/"scripts/hs2_design_assets").iterdir():
        if f.suffix in {".css",".ttf"} or f.name.startswith("OFL"):
            shutil.copyfile(f,assets/f.name)
    for group in ("hs2-unified","hs2-complete"):
        folder=ROOT/"artifacts/mockup-sandbox/public/images"/group
        for f in folder.iterdir():
            if f.suffix in {".jpg",".png",".webp"}:shutil.copyfile(f,assets/(group+"-"+f.name))
    for p in (BUNDLE/"pages").glob("*.html"):
        text=p.read_text()
        def resource(match):
            url=match[1];path=None
            if url.startswith("/hs2/design-assets/"):
                return '../page-assets/'+url.rsplit("/",1)[-1]
            m=re.fullmatch(r"/hs2/design-images/(hs2-unified|hs2-complete)/([^?]+)",url)
            if m:return "../page-assets/"+m[1]+"-"+m[2]
            m=re.fullmatch(r"/__development__/seongsu/assets/(interior-[1-4]\.jpg)",url)
            if m:return "../page-assets/hs2-unified-"+m[1]
            m=re.fullmatch(r"/hs2/([^/]+)/assets/([^?]+\.css)",url)
            if m:path=ROOT/("hs2_"+m[1].replace("-","_"))/"web"/m[2]
            if url.startswith("/__development__/seongsu/map-assets/"):
                name=url.rsplit("/",1)[-1]
                target=map_targets.get(name)
                if target:path=ROOT/target[0]/target[1]
            if path and path.exists():
                name="native-"+path.parent.parent.name+"-"+path.name
                shutil.copyfile(path,assets/name)
                return "../page-assets/"+name
            return url
        text=re.sub(r'(?<=[\"\\\'])(/(?:hs2|__development__)/[^\"\\\']+)(?=[\"\\\'])',lambda m:resource(m),text)
        text=text.replace("</body>",'<script>document.addEventListener("submit",e=>e.preventDefault());document.querySelector("#hs-mobile-menu-toggle")?.addEventListener("click",()=>document.querySelector(".hs-live-header")?.classList.toggle("hs-menu-open"));</script></body>')
        p.write_text(text)
    for p in assets.glob("*.css"):
        p.write_text(p.read_text().replace("/hs2/design-assets/", ""))

def main():
    registry = json.loads((ROOT/"scripts/hs2_design_registry.json").read_text())
    report = json.loads((OUT/"capture-report.json").read_text())
    records = {(r["id"],r["width"]):r for r in report["records"]}
    assert len(records) == 492, "All 246 items need both viewport records"
    rows=[]
    for s in registry["screens"]:
        variants=[records[s["id"],w] for w in (1440,390)]
        passed=all(v["status"]=="기본 화면 검사 통과" for v in variants)
        pros,cons,reason=design_review(s)
        rows.append(dict(id=s["id"],role=s["role"],title=s["title"],kind=s["kind"],
            page_group=s["page_group"],alias_of=s["alias_of"] or "",
            preview_url=report["origin"]+s["preview_path"],
            reflection_status="프리뷰 반영됨",
            visual_status="화면 검수 통과 · 자동 기본검사" if passed else "프리뷰 반영됨 · 보완/미검수",
            functional_scope="기존 개발 API/가상 원장 연결" if s["native"] else "디자인·로컬 UI만; 실제 계정/운영 원장 미연결",
            web=variants[0]["capture"],mobile=variants[1]["capture"],
             web_status=variants[0]["status"],mobile_status=variants[1]["status"],
             advantages=pros,disadvantages=cons,adoption_reason=reason,
              changes="공통 모바일 메뉴·검정 16px 이상 글자·반응형 폭 적용; "
                      +("목록/지도 분리·검색 조건 접기·지도 도구 겹침 개선" if "map" in s["view"] or "search" in s["view"]
                        else "팝업 닫기·폭 개선" if s["kind"] in {"popup","state"}
                        else "컨텐츠 1열 재배치·사진/표/원장 넘침 개선(해당 요소가 있는 화면)"),
             design_sources="; ".join(s.get("source_files") or []),
             html_snapshot=f'pages/{s["id"]}.html'))
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
        "mobile_browser_widths":[390,768,1024,1440],"physical_phone_verified":False,
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
        ws.append(["ID","화면","종류·별칭·페이지군","상태","실제 프리뷰 URL","기능 연결 범위","Desktop 1440","Mobile 390",
                   "장점","단점·주의","채택 이유","변경 내용","원본 시안/기능 소스 경로","HTML 스냅샷"])
        ws.freeze_panes="G2"
        for i,key in enumerate("ABCDEFGH"):
            ws.column_dimensions[key].width=[12,28,36,38,70,60,84,50][i]
        for row in [r for r in rows if r["role"]==role]:
            n=ws.max_row+1
            ws.append([row["id"],row["title"],f'{row["kind"]} / {row["alias_of"] or "-"} / {row["page_group"]}',
                        row["visual_status"],row["preview_url"],row["functional_scope"],None,None,
                        row["advantages"],row["disadvantages"],row["adoption_reason"],row["changes"],
                        row["design_sources"],row["html_snapshot"]])
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
        for col in ("I","J","K","L","M"):ws.column_dimensions[col].width=55
    xlsx=OUT/"homenstay-running-preview-comparison.xlsx"
    temporary_xlsx=xlsx.with_suffix(".tmp.xlsx")
    wb.save(temporary_xlsx);temporary_xlsx.replace(xlsx)
    # Confirm actual embedded image count, not just worksheet row count.
    with zipfile.ZipFile(xlsx) as z:
        image_count=sum(n.startswith("xl/media/") for n in z.namelist())
    cards=[]
    for r in rows:
        cards.append(f'<article id="{r["id"]}"><h2>{r["id"]} · {html.escape(r["title"])}</h2>'
            f'<p>{html.escape(r["role"])} · {r["kind"]} · {html.escape(r["visual_status"])}</p>'
            f'<p>{html.escape(r["functional_scope"])}</p><p><a href="{html.escape(r["preview_url"],quote=True)}">실제 개발 프리뷰 열기</a> · '
            f'<a href="{r["html_snapshot"]}">정적 HTML 검수 자료</a></p>'
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
        "pages/는 실행 서버 DOM에서 인증 토큰·스크립트를 제거한 246개 정적 화면 스냅샷입니다.\n"
        "실행 앱 소스/독립 실행 패키지가 아니며 폼은 실제 저장·결제·발송을 수행하지 않습니다.\n"
        "지도 공급자 타일과 일부 가상 원장 사진은 온라인 주소를 유지합니다. JPG는 모두 포함됩니다.\n"
        "운영 게시·운영 DB 변경·실제 결제·외부 발송은 하지 않았습니다.\n")
    portable_snapshots()
    interaction=OUT/"interaction-report.json"
    if interaction.exists():shutil.copyfile(interaction,BUNDLE/"interaction-report.json")
    archive=OUT/"homenstay-running-preview-captures.zip"
    temporary_archive=archive.with_suffix(".tmp.zip")
    with zipfile.ZipFile(temporary_archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(BUNDLE.rglob("*")):
            if p.is_file():z.write(p,p.relative_to(BUNDLE))
    temporary_archive.replace(archive)
    print(json.dumps({**summary,"excel_embedded_images":image_count,"xlsx_bytes":xlsx.stat().st_size,
                      "zip_bytes":archive.stat().st_size},ensure_ascii=False))


if __name__=="__main__":
    main()
