"""Classify raw postings into the roles and regions we actually care about.

Every adapter returns loosely-shaped postings; this module is the single place
that decides "is this an internship or placement?" and "is this UK or China
mainland?". Keeping it separate means one fix improves every firm at once.
"""

import re


def _words(*terms):
    """Build a regex that matches any term on word boundaries.

    Word boundaries matter more than they look: a naive `"intern" in title`
    also matches "International Banking" and "Internal Audit", which would
    poison the results with senior roles.
    """
    joined = "|".join(re.escape(t) for t in terms)
    # The alternation MUST be wrapped in a non-capturing group. Without it,
    # `|` (lowest precedence in regex) binds looser than the lookarounds, so
    # `(?<![a-z])a|b|c(?![a-z])` means "a with a leading boundary" OR "bare b"
    # OR "c with a trailing boundary" -- and unanchored `intern` then happily
    # matches "International".
    return re.compile(rf"(?<![a-z])(?:{joined})(?![a-z])", re.IGNORECASE)


# --- Role classification -------------------------------------------------

INTERNSHIP_RE = _words(
    "intern",
    "interns",
    "internship",
    "internships",
    "summer analyst",
    "summer associate",
    "summer scheme",
    "summer programme",
    "summer program",
    "spring week",
    "spring insight",
    "spring programme",
    "insight programme",
    "insight program",
    "insight week",
    "off-cycle",
    "off cycle",
    "offcycle",
    "vacation scheme",
    "vacation programme",
)

PLACEMENT_RE = _words(
    "industrial placement",
    "placement year",
    "year in industry",
    "yearly placement",
    "sandwich placement",
    "sandwich year",
    "undergraduate placement",
    "work placement",
    "12 month placement",
    "12-month placement",
    "student placement",
    "placement student",
    "industrial trainee",
)

# Titles that are ABOUT the internship programme rather than a seat on it.
# These always lose, even though they contain a perfectly good "internship".
#
# Note there's no need to list "internal" or "international" here: with correct
# word boundaries they never match the internship patterns in the first place.
EXCLUDE_RE = _words(
    "internal audit",
    "intern supervisor",
    "internship manager",
    "internship coordinator",
    "internship lead",
    "programme manager",
    "program manager",
    "recruiter",
    "recruiting manager",
    "campus recruiter",
)


def classify_role(title, worker_sub_type=None):
    """Return 'internship', 'placement' or None.

    `worker_sub_type` is the platform's own tag (e.g. Workday's "Intern"). When
    the platform tells us directly we trust it, since it's set by the employer
    rather than inferred from marketing copy in a job title.
    """
    title = title or ""

    if PLACEMENT_RE.search(title):
        return "placement"

    if INTERNSHIP_RE.search(title):
        return "internship"

    # The platform's own label, for titles that don't say ("2027 Analyst,
    # London" tagged Intern; HSBC's "Programme type: Internship Programme").
    # Graduate schemes are explicitly not what we want, so they lose even
    # when a label also mentions placements.
    label = (worker_sub_type or "").strip().lower()
    if label and "graduate" not in label:
        if "placement" in label:
            return "placement"
        if "intern" in label or label == "student":
            return "internship"

    return None


def is_excluded(title):
    """True for titles that mention internships but aren't one."""
    return bool(EXCLUDE_RE.search(title or ""))


# --- Region classification ----------------------------------------------

# Ordered: the first region whose terms appear wins. Hong Kong is checked
# before China so "Hong Kong, China" lands in the right bucket.
REGIONS = [
    ("hong-kong", [
        "hong kong", "hongkong", "kowloon", "causeway bay", "admiralty",
        "central, hk", " hk",
    ]),
    ("china", [
        "china", "mainland china", "shanghai", "beijing", "shenzhen",
        "guangzhou", "chengdu", "hangzhou", "tianjin", "nanjing", "suzhou",
        "wuhan", "xi'an", "dalian", "qingdao", "chongqing",
    ]),
    ("australia", [
        "australia", "sydney", "melbourne", "brisbane", "perth", "canberra",
        "adelaide", "gold coast", "barangaroo", "collins street",
    ]),
    ("uk", [
        "united kingdom", "england", "scotland", "wales", "northern ireland",
        "london", "canary wharf", "churchill place", "bank street", "moorgate",
        "liverpool street", "broadgate", "bishopsgate", "city of london",
        "birmingham", "glasgow", "edinburgh", "manchester", "leeds", "bristol",
        "belfast", "cardiff", "sheffield", "nottingham", "reading", "cambridge",
        "oxford", "knutsford", "radbroke", "northampton", "bournemouth",
        "chester", "swindon", "milton keynes", "gb-", "(uk)", " uk",
    ]),
]

# Places that share a name with somewhere we care about. Each is stripped
# from the text before matching so the remainder is judged on its own.
FALSE_FRIENDS = [
    "new london",            # Connecticut
    "london, ontario",       # Canada
    "london, on",
    "london, ky",
    "birmingham, al",
    "birmingham, alabama",
    "manchester, nh",
    "cambridge, ma",
    "cambridge, massachusetts",
    "melbourne, fl",         # Florida
    "melbourne, florida",
    "sydney, ns",            # Nova Scotia
    "sydney, nova scotia",
    "perth, scotland",       # the original Perth -- routed to UK below
    "perth, uk",
    "china town",
    "chinatown",
    "taiwan", "taipei", "macau", "macao",
]


def classify_region(location_text, country=None):
    """Return a region name from REGIONS, or None."""
    haystack = " ".join(filter(None, [location_text, country])).lower()
    if not haystack.strip():
        return None

    # Perth is in Scotland as well as Western Australia. For these firms the
    # Australian one is overwhelmingly more likely, unless the text says
    # otherwise -- so decide that before the false friends are stripped.
    if "perth" in haystack and any(t in haystack for t in ("scotland", "united kingdom", " uk")):
        return "uk"

    for bad in FALSE_FRIENDS:
        if bad in haystack:
            haystack = haystack.replace(bad, " ")

    for name, terms in REGIONS:
        if any(term in haystack for term in terms):
            return name

    return None


def keep(posting):
    """Final yes/no for a normalised posting dict.

    Returns (keep: bool, category: str|None, region: str|None).
    """
    title = posting.get("title", "")

    if is_excluded(title):
        return False, None, None

    category = classify_role(title, posting.get("worker_sub_type"))
    if not category:
        return False, None, None

    region = classify_region(posting.get("location", ""), posting.get("country"))
    if not region:
        return False, category, None

    return True, category, region
