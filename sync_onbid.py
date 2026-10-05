"""별도 프로세스의 온비드 공매 수집. 공개 요청은 이 프로그램을 호출하지 않는다."""
import argparse
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

import requests
from psycopg2.extras import Json, execute_values

from addr_norm import normalize_road_prefix, normalize_jibun_prefix
from auction_domain import (
    ENDPOINTS, PROPERTY_CODES, USAGES, KST, normalize, response_items,
    number, source_date, safe_url, VISIBLE_SQL, ELIGIBLE_SQL, is_collectible,
    category, VERIFIED_LIVING_CATEGORY_SQL,
)
from auction_service import STATUS_KEY, SUCCESS_KEY, auction_deep_link
from db import get_conn
from auction_building_matching import build_indexes, choose_building
from geocode_buildings import geocode_address
from secret_redaction import redact_env_secrets, redact_exception


class BudgetExceeded(Exception):
    pass


class LostOwnership(Exception):
    pass


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Runner:
    def __init__(self, args):
        self.args = args
        self.run_id = args.run_id or str(uuid.uuid4())
        self.stopped = threading.Event()
        self.state = {
            "state": "running", "run_id": self.run_id,
            "started_at": datetime.now(KST).isoformat(), "finished_at": None,
            "processed": 0, "total": 0, "new": 0, "updated": 0, "matched": 0,
            "geocode_failed": 0, "errors": 0, "last_error": None,
            "calls_today": {}, "detail_pending": 0, "list_complete": False,
        }
        self.session = requests.Session()
        self.key = unquote(os.environ.get("DATA_GO_KR_BROKER_API_KEY", ""))
        self.failures = 0
        self.notices = {}
        self.geo = {}
        self.master_road, self.master_jibun = defaultdict(list), defaultdict(list)
        self.lock_conn = None

    def own(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value::jsonb->>'run_id' AS owner FROM app_meta WHERE key=%s", [self.args.status_key])
                row = cur.fetchone()
                return bool(row and row["owner"] == self.run_id)

    def save_state(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE app_meta SET value=%s,updated_at=NOW()
                  WHERE key=%s AND value::jsonb->>'run_id'=%s""",
                            [json.dumps(dict(self.state), ensure_ascii=False), self.args.status_key, self.run_id])
                if not cur.rowcount:
                    raise LostOwnership()

    def heartbeat(self):
        while not self.stopped.wait(15):
            try:
                self.save_state()
            except LostOwnership:
                self.stopped.set()
                return
            except Exception:
                # 저장 장애는 다음 하트비트에서 재시도하되 API 호출 전에도 소유권을 검증한다.
                continue

    def claim(self):
        self.lock_conn = get_conn()
        with self.lock_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(72941681) AS acquired")
            acquired = cur.fetchone()["acquired"]
        self.lock_conn.commit()
        if not acquired:
            return False
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                  INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
                  ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()
                  WHERE app_meta.value::jsonb->>'run_id'=%s
                     OR app_meta.value::jsonb->>'state' IS DISTINCT FROM 'running'
                     OR app_meta.updated_at<NOW()-INTERVAL '15 minutes'
                """, [self.args.status_key, json.dumps(self.state, ensure_ascii=False), self.run_id])
                return cur.rowcount > 0

    def reserve(self, service):
        if self.stopped.is_set() or not self.own():
            raise LostOwnership()
        # 1000회 공개 개발계정 기본 한도 중 800회까지만 정기 사용, 재시도도 예약한다.
        date = datetime.now(KST).date().isoformat()
        key = "onbid_api_calls:" + date + ":" + service
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,'0',NOW())
                  ON CONFLICT(key) DO NOTHING""", [key])
                cur.execute("""UPDATE app_meta SET value=(value::integer+1)::text,updated_at=NOW()
                  WHERE key=%s AND value::integer<%s RETURNING value""", [key, self.args.daily_cap])
                row = cur.fetchone()
                if not row:
                    raise BudgetExceeded(service + " 일일 호출 예산 소진")
                self.state["calls_today"][service] = int(row["value"])

    def call(self, service, **params):
        for attempt in range(4):
            self.reserve(service)
            try:
                response = self.session.get(
                    "https://apis.data.go.kr/B010003/" + ENDPOINTS[service],
                    params={"serviceKey": self.key, "pageNo": 1, "numOfRows": 1000,
                            "resultType": "json", **params},
                    timeout=(15, 30),
                )
                if response.status_code in (401, 403):
                    raise PermissionError(service + " 인증·활용승인 확인 필요 (HTTP " + str(response.status_code) + ")")
                if response.status_code == 429:
                    raise BudgetExceeded(service + " 공급자 호출 한도 도달")
                response.raise_for_status()
                data = response.json()
                code = str((data.get("header") or data.get("result") or {}).get("resultCode", ""))
                if code == "22":
                    raise BudgetExceeded(service + " 공급자 호출 한도 도달")
                if code in ("20", "21", "30", "31", "32"):
                    raise PermissionError(service + " 인증 오류 코드 " + code)
                result = response_items(data)
                self.failures = 0
                if self.args.sleep:
                    self.stopped.wait(self.args.sleep)
                return result
            except (requests.RequestException, ValueError) as exc:
                self.failures += 1
                self.state["last_error"] = redact_exception(exc, [
                    "DATA_GO_KR_BROKER_API_KEY", "KAKAO_REST_API_KEY",
                ])[:300]
                self.save_state()
                if self.failures >= 10:
                    self.stopped.wait(300)
                    self.failures = 0
                if attempt == 3:
                    raise RuntimeError(
                        service + " 재시도 후 조회 실패: " + str(self.state["last_error"] or "원인 확인 필요")
                    ) from None
                self.stopped.wait((15, 30, 60)[attempt])
                if self.stopped.is_set():
                    raise LostOwnership()

    def load_master_index(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,road_address,jibun_address,sgg_text,umd_nm,jibun,lodging_type,lodging_type_detail,lat,lng FROM master_buildings")
                rows = cur.fetchall()
        self.master_road, self.master_jibun, _ = build_indexes(rows)

    def coordinates(self, values):
        road = normalize_road_prefix(values["address_road"]) if values["address_road"] else None
        jibun = normalize_jibun_prefix(values["address_jibun"]) if values["address_jibun"] else None
        multi_parcel = bool(re.search(r"외\s*\d+\s*필지|,\s*\d+-\d+", values["address_jibun"]))
        building = choose_building(values, self.master_road, self.master_jibun)
        if building and values.get("lodging_category") in (None, "", "기타"):
            values["lodging_category"] = category({
                "cltrUsgSclsCtgrNm": values.get("usage_name"),
                "onbidCltrNm": values.get("title"),
            }, building)
        if building and building["lat"] is not None and building["lng"] is not None:
            return building["id"], building["lat"], building["lng"]
        # 정규화 키는 공백을 지워 매칭하기 위한 값. 지오코딩에는 실제 주소를 전달한다.
        address = values["address_road"] if road else values["address_jibun"] if jibun else None
        if address and multi_parcel:
            address = address.split(",")[0].strip()
        if not address:
            return building["id"] if building else None, None, None
        if address not in self.geo:
            key = "onbid_geo:" + hashlib.sha256(address.encode()).hexdigest()
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM app_meta WHERE key=%s", [key])
                    cached = cur.fetchone()
            if cached:
                self.geo[address] = json.loads(cached["value"])
            else:
                try:
                    self.geo[address] = geocode_address(address)
                except requests.RequestException:
                    self.geo[address] = None
                if self.geo[address]:
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
                              ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",
                                        [key, json.dumps(self.geo[address])])
        coord = self.geo[address] or (None, None)
        return building["id"] if building else None, coord[0], coord[1]

    def collect_lists(self):
        rows = {}
        for usage in USAGES:
            for possible in ("N", "Y"):
                page = 1
                while True:
                    items, total = self.call("list", prptDivCd=PROPERTY_CODES, pvctTrgtYn=possible,
                                             cltrUsgSclsCtgrNm=usage, pageNo=page)
                    for row in items:
                        if is_collectible(row) and row.get("cltrMngNo") and row.get("pbctCdtnNo") is not None:
                            rows[(str(row["cltrMngNo"]), str(row["pbctCdtnNo"]))] = row
                    if not items or page * 1000 >= total:
                        break
                    if len(items) != 1000:
                        raise ValueError("온비드 페이지 크기 변경: 전체 수집을 완료로 처리하지 않습니다.")
                    page += 1
                self.state["total"] = len(rows)
                self.save_state()
        self.state["list_complete"] = True
        return rows

    def stage_rows(self, rows):
        """원장 변경을 작은 배치로 커밋. 상세 예산 소진 시 다음 실행에서 이어 받는다."""
        values = []
        columns = list(normalize(next(iter(rows.values())))) if rows else []
        for key, row in rows.items():
            if not is_collectible(row):
                continue
            val = normalize(row)
            building = choose_building(val, self.master_road, self.master_jibun)
            val["lodging_category"] = category(row, building)
            raw = {"list": row}
            if val["status"] in ("sold", "canceled", "failed"):
                raw["_confirmed_result"] = val["status"]
            values.append(tuple(val[k] for k in columns) + (Json(raw),))
        staged = []
        for offset in range(0, len(values), 100):
            if not self.own():
                raise LostOwnership()
            assignments = []
            for column in columns:
                if column in ("source", "source_item_id", "pbct_cdtn_no"):
                    continue
                if column in ("address_road", "address_jibun"):
                    assignments.append(f"{column}=COALESCE(NULLIF(EXCLUDED.{column},''),auction_items.{column})")
                elif column == "sale_kind":
                    assignments.append("sale_kind=CASE WHEN auction_items.sale_kind='신탁' THEN auction_items.sale_kind ELSE EXCLUDED.sale_kind END")
                elif column == "lodging_category":
                    # 목록의 넓은 숙박시설 문구로 확인된 대장 분류를 매일 되돌리지 않는다.
                    assignments.append("lodging_category=CASE WHEN EXCLUDED.lodging_category='기타' "
                                       "AND (NULLIF(EXCLUDED.address_jibun,'') IS NULL OR "
                                       "EXCLUDED.address_jibun=auction_items.address_jibun) "
                                       "AND (NULLIF(EXCLUDED.address_road,'') IS NULL OR "
                                       "EXCLUDED.address_road=auction_items.address_road) AND " +
                                       VERIFIED_LIVING_CATEGORY_SQL.replace("a.", "auction_items.") +
                                       " THEN '생활숙박' ELSE EXCLUDED.lodging_category END")
                elif column == "status":
                    assignments.append("""status=CASE
                      WHEN auction_items.status='closed' AND EXCLUDED.status IN ('sold','canceled','failed')
                        AND auction_items.raw->>'_confirmed_result'=EXCLUDED.status THEN 'closed'
                      WHEN EXCLUDED.status='closed'
                      AND auction_items.status IN ('failed','sold','canceled') THEN auction_items.status ELSE EXCLUDED.status END""")
                else:
                    assignments.append(f"{column}=EXCLUDED.{column}")
            # status_changed_at은 실제 상태 변경 시에만 갱신(보존 기간을 매일 연장하지 않음).
            assignments.extend([
                """status_changed_at=CASE WHEN EXCLUDED.status IS DISTINCT FROM auction_items.status
                  AND NOT (EXCLUDED.status='closed' AND auction_items.status IN ('failed','sold','canceled'))
                  AND NOT (auction_items.status='closed' AND auction_items.raw->>'_confirmed_result'=EXCLUDED.status)
                  THEN NOW() ELSE auction_items.status_changed_at END""",
                "raw=auction_items.raw||EXCLUDED.raw", "last_seen_at=NOW()", "updated_at=NOW()",
            ])
            with get_conn() as conn:
                with conn.cursor() as cur:
                    execute_values(cur, f"""INSERT INTO auction_items({','.join(columns)},raw) VALUES %s
                      ON CONFLICT(source,source_item_id,pbct_cdtn_no) DO UPDATE SET {','.join(assignments)}
                      RETURNING id,source_item_id,pbct_cdtn_no,detail_fingerprint,
                        status,bid_end_at,raw->>'_confirmed_result' AS confirmed_result,
                        (raw->>'_detail_checked_at')::timestamptz AS checked_at,
                        (xmax=0) AS inserted""",
                                   values[offset:offset + 100])
                    staged.extend(cur.fetchall())
        self.state["new"] = len({s["source_item_id"] for s in staged if s["inserted"]})
        # 목록은 매 실행 보았음을 기록하되 상세 호출 여부는 fingerprint로 판단한다.
        now = datetime.now(timezone.utc)
        changed = [s for s in staged if (
            s["detail_fingerprint"] != fingerprint(rows[(s["source_item_id"], s["pbct_cdtn_no"])])
            or (s["status"] == "closed" and s["confirmed_result"] not in ("sold", "canceled")
                and s["bid_end_at"] and now - timedelta(days=30) < s["bid_end_at"] < now
                and (not s["checked_at"] or s["checked_at"] < now - timedelta(days=1)))
        )]
        self.state["updated"] = len({s["source_item_id"] for s in changed if not s["inserted"]})
        return staged, changed

    def save_detail(self, target, source, detail, bid, notices):
        merged = {**source, **detail}
        values = normalize(merged, bid, notices)
        building_id, lat, lng = self.coordinates(values)
        raw = json.loads(redact_env_secrets(json.dumps({
            "list": source, "detail": detail, "bid": bid, "notices": notices,
            "_detail_checked_at": datetime.now(KST).isoformat(),
        }, ensure_ascii=False), ["DATA_GO_KR_BROKER_API_KEY", "KAKAO_REST_API_KEY"]))
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 조회 사이에 관리자 새 실행이 소유권을 가져갔으면 이전 실행의 쓰기를 막는다.
                cur.execute("SELECT value::jsonb->>'run_id' AS owner FROM app_meta WHERE key=%s FOR UPDATE",
                            [self.args.status_key])
                if cur.fetchone()["owner"] != self.run_id:
                    raise LostOwnership()
                cur.execute("SELECT status,raw FROM auction_items WHERE id=%s FOR UPDATE", [target["id"]])
                previous = cur.fetchone()
                evidence = previous["raw"].get("_building_category_evidence")
                if (not building_id and evidence and evidence.get("source") == "master_building"
                        and evidence.get("address_jibun") == values["address_jibun"]):
                    values["lodging_category"] = category(merged, evidence)
                    raw["_building_category_evidence"] = evidence
                previous_result = previous["raw"].get("_confirmed_result")
                result = values["status"]
                if result in ("sold", "canceled", "failed"):
                    raw["_confirmed_result"] = result
                    if previous["status"] == "closed" and previous_result == result:
                        values["status"] = "closed"
                elif previous_result in ("sold", "canceled"):
                    raw["_confirmed_result"] = previous_result
                    if result == "closed":
                        values["status"] = previous["status"]
                cols = [c for c in values if c not in ("source", "source_item_id", "pbct_cdtn_no")]
                cur.execute("UPDATE auction_items SET "
                            + """status_changed_at=CASE WHEN status<>%s THEN NOW() ELSE status_changed_at END,"""
                            + ",".join(c + "=%s" for c in cols)
                            + """,master_building_id=%s,lat=%s,lng=%s,raw=%s,detail_fingerprint=%s,
                            updated_at=NOW() WHERE id=%s""",
                            [values["status"]] + [values[c] for c in cols] + [
                                building_id, lat, lng, Json(raw), fingerprint(source), target["id"],
                            ])
                # 같은 물건관리번호의 다른 회차에 공통 주소·좌표만 반영한다.
                # 가격·상태·면적은 회차마다 다를 수 있어 공유하지 않는다.
                cur.execute("""UPDATE auction_items SET address_road=%s,address_jibun=%s,
                  master_building_id=%s,lat=%s,lng=%s
                  WHERE source=%s AND source_item_id=%s AND id<>%s""",
                            [values["address_road"], values["address_jibun"], building_id, lat, lng,
                             values["source"], values["source_item_id"], target["id"]])
                for n, photo in enumerate(detail.get("potoUrlList") or []):
                    url = safe_url(photo.get("urlAdr") if isinstance(photo, dict) else photo, onbid_only=True)
                    if url:
                        cur.execute("""INSERT INTO auction_photos(auction_item_id,url,sort_order) VALUES(%s,%s,%s)
                          ON CONFLICT(auction_item_id,url) DO UPDATE SET sort_order=EXCLUDED.sort_order""",
                                    [target["id"], url, n])
                rounds = [("current", {
                    "pbctNsq": values["round_no"], "cltrBidBgngDt": merged.get("cltrBidBgngDt"),
                    "cltrBidEndDt": merged.get("cltrBidEndDt"),
                    "lowstBidPrcIndctCont": merged.get("lowstBidPrcIndctCont"),
                    "pbctStatNm": {"sold": "낙찰", "failed": "유찰", "canceled": "취소",
                                   "scheduled": "예정", "bidding": "입찰중"}.get(
                                       raw.get("_confirmed_result") if values["status"] == "closed" else values["status"],
                                       "결과 확인 중"),
                })] + [("next", r) for r in bid.get("cseqBidInfClgList") or []] + [
                    ("past", r) for r in bid.get("prcnBidClgList") or []
                ]
                for phase, r in rounds:
                    round_no = int(r.get("pbctNsq") or 0)
                    if round_no <= 0:
                        continue
                    result = r.get("pbctStatNm") or "예정"
                    round_key = "current" if phase == "current" else phase + ":" + fingerprint({
                        k: r.get(k) for k in ("pbctsn", "pbctNsq", "cltrOpbdDt", "cltrBidBgngDt", "cltrBidEndDt")
                    })
                    cur.execute("""
                      INSERT INTO auction_rounds(auction_item_id,round_no,bid_start_at,bid_end_at,min_bid_price,result,result_at,source_round_key)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT(auction_item_id,source_round_key) DO UPDATE SET
                        bid_start_at=COALESCE(EXCLUDED.bid_start_at,auction_rounds.bid_start_at),
                        bid_end_at=COALESCE(EXCLUDED.bid_end_at,auction_rounds.bid_end_at),
                        min_bid_price=COALESCE(EXCLUDED.min_bid_price,auction_rounds.min_bid_price),
                        result=CASE WHEN auction_rounds.result IN ('유찰','낙찰','취소')
                          AND EXCLUDED.result='예정' THEN auction_rounds.result ELSE EXCLUDED.result END
                    """, [target["id"], round_no, source_date(r.get("cltrBidBgngDt")),
                          source_date(r.get("cltrBidEndDt")), number(r.get("lowstBidPrcIndctCont"), True), result,
                          source_date(r.get("cltrOpbdDt")), round_key])
                cur.execute("DELETE FROM auction_rounds WHERE auction_item_id=%s AND source_round_key LIKE 'legacy:%%'",
                            [target["id"]])
                if building_id and values["status"] in ("scheduled", "bidding"):
                    notify_auction_watchers(cur, target["id"], {**values, "master_building_id": building_id})
        self.state["matched"] += int(building_id is not None)
        self.state["geocode_failed"] += int(lat is None or lng is None)

    def detail_target(self, target, source):
        items, _ = self.call("detail", cltrMngNo=target["source_item_id"], pbctCdtnNo=target["pbct_cdtn_no"])
        if not items:
            raise ValueError("물건 상세 응답 없음: 원장 삭제·최종 결과 추정 없이 다음 실행에서 재조회")
        bids, _ = self.call("bid", cltrMngNo=target["source_item_id"], pbctCdtnNo=target["pbct_cdtn_no"])
        if not bids:
            raise ValueError("입찰정보 응답 없음: 다음 실행에서 재조회")
        bid = bids[0]
        notice_no = bid.get("pbancMngNo")
        notices = []
        if notice_no:
            if notice_no not in self.notices:
                self.notices[notice_no], _ = self.call("notice", pbancMngNo=notice_no)
            notices = self.notices[notice_no]
        self.save_detail(target, source, items[0], bid, notices)

    def run(self):
        if not self.key:
            raise ValueError("공공데이터포털 인증키가 등록되지 않았습니다.")
        if not self.claim():
            print("온비드 공매 수집이 이미 실행 중입니다.", flush=True)
            return
        worker = threading.Thread(target=self.heartbeat, daemon=True)
        worker.start()
        try:
            rows = self.collect_lists()
            self.load_master_index()
            staged, changed = self.stage_rows(rows)
            # 목록 원장이 정상적으로 전부 커밋된 시각. 상세 예산 소진과 구분한다.
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
                      ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",
                                [SUCCESS_KEY, datetime.now(KST).isoformat()])
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE auction_items SET status='closed',updated_at=NOW()
                      WHERE (status='sold' AND status_changed_at<NOW()-INTERVAL '30 days')
                         OR (status='canceled' AND status_changed_at<NOW()-INTERVAL '7 days')""")
                    cur.execute("""UPDATE auction_items a SET status='closed',
                      raw=a.raw||'{"_confirmed_result":"failed"}'::jsonb,updated_at=NOW()
                      WHERE a.status='failed' AND NOT """ + VISIBLE_SQL)
            # 입찰 중·가장 가까운 예정 물건을 먼저 상세 조회. 한 물건의 먼 미래 회차가
            # 다른 물건의 첫 사진 수집을 밀어내지 않게 첫 회차 후보를 우선한다.
            ordered = sorted(changed, key=lambda s: (
                normalize(rows[(s["source_item_id"], s["pbct_cdtn_no"])])["status"] not in ("bidding", "scheduled"),
                source_date(rows[(s["source_item_id"], s["pbct_cdtn_no"])].get("cltrBidBgngDt")) or datetime.max.replace(tzinfo=KST),
            ))
            first, other, seen = [], [], set()
            for s in ordered:
                (other if s["source_item_id"] in seen else first).append(s)
                seen.add(s["source_item_id"])
            targets = first + other
            if self.args.limit:
                targets = targets[:self.args.limit]
            self.state["detail_pending"] = len(changed)
            for target in targets:
                try:
                    self.detail_target(target, rows[(target["source_item_id"], target["pbct_cdtn_no"])])
                    self.state["detail_pending"] -= 1
                except (BudgetExceeded, PermissionError, LostOwnership):
                    raise
                except Exception as exc:
                    self.state["errors"] += 1
                    self.state["last_error"] = redact_exception(exc, [
                        "DATA_GO_KR_BROKER_API_KEY", "KAKAO_REST_API_KEY",
                    ])[:300]
                self.state["processed"] += 1
                self.save_state()
                print(json.dumps(self.state, ensure_ascii=False), flush=True)
            # 목록 소실은 결과가 아니다. 종료된 기존 물건은 결과 API로 다시 확인한다.
            if not self.args.limit:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(f"""SELECT a.id,a.source_item_id,a.pbct_cdtn_no,a.raw->'list' AS source_row
                          FROM auction_items a WHERE a.source='onbid' AND {ELIGIBLE_SQL}
                            AND bid_end_at<NOW() AND last_seen_at<NOW()-INTERVAL '5 minutes'
                            AND status IN ('scheduled','bidding','failed','closed')
                            AND COALESCE(raw->>'_confirmed_result','') NOT IN ('sold','canceled')
                            AND ((raw->>'_detail_checked_at')::timestamptz<NOW()-INTERVAL '1 day'
                              OR raw->>'_detail_checked_at' IS NULL)
                          ORDER BY updated_at ASC LIMIT 100""")
                        ended = cur.fetchall()
                for old in ended:
                    if not old["source_row"]:
                        continue
                    try:
                        self.detail_target(old, old["source_row"])
                    except (BudgetExceeded, PermissionError, LostOwnership):
                        raise
                    except Exception as exc:
                        self.state["errors"] += 1
                        self.state["last_error"] = redact_exception(exc, ["DATA_GO_KR_BROKER_API_KEY"])[:300]
            self.state["state"] = "partial" if self.state["detail_pending"] or self.state["errors"] else "done"
        except BudgetExceeded as exc:
            self.state.update(state="waiting_quota", last_error=str(exc))
        except LostOwnership:
            return
        except Exception as exc:
            self.state.update(state="failed", last_error=redact_exception(
                exc, ["DATA_GO_KR_BROKER_API_KEY", "KAKAO_REST_API_KEY"],
            )[:300])
        finally:
            self.stopped.set()
            worker.join(timeout=20)
            self.state["finished_at"] = datetime.now(KST).isoformat()
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value::jsonb->>'run_id' AS owner FROM app_meta WHERE key=%s FOR UPDATE",
                                [self.args.status_key])
                    owner = cur.fetchone()
                    if owner and owner["owner"] == self.run_id:
                        # 실패·quota 종료에서는 원장을 삭제하거나 종료 상태로 바꾸지 않는다.
                        record_sync_outcome(cur, self.state, self.args.status_key)
            if self.lock_conn:
                with self.lock_conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(72941681)")
                self.lock_conn.commit()
                self.lock_conn.close()
                self.lock_conn = None
            if self.own():
                self.save_state()
            self.session.close()
        print(json.dumps(self.state, ensure_ascii=False), flush=True)


