"""Agent 4 - Development (blueprint section 5)."""

from __future__ import annotations

from pathlib import Path

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, PipelineStage
from appforge.services.codegen import generate_flutter_project

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
