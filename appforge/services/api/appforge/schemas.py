"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NicheOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    category: str
    icon: str | None = None
    description: str | None = None
    app_count: int = 0
    saturation: float = 0.5


class ViralAppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    niche_id: int | None = None
    name: str
    package_name: str | None = None
    developer: str | None = None
    icon: str | None = None
    rating: float | None = None
    total_downloads: int | None = None
    last_month_downloads: int | None = None
    last_month_revenue: int | None = None
    total_reviews: int | None = None
    category: str | None = None
    description: str | None = None
    problem_solved: str | None = None
    key_features: list[Any] | None = None
    monetization_model: str | None = None
    rank: int | None = None
    trend_score: float | None = None
    clone_potential_score: int | None = None
    clone_score_breakdown: dict[str, Any] | None = None
    status: str
    created_at: datetime | None = None


class ViralAppDetail(ViralAppOut):
    positive_reviews: list[Any] | None = None
    negative_reviews: list[Any] | None = None
    identified_issues: list[Any] | None = None
    improvement_suggestions: list[Any] | None = None
    rating_distribution: dict[str, Any] | None = None
    screenshots: list[Any] | None = None
    analysis: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_app_id: int | None = None
    clone_name: str
    clone_package_name: str | None = None
    tagline: str | None = None
    status: str
    pipeline_stage: str
    progress: int
    blocked_reason: str | None = None
    ai_recommended_price: float | None = None
    monthly_revenue: float = 0.0
    total_revenue: float = 0.0
    repository_url: str | None = None
    simulator_url: str | None = None
    play_store_url: str | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectDetail(ProjectOut):
    description: str | None = None
    design_assets: dict[str, Any] | None = None
    patched_issues: list[Any] | None = None
    new_features: list[Any] | None = None
    tech_stack: dict[str, Any] | None = None
    build_logs: list[Any] | None = None
    test_results: dict[str, Any] | None = None
    store_listing: dict[str, Any] | None = None
    monetization_config: dict[str, Any] | None = None
    rollout_status: dict[str, Any] | None = None
    version_history: list[Any] | None = None
    ltv: float | None = None
    source_app: ViralAppOut | None = None


class PipelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    stage: str
    event_type: str
    message: str | None = None
    created_at: datetime


class EarningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    downloads: int
    revenue: float
    ad_revenue: float
    iap_revenue: float
    subscription_revenue: float


class ApprovalRequest(BaseModel):
    approved_by: str = Field(default="operator", max_length=200)
    feedback: str | None = None


class RejectionRequest(BaseModel):
    rejected_by: str = Field(default="operator", max_length=200)
    feedback: str = Field(min_length=1)


class CloneRequest(BaseModel):
    clone_name: str | None = None


class TriggerRequest(BaseModel):
    agent: str
    task_type: str
    project_id: int | None = None
    app_id: int | None = None
    priority: int = 0
    input_data: dict[str, Any] = Field(default_factory=dict)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_type: str
    task_type: str
    project_id: int | None = None
    app_id: int | None = None
    status: str
    priority: int
    attempts: int
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class PaginatedApps(BaseModel):
    items: list[ViralAppOut]
    total: int
    page: int
    limit: int
