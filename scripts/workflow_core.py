#!/usr/bin/env python3
"""Deterministic primitives shared by the local-first workflow tools."""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PHASE_TYPES = {"deterministic", "assistive", "human", "mutation"}
RISK_LEVELS = {"low", "medium", "high", "critical"}
EVENT_TYPES = {
    "run_created",
    "phase_started",
    "artifact_recorded",
    "verification_recorded",
    "phase_completed",
    "phase_failed",
    "human_decision",
    "input_changed",
}


class WorkflowError(RuntimeError):
    """A user-actionable workflow error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"JSON 格式错误：{path}（第 {exc.lineno} 行）") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"顶层必须是 JSON object：{path}")
    return value


def phase_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {phase["id"]: phase for phase in workflow.get("phases", []) if isinstance(phase, dict) and "id" in phase}


def descendants(workflow: dict[str, Any], seeds: Iterable[str]) -> set[str]:
    children: dict[str, set[str]] = defaultdict(set)
    for phase in workflow.get("phases", []):
        for parent in phase.get("depends_on", []):
            children[parent].add(phase["id"])
    seen = set(seeds)
    queue = deque(seeds)
    while queue:
        current = queue.popleft()
        for child in children.get(current, set()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def validate_workflow(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = {"id", "version", "title", "audiences", "job_stories", "inputs", "phases", "deliverables"}
    for field in sorted(required_top - workflow.keys()):
        errors.append(f"缺少顶层字段：{field}")

    phases = workflow.get("phases")
    if not isinstance(phases, list) or not phases:
        errors.append("phases 必须是非空数组")
        return errors

    ids: list[str] = []
    phase_outputs: dict[str, set[str]] = {}
    for index, phase in enumerate(phases):
        label = f"phases[{index}]"
        if not isinstance(phase, dict):
            errors.append(f"{label} 必须是 object")
            continue
        required_phase = {
            "id",
            "title",
            "type",
            "risk",
            "depends_on",
            "inputs",
            "outputs",
            "checks",
            "completion",
            "abandon_when",
            "retry",
        }
        for field in sorted(required_phase - phase.keys()):
            errors.append(f"{label} 缺少字段：{field}")
        phase_id = phase.get("id")
        if not isinstance(phase_id, str) or not phase_id:
            errors.append(f"{label}.id 必须是非空字符串")
        else:
            ids.append(phase_id)
        if phase.get("type") not in PHASE_TYPES:
            errors.append(f"{label}.type 必须是 {sorted(PHASE_TYPES)} 之一")
        if phase.get("risk") not in RISK_LEVELS:
            errors.append(f"{label}.risk 必须是 {sorted(RISK_LEVELS)} 之一")
        for list_field in ("depends_on", "inputs", "outputs", "checks", "abandon_when"):
            if list_field in phase and not isinstance(phase[list_field], list):
                errors.append(f"{label}.{list_field} 必须是数组")
        retry = phase.get("retry")
        if not isinstance(retry, dict) or not isinstance(retry.get("max_attempts"), int) or retry.get("max_attempts", 0) < 1:
            errors.append(f"{label}.retry.max_attempts 必须是正整数")
        elif retry.get("max_attempts", 0) > 3:
            errors.append(f"{label}.retry.max_attempts 不得超过 3；更多尝试应进入异常队列")
        if phase.get("type") == "mutation":
            errors.append(f"{label} 是 mutation；公开首版禁止真实 mutation 阶段，只能生成 action manifest")
        output_names = [item.get("name") for item in phase.get("outputs", []) if isinstance(item, dict)]
        check_names = [item.get("name") for item in phase.get("checks", []) if isinstance(item, dict)]
        if len(output_names) != len(set(output_names)):
            errors.append(f"{label}.outputs 的 name 必须唯一")
        if len(check_names) != len(set(check_names)):
            errors.append(f"{label}.checks 的 name 必须唯一")
        if phase_id:
            phase_outputs[phase_id] = {name for name in output_names if isinstance(name, str)}

    if len(ids) != len(set(ids)):
        errors.append("phase id 必须唯一")
    known = set(ids)
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("id") not in known:
            continue
        for dependency in phase.get("depends_on", []):
            if dependency not in known:
                errors.append(f"{phase['id']} 依赖未知阶段：{dependency}")
            if dependency == phase["id"]:
                errors.append(f"{phase['id']} 不能依赖自身")

    indegree = {phase_id: 0 for phase_id in known}
    children: dict[str, list[str]] = defaultdict(list)
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("id") not in known:
            continue
        for dependency in phase.get("depends_on", []):
            if dependency in known:
                indegree[phase["id"]] += 1
                children[dependency].append(phase["id"])
    queue = deque(phase_id for phase_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(known):
        errors.append("阶段依赖存在环；返工请通过 input_changed 失效传播表达，不能在 DAG 中成环")

    targets = workflow.get("targets", [])
    if targets:
        if not isinstance(targets, list):
            errors.append("targets 必须是数组")
        else:
            target_ids = []
            for index, target in enumerate(targets):
                if not isinstance(target, dict) or not isinstance(target.get("id"), str) or not isinstance(target.get("terminal_phase"), str):
                    errors.append(f"targets[{index}] 必须包含字符串 id 与 terminal_phase")
                    continue
                target_ids.append(target["id"])
                if target["terminal_phase"] not in known:
                    errors.append(f"targets[{index}] 引用了未知 terminal_phase：{target['terminal_phase']}")
            if len(target_ids) != len(set(target_ids)):
                errors.append("target id 必须唯一")
            if workflow.get("default_target") not in set(target_ids):
                errors.append("default_target 必须引用已声明 target")

    ancestors: dict[str, set[str]] = {phase_id: set() for phase_id in known}
    changed = True
    while changed:
        changed = False
        for phase in phases:
            if not isinstance(phase, dict) or phase.get("id") not in known:
                continue
            expanded = set(phase.get("depends_on", []))
            for dependency in phase.get("depends_on", []):
                expanded.update(ancestors.get(dependency, set()))
            if expanded != ancestors[phase["id"]]:
                ancestors[phase["id"]] = expanded
                changed = True

    from verifier_registry import verifier_for

    for phase in phases:
        if not isinstance(phase, dict) or phase.get("id") not in known:
            continue
        available_outputs = set()
        for ancestor in ancestors[phase["id"]]:
            available_outputs.update(phase_outputs.get(ancestor, set()))
        for item in phase.get("inputs", []):
            if isinstance(item, str) and item.startswith("artifact:") and item[9:] not in available_outputs:
                errors.append(f"{phase['id']} 引用了祖先未产出的 artifact：{item}")
        if phase.get("type") == "deterministic":
            missing_verifiers = [
                check.get("name")
                for check in phase.get("checks", [])
                if isinstance(check, dict) and verifier_for(check.get("name", "")) is None
            ]
            if missing_verifiers:
                errors.append(
                    f"{phase['id']} 标为 deterministic，但以下检查没有 runner verifier：{', '.join(missing_verifiers)}；"
                    "请实现 verifier 或将阶段改为 assistive/human"
                )

    input_names = set()
    for index, item in enumerate(workflow.get("inputs", [])):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            errors.append(f"inputs[{index}] 必须包含字符串 name")
            continue
        input_names.add(item["name"])
        if "required" not in item or "rights_required" not in item:
            errors.append(f"inputs[{index}] 必须声明 required 与 rights_required")

    for phase in phases:
        if not isinstance(phase, dict):
            continue
        for item in phase.get("inputs", []):
            if item.startswith("input:") and item[6:] not in input_names:
                errors.append(f"{phase.get('id')} 引用了未知工作流输入：{item}")
    return errors


class EventLog:
    """Append-only hash-chained JSONL event log."""

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")

    @staticmethod
    def _open_no_follow(path: Path, flags: int, mode: int = 0o600) -> int:
        if path.is_symlink():
            raise WorkflowError(f"拒绝跟随符号链接：{path.name}")
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(path, flags, mode)
        except OSError as exc:
            raise WorkflowError(f"无法安全打开控制文件：{path.name}") from exc

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise WorkflowError("事件日志不能是符号链接")
        events: list[dict[str, Any]] = []
        previous = "0" * 64
        descriptor = self._open_no_follow(self.path, os.O_RDONLY)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise WorkflowError(f"事件日志第 {line_number} 行不完整；请保留文件并运行备份恢复，不要手工补写")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise WorkflowError(f"事件日志第 {line_number} 行损坏") from exc
                stored_hash = event.pop("event_hash", None)
                if event.get("prev_hash") != previous:
                    raise WorkflowError(f"事件日志第 {line_number} 行前序哈希不匹配")
                calculated = sha256_bytes(canonical_json(event).encode("utf-8"))
                if stored_hash != calculated:
                    raise WorkflowError(f"事件日志第 {line_number} 行内容哈希不匹配")
                event["event_hash"] = stored_hash
                events.append(event)
                previous = stored_hash
        return events

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise WorkflowError(f"未知事件类型：{event_type}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_descriptor = self._open_no_follow(self.lock_path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            events = self.read()
            previous = events[-1]["event_hash"] if events else "0" * 64
            event = {
                "event_id": f"evt_{len(events) + 1:06d}",
                "type": event_type,
                "time": utc_now(),
                "prev_hash": previous,
                "payload": payload,
            }
            event["event_hash"] = sha256_bytes(canonical_json(event).encode("utf-8"))
            descriptor = self._open_no_follow(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY)
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(canonical_json(event) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            os.close(lock_descriptor)
        return event


def initial_phase_state(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        phase["id"]: {
            "status": "pending",
            "attempts": 0,
            "generation": 1,
            "artifacts": [],
            "checks": {},
            "decision": None,
            "failure": None,
        }
        for phase in workflow["phases"]
    }


def reduce_events(workflow: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    phases = initial_phase_state(workflow)
    inputs: dict[str, dict[str, Any]] = {}
    run_id = None
    generation = 1
    target = None
    for event in events:
        event_type = event["type"]
        payload = event["payload"]
        phase_id = payload.get("phase")
        if event_type == "run_created":
            run_id = payload["run_id"]
            inputs = payload.get("inputs", {})
            generation = payload.get("generation", 1)
            target = payload.get("target")
        elif event_type == "phase_started" and phase_id in phases:
            event_generation = payload.get("generation", generation)
            phases[phase_id]["generation"] = event_generation
            phases[phase_id]["status"] = "running"
            phases[phase_id]["attempts"] += 1
            phases[phase_id]["artifacts"] = []
            phases[phase_id]["checks"] = {}
            phases[phase_id]["decision"] = None
            phases[phase_id]["failure"] = None
        elif event_type == "artifact_recorded" and phase_id in phases:
            if payload.get("generation", phases[phase_id]["generation"]) == phases[phase_id]["generation"]:
                phases[phase_id]["artifacts"].append(payload)
        elif event_type == "verification_recorded" and phase_id in phases:
            if payload.get("generation", phases[phase_id]["generation"]) == phases[phase_id]["generation"]:
                phases[phase_id]["checks"][payload["check"]] = {
                    "passed": payload["passed"],
                    "evidence": payload.get("evidence"),
                    "by": payload.get("by"),
                    "generation": payload.get("generation"),
                    "artifact_hashes": payload.get("artifact_hashes", {}),
                }
        elif event_type == "human_decision" and phase_id in phases:
            if payload.get("generation", phases[phase_id]["generation"]) == phases[phase_id]["generation"]:
                phases[phase_id]["decision"] = payload
        elif event_type == "phase_completed" and phase_id in phases:
            phases[phase_id]["status"] = "completed"
            phases[phase_id]["failure"] = None
        elif event_type == "phase_failed" and phase_id in phases:
            phases[phase_id]["status"] = "blocked" if payload.get("exhausted") else "failed"
            phases[phase_id]["failure"] = payload
        elif event_type == "input_changed":
            generation = payload.get("generation", generation + 1)
            input_name = payload["name"]
            inputs[input_name] = payload["input"]
            for invalidated in payload.get("invalidated", []):
                if invalidated in phases:
                    phases[invalidated]["status"] = "invalidated"
                    phases[invalidated]["generation"] = generation
                    phases[invalidated]["attempts"] = 0
                    phases[invalidated]["artifacts"] = []
                    phases[invalidated]["checks"] = {}
                    phases[invalidated]["decision"] = None
    return {
        "run_id": run_id,
        "generation": generation,
        "target": target,
        "inputs": inputs,
        "phases": phases,
        "events": len(events),
    }


def path_in_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False
