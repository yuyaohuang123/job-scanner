"""Probe five lightweight ATSs for a list of firm names and report verified hits.

    python tools/probe_small.py names.txt hits.json

Slug variants are generated from each name ("Rede Partners" -> redepartners,
rede-partners, rede, ...) and tried against Greenhouse, Lever,
SmartRecruiters, Ashby and Workable. Where the platform reports the board's
owner, it's compared to the name so a slug that happens to exist for some
unrelated company is rejected rather than silently polluting results.
"""

import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import filters  # noqa: E402

S = requests.Session()
H = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}
STOP = {"the", "and", "of", "group", "partners", "capital", "management", "llp", "ltd", "plc", "co", "company", "inc", "limited", "&"}


def slug_variants(name):
    base = re.sub(r"[^a-z0-9 &-]", "", name.lower().replace("&", " and "))
    words = [w for w in re.split(r"[\s-]+", base) if w]
    core = [w for w in words if w not in STOP] or words
    variants = [
        "".join(words), "-".join(words),
        "".join(core), "-".join(core),
        core[0] if core else "",
        "".join(words[:2]), "-".join(words[:2]),
    ]
    out, seen = [], set()
    for v in variants:
        if v and len(v) >= 3 and v not in seen:
            seen.add(v); out.append(v)
    return out


def owner_matches(owner, name):
    if not owner:
        return None  # unknown; caller decides
    a = re.sub(r"[^a-z0-9]", "", owner.lower()); b = re.sub(r"[^a-z0-9]", "", name.lower())
    core = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in STOP]
    return b in a or a in b or (bool(core) and core[0] in a)


def probe_greenhouse(slug):
    r = S.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false", headers=H, timeout=20)
    if r.status_code != 200: return None
    jobs = r.json().get("jobs") or []
    o = S.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}", headers=H, timeout=20)
    owner = o.json().get("name") if o.ok else None
    return [(j.get("title", ""), (j.get("location") or {}).get("name", "")) for j in jobs], owner


def probe_lever(slug):
    r = S.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=H, timeout=20)
    if r.status_code != 200: return None
    data = r.json()
    if not isinstance(data, list): return None
    return [(j.get("text", ""), (j.get("categories") or {}).get("location", "")) for j in data], None


def probe_smartrecruiters(slug):
    r = S.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100}, headers=H, timeout=20)
    if r.status_code != 200: return None
    body = r.json(); items = body.get("content") or []
    if not items and not body.get("totalFound"): return None
    owner = (items[0].get("company") or {}).get("name") if items else None
    return [(j.get("name", ""), ", ".join(p for p in ((j.get("location") or {}).get("city"), (j.get("location") or {}).get("country")) if p)) for j in items], owner


def probe_ashby(slug):
    r = S.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=H, timeout=20)
    if r.status_code != 200: return None
    jobs = r.json().get("jobs")
    if jobs is None: return None
    return [(j.get("title", ""), j.get("location", "")) for j in jobs], None


def probe_workable(slug):
    r = S.post(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", json={"query": ""}, headers={**H, "Content-Type": "application/json"}, timeout=20)
    if r.status_code != 200: return None
    results = r.json().get("results")
    if results is None: return None
    o = S.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", headers=H, timeout=20)
    owner = o.json().get("name") if o.ok else None
    return [(j.get("title", ""), ", ".join(p for p in ((j.get("location") or {}).get("city"), (j.get("location") or {}).get("country")) if p)) for j in results], owner


PLATFORMS = [("greenhouse", probe_greenhouse), ("lever", probe_lever), ("smartrecruiters", probe_smartrecruiters), ("ashby", probe_ashby), ("workable", probe_workable)]


def run(names, out_path=None):
    hits = {}
    for name in names:
        found = None
        for slug in slug_variants(name):
            for platform, fn in PLATFORMS:
                try:
                    res = fn(slug)
                except (requests.RequestException, ValueError):
                    res = None
                if res is None:
                    continue
                jobs, owner = res
                ok = owner_matches(owner, name)
                if ok is False:
                    continue  # a real board, but someone else's
                interns = [(t, l, filters.classify_region(l)) for t, l in jobs if filters.classify_role(t) and not filters.is_excluded(t)]
                inreg = [x for x in interns if x[2]]
                found = {"platform": platform, "slug": slug, "owner": owner, "total": len(jobs), "interns": len(interns), "in_region": len(inreg), "samples": inreg[:3]}
                verified = "owner-verified" if ok else "owner-unknown"
                print(f"HIT  {name:<28} {platform:<16} {slug:<24} jobs={len(jobs):<4} interns={len(interns):<3} in-region={len(inreg):<2} [{verified}]", flush=True)
                break
            if found:
                break
            time.sleep(0.15)
        if found:
            hits[name] = found
    print(f"\n=== DONE: {len(hits)} hits of {len(names)} names ===")
    if out_path:
        json.dump(hits, open(out_path, "w"), indent=2, default=str)
    return hits


if __name__ == "__main__":
    names = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    run(names, sys.argv[2] if len(sys.argv) > 2 else None)
