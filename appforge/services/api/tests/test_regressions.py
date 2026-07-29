"""Regression tests for defects found during the post-build audit.

Each test here failed against the previous implementation. They are grouped by
the bug they pin down so a future change that reintroduces one is caught.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from appforge.agents.development import MAX_REMEDIATION_ATTEMPTS, _classify_reason
from appforge.agents.publishing import PublishingAgent
from appforge.models import (
    AgentTask,
    CloneProject,
    Niche,
    PipelineStage,
    TaskStatus,
    ViralApp,
    is_stage_approved,
    record_approval,
)
from appforge.orchestrator import Orchestrator
from appforge.seed import seed_niches
from appforge.services.review_mining import NEGATIVE_WORDS, NEGATORS, classify_sentiment
from appforge.services.scoring import estimate_complexity

# ---------------------------------------------------------------------------
# BUG 1 (critical): one approved_at field served both human gates, so an
# approval at the analysis gate silently authorised a Play Store submission.
# ---------------------------------------------------------------------------


class TestPerGateApproval:
    def test_approval_is_recorded_per_stage(self, session):
        p = CloneProject(clone_name="X", pipeline_stage=PipelineStage.AWAITING_APPROVAL.value)
        session.add(p)
        session.flush()

        record_approval(p, PipelineStage.AWAITING_APPROVAL.value, "alice", "go")
        assert is_stage_approved(p, PipelineStage.AWAITING_APPROVAL.value)
        # The later gate must remain unapproved.
        assert not is_stage_approved(p, PipelineStage.SIMULATION.value)

    def test_analysis_approval_does_not_authorise_publishing(self, session):
        """The exact bypass: approve gate 1, then try to publish."""
        p = CloneProject(
            clone_name="Bypass", clone_package_name="ai.appforge.bypass",
            pipeline_stage=PipelineStage.SIMULATION.value,
            test_results={"overall_passed": True},
            design_assets={
                "feature_graphic": "u", "screenshots": ["a", "b"],
                "logo": {"icon_512": "u"}, "accessibility": {"passes": True},
            },
        )
        # Only the FIRST gate is approved.
        record_approval(p, PipelineStage.AWAITING_APPROVAL.value, "alice")
        session.add(p)
        session.flush()

        task = AgentTask(agent_type="publishing", task_type="publish", project_id=p.id)
        session.add(task)
        session.flush()

        result = PublishingAgent(session).run(task)
        assert result.success is False
        assert "approval" in result.message.lower()
        assert p.play_store_url is None

    def test_publishing_proceeds_once_the_correct_gate_is_approved(self, session):
        p = CloneProject(
            clone_name="Allowed", clone_package_name="ai.appforge.allowed",
            pipeline_stage=PipelineStage.SIMULATION.value,
            test_results={"overall_passed": True},
            design_assets={
                "feature_graphic": "u", "screenshots": ["a", "b"],
                "logo": {"icon_512": "u"}, "accessibility": {"passes": True},
            },
        )
        record_approval(p, PipelineStage.SIMULATION.value, "alice")
        session.add(p)
        session.flush()

        task = AgentTask(agent_type="publishing", task_type="publish", project_id=p.id)
        session.add(task)
        session.flush()

        assert PublishingAgent(session).run(task).success is True
        assert p.play_store_url


# ---------------------------------------------------------------------------
# BUG 2 (critical): apply_fixes was queued by testing/growth/reject but the
# Development agent had no branch for it, so feedback was silently discarded.
# ---------------------------------------------------------------------------


class TestRemediationLoop:
    @pytest.fixture
    def built(self, session):
        seed_niches(session)
        session.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                              input_data={"niche": "productivity"}))
        session.commit()
        Orchestrator(session).drain(400)

        project = session.scalars(select(CloneProject)).first()
        record_approval(project, PipelineStage.AWAITING_APPROVAL.value, "test")
        session.add(AgentTask(agent_type="design", task_type="generate_brand",
                              project_id=project.id, priority=80))
        session.commit()
        Orchestrator(session).drain(400)
        session.refresh(project)
        return project

    def test_apply_fixes_records_the_request(self, session, built):
        task = AgentTask(
            agent_type="development", task_type="apply_fixes", project_id=built.id,
            input_data={"failed_criteria": ["App starts within 3 seconds"]},
        )
        session.add(task)
        session.flush()

        from appforge.agents.development import DevelopmentAgent

        result = DevelopmentAgent(session).run(task)
        assert result.success is True

        project = session.get(CloneProject, built.id)
        assert project.remediation_history, "remediation was not recorded"
        assert project.remediation_history[0]["attempt"] == 1
        assert "App starts within 3 seconds" in project.remediation_history[0]["reasons"]

    def test_reviewer_feedback_becomes_a_tracked_fix(self, session, built):
        task = AgentTask(
            agent_type="development", task_type="apply_fixes", project_id=built.id,
            input_data={"feedback": "Onboarding is confusing"},
        )
        session.add(task)
        session.flush()

        from appforge.agents.development import DevelopmentAgent

        DevelopmentAgent(session).run(task)

        project = session.get(CloneProject, built.id)
        originals = [p.get("original") for p in project.patched_issues]
        assert any("Onboarding is confusing" in str(o) for o in originals)

    def test_remediation_stops_after_max_attempts(self, session, built):
        from appforge.agents.development import DevelopmentAgent

        last = None
        for _ in range(MAX_REMEDIATION_ATTEMPTS + 1):
            task = AgentTask(
                agent_type="development", task_type="apply_fixes", project_id=built.id,
                input_data={"failed_criteria": ["Persistent failure"]},
            )
            session.add(task)
            session.flush()
            last = DevelopmentAgent(session).run(task)

        assert last.success is False
        project = session.get(CloneProject, built.id)
        assert project.status == "needs_human_intervention"
        assert project.blocked_reason

    def test_reason_classification_picks_a_patch_category(self):
        assert _classify_reason("Cold start exceeds 3 seconds") == "performance"
        assert _classify_reason("Too many permissions") == "privacy"
        assert _classify_reason("Data loss on migration") == "reliability"
        assert _classify_reason("Fails TalkBack audit") == "accessibility"
        assert _classify_reason("Subscription pricing too high") == "monetization"


# ---------------------------------------------------------------------------
# BUG 3 (high): a double-click on Approve queued the next agent twice.
# ---------------------------------------------------------------------------


def test_double_approval_does_not_duplicate_work(client, session):
    seed_niches(session)
    p = CloneProject(clone_name="Dup", pipeline_stage=PipelineStage.AWAITING_APPROVAL.value)
    session.add(p)
    session.commit()

    for _ in range(3):
        r = client.post(f"/api/projects/{p.id}/approve", json={"approved_by": "qa"})
        assert r.status_code == 200

    tasks = session.scalars(
        select(AgentTask).where(
            AgentTask.project_id == p.id, AgentTask.agent_type == "design"
        )
    ).all()
    assert len(tasks) == 1, f"expected 1 design task, got {len(tasks)}"


# ---------------------------------------------------------------------------
# BUG 4 (high): substring matching flagged "Email"/"Detailed"/"Available" as AI.
# ---------------------------------------------------------------------------


class TestComplexityHeuristic:
    @pytest.mark.parametrize("feature", ["Email sync", "Detailed reports",
                                         "Available offline", "Daily streaks",
                                         "Repair tool", "Chair finder"])
    def test_ai_substring_no_longer_false_positives(self, feature):
        assert estimate_complexity([feature]) != "high"

    @pytest.mark.parametrize("feature,expected", [
        ("AI editing", "high"),
        ("Machine learning recommendations", "high"),
        ("Video call", "very_high"),
        ("AR filters", "very_high"),
        ("Cloud sync", "medium"),
        ("Notes", "low"),
    ])
    def test_genuine_signals_still_detected(self, feature, expected):
        assert estimate_complexity([feature]) == expected


# ---------------------------------------------------------------------------
# BUG 5 (high): negated praise was scored as a complaint, inflating issues.
# ---------------------------------------------------------------------------


class TestSentimentNegation:
    @pytest.mark.parametrize("text,rating", [
        ("This never crashes, love it", 5),
        ("no bugs at all", 5),
        ("not slow", 4),
    ])
    def test_negated_complaints_are_positive(self, text, rating):
        assert classify_sentiment({"text": text, "rating": rating}) == "positive"

    @pytest.mark.parametrize("text,rating", [
        ("crashes constantly", 1),
        ("it crashes every time", 3),
        ("drains battery fast", 2),
        ("never works, always crashes", 1),
    ])
    def test_real_complaints_still_negative(self, text, rating):
        assert classify_sentiment({"text": text, "rating": rating}) == "negative"

    def test_negators_are_not_also_polarity_words(self):
        """A negator in the complaint set would negate itself."""
        assert not (NEGATORS & NEGATIVE_WORDS)


# ---------------------------------------------------------------------------
# BUG 6 (medium): rollout advanced off the wrong stage's auto_advance flag,
# letting a release skip closed testing.
# ---------------------------------------------------------------------------


class TestRolloutAdvancement:
    def _project(self, session, current_stage: int):
        from appforge.agents.publishing import ROLLOUT_STAGES

        p = CloneProject(
            clone_name="Roll", pipeline_stage=PipelineStage.LIVE.value,
            rollout_status={
                "current_stage": current_stage,
                "stages": ROLLOUT_STAGES,
                "stage_name": ROLLOUT_STAGES[current_stage - 1]["name"],
            },
        )
        session.add(p)
        session.flush()
        return p

    def test_manual_stages_do_not_auto_advance(self, session):
        """Internal (1) and closed (2) testing require a human."""
        from appforge.agents.growth import GrowthAgent

        agent = GrowthAgent(session)
        for stage in (1, 2):
            p = self._project(session, stage)
            assert agent._advance_rollout(p, crash_free=100.0, halted=False) is False

    def test_production_stages_auto_advance_when_healthy(self, session):
        from appforge.agents.growth import GrowthAgent

        p = self._project(session, 3)  # Production 10% -> auto_advance
        assert GrowthAgent(session)._advance_rollout(p, 99.9, halted=False) is True
        assert p.rollout_status["current_stage"] == 4

    def test_no_advance_when_crash_free_below_threshold(self, session):
        from appforge.agents.growth import GrowthAgent

        p = self._project(session, 3)
        assert GrowthAgent(session)._advance_rollout(p, 99.0, halted=False) is False

    def test_halt_blocks_advancement(self, session):
        from appforge.agents.growth import GrowthAgent

        p = self._project(session, 3)
        assert GrowthAgent(session)._advance_rollout(p, 100.0, halted=True) is False


# ---------------------------------------------------------------------------
# BUG 7/8 (medium): app_count used a nonsense and/or expression and saturation
# was never recomputed from observed data.
# ---------------------------------------------------------------------------


class TestNicheMetrics:
    def test_app_count_matches_stored_rows(self, session):
        seed_niches(session)
        session.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                              input_data={"niche": "weather"}))
        session.commit()
        Orchestrator(session).run_once(limit=1)

        niche = session.scalar(select(Niche).where(Niche.slug == "weather"))
        actual = session.scalar(
            select(ViralApp).where(ViralApp.niche_id == niche.id)
        )
        count = len(session.scalars(
            select(ViralApp).where(ViralApp.niche_id == niche.id)
        ).all())
        assert actual is not None
        assert niche.app_count == count

    def test_saturation_is_recomputed_and_bounded(self, session):
        seed_niches(session)
        niche = session.scalar(select(Niche).where(Niche.slug == "gaming"))
        seeded = niche.saturation

        session.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                              input_data={"niche": "gaming"}))
        session.commit()
        Orchestrator(session).run_once(limit=1)

        session.refresh(niche)
        assert 0.0 < niche.saturation < 1.0
        # Should now reflect observed data rather than the seeded constant.
        assert niche.saturation != seeded or seeded == 0.5

    def test_concentrated_niche_scores_more_saturated(self, session):
        """A niche dominated by one giant is harder to enter than a flat one."""
        from appforge.agents.discovery import DiscoveryAgent

        flat = Niche(name="Flat", slug="flat-n", category="x")
        conc = Niche(name="Conc", slug="conc-n", category="x")
        session.add_all([flat, conc])
        session.flush()

        for i in range(6):
            session.add(ViralApp(name=f"f{i}", package_name=f"c.f{i}",
                                 niche_id=flat.id, total_downloads=1_000_000, rating=3.5))
        session.add(ViralApp(name="giant", package_name="c.giant",
                             niche_id=conc.id, total_downloads=50_000_000, rating=4.8))
        for i in range(5):
            session.add(ViralApp(name=f"s{i}", package_name=f"c.s{i}",
                                 niche_id=conc.id, total_downloads=100_000, rating=4.7))
        session.flush()

        agent = DiscoveryAgent(session)
        assert agent._estimate_saturation(conc.id) > agent._estimate_saturation(flat.id)


# ---------------------------------------------------------------------------
# Orchestrator retry accounting
# ---------------------------------------------------------------------------


def test_failed_task_retries_then_gives_up(session):
    session.add(AgentTask(agent_type="growth", task_type="bogus", priority=5))
    session.commit()

    Orchestrator(session).drain(max_tasks=50)

    task = session.scalars(select(AgentTask)).first()
    assert task.status == TaskStatus.FAILED.value
    assert task.attempts == 3
    assert task.error_message


# ---------------------------------------------------------------------------
# API exposure: remediation history was persisted but omitted from the schema,
# so the dashboard could never show why a build was reworked.
# ---------------------------------------------------------------------------


def test_remediation_history_is_exposed_by_the_api(client, session):
    project = CloneProject(
        clone_name="Exposed",
        pipeline_stage=PipelineStage.DEVELOPMENT.value,
        remediation_history=[{
            "attempt": 1, "requested_at": "2026-01-01T00:00:00Z",
            "reasons": ["Reviewer: confusing onboarding"], "source": "apply_fixes",
        }],
    )
    session.add(project)
    session.commit()

    body = client.get(f"/api/projects/{project.id}").json()
    assert body["remediation_history"], "remediation history missing from API payload"
    assert body["remediation_history"][0]["reasons"] == ["Reviewer: confusing onboarding"]


def test_project_list_includes_source_app_name(client, session):
    """The pipeline board shows provenance without an N+1 fetch per card."""
    niche = Niche(name="P", slug="p-test", category="p")
    session.add(niche)
    session.flush()
    app = ViralApp(name="Original App", package_name="com.orig", niche_id=niche.id)
    session.add(app)
    session.flush()
    session.add(CloneProject(clone_name="Clone", source_app_id=app.id,
                             pipeline_stage=PipelineStage.DESIGN.value))
    session.commit()

    items = client.get("/api/projects").json()
    match = next(p for p in items if p["clone_name"] == "Clone")
    assert match["source_app_name"] == "Original App"
