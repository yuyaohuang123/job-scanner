"""Greenhouse adapter.

Greenhouse publishes a clean, unauthenticated JSON board:

    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false

The board token is the slug in the public careers URL
(boards.greenhouse.io/<token>). Common among boutiques and quant/trading firms.
"""

import requests

REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "job-tracker/1.0"}


class GreenhouseAdapter:
    platform = "greenhouse"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=None):
        url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{self.firm['board']}/jobs?content=false"
        )
        response = self.session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        for raw in response.json().get("jobs") or []:
            yield {
                "source_id": str(raw.get("id")),
                "title": raw.get("title") or "",
                "url": raw.get("absolute_url") or "",
                "location": (raw.get("location") or {}).get("name", ""),
                "posted_on": raw.get("updated_at") or "",
                "time_type": "",
                "worker_sub_type": "",
                "location_is_vague": False,
                "external_path": "",
            }

    def resolve_location(self, posting):
        return posting
