#!/usr/bin/env python3
"""고캠핑 웹에는 있으나 basedList API에서 빠진 캠핑장의 사진·예약 URL을 보강한다."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import html
import json
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from db import get_conn
from import_airbnb_lodging import normalize_name, normalize_road_prefix


BASE_URL = "https://gocamping.or.kr"
LIST_URL = f"{BASE_URL}/bsite/camp/info/list.do"
DETAIL_URL = f"{BASE_URL}/bsite/camp/info/read.do"
HEADERS = {"User-Agent": "HomeAndStay/1.0 (+https://homenstay.com)"}
PARSER_VERSION = 2


def _text(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def _public_url(value):
    value = html.unescape((value or "").strip())
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else None
    except ValueError:
        return None


def _tag_attrs(tag):
    return {
        name.lower(): html.unescape(value)
        for name, _, value in re.findall(
            r"""([\w:-]+)\s*=\s*(["'])(.*?)\2""", tag or "", re.S
        )
    }


def _tags(page_html, tag_name):
    pattern = rf"""<{tag_name}\b(?:"[^"]*"|'[^']*'|[^>])*>"""
    return re.findall(pattern, page_html or "", re.I | re.S | re.X)


def parse_web_list(page_html):
    """목록 HTML에서 상세 ID·시설명·주소·대표사진을 읽는다."""
    result = []
    blocks = re.split(r'(?=<div class="list-item(?:\s|"))', page_html)
    for block in blocks:
        content = re.search(r"read\.do\?c_no=(\d+)", block)
        address = re.search(
            r"""<a[^>]+class=["'][^"']*\baddress\b[^"']*["'][^>]*>
                (.*?)</a>""",
            block,
            re.I | re.S | re.X,
        )
        image = {}
        for image_tag in _tags(block, "img"):
            attrs = _tag_attrs(image_tag)
            if attrs.get("src") and "alt" in attrs:
                image = attrs
                break
        if not (content and image.get("src") and "alt" in image and address):
            continue
        result.append({
            "content_id": content.group(1),
            "name": _text(image["alt"]),
            "address": _text(address.group(1)),
            "first_image_url": urljoin(BASE_URL, image["src"]),
        })
    return result


def parse_web_detail(page_html, content_id, first_image_url=None):
    """상세 HTML의 표기 필드와 공개 사진 전체를 구조화한다."""
    reservation = None
    reservation_block = re.search(
        r'<dt[^>]*>\s*예약페이지\s*</dt>\s*<dd[^>]*>(.*?)</dd>',
        page_html,
        re.I | re.S,
    )
    if reservation_block:
        links = _tags(reservation_block.group(1), "a")
        if links:
            reservation = _public_url(_tag_attrs(links[0]).get("href"))

    fields = []
    seen_labels = set()
    pair_patterns = (
        r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>",
        r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>",
    )
    for pattern in pair_patterns:
        for raw_label, raw_value in re.findall(pattern, page_html, re.I | re.S):
            label, value = _text(raw_label), _text(raw_value)
            if label and value and label not in seen_labels:
                fields.append({"label": label, "value": value})
                seen_labels.add(label)

    field_map = {item["label"].replace(" ", ""): item["value"] for item in fields}
    homepage = None
    for label in ("홈페이지", "바로가기"):
        block = re.search(
            rf"<(?:dt|th)[^>]*>\s*{label}\s*</(?:dt|th)>\s*"
            r"<(?:dd|td)[^>]*>(.*?)</(?:dd|td)>",
            page_html, re.I | re.S,
        )
        links = _tags(block.group(1), "a") if block else []
        if links:
            homepage = _public_url(_tag_attrs(links[0]).get("href"))
            if homepage:
                break

    intro = None
    for class_name in ("camp-intro", "intro", "camp-cont", "content"):
        block = re.search(
            rf'<(?:div|p)[^>]+class=["\'][^"\']*\b{class_name}\b[^"\']*["\'][^>]*>'
            r"(.*?)</(?:div|p)>",
            page_html, re.I | re.S,
        )
        value = _text(block.group(1)) if block else ""
        if len(value) >= 30:
            intro = value
            break

    urls = []
    layout_images = []
    safety_images = []
    if _public_url(first_image_url):
        urls.append(first_image_url)
    full_prefix = f"/upload/camp/{content_id}/"
    for image_tag in _tags(page_html, "img"):
        raw = _tag_attrs(image_tag).get("src", "")
        if not raw.startswith(full_prefix) or "/thumb/" in raw:
            continue
        url = urljoin(BASE_URL, raw)
        if url not in urls:
            urls.append(url)
        attrs = _tag_attrs(image_tag)
        image_label = f"{attrs.get('alt', '')} {attrs.get('title', '')}".lower()
        if any(word in image_label for word in ("배치", "layout", "시설도")):
            layout_images.append(url)
        if any(word in image_label for word in ("안전", "대피", "safety")):
            safety_images.append(url)

    source_url = f"{DETAIL_URL}?c_no={content_id}"
    return {
        "content_id": str(content_id),
        "source_url": source_url,
        "reservation_url": reservation,
        "homepage_url": homepage,
        "phone": field_map.get("문의처") or field_map.get("전화번호"),
        "address": field_map.get("주소"),
        "intro": intro,
        "directions": field_map.get("오시는길") or field_map.get("찾아오시는길"),
        "updated_at": field_map.get("등록일") or field_map.get("수정일"),
        "detail_fields": fields,
        "image_urls": urls,
        "layout_images": list(dict.fromkeys(layout_images)),
        "safety_images": list(dict.fromkeys(safety_images)),
    }


