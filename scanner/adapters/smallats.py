"""Adapters for the lightweight ATSs small and mid-sized firms favour.

All three expose an unauthenticated JSON feed keyed by the company slug in
the public careers URL, so adding a firm is one config line:

    SmartRecruiters  GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
    Ashby            GET https://api.ashbyhq.com/posting-api/job-board/{slug}
    Workable         POST https://apply.workable.com/api/v3/accounts/{slug}/jobs

SmartRecruiters echoes the company name in each posting and Workable has a
widget endpoint for it, which lets the slug prober confirm who a board
belongs to before it goes into config.
"""

import time

import requests

REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}


class SmartRecruitersAdapter:
    platform = "smartrecruiters"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=10):
        offset, seen = 0, 0
        for _ in range(max_pages):
            response = self.session.get(
                f"https://api.smartrecruiters.com/v1/companies/{self.firm['board']}/postings",
                params={"limit": 100, "offset": offset},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
            items = body.get("content") or []
            for raw in items:
                loc = raw.get("location") or {}
                location = ", ".join(p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p)
                yield {
                    "source_id": str(raw.get("id") or raw.get("ref") or ""),
                    "title": " ".join((raw.get("name") or "").split()),
                    "url": f"https://jobs.smartrecruiters.com/{self.firm['board']}/{raw.get('id')}",
                    "location": location,
                    "country": loc.get("country") or "",
                    "posted_on": (raw.get("releasedDate") or "")[:10],
                    "close_date": None,
                    "time_type": (raw.get("typeOfEmployment") or {}).get("label", ""),
                    "worker_sub_type": (raw.get("experienceLevel") or {}).get("label", ""),
                    "location_is_vague": False,
                    "external_path": "",
                }
            seen += len(items)
            offset += 100
            if not items or seen >= int(body.get("totalFound") or 0):
                break
            time.sleep(self.delay)

    def resolve_location(self, posting):
        return posting


class AshbyAdapter:
    platform = "ashby"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=None):
        response = self.session.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{self.firm['board']}",
            params={"includeCompensation": "false"},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        for raw in response.json().get("jobs") or []:
            if raw.get("isListed") is False:
                continue
            secondary = [s.get("location") for s in raw.get("secondaryLocations") or [] if s.get("location")]
            location = "; ".join(p for p in [raw.get("location")] + secondary if p)
            yield {
                "source_id": str(raw.get("id") or ""),
                "title": " ".join((raw.get("title") or "").split()),
                "url": raw.get("jobUrl") or raw.get("applyUrl") or "",
                "location": location,
                "posted_on": (raw.get("publishedAt") or "")[:10],
                "close_date": None,
                "time_type": raw.get("employmentType") or "",
                "worker_sub_type": raw.get("employmentType") or "",
                "location_is_vague": False,
                "external_path": "",
            }

    def resolve_location(self, posting):
        return posting


class WorkableAdapter:
    platform = "workable"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=10):
        token = None
        for _ in range(max_pages):
            body = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
            if token:
                body["token"] = token
            response = self.session.post(
                f"https://apply.workable.com/api/v3/accounts/{self.firm['board']}/jobs",
                json=body,
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            for raw in payload.get("results") or []:
                loc = raw.get("location") or {}
                location = ", ".join(p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p)
                yield {
                    "source_id": str(raw.get("shortcode") or raw.get("id") or ""),
                    "title": " ".join((raw.get("title") or "").split()),
                    "url": f"https://apply.workable.com/{self.firm['board']}/j/{raw.get('shortcode')}/",
                    "location": location,
                    "country": loc.get("country") or "",
                    "posted_on": (raw.get("published") or "")[:10],
                    "close_date": None,
                    "time_type": raw.get("type") or "",
                    "worker_sub_type": raw.get("type") or "",
                    "location_is_vague": False,
                    "external_path": "",
                }
            token = payload.get("nextPage")
            if not token:
                break
            time.sleep(self.delay)

    def resolve_location(self, posting):
        return posting
