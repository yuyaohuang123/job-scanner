"""Phenom People adapter (BCG's careers.bcg.com and many other corporate sites).

Phenom sites answer a single widgets endpoint:

    POST https://{host}/widgets
    {"ddoKey": "refineSearch", "pageName": "search-results", "from": 0,
     "size": 100, "selected_fields": {"country": [...]}, ...}

Jobs come back structured (title, city, country, postedDate, applyUrl,
jobId). `selected_fields.country` is an OR list, and an unknown country
name just matches nothing, so we pass every spelling we've seen for our
regions in one query rather than probing the facet.
"""

import time

import requests

PAGE_SIZE = 100
REQUEST_TIMEOUT = 30

COUNTRY_NAMES = [
    "United Kingdom", "UK",
    "Hong Kong", "Hong Kong SAR", "Hong Kong SAR, China",
    "China", "Mainland China", "China Mainland", "Greater China",
    "Australia",
]


class PhenomAdapter:
    platform = "phenom"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _headers(self):
        origin = f"https://{self.firm['host']}"
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0",
            "Origin": origin,
            "Referer": f"{origin}/{self.firm.get('search_path', 'global/en/search-results')}",
        }

    def _search(self, offset):
        body = {
            "lang": self.firm.get("lang", "en_global"),
            "deviceType": "desktop",
            "country": self.firm.get("country", "global"),
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "sortBy": "",
            "subsearch": "",
            "from": offset,
            "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "state", "city", "type"],
            "size": PAGE_SIZE,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": self.firm.get("page_id", "page12"),
            "siteType": "external",
            "keywords": "",
            "global": True,
            "selected_fields": {"country": self.firm.get("countries") or COUNTRY_NAMES},
            "locationData": {},
        }
        response = self.session.post(
            f"https://{self.firm['host']}/widgets", json=body, headers=self._headers(), timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("refineSearch") or {}

    def fetch(self, max_pages=20):
        offset = 0
        for _ in range(max_pages):
            result = self._search(offset)
            jobs = (result.get("data") or {}).get("jobs") or []
            for raw in jobs:
                yield self._normalise(raw)
            offset += len(jobs)
            if not jobs or offset >= int(result.get("totalHits") or 0):
                break
            time.sleep(self.delay)

    def _normalise(self, raw):
        location = ", ".join(p for p in (raw.get("city"), raw.get("state"), raw.get("country")) if p)
        job_id = raw.get("jobId") or raw.get("reqId") or ""
        url = raw.get("applyUrl") or f"https://{self.firm['host']}/global/en/job/{job_id}"
        posted = raw.get("postedDate") or raw.get("dateCreated") or ""
        return {
            "source_id": str(job_id),
            "title": " ".join((raw.get("title") or "").split()),
            "url": url,
            "location": location,
            "country": raw.get("country") or "",
            "posted_on": posted[:10] if posted else "",
            "close_date": None,
            "time_type": raw.get("type") or "",
            "worker_sub_type": "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
