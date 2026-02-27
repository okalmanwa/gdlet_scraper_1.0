#!/usr/bin/env python3
"""
GDELT scraper pipeline: fetch exports, collect URLs, scrape articles, merge into master CSV.

Usage:
  python run_pipeline.py --year 2020
  python run_pipeline.py --year-from 2018 --year-to 2022
  python run_pipeline.py --month 2022-06
  python run_pipeline.py --month-from 2021-03 --month-to 2021-08
  python run_pipeline.py --year 2021 --max-downloads 1000
  python run_pipeline.py --month 2022-06 --political-only
"""

import argparse
import calendar
import csv
import glob
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(SCRIPT_DIR, "results")
GDELT_DIR = os.path.join(RESULTS, "gdelt")
ARTICLES_CSV = os.path.join(RESULTS, "articles_scraped.csv")
MERGED_CSV = os.path.join(RESULTS, "merged_articles.csv")
STATS_CSV = os.path.join(RESULTS, "stats.csv")
DOMAINS_FILE = os.path.join(SCRIPT_DIR, "domains_left_right_no_paywall.txt")
DEFAULT_MAX_DOWNLOADS = 4000

MERGED_COLS = ["title", "year", "outlet", "lean", "content", "event_code", "event_label", "actor1_name", "actor2_name"]


def load_outlet_map(domains_file: str) -> dict:
    out = {}
    with open(domains_file, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            domain = parts[0].lower()
            outlet = parts[1] if len(parts) >= 2 else domain
            out[domain] = outlet
            out[outlet] = outlet
            out[outlet.lower()] = outlet
    return out


OUTLET_MAP = load_outlet_map(DOMAINS_FILE)
TRAILING_SOURCES = set(OUTLET_MAP.keys())


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or SCRIPT_DIR)
    return r.returncode == 0


def normalize_outlet(s):
    raw = (s or "").strip()
    return OUTLET_MAP.get(raw, OUTLET_MAP.get(raw.lower(), raw)) or raw or "unknown"


def clean_title(t):
    s = (t or "").strip()
    if " | " not in s:
        return s
    left, right = s.rsplit(" | ", 1)
    right = right.strip()
    if right.lower() in TRAILING_SOURCES or (len(right) < 35 and " - " not in right):
        return left.strip()
    return s


def parse_month(s: str):
    s = s.strip().replace("-", "")
    if len(s) != 6:
        raise argparse.ArgumentTypeError(f"Month must be YYYY-MM or YYYYMM, got: {s}")
    try:
        return int(s[:4]), int(s[4:6])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid month: {s}")


def month_date_range(year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}{month:02d}01", f"{year}{month:02d}{last_day:02d}"


