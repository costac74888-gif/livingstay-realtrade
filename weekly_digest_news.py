"""Fetch recent lodging/accommodation news from official Korean sources.

The Korea Tourism Organization's official press-release listing provides
direct article links under an open-government Type 1 attribution license.
MCST's official RSS feed is also checked, but its current items link over HTTP
and are rejected rather than upgraded or followed.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import logging
import re
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)
from xml.etree import ElementTree
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

FEED_URL = "https://www.mcst.go.kr/common/rss/rssGenXml.jsp?pMenuCD=0302000000"
KTO_PRESS_RELEASE_URL = (
    "https://knto.or.kr/pressRelease?srchText=%EC%88%99%EB%B0%95"
)
_ALLOWED_HOSTS = frozenset({"www.mcst.go.kr", "mcst.go.kr", "knto.or.kr"})
_MAX_FEED_BYTES = 512 * 1024
_TIMEOUT_SECONDS = 5
_MAX_AGE = timedelta(days=30)
_SEOUL = ZoneInfo("Asia/Seoul")

_SOURCE_FEEDS = (
    ("knto", KTO_PRESS_RELEASE_URL, "한국관광공사"),
    ("mcst", FEED_URL, "문화체육관광부"),
)
_LODGING_WORDS = (
    "숙박", "숙소", "숙박시설", "숙박업", "호텔", "모텔", "민박", "펜션",
    "리조트", "객실", "야영장", "캠핑장", "캠핑",
    "lodging", "accommodation", "hotel", "motel", "camping", "campground",
    "resort", "hostel",
)


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    """Permit only HTTPS redirects that stay on the configured source host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if (
            new.scheme.lower() != "https"
            or (new.hostname or "").lower() != (old.hostname or "").lower()
            or (new.hostname or "").lower() not in _ALLOWED_HOSTS
            or new.username
            or new.password
        ):
            raise URLError("Rejected redirect outside the HTTPS news source")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_feed(url=FEED_URL):
    """Retrieve a bounded feed with a hard per-request timeout."""
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in _ALLOWED_HOSTS
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Feed URL is not an allowlisted HTTPS source")

    request = Request(url, headers={"User-Agent": "HomeNStayWeeklyDigest/1.0"})
    opener = build_opener(_AllowlistedRedirectHandler())
    with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
        payload = response.read(_MAX_FEED_BYTES + 1)
    if len(payload) > _MAX_FEED_BYTES:
        raise ValueError("RSS feed exceeded the size limit")
    return payload


def _article_url(feed_link, source="mcst"):
    """Accept only direct HTTPS article URLs on a source's allowlisted host."""
    try:
        parsed = urlsplit((feed_link or "").strip())
        host = (parsed.hostname or "").lower()
        if source == "knto":
            if (
                parsed.scheme.lower() not in ("", "https")
                or (host and host != "knto.or.kr")
                or parsed.port is not None
                or parsed.username
                or parsed.password
                or parsed.fragment
                or not re.fullmatch(r"/pressRelease/\d{6,10}", parsed.path)
            ):
                return None
            return "https://knto.or.kr" + parsed.path
        if parsed.scheme.lower() != "https" or parsed.port is not None:
            return None
        if parsed.username or parsed.password or parsed.fragment:
            return None
        if source == "mcst":
            if host not in {"www.mcst.go.kr", "mcst.go.kr"}:
                return None
            if parsed.path != "/site/s_notice/press/pressView.jsp":
                return None
            query = parse_qs(parsed.query, strict_parsing=True)
            press_ids = query.get("pSeq", [])
            if len(press_ids) != 1 or not re.fullmatch(r"\d{1,10}", press_ids[0]):
                return None
            # Keep the supplied HTTPS article URL intact; never upgrade HTTP RSS links.
            return feed_link.strip()
        return None
    except (TypeError, ValueError):
        return None


def _parse_published(value):
    """Parse MCST's compact RSS timestamp and standard RSS dates."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{14}", value):
            return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=_SEOUL)
        parsed = parsedate_to_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_SEOUL)
        return parsed.astimezone(_SEOUL)
    except (TypeError, ValueError, OverflowError):
        return None


def _is_valid_title(title):
    if not isinstance(title, str):
        return False
    title = title.strip()
    return (
        4 <= len(title) <= 180
        and not any(ord(char) < 32 for char in title)
        and any(char.isalnum() for char in title)
    )


def _now_seoul():
    return datetime.now(_SEOUL)


class _KtoListingParser(HTMLParser):
    """Extract only press-release rows from KTO's official listing page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current = None
        self.capture = None
        self.records = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            if self.depth == 0:
                self.current = {"title": [], "date": []}
            self.depth += 1
        elif self.current is not None and tag == "a":
            url = _article_url(attrs.get("href", ""), source="knto")
            if url:
                self.current["path"] = url.removeprefix("https://knto.or.kr")
                self.capture = "title"
        elif self.current is not None and tag in ("span", "div"):
            classes = (attrs.get("class") or "").split()
            if "col-date" in classes:
                self.capture = "date"

    def handle_data(self, data):
        if self.current is not None and self.capture in ("title", "date"):
            self.current[self.capture].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.capture == "title":
            self.capture = None
        elif tag == "span" and self.capture == "date":
            self.capture = None
        elif tag == "li" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.current is not None:
                record = {
                    "path": self.current.get("path"),
                    "title": "".join(self.current["title"]).strip(),
                    "published": "".join(self.current["date"]).strip(),
                }
                if record["path"]:
                    self.records.append(record)
                self.current = None
                self.capture = None