def fetch_web_list(session):
    response = session.get(
        LIST_URL,
        params={"pageUnit": "5000", "pageIndex": "1", "searchKrwd": ""},
        timeout=120,
    )
    response.raise_for_status()
    rows = parse_web_list(response.text)
    total_match = re.search(
        r'<span[^>]+class=["\'][^"\']*\bcount\b[^"\']*["\'][^>]*>'
        r'\s*([\d,]+)\s*</span>',
        response.text,
        re.I,
    )
    total = int(total_match.group(1).replace(",", "")) if total_match else None
    if total is None or total > 5000 or len(rows) != total:
        raise RuntimeError(
            f"고캠핑 웹 목록 검증 실패: 표시 총계={total}, 파싱={len(rows)}"
        )
    return rows


def _load_candidates(cur, building_id=None, refresh_existing=False):
    params = []
    building_filter = ""
    if building_id is not None:
        building_filter = " AND applied_building_id=%s"
        params.append(building_id)
    refresh_filter = """
            AND NULLIF(BTRIM(lr.road_address), '') IS NOT NULL
    """ if refresh_existing else """
            AND (
                 checked.key IS NULL
                 OR lr.gocamping_content_id IS NULL
                 OR lr.gocamping_detail IS NULL
            )
            AND (
                 NULLIF(BTRIM(lr.camping_reservation_url), '') IS NULL
                 OR NULLIF(BTRIM(lr.camping_first_image_url), '') IS NULL
                 OR COALESCE(jsonb_array_length(lr.camping_image_urls), 0) = 0
                 OR lr.gocamping_content_id IS NULL
                 OR lr.gocamping_detail IS NULL
            )
    """
    cur.execute(f"""
        SELECT lr.id, lr.permit_number, lr.biz_name, lr.road_address,
               lr.applied_building_id,
               camping_reservation_url, camping_first_image_url,
               camping_image_urls, gocamping_content_id
          FROM lodging_registry lr
          LEFT JOIN app_meta checked
            ON checked.key = 'gocamping_web_checked:' || lr.id::text
         WHERE lr.permit_number LIKE 'CAMPING:%%:%%'
           AND lr.biz_status_name = '영업/정상'
           {refresh_filter}
           {building_filter}
    """, params)
    return cur.fetchall()


def _candidate_key(name, address):
    return normalize_name(name), normalize_road_prefix(address)


def match_web_rows(candidates, web_rows):
    """정규화한 시설명과 주소가 모두 일치하는 유일한 행만 연결한다."""
    candidates_by_key = {}
    web_by_key = {}
    for row in candidates:
        key = _candidate_key(row["biz_name"], row["road_address"])
        if all(key):
            candidates_by_key.setdefault(key, []).append(row)
    for web in web_rows:
        key = _candidate_key(web["name"], web["address"])
        if all(key):
            web_by_key.setdefault(key, []).append(web)

    matches = []
    ambiguous = 0
    for key, rows in candidates_by_key.items():
        webs = web_by_key.get(key, [])
        if len(rows) == 1 and len(webs) == 1:
            matches.append((rows[0], webs[0], "name_address"))
        elif webs and (len(rows) > 1 or len(webs) > 1):
            ambiguous += 1
    return matches, ambiguous


