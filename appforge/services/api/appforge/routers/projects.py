"""Clone project pipeline endpoints, including the human approval gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from appforge.db import get_session
from appforge.models import (
    HUMAN_GATES,
    STAGE_ORDER,
    AgentTask,
    CloneProject,
    PipelineEvent,
    PipelineStage,
    TaskStatus,
    is_stage_approved,
    record_approval,
)
from appforge.routers.deps import require_operator
from appforge.schemas import (
    ApprovalRequest,
    PipelineEventOut,
    ProjectDetail,
    ProjectOut,
    RejectionRequest,
)

router = APIRouter(prefix="/projects", tags=["pipeline"])

# Which agent picks the project up after each gate.
STAGE_NEXT_AGENT = {
    PipelineStage.AWAITING_APPROVAL.value: ("design", "generate_brand"),
    PipelineStage.DESIGN.value: ("development", "generate_code"),
    PipelineStage.DEVELOPMENT.value: ("testing", "run_test_suite"),
    PipelineStage.SIMULATION.value: ("publishing", "publish"),
    PipelineStage.PUBLISHING.value: ("monetization", "configure"),
    PipelineStage.MONETIZATION.value: ("growth", "monitor"),
}


@router.get("", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_session),
    status: str | None = None,
    stage: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|progress|revenue)$"),
):
    stmt = select(CloneProject)
    if status:
        stmt = stmt.where(CloneProject.status == status)
    if stage:
        stmt = stmt.where(CloneProject.pipeline_stage == stage)

    column = {
        "created_at": CloneProject.created_at,
        "progress": CloneProject.progress,
        "revenue": CloneProject.monthly_revenue,
    }[sort_by]

    # Eager-load the source app: the board renders provenance for every card,
    # which would otherwise be one lazy query per project.
    projects = session.scalars(
        stmt.options(joinedload(CloneProject.source_app)).order_by(column.desc())
    ).unique().all()

    out: list[ProjectOut] = []
    for p in projects:
        item = ProjectOut.model_validate(p)
        item.source_app_name = p.source_app.name if p.source_app else None
        out.append(item)
    return out


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(CloneProject, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/{project_id}/events", response_model=list[PipelineEventOut])
def project_events(project_id: int, session: Session = Depends(get_session)):
    return session.scalars(
        select(PipelineEvent)
        .where(PipelineEvent.project_id == project_id)
        .order_by(PipelineEvent.created_at.desc())
        .limit(100)
    ).all()


@router.post("/{project_id}/approve", response_model=ProjectDetail,
             dependencies=[Depends(require_operator)])
def approve(project_id: int, body: ApprovalRequest, session: Session = Depends(get_session)):
    """Human approval gate. Advances the project and queues the next agent."""
    project = session.get(CloneProject, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")

    stage = project.pipeline_stage
    if stage not in STAGE_NEXT_AGENT:
        raise HTTPException(409, f"Stage '{stage}' has no approval gate")

    agent, task_type = STAGE_NEXT_AGENT[stage]

    # Idempotency: a double-click (or a retried request) must not queue the same
    # agent twice and duplicate expensive generation work.
    existing = session.scalar(
        select(AgentTask).where(
            AgentTask.project_id == project.id,
            AgentTask.agent_type == agent,
            AgentTask.task_type == task_type,
            AgentTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
        )
    )
    if existing is not None:
        return project

    record_approval(project, stage, body.approved_by, body.feedback)
    project.status = f"{agent}_queued"
    project.blocked_reason = None

    session.add(AgentTask(
        agent_type=agent, task_type=task_type, project_id=project.id, priority=80,
        input_data={"approved_by": body.approved_by},
    ))
    session.add(PipelineEvent(
        project_id=project.id, stage=stage, event_type="approved",
        message=f"Approved by {body.approved_by}; queued {agent} agent",
        event_metadata={"feedback": body.feedback},
    ))
    session.flush()
    return project


@router.post("/{project_id}/reject", response_model=ProjectDetail,
             dependencies=[Depends(require_operator)])
def reject(project_id: int, body: RejectionRequest, session: Session = Depends(get_session)):
    project = session.get(CloneProject, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")

    project.status = "rejected"
    project.blocked_reason = body.feedback
    project.approval_feedback = body.feedback

    # Rejection at simulation means "needs changes" -> back to development.
    if project.pipeline_stage == PipelineStage.SIMULATION.value:
        project.pipeline_stage = PipelineStage.DEVELOPMENT.value
        project.status = "needs_fixes"
        session.add(AgentTask(
            agent_type="development", task_type="apply_fixes", project_id=project.id,
            priority=95, input_data={"feedback": body.feedback},
        ))
    else:
        project.pipeline_stage = PipelineStage.REJECTED.value

    session.add(PipelineEvent(
        project_id=project.id, stage=project.pipeline_stage, event_type="rejected",
        message=f"Rejected by {body.rejected_by}: {body.feedback}",
    ))
    session.flush()
    return project


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_operator)])
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(CloneProject, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    session.delete(project)


@router.get("/{project_id}/pipeline", tags=["pipeline"])
def project_pipeline(project_id: int, session: Session = Depends(get_session)):
    """Stage-by-stage view used by the dashboard progress rail."""
    project = session.get(CloneProject, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")

    try:
        current_index = STAGE_ORDER.index(PipelineStage(project.pipeline_stage))
    except ValueError:
        current_index = -1

    stages = []
    for i, stage in enumerate(STAGE_ORDER):
        state = "pending"
        if current_index >= 0:
            if i < current_index:
                state = "complete"
            elif i == current_index:
                state = "active"
        stages.append({"stage": stage.value, "state": state,
                       "has_gate": stage.value in HUMAN_GATES,
                       "approved": is_stage_approved(project, stage.value)})

    return {
        "project_id": project.id,
        "current_stage": project.pipeline_stage,
        "progress": project.progress,
        "awaiting_approval": project.pipeline_stage in HUMAN_GATES
        and not is_stage_approved(project, project.pipeline_stage),
        "approvals": project.approvals or {},
        "stages": stages,
    }
