"""Lever adapter.

Lever exposes postings as plain JSON:

    GET https://api.lever.co/v0/postings/{company}?mode=json

Verified working against a live board during setup.
"""

from datetime import datetime, timezone

import requests

REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "job-tracker/1.0"}


def _epoch_ms_to_date(value):
    """Lever timestamps are epoch milliseconds (an int), not ISO strings."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


class LeverAdapter:
    platform = "lever"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=None):
        url = f"https://api.lever.co/v0/postings/{self.firm['board']}?mode=json"
        response = self.session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        for raw in response.json() or []:
            categories = raw.get("categories") or {}
            yield {
                "source_id": raw.get("id") or "",
                "title": raw.get("text") or "",
                "url": raw.get("hostedUrl") or "",
                "location": categories.get("location") or "",
                "posted_on": _epoch_ms_to_date(raw.get("createdAt")),
                "time_type": categories.get("commitment") or "",
                "worker_sub_type": categories.get("commitment") or "",
                "location_is_vague": False,
                "external_path": "",
            }

    def resolve_location(self, posting):
        return posting
