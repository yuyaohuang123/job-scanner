"""Eightfold AI careers adapter (Haleon and other large corporates).

Eightfold-hosted career sites answer a public search endpoint:

    GET https://{host}/api/pcsx/search
        ?domain={domain}&query=&location=&start=0&num=50

Results arrive under `data.positions`, with `data.count` giving the total.
Each position carries a `locations` list, a `department`, a `positionUrl`
and `postedTs` (epoch seconds).

Note the older `/api/apply/v2/jobs` endpoint that some Eightfold tenants
expose is 403 here -- `pcsx` is the one the site itself calls.
"""

import time
from datetime import datetime, timezone

import requests

PAGE = 50
REQUEST_TIMEOUT = 30


def _ts_to_date(value):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


class EightfoldAdapter:
    platform = "eightfold"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _headers(self):
        return {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0",
            "Referer": f"https://{self.firm['host']}/careers",
        }

    def fetch(self, max_pages=40):
        # One query per location keyword: Eightfold's location filter is a
        # free-text match, so asking for each of our countries in turn is
        # both cheaper and more precise than pulling a global board.
        seen = set()
        for location in self.firm.get("locations") or ["United Kingdom", "Hong Kong", "China"]:
            start = 0
            for _ in range(max_pages):
                response = self.session.get(
                    f"https://{self.firm['host']}/api/pcsx/search",
                    params={
                        "domain": self.firm["domain"],
                        "query": self.firm.get("query", ""),
                        "location": location,
                        "start": start,
                        "num": PAGE,
                    },
                    headers=self._headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                data = (response.json() or {}).get("data") or {}
                positions = data.get("positions") or []
                for raw in positions:
                    key = str(raw.get("id") or raw.get("displayJobId") or "")
                    if key in seen:
                        continue
                    seen.add(key)
                    yield self._normalise(raw, location)
                # The API ignores `num` and returns a fixed page (10 at the
                # time of writing), so advance by what actually came back.
                start += len(positions)
                if not positions or start >= int(data.get("count") or 0):
                    break
                time.sleep(self.delay)
            time.sleep(self.delay * 0.5)

    def _normalise(self, raw, queried_location):
        locations = raw.get("locations") or raw.get("standardizedLocations") or []
        if isinstance(locations, str):
            locations = [locations]
        # Eightfold often leaves `locations` empty and puts the city in the
        # title ("..., 2027, Weybridge, UK"), so fall back to what we asked for.
        location = ", ".join(str(l) for l in locations if l) or queried_location
        url = raw.get("positionUrl") or ""
        if url.startswith("/"):
            url = f"https://{self.firm['host']}{url}"
        return {
            "source_id": str(raw.get("id") or raw.get("displayJobId") or ""),
            "title": " ".join((raw.get("name") or "").split()),
            "url": url or f"https://{self.firm['host']}/careers",
            "location": location,
            "posted_on": _ts_to_date(raw.get("postedTs")),
            "close_date": None,
            "time_type": "",
            "worker_sub_type": "",
            "department": raw.get("department") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
