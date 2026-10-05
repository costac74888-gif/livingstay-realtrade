"""Bounded on-demand register lookup. No operating-permit inference or bulk sync.

app_meta holds cross-worker admission, cooldowns and fenced status. External
requests run in a detached child; neither HTTP requests nor DB leases wait on API.
"""
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from address_utils import BjdongMap, normalize_umd_nm, parse_jibun
from addr_norm import normalize_jibun_prefix, normalize_road_prefix, _normalize_region_prefix
from auction_building_matching import build_indexes, choose_building
from auction_domain import ELIGIBLE_SQL
from db import get_conn

PREFIX = "auction_building_lookup:"
CLAIM_LOCK = 74109326
MAX_RUNNING = 2
MAX_DAILY = 200  # Application admission budget, NOT an assumed provider quota.
MESSAGES = {
    "running": "건축물대장을 우선 조회 중입니다. 확인되면 화면이 자동 갱신됩니다.",
    "done": "건축물대장 확인 및 건물 연결이 완료되었습니다.",
    "empty": "해당 주소의 건축물대장 자료를 찾지 못했습니다.",
    "ambiguous": "주소 또는 동별 후보가 여러 개이거나 서로 달라 자동 연결하지 않았습니다.",
    "address_required": "조회에 필요한 정확한 지번주소를 확인하지 못했습니다.",
    "failed": "건축물대장 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    "busy": "다른 우선 조회를 처리 중입니다. 잠시 후 다시 시도해 주세요.",
    "quota": "오늘의 우선 조회 처리 한도에 도달했습니다.",
    "idle": "건축물대장 우선 조회를 시작할 수 있습니다.",
}

def _historical_parcel(address, code_map):
    """Onbid may retain a pre-reorganization district name. Exact full-name only."""
    match = re.search(r"\s+(산\s*)?(\d{1,4})(?:-(\d{1,4}))?(?=\s|,|\(|$)", address)
    if not match:
        return None
    key = normalize_jibun_prefix(address)
    path = BjdongMap._resolve_path(os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip"))
    if not hasattr(code_map, "_auction_historical_rows"):
        with open(path, encoding="cp949", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        code_map._auction_historical_rows = rows
    rows = code_map._auction_historical_rows
    regions = {r["법정동코드"][:5]: r["법정동명"]
               for r in rows if r.get("법정동코드", "").endswith("00000")}
    jibun = ("산 " if match[1] else "") + match[2] + (
        "-" + match[3] if match[3] and int(match[3]) else "")
    candidates = {}
    for row in rows:
        code, name = row.get("법정동코드", ""), row.get("법정동명", "")
        if len(code) != 10 or code[5:] == "00000" or code[:5] not in regions:
            continue
        if normalize_jibun_prefix(name + " " + jibun) == key:
            region = regions[code[:5]]
            if not name.startswith(region + " "):
                continue
            candidates[code] = {"sgg_cd": code[:5], "bjd": code[5:], "sgg_text": region,
                                "umd_nm": normalize_umd_nm(name[len(region):]),
                                "jibun": jibun}
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def status(cur, item_id):
    cur.execute("""SELECT value, updated_at < NOW() - INTERVAL '3 minutes' AS stale
      FROM app_meta WHERE key=%s""", [PREFIX + str(item_id)])
    row = cur.fetchone()
    value = json.loads(row["value"]) if row else {"state": "idle"}
    if value.get("state") == "running" and row["stale"]:
        value = {"state": "failed"}
    if value.get("state") == "done":
        cur.execute("SELECT master_building_id FROM auction_items WHERE id=%s", [item_id])
        linked = cur.fetchone()
        if not linked or not linked["master_building_id"]:
            value = {"state": "idle"}
    state = value.get("state", "idle")
    return {"state": state, "message": MESSAGES.get(state, MESSAGES["failed"]),
            "building_id": value.get("building_id")}


def _finish(cur, item_id, run_id, state, building_id=None):
    cur.execute("""UPDATE app_meta SET value=%s,updated_at=NOW()
      WHERE key=%s AND value::jsonb->>'run_id'=%s""",
                [json.dumps({"run_id": run_id, "state": state, "building_id": building_id}),
                 PREFIX + str(item_id), run_id])


def start_lookup(item_id):
    """Atomically deduplicate, bound global concurrency/day and spawn one child."""
    run_id = uuid.uuid4().hex
    key = PREFIX + str(item_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", [CLAIM_LOCK])
            if not cur.fetchone()["acquired"]:
                return {"state": "busy", "message": MESSAGES["busy"]}
            previous = status(cur, item_id)
            cur.execute("""SELECT updated_at > NOW() - %s * INTERVAL '1 second' AS recent
              FROM app_meta WHERE key=%s""",
                        [60 if previous["state"] == "failed" else 600, key])
            row = cur.fetchone()
            if previous["state"] == "running" or (
                    row and row["recent"] and previous["state"] != "idle"):
                return previous
            cur.execute("""SELECT COUNT(*) AS n FROM app_meta WHERE key LIKE %s
              AND value::jsonb->>'state'='running'
              AND updated_at > NOW() - INTERVAL '3 minutes'""", [PREFIX + "%"])
            if cur.fetchone()["n"] >= MAX_RUNNING:
                return {"state": "busy", "message": MESSAGES["busy"]}
            cur.execute("SELECT 'auction_lookup_budget:' || CURRENT_DATE::text AS key")
            budget_key = cur.fetchone()["key"]
            cur.execute("SELECT value FROM app_meta WHERE key=%s", [budget_key])
            budget = cur.fetchone()
            used = int(budget["value"]) if budget else 0
            if used >= MAX_DAILY:
                return {"state": "quota", "message": MESSAGES["quota"]}
            cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
              ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",
                        [budget_key, str(used + 1)])
            cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
              ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",
                        [key, json.dumps({"state": "running", "run_id": run_id})])
        conn.commit()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).resolve()), "--item-id", str(item_id),
             "--run-id", run_id], cwd=str(Path(__file__).resolve().parent),
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=proc.wait, daemon=True).start()
    except Exception:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _finish(cur, item_id, run_id, "failed")
            conn.commit()
        return {"state": "failed", "message": MESSAGES["failed"]}
    return {"state": "running", "message": MESSAGES["running"]}


