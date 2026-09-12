"""Bank of America campus adapter.

careers.bankofamerica.com has a dedicated campus search servlet that returns
every open student/graduate posting worldwide as JSON in one call:

    GET https://careers.bankofamerica.com/services/campusjobssearchservlet
        ?start=0&rows=200&search=getAllJobs

Fields include city/country, postedDate and applyByDate. Apply links point
at their Oleeo (tal.net) portal; jcrURL is the on-site detail page.
"""

from datetime import datetime

import requests

ENDPOINT = "https://careers.bankofamerica.com/services/campusjobssearchservlet"
SITE = "https://careers.bankofamerica.com"
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}


def _parse_us_date(text):
    """'09/11/2026' (month/day/year) -> '2026-09-11'."""
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


class BofaAdapter:
    platform = "bofa"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=5):
        start, rows = 0, 200
        for _ in range(max_pages):
            response = self.session.get(
                ENDPOINT,
                params={"start": start, "rows": rows, "search": "getAllJobs"},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
            jobs = body.get("jobsList") or []
            for raw in jobs:
                yield self._normalise(raw)
            total = int(body.get("totalMatches") or 0)
            start += rows
            if start >= total or not jobs:
                break

    def _normalise(self, raw):
        location = ", ".join(
            str(raw.get(k)).strip() for k in ("city", "state", "country") if raw.get(k)
        )
        detail = raw.get("jcrURL") or ""
        url = raw.get("externalUrl") or (SITE + detail if detail else SITE)
        return {
            "source_id": str(raw.get("jobRequisitionId") or detail),
            "title": " ".join((raw.get("postingTitle") or "").split()),
            "url": url,
            "location": location,
            "country": raw.get("country") or "",
            "posted_on": _parse_us_date(raw.get("externalPostedDate") or raw.get("postedDate")) or "",
            "close_date": _parse_us_date(raw.get("applyByDate")),
            "time_type": raw.get("timeType") or "",
            "worker_sub_type": raw.get("job_type_text") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
