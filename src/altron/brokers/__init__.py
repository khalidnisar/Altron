"""Optional broker connectivity backends.

Backends are read-only until their explicit execution gate is enabled. Altron never
connects to a broker merely because this package is imported.
"""

from altron.brokers.base import BrokerBackend, BrokerOrder, BrokerOrderResult, BrokerStatus
from altron.brokers.registry import BrokerRegistry

__all__ = [
    "BrokerBackend",
    "BrokerOrder",
    "BrokerOrderResult",
    "BrokerRegistry",
    "BrokerStatus",
]