def parcel_identity(item, code_map):
    """Use full official parcel strings only; never select the first fuzzy result."""
    text = " ".join(str(item.get(k) or "") for k in ("address_jibun", "address_road", "title"))
    if re.search(r"외\s*\d+\s*필지|,\s*\d+(?:-\d+)?(?:\s|$)", text):
        return None
    identities = {}
    for field in ("address_jibun", "title"):
        address = str(item.get(field) or "")
        if not normalize_jibun_prefix(address):
            continue
        region = code_map.extract_sgg_from_address(address)
        match = re.search(r"((?:[가-힣0-9]+(?:읍|면)\s+)?[가-힣0-9]+(?:동|읍|면|리|가))\s+(산\s*)?(\d{1,4})(?:-(\d{1,4}))?(?=\s|,|\(|$)", address)
        if not region or not match:
            historical = _historical_parcel(address, code_map)
            if historical:
                identities[(historical["sgg_cd"], historical["bjd"],
                            *parse_jibun(historical["jibun"]))] = historical
            continue
        sgg = region[2]
        umd = match[1]
        bjd = code_map.find_bjdong_cd(sgg, umd)
        if not bjd:
            historical = _historical_parcel(address, code_map)
            if historical:
                identities[(historical["sgg_cd"], historical["bjd"],
                            *parse_jibun(historical["jibun"]))] = historical
            continue
        jibun = ("산 " if match[2] else "") + match[3] + (
            "-" + match[4] if match[4] and int(match[4]) else "")
        identities[(sgg, bjd, *parse_jibun(jibun))] = {
            "sgg_cd": sgg, "bjd": bjd, "sgg_text": code_map.sgg_text(sgg),
            "umd_nm": normalize_umd_nm(umd), "jibun": jibun,
        }
    return next(iter(identities.values())) if len(identities) == 1 else None


def query_identities(identity, code_map):
    """A retired district can map only to one current full dong in the same city."""
    if identity["sgg_cd"] in code_map._sgg_text_map:
        return [identity]
    province = identity["sgg_text"].split()[0]
    candidates = {}
    for code, name, sgg, bjd in code_map._rows:
        region = code_map.sgg_text(sgg)
        if not region or region.split()[0] != province or not name.startswith(region + " "):
            continue
        if normalize_umd_nm(name[len(region):]) == identity["umd_nm"]:
            candidates[code] = {
                **identity, "sgg_cd": sgg, "bjd": bjd, "sgg_text": region,
                "_source_sgg_text": identity["sgg_text"], "_source_sgg_cd": identity["sgg_cd"],
            }
    return [next(iter(candidates.values())), identity] if len(candidates) == 1 else [identity]


def _region_equivalent(address, identity):
    source = identity.get("_source_sgg_text")
    if not source or not address:
        return address
    normalized = _normalize_region_prefix(str(address))
    old = _normalize_region_prefix(source)
    new = _normalize_region_prefix(identity["sgg_text"])
    return new + normalized[len(old):] if normalized.startswith(old + " ") else normalized


