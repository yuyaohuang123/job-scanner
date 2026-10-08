"""Classify raw postings into the roles and regions we actually care about.

Every adapter returns loosely-shaped postings; this module is the single place
that decides "is this an internship or placement?" and "is this in one of
our regions?". Keeping it separate means one fix improves every firm at once.
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
    "placement analyst",   # Citi's name for an off-cycle internship
    "seasonal analyst",    # J.P. Morgan's
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
    "one year placement",
    "one-year placement",
    "year long placement",
    "year-long placement",
    "business placement",     # KPMG's "One Year Business Placement"
    "placement programme",
    "placement program",
    "placement scheme",
)

# Graduate-role titles: "Full Time Analyst", "Full-Time Associate". Narrow on
# purpose -- "Full-time Summer Intern" is a real internship and must survive.
# Corporates label placement years without the word "internship": Pfizer's
# "Finance Undergraduate", BMW's "Finance Placement", "Year in Industry".
# Checked only after the explicit internship patterns, so "Undergrad Intern"
# still classifies as an internship rather than a placement.
STUDENT_RE = _words(
    "undergraduate", "undergrads", "undergrad",
    "placement", "placements", "placement year", "industrial year",
)

# The STUDENT_RE fallback is weak evidence, so it loses to any professional or
# seniority marker. This is what keeps insurance broking out: in that trade
# "placement" means placing risk in the market, giving titles like "Senior
# Placement Broker" and "Placement Support Specialist".
SENIORITY_RE = _words(
    "senior", "lead", "principal", "manager", "director", "head",
    "vice president", "avp", "svp", "vp", "executive", "officer",
    "specialist", "technician", "broker", "broking", "consultant",
    "administrator", "adviser", "advisor", "partner", "associate director",
)

FULL_TIME_RE = re.compile(r"full[ -]?time\s+(analyst|associate|graduate|hire)", re.IGNORECASE)

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
    # "Private Placements" is a debt/equity product, not a student placement --
    # the bare "placement" fallback above would otherwise claim these.
    "private placement",
    "private placements",
    "placement agent",
    "equity placement",
    "debt placement",
    "placement coordinator",
    "placement manager",
    "placement officer",
)


def classify_role(title, worker_sub_type=None):
    """Return 'internship', 'placement' or None.

    `worker_sub_type` is the platform's own tag (e.g. Workday's "Intern"). When
    the platform tells us directly we trust it, since it's set by the employer
    rather than inferred from marketing copy in a job title.
    """
    title = title or ""

    # A graduate-role title loses whatever else it says. Morgan Stanley tags
    # "Full Time Analyst Programme" as Internship; Citi's conversions read
    # "Full Time Analyst ... (Applicable for 2026 Summer interns only)".
    if FULL_TIME_RE.search(title):
        return None

    if PLACEMENT_RE.search(title):
        return "placement"

    if INTERNSHIP_RE.search(title):
        return "internship"

    if STUDENT_RE.search(title) and not SENIORITY_RE.search(title):
        return "placement"

    # The platform's own label, for titles that don't say ("2027 Analyst,
    # London" tagged Intern; HSBC's "Programme type: Internship Programme").
    # Graduate schemes are explicitly not what we want, so they lose even
    # when a label also mentions placements.
    label = (worker_sub_type or "").strip().lower()
    # "graduate" rules a label out -- but "undergraduate" contains it.
    is_grad_label = "graduate" in label and "undergraduate" not in label
    if label and not is_grad_label:
        if PLACEMENT_RE.search(label) or label == "placement":
            return "placement"
        if INTERNSHIP_RE.search(label) or label in ("student", "seasonal", "undergraduate"):
            return "internship"

    return None


def is_excluded(title):
    """True for titles that mention internships but aren't one."""
    return bool(EXCLUDE_RE.search(title or ""))


# --- Function classification ---------------------------------------------
#
# Only used for firms whose config sets `finance_only: true` -- the large
# non-financial corporates (BMW, Unilever, AstraZeneca ...). Their boards are
# mostly engineering, marketing and operations; this keeps the finance
# function: treasury, audit, strategy, tax, accounting, controlling, FP&A.
# At a bank every role is in scope, so the flag is left off there.

