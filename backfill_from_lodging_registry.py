"""
backfill_from_lodging_registry.py

영업신고(lodging_registry) 기반으로 master_buildings에 누락된 건물을 등록한다.
discover_new_buildings.py(실거래가 기반)에서 buildingUse='오피스텔'로 분류되어
누락된 생숙(블루오션레지던스4 등)을 포착하는 것이 주목적.

사용법:
    # 전체 실행 (처음)
    python backfill_from_lodging_registry.py

    # 특정 시군구만 테스트 (예: 인천 중구 28110)
    python backfill_from_lodging_registry.py --sgg 28110

    # dry-run (실제 등록 없이 후보만 출력)
    python backfill_from_lodging_registry.py --dry-run

    # 건축HUB 정밀 분류 사용
    python backfill_from_lodging_registry.py --use-hub
"""

import os
import argparse
import json
import threading
import time
from datetime import datetime, timezone

from db import get_conn, init_db
from address_utils import BjdongMap, parse_jibun, normalize_umd_nm
from building_registry import classify_lodging_type
from stats_cache import mark_master_stats_invalidated
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")
REQUEST_SLEEP = 0.3  # 건축HUB API 쿼터 보호


def _status_now():
    """상태 시각을 UTC 기준의 기존 문자열 형식으로 반환한다."""
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

LEGACY_SGG_TEXT_MAP = {
    # 2026년 제물포구·영종구 분리 전 인천광역시 중구 코드.
    # 과거 중구 주소와 분리 후 두 구 주소를 모두 같은 실행 범위로 본다.
    "28110": (
        "인천광역시 중구",
        "인천광역시 제물포구",
        "인천광역시 영종구",
    ),
}

HYGIENE_TYPE_MAP = {
    "생활숙박시설":        ("생숙",      "생활숙박시설"),
    "관광숙박업":          ("분양형호텔", "관광숙박업"),
    "일반숙박업":          ("일반",      "일반숙박업"),
    "외국인관광도시민박업": ("생숙",      "외국인관광도시민박업"),
}

# 건물명 키워드 기반 분류 (hygiene_type 없거나 매핑 안 될 때 2차 판단)
LODGING_NAME_KEYWORDS = {
    "일반": ["여관", "여인숙", "모텔", "민박", "게스트하우스", "호스텔"],
    "생숙": ["레지던스", "스테이", "생활숙박"],
    "관광": ["관광호텔", "리조트", "콘도"],
}


def name_to_lodging_type(biz_name: str):
    """건물명 키워드로 lodging_type 추정. 매칭 없으면 None."""
    for ltype, keywords in LODGING_NAME_KEYWORDS.items():
        for kw in keywords:
            if kw in (biz_name or ""):
                return ltype
    return None


def hygiene_to_lodging_type(hygiene_type: str, biz_name: str = ""):
    """영업신고 업종명 → (lodging_type, lodging_type_detail)"""
    for key, val in HYGIENE_TYPE_MAP.items():
        if key in (hygiene_type or ""):
            return val
    # 2차: 건물명 키워드 판단
    name_type = name_to_lodging_type(biz_name)
    if name_type:
        return (name_type, hygiene_type or "")
    return ("기타", hygiene_type or "")


