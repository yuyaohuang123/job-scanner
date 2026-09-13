"""Probe Greenhouse and Lever for candidate board slugs. Reports hits only.

    python tools/probe_boards.py hits.json

Board slugs on these platforms are usually just the company name, so a
broad guess list is cheap to try -- one unauthenticated GET each -- and
turns up firms that would otherwise need a careers page hunted down by hand.
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import filters  # noqa: E402

S = requests.Session()
S.headers["User-Agent"] = "job-tracker/1.0"

# name -> candidate slugs to try
CANDIDATES = {
    # trading & quant
    "Optiver": ["optiver"], "IMC Trading": ["imc", "imctrading"],
    "Hudson River Trading": ["hudsonrivertrading", "hrt"],
    "Susquehanna (SIG)": ["sig", "susquehanna"], "DRW": ["drw", "drwtrading"],
    "Jump Trading": ["jumptrading", "jump"], "Citadel": ["citadel"],
    "Citadel Securities": ["citadelsecurities"], "Point72": ["point72"],
    "Millennium": ["millennium", "mlp", "millenniummanagement"],
    "Jane Street": ["janestreet"], "Two Sigma": ["twosigma"],
    "Tower Research": ["towerresearch", "towerresearchcapital"],
    "XTX Markets": ["xtx", "xtxmarkets"], "G-Research": ["gresearch"],
    "Squarepoint": ["squarepoint", "squarepointcapital"],
    "Quadrature": ["quadrature", "quadraturecapital"],
    "Wintermute": ["wintermute"], "Flow Traders": ["flowtraders"],
    "Maven Securities": ["maven", "mavensecurities"], "Mako": ["mako", "makotrading"],
    "Akuna": ["akuna", "akunacapital"], "Virtu": ["virtu", "virtufinancial"],
    "DV Trading": ["dvtrading"], "CTC": ["ctc", "chicagotradingcompany"],
    "Five Rings": ["fiverings"], "Quantbot": ["quantbot"], "Qube RT": ["qube", "qubert"],
    "Marshall Wace": ["marshallwace"], "Brevan Howard": ["brevanhoward"],
    "Capula": ["capula"], "GSA Capital": ["gsa", "gsacapital"],
    "Da Vinci Trading": ["davinci", "davincitrading", "davincidt"],
    "Wincent": ["wincent"], "Xantium": ["xantium"], "iSAM": ["isam"],
    "Teza": ["teza", "tezatechnologies"], "Aspect Capital": ["aspectcapital"],
    "BMLL": ["bmll"], "Radix": ["radix", "radixtrading"], "Belvedere": ["belvederetrading"],
    "Old Mission": ["oldmission", "oldmissioncapital"], "Headlands": ["headlandstech"],
    "Aquatic": ["aquatic", "aquaticcapital"], "Schonfeld": ["schonfeld"],
    "ExodusPoint": ["exoduspoint"], "Verition": ["verition"], "Balyasny": ["balyasny", "bam"],
    "Man Group": ["mangroup", "man"], "Winton": ["winton"], "Qube": ["quberesearch"],
    "Cubist": ["cubist"], "Walleye": ["walleyecapital", "walleye"],
    "Castleton Commodities": ["cci", "castletoncommodities"],
    "Vitol": ["vitol"], "Trafigura": ["trafigura"], "Gunvor": ["gunvor"],
    # buy-side / PE
    "Blackstone": ["blackstone"], "KKR": ["kkr"], "Apollo": ["apollo"],
    "Ares": ["ares", "aresmgmt"], "Carlyle": ["carlyle"], "TPG": ["tpg"],
    "Bain Capital": ["baincapital"], "General Atlantic": ["generalatlantic"],
    "CD&R": ["cdr", "claytondubilierrice"], "Warburg Pincus": ["warburgpincus"],
    "Permira": ["permira"], "Cinven": ["cinven"], "Advent": ["adventinternational"],
    "EQT": ["eqt", "eqtgroup"], "Hg": ["hgcapital", "hg"], "Bridgepoint": ["bridgepoint"],
    "Oak Hill": ["oakhilladvisors", "oha"], "Sixth Street": ["sixthstreet"],
    "StepStone": ["stepstone", "stepstonegroup"], "Hamilton Lane": ["hamiltonlane"],
    "GIC": ["gic"], "Temasek": ["temasek"], "Neuberger Berman": ["neubergerberman"],
    "Soros": ["sorosfundmanagement", "soros"], "Elliott": ["elliottmanagement"],
    "D.E. Shaw": ["deshaw"], "AQR": ["aqr"], "Bridgewater": ["bridgewater"],
    "Rokos": ["rokos", "rokoscapital"], "Caxton": ["caxton"], "LMR": ["lmrpartners"],
    "Arrowstreet": ["arrowstreetcapital"], "PDT Partners": ["pdtpartners"],
    # boutiques / advisory
    "Evercore": ["evercore"], "Centerview": ["centerview", "centerviewpartners"],
    "PJT Partners": ["pjt", "pjtpartners"], "Moelis": ["moelis"], "Lazard": ["lazard"],
    "Perella Weinberg": ["pwp", "perellaweinberg"], "Qatalyst": ["qatalyst"],
    "LionTree": ["liontree"], "Guggenheim": ["guggenheim", "guggenheimpartners"],
    "Houlihan Lokey": ["houlihanlokey"], "William Blair": ["williamblair"],
    "Rothschild": ["rothschildandco", "rothschild"], "Greenhill": ["greenhill"],
    "Raine": ["raine", "rainegroup"], "Ardea": ["ardeapartners"],
    "Fenchurch": ["fenchurchadvisory"], "DC Advisory": ["dcadvisory"],
    "Eastdil": ["eastdilsecured", "eastdil"], "Jefferies": ["jefferies"],
    "Piper Sandler": ["pipersandler"], "Baird": ["baird", "rwbaird"],
    "Lincoln International": ["lincolninternational"], "Alantra": ["alantra"],
    "Peel Hunt": ["peelhunt"], "Panmure Liberum": ["panmureliberum"],
    "Rede Partners": ["redepartners"], "Campbell Lutyens": ["campbelllutyens"],
    "Gleacher Shacklock": ["gleachershacklock"], "Stifel": ["stifel"],
    "Harris Williams": ["harriswilliams"], "Leerink": ["leerinkpartners"],
    "Berenberg": ["berenberg"], "Numis": ["numis"], "Cavendish": ["cavendish"],
    "Zeus Capital": ["zeuscapital"], "Investec": ["investec"],
    "BTIG": ["btig"], "TD Securities": ["tdsecurities"], "Macquarie": ["macquarie"],
    "Nomura": ["nomura"], "Mizuho": ["mizuho"], "SMBC": ["smbc", "smbcgroup"],
    "BTG Pactual": ["btgpactual"], "Natixis": ["natixis"], "Santander": ["santander"],
    "Deutsche Bank": ["db", "deutschebank"], "Wells Fargo": ["wellsfargo"],
    "Standard Chartered": ["standardchartered", "sc"],
    # consulting / other
    "L.E.K.": ["lek", "lekconsulting"], "OC&C": ["occstrategy", "occ"],
    "Oliver Wyman": ["oliverwyman"], "Bain & Company": ["bain", "bainandcompany"],
    "BCG": ["bcg"], "McKinsey": ["mckinsey"], "Kearney": ["kearney"],
    "Roland Berger": ["rolandberger"], "Simon-Kucher": ["simonkucher"],
    "Alvarez & Marsal": ["alvarezandmarsal"], "FTI": ["fticonsulting"],
    "Teneo": ["teneo"], "AlixPartners": ["alixpartners"], "Analysis Group": ["analysisgroup"],
    "Cornerstone Research": ["cornerstoneresearch"], "NERA": ["nera"],
    "Compass Lexecon": ["compasslexecon"], "Charles River Associates": ["crai", "charlesriverassociates"],
    "Frontier Economics": ["frontiereconomics"], "Oxera": ["oxera"], "Baringa": ["baringa"],
    "ZS": ["zs", "zsassociates"], "Newton": ["newtoneurope", "newton"],
    "Alpha FMC": ["alphafmc"], "Capco": ["capco"], "Accenture": ["accenture"],
    # fintech / misc
    "Revolut": ["revolut"], "Wise": ["wise", "transferwise"], "Monzo": ["monzo"],
    "Checkout.com": ["checkout", "checkoutcom"], "Stripe": ["stripe"],
    "Coinbase": ["coinbase"], "Blockchain.com": ["blockchain"], "Copper": ["copper"],
    "Lendable": ["lendable"], "Bloomberg": ["bloomberg"], "AlphaSights": ["alphasights"],
    "GLG": ["glg"], "Third Bridge": ["thirdbridge"], "Guidepoint": ["guidepoint"],
    "S&P Global": ["spglobal"], "Moody's": ["moodys"], "LSEG": ["lseg"],
    "Tradeweb": ["tradeweb"], "MarketAxess": ["marketaxess"], "ICE": ["ice", "theice"],
    "Cboe": ["cboe"], "Nasdaq": ["nasdaq"], "FactSet": ["factset"], "Preqin": ["preqin"],
    "PitchBook": ["pitchbook"], "Addepar": ["addepar"], "Kraken": ["kraken"],
    "Galaxy": ["galaxy", "galaxydigital"], "Ripple": ["ripple"], "Circle": ["circle"],
    "Anthropic": ["anthropic"], "Palantir": ["palantir"], "Databricks": ["databricks"],
}


def probe_greenhouse(slug):
    r = S.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false", timeout=20)
    if r.status_code != 200:
        return None
    return r.json().get("jobs") or []


def probe_lever(slug):
    r = S.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    return data if isinstance(data, list) else None


def summarise(jobs, platform):
    intern_titles = []
    for j in jobs:
        title = j.get("title") if platform == "greenhouse" else j.get("text")
        loc = (j.get("location") or {}).get("name", "") if platform == "greenhouse" \
            else (j.get("categories") or {}).get("location", "")
        if filters.is_excluded(title):
            continue
        cat = filters.classify_role(title)
        if cat:
            intern_titles.append((title, loc, filters.classify_region(loc)))
    return intern_titles



def run(candidates, out_path=None):
    hits = {}
    for name, slugs in candidates.items():
        for slug in slugs:
            for platform, fn in (("greenhouse", probe_greenhouse), ("lever", probe_lever)):
                try:
                    jobs = fn(slug)
                except requests.RequestException:
                    jobs = None
                if jobs is None:
                    continue
                interns = summarise(jobs, platform)
                in_region = [t for t in interns if t[2]]
                hits[name] = {"platform": platform, "slug": slug, "total": len(jobs),
                              "interns": len(interns), "in_region": len(in_region),
                              "samples": in_region[:3] or interns[:2]}
                print(f"HIT  {name:<26} {platform:<10} {slug:<24} jobs={len(jobs):<4} "
                      f"interns={len(interns):<3} in-region={len(in_region)}", flush=True)
                break
            if name in hits:
                break
            time.sleep(0.3)

    print("\n=== DONE:", len(hits), "hits of", len(CANDIDATES), "candidates ===")
    if out_path:
        json.dump(hits, open(out_path, "w"), indent=2, default=str)
    return hits



if __name__ == "__main__":
    run(CANDIDATES, sys.argv[1] if len(sys.argv) > 1 else None)
