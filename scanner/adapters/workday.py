"""Workday adapter.

Workday powers more of these firms than anything else. Every tenant exposes the
same JSON search endpoint behind its careers page:

    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

The response carries `total`, a page of `jobPostings`, and `facets` describing
the filters that tenant supports. Where a tenant tags postings with a
`workerSubType` of "Intern" we apply that facet server-side, which cuts a
900-role board down to the ~40 that matter before we ever look at a title.
"""

import time

import requests

PAGE_SIZE = 20  # Workday caps the page size at 20 regardless of what we ask.
REQUEST_TIMEOUT = 30

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # Workday returns 406 to requests without a browser-ish UA.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}


class WorkdayAdapter:
    platform = "workday"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay  # polite pause between pages

    @property
    def _endpoint(self):
        return (
            f"https://{self.firm['host']}/wday/cxs/"
            f"{self.firm['tenant']}/{self.firm['site']}/jobs"
        )

    def _job_url(self, external_path):
        return f"https://{self.firm['host']}/en-US/{self.firm['site']}{external_path}"

    def fetch(self, max_pages=25):
        """Yield normalised posting dicts for this firm."""
        applied_facets = self.firm.get("facets") or {}
        offset = 0
        seen = 0
        total = None

        for page in range(max_pages):
            payload = {
                "appliedFacets": applied_facets,
                "limit": PAGE_SIZE,
                "offset": offset,
                # searchText is fuzzy and unreliable on Workday -- it happily
                # returns "Financial Crime Policy Lead" for "intern". We filter
                # on facets and titles instead and leave this empty.
                "searchText": "",
            }

            response = self.session.post(
                self._endpoint, json=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            body = response.json()

            if total is None:
                total = body.get("total", 0)

            postings = body.get("jobPostings") or []
            if not postings:
                break

            for raw in postings:
                yield self._normalise(raw)
                seen += 1

            offset += PAGE_SIZE
            if seen >= (total or 0):
                break
            time.sleep(self.delay)

    def _normalise(self, raw):
        location = raw.get("locationsText") or ""
        external_path = raw.get("externalPath") or ""
        req_ids = raw.get("bulletFields") or []

        return {
            "source_id": req_ids[0] if req_ids else external_path,
            "title": raw.get("title") or "",
            "url": self._job_url(external_path),
            "location": location,
            "posted_on": raw.get("postedOn") or "",
            "time_type": raw.get("timeType") or "",
            "worker_sub_type": raw.get("workerSubType") or "",
            # "2 Locations" means the summary hid the real offices; the detail
            # endpoint has them, and resolve_locations() fills these in.
            "location_is_vague": location.strip().lower().endswith("locations"),
            "external_path": external_path,
        }

    def resolve_location(self, posting):
        """Fetch the detail record for a posting whose location was collapsed.

        Workday summarises multi-office postings as "2 Locations", which is
        useless for region filtering -- a role in London and New York looks the
        same as one in Pune and Houston. This costs one extra request, so we
        only call it for the handful of vague ones.
        """
        detail_url = (
            f"https://{self.firm['host']}/wday/cxs/"
            f"{self.firm['tenant']}/{self.firm['site']}/job{posting['external_path']}"
        )
        try:
            response = self.session.get(
                detail_url, headers=HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            info = (response.json() or {}).get("jobPostingInfo") or {}
        except (requests.RequestException, ValueError):
            return posting

        parts = []
        if info.get("location"):
            parts.append(info["location"])
        for extra in info.get("additionalLocations") or []:
            parts.append(extra)
        if parts:
            posting["location"] = ", ".join(parts)
            posting["location_is_vague"] = False
        if info.get("startDate"):
            posting["posted_on"] = posting["posted_on"] or info["startDate"]
        return posting


def discover_intern_facet(firm, session=None):
    """Return the workerSubType facet id that means "Intern" for this tenant.

    Facet ids are per-tenant hashes, so they can't be hardcoded across firms --
    but they're stable for a given tenant, so we look one up once and cache it
    in the firm config.
    """
    session = session or requests.Session()
    endpoint = (
        f"https://{firm['host']}/wday/cxs/{firm['tenant']}/{firm['site']}/jobs"
    )
    response = session.post(
        endpoint,
        json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    for facet in response.json().get("facets") or []:
        if facet.get("facetParameter") != "workerSubType":
            continue
        for value in facet.get("values") or []:
            if (value.get("descriptor") or "").strip().lower() in ("intern", "student"):
                return value.get("id"), value.get("count")
    return None, 0