def run(sgg_filter=None, dry_run=False, status_key=None, run_id=None, use_hub=False):
    init_db()

    def _status_update(**updates):
        if not status_key or not run_id:
            return
        try:
            status = _read_status(status_key) or {}
            if status.get("run_id") != run_id:
                return
            status.update(updates)
            _write_status(status_key, status, run_id)
        except Exception as e:
            print(f"[상태 저장 실패] {e}")

    _status_update(
        state="running",
        started_at=_status_now(),
        total=0, registered=0, skipped=0, failed=0,
    )

    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    # ── 1. 후보 추출 ────────────────────────────────────────
    # sgg_filter가 있으면 BjdongMap으로 시군구 텍스트 변환 후 SQL에서 먼저 필터
    addr_filters = []
    addr_params = []
    if sgg_filter:
        for sgg_cd_f in sgg_filter:
            sgg_text_f = bjdong.sgg_text(sgg_cd_f)
            if not sgg_text_f:
                # 하위 읍면동이 있는 시군구는 sgg_text()의 leaf 목록에서
                # 제외되므로, 전체 시군구 행에서 상위 텍스트를 보완한다.
                sgg_text_f = next(
                    (name for cd, name in bjdong._all_sgg_rows if cd == sgg_cd_f),
                    None,
                )
            sgg_texts = [sgg_text_f] if sgg_text_f else list(
                LEGACY_SGG_TEXT_MAP.get(sgg_cd_f, ())
            )
            if sgg_texts:
                prefix_filters = []
                for sgg_text in sgg_texts:
                    prefix_filters.append(
                        "(lr.road_address LIKE %s OR lr.jibun_address LIKE %s)"
                    )
                    addr_params += [f"{sgg_text}%", f"{sgg_text}%"]
                addr_filters.append(
                    "(" + " OR ".join(prefix_filters) + ")"
                )
            else:
                raise ValueError(f"시군구 코드에 해당하는 주소명을 찾을 수 없습니다: {sgg_cd_f}")

    where_extra = ("AND (" + " OR ".join(addr_filters) + ")") if addr_filters else ""

    query = f"""
        SELECT lr.id, lr.biz_name, lr.road_address, lr.jibun_address,
               lr.road_norm, lr.jibun_norm, lr.hygiene_type,
               lr.room_count, lr.phone
        FROM lodging_registry lr
        WHERE lr.biz_status_name IN ('영업/정상', '영업중', '영업')
          AND lr.applied_building_id IS NULL
          AND lr.dismissed_at IS NULL
          AND lr.hygiene_type IS NOT NULL
          AND lr.hygiene_type != ''
          {where_extra}
    """
    cur.execute(query, addr_params)
    candidates = cur.fetchall()
    print(f"[후보] 총 {len(candidates)}건")
    _status_update(
        state="running",
        started_at=_status_now(),
        total=len(candidates), registered=0, skipped=0, failed=0,
    )

    registered = skipped = failed = 0

    def _maybe_write_status():
        processed = registered + skipped + failed
        if processed and processed % 100 == 0:
            _status_update(
                state="running",
                total=len(candidates),
                registered=registered,
                skipped=skipped,
                failed=failed,
            )

    for index, lr in enumerate(candidates, 1):
        if (
            status_key
            and run_id
            and index % 20 == 0
            and not _still_owner(cur, status_key, run_id)
        ):
            print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.")
            break

        road_addr = lr["road_address"] or ""
        jibun_addr = lr["jibun_address"] or ""
        biz_name = lr["biz_name"]
        lr_id = lr["id"]

        # ── 3. 로컬 주소 파싱 (외부 API 없음) ───────────────────
        # 우선순위: jibun_address > road_address (지번주소가 파싱이 쉬움)
        parse_src = jibun_addr or road_addr
        if not parse_src:
            failed += 1
            print(f"  [스킵] {biz_name} — 주소 없음")
            _maybe_write_status()
            continue

        # BjdongMap 로컬 매핑으로 시군구 추출 (API 호출 없음)
        sgg_info = bjdong.extract_sgg_from_address(parse_src)
        if not sgg_info:
            failed += 1
            print(f"  [실패] {biz_name} — 시군구 인식 실패: {parse_src[:40]}")
            _maybe_write_status()
            continue

        si_do, sgg_nm, sgg_cd = sgg_info
        sgg_text_local = f"{si_do} {sgg_nm}".strip()

        # 시군구명 이후 부분 파싱 → "중산동 1234-5" 형태
        remainder = parse_src[len(sgg_text_local):].strip()
        tokens = remainder.split()
        if len(tokens) < 2:
            failed += 1
            print(f"  [실패] {biz_name} — umd/jibun 파싱 불가: {remainder[:30]}")
            _maybe_write_status()
            continue

        umd_nm = normalize_umd_nm(tokens[0])
        jibun_str = tokens[1]

        # ── 4. master_buildings 중복 확인 ──────────────────────
        cur.execute("""
            SELECT id FROM master_buildings
            WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
        """, [sgg_cd, umd_nm, jibun_str])
        dup = cur.fetchone()
        if dup:
            if not dry_run:
                cur.execute(
                    "UPDATE lodging_registry SET applied_building_id=%s WHERE id=%s",
                    [dup["id"], lr_id]
                )
                conn.commit()
            skipped += 1
            print(f"  [중복] {biz_name} → #{dup['id']}")
            _maybe_write_status()
            continue

        # ── 5. lodging_type 판정 ──────────────────────────────────
        sgg_text = sgg_text_local
        _use_hub_this = False
        if use_hub:
            # 법정동 코드·지번 파싱도 HUB를 사용할 때만 수행한다.
            try:
                bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
                if not bjdong_cd:
                    raise ValueError(f"법정동 코드 없음: {sgg_cd} {umd_nm}")
                plat_gb, bun2, ji2 = parse_jibun(jibun_str)
                _use_hub_this = True
            except Exception as e:
                print(f"  [HUB 전처리 실패→fallback] {biz_name}: {e}")

        if _use_hub_this:
            # 건축HUB 정밀분류 (--use-hub 옵션 시에만)
            time.sleep(REQUEST_SLEEP)
            try:
                label, detail, subtype, title, reason = classify_lodging_type(
                    sgg_cd, bjdong_cd, plat_gb, bun2, ji2
                )
                if not label:
                    raise ValueError(f"건축HUB 판정불가: {reason}")
                ho_cnt = (title or {}).get("ho_cnt") or lr["room_count"] or 0
            except Exception as e:
                # 건축HUB 실패 시 영업신고 hygiene_type으로 fallback
                label, detail = hygiene_to_lodging_type(
                    lr["hygiene_type"], biz_name
                )
                subtype = ""
                ho_cnt = lr["room_count"] or 0
                print(f"  [건축HUB실패→fallback] {biz_name}: {e}")
        else:
            # 기본: hygiene_type + 건물명 키워드만으로 즉시 분류 (빠름)
            label, detail = hygiene_to_lodging_type(lr["hygiene_type"], biz_name)
            subtype = ""
            ho_cnt = lr["room_count"] or 0

        if dry_run:
            print(f"  [DRY] {biz_name} | {sgg_text} {umd_nm} {jibun_str} | {label}")
            _maybe_write_status()
            continue

        # ── 6. master_buildings 등록 ───────────────────────────
        cur.execute("""
            INSERT INTO master_buildings
                (building_name, sgg_cd, sgg_text, umd_nm, jibun,
                 road_address, lodging_type, lodging_type_detail,
                 lodging_subtype, units, source, name_pending)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'lodging_registry',TRUE)
            RETURNING id
        """, [
            biz_name, sgg_cd, sgg_text, umd_nm, jibun_str,
            road_addr, label, detail, subtype, ho_cnt
        ])
        mb_id = cur.fetchone()["id"]

        cur.execute(
            "UPDATE lodging_registry SET applied_building_id=%s WHERE id=%s",
            [mb_id, lr_id]
        )
        conn.commit()
        mark_master_stats_invalidated("backfill_lodging_registry")
        registered += 1
        print(f"  [등록] {biz_name} → #{mb_id} ({label})")
        _maybe_write_status()

    cur.close()
    conn.close()
    print(f"\n완료 — 신규등록: {registered} / 기존매핑: {skipped} / 실패: {failed}")
    _status_update(
        state="done",
        finished_at=_status_now(),
        total=len(candidates),
        registered=registered,
        skipped=skipped,
        failed=failed,
    )
    return registered, skipped, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sgg", help="특정 시군구 코드만 실행 (예: 28110)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 등록 없이 후보만 출력")
    parser.add_argument("--status-key", default=None,
                        help="app_meta에 진행상황을 기록할 키")
    parser.add_argument("--use-hub", action="store_true",
                        help="건축HUB API로 lodging_type 정밀분류 (기본: hygiene_type+키워드만)")
    args = parser.parse_args()
    sgg_filter = {args.sgg} if args.sgg else None

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[backfill] running 상태가 아니므로 종료합니다.")
            raise SystemExit(0)
        run_id = status.get("run_id") or ""

        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(args.status_key, run_id)
                except Exception:
                    pass

        threading.Thread(target=_beat, daemon=True).start()

    error = None
    counts = (None, None, None)
    try:
        counts = run(
            sgg_filter=sgg_filter,
            dry_run=args.dry_run,
            status_key=args.status_key,
            run_id=run_id,
            use_hub=args.use_hub,
        )
    except Exception as e:
        error = str(e)[:500]
        print(f"[backfill] 실패: {error}")
    finally:
        stop_beat.set()

    if args.status_key and run_id is not None:
        try:
            status = _read_status(args.status_key) or {}
            final_status = {
                "state": "failed" if error else "done",
                "finished_at": _status_now(),
                "error": error,
            }
            if counts[0] is not None:
                final_status.update({
                    "registered": counts[0],
                    "skipped": counts[1],
                    "failed": counts[2],
                })
            status.update(final_status)
            _write_status(args.status_key, status, run_id)
        except Exception as e:
            print(f"[backfill] 최종 상태 저장 실패: {e}")
    if error and not args.status_key:
        raise SystemExit(1)