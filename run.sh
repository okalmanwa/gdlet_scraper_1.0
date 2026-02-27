#!/usr/bin/env bash
# -------------------------------------------------------
# run.sh  –  Bootstrap and run the GDELT scraper pipeline
#
# Usage:
#   bash run.sh --year 2020
#   bash run.sh --year-from 2018 --year-to 2022
#   bash run.sh --month 2022-06
#   bash run.sh --month-from 2021-03 --month-to 2021-08
#   bash run.sh --year 2021 --max-downloads 1000
#   bash run.sh --month 2023-01 --max-downloads 500
#   bash run.sh --year 2019 --skip-fetch
# -------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Checking Python 3..."
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Please install Python 3.8+."
  exit 1
fi
python3 --version

echo ""
echo "==> Installing dependencies..."
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r requirements.txt --quiet
echo "    Done."

echo "OKAL"
echo "==> Running pipeline..."
python3 run_pipeline.py "$@"
