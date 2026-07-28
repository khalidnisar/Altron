"""Pipeline control, agent status, and revenue reporting."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from appforge.db import get_session
from appforge.models import (
    AgentTask,
    CloneProject,
    Earning,
    PipelineStage,
    ViralApp,
)
from appforge.orchestrator import Orchestrator
from appforge.routers.deps import require_operator
from appforge.schemas import EarningOut, TaskOut, TriggerRequest

router = APIRouter(tags=["operations"])


@router.get("/pipeline/status")
def pipeline_status(session: Session = Depends(get_session)):
    stage_counts = dict(
        session.execute(
            select(CloneProject.pipeline_stage, func.count(CloneProject.id))
            .group_by(CloneProject.pipeline_stage)
        ).all()
    )
    app_counts = dict(
        session.execute(
            select(ViralApp.status, func.count(ViralApp.id)).group_by(ViralApp.status)
        ).all()
    )
    task_counts = dict(
        session.execute(
            select(AgentTask.status, func.count(AgentTask.id)).group_by(AgentTask.status)
        ).all()
    )

    live = session.scalars(
        select(CloneProject).where(CloneProject.pipeline_stage == PipelineStage.LIVE.value)
    ).all()
    awaiting = session.scalar(
        select(func.count(CloneProject.id)).where(
            CloneProject.pipeline_stage == PipelineStage.AWAITING_APPROVAL.value
        )
    ) or 0
    simulation = session.scalar(
        select(func.count(CloneProject.id)).where(
            CloneProject.pipeline_stage == PipelineStage.SIMULATION.value
        )
    ) or 0

    total_apps = session.scalar(select(func.count(ViralApp.id))) or 0
    total_revenue = session.scalar(select(func.sum(CloneProject.total_revenue))) or 0.0
    monthly_revenue = session.scalar(select(func.sum(CloneProject.monthly_revenue))) or 0.0

    return {
        "apps_discovered": total_apps,
        "apps_by_status": app_counts,
        "projects_by_stage": stage_counts,
        "tasks_by_status": task_counts,
        "live_apps": len(live),
        "awaiting_approval": awaiting + simulation,
        "total_revenue": round(float(total_revenue), 2),
        "monthly_revenue": round(float(monthly_revenue), 2),
    }


@router.post("/pipeline/trigger", dependencies=[Depends(require_operator)])
def trigger_agent(body: TriggerRequest, session: Session = Depends(get_session)):
    from appforge.agents import AGENT_REGISTRY

    if body.agent not in AGENT_REGISTRY:
        raise HTTPException(400, f"Unknown agent '{body.agent}'")

    task = AgentTask(
        agent_type=body.agent, task_type=body.task_type, project_id=body.project_id,
        app_id=body.app_id, priority=body.priority, input_data=body.input_data,
    )
    session.add(task)
    session.flush()
    return {"queued": True, "task_id": task.id}


@router.post("/pipeline/run", dependencies=[Depends(require_operator)])
def run_pipeline(limit: int = 10, session: Session = Depends(get_session)):
    """Synchronously drain up to ``limit`` queued tasks.

    Useful for demos and for deployments that do not run the worker container.
    """
    results = Orchestrator(session).run_once(limit=limit)
    return {"executed": len(results), "results": results}


@router.get("/agents/status")
def agents_status(session: Session = Depends(get_session)):
    from appforge.agents import AGENT_REGISTRY

    rows = session.execute(
        select(AgentTask.agent_type, AgentTask.status, func.count(AgentTask.id))
        .group_by(AgentTask.agent_type, AgentTask.status)
    ).all()

    summary: dict[str, dict] = {
        name: {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for name in AGENT_REGISTRY
    }
    for agent, status, count in rows:
        summary.setdefault(agent, {"pending": 0, "running": 0, "completed": 0, "failed": 0})
        summary[agent][status] = count

    return {
        "agents": [
            {"agent": name, "healthy": counts["failed"] == 0, **counts}
            for name, counts in summary.items()
        ]
    }


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    session: Session = Depends(get_session),
    status: str | None = None,
    agent: str | None = None,
    limit: int = 50,
):
    stmt = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    if agent:
        stmt = stmt.where(AgentTask.agent_type == agent)
    return session.scalars(stmt).all()


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------


@router.get("/revenue")
def revenue_summary(session: Session = Depends(get_session), days: int = 30):
    since = date.today() - timedelta(days=days)

    daily = session.execute(
        select(
            Earning.date,
            func.sum(Earning.revenue),
            func.sum(Earning.ad_revenue),
            func.sum(Earning.iap_revenue),
            func.sum(Earning.subscription_revenue),
            func.sum(Earning.downloads),
        )
        .where(Earning.date >= since)
        .group_by(Earning.date)
        .order_by(Earning.date)
    ).all()

    per_app = session.execute(
        select(
            CloneProject.id, CloneProject.clone_name,
            CloneProject.monthly_revenue, CloneProject.total_revenue,
        )
        .where(CloneProject.total_revenue > 0)
        .order_by(CloneProject.monthly_revenue.desc())
    ).all()

    totals = session.execute(
        select(
            func.sum(Earning.revenue), func.sum(Earning.ad_revenue),
            func.sum(Earning.iap_revenue), func.sum(Earning.subscription_revenue),
        ).where(Earning.date >= since)
    ).one()

    return {
        "window_days": days,
        "totals": {
            "revenue": round(float(totals[0] or 0), 2),
            "ad_revenue": round(float(totals[1] or 0), 2),
            "iap_revenue": round(float(totals[2] or 0), 2),
            "subscription_revenue": round(float(totals[3] or 0), 2),
        },
        "daily": [
            {
                "date": str(d), "revenue": round(float(r or 0), 2),
                "ad_revenue": round(float(ad or 0), 2),
                "iap_revenue": round(float(iap or 0), 2),
                "subscription_revenue": round(float(sub or 0), 2),
                "downloads": int(dl or 0),
            }
            for d, r, ad, iap, sub, dl in daily
        ],
        "per_app": [
            {"project_id": pid, "name": name,
             "monthly_revenue": round(float(m or 0), 2),
             "total_revenue": round(float(t or 0), 2)}
            for pid, name, m, t in per_app
        ],
    }


@router.get("/revenue/export")
def export_revenue(session: Session = Depends(get_session)):
    rows = session.execute(
        select(
            Earning.date, CloneProject.clone_name, Earning.downloads, Earning.revenue,
            Earning.ad_revenue, Earning.iap_revenue, Earning.subscription_revenue,
        )
        .join(CloneProject, CloneProject.id == Earning.project_id)
        .order_by(Earning.date.desc())
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "app", "downloads", "revenue", "ad_revenue",
                     "iap_revenue", "subscription_revenue"])
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=appforge-revenue.csv"},
    )


@router.get("/revenue/{project_id}", response_model=list[EarningOut])
def project_revenue(project_id: int, session: Session = Depends(get_session)):
    return session.scalars(
        select(Earning).where(Earning.project_id == project_id).order_by(Earning.date)
    ).all()
