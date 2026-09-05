#!/usr/bin/env python3
"""고캠핑 웹에는 있으나 basedList API에서 빠진 캠핑장의 사진·예약 URL을 보강한다."""

import argparse
from concurrent.futures import ThreadPoolExecutor
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
    """상세 HTML에서 예약 URL과 공개 사진을 최대 10장 읽는다."""
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

    urls = []
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
        if len(urls) >= 10:
            break
    return {"reservation_url": reservation, "image_urls": urls[:10]}


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


def _load_candidates(cur, building_id=None):
    params = []
    building_filter = ""
    if building_id is not None:
        building_filter = " AND applied_building_id=%s"
        params.append(building_id)
    cur.execute(f"""
        SELECT lr.id, lr.permit_number, lr.biz_name, lr.road_address,
               lr.applied_building_id,
               camping_reservation_url, camping_first_image_url,
               camping_image_urls
          FROM lodging_registry lr
          LEFT JOIN app_meta checked
            ON checked.key = 'gocamping_web_checked:' || lr.id::text
         WHERE lr.permit_number LIKE 'CAMPING:%%:%%'
           AND lr.biz_status_name = '영업/정상'
           AND checked.key IS NULL
           AND (
                NULLIF(BTRIM(lr.camping_reservation_url), '') IS NULL
                OR NULLIF(BTRIM(lr.camping_first_image_url), '') IS NULL
                OR COALESCE(jsonb_array_length(lr.camping_image_urls), 0) = 0
           )
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


def run(
    *, building_id=None, max_details=300, sleep_sec=0.2, dry_run=False,
    workers=6,
):
    conn = get_conn()
    cur = conn.cursor()
    session = requests.Session()
    session.headers.update(HEADERS)
    counters = {
        "web_items": 0, "candidates": 0, "matched": 0,
        "updated": 0, "failed": 0, "ambiguous": 0,
    }
    try:
        web_rows = fetch_web_list(session)
        counters["web_items"] = len(web_rows)
        candidates = _load_candidates(cur, building_id)
        counters["candidates"] = len(candidates)

        matched, counters["ambiguous"] = match_web_rows(candidates, web_rows)
        counters["matched"] = len(matched)

        selected = matched[:max_details]
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            detail_results = pool.map(_fetch_web_detail, selected)
            for row, web, match_reason, detail, fetch_error in detail_results:
                try:
                    if fetch_error:
                        raise fetch_error
                    # 네트워크 요청 뒤 최신 행을 잠가 다른 동기화가 쓴 값을 덮지 않는다.
                    cur.execute("""
                        SELECT camping_reservation_url, camping_first_image_url,
                               camping_image_urls
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
                    images = []
                    for url in list(existing) + detail["image_urls"]:
                        if _public_url(url) and url not in images:
                            images.append(url)
                    reservation = (
                        current.get("camping_reservation_url")
                        or detail["reservation_url"]
                    )
                    first_image = (
                        current.get("camping_first_image_url")
                        or (images[0] if images else None)
                    )
                    if not dry_run and (reservation or first_image or images):
                        cur.execute("""
                            UPDATE lodging_registry
                               SET camping_reservation_url=%s,
                                   camping_first_image_url=%s,
                                   camping_image_urls=%s::jsonb,
                                   updated_at=NOW()
                             WHERE id=%s
                        """, (
                            reservation, first_image,
                            json.dumps(images[:10], ensure_ascii=False), row["id"],
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
                                "has_reservation": bool(reservation),
                                "image_count": len(images[:10]),
                            }, ensure_ascii=False),
                        ))
                        conn.commit()
                    counters["updated"] += 1
                    print(
                        f"[gocamping-web] {row['id']} {row['biz_name']} "
                        f"매칭={match_reason} 예약={'Y' if reservation else 'N'} "
                        f"사진={len(images[:10])}"
                    )
                except Exception as exc:
                    conn.rollback()
                    counters["failed"] += 1
                    print(f"[gocamping-web] {row['id']} 실패: {str(exc)[:160]}")
                if sleep_sec:
                    time.sleep(sleep_sec)
        print(json.dumps(counters, ensure_ascii=False))
        return counters
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
    args = parser.parse_args()
    run(
        building_id=args.building_id,
        max_details=max(1, args.max_details),
        sleep_sec=max(0, args.sleep),
        dry_run=args.dry_run,
        workers=max(1, min(args.workers, 8)),
    )


if __name__ == "__main__":
    main()