"""SQLAlchemy models implementing blueprint section 11 (Database Schema).

JSON columns use the portable ``JSON`` type so the same models run on
PostgreSQL (production) and SQLite (tests).
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Enumerations (kept as plain strings in the DB for forward compatibility)
# --------------------------------------------------------------------------


class AppStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    PENDING_ANALYSIS = "pending_analysis"
    ANALYZED = "analyzed"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLONING = "cloning"
    CLONED = "cloned"


class PipelineStage(str, enum.Enum):
    """Ordered pipeline stages from the blueprint architecture diagram."""

    DISCOVERY = "discovery"
    ANALYSIS = "analysis"
    AWAITING_APPROVAL = "awaiting_approval"
    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    SIMULATION = "simulation"
    PUBLISHING = "publishing"
    MONETIZATION = "monetization"
    GROWTH = "growth"
    LIVE = "live"
    REJECTED = "rejected"
    SUNSET = "sunset"


STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.DISCOVERY,
    PipelineStage.ANALYSIS,
    PipelineStage.AWAITING_APPROVAL,
    PipelineStage.DESIGN,
    PipelineStage.DEVELOPMENT,
    PipelineStage.TESTING,
    PipelineStage.SIMULATION,
    PipelineStage.PUBLISHING,
    PipelineStage.MONETIZATION,
    PipelineStage.GROWTH,
    PipelineStage.LIVE,
]


class AgentType(str, enum.Enum):
    DISCOVERY = "discovery"
    ANALYSIS = "analysis"
    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    PUBLISHING = "publishing"
    MONETIZATION = "monetization"
    GROWTH = "growth"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    app_count: Mapped[int] = mapped_column(Integer, default=0)
    saturation: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    apps: Mapped[list[ViralApp]] = relationship(back_populates="niche")


class ViralApp(Base):
    __tablename__ = "viral_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche_id: Mapped[int | None] = mapped_column(ForeignKey("niches.id"))

    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    package_name: Mapped[str | None] = mapped_column(String(300), index=True)
    developer: Mapped[str | None] = mapped_column(String(200))
    icon: Mapped[str | None] = mapped_column(Text)

    # Metrics
    rating: Mapped[float | None] = mapped_column(Float)
    total_downloads: Mapped[int | None] = mapped_column(BigInteger)
    last_month_downloads: Mapped[int | None] = mapped_column(BigInteger)
    this_month_downloads: Mapped[int | None] = mapped_column(BigInteger)
    last_month_revenue: Mapped[int | None] = mapped_column(BigInteger)
    total_reviews: Mapped[int | None] = mapped_column(BigInteger)
    rating_distribution: Mapped[dict | None] = mapped_column(JSON)

    # Analysis
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    problem_solved: Mapped[str | None] = mapped_column(Text)
    key_features: Mapped[list | None] = mapped_column(JSON)
    screenshots: Mapped[list | None] = mapped_column(JSON)

    # Reviews
    positive_reviews: Mapped[list | None] = mapped_column(JSON)
    negative_reviews: Mapped[list | None] = mapped_column(JSON)
    identified_issues: Mapped[list | None] = mapped_column(JSON)
    improvement_suggestions: Mapped[list | None] = mapped_column(JSON)

    # Business
    monetization_model: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    trend_score: Mapped[float | None] = mapped_column(Float)
    clone_potential_score: Mapped[int | None] = mapped_column(Integer, index=True)
    clone_score_breakdown: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(50), default=AppStatus.DISCOVERED.value, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    niche: Mapped[Niche | None] = relationship(back_populates="apps")
    analyses: Mapped[list[AppAnalysis]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )
    projects: Mapped[list[CloneProject]] = relationship(back_populates="source_app")

    __table_args__ = (UniqueConstraint("package_name", name="uq_viral_apps_package"),)


class AppAnalysis(Base):
    """Blueprint 3.x - deep analysis report attached to a viral app."""

    __tablename__ = "app_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("viral_apps.id"), index=True)

    functional_analysis: Mapped[dict | None] = mapped_column(JSON)
    review_analysis: Mapped[dict | None] = mapped_column(JSON)
    competitive_analysis: Mapped[dict | None] = mapped_column(JSON)
    technical_assessment: Mapped[dict | None] = mapped_column(JSON)

    recommendation: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    must_fix_issues: Mapped[list | None] = mapped_column(JSON)
    must_add_features: Mapped[list | None] = mapped_column(JSON)
    clone_name_ideas: Mapped[list | None] = mapped_column(JSON)
    reviews_analyzed: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    app: Mapped[ViralApp] = relationship(back_populates="analyses")


class CloneProject(Base):
    __tablename__ = "clone_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_app_id: Mapped[int | None] = mapped_column(ForeignKey("viral_apps.id"), index=True)

    # Clone identity
    clone_name: Mapped[str] = mapped_column(String(200), nullable=False)
    clone_package_name: Mapped[str | None] = mapped_column(String(300))
    tagline: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    # Pipeline
    status: Mapped[str] = mapped_column(String(50), default="discovered", index=True)
    pipeline_stage: Mapped[str] = mapped_column(
        String(50), default=PipelineStage.DISCOVERY.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    blocked_reason: Mapped[str | None] = mapped_column(Text)

    # Business
    ai_recommended_price: Mapped[float | None] = mapped_column(Float)
    monthly_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    ltv: Mapped[float | None] = mapped_column(Float)
    monetization_config: Mapped[dict | None] = mapped_column(JSON)

    # Assets / development
    design_assets: Mapped[dict | None] = mapped_column(JSON)
    patched_issues: Mapped[list | None] = mapped_column(JSON)
    new_features: Mapped[list | None] = mapped_column(JSON)
    tech_stack: Mapped[dict | None] = mapped_column(JSON)
    repository_url: Mapped[str | None] = mapped_column(Text)

    # Testing
    build_logs: Mapped[list | None] = mapped_column(JSON)
    test_results: Mapped[dict | None] = mapped_column(JSON)

    # Publishing
    simulator_url: Mapped[str | None] = mapped_column(Text)
    play_store_url: Mapped[str | None] = mapped_column(Text)
    store_listing: Mapped[dict | None] = mapped_column(JSON)
    version_history: Mapped[list | None] = mapped_column(JSON)
    rollout_status: Mapped[dict | None] = mapped_column(JSON)

    # Approval gate (blueprint: HUMAN APPROVAL between TEST and PUBLISH)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_feedback: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    source_app: Mapped[ViralApp | None] = relationship(back_populates="projects")
    events: Mapped[list[PipelineEvent]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    earnings: Mapped[list[Earning]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("clone_projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    project: Mapped[CloneProject] = relationship(back_populates="events")


class Earning(Base):
    __tablename__ = "earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("clone_projects.id"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    ad_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    iap_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    subscription_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    country_breakdown: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[CloneProject] = relationship(back_populates="earnings")

    __table_args__ = (UniqueConstraint("project_id", "date", name="uq_earnings_project_date"),)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("clone_projects.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(50))
    content: Mapped[str | None] = mapped_column(Text)
    extracted_issues: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("clone_projects.id"), index=True)
    app_id: Mapped[int | None] = mapped_column(ForeignKey("viral_apps.id"))
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    input_data: Mapped[dict | None] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class LiveMonitor(Base):
    """Blueprint 9.2 - rolling health snapshot per live app."""

    __tablename__ = "live_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("clone_projects.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    crash_free_rate: Mapped[float | None] = mapped_column(Float)
    average_rating: Mapped[float | None] = mapped_column(Float)
    daily_revenue: Mapped[float | None] = mapped_column(Float)
    dau: Mapped[int | None] = mapped_column(Integer)
    anomalies: Mapped[list | None] = mapped_column(JSON)
    actions_taken: Mapped[list | None] = mapped_column(JSON)
    halted: Mapped[bool] = mapped_column(Boolean, default=False)
