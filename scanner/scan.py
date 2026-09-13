"""Daily scan entrypoint.

    python -m scanner.scan               # scan, update store, regenerate site
    python -m scanner.scan --dry-run     # scan and report, write nothing
    python -m scanner.scan --firm Barclays

Designed to fail soft: one firm's API going down must not lose the run. Errors
are collected and reported, and a firm that failed keeps its existing listings
rather than having them marked closed.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import requests
import yaml

from . import filters, store
from .adapters import build as build_adapter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "scanner", "config", "firms.yml")
STORE_PATH = os.path.join(ROOT, "data", "listings.json")
SITE_DATA_PATH = os.path.join(ROOT, "site", "data.js")
DIGEST_PATH = os.path.join(ROOT, "data", "last_digest.json")


def load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def scan_firm(firm, session, delay, known=None):
    """Return (postings, error). Postings are already filtered to our criteria.

    `known` maps listing keys to records already in the store; a posting whose
    location was resolved on a previous run reuses it rather than fetching the
    detail page again (GradConnection would otherwise cost ~140 fetches a day).
    """
    known = known or {}
    adapter = build_adapter(firm, session=session, delay=delay)
    if adapter is None:
        return [], f"no adapter for platform {firm.get('platform')!r}"

    kept = []
    try:
        raw_postings = list(adapter.fetch())
    except requests.RequestException as exc:
        return [], f"request failed: {exc}"
    except ValueError as exc:
        return [], f"bad response: {exc}"

    for posting in raw_postings:
        # Cheap check first: if the title can't be a match, don't spend a
        # request resolving its location.
        category = filters.classify_role(posting["title"], posting.get("worker_sub_type"))
        if not category or filters.is_excluded(posting["title"]):
            continue

        if posting.get("location_is_vague"):
            prior = known.get(store.listing_key(firm["name"], posting))
            if prior and prior.get("location") and not prior.get("location_is_vague"):
                posting["location"] = prior["location"]
                posting["location_is_vague"] = False
            else:
                posting = adapter.resolve_location(posting)

        ok, category, region = filters.keep(posting)
        if not ok:
            continue

        posting["firm"] = firm["name"]
        posting["tier"] = firm.get("tier", "Other")
        posting["platform"] = firm.get("platform", "")
        posting["category"] = category
        posting["region"] = region
        kept.append(posting)

    return kept, None


def run(config, only_firm=None, dry_run=False):
    session = requests.Session()
    delay = (config.get("defaults") or {}).get("delay", 1.0)

    scanned = {}
    scanned_firms = set()
    errors = []
    per_firm_counts = {}

    firms = [f for f in config.get("firms", []) if f.get("enabled")]
    if only_firm:
        firms = [f for f in firms if f["name"].lower() == only_firm.lower()]
        if not firms:
            print(f"No enabled firm named {only_firm!r}", file=sys.stderr)
            return 1

    skipped = [f["name"] for f in config.get("firms", []) if not f.get("enabled")]

    known = store.load(STORE_PATH)["listings"]
    for firm in firms:
        print(f"-> {firm['name']} ({firm.get('platform')})", flush=True)
        postings, error = scan_firm(firm, session, delay, known)

        if error:
            errors.append((firm["name"], error))
            print(f"   ERROR: {error}", file=sys.stderr)
            continue

        scanned_firms.add(firm["name"])
        per_firm_counts[firm["name"]] = len(postings)
        for posting in postings:
            scanned[store.listing_key(firm["name"], posting)] = posting
        print(f"   {len(postings)} matching listing(s)")

    current = store.load(STORE_PATH)
    new_items, closed_items = store.reconcile(current, scanned, scanned_firms)

    print("\n" + "=" * 60)
    print(f"matched:  {len(scanned)} listings across {len(scanned_firms)} firm(s)")
    print(f"new:      {len(new_items)}")
    print(f"closed:   {len(closed_items)}")
    if skipped:
        print(f"skipped:  {len(skipped)} firm(s) not yet configured")
    if errors:
        print(f"errors:   {len(errors)}")
        for name, error in errors:
            print(f"          {name}: {error}")

    if new_items:
        print("\nNew since last run:")
        for item in new_items:
            print(f"  [{item['region'].upper()}] {item['firm']} - {item['title']}")
            print(f"        {item['location']}")

    if dry_run:
        print("\n(dry run: nothing written)")
        return 0

    # Order matters. On 2026-09-13 the site writer crashed on a bad date and
    # the digest payload was never written, so 267 new listings were saved to
    # the store but never emailed. Persist the store, then the digest payload,
    # and only then render the site -- the least important output goes last.
    store.save(STORE_PATH, current)
    write_digest_payload(new_items, closed_items, errors, per_firm_counts)
    write_site_data(current)
    print(f"\nwrote {STORE_PATH}")
    print(f"wrote {SITE_DATA_PATH}")
    return 0


def _looks_like_date(value):
    """True for ISO-ish date strings. Workday gives 'Posted Today'; Oracle
    gives 2026-09-12; Lever once gave an integer, which took the run down."""
    return (
        isinstance(value, str)
        and len(value) >= 10
        and value[4] == "-"
        and value[7] == "-"
    )


def write_site_data(current):
    """Regenerate the tracker's data file.

    Emitted as a .js assigning a global rather than .json fetched at runtime,
    so the site still works when opened straight off disk -- fetch() against a
    file:// URL is blocked by CORS, a plain <script> tag is not.
    """
    grouped = defaultdict(list)
    for record in store.open_listings(current):
        grouped[record.get("tier", "Other")].append(record)

    groups = []
    for tier in sorted(grouped):
        rows = sorted(grouped[tier], key=lambda r: (r["firm"], r["title"]))
        groups.append(
            {
                "name": tier,
                "rows": [
                    {
                        "id": store.listing_key(row["firm"], row),
                        "company": row["firm"],
                        "programme": row["title"],
                        "url": row.get("url", ""),
                        "region": row.get("region", ""),
                        "category": row.get("category", ""),
                        "location": row.get("location", ""),
                        "openDate": (row.get("posted_on") or "")[:10] if _looks_like_date(row.get("posted_on")) else None,
                        "closeDate": (row.get("close_date") or "")[:10] if _looks_like_date(row.get("close_date")) else None,
                        "latestStage": None,
                        "process": [],
                        "testPrep": "",
                        "rolling": None,
                        "materials": [],
                        "visa": None,
                        "notes": row.get("posted_on", ""),
                        "firstSeen": row.get("first_seen", ""),
                    }
                    for row in rows
                ],
            }
        )

    payload = {
        "summer-internships": {"label": "Internships & Placements", "groups": groups},
    }

    os.makedirs(os.path.dirname(SITE_DATA_PATH), exist_ok=True)
    with open(SITE_DATA_PATH, "w", encoding="utf-8") as handle:
        handle.write("// Generated by scanner/scan.py -- do not edit by hand.\n")
        handle.write(f"// Last scan: {current.get('last_scan')}\n")
        handle.write("const TRACKS = ")
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write(";\n")


def write_digest_payload(new_items, closed_items, errors, per_firm_counts):
    payload = {
        "new": new_items,
        "closed": closed_items,
        "errors": [{"firm": n, "error": e} for n, e in errors],
        "counts": per_firm_counts,
    }
    os.makedirs(os.path.dirname(DIGEST_PATH), exist_ok=True)
    with open(DIGEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Scan firm career sites for internships.")
    parser.add_argument("--firm", help="scan a single firm by name")
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    args = parser.parse_args()

    config = load_config()
    return run(config, only_firm=args.firm, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
