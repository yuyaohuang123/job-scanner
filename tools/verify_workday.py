"""Verify a batch of Workday (host, tenant, site) candidates against the live API.

    python tools/verify_workday.py out.json

For each candidate: confirms the endpoint answers, discovers the tenant's
intern-type and country facets, runs a pass on each (unioned), resolves any
"2 Locations" summaries, and reports how many postings fall in our regions.
Prints sample titles so a wrong tenant -- a university sharing a bank's
abbreviation, say -- is obvious before it goes into config, and writes a
ready-to-paste firms.yml block for every candidate that checks out.
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import filters  # noqa: E402
from scanner.adapters.workday import WorkdayAdapter, discover_facets  # noqa: E402

# name, tier, host, tenant, site
CANDIDATES = [
    ("Morgan Stanley",       "Bulge Bracket",   "ms.wd5.myworkdayjobs.com",             "ms",            "External"),
    ("Deutsche Bank",        "Bulge Bracket",   "db.wd3.myworkdayjobs.com",             "db",            "DBWebsite"),
    ("Wells Fargo",          "Bulge Bracket",   "wf.wd1.myworkdayjobs.com",             "wf",            "WellsFargoJobs"),
    ("Greenhill (Mizuho)",   "Elite Boutique",  "mizuho.wd1.myworkdayjobs.com",         "mizuho",        "mizuhoamericas"),
    ("Mizuho",               "Middle Market",   "mizuhogroup.wd102.myworkdayjobs.com",  "mizuhogroup",   "External"),
    ("Blackstone",           "Buy-Side",        "blackstone.wd1.myworkdayjobs.com",     "blackstone",    "Blackstone_Campus_Careers"),
    ("BlackRock",            "Asset Management","blackrock.wd1.myworkdayjobs.com",      "blackrock",     "BlackRock_Professional"),
    ("Invesco",              "Asset Management","invesco.wd1.myworkdayjobs.com",        "invesco",       "IVZ"),
    ("Neuberger Berman",     "Asset Management","nb.wd1.myworkdayjobs.com",             "nb",            "NBCareers"),
    ("Harris Williams",      "Middle Market",   "pnc.wd5.myworkdayjobs.com",            "pnc",           "HarrisWilliams"),
    ("Guggenheim Partners",  "Middle Market",   "guggenheim.wd1.myworkdayjobs.com",     "guggenheim",    "Guggenheim_Careers_Campus"),
    ("PJT Partners",         "Elite Boutique",  "pjtpartners.wd1.myworkdayjobs.com",    "pjtpartners",   "Students"),
    ("Houlihan Lokey",       "Middle Market",   "hl.wd1.myworkdayjobs.com",             "hl",            "Campus"),
    ("Raymond James",        "Middle Market",   "raymondjames.wd1.myworkdayjobs.com",   "raymondjames",  "RaymondJamesEarlyCareers"),
    ("Moelis & Co",          "Elite Boutique",  "moelis.wd1.myworkdayjobs.com",         "moelis",        "University-Hires"),
    ("RBC Capital Markets",  "Middle Market",   "rbc.wd3.myworkdayjobs.com",            "rbc",           "RBCEARLYTALENT1"),
    ("TD Securities",        "Middle Market",   "td.wd3.myworkdayjobs.com",             "td",            "TD_Bank_Careers"),
    ("Lloyds Banking Group", "UK Banking",      "lbg.wd3.myworkdayjobs.com",            "lbg",           "Undergraduate_careers"),
    ("FTI Consulting",       "Consulting",      "fticonsulting.wd108.myworkdayjobs.com","fticonsulting", "FTIConsultingCareers"),
    ("Nasdaq",               "Miscellaneous",   "nasdaq.wd1.myworkdayjobs.com",         "nasdaq",        "Global_External_Site"),
    ("Capital One",          "Miscellaneous",   "capitalone.wd12.myworkdayjobs.com",    "capitalone",    "Capital_One"),
    ("Mastercard",           "Miscellaneous",   "mastercard.wd1.myworkdayjobs.com",     "mastercard",    "Campus"),
]

UNFILTERED_PAGE_CAP = 15  # 300 postings when a tenant offers neither facet

# Boards up to this size are read in full with no facets at all. Facets exist
# to make a 1,900-role board tractable; on a 33-role campus site they only
# add ways to miss things -- Blackstone's country facet tags one posting out
# of 30 real internships.
SMALL_BOARD = 400


def build_passes(found):
    if found.get("total", 0) <= SMALL_BOARD:
        return [{}]  # one unfiltered pass, paginated to the end
    passes = []
    if "intern" in found:
        param, ids, _ = found["intern"]
        passes.append({param: ids})
    if "country" in found:
        param, ids, _ = found["country"]
        passes.append({param: ids})
    return passes or [{}]  # huge board, no facets: unfiltered but capped


def verify(name, tier, host, tenant, site, session):
    firm = {"name": name, "host": host, "tenant": tenant, "site": site}
    result = {"name": name, "tier": tier, "host": host, "tenant": tenant, "site": site}

    try:
        found = discover_facets(firm, session=session)
    except requests.HTTPError as exc:
        result["error"] = f"HTTP {exc.response.status_code}"
        return result
    except (requests.RequestException, ValueError) as exc:
        result["error"] = type(exc).__name__
        return result

    result["total"] = found.get("total", 0)
    result["intern_facet"] = found.get("intern")
    result["country_facet"] = found.get("country")

    passes = build_passes(found)
    firm["passes"] = passes
    # A small board's single unfiltered pass needs enough pages to finish;
    # a huge board with no usable facets gets capped so the daily run stays
    # polite -- that case is reported so it can be looked at by hand.
    if passes == [{}] and found.get("total", 0) > SMALL_BOARD:
        max_pages = UNFILTERED_PAGE_CAP
        result["capped"] = True
    else:
        max_pages = 40

    adapter = WorkdayAdapter(firm, session=session, delay=0.6)
    matches, regions, samples, scanned, vague_resolved = 0, {}, [], 0, 0
    for p in adapter.fetch(max_pages=max_pages):
        scanned += 1
        cat = filters.classify_role(p["title"], p.get("worker_sub_type"))
        if not cat or filters.is_excluded(p["title"]):
            continue
        if p.get("location_is_vague"):
            p = adapter.resolve_location(p)
            vague_resolved += 1
            time.sleep(0.4)
        matches += 1
        region = filters.classify_region(p["location"])
        if region:
            regions[region] = regions.get(region, 0) + 1
            if len(samples) < 4:
                samples.append((p["title"][:58], p["location"][:32], region))
    if not samples:
        # show a couple of out-of-region ones so a wrong tenant is obvious
        samples = samples

    result.update(scanned=scanned, interns=matches, regions=regions,
                  samples=samples, passes=passes, vague_resolved=vague_resolved)
    return result


def yaml_block(res):
    lines = [
        f"  - name: {res['name']}",
        f"    tier: {res['tier']}",
        "    platform: workday",
        "    enabled: true",
        f"    host: {res['host']}",
        f"    tenant: {res['tenant']}",
        f"    site: {res['site']}",
    ]
    if res["passes"]:
        lines.append("    passes:")
        for p in res["passes"]:
            for param, ids in p.items():
                lines.append(f"      - {param}: {json.dumps(ids)}")
    return "\n".join(lines)


def main():
    session = requests.Session()
    out = []
    print(f"{'firm':<22} {'total':>6} {'intern':>7} {'country':>8} {'match':>5}  regions")
    for name, tier, host, tenant, site in CANDIDATES:
        res = verify(name, tier, host, tenant, site, session)
        out.append(res)
        if "error" in res:
            print(f"{name:<22} ERROR {res['error']}")
        else:
            i = res["intern_facet"][2] if res["intern_facet"] else "-"
            c = res["country_facet"][2] if res["country_facet"] else "-"
            print(f"{name:<22} {res['total']:>6} {str(i):>7} {str(c):>8} {res['interns']:>5}  {res['regions'] or '-'}")
            for t, loc, reg in res["samples"]:
                print(f"    [{reg:<9}] {t:<58} {loc}")
        time.sleep(0.8)

    json.dump(out, open(sys.argv[1], "w"), indent=2, default=str)
    print("\n\n# ---- firms.yml blocks for candidates that answered ----\n")
    for res in out:
        if "error" not in res:
            print(yaml_block(res))
            print()


if __name__ == "__main__":
    main()
