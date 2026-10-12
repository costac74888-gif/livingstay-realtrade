"""Reproducible preview registry and bundle generation, no services or secrets."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/mockup-sandbox/src/components/mockups/hs2-complete/_screens.json"
NATIVE = {
    "C001": "/hs2/consumer", "C002": "/hs2/details/",
    "C010": "/hs2/workspace/?view=consumer#favorites-section",
    "C011": "/hs2/bookings/", "C014": "/hs2/finance/",
    "C018": "/hs2/workspace/?view=consumer", "C019": "/hs2/workspace/?view=consumer#conversation",
    "C020": "/hs2/workspace/?view=consumer#notifications-section",
    "C025": "/hs2/help/", "C026": "/hs2/help/#faq",
    "O002": "/hs2/owner-map/", "O003": "/hs2/dashboard/",
    "O004": "/hs2/owner-map/?facilities=1",
    "O007": "/hs2/owner-map/?layer=sale", "O008": "/hs2/owner-map/?layer=business",
    "O009": "/hs2/owner-map/?layer=auction",
    "O006": "/hs2/listings/", "O011": "/hs2/registration/",
    "O019": "/hs2/calendar/", "O021": "/hs2/bookings/?view=operator",
    "O023": "/hs2/workspace/?view=operator", "O024": "/hs2/workspace/?view=operator#conversation",
    "O025": "/hs2/dashboard/?view=owner",
    "A001": "/hs2/admin/login", "A002": "/hs2/admin/",
    "A003": "/hs2/listings/admin", "A006": "/hs2/admin/#bookings",
    "A008": "/hs2/admin/#finance", "A010": "/hs2/admin/#faq", "A016": "/hs2/admin/#audit",
}
ALIASES = {
    "L001":"A002","L002":"C011","L003":"O019","L004":"C001",
    "L005":"O003","L006":"C002","L007":"C014","L008":"C025",
    "L009":"A003","L010":"O006","L011":"C023","L012":"O011",
    "L013":"O002","L014":"O023","L017":"A001","L033":"C001",
    "L043":"C023","L052":"C028","L053":"C042","L055":"C027",
}
FLOW = {}
for parent, ids in {
    "C002":["C003","C004","C005","C006","C007","C008","C009","C034","C035","C036","C037","C038"],
    "C001":["C029","C030","C031"],"C011":["C012","C016","C017","C044"],
    "C014":["C015","C043"],"C020":["C039"],"C026":["C040"],
    "C021":["C022","C042"],"C024":["C041"],
    "O006":["O007","O008","O009","O032","O033","O034","O036","O038"],
    "O011":["O012","O013","O014","O015","O016","O017","O018"],
    "O004":["O005","O035"],"O010":["O037"],"O019":["O020"],
    "O021":["O022"],"O025":["O026"],"O027":["O028"],
    "O005":["O029","O030","O031"],"A003":["A004","A005","A023"],
    "A006":["A007"],"A008":["A009"],"A010":["A011"],"A012":["A013"],
    "A014":["A015"],"A016":["A017"],"A018":["A019"],"A020":["A021"],
}.items():
    FLOW.update({id:parent for id in ids})


def main():
    data = json.loads(SOURCE.read_text())
    screens = data["screens"]
    for s in screens:
        s["flow_parent"] = FLOW.get(s["id"],s.get("parent"))
        if s["id"].startswith("L") and s["kind"] != "page":
            s["flow_parent"] = s.get("parent")
        if s["kind"] in {"popup","state","tab"} and s["flow_parent"]:
            s["parent"] = s["flow_parent"]
        s["native"] = s["id"] in NATIVE
        s["alias_of"] = ALIASES.get(s["id"])
        prefix = {"사용자":"/hs2/stays","임대인":"/hs2/owner","관리자":"/hs2/admin/pages"}[s["role"]]
        slug = s["view"].replace("legacy-","")
        if s["id"].startswith("L"):
            slug = Path(s["source_files"][0]).stem + (
                "-"+s["source_token"] if s.get("source_token") else "")
        # ID prevents collisions without showing reviewer controls on the page.
        s["preview_path"] = NATIVE.get(s["id"],f"{prefix}/{slug}-{s['id'].lower()}/")
        s["page_group"] = s["id"] if s["kind"]=="page" else s["flow_parent"]
        s["function_connection"] = "기존 API/원장 동작 보존" if s["native"] else "디자인·로컬 UI 연결만; 기존 운영 원장/계정 미연결"
    by_id={s["id"]:s for s in screens}
    for s in screens:
        if s["alias_of"]:
            s["preview_path"]=by_id[s["alias_of"]]["preview_path"]
            s["native"]=by_id[s["alias_of"]]["native"]
            s["page_group"]=s["alias_of"]
            s["function_connection"]=by_id[s["alias_of"]]["function_connection"] + " · 별칭"
    for s in screens:
        if s["kind"] == "page":
            s["page_group"] = s["preview_path"].split("?")[0].split("#")[0]
        elif s["flow_parent"] in by_id:
            s["page_group"] = by_id[s["flow_parent"]]["preview_path"].split("?")[0].split("#")[0]
    # Alias parent states stay reachable via their own routes, not same-page IDs.
    paths=[s["preview_path"] for s in screens if not s["native"] and not s["alias_of"]]
    assert len(paths)==len(set(paths))
    (ROOT/"scripts/hs2_design_registry.json").write_text(json.dumps({
        "screen_count":len(screens),"screens":screens,"original_rollback_commit":data.get("rollback_commit"),
        "independent_page_groups":len({s["page_group"] for s in screens if s["kind"]=="page"}),
        "alias_count":sum(bool(s["alias_of"]) for s in screens),
        "capture_is_not_function_pass":True,
    },ensure_ascii=False,indent=2))
    assets=ROOT/"scripts/hs2_design_assets"
    font_source=ROOT/"artifacts/mockup-sandbox/public/images/hs2-complete"
    for p in font_source.iterdir():
        if p.suffix==".ttf" or p.name.startswith("OFL"):
            shutil.copyfile(p,assets/p.name)
    subprocess.run([
        str(ROOT/"artifacts/mockup-sandbox/node_modules/.bin/esbuild"),
        str(ROOT/"scripts/hs2_design_frontend.tsx"),"--bundle","--jsx=automatic",
        "--platform=browser","--format=iife","--minify",
        "--external:/__mockup/*",
        f"--alias:react={ROOT/'artifacts/mockup-sandbox/node_modules/react'}",
        f"--alias:react-dom={ROOT/'artifacts/mockup-sandbox/node_modules/react-dom'}",
        f"--outfile={assets/'app.js'}",
    ],check=True,cwd=ROOT)
    # The platform reserves /__mockup for the separately managed canvas
    # service. Running app media must not depend on that service being up.
    bundle = assets/"app.js"
    bundle.write_text(bundle.read_text().replace("/__mockup/images/", "/hs2/design-images/"))
    print(json.dumps({"screens":len(screens),"native_items":sum(s["native"] for s in screens),
                      "aliases":sum(bool(s["alias_of"]) for s in screens)}))


if __name__=="__main__":
    main()