def select_title(item, identity, rows):
    """Full parcel/road identity, unique register PK and explicit dong only."""
    expected = normalize_jibun_prefix(
        f"{identity['sgg_text']} {identity['umd_nm']} {identity['jibun']}")
    road = normalize_road_prefix(_region_equivalent(item.get("address_road"), identity))
    candidates = {}
    for row in rows:
        if normalize_jibun_prefix(row.get("platPlc")) != expected:
            continue
        if road and normalize_road_prefix(row.get("newPlatPlc")) != road:
            continue
        pk = row.get("mgmBldrgstPk")
        if pk:
            candidates[pk] = row
    text = str(item.get("title") or "")
    explicit_dongs = set(re.findall(r"(?<![가-힣A-Za-z0-9])([A-Za-z가-힣0-9]+동)(?![가-힣A-Za-z0-9])", text))
    explicit_dongs.discard(identity["umd_nm"])
    if len(candidates) > 1 or explicit_dongs:
        selected = {}
        for pk, row in candidates.items():
            label = row.get("dongNm") or ""
            if not label:
                labels = re.findall(r"(?<![가-힣A-Za-z0-9])([A-Za-z가-힣0-9]+동)(?![가-힣A-Za-z0-9])", row.get("bldNm") or "")
                label = labels[0] if len(labels) == 1 else ""
            if (label and label in explicit_dongs) or (not label and len(candidates) == 1):
                selected[pk] = row
        candidates = selected
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _number(row, field, integer=False):
    try:
        value = float(row.get(field))
        if not math.isfinite(value) or value < 0:
            return None
        return int(value) if integer else value
    except (ValueError, TypeError):
        return None


def persist_title(cur, item, identity, title, *, allow_legacy_reuse=False):
    """Recheck the parcel inside a transaction; do not overwrite known facts."""
    from building_registry import _find_categories, _combine_labels, resolve_api_building_name, _title_row_to_dict
    from lodging_classification import classify_building_use
    cur.execute("""SELECT address_road,address_jibun,title,master_building_id
      FROM auction_items WHERE id=%s FOR UPDATE""", [item["id"]])
    current = cur.fetchone()
    if not current or any(current.get(field) != item.get(field)
                          for field in ("address_road", "address_jibun", "title", "master_building_id")):
        return None
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                ["auction-parcel:" + json.dumps(
                    [identity["sgg_cd"], identity["bjd"], identity["jibun"]])])
    cur.execute("""SELECT id,building_name,road_address,jibun_address,sgg_text,umd_nm,jibun,
      mgm_bldrgst_pk FROM master_buildings WHERE mgm_bldrgst_pk=%s OR (sgg_cd=ANY(%s)
      AND REPLACE(umd_nm,' ','')=%s AND jibun=%s) FOR UPDATE""",
                [title["mgmBldrgstPk"],
                 [identity["sgg_cd"], identity.get("_source_sgg_cd", identity["sgg_cd"])],
                 identity["umd_nm"], identity["jibun"]])
    existing = [dict(row) for row in cur.fetchall()]
    pk = title["mgmBldrgstPk"]
    exact = [row for row in existing if row.get("mgm_bldrgst_pk") == pk]
    if len(exact) > 1:
        return None
    if exact:
        building_id = exact[0]["id"]
    elif existing:
        # An old parcel-level master without PK can be reused only if unique.
        unknown = [row for row in existing if not row.get("mgm_bldrgst_pk")]
        match = choose_building(item, *build_indexes(unknown)[:2]) if (
            allow_legacy_reuse and len(existing) == 1) else None
        if not match:
            return None
        dong = title.get("dongNm") or ""
        old_dongs = set(re.findall(r"(?<![가-힣A-Za-z0-9])([A-Za-z가-힣0-9]+동)(?![가-힣A-Za-z0-9])",
                                  match.get("building_name") or ""))
        old_dongs.discard(identity["umd_nm"])
        if old_dongs and (not dong or dong not in old_dongs):
            return None
        building_id = match["id"]
    else:
        purpose = " ".join(str(title.get(k) or "") for k in ("mainPurpsCdNm", "etcPurps")).strip()
        if classify_building_use(purpose) not in ("숙박시설", "수련시설", "복합"):
            return None
        cats = _find_categories(purpose)
        if "생활형숙박" in purpose:
            cats.add("생활")
        label = _combine_labels(cats) if cats else ("일반" if "숙박" in purpose else "복합")
        name = resolve_api_building_name(_title_row_to_dict(title)) or f"{identity['umd_nm']} {identity['jibun']}"
        fields = {
            "building_name": name, "road_address": title.get("newPlatPlc") or title["platPlc"],
            "jibun_address": title["platPlc"], "sgg_text": identity["sgg_text"],
            "sgg_cd": identity["sgg_cd"], "umd_nm": identity["umd_nm"], "jibun": identity["jibun"],
            "mgm_bldrgst_pk": pk, "source": "auction_register", "source_key": "auction_register|" + pk,
            "lodging_type": label, "lodging_type_detail": purpose,
            "building_use_type": classify_building_use(purpose), "building_use_detail": purpose,
            "lodging_classification_source": "building_registry", "main_purps_nm": title.get("mainPurpsCdNm"),
            "strct_nm": title.get("strctCdNm"), "use_apr_day": title.get("useAprDay") or None,
        }
        for target, source, integer in (
            ("units", "hoCnt", True), ("hhld_cnt", "hhldCnt", True),
            ("grnd_flr_cnt", "grndFlrCnt", True), ("ugrnd_flr_cnt", "ugrndFlrCnt", True),
            ("plat_area", "platArea", False), ("arch_area", "archArea", False),
            ("tot_area", "totArea", False), ("bc_rat", "bcRat", False),
            ("vl_rat", "vlRat", False), ("heit", "heit", False),
        ):
            fields[target] = _number(title, source, integer)
        columns = ",".join(fields)
        placeholders = ",".join(["%s"] * len(fields))
        cur.execute(f"""INSERT INTO master_buildings({columns})
          VALUES({placeholders}) ON CONFLICT DO NOTHING RETURNING id""", list(fields.values()))
        inserted = cur.fetchone()
        if not inserted:
            return None
        building_id = inserted["id"]
    if existing:
        # Fill missing register facts only. Preserve names, legal classifications,
        # existing confirmed values, and all operating/permit information.
        fields = {"mgm_bldrgst_pk": pk, "main_purps_nm": title.get("mainPurpsCdNm"),
                  "strct_nm": title.get("strctCdNm"), "use_apr_day": title.get("useAprDay") or None}
        for target, source, integer in (
            ("units", "hoCnt", True), ("hhld_cnt", "hhldCnt", True),
            ("grnd_flr_cnt", "grndFlrCnt", True), ("ugrnd_flr_cnt", "ugrndFlrCnt", True),
            ("plat_area", "platArea", False), ("tot_area", "totArea", False),
        ):
            fields[target] = _number(title, source, integer)
        assignments = ",".join(f"{field}=COALESCE({field},%s)" for field in fields)
        cur.execute(f"UPDATE master_buildings SET {assignments} WHERE id=%s",
                    [*fields.values(), building_id])
    cur.execute("""UPDATE auction_items SET master_building_id=%s,updated_at=NOW()
      WHERE id=%s AND master_building_id IS NULL""", [building_id, item["id"]])
    if cur.rowcount != 1:
        return None
    return building_id


