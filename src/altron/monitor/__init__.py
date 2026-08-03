"""Altron website monitor.

Detect changes on a webpage (price drop, sale, launch, new listing,
keyword appearance) and notify the user through Telegram or email.

The package uses only the standard library plus the deps Altron already
requires (pydantic, pyyaml). No third-party HTTP client, HTML parser,
or DIFF library.
"""

from altron.monitor.models import Alert, DiffConfig, Monitor, NotifyConfig
from altron.monitor.runner import MonitorOutcome, run_monitor

__all__ = [
    "Alert",
    "DiffConfig",
    "Monitor",
    "MonitorOutcome",
    "NotifyConfig",
    "run_monitor",
]
