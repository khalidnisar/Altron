"""Agent 3 - Design Studio (blueprint section 4)."""

from __future__ import annotations

import hashlib

from appforge.agents.base import AgentResult, BaseAgent
from appforge.models import AgentTask, PipelineStage
from appforge.services.providers import ImageProvider

BASE_SCREENS = [
    {"id": "splash", "name": "Splash Screen", "priority": "high"},
    {"id": "onboarding_1", "name": "Welcome", "priority": "high"},
    {"id": "onboarding_2", "name": "Features", "priority": "high"},
    {"id": "onboarding_3", "name": "Permissions", "priority": "high"},
    {"id": "login", "name": "Login / Signup", "priority": "high"},
    {"id": "home", "name": "Home", "priority": "high"},
    {"id": "detail", "name": "Detail", "priority": "high"},
    {"id": "create", "name": "Create", "priority": "high"},
    {"id": "profile", "name": "Profile", "priority": "medium"},
    {"id": "settings", "name": "Settings", "priority": "low"},
    {"id": "subscription", "name": "Premium Upgrade", "priority": "high"},
]

# Niche-appropriate primary hues (blueprint 4.2.2).
NICHE_HUES = {
    "finance": "#0E9F6E", "health_fitness": "#EF4444", "productivity": "#5C7CFA",
    "education": "#8B5CF6", "photography": "#EC4899", "travel": "#0EA5E9",
    "food_drink": "#F59E0B", "gaming": "#7C3AED", "weather": "#38BDF8",
    "finance_default": "#5C7CFA",
}


def _palette_for(niche: str | None, name: str) -> dict:
    primary = NICHE_HUES.get(niche or "", None)
    if primary is None:
        digest = hashlib.sha256((name or "app").encode()).hexdigest()
        hue = int(digest[:2], 16)
        primary = ["#5C7CFA", "#0EA5E9", "#8B5CF6", "#0E9F6E", "#F59E0B", "#EC4899"][hue % 6]
    return {
        "primary": primary,
        "primary_light": primary + "CC",
        "primary_dark": primary,
        "secondary": "#10B981",
        "accent": "#F59E0B",
        "background_dark": "#0F1117",
        "background_light": "#F8FAFC",
        "surface": "#181B24",
        "surface_light": "#FFFFFF",
        "text_primary": "#F0F0F5",
        "text_secondary": "#9CA3AF",
        "text_primary_light": "#0F172A",
        "error": "#EF4444",
        "success": "#22C55E",
    }


DESIGN_SYSTEM = {
    "typography": {
        "font_family": "Inter",
        "heading_1": {"size": 32, "weight": 700, "line_height": 1.2},
        "heading_2": {"size": 24, "weight": 600, "line_height": 1.3},
        "heading_3": {"size": 20, "weight": 600, "line_height": 1.4},
        "body": {"size": 16, "weight": 400, "line_height": 1.5},
        "body_small": {"size": 14, "weight": 400, "line_height": 1.5},
        "caption": {"size": 12, "weight": 400, "line_height": 1.4},
    },
    "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "xxl": 48},
    "border_radius": {"sm": 4, "md": 8, "lg": 16, "xl": 24, "full": 9999},
    "shadows": {
        "sm": "0 1px 2px rgba(0,0,0,0.1)",
        "md": "0 4px 6px rgba(0,0,0,0.1)",
        "lg": "0 10px 15px rgba(0,0,0,0.1)",
    },
    "components": {
        "button_primary": {"background": "primary", "text_color": "white",
                           "border_radius": "lg", "padding": "md lg", "font_weight": 600},
        "button_secondary": {"background": "transparent", "text_color": "primary",
                             "border": "1px solid primary", "border_radius": "lg",
                             "padding": "md lg", "font_weight": 600},
        "card": {"background": "surface", "border_radius": "xl", "padding": "lg",
                 "border": "1px solid rgba(255,255,255,0.1)"},
        "input": {"background": "surface", "border": "1px solid rgba(255,255,255,0.2)",
                  "border_radius": "md", "padding": "md", "focus_border": "primary"},
    },
}


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    def luminance(h: str) -> float:
        h = h.lstrip("#")[:6]
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        adj = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * adj[0] + 0.7152 * adj[1] + 0.0722 * adj[2]

    la, lb = luminance(hex_a), luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


class DesignAgent(BaseAgent):
    agent_type = "design"
    completes_stage = PipelineStage.DESIGN

    def run(self, task: AgentTask) -> AgentResult:
        project = self.project(task)
        source = project.source_app
        niche = source.category if source else None

        palette = _palette_for(niche, project.clone_name)

        # Accessibility gate (WCAG 2.1 AA = 4.5:1 for body text).
        contrast = _contrast_ratio(palette["text_primary"], palette["background_dark"])
        accessible = contrast >= 4.5

        images = ImageProvider(self.settings)
        logo_assets = images.generate_logo_set(project.id, project.clone_name, palette)

        screens = list(BASE_SCREENS)
        screenshots = images.generate_screenshots(project.id, screens, palette)
        feature_graphic = images.generate_feature_graphic(
            project.id, project.clone_name, project.tagline or "", palette
        )

        # UX improvements derived from the issues we committed to patching.
        ux_improvements = [
            {"issue": p["original"], "design_response": p["fix"]}
            for p in (project.patched_issues or [])
        ]

        project.design_assets = {
            "palette": palette,
            "design_system": DESIGN_SYSTEM,
            "logo": logo_assets,
            "screens": screens,
            "screenshots": screenshots,
            "feature_graphic": feature_graphic,
            "themes": ["dark", "light"],
            "ux_improvements": ux_improvements,
            "accessibility": {
                "wcag_target": "2.1 AA",
                "body_contrast_ratio": round(contrast, 2),
                "passes": accessible,
            },
        }
        project.pipeline_stage = PipelineStage.DESIGN.value
        project.status = "design_complete"
        project.progress = 40

        self.append_build_log(project, "design", "Brand and UI assets generated", "success")
        self.log_event(
            project.id, PipelineStage.DESIGN.value, "design_complete",
            f"Generated brand identity and {len(screens)} screen designs",
            {"palette": palette["primary"], "screens": len(screens)},
        )

        self.queue_task("development", "generate_code", project_id=project.id, priority=50)

        return AgentResult(
            success=True,
            output={"screens": len(screens), "contrast": round(contrast, 2),
                    "accessible": accessible},
            message=f"Design complete for {project.clone_name}",
        )
