#!/usr/bin/env python3
"""Local-first, resumable runner for the toolkit's declarative AI loops."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from workflow_core import (
    EventLog,
    WorkflowError,
    canonical_json,
    descendants,
    load_json,
    path_in_workspace,
    phase_map,
    reduce_events,
    sha256_file,
    validate_workflow,
)
from verifier_registry import run_verifier, verifier_for


CONTROL_DIR = ".loop"


def control_paths(workspace: Path) -> tuple[Path, Path]:
    control = workspace / CONTROL_DIR
    if workspace.is_symlink() or control.is_symlink():
        raise WorkflowError("workspace 和 .loop 控制目录不能是符号链接")
    return control / "workflow.json", control / "events.jsonl"


def load_run(workspace: Path) -> tuple[dict[str, Any], EventLog, dict[str, Any]]:
    workflow_path, events_path = control_paths(workspace)
    workflow = load_json(workflow_path)
    event_log = EventLog(events_path)
    state = reduce_events(workflow, event_log.read())
    if state["run_id"] is None:
        raise WorkflowError("运行目录没有 run_created 事件")
    return workflow, event_log, state


def parse_named_paths(values: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise WorkflowError(f"输入必须写成 name=/path：{value}")
        name, raw_path = value.split("=", 1)
        if not name or not raw_path:
            raise WorkflowError(f"输入必须写成 name=/path：{value}")
        parsed[name] = Path(raw_path).expanduser().resolve()
    return parsed


def selected_phase_ids(workflow: dict[str, Any], target_id: str | None) -> set[str]:
    if not target_id:
        return {phase["id"] for phase in workflow["phases"]}
    target = next((item for item in workflow.get("targets", []) if item.get("id") == target_id), None)
    if target is None:
        raise WorkflowError(f"未知 target：{target_id}")
    phases = phase_map(workflow)
    needed = set()
    stack = [target["terminal_phase"]]
    while stack:
        current = stack.pop()
        if current in needed:
            continue
        needed.add(current)
        stack.extend(phases[current].get("depends_on", []))
    return needed


def command_init(args: argparse.Namespace) -> None:
    workflow = load_json(args.workflow.resolve())
    errors = validate_workflow(workflow)
    if errors:
        raise WorkflowError("工作流定义未通过验证：\n- " + "\n- ".join(errors))
    workspace = args.workspace.expanduser().absolute()
    if workspace.is_symlink():
        raise WorkflowError("workspace 不能是符号链接")
    workflow_path, events_path = control_paths(workspace)
    if workflow_path.exists() or events_path.exists():
        raise WorkflowError(f"目录已经初始化：{workspace}")
    provided = parse_named_paths(args.input)
    declared = {item["name"]: item for item in workflow["inputs"]}
    unknown = sorted(set(provided) - set(declared))
    if unknown:
        raise WorkflowError(f"工作流未声明这些输入：{', '.join(unknown)}")
    missing = [name for name, item in declared.items() if item.get("required") and name not in provided]
    if missing:
        raise WorkflowError(f"缺少必填输入：{', '.join(missing)}")
    selected_target = args.target or workflow.get("default_target")
    selected_phase_ids(workflow, selected_target)
    inputs: dict[str, dict[str, Any]] = {}
    for name, path in provided.items():
        if not path.is_file():
            raise WorkflowError(f"输入必须是可读文件：{name}={path}")
        allowed_formats = {value.lower().lstrip(".") for value in declared[name].get("formats", [])}
        actual_format = path.suffix.lower().lstrip(".")
        if allowed_formats and actual_format not in allowed_formats:
            raise WorkflowError(f"输入 {name} 格式为 {actual_format or '[none]'}；允许：{', '.join(sorted(allowed_formats))}")
    for folder in ("00_input", "10_work", "20_output", "90_logs", "99_exception_queue"):
        (workspace / folder).mkdir(parents=True, exist_ok=True)
    for name, path in provided.items():
        snapshot = workspace / "00_input" / f"{name}{path.suffix.lower()}"
        if snapshot.exists() or snapshot.is_symlink():
            raise WorkflowError(f"输入快照目标已存在：{snapshot.name}")
        shutil.copy2(path, snapshot)
        inputs[name] = {
            "stored_path": snapshot.relative_to(workspace).as_posix(),
            "sha256": sha256_file(snapshot),
            "size": snapshot.stat().st_size,
            "format": path.suffix.lower().lstrip("."),
        }
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.workflow.resolve(), workflow_path)
    event_log = EventLog(events_path)
    event_log.append(
        "run_created",
        {
            "run_id": f"run_{uuid.uuid4().hex[:12]}",
            "workflow_id": workflow["id"],
            "workflow_version": workflow["version"],
            "inputs": inputs,
            "mode": "local-read-only",
            "generation": 1,
            "target": selected_target,
        },
    )
    print(f"已初始化：{workspace}")
    print("下一步：运行 status，查看可开始阶段。")


def ready_phases(workflow: dict[str, Any], state: dict[str, Any]) -> list[str]:
    ready = []
    selected = selected_phase_ids(workflow, state.get("target"))
    for phase in workflow["phases"]:
        if phase["id"] not in selected:
            continue
        current = state["phases"][phase["id"]]["status"]
        if current not in {"pending", "failed", "invalidated"}:
            continue
        if all(state["phases"][dependency]["status"] == "completed" for dependency in phase["depends_on"]):
            ready.append(phase["id"])
    return ready


def command_status(args: argparse.Namespace) -> None:
    workflow, _, state = load_run(args.workspace.resolve())
    output = {
        "run_id": state["run_id"],
        "workflow": workflow["id"],
        "target": state.get("target") or "full",
        "events": state["events"],
        "generation": state["generation"],
        "ready": ready_phases(workflow, state),
        "phases": state["phases"],
    }
    selected = selected_phase_ids(workflow, state.get("target"))
    output["run_status"] = (
        "completed" if selected and all(state["phases"][phase_id]["status"] == "completed" for phase_id in selected) else "active"
    )
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    print(
        f"Run: {state['run_id']}  Workflow: {workflow['id']}  Target: {output['target']}  "
        f"Status: {output['run_status']}  Generation: {state['generation']}  Events: {state['events']}"
    )
    print(f"可开始：{', '.join(output['ready']) or '无'}")
    for phase in workflow["phases"]:
        phase_state = state["phases"][phase["id"]]
        marker = "" if phase["id"] in selected else " [not in target]"
        print(f"- {phase['id']}: {phase_state['status']} (attempts={phase_state['attempts']}){marker}")


def ensure_phase(workflow: dict[str, Any], phase_id: str) -> dict[str, Any]:
    phase = phase_map(workflow).get(phase_id)
    if phase is None:
        raise WorkflowError(f"未知阶段：{phase_id}")
    return phase


def command_start(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    if phase["type"] == "mutation":
        raise WorkflowError("公开运行器禁止真实 mutation 阶段")
    if args.phase not in ready_phases(workflow, state):
        raise WorkflowError("阶段尚不可开始；请检查依赖、当前状态或失败预算")
    attempts = state["phases"][args.phase]["attempts"]
    if attempts >= phase["retry"]["max_attempts"]:
        raise WorkflowError("已达到最大尝试次数；请处理 99_exception_queue，不要继续同路重试")
    if attempts > 0 and not args.strategy:
        raise WorkflowError("重试必须用 --strategy 说明本次改变；禁止原路无限重试")
    event_log.append(
        "phase_started",
        {"phase": args.phase, "strategy": args.strategy or "initial", "generation": state["generation"]},
    )
    print(f"已开始：{args.phase}（第 {attempts + 1} 次）")


def command_record(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    if state["phases"][args.phase]["status"] != "running":
        raise WorkflowError("只能给 running 阶段登记产物")
    path = args.path.resolve()
    if not path.is_file():
        raise WorkflowError(f"产物不存在或不是文件：{path}")
    if not path_in_workspace(path, workspace):
        raise WorkflowError("产物必须位于运行工作区内，避免把私有绝对路径写入日志")
    relative = path.relative_to(workspace).as_posix()
    declared = {item["name"] for item in phase["outputs"]}
    if args.name not in declared:
        raise WorkflowError(f"阶段未声明产物 {args.name}；允许：{', '.join(sorted(declared))}")
    if any(item.get("name") == args.name for item in state["phases"][args.phase]["artifacts"]):
        raise WorkflowError(f"本代已经登记产物 {args.name}；请先失败并以新策略重启阶段，不得覆盖证据")
    event_log.append(
        "artifact_recorded",
        {
            "phase": args.phase,
            "name": args.name,
            "path": relative,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "taint": args.taint,
            "generation": state["generation"],
        },
    )
    print(f"已登记产物：{args.name} -> {relative}")


def command_verify(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    if state["phases"][args.phase]["status"] != "running":
        raise WorkflowError("只能验证 running 阶段")
    declared = {item["name"] for item in phase["checks"]}
    if args.check not in declared:
        raise WorkflowError(f"阶段未声明检查 {args.check}；允许：{', '.join(sorted(declared))}")
    phase_state = state["phases"][args.phase]
    artifact_hashes = {}
    for artifact in phase_state["artifacts"]:
        path = workspace / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise WorkflowError(f"产物在验证前缺失或已变化：{artifact['name']}")
        artifact_hashes[artifact["name"]] = artifact["sha256"]
    automatic = verifier_for(args.check)
    evidence = None
    if automatic:
        if args.by != "auto":
            raise WorkflowError(f"检查 {args.check} 绑定 runner verifier {automatic}，不能由人工或 AI 自报")
        passed, verifier_evidence = run_verifier(args.check, workspace, phase_state, state["generation"])
        evidence_path = workspace / CONTROL_DIR / "verification" / f"g{state['generation']}_{args.phase}_{args.check}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(verifier_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        evidence = {"path": evidence_path.relative_to(workspace).as_posix(), "sha256": sha256_file(evidence_path)}
    else:
        if args.by != "human":
            raise WorkflowError(f"检查 {args.check} 尚无自动 verifier，必须提供独立人工证据")
        if not args.reviewer or not args.producer or args.reviewer == args.producer:
            raise WorkflowError("人工验证必须提供不同的 --reviewer 与 --producer，AI 不能批准自己的产物")
        if args.result is None:
            raise WorkflowError("人工验证必须明确 --result pass 或 --result fail")
        if not args.evidence:
            raise WorkflowError("人工验证必须提供 --evidence，空证据不能 PASS")
        evidence_path = args.evidence.resolve()
        if not evidence_path.is_file() or not path_in_workspace(evidence_path, workspace):
            raise WorkflowError("验证证据必须是运行工作区内的文件")
        passed = args.result == "pass"
        evidence = {
            "path": evidence_path.relative_to(workspace).as_posix(),
            "sha256": sha256_file(evidence_path),
            "reviewer": args.reviewer,
            "producer": args.producer,
        }
    event_log.append(
        "verification_recorded",
        {
            "phase": args.phase,
            "check": args.check,
            "passed": passed,
            "evidence": evidence,
            "by": args.by,
            "generation": state["generation"],
            "artifact_hashes": artifact_hashes,
        },
    )
    print(f"检查 {args.check}: {'PASS' if passed else 'FAIL'} ({args.by})")


def command_decide(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    if phase["type"] != "human":
        raise WorkflowError("只有 human 阶段接受人工决定")
    if state["phases"][args.phase]["status"] != "running":
        raise WorkflowError("只能对 running 的人工阶段作决定")
    if args.reviewer == args.producer:
        raise WorkflowError("reviewer 与 producer 必须不同")
    evidence_path = args.evidence.resolve()
    if not evidence_path.is_file() or not path_in_workspace(evidence_path, workspace):
        raise WorkflowError("人工决定必须提供工作区内的证据文件")
    artifact_hashes = {
        item["name"]: item["sha256"] for item in state["phases"][args.phase]["artifacts"]
    }
    review_object = hashlib.sha256(canonical_json({"inputs": state["inputs"], "artifacts": artifact_hashes}).encode("utf-8")).hexdigest()
    event_log.append(
        "human_decision",
        {
            "phase": args.phase,
            "decision": args.decision,
            "note": args.note or "",
            "reviewer": args.reviewer,
            "producer": args.producer,
            "evidence": {"path": evidence_path.relative_to(workspace).as_posix(), "sha256": sha256_file(evidence_path)},
            "review_object": review_object,
            "generation": state["generation"],
        },
    )
    print(f"已记录人工决定：{args.decision}")


def command_complete(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    phase_state = state["phases"][args.phase]
    if phase_state["status"] != "running":
        raise WorkflowError("只能完成 running 阶段")
    required_outputs = {item["name"] for item in phase["outputs"] if item.get("required", True)}
    recorded_outputs = {item["name"] for item in phase_state["artifacts"]}
    missing_outputs = sorted(required_outputs - recorded_outputs)
    if missing_outputs:
        raise WorkflowError(f"缺少必填产物：{', '.join(missing_outputs)}")
    current_hashes = {}
    for artifact in phase_state["artifacts"]:
        path = workspace / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise WorkflowError(f"产物缺失或在验证后变化：{artifact['name']}")
        current_hashes[artifact["name"]] = artifact["sha256"]
    required_checks = {item["name"] for item in phase["checks"] if item.get("required", True)}
    failed_or_missing = sorted(
        name for name in required_checks if not phase_state["checks"].get(name, {}).get("passed", False)
    )
    if failed_or_missing:
        raise WorkflowError(f"以下检查尚未通过：{', '.join(failed_or_missing)}")
    stale_checks = sorted(
        name
        for name in required_checks
        if phase_state["checks"][name].get("generation") != state["generation"]
        or phase_state["checks"][name].get("artifact_hashes") != current_hashes
    )
    if stale_checks:
        raise WorkflowError(f"以下检查未绑定当前代或当前产物：{', '.join(stale_checks)}")
    if phase["type"] == "human":
        decision = phase_state.get("decision")
        if not decision or decision.get("decision") != "approve":
            raise WorkflowError("人工阶段需要明确 approve；AI 不能代替批准")
        expected_object = hashlib.sha256(canonical_json({"inputs": state["inputs"], "artifacts": current_hashes}).encode("utf-8")).hexdigest()
        if decision.get("generation") != state["generation"] or decision.get("review_object") != expected_object:
            raise WorkflowError("人工批准未绑定当前输入代与当前产物")
    event_log.append(
        "phase_completed",
        {"phase": args.phase, "completion": phase["completion"], "generation": state["generation"]},
    )
    print(f"已完成：{args.phase}")


def command_fail(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    phase = ensure_phase(workflow, args.phase)
    phase_state = state["phases"][args.phase]
    if phase_state["status"] != "running":
        raise WorkflowError("只能将 running 阶段标记失败")
    exhausted = phase_state["attempts"] >= phase["retry"]["max_attempts"]
    event_log.append(
        "phase_failed",
        {"phase": args.phase, "kind": args.kind, "note": args.note or "", "exhausted": exhausted},
    )
    if exhausted:
        queue = workspace / "99_exception_queue" / f"{args.phase}.md"
        if not queue.exists():
            queue.write_text(
                f"# 阶段异常：{args.phase}\n\n错误类别：{args.kind}\n\n请人工选择替代路径；不要继续同路重试。\n",
                encoding="utf-8",
            )
        print(f"失败预算已耗尽，已阻断并生成：{queue.relative_to(workspace)}")
    else:
        print("已记录失败；下一次 start 必须通过 --strategy 说明改变的策略。")


def command_change_input(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    declared = {item["name"]: item for item in workflow["inputs"]}
    if args.name not in declared:
        raise WorkflowError(f"未知输入：{args.name}")
    path = args.path.resolve()
    if not path.is_file():
        raise WorkflowError("新输入必须是可读文件")
    affected = []
    for phase in workflow["phases"]:
        if f"input:{args.name}" in phase["inputs"]:
            affected.append(phase["id"])
    invalidated = sorted(descendants(workflow, affected))
    allowed_formats = {value.lower().lstrip(".") for value in declared[args.name].get("formats", [])}
    actual_format = path.suffix.lower().lstrip(".")
    if allowed_formats and actual_format not in allowed_formats:
        raise WorkflowError(f"输入格式不匹配；允许：{', '.join(sorted(allowed_formats))}")
    new_generation = state["generation"] + 1
    snapshot = workspace / "00_input" / f"{args.name}.g{new_generation}{path.suffix.lower()}"
    if snapshot.exists() or snapshot.is_symlink():
        raise WorkflowError("新一代输入快照目标已存在")
    shutil.copy2(path, snapshot)
    new_input = {
        "stored_path": snapshot.relative_to(workspace).as_posix(),
        "sha256": sha256_file(snapshot),
        "size": snapshot.stat().st_size,
        "format": actual_format,
    }
    if state["inputs"].get(args.name, {}).get("sha256") == new_input["sha256"]:
        raise WorkflowError("输入内容指纹未变化，无需失效下游")
    event_log.append(
        "input_changed",
        {"name": args.name, "input": new_input, "invalidated": invalidated, "generation": new_generation},
    )
    print(f"输入已变化；失效阶段：{', '.join(invalidated) or '无'}")


def command_doctor(args: argparse.Namespace) -> None:
    workspace = args.workspace.resolve()
    workflow, event_log, state = load_run(workspace)
    errors = validate_workflow(workflow)
    if errors:
        raise WorkflowError("工作流定义错误：\n- " + "\n- ".join(errors))
    missing = []
    changed = []
    for phase_id, phase_state in state["phases"].items():
        for artifact in phase_state["artifacts"]:
            path = workspace / artifact["path"]
            if not path.is_file():
                missing.append(artifact["path"])
            elif sha256_file(path) != artifact["sha256"]:
                changed.append(artifact["path"])
    print(f"事件链：OK（{len(event_log.read())} 条）")
    print(f"工作流契约：OK（{workflow['id']} {workflow['version']}）")
    print(f"缺失产物：{len(missing)}")
    print(f"指纹变化产物：{len(changed)}")
    if missing or changed:
        raise WorkflowError("产物完整性检查失败；请保留现场并通过 change-input 或重新执行受影响阶段恢复")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全、可恢复的本地 AI Loop 状态机")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化工作区")
    init_parser.add_argument("workflow", type=Path)
    init_parser.add_argument("--workspace", required=True, type=Path)
    init_parser.add_argument("--input", action="append", default=[], help="name=/absolute/or/relative/file")
    init_parser.add_argument("--target", help="可选完成目标；例如 positioning-only")
    init_parser.set_defaults(func=command_init)

    status_parser = subparsers.add_parser("status", help="显示当前状态")
    status_parser.add_argument("--workspace", required=True, type=Path)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=command_status)

    start_parser = subparsers.add_parser("start", help="开始一个可运行阶段")
    start_parser.add_argument("phase")
    start_parser.add_argument("--workspace", required=True, type=Path)
    start_parser.add_argument("--strategy", help="重试时说明改变的策略")
    start_parser.set_defaults(func=command_start)

    record_parser = subparsers.add_parser("record", help="登记阶段产物")
    record_parser.add_argument("phase")
    record_parser.add_argument("name")
    record_parser.add_argument("path", type=Path)
    record_parser.add_argument("--workspace", required=True, type=Path)
    record_parser.add_argument("--taint", choices=["private", "sensitive-derived", "publishable"], default="private")
    record_parser.set_defaults(func=command_record)

    verify_parser = subparsers.add_parser("verify", help="运行自动 verifier 或登记独立人工证据")
    verify_parser.add_argument("phase")
    verify_parser.add_argument("check")
    verify_parser.add_argument("--workspace", required=True, type=Path)
    verify_parser.add_argument("--by", choices=["auto", "human"], required=True)
    verify_parser.add_argument("--result", choices=["pass", "fail"], help="仅人工验证使用")
    verify_parser.add_argument("--evidence", type=Path)
    verify_parser.add_argument("--reviewer")
    verify_parser.add_argument("--producer")
    verify_parser.set_defaults(func=command_verify)

    decide_parser = subparsers.add_parser("decide", help="记录人工决定")
    decide_parser.add_argument("phase")
    decide_parser.add_argument("decision", choices=["approve", "reject", "revise"])
    decide_parser.add_argument("--workspace", required=True, type=Path)
    decide_parser.add_argument("--note")
    decide_parser.add_argument("--reviewer", required=True)
    decide_parser.add_argument("--producer", required=True)
    decide_parser.add_argument("--evidence", required=True, type=Path)
    decide_parser.set_defaults(func=command_decide)

    complete_parser = subparsers.add_parser("complete", help="在产物和检查满足后完成阶段")
    complete_parser.add_argument("phase")
    complete_parser.add_argument("--workspace", required=True, type=Path)
    complete_parser.set_defaults(func=command_complete)

    fail_parser = subparsers.add_parser("fail", help="记录失败并执行有限重试预算")
    fail_parser.add_argument("phase")
    fail_parser.add_argument("kind")
    fail_parser.add_argument("--workspace", required=True, type=Path)
    fail_parser.add_argument("--note")
    fail_parser.set_defaults(func=command_fail)

    change_parser = subparsers.add_parser("change-input", help="输入变化并失效受影响分支")
    change_parser.add_argument("name")
    change_parser.add_argument("path", type=Path)
    change_parser.add_argument("--workspace", required=True, type=Path)
    change_parser.set_defaults(func=command_change_input)

    doctor_parser = subparsers.add_parser("doctor", help="检查事件链和产物完整性")
    doctor_parser.add_argument("--workspace", required=True, type=Path)
    doctor_parser.set_defaults(func=command_doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except WorkflowError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
