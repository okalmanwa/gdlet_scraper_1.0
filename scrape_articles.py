#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import urlparse, urlunparse

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Install beautifulsoup4: pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

OUTPUT_COLUMNS = ["url", "title", "year", "outlet", "lean", "content", "event_code", "event_label"]

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 45
DEFAULT_RETRIES = 2

BOILERPLATE_STARTS = (
    "listen", "transcript", "toggle more options", "download", "embed", "share", "facebook", "flipboard", "email",
    "·", "copyright ©", "terms of use", "permissions", "privacy policy", "sponsored content", "popular reads",
    "interest successfully added", "we'll notify you", "turn on desktop notifications", "stream on", "off", "on",
    "abc news live", "24/7 coverage", "contact us", "do not sell or share", "your us state privacy rights",
    "children's online privacy policy", "interest-based ads", "about nielsen measurement", "featured weekly ad",
    "contributing:", "usa today brings you", "learn more at", "add topic", "medical marijuana", "news",
    "abc news", "video", "shows", "nan:nan", "bluesky", "print (opens in new window)", "print", "published:",
    "getting your", "trinity audio", "player ready", "revcontent feed", "abc news network",
    "interest-based ads", "©",
    "twitter", "threads", "close", "published", "add fox news on google", "add cnn on", "add nbc", "add reuters",
    "and", ", which includes our",
    "join fox news for access", "plus special access", "by entering your email", "notice of financial incentive",
    "please enter a valid email", "you can now listen to", "click to get the fox news app", "follow on twitter",
    "follow on x", "sign up for", "get the app", "more from fox news", "more from cnn", "more from nbc",
    "get the latest updates", "at our fox news digital", "election hub", "at our cnn ",
    "this article was written by",
    "now playing", "story highlights", "see more videos", "more on this...", "like us on",
    "watch live:",
    "follow us on", "best pix of the week", "related:",
    "continue", "close modal",
    "fox news flash top headlines", "click here to get the fox news app",
    "advertisement",
    "previous", "next",
)

LONG_BOILERPLATE_STARTS = (
    "plus special access", "by entering your email", "please enter a valid email",
    "you can now listen to", "join fox news for access", "notice of financial incentive",
    "click here to get the", "click to get the fox news app", "click here",
    "like what you're reading", "app users click here",
    "get the latest updates",
    "reports the latest on what's expected",
)

FOOTER_MARKERS = (
    "copyright ©", "all rights reserved", "terms of use", "privacy policy", "contact us",
    "sponsored content by taboola", "popular reads", "contributing:", "featured weekly ad",
    "abc news network", "revcontent feed", "usa today brings you", "learn more at", "rmpbs.org",
    "like us on", "follow us on", "instagram", "best pix of the week", "more on this...",
    "recommended articles", "recommended videos", "true crime", "close modal", "filed under",
)

