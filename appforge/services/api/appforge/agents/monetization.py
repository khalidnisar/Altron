"""Agent 7 - Monetization (blueprint section 8)."""

from __future__ import annotations

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, PipelineStage

REGIONAL_MULTIPLIERS = {
    "US": 1.0, "GB": 0.95, "DE": 0.90, "FR": 0.85, "JP": 1.05, "AU": 0.90,
    "CA": 0.90, "IN": 0.30, "BR": 0.40, "MX": 0.35, "RU": 0.35, "ID": 0.25,
}

AD_NETWORKS = [
    {"name": "AdMob", "priority": 1, "floor_cpm": 2.0},
    {"name": "Meta Audience Network", "priority": 2, "floor_cpm": 1.5},
    {"name": "Unity Ads", "priority": 3, "floor_cpm": 1.0},
    {"name": "AppLovin", "priority": 4, "floor_cpm": 0.8},
]

# Niches where users habitually pay a subscription.
SUBSCRIPTION_ACCEPTANCE = {
    "finance": 0.55, "health_fitness": 0.6, "education": 0.55, "productivity": 0.5,
    "business": 0.65, "photography": 0.45, "music_audio": 0.5, "dating": 0.5,
    "entertainment": 0.45, "news_magazines": 0.4, "parenting": 0.35,
    "utilities": 0.25, "gaming": 0.2, "weather": 0.2, "shopping": 0.15,
    "travel": 0.25, "food_drink": 0.25, "communication": 0.2,
    "lifestyle": 0.3, "social_media": 0.2,
}


class MonetizationAgent(BaseAgent):
    agent_type = "monetization"
    completes_stage = PipelineStage.MONETIZATION

    def run(self, task: AgentTask) -> AgentResult:
        project = self.project(task)
        source = project.source_app
        niche = source.category if source else "utilities"

        value_score = self._value_score(project, source)
        acceptance = SUBSCRIPTION_ACCEPTANCE.get(niche, 0.3)
        config = self._pricing(project, niche, value_score, acceptance)

        config["ads"] = self._ad_config(config["model"])
        config["value_score"] = value_score
        config["subscription_acceptance"] = acceptance

        project.monetization_config = config
        project.ai_recommended_price = config.get("headline_price", 0.0)
        project.pipeline_stage = PipelineStage.MONETIZATION.value
        project.status = "monetization_configured"
        project.progress = 95

        self.append_build_log(
            project, "monetization",
            f"Model={config['model']} price={config.get('headline_price')}", "success",
        )
        self.log_event(
            project.id, PipelineStage.MONETIZATION.value, "monetization_configured",
            f"Selected {config['model']} model",
            {"value_score": value_score, "price": config.get("headline_price")},
        )

        self.queue_task("growth", "monitor", project_id=project.id, priority=40)

        return AgentResult(
            success=True, output=config,
            message=f"{config['model']} configured at ${config.get('headline_price', 0)}",
        )

    # ------------------------------------------------------------------
    def _value_score(self, project, source) -> int:
        """0-100 composite of problem severity, uniqueness, and alternative cost."""
        score = 40

        issues = project.patched_issues or []
        critical = sum(1 for i in issues if i.get("severity") in {"critical", "high"})
        score += min(25, critical * 8)  # problem severity

        score += min(15, len(project.new_features or []) * 5)  # uniqueness

        if source:
            revenue = source.last_month_revenue or 0
            if revenue > 1_000_000:
                score += 20
            elif revenue > 250_000:
                score += 14
            elif revenue > 50_000:
                score += 8
            if (source.monetization_model or "") == "subscription":
                score += 5

        return max(0, min(100, score))

    def _pricing(self, project, niche: str, value_score: int, acceptance: float) -> dict:
        features = list((project.source_app.key_features if project.source_app else []) or [])
        features += [f for f in (project.new_features or []) if f not in features]

        if value_score > 80 and acceptance > 0.4:
            base = round(4.99 + (value_score - 80) * 0.25, 2)
            base = min(base, 14.99)
            return {
                "model": "subscription",
                "headline_price": base,
                "tiers": {
                    "free": {"price": 0.0,
                             "features": features[:2] + ["Ads shown", "Limited exports"]},
                    "premium": {"monthly": base, "yearly": round(base * 12 * 0.5, 2),
                                "trial_days": 7,
                                "features": features + ["No ads", "Unlimited use", "Priority support"]},
                    "pro": {"monthly": round(base * 2, 2), "yearly": round(base * 2 * 12 * 0.5, 2),
                            "features": ["Everything in Premium", "Commercial license",
                                         "Advanced analytics", "Early access"]},
                },
                "regional_prices": {r: round(base * m, 2) for r, m in REGIONAL_MULTIPLIERS.items()},
                "psychology": {"anchor_to_yearly": True, "show_savings_percentage": True,
                               "default_selected": "yearly", "trial_conversion_target": 0.25},
                "churn_tactics": ["Winback email day 3/7/14", "Discount offer on cancel",
                                  "Usage stats to demonstrate value"],
            }

        if value_score > 60:
            unlock = round(9.99 + (value_score - 60) * 0.25, 2)
            return {
                "model": "freemium",
                "headline_price": unlock,
                "free_tier": features[:3],
                "premium_features": features[3:] or ["Advanced tools"],
                "iap_catalog": {
                    "consumables": [
                        {"id": "credits_100", "price": 0.99, "description": "100 credits"},
                        {"id": "credits_500", "price": 3.99, "description": "500 credits + 50 bonus"},
                        {"id": "credits_1000", "price": 6.99, "description": "1000 credits + 200 bonus"},
                    ],
                    "non_consumables": [
                        {"id": "unlock_all", "price": unlock, "description": "Unlock everything"},
                        {"id": "remove_ads", "price": 4.99, "description": "Remove all ads forever"},
                    ],
                },
                "show_ads_in_free": True,
                "conversion_tactics": ["Prompt after 5th free-tier limit hit",
                                       "50% off first purchase", "Bundle discount"],
                "regional_prices": {r: round(unlock * m, 2) for r, m in REGIONAL_MULTIPLIERS.items()},
            }

        return {
            "model": "free_with_ads",
            "headline_price": 4.99,
            "optional_ad_removal_price": 4.99,
            "regional_prices": {r: round(4.99 * m, 2) for r, m in REGIONAL_MULTIPLIERS.items()},
        }

    def _ad_config(self, model: str) -> dict:
        placements = [
            {"type": "banner", "location": "bottom_of_screen",
             "screens": ["home", "browse"], "refresh_rate_seconds": 30},
            {"type": "interstitial", "trigger": "after_completing_core_action",
             "frequency_cap": "1 per 3 actions", "skip_for_premium": True},
            {"type": "rewarded_video", "reward": "unlock_premium_feature_for_1_use",
             "trigger": "user_initiated"},
            {"type": "native", "location": "in_feed", "frequency": "1 per 10 items"},
        ]
        if model == "subscription":
            placements = [p for p in placements if p["type"] in {"rewarded_video", "native"}]
        return {
            "networks": AD_NETWORKS,
            "mediation": "AdMob mediation with waterfall",
            "placements": placements,
            "optimization_rules": [
                "Disable interstitials for first 3 sessions (retention)",
                "Increase frequency for highly engaged users",
                "Reduce frequency for users showing churn signals",
                "A/B test placement variations weekly",
            ],
            "consent": {"gdpr": "UMP consent form", "ccpa": "Do Not Sell opt-out"},
        }
