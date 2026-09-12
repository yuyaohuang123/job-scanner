"""Bain & Company adapter.

bain.com's "Find a role" page reads a JSON endpoint that returns everything
in one call:

    GET https://www.bain.com/en/api/jobsearch/keyword/get
        ?start=0&results=500&filters=&searchValue=

Postings are global: "Associate Consultant Internship" carries a list of
60+ office cities. We join the list so region matching sees every office,
which means a worldwide posting lands in whichever of our regions appears
first in it -- but it is captured, with all offices visible in the
location text.
"""

import time

import requests

ENDPOINT = "https://www.bain.com/en/api/jobsearch/keyword/get"
REQUEST_TIMEOUT = 30
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0",
    "Referer": "https://www.bain.com/careers/find-a-role/",
}
PAGE = 500


class BainAdapter:
    platform = "bain"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=5):
        start = 0
        for _ in range(max_pages):
            response = self.session.get(
                ENDPOINT,
                params={"start": start, "results": PAGE, "filters": "", "searchValue": ""},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
            results = body.get("results") or []
            for raw in results:
                yield self._normalise(raw)
            start += len(results)
            if not results or start >= int(body.get("totalResults") or 0):
                break
            time.sleep(self.delay)

    def _normalise(self, raw):
        offices = raw.get("Location") or []
        if isinstance(offices, str):
            offices = [offices]
        offices = [str(o).strip() for o in offices if str(o).strip()]
        link = raw.get("Link") or ""
        if link.startswith("/"):
            link = "https://www.bain.com" + link
        return {
            "source_id": str(raw.get("JobId") or link),
            "title": " ".join((raw.get("JobTitle") or "").split()),
            "url": link or "https://www.bain.com/careers/find-a-role/",
            "location": ", ".join(offices),
            "posted_on": "",
            "close_date": None,
            "time_type": raw.get("EmployeeType") or "",
            # "Intern (Full-Time)" is Bain's own label for internships.
            "worker_sub_type": raw.get("EmployeeType") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