FINANCE_FUNCTION_RE = _words(
    "finance", "financial", "financials",
    "treasury", "treasurer",
    "audit", "audits", "auditing", "auditor",
    "accounting", "accountancy", "accountant", "accounts", "aca", "acca", "cima",
    "tax", "taxation",
    "controlling", "controller", "comptroller",
    "strategy", "strategic", "strategist",
    "fp&a", "investor relations", "corporate development",
    "m&a", "mergers", "acquisitions", "corporate finance",
    "commercial finance", "business finance", "group finance",
    "actuarial", "economics", "economist",
    "credit", "capital markets", "procurement finance",
)

# Words that make a "finance-sounding" title something else entirely:
# "Cyber Risk", "Quality Audit", "Safety Audit", "Clinical Strategy".
FUNCTION_EXCLUDE_RE = _words(
    "cyber", "cybersecurity", "information security", "infosec",
    "health and safety", "safety", "quality", "clinical", "medical",
    "environmental", "energy audit", "supplier audit", "food", "patient",
)


def is_finance_function(title):
    """True if a corporate posting sits in the finance function."""
    title = title or ""
    if FUNCTION_EXCLUDE_RE.search(title):
        return False
    return bool(FINANCE_FUNCTION_RE.search(title))


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
    # UK is handled separately below: its country markers are unambiguous but
    # its town names collide with American ones, so the two are judged
    # differently.
]

# Unambiguous "this is in the UK" markers.
UK_STRONG = [
    "united kingdom", "england", "scotland", "wales", "northern ireland",
    "great britain", "gb-", "(uk)", " uk", ",uk", "u.k.",
]

# UK towns and employer sites. Matched on word boundaries, and only trusted
# when the text carries no non-UK country or US-state marker (see below) --
# which is what separates Cambridge from Cambridge, MA.
#
# This list is deliberately long: it was originally built around bank offices
# (London, Glasgow, Birmingham) and silently dropped every corporate site, so
# Airbus's finance placements at Broughton, Filton and Stevenage never
# reached the digest.
UK_CITIES = [
    # London and its financial districts
    "london", "canary wharf", "churchill place", "bank street", "moorgate",
    "liverpool street", "broadgate", "bishopsgate", "city of london",
    "croydon", "uxbridge", "brentford", "hounslow", "staines", "chertsey",
    "egham", "watford", "borehamwood", "enfield", "barnet", "harrow",
    # major cities
    "birmingham", "glasgow", "edinburgh", "manchester", "leeds", "bristol",
    "liverpool", "sheffield", "newcastle", "nottingham", "leicester",
    "coventry", "bradford", "wolverhampton", "plymouth", "derby", "swansea",
    "aberdeen", "dundee", "sunderland", "hull", "stoke", "stoke-on-trent",
    "belfast", "cardiff", "newport", "wrexham", "lisburn", "londonderry",
    "inverness", "stirling", "falkirk", "livingston", "paisley", "kilmarnock",
    # the Thames Valley / M4 / M3 corridor, where most corporate HQs sit
    "reading", "bracknell", "slough", "maidenhead", "windsor", "woking",
    "guildford", "farnborough", "fleet", "camberley", "aldershot", "basingstoke",
    "newbury", "thatcham", "wokingham", "weybridge", "walton oaks", "leatherhead",
    "epsom", "redhill", "crawley", "gatwick", "horsham", "chichester",
    # the Oxford / Cambridge / M1 arc
    "oxford", "cambridge", "abingdon", "didcot", "harwell", "culham",
    "bicester", "banbury", "aylesbury", "high wycombe", "hemel hempstead",
    "st albans", "welwyn", "hatfield", "stevenage", "hertford", "ware",
    "luton", "milton keynes", "bedford", "northampton", "rugby", "daventry",
    "corby", "kettering", "wellingborough", "huntingdon", "peterborough",
    "royston", "letchworth", "hitchin", "stansted",
    # the North and Midlands industrial belt
    "knutsford", "radbroke", "chester", "broughton", "warrington", "crewe",
    "macclesfield", "alderley park", "stockport", "salford", "oldham",
    "rochdale", "bolton", "wigan", "preston", "blackburn", "burnley",
    "blackpool", "lancaster", "carlisle", "barrow", "middlesbrough",
    "darlington", "durham", "gateshead", "halifax", "huddersfield",
    "wakefield", "doncaster", "rotherham", "barnsley", "chesterfield",
    "mansfield", "telford", "shrewsbury", "stafford", "burton", "tamworth",
    "solihull", "redditch", "worcester", "hereford", "gloucester",
    "cheltenham", "swindon", "warwick", "whitley", "gaydon", "halewood",
    "ellesmere port", "deeside", "burnaston", "castle bromwich",
    # the South and South West
    "southampton", "portsmouth", "winchester", "salisbury", "bournemouth",
    "poole", "exeter", "plymouth", "taunton", "yeovil", "bath", "truro",
    "brighton", "worthing", "eastbourne", "hastings", "canterbury",
    "maidstone", "ashford", "dartford", "rochester", "chatham", "southend",
    "basildon", "chelmsford", "colchester", "ipswich", "norwich", "cowley",
    # aerospace / defence / energy sites
    "filton", "warton", "samlesbury", "brough", "yeovilton", "barnoldswick",
    "hucknall", "goodwood", "dunton", "bridgend", "port talbot", "scunthorpe",
    "grangemouth", "fawley", "stanlow", "immingham", "sandwich",
    "barnard castle", "speke", "ulverston", "sellafield", "aldermaston",
]

