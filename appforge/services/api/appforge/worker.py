"""Long-running worker process that drains the agent task queue."""

from __future__ import annotations

import logging
import signal
import time

from appforge.config import get_settings
from appforge.db import init_db, session_scope
from appforge.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("appforge.worker")

_running = True


def _stop(signum, frame):  # noqa: ARG001
    global _running
    logger.info("Received signal %s, shutting down after current task", signum)
    _running = False


def main() -> None:
    settings = get_settings()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    for attempt in range(30):
        try:
            init_db()
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Database not ready (%s/30): %s", attempt + 1, exc)
            time.sleep(2)
    else:
        raise SystemExit("Database never became available")

    logger.info(
        "Worker started (offline_mode=%s, poll=%.1fs)",
        settings.offline_mode, settings.worker_poll_seconds,
    )

    while _running:
        try:
            with session_scope() as session:
                results = Orchestrator(session, settings).run_once()
            for r in results:
                level = logging.INFO if r["success"] else logging.ERROR
                logger.log(level, "task=%s agent=%s %s",
                           r["task_id"], r.get("agent"), r.get("message") or r.get("error"))
            if not results:
                time.sleep(settings.worker_poll_seconds)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error; backing off")
            time.sleep(5)

    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
