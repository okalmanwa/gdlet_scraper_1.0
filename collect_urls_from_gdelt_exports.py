#!/usr/bin/env python3
"""
Collect URLs from GDELT 2.0 export CSVs, filtered by domains in --domains-file.
Outputs: url, year, outlet, lean, event_code, event_label, actor1_name, actor2_name, source
"""

import argparse
import csv
import os
import sys
from urllib.parse import urlparse

IDX_YEAR          = 3
IDX_ACTOR1NAME    = 6
IDX_ACTOR2NAME    = 16
IDX_EVENTCODE     = 26
IDX_EVENTBASECODE = 27
IDX_SOURCEURL     = 60

OUTPUT_COLUMNS = [
    "url", "year", "outlet", "lean", "event_code", "event_label",
    "actor1_name", "actor2_name", "source",
]

POLITICAL_ROOT_CODES = {
    "01", "02", "03", "04", "05", "06", "07", "08",
    "09", "10", "11", "12", "13", "14", "15", "16", "17",
}

CAMEO_ROOT_LABELS = {
    "01": "Make Public Statement", "02": "Appeal", "03": "Express Intent to Cooperate",
    "04": "Consult", "05": "Diplomatic Cooperation", "06": "Material Cooperation",
    "07": "Provide Aid", "08": "Yield", "09": "Investigate", "10": "Demand",
    "11": "Disapprove / Criticize", "12": "Reject", "13": "Threaten", "14": "Protest",
    "15": "Exhibit Force Posture", "16": "Reduce Relations", "17": "Coerce",
    "18": "Assault", "19": "Fight", "20": "Mass Violence",
}

CAMEO_LABELS = {
    "010": "Make statement", "011": "Decline comment", "012": "Make pessimistic comment",
    "013": "Make optimistic comment", "014": "Consider policy option", "015": "Claim responsibility",
    "016": "Deny responsibility", "017": "Symbolic act", "018": "Empathetic comment",
    "019": "Express accord", "020": "Appeal", "021": "Appeal for material cooperation",
    "022": "Appeal for diplomatic cooperation", "023": "Appeal for aid",
    "024": "Appeal for political reform", "025": "Appeal to yield",
    "026": "Appeal to meet or negotiate", "027": "Appeal to settle dispute",
    "028": "Appeal to accept mediation", "030": "Express intent to cooperate",
    "036": "Express intent to meet/negotiate", "037": "Express intent to settle dispute",
    "040": "Consult", "041": "Discuss by telephone", "042": "Make a visit",
    "043": "Host a visit", "044": "Meet at third location", "045": "Mediate", "046": "Negotiate",
    "050": "Diplomatic cooperation", "051": "Praise or endorse", "052": "Defend verbally",
    "053": "Rally support", "054": "Grant diplomatic recognition", "055": "Apologize",
    "057": "Sign formal agreement", "060": "Material cooperation", "061": "Cooperate economically",
    "062": "Cooperate militarily", "063": "Judicial cooperation", "064": "Share intelligence",
    "070": "Provide aid", "071": "Provide economic aid", "072": "Provide military aid",
    "073": "Provide humanitarian aid", "074": "Provide military protection", "075": "Grant asylum",
    "080": "Yield", "081": "Ease administrative sanctions", "082": "Ease political dissent",
    "083": "Accede to political reform demands", "084": "Return or release",
    "085": "Ease economic sanctions", "086": "Allow international involvement",
    "087": "De-escalate military engagement", "090": "Investigate",
    "091": "Investigate crime or corruption", "092": "Investigate human rights abuses",
    "093": "Investigate military action", "094": "Investigate war crimes",
    "100": "Demand", "101": "Demand information or investigation", "102": "Demand policy support",
    "103": "Demand aid or protection", "104": "Demand political reform", "105": "Demand mediation",
    "106": "Demand withdrawal", "107": "Demand ceasefire", "108": "Demand meeting or negotiation",
    "110": "Disapprove", "111": "Criticize or denounce", "112": "Accuse",
    "113": "Rally opposition", "114": "Complain officially", "115": "Bring lawsuit",
    "116": "Find guilty", "120": "Reject", "121": "Reject material cooperation",
    "122": "Reject request for aid", "123": "Reject request for political reform",
    "124": "Refuse to yield", "125": "Reject proposal to meet", "126": "Reject mediation",
    "127": "Reject settlement plan", "128": "Defy norms or law", "129": "Veto",
    "130": "Threaten", "131": "Threaten non-force", "132": "Threaten administrative sanctions",
    "133": "Threaten political dissent", "134": "Threaten to halt negotiations",
    "135": "Threaten to halt mediation", "136": "Threaten to halt international involvement",
    "137": "Threaten violent repression", "138": "Threaten military force", "139": "Give ultimatum",
    "140": "Protest", "141": "Demonstrate or rally", "142": "Hunger strike",
    "143": "Strike or boycott", "144": "Obstruct passage", "145": "Violent protest or riot",
    "150": "Demonstrate military power", "151": "Increase police alert",
    "152": "Increase military alert", "153": "Mobilize police", "154": "Mobilize armed forces",
    "160": "Reduce relations", "161": "Break diplomatic relations", "162": "Reduce or stop aid",
    "163": "Impose sanctions", "164": "Halt negotiations", "165": "Halt mediation",
    "166": "Expel or withdraw", "170": "Coerce", "171": "Seize or damage property",
    "172": "Impose administrative sanctions", "173": "Arrest or detain",
    "174": "Expel or deport", "175": "Violent repression", "180": "Assault",
    "181": "Abduct or take hostage", "182": "Physically assault", "183": "Bombing",
    "185": "Attempt assassination", "186": "Assassinate", "190": "Use military force",
    "191": "Impose blockade", "192": "Occupy territory", "193": "Fight with small arms",
    "194": "Fight with artillery", "195": "Aerial weapons", "196": "Violate ceasefire",
    "200": "Mass violence", "201": "Mass expulsion", "202": "Mass killings",
    "203": "Ethnic cleansing", "204": "Weapons of mass destruction",
}


