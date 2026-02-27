# GDELT Scraper Bundle (Can scrape from 2015 onwards)
## GDELT Terms of use: (https://www.gdeltproject.org/about.html#termsofuse)

Self-contained folder to scrape GDELT news articles for any year or range of years.
Runs on any machine with Python 3.8+.

## Contents

| File | Purpose |
|------|---------|
| `run.sh` | Entry point — installs deps and runs the pipeline |
| `run_pipeline.py` | Main pipeline: fetch → collect URLs → scrape → clean → merge → stats |
| `fetch_gdelt.py` | Downloads GDELT export files |
| `collect_urls_from_gdelt_exports.py` | Extracts article URLs from exports, with political filtering |
| `scrape_articles.py` | Scrapes article content from URLs |
| `normalize_and_cap_articles.py` | Normalizes outlet names |
| `clean_articles.py` | Cleans boilerplate from `merged_articles.csv` (run separately) |
| `domains_left_right_no_paywall.txt` | Domain → outlet/lean mapping |
| `requirements.txt` | Python dependencies |

## Requirements

- Python 3.8+

## Usage

```bash
On your terminal,
1.  run: `git clone https://github.com/okalmanwa/gdlet_scraper_1.0.git`
2. `cd gdelt_scrapper_1.0.git`
3. To scrape, choose any of the following options:
# Single year e.g 2020
bash run.sh --year 2020

# Range of years
bash run.sh --year-from 2018 --year-to 2022

# Single month
bash run.sh --month 2022-06

# Range of months
bash run.sh --month-from 2021-03 --month-to 2021-08

# Limit downloads per period (default: 4000)
bash run.sh --year 2021 --max-downloads 1000
bash run.sh --month 2023-01 --max-downloads 500

# Only scrape politically-coded articles (CAMEO roots 01–17)
bash run.sh --year 2022 --political-only
bash run.sh --month 2022-06 --political-only --max-downloads 500

# Skip GDELT download (use existing exports in results/gdelt/)
bash run.sh --year 2019 --skip-fetch
bash run.sh --month 2022-06 --skip-fetch
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--year` | — | Single year  e.g. `2020` |
| `--year-from` | — | Start of year range |
| `--year-to` | — | End of year range (inclusive) |
| `--month` | — | Single month  e.g. `2022-06` |
| `--month-from` | — | Start of month range  e.g. `2021-03` |
| `--month-to` | — | End of month range (inclusive)  e.g. `2021-08` |
| `--max-downloads` | 4000 | Max GDELT export files downloaded per period |
| `--political-only` | off | Only collect URLs with political CAMEO event codes (roots 01–17) |
| `--skip-fetch` | off | Skip download; use existing exports in `results/gdelt/` |

## Output

Results are written to `results/` (created automatically):

| File | Contents |
|------|----------|
| `results/gdelt_urls_<period>.csv` | Collected URLs per period (includes `event_code`, `event_label`) |
| `results/articles_scraped.csv` | Raw scraped articles from the most recent run |
| `results/merged_articles.csv` | Cumulative deduplicated master file (grows across runs) |
| `results/stats.csv` | Article counts per outlet / lean / event label / year |

### merged_articles.csv vs articles_scraped.csv

- **`articles_scraped.csv`** is overwritten on every run — it contains only the articles from the most recent period.
- **`merged_articles.csv`** is the cumulative master. Each run appends new articles (deduped by title + year + outlet). This is the file to use for analysis.

Both files include these columns:

| Column | Description |
|--------|-------------|
| `title` | Article headline |
| `year` | Publication year |
| `outlet` | Canonical outlet name |
| `lean` | Political lean (`left`, `right`, `mod`) |
| `content` | Full article text |
| `event_code` | CAMEO event code from GDELT |
| `event_label` | Human-readable label for the event code |
| `actor1_name` | Primary actor named in the GDELT event |
| `actor2_name` | Secondary actor named in the GDELT event |

## Adding New Sources

Edit `domains_left_right_no_paywall.txt` — one source per line:

```
domain.com,Outlet Name,lean
```

- `lean` must be one of: `left`, `right`, `mod`
- No restart needed; the pipeline reads the file on each run

Example:
```
apnews.com,AP News,mod
politico.com,Politico,left
thehill.com,The Hill,mod
```

## CAMEO Political Event Codes

When using `--political-only`, only articles linked to CAMEO event code roots 01–17 are collected:

| Root | Category |
|------|----------|
| 01 | Make Public Statement |
| 02 | Appeal |
| 03 | Express Intent to Cooperate |
| 04 | Consult |
| 05 | Diplomatic Cooperation |
| 06 | Material Cooperation |
| 07 | Provide Aid |
| 08 | Yield |
| 09 | Investigate |
| 10 | Demand |
| 11 | Disapprove / Criticize |
| 12 | Reject |
| 13 | Threaten |
| 14 | Protest |
| 15 | Exhibit Force Posture |
| 16 | Reduce Relations |
| 17 | Coerce |


Roots 18 (Assault), 19 (Fight), and 20 (Mass Violence) are excluded — those are conflict/military events rather than political discourse.
