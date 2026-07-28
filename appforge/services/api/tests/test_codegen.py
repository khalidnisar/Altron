"""The generated Flutter code must be structurally valid and patch-complete."""

from __future__ import annotations

import re

import pytest

from appforge.agents.design import DESIGN_SYSTEM, _palette_for
from appforge.services.codegen import generate_flutter_project

PATCHES = [
    {"original": "Excessive battery drain", "fix": "Add battery saver mode",
     "severity": "high", "type": "performance"},
    {"original": "Too many permissions required", "fix": "Minimal permission model",
     "severity": "high", "type": "privacy"},
    {"original": "No offline mode", "fix": "Local-first cache",
     "severity": "medium", "type": "ux"},
    {"original": "Data loss after update", "fix": "Versioned migrations with backup",
     "severity": "critical", "type": "reliability"},
    {"original": "Poor accessibility support", "fix": "Full semantics and contrast",
     "severity": "medium", "type": "accessibility"},
    {"original": "Subscription is overpriced", "fix": "Tiered regional pricing",
     "severity": "medium", "type": "monetization"},
]


@pytest.fixture
def project(tmp_path):
    return generate_flutter_project(
        root=tmp_path / "repo",
        app_name="QuickClip",
        package_name="ai.appforge.quickclip",
        tagline="Create stunning videos in seconds",
        features=["Filters", "Templates", "4K export"],
        palette=_palette_for("photography", "QuickClip"),
        design_system=DESIGN_SYSTEM,
        patches=PATCHES,
    )


def _dart_files(root):
    return list(root.rglob("*.dart"))


def test_generates_expected_structure(project, tmp_path):
    root = tmp_path / "repo"
    assert (root / "pubspec.yaml").exists()
    assert (root / "lib/main.dart").exists()
    assert (root / "lib/core/theme.dart").exists()
    assert (root / "README.md").exists()
    assert (root / ".github/workflows/ci.yaml").exists()
    assert project["file_count"] > 20


def test_no_unrendered_template_markers(tmp_path, project):
    """Regression: patch templates once leaked {{ braces and __MARKERS__."""
    for f in _dart_files(tmp_path / "repo"):
        src = f.read_text()
        assert "{{" not in src, f"double brace leaked into {f.name}"
        assert "}}" not in src, f"double brace leaked into {f.name}"
        assert "__ISSUE__" not in src, f"marker leaked into {f.name}"
        assert "__FIX__" not in src, f"marker leaked into {f.name}"
        assert "__CAUSE__" not in src


def test_dart_string_interpolation_is_not_escaped(tmp_path, project):
    """Regression: '\\$' produces a literal dollar, breaking interpolation."""
    for f in _dart_files(tmp_path / "repo"):
        assert "\\$" not in f.read_text(), f"escaped interpolation in {f.name}"


def test_all_dart_files_have_balanced_delimiters(tmp_path, project):
    for f in _dart_files(tmp_path / "repo"):
        src = f.read_text()
        src = re.sub(r"//[^\n]*", "", src)
        src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
        src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
        assert src.count("{") == src.count("}"), f"unbalanced braces in {f.name}"
        assert src.count("(") == src.count(")"), f"unbalanced parens in {f.name}"


def test_every_patch_produces_a_module_and_tests(project):
    assert len(project["patches"]) == len(PATCHES)
    for patch in project["patches"]:
        assert patch["status"] == "implemented"
        assert patch["file"].endswith(".dart")
        assert patch["tests"], f"no tests for {patch['original']}"


def test_patch_modules_document_their_source_issue(tmp_path, project):
    battery = (tmp_path / "repo/lib/core/perf/battery_manager.dart").read_text()
    assert "Excessive battery drain" in battery
    assert "Add battery saver mode" in battery


def test_privacy_patch_denies_sensitive_permissions(tmp_path, project):
    policy = (tmp_path / "repo/lib/core/privacy/permission_policy.dart").read_text()
    assert "READ_CONTACTS" in policy
    assert "denied" in policy


def test_android_manifest_uses_minimal_permissions(tmp_path, project):
    manifest = (tmp_path / "repo/android/app/src/main/AndroidManifest.xml").read_text()
    assert "android.permission.INTERNET" in manifest
    assert "READ_CONTACTS" not in manifest
    assert "ACCESS_FINE_LOCATION" not in manifest


def test_no_hardcoded_strings_in_screens(tmp_path, project):
    """User-facing text must route through AppStrings for localization."""
    screen = (tmp_path / "repo/lib/features/filters/screens/filters_screen.dart").read_text()
    assert "AppStrings.of(" in screen


def test_theme_reflects_design_system_palette(tmp_path, project):
    theme = (tmp_path / "repo/lib/core/theme.dart").read_text()
    palette = _palette_for("photography", "QuickClip")
    assert palette["primary"].lstrip("#").upper() in theme


def test_generates_tests_per_feature(project):
    counts = project["test_counts"]
    assert counts["unit_files"] == 6  # 3 features x (model + repository)
    assert counts["widget_files"] == 3
    assert counts["unit_cases"] >= 18


def test_features_include_requested_additions(tmp_path):
    result = generate_flutter_project(
        root=tmp_path / "r2", app_name="Test", package_name="a.b.c", tagline="t",
        features=["Offline mode"], palette=_palette_for(None, "Test"),
        design_system=DESIGN_SYSTEM, patches=[],
    )
    assert "Offline mode" in result["features"]
    # Baseline modules must exist even with no patches, since screens import them.
    assert (tmp_path / "r2/lib/core/a11y/accessibility.dart").exists()
    assert (tmp_path / "r2/lib/core/data/offline_cache.dart").exists()
