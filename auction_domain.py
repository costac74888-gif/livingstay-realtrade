"""온비드 원장 정규화. 네트워크·DB와 분리해 판정 규칙을 검증한다."""
import math
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl, urlsplit, urlencode
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ENDPOINTS = {
    "list": "OnbidRlstListSrvc2/getRlstCltrList2",
    "detail": "OnbidRlstDtlSrvc2/getRlstDtlInf2",
    "bid": "OnbidCltrBidDtlSrvc2/getCltrBidInf2",
    "notice": "OnbidPbancDtlnfSrvc2/getPbancDtlInf2",
}
PROPERTY_CODES = "0007,0010,0005,0002,0003,0006,0008,0011,0013"
USAGES = ("숙박시설", "호텔", "오피스텔", "콘도", "콘도미니엄", "모텔", "여관", "펜션", "생활숙박시설")
STATUS_CODES = {"0001": "scheduled", "0002": "bidding", "0010": "sold", "0011": "failed", "0012": "canceled"}
EFFECTIVE_STATUS_SQL = """CASE
 WHEN a.status IN ('scheduled','bidding') AND a.bid_end_at<NOW() THEN 'closed'
 WHEN a.status IN ('scheduled','bidding') AND a.bid_start_at<=NOW() THEN 'bidding'
 ELSE a.status END"""
VISIBLE_SQL = """(
 (a.status IN ('scheduled','bidding') AND a.bid_end_at>=NOW())
 OR (a.status='failed' AND NOT EXISTS (
   SELECT 1 FROM auction_items next_round
   WHERE next_round.source=a.source AND next_round.source_item_id=a.source_item_id
     AND next_round.pbct_cdtn_no<>a.pbct_cdtn_no
     AND (next_round.bid_start_at>a.bid_start_at
       OR (next_round.round_no>a.round_no AND next_round.status IN ('scheduled','bidding','sold','canceled')))
 ))
 OR (a.status='sold' AND a.status_changed_at >= NOW()-INTERVAL '30 days')
 OR (a.status='canceled' AND a.status_changed_at >= NOW()-INTERVAL '7 days')
)"""
# 여러 미래 회차 중 입찰 중인 회차, 그 다음으로 가장 가까운 예정 회차를 노출.
CURRENT_SQL = f"""WITH current_auctions AS (
 SELECT DISTINCT ON (a.source,a.source_item_id) a.*
 FROM auction_items a WHERE {VISIBLE_SQL}
 ORDER BY a.source,a.source_item_id,
 CASE ({EFFECTIVE_STATUS_SQL}) WHEN 'bidding' THEN 0 WHEN 'scheduled' THEN 1
 WHEN 'failed' THEN 2 WHEN 'sold' THEN 3 ELSE 4 END,
 a.bid_start_at ASC NULLS LAST,a.updated_at DESC,a.id DESC
)"""


