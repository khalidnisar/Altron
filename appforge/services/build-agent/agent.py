"""Windows-native build agent.

Polls the AppForge API for queued Windows build work, produces release artifacts
with the Windows toolchain, and reports results back. Runs inside a Windows
Server Core container (see ``Dockerfile.windows``).

This agent is optional. The Linux worker handles the standard pipeline; use this
only when artifacts must be produced by Windows tooling.
"""

from __future__ import annotations

import logging
import os
import platform
import signal
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("appforge.build-agent")

API_URL = os.getenv("APPFORGE_API_URL", "http://host.docker.internal:8000").rstrip("/")
TOKEN = os.getenv("APPFORGE_OPERATOR_TOKEN", "")
AGENT_NAME = os.getenv("APPFORGE_AGENT_NAME", "windows-build-agent")
STORAGE_ROOT = Path(os.getenv("APPFORGE_STORAGE_ROOT", r"C:\data\artifacts"))
POLL_SECONDS = float(os.getenv("APPFORGE_POLL_SECONDS", "10"))

_running = True


def _stop(signum, frame):  # noqa: ARG001
    global _running
    logger.info("Signal %s received; finishing current job then exiting", signum)
    _running = False


def _headers() -> dict[str, str]:
    return {"X-Operator-Token": TOKEN} if TOKEN else {}


def wait_for_api(client: httpx.Client, attempts: int = 60) -> bool:
    for i in range(attempts):
        try:
            r = client.get(f"{API_URL}/api/health", timeout=10)
            if r.status_code == 200:
                logger.info("Connected to API at %s", API_URL)
                return True
        except Exception as exc:  # noqa: BLE001
            logger.info("Waiting for API (%s/%s): %s", i + 1, attempts, exc)
        time.sleep(3)
    return False


def fetch_build_jobs(client: httpx.Client) -> list[dict]:
    """Projects that have reached publishing and need a Windows artifact."""
    try:
        r = client.get(f"{API_URL}/api/projects", params={"stage": "publishing"},
                       headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch jobs: %s", exc)
        return []


def build_artifact(project: dict) -> Path:
    """Produce a Windows build artifact for the project.

    Real deployments invoke the Windows toolchain here (MSBuild, signtool,
    Flutter Windows desktop, packaging scripts). This writes a manifest so the
    container is verifiably doing work and the wiring can be tested end to end.
    """
    project_id = project["id"]
    out_dir = STORAGE_ROOT / f"projects/{project_id}/windows"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = out_dir / "build-manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"project_id={project_id}",
                f"clone_name={project.get('clone_name')}",
                f"package={project.get('clone_package_name')}",
                f"agent={AGENT_NAME}",
                f"host={platform.platform()}",
                f"python={sys.version.split()[0]}",
                f"built_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            ]
        ),
        encoding="utf-8",
    )
    logger.info("Wrote artifact manifest for project %s -> %s", project_id, manifest)
    return manifest


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("%s starting on %s", AGENT_NAME, platform.platform())
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        if not wait_for_api(client):
            logger.error("API never became reachable at %s", API_URL)
            raise SystemExit(1)

        seen: set[int] = set()
        while _running:
            for project in fetch_build_jobs(client):
                pid = project["id"]
                if pid in seen:
                    continue
                try:
                    build_artifact(project)
                    seen.add(pid)
                except Exception:  # noqa: BLE001
                    logger.exception("Build failed for project %s", pid)
            time.sleep(POLL_SECONDS)

    logger.info("%s stopped", AGENT_NAME)


if __name__ == "__main__":
    main()
