"""Niches and viral app discovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from appforge.db import get_session
from appforge.models import (
    AgentTask,
    AppAnalysis,
    AppStatus,
    CloneProject,
    Niche,
    PipelineStage,
    ViralApp,
)
from appforge.routers.deps import require_operator
from appforge.schemas import (
    CloneRequest,
    NicheOut,
    PaginatedApps,
    ProjectOut,
    ViralAppDetail,
)

router = APIRouter(tags=["discovery"])


@router.get("/niches", response_model=list[NicheOut])
def list_niches(session: Session = Depends(get_session)):
    return session.scalars(select(Niche).order_by(Niche.name)).all()


@router.get("/niches/{slug}", response_model=NicheOut)
def get_niche(slug: str, session: Session = Depends(get_session)):
    niche = session.scalar(select(Niche).where(Niche.slug == slug))
    if niche is None:
        raise HTTPException(404, "Niche not found")
    return niche


@router.get("/apps", response_model=PaginatedApps)
def list_apps(
    session: Session = Depends(get_session),
    niche: str | None = None,
    status: str | None = None,
    min_revenue: int | None = None,
    min_downloads: int | None = None,
    min_clone_score: int | None = None,
    search: str | None = None,
    sort_by: str = Query("clone_score", pattern="^(revenue|downloads|trend_score|clone_score|rating)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    stmt = select(ViralApp)
    count_stmt = select(func.count(ViralApp.id))

    filters = []
    if niche:
        sub = select(Niche.id).where(Niche.slug == niche).scalar_subquery()
        filters.append(ViralApp.niche_id == sub)
    if status:
        filters.append(ViralApp.status == status)
    if min_revenue is not None:
        filters.append(ViralApp.last_month_revenue >= min_revenue)
    if min_downloads is not None:
        filters.append(ViralApp.total_downloads >= min_downloads)
    if min_clone_score is not None:
        filters.append(ViralApp.clone_potential_score >= min_clone_score)
    if search:
        filters.append(ViralApp.name.ilike(f"%{search}%"))

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    column = {
        "revenue": ViralApp.last_month_revenue,
        "downloads": ViralApp.total_downloads,
        "trend_score": ViralApp.trend_score,
        "clone_score": ViralApp.clone_potential_score,
        "rating": ViralApp.rating,
    }[sort_by]
    stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())

    total = session.scalar(count_stmt) or 0
    items = session.scalars(stmt.offset((page - 1) * limit).limit(limit)).all()
    return PaginatedApps(items=items, total=total, page=page, limit=limit)


@router.get("/apps/{app_id}", response_model=ViralAppDetail)
def get_app(app_id: int, session: Session = Depends(get_session)):
    app = session.get(ViralApp, app_id)
    if app is None:
        raise HTTPException(404, "App not found")

    analysis = session.scalar(
        select(AppAnalysis).where(AppAnalysis.app_id == app_id)
        .order_by(AppAnalysis.created_at.desc()).limit(1)
    )
    payload = ViralAppDetail.model_validate(app)
    if analysis:
        payload.analysis = {
            "functional_analysis": analysis.functional_analysis,
            "review_analysis": analysis.review_analysis,
            "competitive_analysis": analysis.competitive_analysis,
            "technical_assessment": analysis.technical_assessment,
            "recommendation": analysis.recommendation,
            "recommendation_reason": analysis.recommendation_reason,
            "must_fix_issues": analysis.must_fix_issues,
            "must_add_features": analysis.must_add_features,
            "clone_name_ideas": analysis.clone_name_ideas,
            "reviews_analyzed": analysis.reviews_analyzed,
        }
    return payload


@router.post("/apps/{app_id}/analyze", dependencies=[Depends(require_operator)])
def trigger_analysis(app_id: int, session: Session = Depends(get_session)):
    app = session.get(ViralApp, app_id)
    if app is None:
        raise HTTPException(404, "App not found")

    task = AgentTask(
        agent_type="analysis", task_type="analyze_app", app_id=app.id,
        priority=app.clone_potential_score or 50, input_data={"app_id": app.id},
    )
    session.add(task)
    app.status = AppStatus.PENDING_ANALYSIS.value
    session.flush()
    return {"queued": True, "task_id": task.id}


@router.post("/apps/{app_id}/clone", response_model=ProjectOut,
             dependencies=[Depends(require_operator)])
def start_clone(app_id: int, body: CloneRequest, session: Session = Depends(get_session)):
    app = session.get(ViralApp, app_id)
    if app is None:
        raise HTTPException(404, "App not found")

    existing = session.scalar(select(CloneProject).where(CloneProject.source_app_id == app_id))
    if existing:
        raise HTTPException(409, f"Project {existing.id} already clones this app")

    name = body.clone_name or f"{app.name} Plus"
    project = CloneProject(
        source_app_id=app.id,
        clone_name=name,
        clone_package_name=f"ai.appforge.{name.lower().replace(' ', '')}",
        tagline="Built around what users asked for",
        description=app.problem_solved,
        status="awaiting_approval",
        pipeline_stage=PipelineStage.AWAITING_APPROVAL.value,
        progress=20,
        patched_issues=[
            {"original": i.get("issue"), "fix": i.get("suggested_fix"),
             "severity": i.get("severity", "medium"), "type": i.get("type", "ux"),
             "status": "planned"}
            for i in (app.identified_issues or [])[:5]
        ],
        tech_stack={"mobile": "flutter", "state": "riverpod", "backend": "supabase"},
    )
    session.add(project)
    app.status = AppStatus.CLONING.value
    session.flush()
    return project
