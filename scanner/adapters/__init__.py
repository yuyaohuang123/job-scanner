"""Adapter registry.

Each adapter turns one platform's API into the same normalised posting dict, so
`scan.py` never needs to know which platform a firm is on.
"""

from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .oracle import OracleAdapter
from .workday import WorkdayAdapter

ADAPTERS = {
    "workday": WorkdayAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "oracle": OracleAdapter,
}


def build(firm, session=None, delay=1.0):
    """Return an adapter instance for a firm config, or None if unsupported."""
    adapter_cls = ADAPTERS.get(firm.get("platform"))
    if adapter_cls is None:
        return None
    return adapter_cls(firm, session=session, delay=delay)


__all__ = ["ADAPTERS", "build", "WorkdayAdapter", "GreenhouseAdapter", "LeverAdapter"]
