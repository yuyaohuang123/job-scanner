"""Find a firm's Workday tenant and site id from its name alone.

    python tools/discover_workday.py names.txt out.json

Site ids cannot be guessed blind -- that was established early on, when every
obvious candidate missed against a known tenant. But the search space is far
smaller than it looks, because it factors into three cheap steps:

1. Tenant + data centre. One request to a deliberately bogus site id tells
   them apart: a real tenant answers 404 naming `Job_Posting_Site_ID`, while a
   tenant that doesn't exist answers 422 with an empty message.

   (DNS is NOT usable for this, which cost me an hour: *.myworkdayjobs.com is
   a wildcard, so nonsense12345.wd3.myworkdayjobs.com resolves perfectly
   happily. An earlier version of this tool sieved on DNS, let everything
   through, and brute-forced site ids against every guess.)
2. Site id. Against a live tenant the CXS endpoint answers 404 with a
   `Job_Posting_Site_ID` message for a wrong site and 200 for a right one, so a
   candidate list settles it in a handful of requests. Most tenants use one of
   a dozen conventions ("External", "{Tenant}Careers", "Early_Careers", ...).
3. Confirmation. A hit is only reported once the board actually returns
   postings, so a site that exists but is empty doesn't become config.

Nothing here is guesswork by the time it reaches firms.yml: every hit has been
fetched from.
"""

import json
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import filters  # noqa: E402
from scanner.adapters.workday import HEADERS, discover_facets  # noqa: E402

# Workday spreads tenants across numbered data centres; these are the ones
# that actually show up for large employers.
# Every large tenant verified so far sits on one of these; the long tail
# (wd103, wd105, wd108) is rare enough that probing it triples the DNS cost
# for almost no return. Add one back if a known firm is being missed.
DATA_CENTRES = ["wd1", "wd3", "wd5", "wd2", "wd12", "wd10"]

STOP = {"the", "and", "group", "plc", "ltd", "limited", "inc", "co", "company",
        "holdings", "international", "uk", "global", "corporation", "corp"}

SITE_PATTERNS = [
    "External", "Careers", "External_Careers", "ExternalCareers",
    "{T}Careers", "{T}_Careers", "{T}", "{T}_External", "{T}External",
    "Global_Careers", "GlobalCareers", "{T}_Careers_Site", "Careers_External",
    "Early_Careers", "EarlyCareers", "{T}EarlyCareers", "{T}_Early_Careers",
    "Students", "Campus", "University", "Graduates", "Early_Talent",
    "{T}_Professional", "Professional", "jobs", "Jobs", "{T}_jobs",
    "{T}_Careers_External", "CareersSite", "{T}CareerSite", "{T}_Career_Site",
    # Barclays-style verbose names, and the "CareersatX" convention.
    "External_Career_Site_{T}", "External_Career_Site", "Careersat{T}",
    "{T}_Website", "{T}Website", "{T}_Talent", "{T}_Recruiting",
]


def slug_variants(name):
    base = "".join(c for c in name.lower() if c.isalnum() or c in " -")
    words = [w for w in base.replace("-", " ").split() if w]
    core = [w for w in words if w not in STOP] or words
    out, seen = [], set()
    for v in ("".join(core), "".join(words), core[0] if core else "",
              "".join(core[:2]), "-".join(core)):
        if v and len(v) >= 2 and v not in seen:
            seen.add(v); out.append(v)
    return out[:3]


BOGUS_SITE = "ZZZNotARealSite"


def _tenant_exists(candidate):
    """One request: 404 naming Job_Posting_Site_ID means the tenant is real."""
    host, slug = candidate
    try:
        r = requests.post(
            f"https://{host}/wday/cxs/{slug}/{BOGUS_SITE}/jobs",
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            headers=HEADERS, timeout=15,
        )
    except requests.RequestException:
        return False
    return r.status_code == 404 and "Job_Posting_Site_ID" in r.text


def find_hosts(name, pool):
    """Return (host, tenant) pairs whose tenant actually exists."""
    candidates = [(f"{slug}.{dc}.myworkdayjobs.com", slug)
                  for slug in slug_variants(name) for dc in DATA_CENTRES]
    results = pool.map(_tenant_exists, candidates)
    return [c for c, ok in zip(candidates, results) if ok]


def find_site(host, tenant, session):
    """Brute-force the site id against a live tenant."""
    tried = set()
    for pattern in SITE_PATTERNS:
        site = pattern.replace("{T}", tenant.capitalize()) if "{T}" in pattern else pattern
        if site in tried:
            continue
        tried.add(site)
        try:
            r = session.post(
                f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                headers=HEADERS, timeout=20,
            )
        except requests.RequestException:
            continue
        if r.status_code == 200:
            try:
                total = r.json().get("total", 0)
            except ValueError:
                continue
            if total:
                return site, total
        time.sleep(0.15)
    return None, 0


def run(names, out_path=None):
    session = requests.Session()
    hits = []
    pool = ThreadPoolExecutor(max_workers=8)
    for name in names:
        for host, tenant in find_hosts(name, pool):
            site, total = find_site(host, tenant, session)
            if not site:
                continue
            firm = {"name": name, "host": host, "tenant": tenant, "site": site}
            try:
                found = discover_facets(firm, session=session)
            except (requests.RequestException, ValueError):
                found = {}
            hits.append({**firm, "total": total, "facets": {
                k: v for k, v in found.items() if k in ("intern", "country")}})
            print(f"HIT  {name:<26} {host:<42} site={site:<28} total={total}", flush=True)
            break
    print(f"\n=== DONE: {len(hits)} tenants found for {len(names)} names ===")
    if out_path:
        json.dump(hits, open(out_path, "w"), indent=2, default=str)
    return hits


if __name__ == "__main__":
    names = [l.strip() for l in open(sys.argv[1], encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    run(names, sys.argv[2] if len(sys.argv) > 2 else None)
