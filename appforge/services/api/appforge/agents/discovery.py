"""Agent 1 - Discovery (blueprint section 2)."""

from __future__ import annotations

from sqlalchemy import select

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, AppStatus, Niche, ViralApp
from appforge.services.providers import EXCLUDED_DEVELOPERS, NICHE_CATEGORIES, PlayStoreProvider
from appforge.services.scoring import calculate_clone_potential, trend_score


class DiscoveryAgent(BaseAgent):
    agent_type = "discovery"

    def run(self, task: AgentTask) -> AgentResult:
        if task.task_type == "scan_all_niches":
            return self._scan_all()
        if task.task_type == "scan_niche":
            slug = (task.input_data or {}).get("niche")
            return self._scan_niche(slug)
        raise ValueError(f"Unknown discovery task: {task.task_type}")

    # ------------------------------------------------------------------
    def _scan_all(self) -> AgentResult:
        totals = {"scanned": 0, "created": 0, "updated": 0, "queued": 0, "excluded": 0}
        for slug in NICHE_CATEGORIES:
            result = self._scan_niche(slug)
            for key in totals:
                totals[key] += result.output.get(key, 0)
        return AgentResult(
            success=True,
            output=totals,
            message=f"Scanned {len(NICHE_CATEGORIES)} niches: {totals['created']} new, "
                    f"{totals['queued']} queued for analysis",
        )

    def _scan_niche(self, slug: str | None) -> AgentResult:
        if not slug:
            raise ValueError("scan_niche requires a 'niche' slug")

        niche = self.session.scalar(select(Niche).where(Niche.slug == slug))
        if niche is None:
            niche = Niche(name=slug.replace("_", " ").title(), slug=slug, category=slug)
            self.session.add(niche)
            self.session.flush()

        provider = PlayStoreProvider(self.settings)
        raw_apps = provider.top_apps(slug, self.settings.discovery_top_n_per_niche)

        stats = {"scanned": 0, "created": 0, "updated": 0, "queued": 0, "excluded": 0}

        for raw in raw_apps:
            stats["scanned"] += 1

            # Blueprint 2.6 data-quality rule: skip big-tech publishers.
            if (raw.get("developer") or "").strip().lower() in EXCLUDED_DEVELOPERS:
                stats["excluded"] += 1
                continue

            scoring = calculate_clone_potential(raw, niche_saturation=niche.saturation)
            score = scoring["score"]

            app = self.session.scalar(
                select(ViralApp).where(ViralApp.package_name == raw["package_name"])
            )
            created = app is None
            if app is None:
                app = ViralApp(package_name=raw["package_name"])
                self.session.add(app)

            app.niche_id = niche.id
            app.name = raw["name"]
            app.developer = raw.get("developer")
            app.icon = raw.get("icon")
            app.rating = raw.get("rating")
            app.total_downloads = raw.get("total_downloads")
            app.last_month_downloads = raw.get("last_month_downloads")
            app.this_month_downloads = raw.get("this_month_downloads")
            app.last_month_revenue = raw.get("last_month_revenue")
            app.total_reviews = raw.get("total_reviews")
            app.rating_distribution = raw.get("rating_distribution")
            app.category = slug
            app.description = raw.get("description")
            app.problem_solved = raw.get("problem_solved")
            app.key_features = raw.get("key_features")
            app.monetization_model = raw.get("monetization_model")
            app.price = raw.get("price")
            app.rank = raw.get("rank")
            app.trend_score = trend_score(raw)
            app.clone_potential_score = score
            app.clone_score_breakdown = scoring

            if created:
                stats["created"] += 1
                app.status = AppStatus.DISCOVERED.value
            else:
                stats["updated"] += 1

            self.session.flush()

            # Blueprint 2.6: score > threshold auto-queues the Analysis Agent.
            if score > self.settings.clone_score_threshold and app.status in {
                AppStatus.DISCOVERED.value,
                AppStatus.PENDING_ANALYSIS.value,
            }:
                already = self.session.scalar(
                    select(AgentTask).where(
                        AgentTask.app_id == app.id,
                        AgentTask.agent_type == "analysis",
                        AgentTask.status.in_(["pending", "running"]),
                    )
                )
                if already is None:
                    app.status = AppStatus.PENDING_ANALYSIS.value
                    self.queue_task(
                        "analysis",
                        "analyze_app",
                        app_id=app.id,
                        priority=score,
                        input_data={"app_id": app.id},
                    )
                    stats["queued"] += 1

        niche.app_count = self.session.scalar(
            select(ViralApp).where(ViralApp.niche_id == niche.id).with_only_columns(ViralApp.id)
        ) and len(raw_apps) or len(raw_apps)

        return AgentResult(
            success=True,
            output=stats,
            message=f"{slug}: scanned {stats['scanned']}, queued {stats['queued']}",
        )
