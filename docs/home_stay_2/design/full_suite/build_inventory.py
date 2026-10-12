"""Read-only source inventory; writes only design manifests and generated evidence."""
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "generated-artifacts/hs2-full-design"
GROUP = ROOT / "artifacts/mockup-sandbox/src/components/mockups/hs2-complete"
SOURCES = [*ROOT.glob("*.py"), *ROOT.glob("hs2_*/*.py")]

class SurfaceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.outline = []
        self.capture = None
        self.surface = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.surface = None
        if tag in ("h1","h2","h3","label","th","button"):
            self.capture = tag
        id_ = a.get("id", "")
        if a.get("role") in ("tab", "dialog") or re.search(r"(modal|dialog|popup)$", id_, re.I) or any(k in a for k in ("data-tab", "data-pane", "data-menu", "data-section", "data-panel")):
            token = id_ or a.get("data-tab") or a.get("data-pane") or a.get("data-menu") or a.get("data-section") or a.get("data-panel") or a.get("aria-controls")
            if token:
                self.surface = {"token": token, "kind": "popup" if a.get("role") == "dialog" or re.search(r"modal|dialog|popup", token, re.I) else "tab"}
                self.items.append(self.surface)
    def handle_data(self, data):
        if self.capture:
            text = data.strip()
            if 1 < len(text) < 60 and not any(t in text for t in ("${","{{","http","@","function","const ")):
                self.outline.append(text)
                if self.surface:
                    self.surface["label"] = text
    def handle_endtag(self, tag):
        if tag == self.capture:
            self.capture = None