def run_lookup(item_id, run_id):
    """No raw external errors are persisted or exposed; all terminal writes fenced."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_meta WHERE key=%s", [PREFIX + str(item_id)])
                row = cur.fetchone()
                if not row or json.loads(row["value"]).get("run_id") != run_id:
                    return
                cur.execute(f"SELECT * FROM auction_items a WHERE a.id=%s AND {ELIGIBLE_SQL}", [item_id])
                item = cur.fetchone()
        if not item:
            state, building_id = "empty", None
        elif item["master_building_id"]:
            state, building_id = "done", item["master_building_id"]
        else:
            import building_registry
            code_map = BjdongMap(os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip"))
            identity = parcel_identity(item, code_map)
            state, building_id = "address_required", None
            if identity:
                # Realtime relay token/bucket, not batch. Bounded pages/retries.
                for identity in query_identities(identity, code_map):
                    rows = building_registry._fetch_title_rows(
                        identity["sgg_cd"], identity["bjd"], *parse_jibun(identity["jibun"]),
                        timeout=8, retry_max=0, purpose="realtime", max_pages=3)
                    if rows:
                        break
                title = select_title(item, identity, rows)
                state = "empty" if not rows else "ambiguous"
                if title:
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""SELECT value FROM app_meta WHERE key=%s FOR UPDATE""",
                                        [PREFIX + str(item_id)])
                            claim = cur.fetchone()
                            if not claim or json.loads(claim["value"]).get("run_id") != run_id:
                                return
                            building_id = persist_title(
                                cur, item, identity, title,
                                allow_legacy_reuse=len({r.get("mgmBldrgstPk") for r in rows}) == 1)
                            if building_id:
                                state = "done"
                            _finish(cur, item_id, run_id, state, building_id)
                        conn.commit()
                    if building_id:
                        from stats_cache import mark_master_stats_invalidated
                        try:
                            mark_master_stats_invalidated("auction_register")
                        except Exception:
                            pass  # Main source commit must not be undone by a signal.
                    return
        with get_conn() as conn:
            with conn.cursor() as cur:
                _finish(cur, item_id, run_id, state, building_id)
            conn.commit()
    except Exception:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _finish(cur, item_id, run_id, "failed")
            conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--item-id", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_lookup(args.item_id, args.run_id)
