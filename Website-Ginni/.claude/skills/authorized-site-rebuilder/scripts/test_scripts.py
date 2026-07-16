#!/usr/bin/env python3
"""Regression tests for the bundled workspace scripts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INIT = SCRIPT_DIR / "init_workspace.py"
VALIDATE = SCRIPT_DIR / "validate_workspace.py"


class WorkspaceScriptTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_initialize_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "workspace"
            created = self.run_script(
                INIT,
                "--url",
                "HTTPS://Example.COM:443/app#ignored",
                "--output",
                str(root),
                "--mode",
                "black-box-authorized",
                "--authorization",
                "confirmed",
                "--authorization-reference",
                "owner-confirmed 2026-07-16",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            result = json.loads(created.stdout)
            self.assertEqual(result["target_url"], "https://example.com/app")
            self.assertEqual(result["network_requests"], 0)
            self.assertTrue((root / "contracts" / "openapi.yaml").is_file())

            validated = self.run_script(VALIDATE, "--root", str(root), "--json")
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            report = json.loads(validated.stdout)
            self.assertEqual(report["errors"], 0)
            self.assertGreater(report["warnings"], 0)  # Expected template TBD markers.

            strict = self.run_script(VALIDATE, "--root", str(root), "--strict")
            self.assertEqual(strict.returncode, 1)

    def test_refuses_inconsistent_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_script(
                INIT,
                "--url",
                "https://example.com",
                "--output",
                str(Path(temp) / "workspace"),
                "--mode",
                "black-box-authorized",
                "--authorization",
                "inspiration-only",
                "--authorization-reference",
                "not-authorized",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("require --authorization confirmed", result.stderr)

    def test_refuses_embedded_url_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_script(
                INIT,
                "--url",
                "https://user:password@example.com",
                "--output",
                str(Path(temp) / "workspace"),
                "--mode",
                "source-assisted",
                "--authorization",
                "confirmed",
                "--authorization-reference",
                "owner-confirmed",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("embedded credentials", result.stderr)

    def test_detects_common_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "workspace"
            created = self.run_script(
                INIT,
                "--url",
                "https://example.com",
                "--output",
                str(root),
                "--mode",
                "contract-assisted",
                "--authorization",
                "confirmed",
                "--authorization-reference",
                "owner-confirmed",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            (root / "evidence" / "sanitized" / "bad.txt").write_text(
                "Authorization: Bearer this-is-a-real-looking-secret-token\n",
                encoding="utf-8",
            )

            validated = self.run_script(VALIDATE, "--root", str(root), "--json")
            self.assertEqual(validated.returncode, 1)
            report = json.loads(validated.stdout)
            self.assertGreaterEqual(report["errors"], 1)
            self.assertTrue(
                any(item["code"] == "possible-secret" for item in report["findings"])
            )

    def test_resume_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "workspace"
            common = (
                "--url",
                "https://example.com",
                "--output",
                str(root),
                "--mode",
                "source-assisted",
                "--authorization",
                "confirmed",
                "--authorization-reference",
                "owner-confirmed",
            )
            first = self.run_script(INIT, *common)
            self.assertEqual(first.returncode, 0, first.stderr)
            brief = root / "project-brief.md"
            brief.write_text("custom content\n", encoding="utf-8")

            second = self.run_script(INIT, *common, "--resume")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(brief.read_text(encoding="utf-8"), "custom content\n")


if __name__ == "__main__":
    unittest.main()
