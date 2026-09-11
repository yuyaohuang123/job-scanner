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

import sys
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
        """Yield normalised posting dicts for this firm, de-duplicated.

        Config may give `passes`: a list of appliedFacets dicts, each run as
        its own query with results unioned. Two passes are typical -- one on
        the tenant's intern facet (precise but sometimes incomplete) and one
        on its country facet (complete for our regions, title-filtered
        later). A legacy single `facets` dict is treated as one pass, and no
        config at all means one unfiltered pass, capped by max_pages.
        """
        passes = self.firm.get("passes")
        if not passes:
            passes = [self.firm.get("facets") or {}]

        seen_ids = set()
        for applied in passes:
            try:
                for posting in self._fetch_pass(applied, max_pages):
                    key = posting["source_id"]
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    yield posting
            except requests.HTTPError as exc:
                # A stale facet id (tenants do reshuffle them) makes Workday
                # answer 400 for that pass. Losing one pass is a degraded scan;
                # losing the whole firm to it would be silent data loss.
                if len(passes) > 1 and exc.response is not None and exc.response.status_code == 400:
                    print(f"   warning: {self.firm['name']} pass {applied} rejected (400); skipped",
                          file=sys.stderr)
                    continue
                raise

    def _fetch_pass(self, applied_facets, max_pages):
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


# Facet value descriptors that mean "this is an early-careers posting".
# Substring match, lower-cased. "internal" is guarded against separately.
INTERN_FACET_TERMS = ("intern", "student", "campus", "early career", "early-career",
                      "graduate program", "graduate programme", "placement")

# Country descriptors we want, mapped from how tenants tend to spell them.
COUNTRY_FACET_TERMS = ("united kingdom", "hong kong", "australia", "china")

# Facet parameters that hold a country-level location, in preference order.
COUNTRY_FACET_PARAMS = ("Location_Country", "locationCountry", "Country",
                        "country", "locationMainGroup", "locations")


def _fetch_facets(firm, session):
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
    body = response.json()
    return body.get("facets") or [], body.get("total", 0)


def _is_intern_descriptor(text):
    text = (text or "").strip().lower()
    if "internal" in text or "international" in text:
        # "Internal Audit" is a job family; guard it explicitly since we're
        # substring-matching "intern" here.
        text = text.replace("internal", "").replace("international", "")
    return any(term in text for term in INTERN_FACET_TERMS)


def discover_facets(firm, session=None):
    """Work out which server-side filters this tenant supports.

    Returns a dict with up to two entries, each `(facetParameter, [ids], count)`:

        intern   -- values tagging early-careers postings. Applying this on
                    Barclays turns 808 roles into 40 before a title is read.
        country  -- values for the countries we care about. Big tenants
                    (Wells Fargo: 1,873 roles) can't be paginated daily, but
                    the 30 of them in the UK can.

    Facet ids are per-tenant hashes, so they can't be hardcoded across firms,
    but they're stable for a tenant -- look them up once, keep them in config.
    """
    session = session or requests.Session()
    facets, total = _fetch_facets(firm, session)
    found = {"total": total}

    # Intern-type facet: prefer workerSubType (employment type) over
    # jobFamilyGroup, which is a coarser taxonomy that sometimes mislabels.
    for preferred in ("workerSubType", "jobFamilyGroup", "timeType"):
        for facet in facets:
            if facet.get("facetParameter") != preferred:
                continue
            hits = [
                (v["id"], v.get("count", 0))
                for v in facet.get("values") or []
                if _is_intern_descriptor(v.get("descriptor"))
            ]
            if hits:
                found["intern"] = (preferred, [h[0] for h in hits], sum(h[1] for h in hits))
                break
        if "intern" in found:
            break

    # Country facet. Some tenants nest location facets one level deep
    # (locationMainGroup -> a child facet "locations" -> office values); the
    # ids in that case belong to the CHILD's facetParameter, not the parent's,
    # and applying them under the parent's name is a 400.
    by_param = {}
    for facet in facets:
        for param, value in _walk_facet_values(facet):
            if any(t in (value.get("descriptor") or "").lower() for t in COUNTRY_FACET_TERMS):
                by_param.setdefault(param, []).append((value["id"], value.get("count", 0)))
    if by_param:
        # Prefer a true country-level parameter; otherwise whichever matched most.
        ordered = sorted(
            by_param.items(),
            key=lambda kv: (
                kv[0] not in COUNTRY_FACET_PARAMS,
                COUNTRY_FACET_PARAMS.index(kv[0]) if kv[0] in COUNTRY_FACET_PARAMS else 99,
                -len(kv[1]),
            ),
        )
        param, hits = ordered[0]
        found["country"] = (param, [h[0] for h in hits], sum(h[1] for h in hits))

    return found


def _walk_facet_values(facet, param=None):
    """Yield (facetParameter, value) for every leaf value under a facet.

    A value carrying its own `facetParameter` and `values` is a nested facet;
    its children are attributed to it, not to the top-level parameter.
    """
    param = facet.get("facetParameter") or param
    for value in facet.get("values") or []:
        if value.get("values"):
            yield from _walk_facet_values(value, param)
        elif value.get("id"):
            yield param, value


def discover_intern_facet(firm, session=None):
    """Back-compat shim: return (first intern facet id, count) or (None, 0)."""
    found = discover_facets(firm, session=session)
    if "intern" in found:
        _, ids, count = found["intern"]
        return ids[0], count
    return None, 0
