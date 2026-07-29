"""Clone Potential Score - direct implementation of blueprint section 2.4."""

from __future__ import annotations

import re
from typing import Any

COMPLEXITY_POINTS = {"low": 15, "medium": 10, "high": 5, "very_high": 0}


# Multi-word phrases are matched as substrings; single tokens are matched on
# word boundaries. Matching "ai" as a substring wrongly flagged "Email",
# "Detailed", and "Available" as high complexity, corrupting the feasibility
# score and the recommended MVP scope.
_VERY_HIGH_PHRASES = ["real-time streaming", "augmented reality", "3d render",
                      "video call", "live streaming", "face tracking"]
_VERY_HIGH_TOKENS = {"ar", "vr", "blockchain", "metaverse"}

_HIGH_PHRASES = ["machine learning", "real time", "on-device model"]
_HIGH_TOKENS = {"ai", "ml", "video", "live", "encryption", "wearable",
                "recommendation", "streaming", "transcription"}

_MEDIUM_PHRASES = ["push notification", "in-app purchase"]
_MEDIUM_TOKENS = {"sync", "cloud", "social", "payment", "payments", "map",
                  "maps", "chat", "notification", "notifications", "backup",
                  "collaboration", "offline"}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def estimate_complexity(features: list[str] | None) -> str:
    """Heuristic complexity estimate driven by feature keywords."""
    if not features:
        return "low"
    text = " ".join(features).lower()
    tokens = _tokens(text)

    if any(p in text for p in _VERY_HIGH_PHRASES) or (tokens & _VERY_HIGH_TOKENS):
        return "very_high"
    if any(p in text for p in _HIGH_PHRASES) or (tokens & _HIGH_TOKENS):
        return "high"
    if any(p in text for p in _MEDIUM_PHRASES) or (tokens & _MEDIUM_TOKENS):
        return "medium"
    return "low"


def calculate_clone_potential(app: dict[str, Any], niche_saturation: float = 0.5) -> dict[str, Any]:
    """Return the 0-100 score plus its component breakdown."""
    breakdown: dict[str, int] = {}

    # Revenue potential (0-25)
    revenue = app.get("last_month_revenue") or 0
    if revenue > 1_000_000:
        breakdown["revenue_potential"] = 25
    elif revenue > 500_000:
        breakdown["revenue_potential"] = 20
    elif revenue > 100_000:
        breakdown["revenue_potential"] = 15
    elif revenue > 50_000:
        breakdown["revenue_potential"] = 10
    elif revenue > 10_000:
        breakdown["revenue_potential"] = 5
    else:
        breakdown["revenue_potential"] = 0

    # Growth velocity (0-20)
    last = app.get("last_month_downloads") or 0
    this = app.get("this_month_downloads") or 0
    growth = ((this - last) / last) if last else 0.0
    if growth > 0.5:
        breakdown["growth_velocity"] = 20
    elif growth > 0.25:
        breakdown["growth_velocity"] = 15
    elif growth > 0.1:
        breakdown["growth_velocity"] = 10
    elif growth > 0:
        breakdown["growth_velocity"] = 5
    else:
        breakdown["growth_velocity"] = 0

    # Improvement opportunity (0-25)
    total_reviews = app.get("total_reviews") or 0
    negative = app.get("one_to_three_star_reviews") or 0
    ratio = (negative / total_reviews) if total_reviews else 0.0
    if ratio > 0.3:
        breakdown["improvement_opportunity"] = 25
    elif ratio > 0.2:
        breakdown["improvement_opportunity"] = 20
    elif ratio > 0.15:
        breakdown["improvement_opportunity"] = 15
    elif ratio > 0.1:
        breakdown["improvement_opportunity"] = 10
    else:
        breakdown["improvement_opportunity"] = 0

    # Market competition (0-15)
    if niche_saturation < 0.3:
        breakdown["market_competition"] = 15
    elif niche_saturation < 0.5:
        breakdown["market_competition"] = 10
    elif niche_saturation < 0.7:
        breakdown["market_competition"] = 5
    else:
        breakdown["market_competition"] = 0

    # Technical feasibility (0-15)
    complexity = estimate_complexity(app.get("key_features"))
    breakdown["technical_feasibility"] = COMPLEXITY_POINTS[complexity]

    return {
        "score": sum(breakdown.values()),
        "breakdown": breakdown,
        "complexity": complexity,
        "growth_rate": round(growth, 4),
        "negative_review_ratio": round(ratio, 4),
    }


def trend_score(app: dict[str, Any]) -> float:
    """Composite 0-100 trend indicator from growth and social signal."""
    last = app.get("last_month_downloads") or 0
    this = app.get("this_month_downloads") or 0
    growth = ((this - last) / last) if last else 0.0
    mentions = app.get("social_mentions_7d") or 0
    growth_component = max(0.0, min(1.0, (growth + 0.2) / 1.0)) * 60
    social_component = min(1.0, mentions / 40_000) * 40
    return round(growth_component + social_component, 1)
