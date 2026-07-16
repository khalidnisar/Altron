#!/usr/bin/env python3
"""Validate structure and scan text for common secret patterns.

This is a best-effort local check, not a substitute for manual privacy/security
review or a dedicated secret scanner. It performs no network requests.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import urlsplit

REQUIRED_FILES = (
    "manifest.json",
    "authorization.md",
    "project-brief.md",
    ".gitignore",
    "inventories/routes.csv",
    "inventories/states.csv",
    "inventories/journeys.csv",
    "inventories/endpoints.csv",
    "inventories/assets.csv",
    "design/tokens.md",
    "architecture.md",
    "contracts/openapi.yaml",
    "parity-matrix.csv",
    "test-plan.md",
    "handoff.md",
    "evidence/README.md",
)

CSV_HEADERS: Dict[str, Sequence[str]] = {
    "inventories/routes.csv": (
        "route_id",
        "route_pattern",
        "title_or_purpose",
        "auth_role",
        "locale",
        "theme",
        "viewport_classes",
        "source",
        "confidence",
        "priority",
        "implementation_status",
        "notes",
    ),
    "inventories/states.csv": (
        "state_id",
        "route_id",
        "component_or_region",
        "state_name",
        "trigger",
        "expected_behavior",
        "exit_behavior",
        "evidence_ref",
        "confidence",
        "priority",
        "implementation_status",
        "notes",
    ),
    "inventories/journeys.csv": (
        "journey_id",
        "name",
        "role",
        "preconditions",
        "start_route_id",
        "steps",
        "linked_state_ids",
        "linked_endpoint_ids",
        "side_effect_class",
        "cleanup",
        "priority",
        "implementation_status",
        "test_ref",
        "notes",
    ),
    "inventories/endpoints.csv": (
        "endpoint_id",
        "protocol",
        "method_or_event",
        "parameterized_path_or_operation",
        "purpose",
        "auth_role",
        "request_schema_ref",
        "response_schema_ref",
        "status_or_error_codes",
        "side_effects",
        "idempotency",
        "pagination_or_streaming",
        "evidence_ref",
        "confidence",
        "implementation_status",
        "notes",
    ),
    "inventories/assets.csv": (
        "asset_id",
        "type",
        "purpose",
        "source_reference",
        "dimensions_or_variants",
        "rights_status",
        "license_or_attribution",
        "replacement_plan",
        "implementation_status",
        "notes",
    ),
    "parity-matrix.csv": (
        "parity_id",
        "kind",
        "subject_id",
        "dimension",
        "acceptance_criteria",
        "reference_evidence",
        "test_evidence",
        "status",
        "residual_delta",
        "owner_decision",
        "notes",
    ),
}

SECRET_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "authorization-bearer",
        re.compile(r"(?im)^\s*authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "cookie-header",
        re.compile(r"(?im)^\s*(?:cookie|set-cookie)\s*:\s*[^\s].{7,}"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password)"
            r"\b\s*[:=]\s*[\"']?(?!(?:TBD|REDACTED|PLACEHOLDER|EXAMPLE)\b)[A-Za-z0-9_./+~-]{16,}"
        ),
    ),
    (
        "sensitive-query",
        re.compile(
            r"(?i)[?&](?:access_token|refresh_token|api_key|apikey|signature|sig|session)="
            r"(?!(?:REDACTED|PLACEHOLDER|EXAMPLE)(?:&|$))[^\s&#]{8,}"
        ),
    ),
)

SENSITIVE_NAME_PATTERNS = (
    re.compile(r"(?i)(?:^|[-_.])storage[-_.]?state(?:[-_.]|$)"),
    re.compile(r"(?i)(?:^|[-_.])cookies?(?:[-_.]|$)"),
    re.compile(r"(?i)\.har$"),
    re.compile(r"(?i)\.(?:pem|key|p12|pfx)$"),
)

TEXT_SUFFIXES = {
    "",
    ".md",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".xml",
    ".env",
    ".log",
}
MAX_SCAN_BYTES = 5 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a site reconstruction workspace and scan for common secret patterns."
    )
    parser.add_argument("--root", default=".site-rebuild", help="Workspace root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    return parser.parse_args()


def issue(level: str, code: str, message: str, path: str = "") -> Dict[str, str]:
    result = {"level": level, "code": code, "message": message}
    if path:
        result["path"] = path
    return result


def read_text_safely(path: Path) -> Tuple[str, str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "", f"cannot stat file: {exc}"
    if size > MAX_SCAN_BYTES:
        return "", f"file exceeds {MAX_SCAN_BYTES} byte scan limit"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return "", f"cannot read file: {exc}"
    if b"\x00" in data[:4096]:
        return "", "binary file skipped"
    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError:
        return "", "non-UTF-8 file skipped"


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path


def validate_manifest(root: Path, findings: List[Dict[str, str]]) -> None:
    path = root / "manifest.json"
    if not path.is_file():
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(issue("error", "manifest-invalid", str(exc), "manifest.json"))
        return

    if manifest.get("schema_version") != 1:
        findings.append(issue("error", "manifest-schema", "schema_version must equal 1", "manifest.json"))
    mode = manifest.get("mode")
    authorization = manifest.get("authorization")
    if mode not in {
        "source-assisted",
        "contract-assisted",
        "black-box-authorized",
        "inspiration-only",
    }:
        findings.append(issue("error", "manifest-mode", "unsupported mode", "manifest.json"))
    if mode == "inspiration-only" and authorization != "inspiration-only":
        findings.append(
            issue("error", "manifest-authorization", "inspiration-only mode has inconsistent authorization", "manifest.json")
        )
    if mode and mode != "inspiration-only" and authorization != "confirmed":
        findings.append(
            issue("error", "manifest-authorization", "rebuild mode requires confirmed authorization", "manifest.json")
        )

    target_url = str(manifest.get("target_url", ""))
    parsed = urlsplit(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        findings.append(issue("error", "manifest-url", "target_url must be an http(s) URL without credentials", "manifest.json"))
    reference = manifest.get("authorization_reference")
    if not isinstance(reference, str) or not reference.strip():
        findings.append(issue("error", "manifest-reference", "authorization_reference is required", "manifest.json"))
    if manifest.get("contains_secrets") is not False:
        findings.append(issue("error", "manifest-secrets", "contains_secrets must be false", "manifest.json"))


def validate_csv(root: Path, findings: List[Dict[str, str]]) -> None:
    for relative, expected in CSV_HEADERS.items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                actual = next(reader, [])
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            findings.append(issue("error", "csv-invalid", str(exc), relative))
            continue
        if tuple(actual) != tuple(expected):
            findings.append(
                issue(
                    "error",
                    "csv-header",
                    "header does not match the bundled artifact contract",
                    relative,
                )
            )


def scan_workspace(root: Path, findings: List[Dict[str, str]]) -> None:
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        name = path.name
        if any(pattern.search(name) for pattern in SENSITIVE_NAME_PATTERNS):
            findings.append(
                issue(
                    "warning",
                    "sensitive-filename",
                    "sensitive capture/key filename present; keep it outside version control and review manually",
                    relative,
                )
            )

        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES and path.name not in {".gitignore", ".env"}:
            continue
        text, skipped_reason = read_text_safely(path)
        if skipped_reason:
            if skipped_reason not in {"binary file skipped", "non-UTF-8 file skipped"}:
                findings.append(issue("warning", "scan-skipped", skipped_reason, relative))
            continue

        for secret_type, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(
                    issue(
                        "error",
                        "possible-secret",
                        f"possible {secret_type} at line {line_number(text, match.start())}; value not displayed",
                        relative,
                    )
                )
        unresolved = text.count("{{")
        if unresolved:
            findings.append(
                issue(
                    "warning",
                    "unrendered-template",
                    f"contains {unresolved} unresolved template marker(s)",
                    relative,
                )
            )
        tbd_count = len(re.findall(r"\bTBD\b", text))
        if tbd_count:
            findings.append(
                issue(
                    "warning",
                    "incomplete-artifact",
                    f"contains {tbd_count} TBD marker(s)",
                    relative,
                )
            )


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    findings: List[Dict[str, str]] = []

    if not root.is_dir():
        findings.append(issue("error", "workspace-missing", "workspace directory does not exist", str(root)))
    else:
        for relative in REQUIRED_FILES:
            if not (root / relative).is_file():
                findings.append(issue("error", "required-file", "required file is missing", relative))

        gitignore = root / ".gitignore"
        if gitignore.is_file():
            text = gitignore.read_text(encoding="utf-8", errors="replace")
            for rule in ("evidence/raw/", "*.har", "*storage-state*"):
                if rule not in text:
                    findings.append(issue("error", "ignore-rule", f"missing ignore rule: {rule}", ".gitignore"))

        validate_manifest(root, findings)
        validate_csv(root, findings)
        scan_workspace(root, findings)

    errors = sum(1 for item in findings if item["level"] == "error")
    warnings = sum(1 for item in findings if item["level"] == "warning")
    result = {
        "workspace": str(root),
        "valid": errors == 0 and (not args.strict or warnings == 0),
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
        "note": "Common-pattern scan only; manually review evidence and use a dedicated secret scanner before commit.",
        "network_requests": 0,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Workspace: {root}")
        for item in findings:
            location = f" [{item.get('path')}]" if item.get("path") else ""
            print(f"{item['level'].upper()} {item['code']}{location}: {item['message']}")
        print(f"Result: {errors} error(s), {warnings} warning(s)")
        print(result["note"])

    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
