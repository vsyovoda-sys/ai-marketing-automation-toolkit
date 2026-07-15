#!/usr/bin/env python3
"""Create and validate mutation plans; this tool never commits them."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED = {
    "manifest_version", "manifest_id", "created_at", "expires_at", "tenant",
    "profile", "actor", "action", "target", "diff", "quantity", "cost_cap",
    "currency", "input_fingerprints", "idempotency_key", "status",
}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入 JSON 顶层必须是 object")
    return value


def business_payload(manifest: dict[str, object]) -> dict[str, object]:
    return {
        field: manifest.get(field)
        for field in (
            "tenant", "profile", "actor", "action", "target", "diff", "quantity",
            "cost_cap", "currency", "input_fingerprints",
        )
    }


def expected_idempotency_key(manifest: dict[str, object]) -> str:
    return hashlib.sha256(canonical(business_payload(manifest)).encode("utf-8")).hexdigest()


def validate(manifest: dict[str, object]) -> list[str]:
    errors = [f"缺少字段：{field}" for field in sorted(REQUIRED - manifest.keys())]
    if manifest.get("status") != "plan_only":
        errors.append("公开首版 status 必须是 plan_only")
    for field in ("tenant", "profile", "actor", "action", "target"):
        if not isinstance(manifest.get(field), str) or not str(manifest.get(field)).strip():
            errors.append(f"{field} 必须是非空字符串，不能从历史默认值猜测")
    if not isinstance(manifest.get("diff"), dict) or not manifest.get("diff"):
        errors.append("diff 必须是非空 object，写明精确变化")
    if not isinstance(manifest.get("input_fingerprints"), dict) or not manifest.get("input_fingerprints"):
        errors.append("input_fingerprints 必须是非空 object")
    quantity = manifest.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
        errors.append("quantity 必须是非负整数")
    cost = manifest.get("cost_cap")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(float(cost)) or float(cost) < 0:
        errors.append("cost_cap 必须是非负数字")
    try:
        expires = datetime.fromisoformat(str(manifest.get("expires_at")))
        created = datetime.fromisoformat(str(manifest.get("created_at")))
        timezone_missing = expires.tzinfo is None or created.tzinfo is None
        if timezone_missing:
            errors.append("created_at/expires_at 必须含时区")
        if expires <= created:
            errors.append("expires_at 必须晚于 created_at")
        if expires - created > timedelta(minutes=60):
            errors.append("TTL 不得超过 60 分钟")
        if not timezone_missing and expires <= datetime.now(timezone.utc):
            errors.append("manifest 已过期")
    except ValueError:
        errors.append("created_at/expires_at 必须是 ISO 8601")
    if manifest.get("idempotency_key") != expected_idempotency_key(manifest):
        errors.append("idempotency_key 与规范化业务字段不匹配")
    return errors


def command_create(args: argparse.Namespace) -> int:
    change = load_object(args.change)
    fingerprints = load_object(args.fingerprints)
    if args.ttl_minutes < 1 or args.ttl_minutes > 60:
        print("ttl-minutes 必须在 1 到 60 之间", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    seed = secrets.token_hex(16)
    base = {
        "manifest_version": "1.0",
        "manifest_id": "act_" + hashlib.sha256(seed.encode()).hexdigest()[:16],
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=args.ttl_minutes)).isoformat(),
        "tenant": args.tenant,
        "profile": args.profile,
        "actor": args.actor,
        "action": args.action,
        "target": args.target,
        "diff": change,
        "quantity": args.quantity,
        "cost_cap": args.cost_cap,
        "currency": args.currency,
        "input_fingerprints": fingerprints,
        "status": "plan_only",
    }
    base["idempotency_key"] = expected_idempotency_key(base)
    errors = validate(base)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    if args.output.exists():
        print("拒绝覆盖现有 manifest；请使用新路径", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成只读动作清单：{args.output}")
    print("本工具不会执行 commit；请人工核对租户、身份、目标、diff、数量、费用和 TTL。")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    try:
        manifest = load_object(args.manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"读取失败：{type(exc).__name__}", file=sys.stderr)
        return 2
    errors = validate(manifest)
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK：manifest 合法，且仍为 plan_only；未执行任何外部操作。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="只生成外部写操作清单，不执行写入")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--tenant", required=True)
    create.add_argument("--profile", required=True)
    create.add_argument("--actor", required=True)
    create.add_argument("--action", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--change", required=True, type=Path)
    create.add_argument("--fingerprints", required=True, type=Path)
    create.add_argument("--quantity", required=True, type=int)
    create.add_argument("--cost-cap", required=True, type=float)
    create.add_argument("--currency", required=True)
    create.add_argument("--ttl-minutes", type=int, default=30)
    create.add_argument("--output", required=True, type=Path)
    create.set_defaults(func=command_create)
    check = subparsers.add_parser("validate")
    check.add_argument("manifest", type=Path)
    check.set_defaults(func=command_validate)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
