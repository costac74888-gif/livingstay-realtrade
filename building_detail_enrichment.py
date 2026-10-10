"""Restartable, independently committed building-detail stages (no new schema).

Only existing app_meta and master_buildings are used. An expiring DB lease
fences web workers and the batch runner; failed stages never erase good data.
"""
import json
import math
import re
import time
import uuid
from datetime import datetime

import building_registry as registry
from address_utils import parse_jibun
from db import get_conn
from quota_policy import claim_building_hub_request, QuotaExhausted, PROVIDER_QUOTAS
from building_detail_budget import reserve, next_reset, INSPECTION_KEY, INSPECTION_REQUEST_LIMIT
from secret_redaction import redact_exception

PREFIX = "building_detail:v1:"
STAGES = ("title", "zoning", "inspection")
TERMINAL = ("ok", "empty")
RETRY_SECONDS = 6 * 3600
FIELDS = {
    "title": {
        "plat_area": "platArea", "arch_area": "archArea", "tot_area": "totArea",
        "bc_rat": "bcRat", "vl_rat": "vlRat", "heit": "heit",
        "grnd_flr_cnt": "grndFlrCnt", "ugrnd_flr_cnt": "ugrndFlrCnt",
        "ride_use_elvt_cnt": "rideUseElvtCnt", "emgen_use_elvt_cnt": "emgenUseElvtCnt",
        "main_purps_nm": "mainPurpsCdNm", "strct_nm": "strctCdNm",
        "hhld_cnt": "hhldCnt", "tot_pkng_cnt": "totPkngCnt",
        "indr_auto_utcnt": "indrAutoUtcnt", "oudr_auto_utcnt": "oudrAutoUtcnt",
        "indr_mech_utcnt": "indrMechUtcnt", "oudr_mech_utcnt": "oudrMechUtcnt",
        "use_apr_day": "useAprDay", "permit_day": "pmsDay",
        "actual_start_day": "stcnsDay", "mgm_bldrgst_pk": "mgmBldrgstPk",
    },
    "zoning": {"jiyuk_nm": "jiyukNm", "jigu_nm": "jiguNm", "guyuk_nm": "guyukNm"},
    "inspection": {
        "last_inspection_agency": "chkCoNm",
        "last_inspection_start_day": "chkStrtDay",
        "last_inspection_submit_day": "submitDe",
    },
}
TEXT_FIELDS = {
    "main_purps_nm", "strct_nm", "mgm_bldrgst_pk",
    "jiyuk_nm", "jigu_nm", "guyuk_nm", "last_inspection_agency",
}
DATE_FIELDS = {
    "use_apr_day", "permit_day", "actual_start_day",
    "last_inspection_start_day", "last_inspection_submit_day",
}
INTEGER_FIELDS = {
    "grnd_flr_cnt", "ugrnd_flr_cnt", "ride_use_elvt_cnt", "emgen_use_elvt_cnt",
    "hhld_cnt", "tot_pkng_cnt", "indr_auto_utcnt", "oudr_auto_utcnt",
    "indr_mech_utcnt", "oudr_mech_utcnt",
}


def parse_value(field, value):
    if value is None or str(value).strip() == "":
        return None
    value = str(value).strip()
    if field in TEXT_FIELDS:
        return value
    if field in DATE_FIELDS:
        compact = value.replace("-", "")
        if not compact.strip("0"):
            return None
        return datetime.strptime(compact, "%Y%m%d").strftime("%Y-%m-%d")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Invalid nonnegative building value")
    if field in INTEGER_FIELDS:
        if number != int(number):
            raise ValueError("Nonintegral building count")
        return int(number)
    return number


def select_title(rows, building):
    if not rows:
        return None
    pk = str(building.get("mgm_bldrgst_pk") or "")
    matches = [r for r in rows if str(r.get("mgmBldrgstPk") or "") == pk] if pk else []
    if len(matches) == 1:
        return matches[0]
    if not pk and len(rows) == 1:
        return rows[0]
    raise ValueError("표제부 건물 식별 불일치 또는 여러 동: 수동 확인 필요")


def stage_values(stage, rows, building):
    if stage == "title":
        representative = select_title(rows, building)
    elif stage == "zoning":
        representative = {}
        keyed = [r for r in rows if r.get("mgmBldrgstPk")]
        if keyed:
            rows = [r for r in keyed if str(r["mgmBldrgstPk"]) == str(building.get("mgm_bldrgst_pk") or "")]
            if not rows:
                raise ValueError("지역지구 건물 식별 불일치")
        for field, source in FIELDS[stage].items():
            label = {"jiyuk_nm": "지역", "jigu_nm": "지구", "guyuk_nm": "구역"}[field]
            values = sorted({
                r.get("jijiguCdNm") or r.get("etcJijigu")
                for r in rows if label in str(r.get("jijiguGbCdNm") or "")
                and (r.get("jijiguCdNm") or r.get("etcJijigu"))
            } | {r.get(source) for r in rows if r.get(source)})
            representative[source] = " · ".join(values) or None
    else:
        # 공급자가 건물 식별자를 제공하면 같은 건물의 이력만 사용한다.
        keyed = [r for r in rows if r.get("mgmBldrgstPk")]
        if keyed:
            rows = [r for r in keyed if inspection_identity_matches(r, building)]
            if not rows:
                raise ValueError("정기점검 건물 식별 불일치")
        representative = max(rows, key=lambda r: r.get("submitDe") or r.get("chkStrtDay") or "") if rows else None
    values = {
        field: parse_value(field, (representative or {}).get(source))
        for field, source in FIELDS[stage].items()
    }
    if stage == "title" and values["tot_pkng_cnt"] is None:
        parking = [values[k] for k in ("indr_auto_utcnt", "oudr_auto_utcnt", "indr_mech_utcnt", "oudr_mech_utcnt")]
        if all(value is not None for value in parking):
            values["tot_pkng_cnt"] = sum(parking)
    return values


