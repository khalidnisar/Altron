"""Task queue orchestration.

Claims pending tasks, dispatches them to the right agent, and records results.
The queue lives in PostgreSQL (``agent_tasks``) so no broker is required for the
default deployment; Redis/Celery can be layered on later without changing the
agent contract.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from appforge.agents import AGENT_REGISTRY
from appforge.config import Settings, get_settings
from appforge.models import AgentTask, TaskStatus

logger = logging.getLogger("appforge.orchestrator")


class Orchestrator:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def claim_next(self) -> AgentTask | None:
        """Claim the highest-priority pending task."""
        stmt = (
            select(AgentTask)
            .where(AgentTask.status == TaskStatus.PENDING.value)
            .order_by(AgentTask.priority.desc(), AgentTask.created_at.asc())
            .limit(1)
        )
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        task = self.session.scalar(stmt)
        if task is None:
            return None

        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.utcnow()
        task.attempts += 1
        self.session.flush()
        return task

    def execute(self, task: AgentTask) -> dict:
        """Run a single claimed task to completion."""
        agent_cls = AGENT_REGISTRY.get(task.agent_type)
        if agent_cls is None:
            self._fail(task, f"No agent registered for '{task.agent_type}'")
            return {"task_id": task.id, "success": False, "error": "unknown agent"}

        agent = agent_cls(self.session, self.settings)
        try:
            result = agent.run(task)
        except Exception as exc:  # noqa: BLE001 - recorded on the task row
            logger.exception("Task %s failed", task.id)
            self._fail(task, str(exc))
            return {"task_id": task.id, "success": False, "error": str(exc)}

        task.status = TaskStatus.COMPLETED.value if result.success else TaskStatus.FAILED.value
        task.completed_at = datetime.utcnow()
        task.output_data = result.output
        if not result.success:
            task.error_message = result.message

        for spec in result.next_tasks:
            self.session.add(AgentTask(**spec))

        return {
            "task_id": task.id,
            "agent": task.agent_type,
            "task_type": task.task_type,
            "success": result.success,
            "message": result.message,
            "output": result.output,
        }

    def run_once(self, limit: int | None = None) -> list[dict]:
        """Drain up to ``limit`` tasks. Returns one record per executed task."""
        limit = limit or self.settings.worker_batch_size
        results = []
        for _ in range(limit):
            task = self.claim_next()
            if task is None:
                break
            results.append(self.execute(task))
            self.session.commit()
        return results

    def drain(self, max_tasks: int = 200) -> list[dict]:
        """Run until the queue is empty (used by the demo pipeline and tests)."""
        results = []
        while len(results) < max_tasks:
            batch = self.run_once(limit=1)
            if not batch:
                break
            results.extend(batch)
        return results

    def _fail(self, task: AgentTask, error: str) -> None:
        task.error_message = error
        task.completed_at = datetime.utcnow()
        if task.attempts >= self.settings.task_max_attempts:
            task.status = TaskStatus.FAILED.value
        else:
            task.status = TaskStatus.PENDING.value  # retry
        self.session.flush()