SHORT_DATETIME_LINE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{1,2}:\d{2}\s*(AM|PM)?$", re.I)
FULL_DATETIME_LINE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\s+(\d{1,2}:\d{2}\s*(am|pm)\s*(EST|EDT|PST|PDT|CST|CDT)?)?$",
    re.I,
)
STANDALONE_OUTLET = re.compile(
    r"^(Fox News|CNN|NBC News|NY Times|Washington Post|Reuters|The Hill|WSJ|NY Post|MarketWatch|NPR)$",
    re.I,
)
AD_LINE_PATTERNS = (
    "page six",
    "eric dane's grieving wife, rebecca gayheart, seen for first time since actor's als death nypost",
    "eric dane's girlfriend breaks silence on 'grey's anatomy' star's death after heartbreaking als battle nypost",
    "homeland security suspends tsa precheck, global entry airport security programs",
    "fox news flash top headlines are here. check out what's clicking on foxnews.com.",
    "get more news",
    "related article",
)
AD_SHORT_LINES = frozenset(("updated", "associated press", "media", "(getty images)", "previous", "next", "ap", "epa"))
N_OF_N_LINE = re.compile(r"^\d+\s+of\s+\d+\s*$", re.I)
NOW_PLAYING_LINE = re.compile(r"^now\s+playing\s*[•·]\s*source\s*:?\s*$", re.I)
NOW_PLAYING_STANDALONE = re.compile(r"^now\s+playing\s*$", re.I)
LATEST_VIDEOS_LINE = re.compile(r"^latest\s+videos\s+\d+\s+videos?\s*$", re.I)
STORY_HIGHLIGHTS_LINE = re.compile(r"^story\s+highlights\s*$", re.I)
SEE_MORE_VIDEOS_LINE = re.compile(r"^see\s+more\s+videos\s*$", re.I)
N_VIDEOS_LINE = re.compile(r"^.+?\s+\d+\s+videos?\s*$", re.I)
ABBREV_DATETIME_TZ_LINE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4},?\s+\d{1,2}:\d{2}\s*(AM|PM)?\s*(EST|EDT|PST|PDT|CST|CDT)?\s*(/\s*)?$",
    re.I,
)
SOURCE_LINK_LINE = re.compile(r".*[•·]\s*Source\s*:?\s*$", re.I)
PHOTO_CREDIT_LINE = re.compile(
    r"^[^/]+\s*/\s*(Getty Images|AP|Reuters|AFP|USA Today|Bloomberg|CNN|TNS|Zuma|Anadolu|MediaNews Group|"
    r"The Denver Post|Columbus Dispatch|The Gazette|The TimesDaily|Tribune News Service|Corbis News)(\s*/\s*[^/]+)*\s*$",
    re.I,
)
PHOTO_CREDIT_SLASH_LINE = re.compile(
    r"^[A-Za-z\s\-\.']+\s+/\s+(AP|Reuters|AFP|Getty Images|Getty|USA Today|Bloomberg|TNS|Zuma|Anadolu|EPA|UPI)(\s*/\s*)?$",
    re.I,
)
SECTION_HEADERS = frozenset((
    "u.s. news", "world news", "us news", "health", "politics", "sports", "business",
    "entertainment", "tech", "science", "nation", "local", "opinion", "lifestyle",
))
AUTHOR_BYLINE_LINE = re.compile(r"^[A-Z][a-z]+\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s*,?\s*$")
CITATION_LINE_STARTS = ("courtesy ", "credit ", "photo: ", "image: ", "(courtesy ")
ATTRIBUTION_KEYWORDS = (
    "images", "stock photo", "alamy", "via getty", "getty images", "attribution",
    "shutterstock", "/getty", "/ap)", "reuters)", "ltd/", "inc/", "stock photo",
    "photo)", "image)", "photo credit", "image credit", "via reuters", "via ap",
)
REPORTER_BIO_LINE = re.compile(
    r"^.{10,280}\s+is\s+a\s+(\w+\s+)?reporter\s+.*(based\s+in|\.\s+He\s+covers|\.\s+She\s+covers|covers\s+the\s+).*",
    re.I,
)
REPORTER_BIO_FORMER_LINE = re.compile(
    r"^.{10,280}\s+is\s+a\s+former\s+.*reporter\s+for\s+.*",
    re.I,
)
AUTHOR_PIPE_LINE = re.compile(r"^[A-Z][a-z]+\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s*\|\s*$")
ALLCAPS_HEADLINE_LINE = re.compile(r"^[A-Z0-9\s\'\"\-\:,\.]+$")
CAPTION_LINE_STARTS = ("mug shot of", "photo composite showing", "photo showing", "photo of ")
CAPTION_PHRASE_IN = " poses for a photo "
CAPTION_PASS_BY = re.compile(r"^(cars|people|pedestrians|vehicles)\s+pass\s+by\s+.+", re.I)
CAPTION_BUILDING_AT_CENTER = re.compile(r".*\b(building at center|in downtown)\b.*[,.]\s*$", re.I)
RELATED_HEADLINE_PATTERNS = (" says ", " unveils ", " plan to ", " plan for ", " watch: ", " cam watch:", "meet the ")
VISIBLE_DATE_LINE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4},?\s+\d{1,2}:\d{2}\s*(AM|PM)?\s*(EST|EDT|PST|PDT|CST|CDT)?(\s*/\s*.*)?$",
    re.I,
)
BYLINE_BY_LINE = re.compile(r"^By\s+[A-Z][a-z]+\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s*\.?\s*$", re.I)
PHOTO_CAPTION_LOCATION_DATE = re.compile(r"^[A-Z][A-Z0-9\s,]+\s*-\s*[A-Z]+\s+\d{1,2}\s*:", re.I)
FOX_PUBLISHED_LINE = re.compile(
    r"^Published\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})\s+.*$",
    re.I,
)
FOX_CONTINUE_LINE = re.compile(r"^Continue\s*$", re.I)
FOX_BYLINE = re.compile(r"^By\s+.+?\s+Fox\s+News\s*\.?\s*$", re.I)
NYPOST_PUBLISHED_LINE = re.compile(
    r"^Published\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+(\d{4})\s*\.?\s*$",
    re.I,
)
NYPOST_UPDATED_LINE = re.compile(
    r"^Updated\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4},?\s+.*$",
    re.I,
)