def inspection_identity_matches(row, building):
    pk = str(building.get("mgm_bldrgst_pk") or "")
    other = str(row.get("mgmBldrgstPk") or "")
    if pk and pk == other:
        return True
    # 실제 두 원본에서 확인된 HUB 14자리 ↔ 점검 시군구-9자리 형식.
    # 번호 뒷부분만 비교하지 않고 시군구·지번까지 함께 확인한다.
    if not (pk.isdigit() and len(pk) == 14 and re.fullmatch(r"\d{5}-\d{9}", other)):
        return False
    try:
        _plat, bun, ji = parse_jibun(building["jibun"])
        return (
            other.split("-")[1] == pk[-9:]
            and other.split("-")[0] == str(building["sgg_cd"])
            and str(row.get("sigunguCd")) == str(building["sgg_cd"])
            and int(row.get("bun") or -1) == int(bun)
            and int(row.get("ji") or 0) == int(ji)
        )
    except (KeyError, ValueError, TypeError):
        return False


def read_status(cur, building_id):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", [PREFIX + str(building_id)])
    row = cur.fetchone()
    return json.loads(row["value"]) if row and row["value"] else {"stages": {}}


def public_status(status):
    """No provider exceptions, credentials or lease tokens in public JSON."""
    return {
        "running": bool(status.get("owner") and status.get("lease_until", 0) > time.time()),
        "stages": {
            name: {"status": data.get("status"), "checked_at": data.get("checked_at"),
                   "failure_kind": data.get("failure_kind")}
            for name, data in status.get("stages", {}).items() if name in STAGES
        },
        "fields": {
            field: state for field, state in status.get("fields", {}).items()
            if any(field in values for values in FIELDS.values())
            and state in ("ok", "empty", "failed", "existing")
        },
    }


def due_stages(status, now=None):
    now = time.time() if now is None else now
    return [
        stage for stage in STAGES
        if status.get("stages", {}).get(stage, {}).get("status") not in TERMINAL
        and status.get("stages", {}).get(stage, {}).get("retry_at", 0) <= now
    ]


def summary_counts(cur):
    projections = ["COUNT(*) AS checked"]
    for stage in STAGES:
        for outcome in (*TERMINAL, "failed"):
            projections.append(
                f"COUNT(*) FILTER (WHERE value::jsonb->'stages'->'{stage}'->>'status'='{outcome}') AS {stage}_{outcome}"
            )
    completed = " AND ".join(
        f"value::jsonb->'stages'->'{s}'->>'status' IN ('ok','empty')" for s in STAGES
    )
    projections.append(f"COUNT(*) FILTER (WHERE {completed}) AS completed")
    cur.execute(f"SELECT {', '.join(projections)} FROM app_meta WHERE key LIKE %s", [PREFIX + "%"])
    row = cur.fetchone()
    return {
        "checked": row["checked"], "completed": row["completed"],
        "stages": {s: {v: row[f"{s}_{v}"] for v in (*TERMINAL, "failed")} for s in STAGES},
    }


def _save(cur, bid, status):
    cur.execute(
        "UPDATE app_meta SET value=%s, updated_at=NOW() WHERE key=%s",
        [json.dumps(status, ensure_ascii=False), PREFIX + str(bid)],
    )


