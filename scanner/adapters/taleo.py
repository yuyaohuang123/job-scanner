"""Taleo "TGnewUI" adapter (UBS graduate board, and other Taleo Enterprise sites).

The Angular front end pages through jobs with:

    POST https://{host}/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs
    {"partnerId": ..., "siteId": ..., "pageNumber": N, "jobsToShow": 50, ...}

Each job is a list of {QuestionName, Value} pairs rather than named fields;
the useful ones are jobtitle, formtext23 (country), department, lastupdated
and reqid. Custom "formtext" fields vary by tenant, so which one holds the
country is configurable.

The site fronts with bot protection that rejects bare clients, but a normal
browser User-Agent and Referer get through. The session token the page
embeds turned out to be optional.
"""

import html
import time
from datetime import datetime

import requests

PAGE_SIZE = 50
REQUEST_TIMEOUT = 30


def _parse_date(text):
    """'11-Sep-2026' -> '2026-09-11'."""
    if not text:
        return ""
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


class TaleoAdapter:
    platform = "taleo"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    @property
    def _home(self):
        return (
            f"https://{self.firm['host']}/TGnewUI/Search/Home/Home"
            f"?partnerid={self.firm['partner_id']}&siteid={self.firm['site_id']}"
        )

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Referer": self._home,
            "X-Requested-With": "XMLHttpRequest",
        }

    def fetch(self, max_pages=20):
        seen = 0
        for page in range(1, max_pages + 1):
            body = {
                "partnerId": str(self.firm["partner_id"]),
                "siteId": str(self.firm["site_id"]),
                "keyword": "",
                "location": "",
                "keywordCustomSolrFields": self.firm.get("keyword_fields", "FORMTEXT21,AutoReq,Department,JobTitle"),
                "locationCustomSolrFields": self.firm.get("location_fields", "FORMTEXT2,FORMTEXT23,Location"),
                "turnOffHttps": False,
                "Latitude": 0,
                "Longitude": 0,
                "encryptedSessionValue": "",
                "facetfilterfields": {"Facet": []},
                "powersearchoptions": {"PowerSearchOption": []},
                "SortType": "LastUpdated",
                "pageNumber": page,
                "jobsToShow": PAGE_SIZE,
                "locale": "en-US",
            }
            response = self.session.post(
                f"https://{self.firm['host']}/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs",
                json=body,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            jobs = (payload.get("Jobs") or {}).get("Job") or []
            for raw in jobs:
                yield self._normalise(raw)
            seen += len(jobs)
            total = int(payload.get("JobsCount") or 0)
            if not jobs or seen >= total:
                break
            time.sleep(self.delay)

    def _normalise(self, raw):
        fields = {q.get("QuestionName"): q.get("Value") for q in raw.get("Questions") or []}
        country_field = self.firm.get("country_field", "formtext23")
        city_field = self.firm.get("city_field", "formtext2")
        location = ", ".join(
            str(fields.get(k)).strip() for k in (city_field, "location", country_field) if fields.get(k)
        )
        req_id = str(fields.get("reqid") or "")
        return {
            "source_id": req_id,
            "title": " ".join(html.unescape(fields.get("jobtitle") or "").split()),
            "url": f"{self._home.replace('/Home/Home', '/home/HomeWithPreLoad')}&PageType=JobDetails&jobid={req_id}",
            "location": location,
            "country": str(fields.get(country_field) or "").strip(),
            "posted_on": _parse_date(fields.get("lastupdated")),
            "close_date": None,
            "time_type": "",
            "worker_sub_type": "",
            "department": fields.get("department") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
