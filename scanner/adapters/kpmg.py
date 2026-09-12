"""KPMG UK adapter.

kpmgcareers.co.uk renders vacancies as HTML cards, six per page, paged by
`?page=N`. The intake-type filter on the site is applied client-side by
JavaScript, so we read every page and classify from each card's type label
("Undergraduate", "Graduate", "Experienced Professional") and title.

Student programmes weren't open at setup ("No search results" under the
student filter); the adapter is in place so they're picked up the day
KPMG's 2027 cycle opens.
"""

import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.kpmgcareers.co.uk"
LIST_URL = BASE + "/search/vacancies/"
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0"}
PAGE_CAP = 60


class KpmgAdapter:
    platform = "kpmg"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=PAGE_CAP):
        seen = set()
        last_page = None
        page = 1
        while page <= max_pages:
            response = self.session.get(
                LIST_URL, params={"page": page}, headers=HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            if last_page is None:
                pages = [int(a["data-page"]) for a in soup.select("[data-page]") if str(a.get("data-page", "")).isdigit()]
                last_page = max(pages) if pages else 1

            cards = soup.select(".vacancy-result")
            if not cards:
                break
            for card in cards:
                posting = self._parse(card)
                if posting and posting["source_id"] not in seen:
                    seen.add(posting["source_id"])
                    yield posting

            if page >= last_page:
                break
            page += 1
            time.sleep(self.delay)

    def _parse(self, card):
        title_el = card.find("h3")
        if not title_el:
            return None
        link = card.select_one("a.view-job-description")
        vac_type = card.select_one(".vacancy-type")
        loc = card.select_one(".vacancy-location b") or card.select_one(".vacancy-location")
        area = card.select_one(".vacancy-service-line b")
        href = link.get("href") if link else ""
        if href.startswith("/"):
            href = BASE + href
        location = loc.get_text(" ", strip=True).replace("Location:", "").strip() if loc else ""
        return {
            "source_id": str(card.get("data-vacancy-id") or href),
            "title": " ".join(title_el.get_text(" ", strip=True).split()),
            "url": href or LIST_URL,
            # Every KPMG UK vacancy is in the UK; the card gives the city.
            "location": f"{location}, United Kingdom" if location else "United Kingdom",
            "posted_on": "",
            "close_date": None,
            "time_type": "",
            "worker_sub_type": vac_type.get_text(" ", strip=True) if vac_type else "",
            "area": area.get_text(" ", strip=True) if area else "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
