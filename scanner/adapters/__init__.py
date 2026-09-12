"""Adapter registry.

Each adapter turns one platform's API into the same normalised posting dict, so
`scan.py` never needs to know which platform a firm is on.
"""

from .bofa import BofaAdapter
from .greenhouse import GreenhouseAdapter
from .hsbc import HsbcAdapter
from .lever import LeverAdapter
from .morganstanley import MorganStanleyAdapter
from .oracle import OracleAdapter
from .radancy import RadancyAdapter
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
}


def build(firm, session=None, delay=1.0):
    """Return an adapter instance for a firm config, or None if unsupported."""
    adapter_cls = ADAPTERS.get(firm.get("platform"))
    if adapter_cls is None:
        return None
    return adapter_cls(firm, session=session, delay=delay)


__all__ = ["ADAPTERS", "build", "WorkdayAdapter", "GreenhouseAdapter", "LeverAdapter"]
