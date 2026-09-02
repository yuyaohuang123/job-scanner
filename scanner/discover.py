"""Resolve a firm's careers URL into a ready-to-paste firms.yml block.

Site ids are per-tenant and cannot be guessed -- a candidate list of the obvious
names ("External", "Careers", ...) was tried against a live tenant during setup
and missed every time. But they are sitting in plain sight in the public
careers URL, so the fast path is: find the URL once, let this parse it.

    python -m scanner.discover https://barclays.wd3.myworkdayjobs.com/External_Career_Site_Barclays
    python -m scanner.discover https://boards.greenhouse.io/someboard
    python -m scanner.discover https://jobs.lever.co/somecompany

It also probes the endpoint and reports how many postings and interns it sees,
so a bad guess fails here rather than silently returning nothing every morning.
"""

import re
import sys
from urllib.parse import urlparse

import requests

from .adapters.workday import discover_intern_facet

WORKDAY_HOST_RE = re.compile(r"^(?P<tenant>[^.]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com$", re.I)


def discover_workday(url):
    parsed = urlparse(url)
    match = WORKDAY_HOST_RE.match(parsed.netloc)
    if not match:
        return None

    tenant = match.group("tenant")
    # Path is /<site> or /<locale>/<site>, e.g. /en-US/External_Career_Site_X
    segments = [s for s in parsed.path.split("/") if s]
    segments = [s for s in segments if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", s)]
    if not segments:
        print("Could not find a site id in that URL path.", file=sys.stderr)
        return None
    site = segments[0]

    firm = {"host": parsed.netloc, "tenant": tenant, "site": site}

    session = requests.Session()
    try:
        facet_id, intern_count = discover_intern_facet(firm, session=session)
    except requests.RequestException as exc:
        print(f"Endpoint check failed: {exc}", file=sys.stderr)
        return None

    lines = [
        "  - name: CHANGE_ME",
        "    tier: CHANGE_ME",
        "    platform: workday",
        "    enabled: true",
        f"    host: {parsed.netloc}",
        f"    tenant: {tenant}",
        f"    site: {site}",
    ]
    if facet_id:
        lines += [
            "    facets:",
            f'      workerSubType: ["{facet_id}"]  # Intern ({intern_count} open)',
        ]
    else:
        lines.append("    # no Intern facet on this tenant; filtering falls back to titles")

    return "\n".join(lines)


def discover_board(url, platform):
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return None
    board = segments[0]
    return "\n".join(
        [
            "  - name: CHANGE_ME",
            "    tier: CHANGE_ME",
            f"    platform: {platform}",
            "    enabled: true",
            f"    board: {board}",
        ]
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    url = sys.argv[1]
    host = urlparse(url).netloc.lower()

    if "myworkdayjobs.com" in host:
        block = discover_workday(url)
    elif "greenhouse.io" in host:
        block = discover_board(url, "greenhouse")
    elif "lever.co" in host:
        block = discover_board(url, "lever")
    else:
        print(f"Unrecognised platform for host {host!r}.", file=sys.stderr)
        print("Supported: myworkdayjobs.com, greenhouse.io, lever.co", file=sys.stderr)
        return 1

    if not block:
        return 1

    print("\nAdd this to scanner/config/firms.yml:\n")
    print(block)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