def record_sync_outcome(cur, state, status_key=STATUS_KEY):
    """공유 app_meta에 실행 간 실패 연속성을 보존; 두 번째 실패에 한 번 알림."""
    failed = state.get("state") == "failed" or bool(state.get("errors"))
    if not failed and not state.get("list_complete"):
        return  # 한도 소진·소유권 상실은 공급자 장애로 추정하지 않는다.
    key = status_key + ":failure_streak"
    cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,'0',NOW())
      ON CONFLICT(key) DO NOTHING""", [key])
    cur.execute("""UPDATE app_meta SET value=CASE WHEN %s THEN (value::integer+1)::text ELSE '0' END,
      updated_at=NOW() WHERE key=%s RETURNING value""", [failed, key])
    streak = int(cur.fetchone()["value"])
    if streak == 2:
        cur.execute("""INSERT INTO admin_notifications
          (admin_user_id,event_type,source_table,source_id,title,body,deep_link)
          SELECT id,'sync_failure','app_meta',(EXTRACT(EPOCH FROM clock_timestamp())*1000000)::bigint,
            '온비드 공매 수집 2회 연속 실패',
            '기존 공매 원장은 보존했습니다. 데이터 동기화에서 수집 상태와 공급자 연결을 확인하세요.',
            '/admin#datasync' FROM admin_users
          ON CONFLICT DO NOTHING""")


def notify_auction_watchers(cur, item_id, values):
    """새 물건만 기존 헤더 알림함에 전달한다. 메일·SMS는 발송하지 않는다."""
    cur.execute("""SELECT w.user_id,b.building_name,b.road_address,b.jibun_address
      FROM auction_watches w JOIN master_buildings b ON b.id=w.master_building_id
      JOIN auction_items a ON a.master_building_id=b.id
      WHERE a.id=%s AND w.enabled AND w.created_at<(
        SELECT MIN(owner.first_seen_at) FROM auction_items owner
        WHERE owner.source=a.source AND owner.source_item_id=a.source_item_id
      )
        AND EXISTS (SELECT 1 FROM user_favorites f WHERE f.user_id=w.user_id
          AND (f.master_building_id=b.id OR f.address=b.road_address OR f.address=b.jibun_address))
    """, [item_id])
    for watcher in cur.fetchall():
        key = "auction_notified:" + str(watcher["user_id"]) + ":" + fingerprint({
            "source": values["source"], "source_item_id": values["source_item_id"],
        })
        cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,'sent',NOW())
          ON CONFLICT(key) DO NOTHING RETURNING key""", [key])
        if not cur.fetchone():
            continue
        price = f"{values['min_bid_price']:,}원" if values["min_bid_price"] else "확인 필요"
        cur.execute("""INSERT INTO notifications(user_id,title,body,building_name,address,master_building_id)
          VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                    [watcher["user_id"], "관심단지에 새 공매가 등록되었습니다",
                     f"{values['sale_kind']} 공매 · 최저입찰가 {price}. 건물 상세의 공매 탭에서 원문을 확인하세요.",
                     watcher["building_name"], watcher["road_address"] or watcher["jibun_address"],
                     values.get("master_building_id") or None])
        notification = cur.fetchone()
        cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
          ON CONFLICT(key) DO NOTHING""",
                    ["auction_notification_link:" + str(notification["id"]),
                     auction_deep_link(item_id, values.get("master_building_id"))])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-key", default=STATUS_KEY)
    parser.add_argument("--run-id")
    parser.add_argument("--daily-cap", type=int, default=800)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0, help="첫 실행 검증용 상세 조회 상한; 목록은 전체 수집")
    args = parser.parse_args()
    if not 1 <= args.daily_cap <= 800 or args.limit < 0 or args.sleep < 0:
        parser.error("일일 사용 예산은 1~800, limit/sleep은 0 이상이어야 합니다.")
    runner = Runner(args)
    try:
        runner.run()
    finally:
        if runner.lock_conn:
            runner.lock_conn.close()


if __name__ == "__main__":
    main()