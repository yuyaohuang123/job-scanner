"""SAP SuccessFactors career-site adapter (EY's careers.ey.com and many others).

The public search is server-rendered HTML:

    GET https://{host}/{site}/search/?q=<kw>&locationsearch=<country>&startrow=N

25 results per page as `tr.data-row` rows with `a.jobTitle-link` and
`.jobLocation`; the total appears as "Results 1 to 25 of 927".

A country alone returns everything the firm has there (EY UK: 927 roles),
too much to page daily. Keyword search is fuzzy but it narrows, so we run a
few early-careers keywords per country, union the rows, and let the title
classifier make the precise call.
"""

import re
import time

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 job-tracker/1.0"}
PAGE = 25
TOTAL_RE = re.compile(r"Results\s+\d+\s+to\s+\d+\s+of\s+(\d+)", re.I)

DEFAULT_KEYWORDS = ["intern", "internship", "placement", "summer", "student", "undergraduate"]
DEFAULT_COUNTRIES = ["United Kingdom", "Hong Kong", "China", "Australia"]


class SuccessFactorsAdapter:
    platform = "successfactors"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    @property
    def _base(self):
        return f"https://{self.firm['host']}/{self.firm.get('site', '').strip('/')}".rstrip("/")

    def _page(self, keyword, country, startrow):
        response = self.session.get(
            f"{self._base}/search/",
            params={"q": keyword, "locationsearch": country, "startrow": startrow},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    def fetch(self, max_pages=8):
        seen = set()
        keywords = self.firm.get("keywords") or DEFAULT_KEYWORDS
        countries = self.firm.get("countries") or DEFAULT_COUNTRIES
        for country in countries:
            for keyword in keywords:
                startrow = 0
                for _ in range(max_pages):
                    html = self._page(keyword, country, startrow)
                    soup = BeautifulSoup(html, "html.parser")
                    rows = soup.select("tr.data-row")
                    for row in rows:
                        posting = self._parse(row)
                        if posting and posting["source_id"] not in seen:
                            seen.add(posting["source_id"])
                            yield posting
                    total_match = TOTAL_RE.search(html)
                    total = int(total_match.group(1)) if total_match else 0
                    startrow += PAGE
                    if not rows or startrow >= total:
                        break
                    time.sleep(self.delay)
                time.sleep(self.delay * 0.5)

    def _parse(self, row):
        link = row.select_one("a.jobTitle-link")
        if not link:
            return None
        href = link.get("href") or ""
        if href.startswith("/"):
            href = f"https://{self.firm['host']}{href}"
        loc = row.select_one(".jobLocation")
        # SuccessFactors ids sit in the URL: /ey/job/<City>/<Title>/<id>/
        id_match = re.search(r"/(\d+)/?$", href)
        return {
            "source_id": id_match.group(1) if id_match else href,
            "title": " ".join(link.get_text(" ", strip=True).split()),
            "url": href,
            "location": loc.get_text(" ", strip=True) if loc else "",
            "posted_on": "",
            "close_date": None,
            "time_type": "",
            "worker_sub_type": "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
