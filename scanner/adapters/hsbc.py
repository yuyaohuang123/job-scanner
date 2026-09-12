"""HSBC adapter.

HSBC's student programmes are curated on hsbc.com rather than pulled from an
ATS -- a "Find a programme" page listing everything currently open, with
programme type, opening date, closing date and start date. That's better
data than most ATSs give.

The page renders 20 and a "Load more" button fetches the rest from:

    GET https://www.hsbc.com/api/programmes/get-programmes
        ?skip=0&take=N&count=N&s=<settings token>

The response is a JSON list of pre-rendered HTML fragments (one <li> each),
so we parse markup rather than fields. The `s` token is a hash of the
finder's settings; it's embedded on the page as `data-props-settings`, so we
read it fresh every run instead of hardcoding one that may rotate.
"""

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.hsbc.com/careers/students-and-graduates/find-a-programme"
API_URL = "https://www.hsbc.com/api/programmes/get-programmes"
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "text/html,application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}

ORDINAL_RE = re.compile(r"(\d+)(st|nd|rd|th)")


def _parse_date(text):
    """'8th Sep 2026' -> '2026-09-08'; anything unparseable -> None."""
    if not text:
        return None
    cleaned = ORDINAL_RE.sub(r"\1", text.strip())
    for fmt in ("%d %b %Y", "%d %B %Y", "%a %b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class HsbcAdapter:
    platform = "hsbc"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _settings(self):
        """Return (token, total) read from the live page."""
        response = self.session.get(PAGE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        finder = soup.find(attrs={"data-component": "ProgramFinder"})
        if finder is None:
            raise ValueError("ProgramFinder component not found on HSBC page; markup changed?")
        token = finder.get("data-props-settings")
        total = int(finder.get("data-props-total-count") or 0)
        if not token:
            raise ValueError("HSBC ProgramFinder has no settings token")
        return token, total

    def fetch(self, max_pages=None):
        token, total = self._settings()
        take = max(total, 20)
        response = self.session.get(
            API_URL,
            params={"skip": 0, "take": take, "count": take, "s": token},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        fragments = response.json()
        if not isinstance(fragments, list):
            raise ValueError("HSBC programmes API returned an unexpected shape")

        for fragment in fragments:
            posting = self._parse_fragment(fragment)
            if posting:
                yield posting

    def _parse_fragment(self, html):
        soup = BeautifulSoup(html, "html.parser")
        item = soup.find("li", class_="program-item") or soup
        title_el = item.find(class_="program-text__destination")
        link_el = item.find("a", class_="program-text__destination-link")
        if not title_el:
            return None

        title = " ".join(title_el.get_text(" ", strip=True).replace("(opens in new window)", "").split())
        location = (item.find(class_="program-location") or item).get_text(" ", strip=True)
        area = ""
        area_el = item.find(class_="program-text__area")
        if area_el:
            area = area_el.get_text(" ", strip=True)

        fields = {}
        for group in item.select("dl.program-text__groups .program-text__group"):
            label = group.find("dt")
            value = group.find("dd")
            if label and value:
                fields[label.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True)

        programme_type = fields.get("programme type", "")
        source_id = item.get("data-cs-override-id") or (link_el.get("href") if link_el else title)

        return {
            "source_id": source_id,
            "title": title,
            "url": link_el.get("href") if link_el else PAGE_URL,
            "location": location,
            "posted_on": _parse_date(fields.get("opening date")) or "",
            "close_date": _parse_date(fields.get("closing date")),
            "time_type": "",
            # Programme type is HSBC's own label -- "Internship Programme",
            # "Graduate Programme", etc. -- and is more reliable than the
            # title for telling internships from grad schemes.
            "worker_sub_type": programme_type,
            "area": area,
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