def is_likely_article(content: str) -> bool:
    if not content or not content.strip():
        return False
    lines = [s.strip() for s in content.split("\n") if s.strip()]
    if len(lines) < 8:
        return True
    short = [s for s in lines if len(s) < 45]
    if len(lines) > 18 and len(short) / len(lines) >= 0.45:
        return False
    phrases = []
    for s in lines:
        words = s.split()
        for n in (3, 4, 2):
            for i in range(len(words) - n + 1):
                phrases.append(" ".join(words[i : i + n]).lower())
    if not phrases:
        return True
    most = Counter(phrases).most_common(1)[0]
    if most[1] >= 6 and len(lines) >= 20:
        return False
    return True


def clean_content(raw: str, title: str | None = None) -> str:
    if not raw or not raw.strip():
        return ""
    raw = re.sub(r"New York Cit\s+y\s+police", "New York City police", raw, flags=re.I)
    raw = re.sub(r"\bA\s+y\s*(?:City\s*)?police\b", "A New York City police", raw, flags=re.I)
    raw = re.sub(r"\bA\s+y\s+City\b", "A New York City", raw, flags=re.I)
    raw = re.sub(r"\bA\s*\n\s*New York City police", "A New York City police", raw, flags=re.I)
    raw = raw.replace("&#151;", "—").replace("&#8212;", "—")
    raw = raw.replace("\u2019", "'").replace("\u2018", "'")
    lines = raw.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        if s.startswith("<") or (s.startswith("iframe") and "src=" in s):
            continue
        if len(s) <= 2 and s in ("·", "·", "»", "•", "©", ".", "/"):
            continue
        if s.strip() in ("/", " / ", " /"):
            continue
        if len(s) <= 3 and s.lower() in ("by", "x", "off", "on"):
            continue
        if len(s) <= 4 and s.lower() in ("listen", "embed", "share", "live", "shop", "video", "shows"):
            continue
        if re.match(r"^\d{1,2}:\d{2}(\s*(AM|PM)\s*ET?)?$", s, re.I):
            continue
        if re.match(r"^\d{4}$", s):
            continue
        if FULL_DATETIME_LINE.match(s):
            continue
        if STANDALONE_OUTLET.match(s):
            continue
        if len(s) <= 5 and s.lower() == "new":
            continue
        if NOW_PLAYING_LINE.match(s):
            continue
        if NOW_PLAYING_STANDALONE.match(s):
            continue
        if LATEST_VIDEOS_LINE.match(s):
            continue
        if STORY_HIGHLIGHTS_LINE.match(s):
            continue
        if SEE_MORE_VIDEOS_LINE.match(s):
            continue
        if len(s) < 65 and N_VIDEOS_LINE.match(s):
            continue
        if ABBREV_DATETIME_TZ_LINE.match(s):
            continue
        if VISIBLE_DATE_LINE.match(s):
            continue
        if FOX_PUBLISHED_LINE.match(s):
            continue
        if NYPOST_PUBLISHED_LINE.match(s) or NYPOST_UPDATED_LINE.match(s):
            continue
        if FOX_CONTINUE_LINE.match(s):
            continue
        if 25 <= len(s) <= 120 and re.match(r"^[A-Z0-9\s\'\"\-\:\,\.]+$", s) and " " in s and not s.rstrip().endswith("."):
            continue
        if len(s) < 55 and BYLINE_BY_LINE.match(s):
            continue
        if len(s) < 80 and FOX_BYLINE.match(s):
            continue
        if SOURCE_LINK_LINE.match(s):
            continue
        if len(s) < 120 and PHOTO_CREDIT_LINE.match(s):
            continue
        if PHOTO_CREDIT_SLASH_LINE.match(s):
            continue
        lower = s.lower()
        if len(s) < 30 and (lower in SECTION_HEADERS or (lower.endswith(" news") and len(s) < 25)):
            continue
        if len(s) < 35 and AUTHOR_BYLINE_LINE.match(s):
            continue
        if len(s) < 35 and AUTHOR_PIPE_LINE.match(s):
            continue
        if 15 <= len(s) <= 130 and ALLCAPS_HEADLINE_LINE.match(s) and (":" in s or not s.rstrip().endswith(".")):
            continue
        if len(s) < 180:
            if any(lower.startswith(prefix) for prefix in CAPTION_LINE_STARTS):
                continue
            if CAPTION_PHRASE_IN in lower:
                continue
            if CAPTION_PASS_BY.match(s) or (len(s) < 120 and CAPTION_BUILDING_AT_CENTER.match(s)):
                continue
        if 25 <= len(s) <= 105 and not s.rstrip().endswith((".", "!", "?", '"', "'")):
            if any(p in lower for p in RELATED_HEADLINE_PATTERNS):
                continue
        if len(s) < 95 and ("reports the latest on what's expected" in lower or "reports the latest on what is expected" in lower):
            continue
        if len(s) < 85 and ("contributed to this report" in lower or "contributed to this story" in lower):
            continue
        if 25 <= len(s) <= 120 and (lower.endswith(": report") or lower.endswith(": report.")):
            continue
        if REPORTER_BIO_FORMER_LINE.match(s):
            continue
        if any(lower.startswith(prefix) for prefix in CITATION_LINE_STARTS):
            continue
        if len(s) < 60 and "(courtesy " in lower:
            continue
        if len(s) < 85 and ("courtesy of " in lower or "; courtesy " in lower) and not any(c in s for c in ".?!"):
            continue
        if len(s) < 120 and not any(c in s for c in ".?!"):
            if any(kw in lower for kw in ATTRIBUTION_KEYWORDS):
                if (s.startswith("(") and s.endswith(")")) or "/" in s:
                    continue
        if REPORTER_BIO_LINE.match(s):
            continue
        if any(lower.startswith(b) for b in LONG_BOILERPLATE_STARTS):
            continue
        if len(s) < 80 and any(lower == b or lower.startswith(b + " ") or lower.startswith(b) for b in BOILERPLATE_STARTS):
            continue
        if len(s) <= 10 and lower in ("politics", "news", "sports", "world", "opinion"):
            continue
        if lower.strip() in AD_SHORT_LINES:
            continue
        if N_OF_N_LINE.match(s.strip()):
            continue
        if len(s) <= 6 and lower.strip() == "media":
            continue
        if lower.strip() in AD_LINE_PATTERNS:
            continue
        if len(s) < 200 and any(ad in lower for ad in AD_LINE_PATTERNS):
            continue
        if ")" in s and s.rstrip().endswith(")"):
            r = s.rstrip()
            last_open = r.rfind("(")
            if last_open != -1:
                inner = r[last_open + 1 : -1]
                if len(inner) < 95 and any(kw in inner.lower() for kw in ATTRIBUTION_KEYWORDS):
                    s = r[:last_open].rstrip()
                    if not s:
                        continue
        out.append(s)

    out2 = []
    i = 0
    while i < len(out):
        line = out[i]
        nxt = out[i + 1].strip() if i + 1 < len(out) else ""
        if SHORT_DATETIME_LINE.match(line.strip()):
            i += 1
            continue
        if nxt and SHORT_DATETIME_LINE.match(nxt):
            i += 2
            continue
        out2.append(line)
        i += 1

    trimmed = []
    for s in out2:
        lower = s.lower()
        if any(m in lower for m in FOOTER_MARKERS):
            break
        trimmed.append(s)

    text = "\n".join(trimmed)
    lines = text.split("\n")
    while lines:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            continue
        lower = first.lower()
        is_junk = (
            PHOTO_CAPTION_LOCATION_DATE.match(first) or
            lower.startswith("updated ") or
            lower.startswith("originally published") or
            first.startswith("<") or
            (len(first) <= 20 and re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)?\s*ET?$", first, re.I)) or
            (len(first) <= 6 and re.match(r"^\d{1,2}:\d{2}$", first)) or
            re.match(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}$", first, re.I)
        )
        if is_junk:
            lines.pop(0)
            continue
        if len(lines) > 1:
            n = lines[1].strip().lower()
            next_junk = (
                n.startswith("updated ") or n.startswith("originally published") or
                re.match(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}$", lines[1].strip(), re.I)
            )
            if next_junk:
                lines.pop(0)
                continue
        if len(lines) > 1 and len(first) > 20 and first == lines[1].strip():
            lines.pop(0)
            continue
        if len(lines) > 1 and len(first) > 30 and re.match(r"^[A-Z][A-Za-z\s\']+, (HOST|BYLINE):", lines[1].strip()):
            lines.pop(0)
            continue
        if len(lines) > 1 and 15 <= len(first) <= 95 and first.rstrip().endswith("?"):
            second = lines[1].strip()
            if len(second) > 40 and not second.rstrip().endswith("?"):
                lines.pop(0)
                continue
        break

    text = "\n".join(lines).strip()
    lines = text.split("\n")
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if not nxt:
                i += 1
                continue
            last = line.rstrip()[-1] if line.rstrip() else ""
            first_ch = nxt[0] if nxt else ""
            if nxt.startswith('. "') or nxt.startswith('."') or (len(nxt) <= 3 and nxt.startswith(".")):
                line = line.rstrip() + " " + nxt.lstrip()
                i += 1
                continue
            if last in ".?!\"" and last != ",":
                break
            if first_ch.islower():
                line = line.rstrip() + " " + nxt
                i += 1
                continue
            if last == "," and len(nxt) < 55 and re.match(r"^[A-Z][a-z]+ (said|says),?\s*(according to\s+)?", nxt, re.I):
                line = line.rstrip() + " " + nxt
                i += 1
                continue
            if nxt.startswith("(") and len(nxt) < 80:
                line = line.rstrip() + " " + nxt
                i += 1
                continue
            if len(nxt) <= 35 and not re.match(r"^[A-Z][a-z]+", nxt):
                line = line.rstrip() + " " + nxt
                i += 1
                continue
            break
        merged.append(line)
        i += 1

    text = "\n".join(merged).strip()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"\s*&\s*\"?\s*$", "", text).strip()

    lines = text.split("\n")

    def _norm(s: str) -> str:
        return " ".join((s or "").strip().split())

    if title and title.strip():
        title_norm = _norm(title)
        while lines:
            first = lines[0].strip()
            if not first:
                lines.pop(0)
                continue
            first_norm = _norm(first)
            if first_norm == title_norm or (len(first_norm) > 15 and (title_norm in first_norm or first_norm in title_norm)):
                lines.pop(0)
                continue
            break

    while lines:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            continue
        if 15 <= len(first) <= 95 and first.rstrip().endswith("?"):
            second = lines[1].strip() if len(lines) > 1 else ""
            if len(second) > 40 and not second.rstrip().endswith("?"):
                lines.pop(0)
                continue
        break

    while lines and PHOTO_CAPTION_LOCATION_DATE.match(lines[0].strip()):
        lines.pop(0)

    if len(lines) >= 2:
        first = lines[0].strip()
        rest = "\n".join(lines[1:])
        if 20 <= len(first) <= 90 and first.rstrip().endswith(".") and first in rest:
            lines.pop(0)

    dateline = re.compile(r"^[A-Z][A-Z\s]+ —\s+")
    for i, line in enumerate(lines):
        if line.strip() and dateline.match(line.strip()):
            lines = lines[i:]
            break

    return "\n".join(lines).strip()