# If any of these appear, a UK-looking town name is somewhere else:
# "Cambridge, MA", "Birmingham, AL", "Newcastle, Australia".
NON_UK_MARKERS = [
    "united states", "u.s.", "usa", "canada", "mexico", "brazil",
    "germany", "france", "spain", "italy", "netherlands", "belgium",
    "switzerland", "austria", "poland", "czech", "hungary", "romania",
    "sweden", "norway", "denmark", "finland", "portugal", "greece",
    "turkey", "india", "japan", "korea", "singapore", "malaysia",
    "thailand", "vietnam", "indonesia", "philippines", "australia",
    "new zealand", "south africa", "israel", "uae", "dubai", "qatar",
    "saudi", "egypt", "nigeria", "kenya", "argentina", "chile", "colombia",
    # US state abbreviations, as they appear in "Atlanta Area, GA"
    ", al", ", ak", ", az", ", ar", ", ca", ", co", ", ct", ", de", ", fl",
    ", ga", ", hi", ", id", ", il", ", in", ", ia", ", ks", ", ky", ", la",
    ", me", ", md", ", ma", ", mi", ", mn", ", ms", ", mo", ", mt", ", ne",
    ", nv", ", nh", ", nj", ", nm", ", ny", ", nc", ", nd", ", oh", ", ok",
    ", or", ", pa", ", ri", ", sc", ", sd", ", tn", ", tx", ", ut", ", vt",
    ", va", ", wa", ", wv", ", wi", ", wy", ", dc",
]

# Places that share a name with somewhere we care about. Each is stripped
# from the text before matching so the remainder is judged on its own.
FALSE_FRIENDS = [
    "new london",            # Connecticut
    "new york",              # otherwise "York" reads as Yorkshire
    "london, ontario",       # Canada
    "london, on",
    "london, ky",
    "birmingham, al",
    "birmingham, alabama",
    "manchester, nh",
    "cambridge, ma",
    "cambridge, massachusetts",
    "china town",
    "chinatown",
    "taiwan", "taipei", "macau", "macao",
]

_UK_CITY_RE = _words(*UK_CITIES)


def classify_region(location_text, country=None):
    """Return a region name, or None.

    Country-level markers decide outright. A bare UK town name is weaker
    evidence, so it only counts when nothing in the text points abroad.
    """
    haystack = " ".join(filter(None, [location_text, country])).lower()
    if not haystack.strip():
        return None

    for bad in FALSE_FRIENDS:
        if bad in haystack:
            haystack = haystack.replace(bad, " ")

    for name, terms in REGIONS:
        if any(term in haystack for term in terms):
            return name

    if any(term in haystack for term in UK_STRONG):
        return "uk"

    if _UK_CITY_RE.search(haystack) and not any(m in haystack for m in NON_UK_MARKERS):
        return "uk"

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
