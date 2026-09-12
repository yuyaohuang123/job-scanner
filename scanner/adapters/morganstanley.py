"""Morgan Stanley campus adapter.

Morgan Stanley's Workday tenant holds experienced hires only. Students and
graduates are served by a JSON feed behind morganstanley.com/careers:

    GET https://www.morganstanley.com/web/career_services/webapp/service/
        careerservice/resultset.json?opportunity=sg&location=<regions>&lang=EN

One request returns every open campus opportunity worldwide (~120) with
division, city, country, employmentType and -- unusually -- the application
deadline. Apply links point at their Oleeo (tal.net) portal.
"""

import html
from datetime import datetime

import requests

FEED_URL = "https://www.morganstanley.com/web/career_services/webapp/service/careerservice/resultset.json"
ALL_REGIONS = "Americas;Europe, Middle East, Africa;Japan;Non-Japan Asia"
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}


def _parse_deadline(text):
    """'Nov 15, 2026' -> '2026-11-15'."""
    if not text:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


class MorganStanleyAdapter:
    platform = "morganstanley"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=None):
        response = self.session.get(
            FEED_URL,
            params={"opportunity": "sg", "location": ALL_REGIONS, "lang": "EN"},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        for raw in body.get("resultSet") or []:
            yield self._normalise(raw)

    def _normalise(self, raw):
        # Titles arrive with entities half-decoded ("Sales amp; Trading").
        title = html.unescape((raw.get("jobTitle") or "").replace("amp;", "&"))
        title = " ".join(title.split())
        location = ", ".join(p for p in (raw.get("city"), raw.get("country")) if p)
        return {
            "source_id": str(raw.get("jobNumber") or raw.get("url") or title),
            "title": title,
            "url": raw.get("url") or "",
            "location": location,
            "country": raw.get("country") or "",
            "posted_on": "",
            "close_date": _parse_deadline(raw.get("applicationDate")),
            "time_type": "",
            "worker_sub_type": raw.get("employmentType") or "",
            "division": raw.get("division") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