def process_period(label, date_from, date_to, year_filter, skip_fetch, max_downloads, political_only=False):
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"  Processing: {label}  ({date_from} → {date_to})", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    if not skip_fetch:
        print(f"[1] Fetching up to {max_downloads} exports ({date_from}–{date_to})...", file=sys.stderr)
        if not run([
            sys.executable, os.path.join(SCRIPT_DIR, "fetch_gdelt.py"),
            "--source", "masterfilelist",
            "--date-from", date_from, "--date-to", date_to,
            "--max-files", str(max_downloads), "--unzip", "--output-dir", GDELT_DIR,
        ]):
            print(f"Fetch failed for {label}.", file=sys.stderr)
            return False
    else:
        print(f"[1] Skipping fetch ({label}) — using existing exports.", file=sys.stderr)

    print(f"[2] Collecting URLs ({label})...", file=sys.stderr)
    safe_label = label.replace(" ", "_").replace(":", "-")
    urls_csv = os.path.join(RESULTS, f"gdelt_urls_{safe_label}.csv")
    year_from = int(date_from[:4])
    year_to = int(date_to[:4])
    collect_cmd = [
        sys.executable, os.path.join(SCRIPT_DIR, "collect_urls_from_gdelt_exports.py"),
        "--gdelt-dir", GDELT_DIR,
        "--domains-file", DOMAINS_FILE,
        "--add-outlet-lean",
        "--year-from", str(year_from), "--year-to", str(year_to),
        "--output", urls_csv,
    ]
    if political_only:
        collect_cmd.append("--political-only")
    if not run(collect_cmd):
        print(f"Collect failed for {label}.", file=sys.stderr)
        return False

    print(f"[3] Scraping articles ({label})...", file=sys.stderr)
    if not run([
        sys.executable, os.path.join(SCRIPT_DIR, "scrape_articles.py"),
        "--urls-csv", urls_csv, "--output", ARTICLES_CSV,
        "--skip", "0", "--append",
    ]):
        print(f"Scrape failed for {label}.", file=sys.stderr)
        return False

    print(f"[4] Deleting export files ({label})...", file=sys.stderr)
    removed = 0
    for pattern in (f"{date_from[:4]}*.export.CSV", f"{date_from[:4]}*.zip"):
        for path in glob.glob(os.path.join(GDELT_DIR, pattern)):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    print(f"  Deleted {removed} files.", file=sys.stderr)

    print(f"[5] Merging into {MERGED_CSV}...", file=sys.stderr)
    seen = set()
    merged_rows = []
    if os.path.isfile(MERGED_CSV):
        with open(MERGED_CSV, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                for col in MERGED_COLS:
                    row.setdefault(col, "")
                merged_rows.append(row)
                seen.add((
                    (row.get("title") or "").strip(),
                    (row.get("year") or "").strip(),
                    normalize_outlet(row.get("outlet", "")),
                ))

    added = 0
    with open(ARTICLES_CSV, "r", encoding="utf-8", newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            row_year = (row.get("year") or "").strip()
            try:
                if not (year_from <= int(row_year) <= year_to):
                    continue
            except ValueError:
                continue
            title = clean_title((row.get("title") or "").strip())
            outlet = normalize_outlet(row.get("outlet", ""))
            key = (title, row_year, outlet)
            if key in seen:
                continue
            seen.add(key)
            merged_rows.append({
                "title": title,
                "year": row_year,
                "outlet": outlet,
                "lean": (row.get("lean") or "").strip(),
                "content": (row.get("content") or "").strip(),
                "event_code": (row.get("event_code") or "").strip(),
                "event_label": (row.get("event_label") or "").strip(),
                "actor1_name": (row.get("actor1_name") or "").strip(),
                "actor2_name": (row.get("actor2_name") or "").strip(),
            })
            added += 1

    with open(MERGED_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MERGED_COLS, quoting=csv.QUOTE_NONNUMERIC)
        w.writeheader()
        w.writerows(merged_rows)

    print(f"  Merged: {len(merged_rows)} total rows (+{added} new). Done.", file=sys.stderr)

    print(f"[6] Cleaning {MERGED_CSV}...", file=sys.stderr)
    if not run([sys.executable, os.path.join(SCRIPT_DIR, "clean_articles.py"), "--input", MERGED_CSV]):
        print(f"  Clean step failed for {label}.", file=sys.stderr)
    return True


def generate_stats():
    if not os.path.isfile(MERGED_CSV):
        print("  [stats] No merged CSV found, skipping.", file=sys.stderr)
        return

    from collections import defaultdict

    per_year_outlet = defaultdict(int)
    per_label_outlet = defaultdict(int)
    lean_map = {}

    with open(MERGED_CSV, "r", encoding="utf-8", newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            year = (row.get("year") or "").strip()
            outlet = (row.get("outlet") or "").strip() or "Unknown"
            lean = (row.get("lean") or "").strip() or "unknown"
            label = (row.get("event_label") or "").strip() or "—"
            lean_map[outlet] = lean
            per_year_outlet[(year, outlet)] += 1
            per_label_outlet[(year, outlet, label)] += 1

    stat_rows = []
    for (year, outlet, label), count in sorted(per_label_outlet.items()):
        stat_rows.append({"year": year, "outlet": outlet, "lean": lean_map.get(outlet, ""), "event_label": label, "count": count})

    for (year, outlet), count in sorted(per_year_outlet.items()):
        stat_rows.append({"year": year, "outlet": outlet, "lean": lean_map.get(outlet, ""), "event_label": "ALL", "count": count})

    overall_outlet = defaultdict(int)
    overall_label = defaultdict(lambda: defaultdict(int))
    for (year, outlet), count in per_year_outlet.items():
        overall_outlet[outlet] += count
    for (year, outlet, label), count in per_label_outlet.items():
        overall_label[outlet][label] += count

    for outlet, count in sorted(overall_outlet.items()):
        stat_rows.append({"year": "ALL", "outlet": outlet, "lean": lean_map.get(outlet, ""), "event_label": "ALL", "count": count})
        for label, cnt in sorted(overall_label[outlet].items()):
            stat_rows.append({"year": "ALL", "outlet": outlet, "lean": lean_map.get(outlet, ""), "event_label": label, "count": cnt})

    stat_rows.sort(key=lambda r: (0 if r["year"] == "ALL" else 1, r["year"], r["outlet"], r["event_label"]))

    with open(STATS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "outlet", "lean", "event_label", "count"])
        w.writeheader()
        w.writerows(stat_rows)

    total = sum(overall_outlet.values())
    print(f"  [stats] Wrote {len(stat_rows)} rows to {STATS_CSV}  (total articles: {total})", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="GDELT scraper pipeline — year, year range, month, or month range.")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--year", type=int, help="Single year  e.g. 2020")
    mode.add_argument("--year-from", type=int, help="Start year of range  e.g. 2018")
    mode.add_argument("--month", type=str, metavar="YYYY-MM", help="Single month  e.g. 2022-06")
    mode.add_argument("--month-from", type=str, metavar="YYYY-MM", help="Start month of range  e.g. 2021-03")

    p.add_argument("--year-to", type=int, help="End year (inclusive, use with --year-from)")
    p.add_argument("--month-to", type=str, metavar="YYYY-MM", help="End month (inclusive, use with --month-from)  e.g. 2021-08")
    p.add_argument("--max-downloads", type=int, default=DEFAULT_MAX_DOWNLOADS,
                   help=f"Max GDELT export files to download per period (default: {DEFAULT_MAX_DOWNLOADS})")
    p.add_argument("--political-only", action="store_true",
                   help="Only scrape articles with political CAMEO event codes (roots 01-17)")
    p.add_argument("--skip-fetch", action="store_true", help="Skip download; use existing exports in results/gdelt/")
    args = p.parse_args()

    periods = []
    if args.year:
        periods.append((str(args.year), f"{args.year}0101", f"{args.year}1231", args.year))
    elif args.year_from:
        year_to = args.year_to or args.year_from
        for y in range(args.year_from, year_to + 1):
            periods.append((str(y), f"{y}0101", f"{y}1231", y))
    elif args.month:
        y, m = parse_month(args.month)
        df, dt = month_date_range(y, m)
        periods.append((f"{y}-{m:02d}", df, dt, y))
    elif args.month_from:
        y_start, m_start = parse_month(args.month_from)
        y_end, m_end = parse_month(args.month_to) if args.month_to else (y_start, m_start)
        y, m = y_start, m_start
        while (y, m) <= (y_end, m_end):
            df, dt = month_date_range(y, m)
            periods.append((f"{y}-{m:02d}", df, dt, y))
            m += 1
            if m > 12:
                m = 1
                y += 1

    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(GDELT_DIR, exist_ok=True)

    print(f"Periods to process: {[p[0] for p in periods]}", file=sys.stderr)
    print(f"Max downloads per period: {args.max_downloads}", file=sys.stderr)
    if args.political_only:
        print("Filter: political CAMEO codes only (roots 01-17)", file=sys.stderr)

    failed = []
    for label, date_from, date_to, year_filter in periods:
        ok = process_period(label, date_from, date_to, year_filter, args.skip_fetch, args.max_downloads, args.political_only)
        if not ok:
            failed.append(label)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Done. Processed {len(periods)} period(s).", file=sys.stderr)
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
    else:
        print("All periods completed successfully.", file=sys.stderr)

    print(f"\n[stats] Generating stats from {MERGED_CSV}...", file=sys.stderr)
    generate_stats()



if __name__ == "__main__":
    main()
