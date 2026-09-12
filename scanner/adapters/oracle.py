"""Oracle Recruiting Cloud adapter (J.P. Morgan and others on Oracle HCM).

The candidate-experience site is backed by a public REST finder:

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&expand=requisitionList.secondaryLocations
        &finder=findReqs;siteNumber={site},selectedLocationsFacet={id},limit=100,offset=0

Keyword search is fuzzy (it matches description text -- "placement" pulls in
branch-manager roles), so we don't use it. Instead we filter by the location
facet for each of our countries, which is exact, then title-match. Facet ids
are stable per tenant; they're discovered once by searching for a city in
that country and reading the facet back.
"""

import time

import requests

PAGE_SIZE = 100  # the finder honours up to 100 per page
REQUEST_TIMEOUT = 30
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-tracker/1.0"}


class OracleAdapter:
    platform = "oracle"

    def __init__(self, firm, session=None, delay=1.0):
        self.firm = firm
        self.session = session or requests.Session()
        self.delay = delay

    def _finder_url(self, location_id, offset):
        return (
            f"https://{self.firm['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            "?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={self.firm['site']},"
            f"selectedLocationsFacet={location_id},limit={PAGE_SIZE},offset={offset}"
        )

    def _job_url(self, req_id):
        return (
            f"https://{self.firm['host']}/hcmUI/CandidateExperience/en/sites/"
            f"{self.firm['site']}/job/{req_id}"
        )

    def fetch(self, max_pages=20):
        seen = set()
        for location_id in self.firm.get("locations") or []:
            offset = 0
            for _ in range(max_pages):
                response = self.session.get(
                    self._finder_url(location_id, offset), headers=HEADERS, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                items = response.json().get("items") or []
                if not items:
                    break
                block = items[0]
                reqs = block.get("requisitionList") or []
                for raw in reqs:
                    key = str(raw.get("Id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    yield self._normalise(raw)
                total = block.get("TotalJobsCount", 0)
                offset += PAGE_SIZE
                if offset >= total or not reqs:
                    break
                time.sleep(self.delay)

    def _normalise(self, raw):
        locations = [raw.get("PrimaryLocation") or ""]
        for extra in raw.get("secondaryLocations") or []:
            name = extra.get("Name") if isinstance(extra, dict) else None
            if name:
                locations.append(name)
        return {
            "source_id": str(raw.get("Id")),
            "title": raw.get("Title") or "",
            "url": self._job_url(raw.get("Id")),
            "location": "; ".join(l for l in locations if l),
            "country": raw.get("PrimaryLocationCountry") or "",
            "posted_on": raw.get("PostedDate") or "",
            "close_date": raw.get("PostingEndDate") or None,
            "time_type": raw.get("JobSchedule") or "",
            "worker_sub_type": raw.get("WorkerType") or raw.get("JobType") or "",
            "location_is_vague": False,
            "external_path": "",
        }

    def resolve_location(self, posting):
        return posting
