#!/usr/bin/env python3
"""Rebuild a publishable directory from an explicit allowlist and scan it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from redact_scan import load_custom_terms, run_scan


def safe_destination(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_exclusive_and_hash(source: Path, target: Path) -> tuple[str, int]:
    source_flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | (getattr(os, "O_NOFOLLOW", 0))
    source_fd = os.open(source, source_flags)
    try:
        before = os.fstat(source_fd)
        target_fd = os.open(target, target_flags, 0o644)
        digest = hashlib.sha256()
        total = 0
        try:
            while chunk := os.read(source_fd, 1024 * 1024):
                digest.update(chunk)
                total += len(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(target_fd, view)
                    view = view[written:]
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        after = os.fstat(source_fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("源文件在复制过程中发生变化")
        return digest.hexdigest(), total
    finally:
        os.close(source_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="从明确允许清单重建发布目录并 fail-closed 扫描")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--custom-terms", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        items = manifest.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("manifest.items 必须是非空数组")
        if args.output.exists():
            raise ValueError("输出目录已存在，拒绝覆盖；发布物必须从空目录重建")
        prepared = []
        destinations = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"items[{index}] 必须是 object")
            if item.get("taint") != "publishable":
                raise ValueError(f"items[{index}] 不是 publishable")
            if item.get("rights_status") != "approved":
                raise ValueError(f"items[{index}] 缺少 approved 权利状态")
            expected_sha256 = item.get("source_sha256")
            if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
                raise ValueError(f"items[{index}] 必须提供 64 位 source_sha256，绑定人工允许的具体字节")
            source = Path(item.get("source", "")).expanduser().resolve()
            destination = item.get("destination", "")
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"items[{index}] source 不是普通文件")
            if not safe_destination(destination):
                raise ValueError(f"items[{index}] destination 不安全")
            normalized_destination = PurePosixPath(destination).as_posix().casefold()
            if normalized_destination in destinations:
                raise ValueError(f"items[{index}] destination 与前项重名")
            destinations.add(normalized_destination)
            prepared.append((source, destination, item, expected_sha256))
        args.output.mkdir(parents=True)
        records = []
        for source, destination, item, expected_sha256 in prepared:
            target = args.output / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = copy_exclusive_and_hash(source, target)
            if digest != expected_sha256:
                raise ValueError("源文件内容与 allowlist 指纹不一致")
            records.append(
                {
                    "artifact_id": "pub_" + hashlib.sha256(destination.encode()).hexdigest()[:12],
                    "destination": destination,
                    "sha256": digest,
                    "size": size,
                    "source_category": item.get("source_category", "unspecified"),
                    "rights_status": "approved",
                    "taint": "publishable",
                }
            )
        artifact_set_hash = hashlib.sha256(
            json.dumps(
                {item["destination"]: item["sha256"] for item in records},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        release_manifest = {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "artifacts": records,
            "artifact_set_hash": artifact_set_hash,
            "scan_policy": "redaction_v1_fail_closed",
            "approved": True,
            "note": "No private source paths or matched values are stored in this manifest.",
        }
        (args.output / "RELEASE_MANIFEST.json").write_text(
            json.dumps(release_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        scan = run_scan(args.output, load_custom_terms(args.custom_terms))
        if not scan["safe_to_publish"]:
            release_manifest["approved"] = False
            (args.output / "RELEASE_MANIFEST.json").write_text(
                json.dumps(release_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (args.output / "BLOCKED.txt").write_text("Release gate failed. Do not publish.\n", encoding="utf-8")
            print("发布阻断：发现敏感规则命中或无法扫描的格式。输出目录保留供本地审查，不得发布。", file=sys.stderr)
            print(json.dumps(scan["summary"], ensure_ascii=False), file=sys.stderr)
            return 1
        print(f"发布门通过：{args.output}（{len(records)} 个允许文件）")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        try:
            if args.output.exists() and args.output.is_dir():
                (args.output / "INCOMPLETE.txt").write_text("Release build incomplete. Do not publish.\n", encoding="utf-8")
        except OSError:
            pass
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
