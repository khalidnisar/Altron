"""Base agent contract and shared helpers (blueprint section 13.1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from appforge.config import Settings, get_settings
from appforge.models import AgentTask, CloneProject, PipelineEvent, PipelineStage


@dataclass
class AgentResult:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    next_tasks: list[dict[str, Any]] = field(default_factory=list)


class BaseAgent:
    """All eight agents inherit from this."""

    agent_type: str = "base"
    #: Stage this agent advances the project to once it succeeds.
    completes_stage: PipelineStage | None = None

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.logger = logging.getLogger(f"appforge.agent.{self.agent_type}")

    # -- contract ----------------------------------------------------------
    def run(self, task: AgentTask) -> AgentResult:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- helpers -----------------------------------------------------------
    def project(self, task: AgentTask) -> CloneProject:
        project = self.session.get(CloneProject, task.project_id)
        if project is None:
            raise ValueError(f"Task {task.id} has no project (project_id={task.project_id})")
        return project

    def log_event(
        self,
        project_id: int,
        stage: str,
        event_type: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        self.session.add(
            PipelineEvent(
                project_id=project_id,
                stage=stage,
                event_type=event_type,
                message=message,
                event_metadata=metadata or {},
            )
        )

    def append_build_log(self, project: CloneProject, stage: str, message: str, status: str) -> None:
        logs = list(project.build_logs or [])
        logs.append(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "stage": stage,
                "message": message,
                "status": status,
            }
        )
        project.build_logs = logs

    def queue_task(
        self,
        agent_type: str,
        task_type: str,
        *,
        project_id: int | None = None,
        app_id: int | None = None,
        priority: int = 0,
        input_data: dict | None = None,
    ) -> AgentTask:
        task = AgentTask(
            agent_type=agent_type,
            task_type=task_type,
            project_id=project_id,
            app_id=app_id,
            priority=priority,
            input_data=input_data or {},
        )
        self.session.add(task)
        return task
