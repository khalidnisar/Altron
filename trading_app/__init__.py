"""ALTRON AutoTrade — standalone automated trading application.

Implements the ADVANCED AUTOMATED TRADING APP blueprint:
  * Risk Management Engine (hard stops, Kelly/fixed-fractional sizing,
    drawdown tiers, equity preservation, correlation checks)
  * AI Trading Engine (technical confluence, lightweight ML ensemble,
    sentiment, microstructure, regime-adaptive strategies)
  * MT5 Integration Layer (demo-gated MetaTrader 5 adapter + simulated broker)
  * Execution Engine (multi-level TP, breakeven, trailing, time stops)
  * Monitoring & Alerts + real-time web dashboard

Safety posture: paper/simulated by default. The MetaTrader 5 adapter refuses
to connect to any account that is not positively identified as DEMO.
"""

__version__ = "0.1.0"
