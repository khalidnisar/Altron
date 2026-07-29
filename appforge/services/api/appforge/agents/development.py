"""Agent 4 - Development (blueprint section 5)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, PipelineStage
from appforge.services.codegen import generate_flutter_project

#: Stop the test -> fix -> test cycle before it loops forever.
MAX_REMEDIATION_ATTEMPTS = 3


def _classify_reason(reason: str) -> str:
    """Map a free-text failure reason onto a patch generator category."""
    text = reason.lower()
    if any(k in text for k in ("crash", "anr", "memory", "start", "slow", "battery")):
        return "performance"
    if any(k in text for k in ("permission", "privacy", "data collection")):
        return "privacy"
    if any(k in text for k in ("data loss", "migration", "corrupt")):
        return "reliability"
    if any(k in text for k in ("accessib", "contrast", "talkback", "screen reader")):
        return "accessibility"
    if any(k in text for k in ("price", "pricing", "subscription", "paywall")):
        return "monetization"
    return "ux"

INTEGRATIONS = [
    {"name": "Authentication", "provider": "Supabase Auth", "methods": ["email", "google", "apple"]},
    {"name": "Analytics", "provider": "Mixpanel", "events": ["app_open", "feature_used", "purchase"]},
    {"name": "Crash reporting", "provider": "Sentry"},
    {"name": "Push notifications", "provider": "Firebase Cloud Messaging"},
    {"name": "In-app purchases", "provider": "RevenueCat"},
    {"name": "Ads", "provider": "AdMob with mediation"},
]


class DevelopmentAgent(BaseAgent):
    agent_type = "development"
    completes_stage = PipelineStage.DEVELOPMENT

    def run(self, task: AgentTask) -> AgentResult:
        if task.task_type == "apply_fixes":
            return self._apply_fixes(task)
        return self._generate(task)

    # ------------------------------------------------------------------
    def _apply_fixes(self, task: AgentTask) -> AgentResult:
        """Remediation pass triggered by failed tests, a crash spike, or a
        human rejection.

        Records the remediation request on the project, then regenerates so the
        new requirements are reflected in the code. Without this branch the task
        fell through to a plain rebuild and the feedback was silently dropped.
        """
        project = self.project(task)
        payload = task.input_data or {}

        reasons: list[str] = []
        if payload.get("failed_criteria"):
            reasons.extend(payload["failed_criteria"])
        if payload.get("feedback"):
            reasons.append(f"Reviewer: {payload['feedback']}")
        if payload.get("reason") == "crash_spike":
            reasons.append(
                f"Crash spike in production (crash-free {payload.get('crash_free')}%)"
            )
        if not reasons:
            reasons.append("Unspecified remediation request")

        history = list(project.remediation_history or [])
        attempt = len(history) + 1
        history.append({
            "attempt": attempt,
            "requested_at": datetime.utcnow().isoformat() + "Z",
            "reasons": reasons,
            "source": payload.get("reason") or task.task_type,
        })
        project.remediation_history = history
        # Flush so the history survives a later refresh/re-fetch in this session.
        self.session.flush()

        # Guard against an infinite test->fix->test loop.
        if attempt > MAX_REMEDIATION_ATTEMPTS:
            project.status = "needs_human_intervention"
            project.blocked_reason = (
                f"{attempt - 1} automated fix attempts did not clear: "
                f"{'; '.join(reasons)}"
            )
            self.append_build_log(
                project, "development",
                f"Halting after {MAX_REMEDIATION_ATTEMPTS} failed remediation attempts",
                "failure",
            )
            self.log_event(
                project.id, PipelineStage.DEVELOPMENT.value, "remediation_exhausted",
                project.blocked_reason, {"attempts": attempt - 1},
            )
            return AgentResult(
                success=False,
                output={"attempts": attempt - 1, "reasons": reasons},
                message=project.blocked_reason,
            )

        # Convert each reason into a tracked fix item so codegen can respond.
        patches = list(project.patched_issues or [])
        known = {p.get("original") for p in patches}
        for reason in reasons:
            if reason not in known:
                patches.append({
                    "original": reason,
                    "fix": "Regression fix generated from pipeline feedback",
                    "severity": "high",
                    "type": _classify_reason(reason),
                    "status": "planned",
                })
        project.patched_issues = patches

        self.append_build_log(
            project, "development",
            f"Remediation attempt {attempt}: {'; '.join(reasons)}", "info",
        )
        self.log_event(
            project.id, PipelineStage.DEVELOPMENT.value, "remediation_started",
            f"Attempt {attempt} addressing {len(reasons)} item(s)",
            {"reasons": reasons},
        )

        result = self._generate(task, remediation_attempt=attempt)
        result.message = f"Remediation attempt {attempt}: {result.message}"
        return result

    # ------------------------------------------------------------------
    def _generate(self, task: AgentTask, remediation_attempt: int = 0) -> AgentResult:
        project = self.project(task)
        assets = project.design_assets or {}
        palette = assets.get("palette") or {}
        design_system = assets.get("design_system") or {}

        source = project.source_app
        features = list(source.key_features or []) if source else []
        features += [f for f in (project.new_features or []) if f not in features]

        patches = list(project.patched_issues or [])

        root = Path(self.settings.storage_root) / f"projects/{project.id}/repo"
        manifest = generate_flutter_project(
            root=root,
            app_name=project.clone_name,
            package_name=project.clone_package_name or "ai.appforge.app",
            tagline=project.tagline or "",
            features=features,
            palette=palette,
            design_system=design_system,
            patches=patches,
        )

        # Reflect implemented status back onto the project record.
        project.patched_issues = manifest["patches"]
        project.repository_url = f"{self.settings.storage_public_base}/projects/{project.id}/repo"
        project.tech_stack = {**(project.tech_stack or {}), "integrations": INTEGRATIONS}
        project.pipeline_stage = PipelineStage.DEVELOPMENT.value
        project.status = "development_complete"
        project.progress = 60

        self.append_build_log(
            project, "development",
            f"Generated {manifest['file_count']} files across {len(manifest['features'])} features",
            "success",
        )
        self.append_build_log(
            project, "development",
            f"Implemented {len(manifest['patches'])} issue patches", "success",
        )

        self.log_event(
            project.id, PipelineStage.DEVELOPMENT.value, "code_generated",
            f"Generated Flutter project with {manifest['file_count']} files",
            {"features": manifest["features"], "patches": len(manifest["patches"])},
        )

        self.queue_task("testing", "run_test_suite", project_id=project.id, priority=60)

        return AgentResult(
            success=True,
            output=manifest,
            message=f"Generated {manifest['file_count']} files, "
                    f"{len(manifest['patches'])} patches applied",
        )
