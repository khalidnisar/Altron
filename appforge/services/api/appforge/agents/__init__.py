"""The eight AppForge AI agents."""

from __future__ import annotations

from appforge.agents.analysis import AnalysisAgent
from appforge.agents.base import AgentResult, BaseAgent
from appforge.agents.design import DesignAgent
from appforge.agents.development import DevelopmentAgent
from appforge.agents.discovery import DiscoveryAgent
from appforge.agents.growth import GrowthAgent
from appforge.agents.monetization import MonetizationAgent
from appforge.agents.publishing import PublishingAgent
from appforge.agents.testing import TestingAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "discovery": DiscoveryAgent,
    "analysis": AnalysisAgent,
    "design": DesignAgent,
    "development": DevelopmentAgent,
    "testing": TestingAgent,
    "publishing": PublishingAgent,
    "monetization": MonetizationAgent,
    "growth": GrowthAgent,
}

__all__ = [
    "AGENT_REGISTRY",
    "AgentResult",
    "BaseAgent",
    "AnalysisAgent",
    "DesignAgent",
    "DevelopmentAgent",
    "DiscoveryAgent",
    "GrowthAgent",
    "MonetizationAgent",
    "PublishingAgent",
    "TestingAgent",
]
