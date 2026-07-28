"""Agent 2 - Analysis (blueprint section 3)."""

from __future__ import annotations

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import (
    AgentTask,
    AppAnalysis,
    AppStatus,
    CloneProject,
    PipelineStage,
    ViralApp,
)
from appforge.services.providers import LLMProvider, PlayStoreProvider
from appforge.services.review_mining import analyze_reviews
from appforge.services.scoring import estimate_complexity

INTEGRATION_CATALOG = {
    "video": {"service": "Cloud video processing", "options": ["AWS MediaConvert", "Mux", "Cloudflare Stream"]},
    "ai": {"service": "AI models", "options": ["Replicate", "RunPod", "Self-hosted"]},
    "music": {"service": "Music licensing", "options": ["Epidemic Sound API", "Artlist API"]},
    "payment": {"service": "Payments", "options": ["RevenueCat", "Stripe"]},
    "map": {"service": "Maps", "options": ["Mapbox", "Google Maps SDK"]},
    "sync": {"service": "Realtime sync", "options": ["Supabase Realtime", "Firebase"]},
}


class AnalysisAgent(BaseAgent):
    agent_type = "analysis"

    def run(self, task: AgentTask) -> AgentResult:
        if task.task_type != "analyze_app":
            raise ValueError(f"Unknown analysis task: {task.task_type}")

        app_id = (task.input_data or {}).get("app_id") or task.app_id
        app = self.session.get(ViralApp, app_id)
        if app is None:
            raise ValueError(f"ViralApp {app_id} not found")

        functional = self._functional_analysis(app)
        reviews = PlayStoreProvider(self.settings).fetch_reviews(
            app.package_name, self.settings.review_scrape_target
        )
        review_analysis = analyze_reviews(reviews, self.settings.review_scrape_target)
        competitive = self._competitive_analysis(app)
        technical = self._technical_assessment(app, review_analysis)

        recommendation, reason = self._decide(app, review_analysis, technical)

        must_fix = [i["issue"] for i in review_analysis["identified_issues"][:5]]
        must_add = [f["feature"] for f in review_analysis["feature_requests"][:3]]

        names = LLMProvider(self.settings).generate_json(
            f"Generate app names for a {app.category} app solving: {app.problem_solved}",
            purpose="app_names",
            niche=app.category or "app",
        )
        name_ideas = names if isinstance(names, list) else []

        analysis = AppAnalysis(
            app_id=app.id,
            functional_analysis=functional,
            review_analysis=review_analysis,
            competitive_analysis=competitive,
            technical_assessment=technical,
            recommendation=recommendation,
            recommendation_reason=reason,
            must_fix_issues=must_fix,
            must_add_features=must_add,
            clone_name_ideas=name_ideas,
            reviews_analyzed=review_analysis["total_reviews_analyzed"],
        )
        self.session.add(analysis)

        # Persist the mined signal back onto the app record.
        app.positive_reviews = review_analysis["what_users_love"]
        app.negative_reviews = [
            {"issue": i["issue"], "quote": i["user_quotes"][0] if i["user_quotes"] else "",
             "severity": i["severity"]}
            for i in review_analysis["identified_issues"]
        ]
        app.identified_issues = review_analysis["identified_issues"]
        app.improvement_suggestions = [i["suggested_fix"] for i in review_analysis["identified_issues"][:5]]
        app.status = AppStatus.ANALYZED.value
        self.session.flush()

        created_project = None
        if recommendation == "RECOMMEND":
            created_project = self._create_project(app, analysis, technical)

        return AgentResult(
            success=True,
            output={
                "app_id": app.id,
                "recommendation": recommendation,
                "reviews_analyzed": review_analysis["total_reviews_analyzed"],
                "issues_found": len(review_analysis["identified_issues"]),
                "project_id": created_project.id if created_project else None,
            },
            message=f"{app.name}: {recommendation} ({len(must_fix)} must-fix issues)",
        )

    # ------------------------------------------------------------------
    def _functional_analysis(self, app: ViralApp) -> dict:
        features = app.key_features or []
        return {
            "app_purpose": app.problem_solved or app.description,
            "core_value_prop": app.problem_solved or app.description,
            "primary_use_cases": features[:4],
            "user_journey": [
                {"step": 1, "action": "Open app", "screen": "Home"},
                {"step": 2, "action": "Start core action", "screen": "Main"},
                {"step": 3, "action": "Complete core action", "screen": "Detail"},
                {"step": 4, "action": "Save or share result", "screen": "Share"},
            ],
            "monetization": {
                "model": app.monetization_model,
                "free_features": features[:2],
                "premium_features": features[2:],
                "ad_placements": ["Feed interstitials", "Rewarded unlocks"]
                if app.monetization_model == "free_with_ads"
                else [],
            },
        }

    def _competitive_analysis(self, app: ViralApp) -> dict:
        from sqlalchemy import select

        peers = self.session.scalars(
            select(ViralApp)
            .where(ViralApp.niche_id == app.niche_id, ViralApp.id != app.id)
            .order_by(ViralApp.total_downloads.desc())
            .limit(5)
        ).all()

        competitors = [
            {
                "name": p.name,
                "downloads": p.total_downloads,
                "rating": p.rating,
                "monetization": p.monetization_model,
            }
            for p in peers
        ]

        all_features: set[str] = set(app.key_features or [])
        for p in peers:
            all_features.update(p.key_features or [])

        matrix = {}
        for feature in sorted(all_features):
            row = {"target": feature in (app.key_features or [])}
            for idx, p in enumerate(peers[:2]):
                row[f"comp_{chr(97 + idx)}"] = feature in (p.key_features or [])
            matrix[feature] = row

        gaps = [f for f, row in matrix.items() if not any(row.values())]
        return {
            "direct_competitors": competitors,
            "feature_matrix": matrix,
            "market_gaps": gaps or ["Privacy-first positioning is unoccupied in this niche"],
        }

    def _technical_assessment(self, app: ViralApp, review_analysis: dict) -> dict:
        features = app.key_features or []
        complexity = estimate_complexity(features)
        per_feature = {f: estimate_complexity([f]) for f in features}

        integrations = []
        text = " ".join(features).lower()
        for key, spec in INTEGRATION_CATALOG.items():
            if key in text:
                integrations.append(spec)

        blockers = []
        if complexity == "very_high":
            blockers.append("Feature set requires capabilities we cannot replicate reliably")
        if "music" in text:
            blockers.append("Music licensing costs may be prohibitive at scale")
        if "ai" in text:
            blockers.append("AI inference requires sustained compute budget")

        mvp = [f for f, c in per_feature.items() if c in {"low", "medium"}][:5]

        return {
            "estimated_complexity": complexity,
            "development_time_estimate": {
                "low": "3-5 weeks", "medium": "6-10 weeks",
                "high": "10-16 weeks", "very_high": "16+ weeks",
            }[complexity],
            "core_features_complexity": per_feature,
            "required_integrations": integrations,
            "potential_blockers": blockers,
            "recommended_mvp_scope": mvp or features[:3],
        }

    def _decide(self, app: ViralApp, review_analysis: dict, technical: dict) -> tuple[str, str]:
        """Blueprint 3.3 recommendation rules."""
        score = app.clone_potential_score or 0
        issues = review_analysis["identified_issues"]

        if technical["estimated_complexity"] == "very_high":
            return "SKIP", "Technical complexity is very high; feasibility points score zero."

        # Network-effect guard: social apps derive most value from an existing graph.
        if app.category in {"social_media", "dating", "communication"} and score < 80:
            return (
                "NEEDS_REVIEW",
                "Value depends heavily on network effects we cannot bootstrap; needs human judgement.",
            )

        if not issues:
            return "SKIP", "No corroborated user issues found, so there is no improvement thesis."

        if score >= self.settings.clone_score_threshold and len(issues) >= 2:
            return (
                "RECOMMEND",
                f"Clone score {score} with {len(issues)} corroborated issues and a "
                f"{technical['estimated_complexity']} complexity build.",
            )

        return "NEEDS_REVIEW", f"Clone score {score} sits near the threshold; human review requested."

    def _create_project(self, app: ViralApp, analysis: AppAnalysis, technical: dict) -> CloneProject:
        idea = (analysis.clone_name_ideas or [{}])[0]
        clone_name = idea.get("name", f"{app.name} Plus")
        slug = clone_name.lower().replace(" ", "")

        project = CloneProject(
            source_app_id=app.id,
            clone_name=clone_name,
            clone_package_name=f"ai.appforge.{slug}",
            tagline=idea.get("tagline", "Built around what users asked for"),
            description=app.problem_solved,
            status="awaiting_approval",
            pipeline_stage=PipelineStage.AWAITING_APPROVAL.value,
            progress=20,
            patched_issues=[
                {"original": i["issue"], "fix": i["suggested_fix"], "severity": i["severity"],
                 "type": i["type"], "status": "planned"}
                for i in (analysis.review_analysis or {}).get("identified_issues", [])[:5]
            ],
            new_features=analysis.must_add_features,
            tech_stack={
                "mobile": "flutter",
                "state": "riverpod",
                "backend": "supabase",
                "database": "postgresql",
                "analytics": "mixpanel",
                "crash_reporting": "sentry",
                "ads": "admob",
                "iap": "revenuecat",
                "push": "fcm",
                "ci_cd": "github_actions",
            },
        )
        self.session.add(project)
        self.session.flush()

        app.status = AppStatus.CLONING.value
        self.log_event(
            project.id,
            PipelineStage.ANALYSIS.value,
            "analysis_complete",
            f"Analysis recommends cloning {app.name}. Awaiting human approval.",
            {"clone_score": app.clone_potential_score, "must_fix": analysis.must_fix_issues},
        )
        return project
