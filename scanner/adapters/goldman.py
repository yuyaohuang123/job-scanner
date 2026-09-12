"""Goldman Sachs campus adapter.

higher.gs.com is a Next.js app over a GraphQL gateway on a separate host:

    POST https://api-higher.gs.com/gateway/api/v1/graphql
    operation GetCampusRoles, variables.searchQueryInput = {
        page: {pageSize, pageNumber}, filters: [], experiences: ["CAMPUS"],
        searchTerm: ""
    }

Found by reading the bundle: the results page is `roleSearch` with an
`experiences` switch (CAMPUS vs EARLY_CAREER/PROFESSIONAL), and the API
host comes from an env constant rather than the page origin -- posting to
higher.gs.com/gateway/... is a 404.

Roles carry `corporateTitle` ("Summer Analyst", "Seasonal", ...) which is
more reliable than the title for classification, and a structured country.
"""

import time
import uuid

import requests

ENDPOINT = "https://api-higher.gs.com/gateway/api/v1/graphql"
ROLE_URL = "https://higher.gs.com/roles/{role_id}"
PAGE_SIZE = 50
REQUEST_TIMEOUT = 30

QUERY = """
query GetCampusRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId
      corporateTitle
      jobTitle
      division
      status
      startDate
      locations { primary country city state }
    }
  }
}
"""


class GoldmanAdapter:
    platform = "goldman"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 job-tracker/1.0",
            "Origin": "https://higher.gs.com",
            "Referer": "https://higher.gs.com/campus",
            # The site attaches a request id per call; harmless to mirror.
            "x-higher-request-id": str(uuid.uuid4()),
        }

    def fetch(self, max_pages=20):
        page = 0
        seen = 0
        while page < max_pages:
            payload = {
                "operationName": "GetCampusRoles",
                "query": QUERY,
                "variables": {
                    "searchQueryInput": {
                        "page": {"pageSize": PAGE_SIZE, "pageNumber": page},
                        "filters": [],
                        "experiences": self.firm.get("experiences") or ["CAMPUS"],
                        "searchTerm": "",
                    }
                },
            }
            response = self.session.post(
                ENDPOINT, json=payload, headers=self._headers(), timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            body = response.json()
            if body.get("errors"):
                raise ValueError(f"Goldman GraphQL error: {body['errors'][0].get('message')}")
            search = (body.get("data") or {}).get("roleSearch") or {}
            items = search.get("items") or []
            for raw in items:
                yield self._normalise(raw)
            seen += len(items)
            page += 1
            if not items or seen >= int(search.get("totalCount") or 0):
                break
            time.sleep(self.delay)

    def _normalise(self, raw):
        locations = raw.get("locations") or []
        primary = next((l for l in locations if l.get("primary")), locations[0] if locations else {})
        location = ", ".join(p for p in (primary.get("city"), primary.get("country")) if p)
        started = raw.get("startDate") or ""
        return {
            "source_id": str(raw.get("roleId")),
            "title": " ".join((raw.get("jobTitle") or "").split()),
            "url": ROLE_URL.format(role_id=raw.get("roleId")),
            "location": location,
            "country": primary.get("country") or "",
            "posted_on": started[:10] if started else "",
            "close_date": None,
            "time_type": "",
            # "Summer Analyst" / "Seasonal" / "Summer Associate" -- the firm's
            # own label. "Analyst" alone is a full-time campus hire.
            "worker_sub_type": raw.get("corporateTitle") or "",
            "division": raw.get("division") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
