#!/usr/bin/env python3
"""
Clean merged_articles.csv — strips outlet boilerplate, drops short/empty/duplicate rows.

Usage:
  python clean_articles.py
  python clean_articles.py --output results/merged_articles_clean.csv
  python clean_articles.py --min-words 30
"""

import argparse
import csv
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "results", "merged_articles.csv")
MIN_WORDS_DEFAULT = 20

OUTPUT_COLS = [
    "title", "year", "outlet", "lean", "content",
    "event_code", "event_label", "actor1_name", "actor2_name",
]

BBC_COPY_LINK = re.compile(r"^Copy link\s*\n.*?(?=\n\S)", re.IGNORECASE | re.DOTALL)
BBC_SAVE = re.compile(r"^Save(?:\s+\S+)?\s*\n", re.IGNORECASE)
BBC_IMAGE_LINE = re.compile(
    r"^Image\s+source\s*,.*$\n?|^Image\s+caption\s*,.*$\n?|^Image\s+source\s*$\n?|^Image\s+caption\s*$\n?",
    re.IGNORECASE | re.MULTILINE,
)
BBC_MEDIA_CAPTION = re.compile(r"^Media\s+caption\s*,.*$\n?", re.IGNORECASE | re.MULTILINE)
BBC_FOOTER = re.compile(r"\n(?:Related\s+topics|More\s+on\s+this\s+story)\b.*$", re.IGNORECASE | re.DOTALL)
BBC_ENGAGEMENT = re.compile(r"Have you been affected[^\n]*\n(?:.*\n){0,8}", re.IGNORECASE)
CNN_NEWSLETTER = re.compile(r"^A version of this story appeared in CNN[^\n]*\n(?:.*\n)?", re.IGNORECASE)
FOX_PROMO = re.compile(r"^[A-Z][^\n]{5,120}(?:on\s+'[^']+'\.|Fox\s+News\s+Digital|Fox\s+Report)[^\n]*\n", re.MULTILINE)
NEWSLETTER_CTA = re.compile(r"Sign up (?:here )?to get[^\n]*\n?", re.IGNORECASE)
LEADING_TIMESTAMP = re.compile(r"^(\s*(?:\d{1,2}:\d{2}\s*)?(?:am|pm)\s*ET\s*)+", re.IGNORECASE)
LEADING_FILE = re.compile(r"^(?:FILE\s*:\s*UNDATED\s*:\s*|FILE\s*:\s*|FILE\s*-\s*-\s*[,\s]*|FILE\s*-\s+)", re.IGNORECASE)
LEADING_IMAGE_COUNT = re.compile(r"^Image\s+\d+\s+of\s+\d+\s*(?:FILE\s*-\s*)?[,.]?\s*", re.IGNORECASE)
LEADING_PHOTO = re.compile(r"^'?\(?Photo\s+courtesy[^)'\n]*[)']?\)?\s*", re.IGNORECASE)
LEADING_NEW = re.compile(r"^NEW\s*:\s*", re.IGNORECASE)
LEADING_BYLINE = re.compile(r"^(?:By\s+The\s+New\s+York\s+Times|The\s+New\s+York\s+Times|---)\s*\n?", re.IGNORECASE)
LEADING_DATELINE = re.compile(r"^[A-Z][A-Z ,\.]{2,40}(?:\([A-Z]+\))?\s*[—–-]\s+")
LEADING_SPECIAL = re.compile(r'^[^\w\'"(]+')
TRAILING_OUTLET = re.compile(
    r"\s*[—–\-]\s*(?:CNN|Fox\s*News|NBC\s*News|BBC|NYTimes|New\s+York\s+Times|AP|Reuters)[\s.]*$",
    re.IGNORECASE,
)
PARENS = re.compile(r"\([^)]{0,200}\)")
MULTI_BLANK = re.compile(r"\n{3,}")


def _strip_leading_loop(s: str) -> str:
    patterns = [LEADING_TIMESTAMP, LEADING_FILE, LEADING_IMAGE_COUNT, LEADING_PHOTO,
                LEADING_NEW, LEADING_BYLINE, LEADING_DATELINE, LEADING_SPECIAL]
    for _ in range(10):
        prev = s
        for p in patterns:
            s = p.sub("", s).strip()
        if s == prev:
            break
    return s


def _strip_trailing_tags(s: str) -> str:
    for _ in range(20):
        prev = s
        lines = s.split("\n")
        while lines:
            last = lines[-1].strip()
            if not last:
                lines.pop()
                continue
            if len(last.split()) <= 5 and not last.endswith((".", "?", "!", '"', "'")):
                lines.pop()
            else:
                break
        s = "\n".join(lines).strip()
        if s == prev:
            break
    return s


def clean_content(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()
    s = BBC_COPY_LINK.sub("", s).strip()
    s = BBC_SAVE.sub("", s).strip()
    s = CNN_NEWSLETTER.sub("", s).strip()
    s = BBC_FOOTER.sub("", s).strip()
    s = BBC_ENGAGEMENT.sub("", s).strip()
    s = NEWSLETTER_CTA.sub("", s).strip()
    s = BBC_IMAGE_LINE.sub("", s)
    s = BBC_MEDIA_CAPTION.sub("", s)
    s = FOX_PROMO.sub("", s)
    s = PARENS.sub("", s)
    s = TRAILING_OUTLET.sub("", s).strip()
    s = _strip_leading_loop(s)
    lines = s.split("\n")
    if len(lines) >= 2:
        first = lines[0].strip()
        if len(first.split()) <= 5 and first and first[0].isupper() and not first.endswith("."):
            s = "\n".join(lines[1:]).strip()
    s = _strip_trailing_tags(s)
    return MULTI_BLANK.sub("\n\n", s).strip()


def main():
    parser = argparse.ArgumentParser(description="Clean merged_articles.csv — strips boilerplate, drops short/empty rows.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=None, help="Output CSV (default: overwrite input)")
    parser.add_argument("--min-words", type=int, default=MIN_WORDS_DEFAULT)
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output or input_path

    if not os.path.isfile(input_path):
        print(f"[ERROR] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    seen = set()
    total = dropped_empty = dropped_short = dropped_dup = cleaned = 0
    rows_out = []

    with open(input_path, "r", encoding="utf-8", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        input_cols = reader.fieldnames or []
        for row in reader:
            total += 1
            out = {c: (row.get(c) or "").strip() for c in input_cols}
            for c in OUTPUT_COLS:
                out.setdefault(c, "")
            raw = out["content"]
            cleaned_content = clean_content(raw)
            out["content"] = cleaned_content
            if not cleaned_content:
                dropped_empty += 1
                continue
            if len(cleaned_content.split()) < args.min_words:
                dropped_short += 1
                continue
            if cleaned_content != raw:
                cleaned += 1
            key = (out["title"], out["year"], out["outlet"])
            if key in seen:
                dropped_dup += 1
                continue
            seen.add(key)
            rows_out.append(out)

    extra_cols = [c for c in input_cols if c not in OUTPUT_COLS]
    final_cols = OUTPUT_COLS + extra_cols
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_cols, quoting=csv.QUOTE_NONNUMERIC, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)

    print(
        f"Done.\n"
        f"  Read:              {total}\n"
        f"  Content cleaned:   {cleaned}\n"
        f"  Dropped (empty):   {dropped_empty}\n"
        f"  Dropped (<{args.min_words} words): {dropped_short}\n"
        f"  Dropped (dup):     {dropped_dup}\n"
        f"  Wrote:             {len(rows_out)}  →  {output_path}"
    )


if __name__ == "__main__":
    main()
