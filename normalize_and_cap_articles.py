#!/usr/bin/env python3
"""
Normalize outlet names in merged_articles.csv using domains_left_right_no_paywall.txt.
Writes results/merged_articles_normalized.csv.
"""

import argparse
import csv
import os
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAINS_FILE = os.path.join(SCRIPT_DIR, "domains_left_right_no_paywall.txt")


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
            if domain.startswith("www."):
                out[domain[4:]] = outlet
    return out


def normalize_outlet(s: str, outlet_map: dict) -> str:
    raw = (s or "").strip()
    return outlet_map.get(raw, outlet_map.get(raw.lower(), raw)) or raw or "unknown"


def main():
    parser = argparse.ArgumentParser(description="Normalize outlet names in a CSV.")
    parser.add_argument("--input", default="results/merged_articles.csv")
    parser.add_argument("--output", default="results/merged_articles_normalized.csv")
    parser.add_argument("--domains-file", default=DOMAINS_FILE)
    args = parser.parse_args()

    outlet_map = load_outlet_map(args.domains_file)
    rows = []
    with open(args.input, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            row["outlet"] = normalize_outlet(row.get("outlet", ""), outlet_map)
            rows.append(row)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        w.writeheader()
        w.writerows(rows)

    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        y = (row.get("year") or "").strip()
        o = (row.get("outlet") or "").strip()
        if y:
            counts[y][o] += 1

    print(f"Read {len(rows)} rows from {args.input}")
    print(f"Wrote {len(rows)} rows to {args.output}")
    print("\n--- Counts per (year, outlet) ---")
    for year in sorted(counts.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        total = sum(counts[year].values())
        parts = [f"{o}:{c}" for o, c in sorted(counts[year].items(), key=lambda x: -x[1])]
        print(f"{year} total={total}: {', '.join(parts)}")


if __name__ == "__main__":
    main()