def _fetch_web_detail(match):
    row, web, match_reason = match
    try:
        response = requests.get(
            DETAIL_URL,
            params={"c_no": web["content_id"]},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        detail = parse_web_detail(
            response.text, web["content_id"], web["first_image_url"]
        )
        return row, web, match_reason, detail, None
    except Exception as exc:
        return row, web, match_reason, None, exc


def _write_run_status(cur, status_key, run_id, payload):
    if not status_key or not run_id:
        return True
    cur.execute("""
        UPDATE app_meta SET value=%s, updated_at=NOW()
         WHERE key=%s AND (value::jsonb ->> 'run_id')=%s
    """, (json.dumps(payload, ensure_ascii=False), status_key, run_id))
    return cur.rowcount == 1


def run(
    *, building_id=None, max_details=300, sleep_sec=0.2, dry_run=False,
    workers=6, status_key=None, run_id=None, refresh_existing=False,
):
    conn = get_conn()
    cur = conn.cursor()
    session = requests.Session()
    session.headers.update(HEADERS)
    counters = {
        "web_items": 0, "candidates": 0, "matched": 0,
        "updated": 0, "failed": 0, "ambiguous": 0,
    }
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = {
        "run_id": run_id, "state": "running", "dry_run": bool(dry_run),
        "refresh_existing": bool(refresh_existing),
        "started_at": started_at, "finished_at": None,
        "current": 0, "target": 0, "counters": counters, "error": None,
    }
    try:
        web_rows = fetch_web_list(session)
        counters["web_items"] = len(web_rows)
        candidates = _load_candidates(
            cur, building_id, refresh_existing=refresh_existing
        )
        counters["candidates"] = len(candidates)

        matched, counters["ambiguous"] = match_web_rows(candidates, web_rows)
        counters["matched"] = len(matched)

        selected = matched[:max_details]
        status["target"] = len(selected)
        if status_key and run_id:
            if not _write_run_status(cur, status_key, run_id, status):
                conn.rollback()
                raise RuntimeError("실행 소유권이 변경되어 중단합니다.")
            conn.commit()
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            detail_results = pool.map(_fetch_web_detail, selected)
            for row, web, match_reason, detail, fetch_error in detail_results:
                try:
                    if fetch_error:
                        raise fetch_error
                    # 네트워크 요청 뒤 최신 행을 잠가 다른 동기화가 쓴 값을 덮지 않는다.
                    cur.execute("""
                        SELECT camping_reservation_url, camping_first_image_url,
                               camping_image_urls, gocamping_content_id
                          FROM lodging_registry
                         WHERE id=%s
                         FOR UPDATE
                    """, (row["id"],))
                    current = cur.fetchone()
                    if not current:
                        conn.rollback()
                        continue
                    existing = current.get("camping_image_urls") or []
                    if isinstance(existing, str):
                        existing = json.loads(existing)
                    image_sources = (
                        detail["image_urls"]
                        if refresh_existing
                        else list(existing) + detail["image_urls"]
                    )
                    images = []
                    for url in image_sources:
                        if _public_url(url) and url not in images:
                            images.append(url)
                    reservation = (
                        detail["reservation_url"]
                        if refresh_existing
                        else (
                            current.get("camping_reservation_url")
                            or detail["reservation_url"]
                        )
                    )
                    first_image = (
                        (images[0] if images else None)
                        if refresh_existing
                        else (
                            current.get("camping_first_image_url")
                            or (images[0] if images else None)
                        )
                    )
                    if not dry_run:
                        cur.execute("""
                            UPDATE lodging_registry
                               SET camping_reservation_url=%s,
                                   camping_first_image_url=%s,
                                   camping_image_urls=%s::jsonb,
                                   gocamping_content_id=%s,
                                   gocamping_detail=%s::jsonb,
                                   gocamping_detail_fetched_at=NOW(),
                                   updated_at=NOW()
                             WHERE id=%s
                        """, (
                            reservation, first_image,
                            json.dumps(images, ensure_ascii=False),
                            web["content_id"],
                            json.dumps(detail, ensure_ascii=False),
                            row["id"],
                        ))
                        payload_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
                        cur.execute("""
                            INSERT INTO gocamping_records
                                (content_id, lodging_registry_id, source_url, web_payload,
                                 photo_urls, payload_hash, parser_version, fetched_at, updated_at)
                            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, NOW(), NOW())
                            ON CONFLICT (content_id) DO UPDATE SET
                                lodging_registry_id=EXCLUDED.lodging_registry_id,
                                source_url=EXCLUDED.source_url,
                                web_payload=EXCLUDED.web_payload,
                                photo_urls=EXCLUDED.photo_urls,
                                payload_hash=EXCLUDED.payload_hash,
                                parser_version=EXCLUDED.parser_version,
                                fetched_at=NOW(), updated_at=NOW()
                        """, (
                            web["content_id"], row["id"], detail["source_url"],
                            payload_json, json.dumps(images, ensure_ascii=False),
                            hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                            PARSER_VERSION,
                        ))
                        # 같은 공식 content_id로 적재된 canonical basedList 원장이
                        # 따로 있으면 검증된 웹 상세를 그 대표 원장에도 투영한다.
                        cur.execute("""
                            UPDATE lodging_registry
                               SET gocamping_content_id=%s,
                                   gocamping_detail=%s::jsonb,
                                   gocamping_detail_fetched_at=NOW(),
                                    camping_reservation_url=CASE
                                        WHEN %s THEN %s
                                        ELSE COALESCE(camping_reservation_url, %s)
                                    END,
                                    camping_first_image_url=CASE
                                        WHEN %s THEN %s
                                        ELSE COALESCE(camping_first_image_url, %s)
                                    END,
                                   camping_image_urls=CASE
                                        WHEN %s
                                          OR COALESCE(jsonb_array_length(camping_image_urls), 0)=0
                                       THEN %s::jsonb
                                       ELSE camping_image_urls
                                   END,
                                   updated_at=NOW()
                             WHERE permit_number=%s
                        """, (
                            web["content_id"], payload_json,
                            refresh_existing, reservation, reservation,
                            refresh_existing, first_image, first_image,
                            refresh_existing, json.dumps(images, ensure_ascii=False),
                            f"CAMPING:{web['content_id']}",
                        ))
                    if not dry_run:
                        cur.execute("""
                            INSERT INTO app_meta (key, value, updated_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (key) DO UPDATE
                            SET value=EXCLUDED.value, updated_at=NOW()
                        """, (
                            f"gocamping_web_checked:{row['id']}",
                            json.dumps({
                                "content_id": web["content_id"],
                                "match": match_reason,
                                "refresh_existing": bool(refresh_existing),
                                "has_reservation": bool(reservation),
                                "image_count": len(images),
                            }, ensure_ascii=False),
                        ))
                    counters["updated"] += 1
                    status["current"] += 1
                    status["counters"] = dict(counters)
                    if not _write_run_status(cur, status_key, run_id, status):
                        conn.rollback()
                        raise RuntimeError("실행 소유권이 변경되어 중단합니다.")
                    conn.commit()
                    print(
                        f"[gocamping-web] {row['id']} {row['biz_name']} "
                        f"매칭={match_reason} 예약={'Y' if reservation else 'N'} "
                        f"사진={len(images)}"
                    )
                except Exception as exc:
                    conn.rollback()
                    if "실행 소유권이 변경" in str(exc):
                        raise
                    counters["failed"] += 1
                    status["current"] += 1
                    status["counters"] = dict(counters)
                    _write_run_status(cur, status_key, run_id, status)
                    conn.commit()
                    print(f"[gocamping-web] {row['id']} 실패: {str(exc)[:160]}")
                if sleep_sec:
                    time.sleep(sleep_sec)
        status.update({
            "state": "done", "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current": len(selected), "counters": dict(counters),
        })
        if _write_run_status(cur, status_key, run_id, status):
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps(counters, ensure_ascii=False))
        return counters
    except Exception as exc:
        conn.rollback()
        status.update({
            "state": "failed", "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "counters": dict(counters), "error": str(exc)[:500],
        })
        if _write_run_status(cur, status_key, run_id, status):
            conn.commit()
        else:
            conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--building-id", type=int)
    parser.add_argument("--max-details", type=int, default=300)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="이미 수집된 시설도 고캠핑 웹 최신값으로 다시 동기화",
    )
    parser.add_argument("--status-key")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    run(
        building_id=args.building_id,
        max_details=max(1, args.max_details),
        sleep_sec=max(0, args.sleep),
        dry_run=args.dry_run,
        workers=max(1, min(args.workers, 8)),
        status_key=args.status_key,
        run_id=args.run_id,
        refresh_existing=args.refresh_existing,
    )


if __name__ == "__main__":
    main()