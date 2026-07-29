"""Seed the database and optionally drive a full demo pipeline run."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from random import Random

from sqlalchemy import func, select

from appforge.db import init_db, session_scope
from appforge.models import (
    AgentTask,
    CloneProject,
    Earning,
    Niche,
    PipelineStage,
    ViralApp,
    record_approval,
)
from appforge.orchestrator import Orchestrator
from appforge.services.providers import NICHE_CATEGORIES

logger = logging.getLogger("appforge.seed")

NICHE_META = {
    "social_media": ("Social Media", "users", 0.85),
    "productivity": ("Productivity", "check-square", 0.55),
    "health_fitness": ("Health & Fitness", "heart", 0.6),
    "finance": ("Finance", "dollar-sign", 0.5),
    "education": ("Education", "book-open", 0.45),
    "entertainment": ("Entertainment", "film", 0.7),
    "shopping": ("Shopping", "shopping-bag", 0.65),
    "travel": ("Travel", "map", 0.4),
    "food_drink": ("Food & Drink", "coffee", 0.45),
    "communication": ("Communication", "message-circle", 0.8),
    "photography": ("Photography", "camera", 0.6),
    "music_audio": ("Music & Audio", "music", 0.65),
    "utilities": ("Utilities", "tool", 0.5),
    "gaming": ("Gaming", "gamepad-2", 0.9),
    "lifestyle": ("Lifestyle", "sun", 0.4),
    "business": ("Business", "briefcase", 0.35),
    "news_magazines": ("News & Magazines", "newspaper", 0.5),
    "weather": ("Weather", "cloud", 0.3),
    "parenting": ("Parenting", "baby", 0.25),
    "dating": ("Dating", "heart-handshake", 0.75),
}


def seed_niches(session) -> int:
    created = 0
    for slug in NICHE_CATEGORIES:
        existing = session.scalar(select(Niche).where(Niche.slug == slug))
        if existing:
            continue
        name, icon, saturation = NICHE_META.get(slug, (slug.title(), "box", 0.5))
        session.add(Niche(
            name=name, slug=slug, category=slug, icon=icon, saturation=saturation,
            description=f"Google Play {name} category monitored by the Discovery Agent.",
        ))
        created += 1
    session.flush()
    return created


def backfill_earnings(session, days: int = 30) -> int:
    """Give live projects a revenue history so the dashboard charts have data."""
    live = session.scalars(
        select(CloneProject).where(
            CloneProject.pipeline_stage.in_([PipelineStage.LIVE.value, PipelineStage.GROWTH.value])
        )
    ).all()

    rows = 0
    today = date.today()
    for project in live:
        rng = Random(project.id * 7919)
        base = rng.uniform(30, 320)
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            exists = session.scalar(
                select(Earning).where(Earning.project_id == project.id, Earning.date == day)
            )
            if exists:
                continue
            # Gentle growth curve plus daily noise.
            revenue = round(base * (1 + (days - offset) / days * 0.6) * rng.uniform(0.75, 1.3), 2)
            ad = round(revenue * 0.45, 2)
            iap = round(revenue * 0.2, 2)
            session.add(Earning(
                project_id=project.id, date=day,
                downloads=rng.randint(40, 1800), revenue=revenue,
                ad_revenue=ad, iap_revenue=iap,
                subscription_revenue=round(revenue - ad - iap, 2),
            ))
            rows += 1
        session.flush()

        totals = session.scalars(
            select(Earning).where(Earning.project_id == project.id)
        ).all()
        month_start = today.replace(day=1)
        project.monthly_revenue = round(sum(e.revenue for e in totals if e.date >= month_start), 2)
        project.total_revenue = round(sum(e.revenue for e in totals), 2)

    return rows


def seed(run_pipeline: bool = True, auto_approve: bool = True) -> dict:
    """Full seed: niches, discovery, analysis, and an approved demo project."""
    init_db()
    summary: dict = {}

    with session_scope() as session:
        summary["niches_created"] = seed_niches(session)

        # Kick off discovery for every niche.
        session.add(AgentTask(agent_type="discovery", task_type="scan_all_niches", priority=100))
        session.flush()

    if not run_pipeline:
        return summary

    with session_scope() as session:
        orchestrator = Orchestrator(session)
        executed = orchestrator.drain(max_tasks=400)
        summary["tasks_executed"] = len(executed)

    # Auto-approve pending projects so the demo reaches a live state.
    if auto_approve:
        with session_scope() as session:
            pending = session.scalars(
                select(CloneProject).where(
                    CloneProject.pipeline_stage == PipelineStage.AWAITING_APPROVAL.value
                ).limit(3)
            ).all()
            for project in pending:
                record_approval(project, PipelineStage.AWAITING_APPROVAL.value, "seed",
                                "Auto-approved by seed")
                project.status = "design_queued"
                session.add(AgentTask(
                    agent_type="design", task_type="generate_brand",
                    project_id=project.id, priority=80,
                ))
            summary["auto_approved"] = len(pending)

        # Design -> development -> testing
        with session_scope() as session:
            summary["tasks_executed"] = summary.get("tasks_executed", 0) + len(
                Orchestrator(session).drain(max_tasks=400)
            )

        # Approve at the simulation gate, then publish -> monetize -> grow.
        with session_scope() as session:
            ready = session.scalars(
                select(CloneProject).where(
                    CloneProject.pipeline_stage == PipelineStage.SIMULATION.value
                )
            ).all()
            for project in ready:
                record_approval(project, PipelineStage.SIMULATION.value, "seed",
                                "Auto-approved by seed")
                session.add(AgentTask(
                    agent_type="publishing", task_type="publish",
                    project_id=project.id, priority=80,
                ))
            summary["simulation_approved"] = len(ready)

        with session_scope() as session:
            summary["tasks_executed"] = summary.get("tasks_executed", 0) + len(
                Orchestrator(session).drain(max_tasks=400)
            )

        with session_scope() as session:
            summary["earnings_rows"] = backfill_earnings(session)

    with session_scope() as session:
        summary["apps_discovered"] = session.scalar(select(func.count(ViralApp.id))) or 0
        summary["projects"] = session.scalar(select(func.count(CloneProject.id))) or 0
        summary["live_projects"] = session.scalar(
            select(func.count(CloneProject.id)).where(
                CloneProject.pipeline_stage == PipelineStage.LIVE.value
            )
        ) or 0

    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = seed(run_pipeline=True)
    logger.info("Seed complete: %s", result)
    print(result)


if __name__ == "__main__":
    main()