def get_event_label(code: str) -> str:
    if not code:
        return ""
    if code in CAMEO_LABELS:
        return CAMEO_LABELS[code]
    if len(code) >= 3 and code[:3] in CAMEO_LABELS:
        return CAMEO_LABELS[code[:3]]
    if len(code) >= 2 and code[:2] in CAMEO_ROOT_LABELS:
        return CAMEO_ROOT_LABELS[code[:2]]
    return code


def is_political(code: str) -> bool:
    return bool(code) and code[:2] in POLITICAL_ROOT_CODES


def load_domains(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            domain = parts[0].lower().strip()
            if not domain:
                continue
            outlet = parts[1] if len(parts) >= 2 else domain
            lean = parts[2] if len(parts) >= 3 else "mod"
            out[domain] = (outlet, lean)
    return out


def domain_from_url(url: str):
    try:
        parsed = urlparse(url if "://" in url else "http://" + url)
        host = (parsed.netloc or parsed.path).lower()
        if not host:
            return None
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return None


def find_export_csvs(gdelt_dir: str, year_from=None, year_to=None):
    for root, _dirs, files in os.walk(gdelt_dir):
        for f in sorted(files):
            if not (f.endswith(".export.CSV") or f.endswith(".export.csv")):
                continue
            if year_from is not None or year_to is not None:
                if len(f) < 4:
                    continue
                try:
                    file_year = int(f[:4])
                    if year_from is not None and file_year < year_from:
                        continue
                    if year_to is not None and file_year > year_to:
                        continue
                except ValueError:
                    continue
            yield os.path.join(root, f)


def collect_urls(gdelt_dir, domains, add_outlet_lean, year_from=None, year_to=None, political_only=False):
    rows = []
    seen_urls = set()
    for csv_path in sorted(find_export_csvs(gdelt_dir, year_from, year_to)):
        n_before = len(rows)
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) <= IDX_SOURCEURL:
                    continue
                url = (parts[IDX_SOURCEURL] or "").strip()
                if not url or url in seen_urls:
                    continue
                domain = domain_from_url(url)
                if not domain or domain not in domains:
                    continue
                event_code = (parts[IDX_EVENTCODE] or "").strip() if len(parts) > IDX_EVENTCODE else ""
                event_base = (parts[IDX_EVENTBASECODE] or "").strip() if len(parts) > IDX_EVENTBASECODE else ""
                code = event_base or event_code
                if political_only and not is_political(code):
                    continue
                year = (parts[IDX_YEAR] or "").strip()
                if year_from is not None or year_to is not None:
                    try:
                        y = int(year)
                        if year_from is not None and y < year_from:
                            continue
                        if year_to is not None and y > year_to:
                            continue
                    except ValueError:
                        continue
                seen_urls.add(url)
                outlet, lean = domains[domain] if add_outlet_lean else (domain, "mod")
                actor1 = (parts[IDX_ACTOR1NAME] or "").strip() if len(parts) > IDX_ACTOR1NAME else ""
                actor2 = (parts[IDX_ACTOR2NAME] or "").strip() if len(parts) > IDX_ACTOR2NAME else ""
                rows.append({
                    "url": url, "year": year, "outlet": outlet, "lean": lean,
                    "event_code": code, "event_label": get_event_label(code),
                    "actor1_name": actor1, "actor2_name": actor2, "source": domain,
                })
        print(f"      {os.path.basename(csv_path)}: +{len(rows)-n_before} URLs (total {len(rows)})", file=sys.stderr)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Collect URLs from GDELT export CSVs filtered by domains.")
    parser.add_argument("--gdelt-dir", required=True)
    parser.add_argument("--domains-file", required=True)
    parser.add_argument("--add-outlet-lean", action="store_true")
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--political-only", action="store_true",
                        help="Only include URLs with political CAMEO event codes (roots 01-17)")
    args = parser.parse_args()

    if not os.path.isdir(args.gdelt_dir):
        print(f"[ERROR] Not a directory: {args.gdelt_dir}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.domains_file):
        print(f"[ERROR] Domains file not found: {args.domains_file}", file=sys.stderr)
        sys.exit(1)

    domains = load_domains(args.domains_file)
    if args.political_only:
        print(f"  [filter] Political CAMEO codes only (roots 01-17)", file=sys.stderr)
    rows = collect_urls(args.gdelt_dir, domains, args.add_outlet_lean,
                        args.year_from, args.year_to, args.political_only)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
