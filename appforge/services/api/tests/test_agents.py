"""Agent behaviour and the end-to-end pipeline."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from appforge.models import (
    AgentTask,
    AppAnalysis,
    CloneProject,
    Niche,
    PipelineStage,
    TaskStatus,
    ViralApp,
    record_approval,
)
from appforge.orchestrator import Orchestrator
from appforge.seed import seed_niches


@pytest.fixture
def seeded(session):
    seed_niches(session)
    session.commit()
    return session


def _run_queue(session, limit=400):
    return Orchestrator(session).drain(max_tasks=limit)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_populates_apps_and_scores(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "productivity"}, priority=10))
    seeded.commit()
    Orchestrator(seeded).run_once(limit=1)

    apps = seeded.scalars(select(ViralApp)).all()
    assert apps, "discovery produced no apps"
    for app in apps:
        assert app.clone_potential_score is not None
        assert 0 <= app.clone_potential_score <= 100
        assert app.clone_score_breakdown["breakdown"]


def test_discovery_queues_analysis_only_above_threshold(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "finance"}, priority=10))
    seeded.commit()
    Orchestrator(seeded).run_once(limit=1)

    queued_app_ids = {
        t.app_id for t in seeded.scalars(
            select(AgentTask).where(AgentTask.agent_type == "analysis")
        ).all()
    }
    for app in seeded.scalars(select(ViralApp)).all():
        if app.id in queued_app_ids:
            assert app.clone_potential_score > 70
        else:
            assert app.clone_potential_score <= 70


def test_discovery_is_idempotent(seeded):
    for _ in range(2):
        seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                             input_data={"niche": "weather"}, priority=10))
        seeded.commit()
        Orchestrator(seeded).run_once(limit=1)

    packages = [a.package_name for a in seeded.scalars(select(ViralApp)).all()]
    assert len(packages) == len(set(packages)), "duplicate apps created on rescan"


def test_discovery_excludes_big_tech(seeded):
    from appforge.agents.discovery import DiscoveryAgent
    from appforge.services.providers import EXCLUDED_DEVELOPERS

    DiscoveryAgent(seeded)  # ensure the agent module imports cleanly
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "photography"}))
    seeded.commit()
    Orchestrator(seeded).run_once(limit=1)

    for app in seeded.scalars(select(ViralApp)).all():
        assert (app.developer or "").lower() not in EXCLUDED_DEVELOPERS


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def test_analysis_produces_full_report(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "productivity"}))
    seeded.commit()
    _run_queue(seeded)

    analyses = seeded.scalars(select(AppAnalysis)).all()
    assert analyses, "no analyses produced"
    a = analyses[0]
    assert a.functional_analysis and a.review_analysis
    assert a.competitive_analysis and a.technical_assessment
    assert a.recommendation in {"RECOMMEND", "NEEDS_REVIEW", "SKIP"}
    assert a.reviews_analyzed > 0


def test_analysis_skips_infeasible_apps(seeded):
    from appforge.agents.analysis import AnalysisAgent

    niche = seeded.scalar(select(Niche).where(Niche.slug == "social_media"))
    app = ViralApp(
        name="Impossible", package_name="com.x.impossible", niche_id=niche.id,
        category="entertainment", key_features=["Real-time streaming", "Video call"],
        clone_potential_score=95, total_reviews=1000, last_month_revenue=500_000,
    )
    seeded.add(app)
    seeded.flush()

    task = AgentTask(agent_type="analysis", task_type="analyze_app",
                     app_id=app.id, input_data={"app_id": app.id})
    seeded.add(task)
    seeded.flush()

    result = AnalysisAgent(seeded).run(task)
    assert result.output["recommendation"] == "SKIP"


def test_analysis_flags_network_effect_apps_for_review(seeded):
    from appforge.agents.analysis import AnalysisAgent

    niche = seeded.scalar(select(Niche).where(Niche.slug == "social_media"))
    app = ViralApp(
        name="Sociable", package_name="com.x.sociable", niche_id=niche.id,
        category="social_media", key_features=["Feed", "Profiles"],
        clone_potential_score=72, total_reviews=5000, last_month_revenue=200_000,
    )
    seeded.add(app)
    seeded.flush()
    task = AgentTask(agent_type="analysis", task_type="analyze_app",
                     app_id=app.id, input_data={"app_id": app.id})
    seeded.add(task)
    seeded.flush()

    result = AnalysisAgent(seeded).run(task)
    assert result.output["recommendation"] == "NEEDS_REVIEW"


def test_recommended_app_creates_project_awaiting_approval(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_all_niches"))
    seeded.commit()
    _run_queue(seeded)

    projects = seeded.scalars(select(CloneProject)).all()
    assert projects, "no clone projects created"
    assert all(p.pipeline_stage == PipelineStage.AWAITING_APPROVAL.value for p in projects)
    assert all(p.approved_at is None for p in projects)


# ---------------------------------------------------------------------------
# Human approval gate
# ---------------------------------------------------------------------------


def test_pipeline_halts_at_approval_gate(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "productivity"}))
    seeded.commit()
    _run_queue(seeded)

    # Draining the queue must never advance a project past the gate on its own.
    for p in seeded.scalars(select(CloneProject)).all():
        assert p.pipeline_stage == PipelineStage.AWAITING_APPROVAL.value

    pending = seeded.scalars(
        select(AgentTask).where(AgentTask.status == TaskStatus.PENDING.value)
    ).all()
    assert not pending, "queue should be drained with no design work queued"


# ---------------------------------------------------------------------------
# Full pipeline after approval
# ---------------------------------------------------------------------------


@pytest.fixture
def live_project(seeded):
    seeded.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                         input_data={"niche": "productivity"}))
    seeded.commit()
    _run_queue(seeded)

    project = seeded.scalars(select(CloneProject)).first()
    record_approval(project, PipelineStage.AWAITING_APPROVAL.value, "test")
    seeded.add(AgentTask(agent_type="design", task_type="generate_brand",
                         project_id=project.id, priority=80))
    seeded.commit()
    _run_queue(seeded)

    seeded.refresh(project)
    return project


def test_design_agent_produces_accessible_assets(live_project):
    assets = live_project.design_assets
    assert assets["palette"]["primary"].startswith("#")
    assert assets["logo"]["icon_512"]
    assert len(assets["screenshots"]) >= 2
    assert assets["accessibility"]["passes"] is True
    assert assets["accessibility"]["body_contrast_ratio"] >= 4.5
    assert set(assets["themes"]) == {"dark", "light"}


def test_development_agent_generates_repo_and_patches(live_project):
    assert live_project.repository_url
    assert live_project.patched_issues
    for patch in live_project.patched_issues:
        assert patch["status"] == "implemented"
        assert patch["file"]


def test_testing_agent_enforces_approval_criteria(live_project):
    results = live_project.test_results
    assert results["overall_passed"] is True
    assert results["coverage"] > 80
    assert results["performance"]["cold_start_seconds"] < 3.0
    assert results["performance"]["peak_memory_mb"] < 300
    assert results["performance"]["crash_free_rate"] == 100.0
    assert len(results["devices"]) >= 10
    for criterion in results["criteria"]["must_pass"]:
        assert criterion["passed"], criterion["criteria"]


def test_project_stops_at_simulation_for_human_review(live_project):
    assert live_project.pipeline_stage == PipelineStage.SIMULATION.value
    assert live_project.simulator_url


def test_publishing_requires_human_approval(seeded, live_project):
    """Publishing must refuse to run before the simulation gate is approved."""
    from appforge.agents.publishing import PublishingAgent

    # Clear every approval so the pre-publish gate is genuinely unmet.
    live_project.approvals = {}
    live_project.approved_at = None
    seeded.flush()

    task = AgentTask(agent_type="publishing", task_type="publish",
                     project_id=live_project.id)
    seeded.add(task)
    seeded.flush()

    result = PublishingAgent(seeded).run(task)
    assert result.success is False
    assert "approval" in result.message.lower()


def test_full_pipeline_reaches_live(seeded, live_project):
    record_approval(live_project, PipelineStage.SIMULATION.value, "test")
    seeded.add(AgentTask(agent_type="publishing", task_type="publish",
                         project_id=live_project.id, priority=80))
    seeded.commit()
    _run_queue(seeded)
    seeded.refresh(live_project)

    assert live_project.play_store_url
    assert live_project.store_listing["title"]
    assert len(live_project.store_listing["title"]) <= 30
    assert len(live_project.store_listing["short_description"]) <= 80
    assert len(live_project.store_listing["full_description"]) <= 4000
    assert live_project.monetization_config["model"] in {
        "subscription", "freemium", "free_with_ads"}
    assert live_project.pipeline_stage == PipelineStage.LIVE.value
    assert live_project.progress == 100


def test_rollout_starts_at_internal_track(seeded, live_project):
    record_approval(live_project, PipelineStage.SIMULATION.value, "test")
    seeded.add(AgentTask(agent_type="publishing", task_type="publish",
                         project_id=live_project.id))
    seeded.commit()
    Orchestrator(seeded).run_once(limit=1)
    seeded.refresh(live_project)

    rollout = live_project.rollout_status
    assert rollout["current_stage"] == 1
    assert rollout["stage_name"] == "Internal Testing"
    assert len(rollout["stages"]) == 6
    assert rollout["halt_conditions"]


def test_monetization_respects_regional_pricing(seeded, live_project):
    record_approval(live_project, PipelineStage.SIMULATION.value, "test")
    seeded.add(AgentTask(agent_type="publishing", task_type="publish",
                         project_id=live_project.id))
    seeded.commit()
    _run_queue(seeded)
    seeded.refresh(live_project)

    config = live_project.monetization_config
    regional = config["regional_prices"]
    assert regional["IN"] < regional["US"], "emerging markets need lower pricing"
    assert config["ads"]["networks"]
    assert 0 <= config["value_score"] <= 100
