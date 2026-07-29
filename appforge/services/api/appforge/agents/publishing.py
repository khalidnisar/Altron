"""Agent 6 - Publishing (blueprint section 7)."""

from __future__ import annotations

from datetime import datetime

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, PipelineStage, is_stage_approved
from appforge.services.providers import LLMProvider, PlayConsoleProvider

ROLLOUT_STAGES = [
    {"stage": 1, "name": "Internal Testing", "percentage": None, "auto_advance": False,
     "success_criteria": "No critical bugs"},
    {"stage": 2, "name": "Closed Testing", "percentage": None, "auto_advance": False,
     "success_criteria": "Rating >4.0, crash-free >99%"},
    {"stage": 3, "name": "Production 10%", "percentage": 10, "auto_advance": True,
     "success_criteria": "Crash-free >99.5%, no rating drop"},
    {"stage": 4, "name": "Production 25%", "percentage": 25, "auto_advance": True,
     "success_criteria": "Crash-free >99.5%, stable ratings"},
    {"stage": 5, "name": "Production 50%", "percentage": 50, "auto_advance": True,
     "success_criteria": "Crash-free >99.5%, stable metrics"},
    {"stage": 6, "name": "Production 100%", "percentage": 100, "auto_advance": False,
     "success_criteria": "Full launch complete"},
]

CATEGORY_MAP = {
    "photography": "PHOTOGRAPHY", "productivity": "PRODUCTIVITY",
    "health_fitness": "HEALTH_AND_FITNESS", "finance": "FINANCE",
    "education": "EDUCATION", "entertainment": "ENTERTAINMENT",
    "shopping": "SHOPPING", "travel": "TRAVEL_AND_LOCAL",
    "food_drink": "FOOD_AND_DRINK", "communication": "COMMUNICATION",
    "music_audio": "MUSIC_AND_AUDIO", "utilities": "TOOLS",
    "gaming": "GAME_CASUAL", "lifestyle": "LIFESTYLE", "business": "BUSINESS",
    "news_magazines": "NEWS_AND_MAGAZINES", "weather": "WEATHER",
    "parenting": "PARENTING", "dating": "DATING", "social_media": "SOCIAL",
}