def enrich(building_id, bjdong, *, purpose="realtime", allowed_stages=STAGES):
    conn = get_conn()
    cur = conn.cursor()
    owner = uuid.uuid4().hex
    key = PREFIX + str(building_id)
    try:
        # Claim uses database time; expired workers cannot publish later.
        cur.execute("""
            INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
            ON CONFLICT(key) DO UPDATE SET value=(
                app_meta.value::jsonb || EXCLUDED.value::jsonb)::text, updated_at=NOW()
            WHERE COALESCE((app_meta.value::jsonb->>'lease_until')::double precision,0)
                  < EXTRACT(EPOCH FROM NOW())
            RETURNING value
        """, [key, json.dumps({"owner": owner, "lease_until": time.time() + 180})])
        claimed = cur.fetchone()
        conn.commit()
        if not claimed:
            return {"busy": True}
        cur.execute("SELECT * FROM master_buildings WHERE id=%s", [building_id])
        building = cur.fetchone()
        conn.commit()
        if not building:
            raise ValueError("건물 없음")
        building = dict(building)
        status = json.loads(claimed["value"])
        stages = [s for s in due_stages(status) if s in allowed_stages]
        bjd = bjdong.find_bjdong_cd(building.get("sgg_cd"), building.get("umd_nm"))
        if not bjd or not building.get("jibun"):
            for stage in stages:
                status.setdefault("stages", {})[stage] = {
                    "status": "failed", "error": "공식 주소코드 미확인",
                    "retry_at": time.time() + RETRY_SECONDS, "failure_kind": "data",
                }
            _save(cur, building_id, status)
            conn.commit()
            return public_status({**status, "owner": None, "lease_until": 0})
        plat, bun, ji = parse_jibun(building["jibun"])
        args = (building["sgg_cd"], bjd, plat, bun, ji)

        def fence():
            cur.execute("SELECT value FROM app_meta WHERE key=%s FOR UPDATE", [key])
            current = cur.fetchone()
            if not current or json.loads(current["value"]).get("owner") != owner:
                raise RuntimeError("건물 상세 수집 소유권 변경")

        def before_request(url):
            fence()
            conn.commit()
            if "/BldRgstHubService/" in url:
                cap = PROVIDER_QUOTAS["building_hub"]["regular"] if purpose == "batch" else PROVIDER_QUOTAS["building_hub"]["total"]
                claim_building_hub_request(cap=cap)
            elif "/MtnChkHubService/" in url:
                reserve(INSPECTION_KEY, INSPECTION_REQUEST_LIMIT)
            fence()
            status["lease_until"] = time.time() + 180
            _save(cur, building_id, status)
            conn.commit()

        with registry.observe_requests(before_request):
            for stage in stages:
                data = {"checked_at": datetime.utcnow().isoformat() + "Z"}
                try:
                    if stage == "title":
                        rows = registry._fetch_title_rows(*args, purpose=purpose)
                        representative = select_title(rows, building)
                        if representative:
                            building["mgm_bldrgst_pk"] = representative.get("mgmBldrgstPk") or building.get("mgm_bldrgst_pk")
                    elif stage == "zoning":
                        rows = registry.fetch_jijigu_rows(*args, purpose=purpose)
                    else:
                        rows = registry.fetch_maintenance_history(*args, purpose=purpose)
                    values = stage_values(stage, rows, building)
                    data["status"] = "ok" if any(v is not None for v in values.values()) else "empty"
                    fence()
                    # The whitelist is static, and COALESCE preserves good stored
                    # values, including genuine 0; never overwrite with a blank.
                    nonempty = {k: v for k, v in values.items() if v is not None}
                    if nonempty:
                        setters = ", ".join(
                            f"{k}=COALESCE(NULLIF({k},''),%s)" if k in TEXT_FIELDS
                            else f"{k}=COALESCE({k},%s)" for k in nonempty
                        )
                        cur.execute(
                            f"UPDATE master_buildings SET {setters} WHERE id=%s",
                            [*nonempty.values(), building_id],
                        )
                    fields = status.setdefault("fields", {})
                    for field, value in values.items():
                        fields[field] = (
                            "ok" if value is not None else
                            "existing" if building.get(field) is not None else "empty"
                        )
                    if stage == "title" and data["status"] == "ok":
                        cur.execute("UPDATE master_buildings SET title_backfilled_at=COALESCE(title_backfilled_at,NOW()) WHERE id=%s", [building_id])
                        building.update({k: building.get(k) if building.get(k) is not None else v for k, v in nonempty.items()})
                except QuotaExhausted:
                    conn.rollback()
                    fence()
                    data.update(status="deferred", retry_at=next_reset(), failure_kind="quota")
                    status.setdefault("stages", {})[stage] = data
                    _save(cur, building_id, status)
                    conn.commit()
                    raise
                except Exception as exc:
                    conn.rollback()
                    fence()
                    data.update({
                        "status": "failed", "retry_at": time.time() + RETRY_SECONDS,
                        "failure_kind": "data" if isinstance(exc, ValueError) else "provider",
                        "error": redact_exception(exc, registry._SECRET_ENV_NAMES)[:300],
                    })
                    for field in FIELDS[stage]:
                        status.setdefault("fields", {})[field] = "failed"
                status.setdefault("stages", {})[stage] = data
                _save(cur, building_id, status)
                if all(status["stages"].get(s, {}).get("status") in TERMINAL for s in STAGES):
                    cur.execute("UPDATE master_buildings SET detail_fetched_at=COALESCE(detail_fetched_at,NOW()) WHERE id=%s", [building_id])
                conn.commit()
                # Each stage has already committed before the next API call.
        return public_status({**status, "owner": None, "lease_until": 0})
    finally:
        try:
            conn.rollback()
            cur.execute("SELECT value FROM app_meta WHERE key=%s FOR UPDATE", [key])
            row = cur.fetchone()
            if row:
                current = json.loads(row["value"])
                if current.get("owner") == owner:
                    current.pop("owner", None)
                    current.pop("lease_until", None)
                    _save(cur, building_id, current)
                    conn.commit()
        finally:
            cur.close()
            conn.close()
