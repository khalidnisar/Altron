"""MT5 Integration Layer (blueprint 1C): broker adapters."""
from .base import Broker, BrokerError, SafetyViolation
from .simulated import SimulatedBroker

__all__ = ["Broker", "BrokerError", "SafetyViolation", "SimulatedBroker", "create_broker"]


def create_broker(cfg):
    """Factory: 'mt5_demo' tries the MetaTrader 5 demo adapter, 'simulated'
    forces paper mode, 'auto' tries MT5 then degrades to simulated."""
    mode = cfg.broker_mode
    if mode in ("mt5_demo", "auto"):
        try:
            from .mt5_demo import MT5DemoBroker
            broker = MT5DemoBroker(cfg)
            broker.connect()
            return broker, "mt5_demo"
        except Exception as exc:  # noqa: BLE001 - fall back to paper mode
            if mode == "mt5_demo":
                raise
            import logging
            logging.getLogger("trading_app").warning(
                "MT5 demo adapter unavailable (%s) — running simulated broker", exc)
    return SimulatedBroker(cfg), "simulated"
