# Internship scanner — UK & China mainland

Scans firms' career sites once a day, finds internship and industrial-placement
listings in the UK and China mainland, emails you what's new, and feeds a
tracker site where you record your own application progress.

## How it works

```
GitHub Actions (daily 06:15 UTC)
  └─ scanner/scan.py
       ├─ adapters/   one per ATS platform (Workday, Greenhouse, Lever)
       ├─ filters.py  is this an internship? is it UK or China?
       ├─ store.py    merge into data/listings.json, diff against yesterday
       ├─ digest.py   email only what changed
       └─ site/data.js regenerated for the tracker UI
```

The design bet is that these firms don't hand-roll their careers pages — they
run on a handful of applicant tracking systems. Writing one adapter per
*platform* rather than one scraper per *firm* means adding a firm is usually
three lines of config, not a new scraper.

## Status

**Verified working:** Barclays (Workday). The live API returns 808 open roles,
40 tagged `Intern`, filterable server-side.

**Not yet configured:** the other ~40 firms in `scanner/config/firms.yml` are
listed as targets with `enabled: false`. Each needs its endpoint resolved once
— see below.

## Adding a firm

Find the firm's careers URL, then let the discovery tool parse it:

```bash
python -m scanner.discover https://barclays.wd3.myworkdayjobs.com/External_Career_Site_Barclays
```

It prints a ready-to-paste `firms.yml` block, including the tenant's "Intern"
facet id, and fails loudly if the endpoint doesn't respond — so a bad guess
surfaces now rather than silently returning nothing every morning.

Site ids can't be guessed: an obvious candidate list (`External`, `Careers`,
`External_Career_Site`, …) was tried against a live tenant and missed every
time. They are, however, sitting in the public careers URL.

## Running it locally

```bash
pip install -r requirements.txt
python -m scanner.scan --dry-run          # scan, print results, write nothing
python -m scanner.scan --firm Barclays    # one firm
python -m scanner.scan                    # full run, updates store + site
python -m scanner.digest --print          # preview the email without sending
```

## Deploying

1. Create a GitHub repo and push this folder.
2. In **Settings → Secrets and variables → Actions**, add:

   | Secret | Value |
   |---|---|
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | your sending address |
   | `SMTP_PASSWORD` | a Gmail **app password**, not your account password |
   | `DIGEST_TO` | where the digest goes |

3. **Actions → Daily job scan → Run workflow** to test it immediately.
4. Optional: **Settings → Pages**, serve from `/site`, and the tracker is
   readable from your phone.

Without the SMTP secrets everything still works — the scan just skips the email
and you read results on the site.

## Design notes

**Word boundaries in the title matcher.** A naive `"intern" in title` also
matches "**Intern**ational Banking" and "**Intern**al Audit". `filters.py` uses
`\b`-anchored patterns, which is why those don't leak in.

**Hong Kong is excluded.** The brief was China *mainland*, so HK, Macau and
Taiwan don't match. A lot of Western-bank APAC finance sits in Hong Kong, so if
you want it, flip `INCLUDE_HONG_KONG = True` in `filters.py`.

**"2 Locations".** Workday collapses multi-office postings into a useless
summary. The adapter detects that and fetches the detail record for just those
few, so a London+NYC role isn't mistaken for a Pune+Houston one.

**Failed firms don't lose data.** If a firm's API is down, its existing
listings stay `open` rather than being marked closed by a scan that simply
couldn't see them.

**`data.js`, not `data.json`.** The site is generated as a script assigning a
global, so it still works opened straight off disk — `fetch()` on a `file://`
URL is blocked by CORS, a `<script>` tag isn't.

**Politeness.** One request per page with a 1s pause, no parallel hammering,
and the intern facet applied server-side so we pull ~40 records instead of 800.

## Caveat

Scrapers break. Career sites get redesigned, tenants move, site ids change. The
digest emails you when a firm errors, which is the signal to re-run
`scanner.discover` for that firm.
