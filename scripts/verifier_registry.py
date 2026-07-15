#!/usr/bin/env python3
"""Automatic verifier registry for checks the runner can truly execute."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from action_manifest import validate as validate_action_manifest
from redact_scan import run_scan
from workflow_core import WorkflowError, sha256_file


CHECK_TO_VERIFIER = {
    "redaction_scan": "redaction_v1",
    "unknown_formats_absent": "redaction_v1",
    "manifest_plan_only": "action_manifest_v1",
    "any_manifest_plan_only": "optional_action_manifest_v1",
    "explicit_tenant_target_diff": "action_manifest_v1",
    "ttl_and_fingerprint": "action_manifest_v1",
}


def verifier_for(check_name: str) -> str | None:
    return CHECK_TO_VERIFIER.get(check_name)


def _current_artifacts(phase_state: dict[str, Any], generation: int) -> list[dict[str, Any]]:
    return [item for item in phase_state.get("artifacts", []) if item.get("generation") == generation]


def _redaction(workspace: Path, phase_state: dict[str, Any], generation: int) -> tuple[bool, dict[str, Any]]:
    artifacts = _current_artifacts(phase_state, generation)
    if not artifacts:
        return False, {"verifier": "redaction_v1", "reason": "no_current_artifacts"}
    summaries = []
    passed = True
    for artifact in artifacts:
        path = workspace / artifact["path"]
        report = run_scan(path, [])
        summaries.append(
            {
                "artifact": artifact["name"],
                "sha256": sha256_file(path) if path.is_file() else None,
                "summary": report["summary"],
                "safe": report["safe_to_publish"],
            }
        )
        passed = passed and bool(report["safe_to_publish"])
    return passed, {"verifier": "redaction_v1", "artifacts": summaries}


def _action_manifest(
    workspace: Path,
    phase_state: dict[str, Any],
    generation: int,
    optional: bool,
) -> tuple[bool, dict[str, Any]]:
    candidates = [item for item in _current_artifacts(phase_state, generation) if item.get("name") == "action_manifest"]
    if not candidates:
        if optional:
            return True, {"verifier": "optional_action_manifest_v1", "status": "absent"}
        return False, {"verifier": "action_manifest_v1", "reason": "action_manifest_not_recorded"}
    artifact = candidates[-1]
    path = workspace / artifact["path"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, {"verifier": "action_manifest_v1", "reason": "manifest_unreadable"}
    if not isinstance(manifest, dict):
        return False, {"verifier": "action_manifest_v1", "reason": "manifest_not_object"}
    errors = validate_action_manifest(manifest)
    return not errors, {
        "verifier": "action_manifest_v1",
        "sha256": sha256_file(path),
        "error_codes": [f"error_{index + 1}" for index, _ in enumerate(errors)],
    }


def run_verifier(
    check_name: str,
    workspace: Path,
    phase_state: dict[str, Any],
    generation: int,
) -> tuple[bool, dict[str, Any]]:
    verifier = verifier_for(check_name)
    if verifier == "redaction_v1":
        return _redaction(workspace, phase_state, generation)
    if verifier == "action_manifest_v1":
        return _action_manifest(workspace, phase_state, generation, optional=False)
    if verifier == "optional_action_manifest_v1":
        return _action_manifest(workspace, phase_state, generation, optional=True)
    raise WorkflowError(f"检查 {check_name} 没有自动 verifier；必须使用独立人工证据")
