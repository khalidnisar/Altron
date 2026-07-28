"""REST API contract tests (blueprint section 12)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from appforge.db import SessionLocal
from appforge.models import AgentTask, CloneProject, ViralApp
from appforge.orchestrator import Orchestrator
from appforge.seed import seed_niches


@pytest.fixture
def populated(client):
    with SessionLocal() as s:
        seed_niches(s)
        s.add(AgentTask(agent_type="discovery", task_type="scan_niche",
                        input_data={"niche": "productivity"}))
        s.commit()
        Orchestrator(s).drain(max_tasks=200)
        s.commit()
    return client


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_schema_available(client):
    assert client.get("/openapi.json").status_code == 200


def test_list_niches(populated):
    r = populated.get("/api/niches")
    assert r.status_code == 200
    assert len(r.json()) == 20


def test_get_niche_by_slug(populated):
    r = populated.get("/api/niches/finance")
    assert r.status_code == 200
    assert r.json()["slug"] == "finance"


def test_unknown_niche_is_404(populated):
    assert populated.get("/api/niches/nope").status_code == 404


def test_list_apps_paginates(populated):
    r = populated.get("/api/apps?limit=3&page=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 3
    assert body["total"] >= len(body["items"])


def test_apps_filter_by_min_clone_score(populated):
    r = populated.get("/api/apps?min_clone_score=70&limit=50")
    assert all(a["clone_potential_score"] >= 70 for a in r.json()["items"])


def test_apps_sorted_by_revenue_desc(populated):
    items = populated.get("/api/apps?sort_by=revenue&sort_order=desc&limit=10").json()["items"]
    revenues = [a["last_month_revenue"] or 0 for a in items]
    assert revenues == sorted(revenues, reverse=True)


def test_app_detail_includes_analysis(populated):
    with SessionLocal() as s:
        app = s.scalars(
            select(ViralApp).where(ViralApp.status == "cloning")
        ).first() or s.scalars(select(ViralApp)).first()
        app_id = app.id

    body = populated.get(f"/api/apps/{app_id}").json()
    assert body["id"] == app_id
    assert "clone_score_breakdown" in body


def test_missing_app_is_404(populated):
    assert populated.get("/api/apps/999999").status_code == 404


def test_pipeline_status_shape(populated):
    body = populated.get("/api/pipeline/status").json()
    for key in ("apps_discovered", "projects_by_stage", "live_apps",
                "awaiting_approval", "total_revenue"):
        assert key in body


def test_agents_status_lists_eight_agents(populated):
    agents = populated.get("/api/agents/status").json()["agents"]
    assert len(agents) == 8
    names = {a["agent"] for a in agents}
    assert names == {"discovery", "analysis", "design", "development",
                     "testing", "publishing", "monetization", "growth"}


def test_projects_list_and_detail(populated):
    projects = populated.get("/api/projects").json()
    assert projects, "expected at least one project"
    pid = projects[0]["id"]
    detail = populated.get(f"/api/projects/{pid}").json()
    assert detail["id"] == pid
    assert "patched_issues" in detail


def test_project_pipeline_view(populated):
    pid = populated.get("/api/projects").json()[0]["id"]
    body = populated.get(f"/api/projects/{pid}/pipeline").json()
    assert body["awaiting_approval"] is True
    assert any(s["state"] == "active" for s in body["stages"])


def test_approve_advances_and_queues_next_agent(populated):
    pid = populated.get("/api/projects").json()[0]["id"]
    r = populated.post(f"/api/projects/{pid}/approve",
                       json={"approved_by": "qa", "feedback": "looks good"})
    assert r.status_code == 200
    assert r.json()["approved_at"]

    with SessionLocal() as s:
        task = s.scalars(
            select(AgentTask).where(AgentTask.project_id == pid,
                                    AgentTask.agent_type == "design")
        ).first()
        assert task is not None, "approval did not queue the design agent"


def test_reject_records_feedback(populated):
    pid = populated.get("/api/projects").json()[0]["id"]
    r = populated.post(f"/api/projects/{pid}/reject",
                       json={"rejected_by": "qa", "feedback": "wrong niche"})
    assert r.status_code == 200
    assert r.json()["status"] in {"rejected", "needs_fixes"}


def test_reject_requires_feedback(populated):
    pid = populated.get("/api/projects").json()[0]["id"]
    r = populated.post(f"/api/projects/{pid}/reject", json={"rejected_by": "qa"})
    assert r.status_code == 422


def test_trigger_rejects_unknown_agent(populated):
    r = populated.post("/api/pipeline/trigger",
                       json={"agent": "wizard", "task_type": "magic"})
    assert r.status_code == 400


def test_trigger_queues_valid_agent(populated):
    r = populated.post("/api/pipeline/trigger",
                       json={"agent": "discovery", "task_type": "scan_niche",
                             "input_data": {"niche": "weather"}})
    assert r.status_code == 200
    assert r.json()["queued"] is True


def test_clone_endpoint_prevents_duplicates(populated):
    with SessionLocal() as s:
        project = s.scalars(select(CloneProject)).first()
        source_id = project.source_app_id

    r = populated.post(f"/api/apps/{source_id}/clone", json={})
    assert r.status_code == 409


def test_revenue_endpoints(populated):
    body = populated.get("/api/revenue").json()
    assert "totals" in body and "daily" in body and "per_app" in body

    export = populated.get("/api/revenue/export")
    assert export.status_code == 200
    assert "date,app,downloads" in export.text


def test_operator_token_enforced(monkeypatch, populated):
    """When a token is configured, mutating endpoints must reject bad tokens."""
    from appforge.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APPFORGE_OPERATOR_TOKEN", "secret-token")

    pid = populated.get("/api/projects").json()[0]["id"]
    denied = populated.post(f"/api/projects/{pid}/approve", json={"approved_by": "x"})
    assert denied.status_code == 401

    allowed = populated.post(f"/api/projects/{pid}/approve", json={"approved_by": "x"},
                             headers={"X-Operator-Token": "secret-token"})
    assert allowed.status_code == 200

    get_settings.cache_clear()
    monkeypatch.delenv("APPFORGE_OPERATOR_TOKEN", raising=False)