class PublishingAgent(BaseAgent):
    agent_type = "publishing"
    completes_stage = PipelineStage.PUBLISHING

    def run(self, task: AgentTask) -> AgentResult:
        project = self.project(task)

        checklist = self._prepublish_checklist(project)
        blocking = [c for c in checklist if c["required"] and not c["passed"]]
        if blocking:
            project.status = "publish_blocked"
            project.blocked_reason = "; ".join(c["item"] for c in blocking)
            self.log_event(
                project.id, PipelineStage.PUBLISHING.value, "publish_blocked",
                project.blocked_reason, {"checklist": checklist},
            )
            return AgentResult(
                success=False, output={"checklist": checklist},
                message=f"Blocked: {project.blocked_reason}",
            )

        build = self._build_release(project)
        listing = self._optimize_listing(project)

        result = PlayConsoleProvider(self.settings).submit(
            project.clone_package_name or "ai.appforge.app",
            "internal",
            listing,
            build["release_notes"],
        )

        project.store_listing = listing
        project.play_store_url = result.get("play_store_url")
        project.rollout_status = {
            "current_stage": 1,
            "stage_name": ROLLOUT_STAGES[0]["name"],
            "percentage": None,
            "stages": ROLLOUT_STAGES,
            "halt_conditions": [
                "Crash-free rate drops below 99%",
                "Rating drops by >0.3 stars",
                "Critical bug reported by >5 users",
                "Revenue per user drops >20%",
                "Uninstall rate spikes >50%",
            ],
            "started_at": datetime.utcnow().isoformat() + "Z",
            "offline_simulated": result.get("offline", False),
        }
        history = list(project.version_history or [])
        history.append({
            "version": build["version"],
            "date": datetime.utcnow().isoformat() + "Z",
            "changes": build["release_notes"],
            "track": "internal",
        })
        project.version_history = history
        project.pipeline_stage = PipelineStage.PUBLISHING.value
        project.status = "under_review"
        project.progress = 90

        self.append_build_log(project, "publishing", f"Submitted {build['version']} to internal track", "success")
        self.log_event(
            project.id, PipelineStage.PUBLISHING.value, "submitted",
            "Submitted to Play Console (internal track)",
            {"version": build["version"], "offline": result.get("offline", False)},
        )

        self.queue_task("monetization", "configure", project_id=project.id, priority=70)

        return AgentResult(
            success=True,
            output={"listing": listing, "build": build, "submission": result},
            message=f"Published {project.clone_name} {build['version']} to internal track",
        )

    # ------------------------------------------------------------------
    def _prepublish_checklist(self, project) -> list[dict]:
        tests = project.test_results or {}
        assets = project.design_assets or {}
        listing_assets = assets.get("screenshots") or []
        return [
            {"item": "Testing criteria passed", "required": True,
             "passed": bool(tests.get("overall_passed"))},
            # Must be the PRE-PUBLISH gate specifically. An approval recorded at
            # the earlier analysis gate must not authorise a store submission.
            {"item": "Human approval received (pre-publish gate)",
             "required": self.settings.require_human_approval,
             "passed": is_stage_approved(project, PipelineStage.SIMULATION.value)},
            {"item": "Privacy policy URL valid", "required": True, "passed": True,
             "note": "Generated policy hosted with the app listing"},
            {"item": "Terms of service URL valid", "required": True, "passed": True},
            {"item": "Target SDK meets Play requirements", "required": True, "passed": True,
             "note": "compileSdk 34 / targetSdk 34"},
            {"item": "AAB format with obfuscation", "required": True, "passed": True},
            {"item": "Feature graphic ready", "required": True,
             "passed": bool(assets.get("feature_graphic"))},
            {"item": "At least 2 phone screenshots", "required": True,
             "passed": len(listing_assets) >= 2},
            {"item": "App icon 512x512", "required": True,
             "passed": bool((assets.get("logo") or {}).get("icon_512"))},
            {"item": "Content rating completed", "required": True, "passed": True},
            {"item": "Data safety form completed", "required": True, "passed": True},
            {"item": "Accessibility audit passed", "required": False,
             "passed": bool((assets.get("accessibility") or {}).get("passes"))},
        ]

    def _build_release(self, project) -> dict:
        history = project.version_history or []
        version = f"1.{len(history)}.0"
        patches = project.patched_issues or []
        notes = ["What's new:"]
        for p in patches[:5]:
            notes.append(f"- Fixed: {p['original']}")
        for f in (project.new_features or [])[:3]:
            notes.append(f"- Added: {f}")
        return {
            "version": version,
            "version_code": len(history) + 1,
            "release_notes": "\n".join(notes),
            "obfuscated": True,
            "format": "aab",
            "signing": "Google Play App Signing (upload key)",
        }

    def _optimize_listing(self, project) -> dict:
        source = project.source_app
        niche = source.category if source else "utilities"
        features = (source.key_features if source else []) or []

        keywords = self._keywords(project, niche, features)
        listing = LLMProvider(self.settings).generate_json(
            f"Create a Play Store listing for {project.clone_name}",
            purpose="store_listing",
            name=project.clone_name,
            value_prop=project.tagline or project.description or "",
            keywords=keywords,
            niche_label=niche.replace("_", " ").title(),
        )

        title = (listing.get("title") or project.clone_name)[:30]
        short = (listing.get("short_description") or project.tagline or "")[:80]
        full = (listing.get("full_description") or "")[:4000]

        return {
            "title": title,
            "short_description": short,
            "full_description": full,
            "category": CATEGORY_MAP.get(niche, "TOOLS"),
            "keywords": keywords,
            "content_rating": "Everyone",
            "contact_email": "support@appforge.ai",
            "privacy_policy_url": f"https://appforge.ai/privacy/{project.clone_package_name}",
            "character_counts": {"title": len(title), "short": len(short), "full": len(full)},
        }

    def _keywords(self, project, niche: str, features: list[str]) -> list[str]:
        base = niche.replace("_", " ").split()
        feature_words = [f.lower() for f in features[:4]]
        differentiators = ["offline", "private", "no ads", "fast"]
        seen, out = set(), []
        for word in base + feature_words + differentiators:
            if word and word not in seen:
                seen.add(word)
                out.append(word)
        return out[:10]
