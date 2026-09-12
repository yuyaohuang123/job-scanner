"""Radancy adapter (Citi and other jobs.<firm>.com sites on the Radancy CMS).

Radancy careers sites share a search endpoint that returns JSON-wrapped HTML:

    GET https://{host}/search-jobs/results?ActiveFacetID=<id>&CurrentPage=1
        &RecordsPerPage=100&FacetFilters[0].ID=<id>&FacetFilters[0].FacetType=2
        &FacetFilters[0].Count=<n>&FacetFilters[0].Display=<name>
        &FacetFilters[0].IsApplied=true&FacetFilters[0].FieldName=&SearchType=5...

Country is facet type 2 and its ids are GeoNames ids (United Kingdom is
2635167), so they're stable across Radancy tenants. We run one search per
country in config and title-match the cards. The custom "career level"
facets are fiddly and inconsistent between tenants, so we don't rely on them.

Filters only take effect when ActiveFacetID carries the facet id AND the
FacetFilters entry includes Count and Display -- omit those and the site
silently returns everything.
"""

import html
import re
import time

import requests

PAGE_SIZE = 100
REQUEST_TIMEOUT = 30
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 job-tracker/1.0",
    "X-Requested-With": "XMLHttpRequest",
}

CARD_RE = re.compile(
    r'<a class="sr-job-item__link" href="([^"]+)" data-job-id="([^"]+)"[^>]*>\s*(.*?)\s*</a>'
    r'(.*?)</li>',
    re.S,
)
LOCATION_RE = re.compile(r'sr-job-location[^>]*>(.*?)</span>', re.S)
TAG_RE = re.compile(r"<[^>]+>")

# GeoNames country ids, shared across Radancy tenants.
COUNTRY_IDS = {
    "uk": ("2635167", "United Kingdom"),
    "hong-kong": ("1819730", "Hong Kong SAR"),
    "china": ("1814991", "China"),
    "australia": ("2077456", "Australia"),
}


class RadancyAdapter:
    platform = "radancy"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _search(self, country_id, country_name, page):
        params = {
            "ActiveFacetID": country_id,
            "CurrentPage": page,
            "RecordsPerPage": PAGE_SIZE,
            "Distance": 50,
            "RadiusUnitType": 0,
            "Keywords": "",
            "Location": "",
            "ShowRadius": "False",
            "IsPagination": "False",
            "CustomFacetName": "",
            "FacetTerm": "",
            "FacetType": 0,
            "FacetFilters[0].ID": country_id,
            "FacetFilters[0].FacetType": 2,
            "FacetFilters[0].Count": 1,  # any positive number; the site echoes it
            "FacetFilters[0].Display": country_name,
            "FacetFilters[0].IsApplied": "true",
            "FacetFilters[0].FieldName": "",
            "SearchResultsModuleName": "Search Results",
            "SearchFiltersModuleName": "Search Filters",
            "SortCriteria": 5,
            "SortDirection": 1,
            "SearchType": 5,
            "PostalCode": "",
            "ResultsType": 0,
        }
        response = self.session.get(
            f"https://{self.firm['host']}/search-jobs/results",
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("results") or ""

    def fetch(self, max_pages=10):
        seen = set()
        for region in self.firm.get("regions") or list(COUNTRY_IDS):
            country_id, country_name = COUNTRY_IDS[region]
            for page in range(1, max_pages + 1):
                markup = self._search(country_id, country_name, page)
                cards = CARD_RE.findall(markup)
                if not cards:
                    break
                for href, job_id, title, rest in cards:
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    yield self._normalise(href, job_id, title, rest)
                if len(cards) < PAGE_SIZE:
                    break
                time.sleep(self.delay)

    def _normalise(self, href, job_id, title, rest):
        loc = LOCATION_RE.search(rest)
        location = html.unescape(TAG_RE.sub("", loc.group(1)).strip()) if loc else ""
        return {
            "source_id": job_id,
            "title": " ".join(html.unescape(title).split()),
            "url": f"https://{self.firm['host']}{href}",
            "location": location,
            "posted_on": "",
            "close_date": None,
            "time_type": "",
            "worker_sub_type": "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
