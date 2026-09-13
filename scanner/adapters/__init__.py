"""Adapter registry.

Each adapter turns one platform's API into the same normalised posting dict, so
`scan.py` never needs to know which platform a firm is on.
"""

from .avature import AvatureAdapter
from .bain import BainAdapter
from .bofa import BofaAdapter
from .goldman import GoldmanAdapter
from .gradconnection import GradConnectionAdapter
from .greenhouse import GreenhouseAdapter
from .hsbc import HsbcAdapter
from .kpmg import KpmgAdapter
from .lever import LeverAdapter
from .morganstanley import MorganStanleyAdapter
from .oracle import OracleAdapter
from .phenom import PhenomAdapter
from .radancy import RadancyAdapter
from .smallats import AshbyAdapter, SmartRecruitersAdapter, WorkableAdapter
from .successfactors import SuccessFactorsAdapter
from .taleo import TaleoAdapter
from .workday import WorkdayAdapter

ADAPTERS = {
    "workday": WorkdayAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "oracle": OracleAdapter,
    "hsbc": HsbcAdapter,
    "morganstanley": MorganStanleyAdapter,
    "radancy": RadancyAdapter,
    "bofa": BofaAdapter,
    "goldman": GoldmanAdapter,
    "taleo": TaleoAdapter,
    "phenom": PhenomAdapter,
    "bain": BainAdapter,
    "kpmg": KpmgAdapter,
    "successfactors": SuccessFactorsAdapter,
    "avature": AvatureAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "ashby": AshbyAdapter,
    "workable": WorkableAdapter,
    "gradconnection": GradConnectionAdapter,
}


def build(firm, session=None, delay=1.0):
    """Return an adapter instance for a firm config, or None if unsupported."""
    adapter_cls = ADAPTERS.get(firm.get("platform"))
    if adapter_cls is None:
        return None
    return adapter_cls(firm, session=session, delay=delay)


__all__ = ["ADAPTERS", "build", "WorkdayAdapter", "GreenhouseAdapter", "LeverAdapter"]