def number(value, integer=False):
    """가격 표시문구(비공개, VAT 등)를 숫자로 오독하지 않는다."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    result = float(text)
    if not math.isfinite(result) or result <= 0:
        return None
    return int(result) if integer else result


def source_date(value):
    text = re.sub(r"\D", "", str(value or ""))
    try:
        if len(text) not in (8, 12, 14):
            return None
        fmt = {8: "%Y%m%d", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}[len(text)]
        result = datetime.strptime(text, fmt).replace(tzinfo=KST)
        return result if 1990 <= result.year < 2100 else None
    except ValueError:
        return None


def safe_url(value, onbid_only=False):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("https", "http") or not host or parsed.username or parsed.password:
            return None
        if onbid_only and not any(host == d or host.endswith("." + d) for d in ("onbid.co.kr", "onbid.or.kr")):
            return None
        if any(k.lower() in ("servicekey", "apikey", "key", "confmkey", "client_secret", "token") for k, _ in parse_qsl(parsed.query)):
            return None
        return value
    except ValueError:
        return None


def response_items(data):
    header = data.get("header") or data.get("result") or {}
    code = str(header.get("resultCode", ""))
    if code == "03":
        return [], 0
    if code != "00":
        # Gateway 에러 원문·URL을 예외에 넣지 않는다.
        raise ValueError("온비드 응답 오류: " + (code or "응답 구조 확인 필요"))
    body = data.get("body") or {}
    items = body.get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ValueError("온비드 items 구조 확인 필요")
    return items, int(body.get("totalCount") or 0)


def category(row):
    usage = str(row.get("cltrUsgSclsCtgrNm") or "")
    title = str(row.get("onbidCltrNm") or "")
    text = usage + " " + title
    for result, terms in (
        ("생활숙박", ("생활숙박", "생활형숙박", "생숙")),
        ("오피스텔", ("오피스텔",)),
        ("콘도", ("콘도",)),
        ("모텔", ("모텔", "여관")),
        ("펜션", ("펜션", "팬션")),
        ("호텔", ("호텔",)),
    ):
        if any(term in text for term in terms):
            return result
    return "기타"


def sale_kind(row, notices):
    code = str(row.get("prptDivCd") or "")
    # 수탁재산은 신탁과 다르다. 신탁회사 + 공고 본문/첨부의 공적 근거를 함께 요구.
    org = str(row.get("orgNm") or "")
    evidence = str(notices)
    if "신탁" in org and any(term in evidence for term in ("신탁재산", "신탁부동산", "신탁공매", "신탁계약")):
        return "신탁"
    if code == "0007":
        return "압류"
    if code == "0010":
        return "국유"
    if code in ("0002", "0003", "0006", "0011", "0013"):
        return "이용기관"
    return "기타"


def status(row, now=None, bid=None):
    now = now or datetime.now(timezone.utc)
    code = str(row.get("pbctStatCd") or "")
    start, end = source_date(row.get("cltrBidBgngDt")), source_date(row.get("cltrBidEndDt"))
    if code in ("0010", "0011", "0012"):
        return STATUS_CODES[code]
    # 이전 회차의 '유찰'을 현재 회차의 유찰로 오인하지 않는다.
    current_round = str(row.get("pbctNsq") or "").lstrip("0")
    for prev in (bid or {}).get("prcnBidClgList") or []:
        result_at = source_date(prev.get("cltrOpbdDt"))
        same_condition = bool(prev.get("pbctCdtnNo")) and str(prev["pbctCdtnNo"]) == str(row.get("pbctCdtnNo"))
        same_ended_round = (
            end and now > end and result_at
            and end.date() <= result_at.date() <= (end + timedelta(days=7)).date()
            and str(prev.get("pbctNsq") or "").lstrip("0") == current_round
        )
        if same_condition or same_ended_round:
            confirmed = {"유찰": "failed", "낙찰": "sold", "취소": "canceled"}.get(prev.get("pbctStatNm"))
            if confirmed:
                return confirmed
    if code in ("0001", "0002"):
        if start and end and end >= start:
            if now < start:
                return "scheduled"
            if now <= end:
                return "bidding"
        # 2999년 placeholder나 마감은 일정 미확인/결과 확인 대기. 지도에 노출하지 않는다.
    return "closed"


def normalize(row, bid=None, notices=None, now=None):
    title = str(row.get("onbidCltrNm") or "").strip()
    price = number(row.get("lowstBidPrcIndctCont"), integer=True)
    appraisal = number(row.get("apslEvlAmt"), integer=True)
    unit = re.search(r"(?:제?\d+층\s*)?(?:제?\d+[A-Za-z가-힣]?(?:동\s*)?제?\d*호)", title)
    link_fields = {
        "cltrPrptDivCd": str(row.get("prptDivCd") or ""),
        "cltrScrnGrpCd": "0001",
        "onbidCltrno": str(row.get("onbidCltrno") or ""),
        "onbidPbancNo": str(row.get("onbidPbancNo") or ""),
        "pbctCdtnNo": str(row.get("pbctCdtnNo") or ""),
        "pbctNo": str(row.get("pbctNo") or ""),
    }
    detail_url = (
        "https://www.onbid.co.kr/op/cltrpbancinf/cltrdtl/CltrDtlController/mvmnCltrDtl.do?"
        + urlencode(link_fields)
    ) if all(re.fullmatch(r"\d+", value) for value in link_fields.values()) else None
    address_jibun = str(row.get("zadrNm") or "").strip()
    pnu = str(row.get("ltnoPnu") or "")
    if not address_jibun and re.fullmatch(r"\d{19}", pnu):
        main, sub = int(pnu[11:15]), int(pnu[15:19])
        if main:
            address_jibun = " ".join(str(row.get(k) or "").strip() for k in (
                "lctnSdnm", "lctnSggnm", "lctnEmdNm",
            )).strip() + " " + ("산 " if pnu[10] == "2" else "") + str(main) + ("-" + str(sub) if sub else "")
    return {
        "source": "onbid", "source_item_id": str(row["cltrMngNo"]),
        "pbct_cdtn_no": str(row["pbctCdtnNo"]),
        "sale_kind": sale_kind(row, notices or []),
        "usage_name": row.get("cltrUsgSclsCtgrNm") or "숙박시설",
        "lodging_category": category(row), "title": title, "unit_label": unit.group(0) if unit else "",
        "address_road": str(row.get("cltrRadr") or "").strip(),
        "address_jibun": address_jibun,
        "area_m2": number(row.get("bldSqms")),
        "appraisal_price": appraisal, "min_bid_price": price,
        "min_bid_ratio": round(price / appraisal * 100, 2) if price and appraisal else None,
        "round_no": int(row.get("pbctNsq") or 0), "failed_count": int(row.get("usbdNft") or 0),
        "bid_start_at": source_date(row.get("cltrBidBgngDt")),
        "bid_end_at": source_date(row.get("cltrBidEndDt")),
        "status": status(row, now, bid),
        "disposal_method": row.get("dspsMthodNm"),
        "notice_org": row.get("orgNm"), "notice_no": (bid or {}).get("pbancMngNo"),
        "detail_url": detail_url,
    }