"""GradConnection (SEEK Grad) adapter -- Australia's national student-jobs board.

Australia's internship calendar runs out of phase with the UK (summer
vacationer programmes recruit March-July for a November start), and the
banks there mostly post to their own portals. Rather than chase twenty
Australian firms individually, this reads the aggregator that nearly all of
them list on. robots.txt allows it (`Allow: /`), and we fetch a handful of
category pages a day.

    GET https://au.gradconnection.com/internships/{category}/?page=N

Cards carry title, employer, link and a relative "Closing in N days", which
we turn into a date. City and the "Accepts international: Yes/No" flag --
important, since many Australian programmes require citizenship or PR --
are on the detail page, fetched only for cards that pass the title filter.
"""

import re
import time
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

BASE = "https://au.gradconnection.com"
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0"}
DEFAULT_CATEGORIES = ["banking-and-finance", "investment-banking", "funds-management", "consulting", "accounting", "actuarial", "economics"]
CLOSING_RE = re.compile(r"closing\s+in\s+(\d+)\s+day", re.I)
CLOSING_TODAY_RE = re.compile(r"clos(?:es|ing)\s+today", re.I)

# Listings that aren't internships: "Notify Me" alert placeholders, Forage-style
# virtual experiences, award competitions, and SEEK Grad's own mirror entries.
NOISE_RE = re.compile(r"notify me|virtual experience|top ?100|future leader award|forage|\bwebinar\b|\bevents?\b", re.I)
NOISE_EMPLOYERS = {"seek grad", "gradconnection", "forage", "readygrad", "premium graduate placements"}


class GradConnectionAdapter:
    platform = "gradconnection"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def fetch(self, max_pages=10):
        seen = set()
        for category in self.firm.get("categories") or DEFAULT_CATEGORIES:
            for page in range(1, max_pages + 1):
                response = self.session.get(
                    f"{BASE}/internships/{category}/", params={"page": page}, headers=HEADERS, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select(".campaign-box")
                new = 0
                for card in cards:
                    posting = self._parse(card)
                    if posting and posting["source_id"] not in seen:
                        seen.add(posting["source_id"])
                        new += 1
                        yield posting
                if not cards or new == 0 or len(cards) < 20:
                    break
                time.sleep(self.delay)
            time.sleep(self.delay * 0.5)

    def _parse(self, card):
        link = card.select_one("a.box-header-title")
        if not link:
            return None
        href = link.get("href") or ""
        title = " ".join(link.get_text(" ", strip=True).split())
        employer_el = card.select_one(".box-employer-name p, .box-employer-name a")
        employer = " ".join(employer_el.get_text(" ", strip=True).split()) if employer_el else ""
        if NOISE_RE.search(title) or employer.strip().lower() in NOISE_EMPLOYERS:
            return None
        tag = card.select_one(".box-closing-interval")
        tag_text = tag.get_text(" ", strip=True) if tag else ""
        close_date = None
        m = CLOSING_RE.search(tag_text)
        if m:
            close_date = (date.today() + timedelta(days=int(m.group(1)))).isoformat()
        elif CLOSING_TODAY_RE.search(tag_text):
            close_date = date.today().isoformat()
        return {
            "source_id": href.rstrip("/").rsplit("/", 1)[-1] or href,
            # Employer goes in the title so the digest and tracker say who it is.
            "title": f"{employer} - {title}" if employer else title,
            "url": BASE + href if href.startswith("/") else href,
            "location": "Australia",
            "posted_on": "",
            "close_date": close_date,
            "time_type": "",
            "worker_sub_type": "internship",
            "employer": employer,
            "location_is_vague": True,  # city + work-rights flag live on the detail page
            "external_path": href,
        }

    def resolve_location(self, posting):
        try:
            response = self.session.get(posting["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            return posting
        text = " ".join(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True).split())
        loc = re.search(r"Locations?:\s*([A-Za-z ,/&()-]{2,80}?)\s+(?:ACCEPTS|Closing|Opening|Start|Positions|$)", text)
        intl = re.search(r"ACCEPTS INTERNATIONAL\s*(Yes|No)", text, re.I)
        city = loc.group(1).strip().rstrip(",") if loc else ""
        if city.lower() == "australia":
            city = ""
        location = f"{city}, Australia" if city else "Australia"
        if intl:
            location += f" (accepts international: {intl.group(1).title()})"
        posting["location"] = location
        posting["location_is_vague"] = False
        time.sleep(self.delay * 0.5)
        return posting
