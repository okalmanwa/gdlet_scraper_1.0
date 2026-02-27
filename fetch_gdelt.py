#!/usr/bin/env python3
"""
Fetch GDELT 2.0 export.CSV.zip files from masterfilelist by date range.

Usage:
  python fetch_gdelt.py --source masterfilelist --date-from 20150101 --date-to 20151231 --max-files 3000 --unzip --output-dir results/gdelt
"""

import argparse
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

MASTERFILELIST_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
BASE_URL = "http://data.gdeltproject.org/gdeltv2/"


def parse_date(s: str) -> datetime:
    s = s.strip().replace("-", "")[:8]
    if len(s) != 8:
        raise ValueError("Need YYYYMMDD")
    return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))


def get_export_urls_from_masterfilelist(date_from: str, date_to: str, max_files: int):
    date_from = date_from.strip()
    date_to = date_to.strip()
    if len(date_from) == 8:
        date_from += "000000"
    if len(date_to) == 8:
        date_to += "235959"
    count = 0
    req = Request(MASTERFILELIST_URL, headers={"User-Agent": "GDELT-fetch/1.0"})
    with urlopen(req, timeout=120) as r:
        for line in r:
            line = line.decode("utf-8", errors="replace").strip()
            if not line or "export.CSV.zip" not in line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            url = parts[2]
            m = re.search(r"(\d{14})\.export\.CSV\.zip", url)
            if not m:
                continue
            ts = m.group(1)
            if date_from <= ts <= date_to:
                yield url, ts
                count += 1
                if count >= max_files:
                    return


def get_export_url_from_lastupdate():
    req = Request(LASTUPDATE_URL, headers={"User-Agent": "GDELT-fetch/1.0"})
    with urlopen(req, timeout=30) as r:
        content = r.read().decode("utf-8", errors="replace")
    for line in content.strip().splitlines():
        if "export.CSV.zip" in line:
            parts = line.split()
            if len(parts) >= 3:
                url = parts[2]
                m = re.search(r"(\d{14})\.export\.CSV\.zip", url)
                if m:
                    return url, m.group(1)
    return None, None


def download_one(url: str, dest_dir: str, unzip_after: bool) -> bool:
    name = url.split("/")[-1]
    dest_zip = os.path.join(dest_dir, name)
    os.makedirs(dest_dir, exist_ok=True)
    try:
        req = Request(url, headers={"User-Agent": "GDELT-fetch/1.0"})
        with urlopen(req, timeout=300) as r:
            data = r.read()
        with open(dest_zip, "wb") as f:
            f.write(data)
        if unzip_after:
            with zipfile.ZipFile(dest_zip, "r") as zf:
                for member in zf.namelist():
                    zf.extract(member, dest_dir)
            try:
                os.remove(dest_zip)
            except OSError:
                pass
            print(f"    Unzipped to {dest_dir}")
        else:
            print(f"    {name}")
        return True
    except Exception as e:
        print(f"    [FAIL] {name}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Fetch GDELT 2.0 export.CSV.zip by date range from masterfilelist.")
    parser.add_argument("--source", choices=["masterfilelist", "lastupdate"], default="masterfilelist")
    parser.add_argument("--date-from", type=str, required=True)
    parser.add_argument("--date-to", type=str, required=True)
    parser.add_argument("--max-files", type=int, default=300)
    parser.add_argument("--output-dir", type=str, default="results/gdelt")
    parser.add_argument("--unzip", action="store_true")
    args = parser.parse_args()

    if args.source == "lastupdate":
        url, ts = get_export_url_from_lastupdate()
        if not url:
            print("No export URL in lastupdate.", file=sys.stderr)
            sys.exit(1)
        urls = [(url, ts)]
        print("Fetching 1 export from lastupdate...")
    else:
        urls = list(get_export_urls_from_masterfilelist(args.date_from, args.date_to, args.max_files))
        if not urls:
            print("No URLs in masterfilelist for this date range.", file=sys.stderr)
            print("GDELT 2.0 exports are only available from ~Feb 2015 onwards.", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(urls)} export.CSV.zip URL(s).")

    ok = 0
    for i, (url, ts) in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] Downloading {ts}.export.CSV.zip...")
        if download_one(url, args.output_dir, args.unzip):
            ok += 1
    print("Done.")


if __name__ == "__main__":
    main()
