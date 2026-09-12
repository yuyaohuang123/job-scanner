"""Avature career-portal adapter (Deloitte UK early careers; HSBC's job board).

Avature portals render results server-side:

    GET https://{host}/{portal}/SearchJobs/?jobRecordsPerPage=50&jobOffset=N

Each hit is an `article.article--result` whose title link ends in the job
id (…/PipelineDetail/<slug>/<id>), with icon-labelled items for location
(span.item--location), contract type (icon--clock) and an open–close date range
(icon--calendar, "08-Sep-2026 - 26-Sep-2026"). Closing dates are useful and
rare, so they're carried through.

Deloitte UK's portal had no early-careers vacancies open at setup; the
adapter is in place for when the 2027 cycle opens.
"""

import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0"}
PAGE = 50
DATE_RE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})")


def _parse_date(text):
    try:
        return datetime.strptime(text, "%d-%b-%Y").date().isoformat()
    except (ValueError, TypeError):
        return None


class AvatureAdapter:
    platform = "avature"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    @property
    def _search_url(self):
        return f"https://{self.firm['host']}/{self.firm['portal'].strip('/')}/SearchJobs/"

    def fetch(self, max_pages=20):
        offset = 0
        seen = set()
        for _ in range(max_pages):
            response = self.session.get(
                self._search_url,
                params={"jobRecordsPerPage": PAGE, "jobOffset": offset},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("article.article--result")
            if not cards:
                break
            new = 0
            for card in cards:
                posting = self._parse(card)
                if posting and posting["source_id"] not in seen:
                    seen.add(posting["source_id"])
                    new += 1
                    yield posting
            if new == 0 or len(cards) < PAGE:
                break
            offset += PAGE
            time.sleep(self.delay)

    def _parse(self, card):
        link = card.select_one(".article__header__title a, h3 a")
        if not link:
            return None
        href = link.get("href") or ""
        id_match = re.search(r"/(\d+)/?$", href)

        location, contract, dates = "", "", ""
        loc_el = card.select_one(".item--location, .location")
        if loc_el:
            location = " ".join(loc_el.get_text(" ", strip=True).split())
        for item in card.select(".item__container"):
            icon = item.find("i")
            classes = " ".join(icon.get("class", [])) if icon else ""
            text = " ".join(item.get_text(" ", strip=True).split())
            if "location" in classes:
                location = text
            elif "clock" in classes:
                contract = text
            elif "calendar" in classes:
                dates = text
        found = DATE_RE.findall(dates)
        opened = _parse_date(found[0]) if found else None
        closes = _parse_date(found[1]) if len(found) > 1 else None

        return {
            "source_id": id_match.group(1) if id_match else href,
            "title": " ".join(link.get_text(" ", strip=True).split()),
            "url": href,
            "location": location or self.firm.get("default_location", ""),
            "posted_on": opened or "",
            "close_date": closes,
            "time_type": contract,
            "worker_sub_type": contract,
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
