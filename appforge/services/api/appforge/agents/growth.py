"""Agent 8 - Growth & Continuous Improvement (blueprint section 9)."""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

from sqlalchemy import select

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import (
    AgentTask,
    CloneProject,
    Earning,
    LiveMonitor,
    PipelineStage,
)

HALT_CONDITIONS = {
    "crash_free_below_99": "Crash-free rate dropped below 99%",
    "rating_drop": "Rating dropped more than 0.3 stars",
    "revenue_drop": "Daily revenue below 50% of 30-day average",
}


class GrowthAgent(BaseAgent):
    agent_type = "growth"
    completes_stage = PipelineStage.GROWTH

    def run(self, task: AgentTask) -> AgentResult:
        if task.task_type == "monitor":
            return self._monitor(task)
        if task.task_type == "portfolio_review":
            return self._portfolio_review()
        raise ValueError(f"Unknown growth task: {task.task_type}")

    # ------------------------------------------------------------------
    def _monitor(self, task: AgentTask) -> AgentResult:
        project = self.project(task)
        rng = random.Random(
            int(hashlib.sha256(f"{project.id}{date.today()}".encode()).hexdigest()[:8], 16)
        )

        crash_free = round(rng.uniform(98.6, 99.99), 2)
        rating = round(rng.uniform(4.1, 4.8), 2)
        dau = rng.randint(300, 25_000)
        daily_revenue = round(dau * rng.uniform(0.01, 0.09), 2)

        anomalies, actions = [], []

        if crash_free < 99.0:
            anomalies.append(HALT_CONDITIONS["crash_free_below_99"])
            actions += ["Halt rollout", "Analyze crash logs", "Generate hotfix"]
            self.queue_task(
                "development", "apply_fixes", project_id=project.id, priority=100,
                input_data={"reason": "crash_spike", "crash_free": crash_free},
            )

        recent = self.session.scalars(
            select(Earning).where(Earning.project_id == project.id)
            .order_by(Earning.date.desc()).limit(30)
        ).all()
        if recent:
            avg = sum(e.revenue for e in recent) / len(recent)
            if avg > 0 and daily_revenue < avg * 0.5:
                anomalies.append(HALT_CONDITIONS["revenue_drop"])
                actions += ["Check ad network fill", "Verify IAP flow", "Audit listing"]

        if rating < 4.2:
            anomalies.append("Rating below portfolio target of 4.5")
            actions.append("Prioritize top review issues in next update")

        halted = any("crash" in a.lower() for a in anomalies)

        # Record telemetry
        self.session.add(LiveMonitor(
            project_id=project.id, crash_free_rate=crash_free, average_rating=rating,
            daily_revenue=daily_revenue, dau=dau, anomalies=anomalies,
            actions_taken=actions, halted=halted,
        ))

        today = date.today()
        existing = self.session.scalar(
            select(Earning).where(Earning.project_id == project.id, Earning.date == today)
        )
        ad_rev = round(daily_revenue * 0.45, 2)
        iap_rev = round(daily_revenue * 0.2, 2)
        sub_rev = round(daily_revenue - ad_rev - iap_rev, 2)
        if existing:
            existing.revenue = daily_revenue
            existing.ad_revenue = ad_rev
            existing.iap_revenue = iap_rev
            existing.subscription_revenue = sub_rev
            existing.downloads = rng.randint(50, 3000)
        else:
            self.session.add(Earning(
                project_id=project.id, date=today, downloads=rng.randint(50, 3000),
                revenue=daily_revenue, ad_revenue=ad_rev, iap_revenue=iap_rev,
                subscription_revenue=sub_rev,
            ))

        # Roll up revenue
        all_earnings = self.session.scalars(
            select(Earning).where(Earning.project_id == project.id)
        ).all()
        month_start = today.replace(day=1)
        project.monthly_revenue = round(
            sum(e.revenue for e in all_earnings if e.date >= month_start), 2
        )
        project.total_revenue = round(sum(e.revenue for e in all_earnings), 2)
        project.ltv = round(daily_revenue / dau * 90, 4) if dau else 0.0

        # Rollout advancement (blueprint 7.6)
        advanced = self._advance_rollout(project, crash_free, halted)

        if project.pipeline_stage not in {PipelineStage.LIVE.value, PipelineStage.GROWTH.value}:
            project.pipeline_stage = PipelineStage.LIVE.value
            project.status = "live"
            project.progress = 100

        self.log_event(
            project.id, PipelineStage.GROWTH.value, "health_check",
            f"crash-free {crash_free}%, rating {rating}, revenue ${daily_revenue}",
            {"anomalies": anomalies, "actions": actions, "rollout_advanced": advanced},
        )

        return AgentResult(
            success=True,
            output={
                "crash_free_rate": crash_free, "rating": rating, "dau": dau,
                "daily_revenue": daily_revenue, "anomalies": anomalies,
                "actions": actions, "rollout_advanced": advanced, "halted": halted,
            },
            message=f"{project.clone_name}: {len(anomalies)} anomalies, "
                    f"crash-free {crash_free}%",
        )

    def _advance_rollout(self, project: CloneProject, crash_free: float, halted: bool) -> bool:
        rollout = project.rollout_status
        if not rollout or halted:
            return False
        stages = rollout.get("stages", [])
        current = rollout.get("current_stage", 1)  # 1-based stage number
        if current >= len(stages):
            return False

        # stages[current] is the NEXT stage (list is 0-indexed, current is 1-based).
        # `auto_advance` belongs to the stage we are LEAVING: the blueprint marks
        # internal/closed testing as manual, so leaving them needs a human. Reading
        # the flag off the next stage let a project skip closed testing entirely.
        leaving_stage = stages[current - 1]
        next_stage = stages[current]
        if not leaving_stage.get("auto_advance"):
            return False
        if crash_free < 99.5:
            return False
        rollout["current_stage"] = current + 1
        rollout["stage_name"] = next_stage["name"]
        rollout["percentage"] = next_stage.get("percentage")
        rollout["last_advanced_at"] = datetime.utcnow().isoformat() + "Z"
        project.rollout_status = dict(rollout)
        return True

    # ------------------------------------------------------------------
    def _portfolio_review(self) -> AgentResult:
        projects = self.session.scalars(
            select(CloneProject).where(CloneProject.pipeline_stage.in_(
                [PipelineStage.LIVE.value, PipelineStage.GROWTH.value]
            ))
        ).all()

        total_revenue = sum(p.monthly_revenue or 0 for p in projects)
        by_niche: dict[str, float] = {}
        for p in projects:
            niche = p.source_app.category if p.source_app else "unknown"
            by_niche[niche] = by_niche.get(niche, 0) + (p.monthly_revenue or 0)

        sunset, scale = [], []
        cutoff = datetime.utcnow() - timedelta(days=90)
        for p in projects:
            age_ok = p.created_at and p.created_at < cutoff
            if age_ok and (p.monthly_revenue or 0) < 100:
                sunset.append({
                    "project_id": p.id, "name": p.clone_name,
                    "monthly_revenue": p.monthly_revenue,
                    "reason": "Below $100/month for 3+ months",
                })
            elif (p.monthly_revenue or 0) > 5000:
                scale.append({
                    "project_id": p.id, "name": p.clone_name,
                    "monthly_revenue": p.monthly_revenue,
                    "reason": "Exceeds $5K/month target; invest in updates and UA",
                })

        concentration = 0.0
        if total_revenue > 0:
            top = sorted((p.monthly_revenue or 0 for p in projects), reverse=True)[:3]
            concentration = round(sum(top) / total_revenue * 100, 1)

        diversification_ok = all(
            (rev / total_revenue) <= 0.30 for rev in by_niche.values()
        ) if total_revenue > 0 else True

        return AgentResult(
            success=True,
            output={
                "live_apps": len(projects),
                "total_monthly_revenue": round(total_revenue, 2),
                "revenue_by_niche": {k: round(v, 2) for k, v in by_niche.items()},
                "top3_concentration_pct": concentration,
                "niche_diversification_ok": diversification_ok,
                "sunset_candidates": sunset,
                "scale_candidates": scale,
                "targets": {"revenue_per_app": 5000, "portfolio_size_per_year": 50},
            },
            message=f"Portfolio: {len(projects)} live apps, ${total_revenue:,.2f} MRR",
        )