def routes():
    records = []
    for source in SOURCES:
        try:
            tree = ast.parse(source.read_text())
        except (SyntaxError, UnicodeError):
            continue
        prefix = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Blueprint":
                for k in node.keywords:
                    if k.arg == "url_prefix" and isinstance(k.value, ast.Constant):
                        prefix = k.value.value
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            path_list = []
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "attr", "") in ("route", "get") and d.args and isinstance(d.args[0], ast.Constant):
                    p = d.args[0].value
                    if isinstance(p, str) and not p.startswith("/api"):
                        path_list.append((prefix or "") + p)
            if path_list:
                htmls = sorted({n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[\w./-]+\.html", n.value)})
                for h in htmls:
                    records.append({"source": str(source.relative_to(ROOT)), "html": h, "paths": path_list})
            if source.name=="app.py" and path_list and any(isinstance(n,ast.Call) and getattr(n.func,"id","")=="_serve_app_shell" for n in ast.walk(node)):
                records.append({"source":"app.py","html":"index.html","paths":path_list})
    return records

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    GROUP.mkdir(parents=True, exist_ok=True)
    commit = sys.argv[1] if len(sys.argv)>1 else subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", commit], cwd=ROOT).decode().split("\0")
    protected = {}
    for name in tracked:
        if not name or name.startswith((".agents/", "docs/home_stay_2/design/full_suite/", "artifacts/mockup-sandbox/src/.generated/")):
            continue
        p = ROOT / name
        if p.is_file():
            protected[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT / "baseline.json").write_text(json.dumps({"rollback_commit": commit, "files": protected}, ensure_ascii=False, indent=2))
    route_list = routes()
    inventory = []
    shared_header = ROOT/"static/js/header.js"
    shared_tokens = set(re.findall(r'''id=["']([\w-]*(?:Modal|Dialog|Popup))["']''', shared_header.read_text())) if shared_header.exists() else set()
    for p in sorted([*ROOT.glob("hs2_*/web/*.html"), *ROOT.glob("static/*.html")]):
        text = p.read_text()
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        source = str(p.relative_to(ROOT))
        matches = [r for r in route_list if r["html"] == p.name or r["html"].endswith("/" + p.name)]
        if p.parent.parent.name.startswith("hs2_"):
            matches = [r for r in matches if r["source"].startswith(p.parent.parent.name + "/")]
        paths = sorted({v for r in matches for v in r["paths"]})
        parser = SurfaceParser()
        parser.feed(text)
        surfaces = parser.items
        linked_files=[]
        # Inline-generated tabs/modal identifiers, without executing application scripts.
        for token in re.findall(r'''(?:showTab|switchTab|setTab|openTab)\(\s*['"]([^'"]+)['"]''', text):
            surfaces.append({"token": token, "kind": "tab"})
        for token in re.findall(r'''id=["']([\w-]*(?:Modal|Dialog|Popup))["']''', text):
            surfaces.append({"token": token, "kind": "popup"})
        for token in re.findall(r'''function\s+(open\w*(?:Modal|Dialog|Popup))\s*\(''', text):
            surfaces.append({"token": token, "kind": "popup"})
        for tag in re.findall(r'''<script[^>]+src=["']([^"']+)["']''', text):
            js = ROOT / tag.lstrip("/") if tag.startswith("/static/") else p.parent / tag
            if js.is_file() and js.suffix == ".js":
                if js.name in ("header.js","auth.js") and p.name!="index.html":
                    continue
                js_text = js.read_text()
                linked_files.append(str(js.relative_to(ROOT)))
                for markup in re.findall(r'''<button\b[^>]*(?:data-panel=|data-tab=|data-menu=|role=["']tab)[^>]*>[^<>]{1,100}</button>''',js_text):
                    extracted=SurfaceParser()
                    extracted.feed(markup)
                    surfaces.extend(extracted.items)
                for token in re.findall(r'''id=["']([\w-]*(?:Modal|Dialog|Popup))["']''', js_text):
                    surfaces.append({"token": token, "kind": "popup"})
                for token in re.findall(r'''function\s+(open\w*(?:Modal|Dialog|Popup))\s*\(''', js_text):
                    surfaces.append({"token": token, "kind": "popup"})
                for token in re.findall(r'''data-tab=["']([\w-]+)["']''',js_text):
                    surfaces.append({"token":token,"kind":"tab"})
        # Shared authentication surfaces are source-defined even when HTML injects them later.
        if p.parent.name=="static":
            header = ROOT/"static/js/header.js"
            if header.exists():
                for token in re.findall(r'''id=["']([\w-]*(?:Modal|Dialog|Popup))["']''', header.read_text()):
                    surfaces.append({"token":token,"kind":"popup"})
        merged={}
        for surface in surfaces:
            key=(surface["token"],surface["kind"])
            if key not in merged or surface.get("label"):
                merged[key]=surface
        surfaces=list(merged.values())
        # Shared auth dialogs get one explicit screen, not dozens of identical captures.
        if p.parent.name=="static":
            surfaces = [s for s in surfaces if s["token"] not in shared_tokens or p.name=="index.html"]
        inventory.append({"source": source, "title": re.sub("<[^>]+>", "", title.group(1)).strip() if title else p.stem,
                          "original_paths": paths, "route_verified": bool(paths), "surfaces": surfaces,
                          "linked_files":linked_files,
                          "source_outline":list(dict.fromkeys(parser.outline))[:60]})
    (OUT / "source-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    definitions = {
      "C": ("사용자", [
        ("검색","search"),("물건 상세","detail"),("공유","share","popup"),("전체 사진","gallery","popup"),
        ("소개 더보기","intro","popup"),("편의시설 전체","amenities","popup"),("후기 전체","reviews","popup"),
        ("규칙·취소 정책","policy","popup"),("예약 금액 내역","cost","popup"),("관심 숙소","favorites"),
        ("예약 목록","booking-list"),("예약 상세","booking-detail"),("신청 확인","booking-confirm"),
        ("결제 화면","payment"),("결제 결과","payment-result"),("변경 안내","change"),("취소 안내","cancel"),
        ("채팅 목록","chat-list"),("대화","chat"),("알림","notifications"),("로그인","login"),("가입","signup"),
        ("프로필","profile"),("계정 설정","account"),("도움말","help"),("FAQ","faq"),
        ("이용약관","terms"),("개인정보처리방침","privacy"),("검색 빈 결과","search-empty","state"),
        ("검색 로딩","search-loading","state"),("검색 오류","search-error","state"),("요금 미등록 상세","detail-missing","state"),
        ("월 임대조건 상세","detail-month","state"),("대략 위치 지도","location","popup"),("호스트 정보","host","popup"),
        ("모바일 예약바·예약카드","booking-card","state"),("날짜·인원 선택","date-guests","popup"),
        ("저장 확인","saved","popup"),("알림 상세","notification-detail"),("FAQ 상세","faq-detail"),
        ("계정 탈퇴 안내","account-close","popup"),("비밀번호 재설정","reset-password"),
        ("결제 실패 결과","payment-failed","state"),("예약 목록 빈 상태","booking-empty","state"),
      ]),
      "O": ("임대인", [
        ("임대인 안내","owner-guide"),("시설·4종 운영 지도","owner-map"),("대시보드","dashboard"),
        ("시설 목록","facilities"),("시설 상세","facility-detail"),("매물 목록·단기","listing-stay"),
        ("매물 목록·매매","listing-sale","tab"),("매물 목록·영업권","listing-business","tab"),
        ("매물 목록·공매","listing-auction","tab"),("건물 주소 선택","address"),
        ("등록·기본정보","registration-info"),("등록·사진","registration-photos","tab"),
        ("등록·옵션","registration-options","tab"),("등록·설명","registration-description","tab"),
        ("등록·요금","registration-price","tab"),("등록·미리보기","registration-preview","tab"),
        ("등록·정책 동의","registration-policy","tab"),("등록·제출 상태","registration-status"),
        ("요금 캘린더","rates-calendar"),("예약 캘린더","bookings-calendar","tab"),
        ("예약 관리","owner-bookings"),("예약 승인","booking-approval","popup"),
        ("임대인 대화 목록","owner-chat-list"),("임대인 대화","owner-chat"),
        ("정산·수입","earnings"),("정산 상세","payout-detail"),
        ("사업자 설정","business-settings"),("소유자 설정","owner-settings","tab"),
        ("시설 실거래","transactions"),("시설 데이터랩","datalab","tab"),
        ("건축 정보","building-info","tab"),("매매 상세","sale-detail"),
        ("영업권 상세","business-detail"),("공매 상세","auction-detail"),
        ("시설 추가","facility-add","popup"),("매물 삭제 안내","listing-delete","popup"),
        ("주소 검색 결과","address-results","state"),("임대·매매 조건 미등록","listing-missing","state"),
      ]),
      "A": ("관리자", [
        ("전용 로그인","admin-login"),("관리자 홈","admin-home"),("등록 심사 목록","review-list"),
        ("등록 심사 상세","review-detail"),("심사 처리","review-action","popup"),
        ("예약 원장","booking-ledger"),("예약 원장 상세","ledger-detail"),
        ("금융 원장","finance-ledger"),("금융 원장 상세","finance-detail"),
        ("FAQ 관리","faq-admin"),("FAQ 편집","faq-edit","popup"),
        ("정책 관리","policy-admin"),("정책 편집","policy-edit","popup"),
        ("프로모션 관리","promotion"),("프로모션 편집","promotion-edit","popup"),
        ("감사 기록","audit"),("감사 상세","audit-detail"),
        ("회원 관리","members"),("회원 상세","member-detail"),
        ("사업자 관리","businesses"),("사업자 상세","business-detail"),
        ("관리자 권한 안내","admin-permissions"),("심사 빈 상태","review-empty","state"),
      ]),
    }
    screens = []
    for prefix, (role, entries) in definitions.items():
        for index, values in enumerate(entries, 1):
            title, view, *kind = values
            screens.append({"id": f"{prefix}{index:03}", "role": role, "title": title, "view": view,
              "kind": kind[0] if kind else "page", "parent": f"{prefix}001",
              "basis": "삼삼엠투" if view.startswith("search") else "혼합" if view.startswith(("detail","booking","registration","listing")) else "에어비앤비" if view in ("gallery","amenities","reviews","host","cost","location") else "자체",
              "design_status": "검수 대기", "function_status": "디자인 시안 · 기능 완료 판정 아님",
              "original_paths": [], "source_files": []})
    # Match explicit flows to actual sources (never invent a verified application route).
    hints = {"search":"hs2_supermap","detail":"hs2_details","booking":"hs2_booking","payment":"hs2_booking",
             "owner-map":"hs2_supermap","dashboard":"hs2_dashboard","listing":"hs2_listings",
             "registration":"hs2_registration","calendar":"hs2_calendar","earnings":"hs2_finance",
             "finance":"hs2_finance","admin":"hs2_admin","review":"hs2_admin","ledger":"hs2_admin",
             "help":"hs2_help","faq":"hs2_help","chat":"hs2_workspace","owner-chat":"hs2_workspace"}
    for s in screens:
        matching = [row for key, folder in hints.items()
                    if s["view"]==key or s["view"].startswith(key+"-") or (key=="calendar" and s["view"].endswith("-calendar"))
                    for row in inventory if row["source"].startswith(folder+"/")]
        if s["role"]!="관리자":
            matching=[row for row in matching if not row["source"].endswith("/admin.html")]
        if s["view"] in ("terms","privacy","reset-password"):
            matching += [r for r in inventory if r["source"].endswith("/"+s["view"]+".html")]
        s["original_paths"] = sorted({path for row in matching for path in row["original_paths"]})
        s["source_files"] = sorted({row["source"] for row in matching})
    # Every discovered page, tab and popup receives a separate comparable design surface.
    for idx, row in enumerate(inventory, 1):
        role = "관리자" if "admin" in row["source"] or "review" in row["source"] else "임대인" if any(k in row["source"] for k in ("agent","operator","partner","loan","apply","building","analysis","transactions","auctions","listings","registration","dashboard","calendar","finance","supermap","workspace")) else "사용자"
        rid = f"L{idx:03}"
        screens.append({"id": rid, "role": role, "title": row["title"], "view":"legacy",
          "kind":"page","parent": "A002" if role=="관리자" else "O002" if role=="임대인" else "C001",
          "basis":"자체", "original_paths":row["original_paths"],"source_files":[row["source"],*row["linked_files"]],
          "source_token":"", "design_status":"검수 대기","function_status":"기존 소스 존재 · 연결/권한 동작 미검증"})
        screens[-1]["source_outline"]=row["source_outline"]
        for n, surface in enumerate(row["surfaces"], 1):
            screens.append({"id":f"{rid}S{n:02}", "role":role, "title":row["title"]+" · "+surface.get("label",surface["token"]),
              "view":"legacy-"+surface["kind"],"kind":surface["kind"],"parent":rid,"basis":"자체",
               "original_paths":row["original_paths"],"source_files":[row["source"],*row["linked_files"]],"source_token":surface["token"],
              "design_status":"검수 대기","function_status":"기존 탭/팝업 소스 존재 · 연결 동작 미검증"})
            screens[-1]["source_outline"]=row["source_outline"]
    payload = {"rollback_commit":commit,"screens":screens,"source_inventory":inventory,
               "exclusions":["체험","서비스","공동호스트"],"inventory_limit":"정적 HTML·인라인 함수·연결 JS의 탭/팝업 식별자를 추출. 공통 헤더 팝업은 원본 홈 아래 1회 열거. 로그인 후 서버 데이터로 생성되는 변형은 운영 권한/데이터 미검수."}
    (GROUP / "_screens.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (OUT / "screen-manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"commit":commit,"source_pages":len(inventory),"screens":len(screens),"roles":{r:sum(s["role"]==r for s in screens) for r in ["사용자","임대인","관리자"]}},ensure_ascii=False))

if __name__ == "__main__":
    main()