def safe_get_text(soup, selector: str) -> str:
    el = soup.select_one(selector)
    return (el.get_text(separator=" ", strip=True) if el else "") or ""


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else "http://" + url)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _normalize_fox_url(url: str) -> str:
    if not url or "foxnews.com" not in url.lower():
        return url
    try:
        parsed = urlparse(url if "://" in url else "http://" + url)
        path = parsed.path or ""
        new_path = re.sub(r"/\d{4}/\d{1,2}/\d{1,2}/", "/", path)
        new_path = re.sub(r"/+", "/", new_path)
        return urlunparse(("http", "foxnews.com", new_path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return url


def _fox_fallback_urls(url: str):
    if not url or "foxnews.com" not in url.lower():
        yield url
        return
    try:
        parsed = urlparse(url if "://" in url else "http://" + url)
        path = (parsed.path or "").rstrip("/")
        parts = path.split("/")
        if len(parts) < 2:
            yield url
            return
        slug = parts[-1]
        segs = slug.split("-")
        yield url
        slug_with_from = re.sub(r"-(\d+)(?=-|$)", r"-from-\1", slug)
        if slug_with_from != slug:
            new_path = "/".join(parts[:-1] + [slug_with_from])
            yield urlunparse(("http", "foxnews.com", new_path, parsed.params, parsed.query, parsed.fragment))
        for n in range(1, len(segs)):
            if len(segs) - n < 2:
                break
            short_slug = "-".join(segs[:-n])
            new_path = "/".join(parts[:-1] + [short_slug])
            yield urlunparse(("http", "foxnews.com", new_path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        yield url


TITLE_SUFFIX_PATTERN = re.compile(
    r"\s*[|\-–—]\s*"
    r"(CNN|Fox News|NBC News|NBC|Washington Post|The New York Times|NYT|Reuters|The Hill|WSJ|"
    r"Wall Street Journal|NY Post|New York Post|MarketWatch|NPR|CBS News|ABC News|USA Today|"
    r"Politico|Axios|AP News|BBC|CNN International|CNN Business)\s*$",
    re.I,
)


def _normalize_title(raw: str) -> str:
    if not raw or not raw.strip():
        return ""
    s = TITLE_SUFFIX_PATTERN.sub("", raw.strip())
    s = re.sub(r"\s*[|\-–—]\s*[A-Za-z0-9\s&.]+\s*$", "", s)
    return s.strip()[:2000] if s else ""


SECTION_LIKE_TITLES = frozenset((
    "cnn", "fox news", "nbc news", "home", "news", "politics", "video", "opinion",
    "u.s. news", "us news", "world news", "movies", "nbcblk", "breaking", "sports",
    "business", "health", "tech", "entertainment", "lifestyle", "nation", "local",
    "science", "weather", "investigations", "today", "nightly news", "dateline",
))


def _is_real_headline(text: str) -> bool:
    if not text or len(text) < 15 or len(text) > 250:
        return False
    if text.lower().strip() in SECTION_LIKE_TITLES:
        return False
    words = text.split()
    if len(words) <= 2 and sum(len(w) for w in words) < 20:
        return False
    return True


def _get_article_h1(soup) -> str:
    article = soup.find("article") or soup.find("main")
    if not article:
        return ""
    for sel in (".article-headline", ".article__headline", ".headline", ".post-title", "[data-editable='headline']", ".entry-title"):
        el = article.select_one(sel)
        if el:
            t = (el.get_text(strip=True) if el else "") or ""
            if _is_real_headline(t):
                return t
    for h1 in article.find_all("h1", limit=5):
        t = (h1.get_text(strip=True) if h1 else "") or ""
        if _is_real_headline(t):
            return t
    return ""


def extract_article(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "iframe", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(
        r"(?:^|\s)sidebar(?:\s|$)|(?:^|\s)sidebar-|ad-|share-buttons|social-share|footer|newsletter|comments?|(?<!-)video(?=\s|$)|carousel|playlist",
        re.I,
    )):
        tag.decompose()
    for tag in soup.find_all("header"):
        if tag.find_parent("article") is None:
            tag.decompose()

    title = _get_article_h1(soup)
    if title:
        title = _normalize_title(title)
    if not title:
        meta_og = soup.find("meta", property="og:title")
        if meta_og and meta_og.get("content"):
            title = _normalize_title((meta_og["content"] or "").strip())
    if not title:
        t = soup.find("title")
        title = _normalize_title((t.get_text(strip=True) if t else "") or "")

    domain = _domain_from_url(url)
    body = None
    if "cnn.com" in domain:
        body = soup.select_one(".article__content") or soup.select_one("[data-zone-label='articleBody']") or soup.select_one(".article__main .paragraph")
        if body and hasattr(body, "parent"):
            for sel in (".paragraph-inner", ".article__body"):
                inner = body.select_one(sel)
                if inner:
                    body = inner
                    break
    if "foxnews.com" in domain:
        body = (
            soup.select_one(".article-body") or soup.select_one("article .article-body") or soup.select_one("main .article-body")
            or soup.select_one(".article-body__content") or soup.select_one(".content-article .article-body")
        )
        if not body or (body and len((body.get_text(separator=" ", strip=True) or "").strip()) < 200):
            speakable_ps = soup.select("p.speakable")
            if speakable_ps:
                body = soup.new_tag("div")
                for p in speakable_ps:
                    body.append(p)
            else:
                body = soup.select_one(".speakable") or soup.select_one("article .speakable") or soup.select_one("main .speakable")
        if not body or (body and len((body.get_text(separator=" ", strip=True) or "").strip()) < 200):
            article_el = soup.find("article") or soup.find("main")
            if article_el:
                paras = article_el.find_all("p")
                if paras:
                    body = soup.new_tag("div")
                    for p in paras:
                        body.append(p)
    if "nypost.com" in domain:
        body = (
            soup.select_one(".single__content.entry-content") or soup.select_one(".single__content")
            or soup.select_one("article .entry-content") or soup.select_one(".entry-content")
            or soup.select_one(".post-content")
        )
        if not body or (body and len((body.get_text(separator=" ", strip=True) or "").strip()) < 200):
            article_el = soup.find("article") or soup.find("main")
            if article_el:
                paras = article_el.find_all("p")
                if paras:
                    body = soup.new_tag("div")
                    for p in paras:
                        body.append(p)
    if not body:
        body = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"article|content|post-body", re.I)) or soup.find("body")

    raw_body_text = ""
    if body:
        raw_body_text = body.get_text(separator="\n", strip=True)
        raw_body_text = re.sub(r"\n{3,}", "\n\n", raw_body_text)
    if not raw_body_text and soup.body:
        raw_body_text = soup.body.get_text(separator="\n", strip=True)
        raw_body_text = re.sub(r"\n{3,}", "\n\n", raw_body_text)
    if "foxnews.com" in domain and (not raw_body_text or raw_body_text.strip() in ("Continue", "")):
        article_el = soup.find("article") or soup.find("main")
        if article_el:
            paras = article_el.find_all("p")
            if paras:
                raw_body_text = "\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                raw_body_text = re.sub(r"\n{3,}", "\n\n", raw_body_text)

    content = clean_content(raw_body_text, title=title)

    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "article:author"})
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    published_at = ""
    meta_date = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"}) or soup.find("meta", attrs={"name": "publishdate"})
    if meta_date and meta_date.get("content"):
        published_at = meta_date["content"].strip()
    if not published_at and raw_body_text:
        fox_pub = re.search(r"Published\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})\s+", raw_body_text, re.I)
        if fox_pub:
            year = fox_pub.group(2)
            month_map = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                         "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
            m = month_map.get(fox_pub.group(1).lower()[:3], "01")
            d = re.search(r"Published\s+\w+\s+(\d{1,2})", raw_body_text, re.I)
            day = d.group(1).zfill(2) if d else "01"
            published_at = f"{year}-{m}-{day}T00:00:00"
        else:
            nypost_pub = re.search(r"Published\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+(\d{4})\b", raw_body_text, re.I)
            if nypost_pub:
                year = nypost_pub.group(2)
                month_map = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                             "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
                m = month_map.get(nypost_pub.group(1).lower()[:3], "01")
                d = re.search(r"Published\s+\w+\.?\s+(\d{1,2})", raw_body_text, re.I)
                day = (d.group(1).zfill(2) if d else "01")
                published_at = f"{year}-{m}-{day}T00:00:00"
            else:
                visible_date = re.search(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})",
                    raw_body_text, re.I,
                )
                if visible_date:
                    mo, day, year = visible_date.group(1), visible_date.group(2), visible_date.group(3)
                    month_map = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                                 "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
                    m = month_map.get(mo.lower()[:3], "01")
                    published_at = f"{year}-{m}-{day.zfill(2)}T00:00:00"

    return {
        "title": title[:2000] if title else "",
        "content": content[:500000] if content else "",
        "author": author[:500] if author else "",
        "description": description[:2000] if description else "",
        "published_at": published_at[:100] if published_at else "",
    }