def _parse_knto_listing(payload, now=None, limit=3, source_name="한국관광공사"):
    if not isinstance(payload, (bytes, bytearray)) or len(payload) > _MAX_FEED_BYTES:
        return []
    try:
        parser = _KtoListingParser()
        parser.feed(bytes(payload).decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        return []

    current = now or _now_seoul()
    if current.tzinfo is None:
        current = current.replace(tzinfo=_SEOUL)
    current = current.astimezone(_SEOUL)
    cutoff_date = (current - _MAX_AGE).date()
    if limit is not None:
        try:
            result_limit = max(0, int(limit))
        except (TypeError, ValueError, OverflowError):
            return []
        if result_limit == 0:
            return []
    else:
        result_limit = None

    results = []
    seen_urls = set()
    for record in parser.records:
        title = record["title"]
        try:
            published = datetime.strptime(record["published"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if (
            not _is_valid_title(title)
            or not any(word in title.casefold() for word in _LODGING_WORDS)
            # Reject the cutoff day because the listing exposes dates only,
            # not times; this avoids accepting an item that may be >30 days old.
            or published <= cutoff_date
            or published > current.date()
        ):
            continue
        url = "https://knto.or.kr" + record["path"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append({
            "title": title,
            "url": url,
            "source": source_name,
            "published": published.isoformat(),
        })
        if result_limit is not None and len(results) >= result_limit:
            break
    return results


def _parse_feed(payload, now=None, limit=3, source="mcst", source_name=None):
    """Validate/filter feed records and return the public article dictionaries."""
    if not isinstance(payload, (bytes, bytearray)) or len(payload) > _MAX_FEED_BYTES:
        return []
    # ElementTree does not resolve external entities, and rejecting DTD/entity
    # declarations also avoids expansion-based XML denial-of-service inputs.
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", payload, re.IGNORECASE):
        return []
    try:
        root = ElementTree.fromstring(payload)
    except (ElementTree.ParseError, ValueError):
        return []
    if root.tag.rsplit("}", 1)[-1].lower() != "rss":
        return []

    current = now or _now_seoul()
    if current.tzinfo is None:
        current = current.replace(tzinfo=_SEOUL)
    current = current.astimezone(_SEOUL)
    cutoff = current - _MAX_AGE
    if limit is not None:
        try:
            result_limit = max(0, int(limit))
        except (TypeError, ValueError, OverflowError):
            return []
        if result_limit == 0:
            return []
    else:
        result_limit = None
    result = []
    seen_urls = set()
    channel = next(
        (element for element in root if element.tag.rsplit("}", 1)[-1].lower() == "channel"),
        None,
    )
    if channel is None:
        return []

    for item in channel:
        if item.tag.rsplit("}", 1)[-1].lower() != "item":
            continue
        fields = {
            child.tag.rsplit("}", 1)[-1].lower(): child.text
            for child in item
        }
        title = (fields.get("title") or "").strip()
        if not _is_valid_title(title):
            continue
        if not any(word in title.casefold() for word in _LODGING_WORDS):
            continue
        published_at = _parse_published(fields.get("pubdate"))
        if published_at is None or published_at < cutoff or published_at > current:
            continue
        url = _article_url(fields.get("link"), source=source)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        result.append({
            "title": title,
            "url": url,
            "source": source_name or "문화체육관광부",
            "published": published_at.date().isoformat(),
        })
        if result_limit is not None and len(result) >= result_limit:
            break
    return result


def get_recent_news(limit=3):
    """Return up to ``limit`` recent verified articles; fail closed to ``[]``."""
    try:
        result_limit = max(0, int(limit))
        if result_limit == 0:
            return []
        now = _now_seoul()
        with ThreadPoolExecutor(max_workers=len(_SOURCE_FEEDS)) as executor:
            futures = [
                executor.submit(_fetch_feed, feed_url)
                for _, feed_url, _ in _SOURCE_FEEDS
            ]
            feeds = []
            for (source, _, source_name), future in zip(_SOURCE_FEEDS, futures):
                try:
                    payload = future.result()
                    if source == "knto":
                        source_articles = _parse_knto_listing(
                            payload, now=now, limit=None, source_name=source_name
                        )
                    else:
                        source_articles = _parse_feed(
                            payload,
                            now=now,
                            limit=None,
                            source=source,
                            source_name=source_name,
                        )
                    feeds.extend(source_articles)
                except Exception:
                    logger.warning(
                        "Could not retrieve %s lodging news feed", source_name,
                        exc_info=True,
                    )
        feeds.sort(key=lambda item: item["published"], reverse=True)
        unique = []
        seen_urls = set()
        for article in feeds:
            if article["url"] in seen_urls:
                continue
            seen_urls.add(article["url"])
            unique.append(article)
            if len(unique) >= result_limit:
                break
        return unique
    except Exception:
        # News enrichment is optional: source outages must never block a digest.
        logger.warning("Could not retrieve lodging news", exc_info=True)
        return []