def fetch_and_extract(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> dict | None:
    last_error = None
    urls_to_try = list(_fox_fallback_urls(url)) if url and "foxnews.com" in url.lower() else [url]
    for try_url in urls_to_try:
        for attempt in range(retries + 1):
            try:
                r = requests.get(try_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
                r.raise_for_status()
                return extract_article(try_url, r.text)
            except requests.exceptions.HTTPError as e:
                last_error = e
                if e.response is not None and e.response.status_code in (401, 403):
                    return {"error": f"{e.response.status_code} {e.response.reason}"}
                if e.response is not None and e.response.status_code == 404 and try_url != urls_to_try[-1]:
                    break
                if attempt < retries:
                    time.sleep(1 + attempt)
                else:
                    return {"error": str(e)}
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < retries:
                    time.sleep(1 + attempt)
                else:
                    return {"error": str(e)}
            except Exception as e:
                return {"error": str(e)}
    return {"error": str(last_error)}


def main():
    parser = argparse.ArgumentParser(description="Scrape articles from GDELT URLs CSV.")
    parser.add_argument("--urls-csv", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--skip", type=int, default=10000)
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--all-years", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    if not os.path.isfile(args.urls_csv):
        print(f"[ERROR] URLs CSV not found: {args.urls_csv}", file=sys.stderr)
        sys.exit(1)

    with open(args.urls_csv, encoding="utf-8", errors="replace") as f:
        all_rows = list(csv.DictReader(f))

    after_skip = all_rows[args.skip : args.skip + args.target]
    total = len(after_skip)
    print(f"URLs in CSV: {len(all_rows)}; skipping {args.skip}; scraping up to {total} articles.", file=sys.stderr)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    file_exists = os.path.isfile(args.output)
    write_header = not (args.append and file_exists)
    scraped = 0
    fail_401 = fail_403 = fail_timeout = fail_other = 0

    with open(args.output, "a" if (args.append and file_exists) else "w", newline="", encoding="utf-8") as out:
        writer = None
        for i, row in enumerate(after_skip):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            url = _normalize_fox_url(url)
            time.sleep(args.delay)
            extracted = fetch_and_extract(url, timeout=args.timeout, retries=args.retries)
            if extracted is None:
                continue
            if "error" in extracted:
                err = extracted["error"]
                if "401" in err:
                    fail_401 += 1
                elif "403" in err:
                    fail_403 += 1
                elif "timeout" in err.lower() or "timed out" in err.lower() or "Connection" in err:
                    fail_timeout += 1
                    print(f"  [{i+1}/{total}] FAIL {url[:60]}... {err}", file=sys.stderr)
                else:
                    fail_other += 1
                    print(f"  [{i+1}/{total}] FAIL {url[:60]}... {err}", file=sys.stderr)
                if (i + 1) % 500 == 0 and (fail_401 or fail_403):
                    print(f"  ... blocked so far: 401={fail_401}, 403={fail_403}", file=sys.stderr)
                continue
            published_at = (extracted.get("published_at") or "").strip()
            year_val = published_at[:4] if (published_at and len(published_at) >= 4 and published_at[:4].isdigit()) else (row.get("year") or "").strip()
            out_row = {
                "url": url,
                "title": (extracted.get("title") or "").strip(),
                "year": year_val,
                "outlet": (row.get("outlet") or "").strip(),
                "lean": (row.get("lean") or "").strip(),
                "content": (extracted.get("content") or "").strip(),
                "event_code": (row.get("event_code") or "").strip(),
                "event_label": (row.get("event_label") or "").strip(),
            }
            if writer is None:
                writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_NONNUMERIC)
                if write_header:
                    writer.writeheader()
            writer.writerow(out_row)
            scraped += 1
            print(f"  [{i+1}/{total}] OK scraped ({scraped} total)", file=sys.stderr)
        if fail_401 or fail_403:
            print(f"  Blocked/paywall (401: {fail_401}, 403: {fail_403}) — skipped.", file=sys.stderr)
    print(f"Done. Wrote {scraped} articles to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
