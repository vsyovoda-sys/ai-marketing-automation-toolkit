#!/usr/bin/env python3
"""Plan and archive cleanup candidates without deleting or moving originals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "Caches", "DerivedData"}
CANDIDATE_RULES = {
    "office_lock": re.compile(r"^~\$"),
    "finder_metadata": re.compile(r"^\.DS_Store$"),
    "temporary_or_backup": re.compile(r"(?i)(?:\.tmp$|\.temp$|\.bak$|\.old$|~$|backup|副本|复制品)"),
    "installer": re.compile(r"(?i)\.(?:dmg|pkg)$"),
    "named_copy": re.compile(r"(?i)(?: \(\d+\)|_copy| copy|副本)(?=\.[^.]+$)"),
}

CATEGORIES = {
    "文档": {".md", ".txt", ".doc", ".docx", ".pdf", ".rtf"},
    "表格": {".csv", ".tsv", ".xls", ".xlsx", ".xlsm", ".numbers"},
    "演示": {".ppt", ".pptx", ".key"},
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".psd", ".ai"},
    "音视频": {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mp3", ".wav", ".m4a", ".aac", ".flac"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"},
    "安装包": {".dmg", ".pkg"},
    "代码": {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".html", ".css", ".sql", ".json", ".yaml", ".yml"},
    "电子书": {".epub", ".mobi", ".azw", ".azw3"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_labels(name: str) -> list[str]:
    return [label for label, pattern in CANDIDATE_RULES.items() if pattern.search(name)]


def category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, extensions in CATEGORIES.items():
        if suffix in extensions:
            return category
    return "其他"


def iter_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            path = Path(current) / name
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and not path.is_symlink():
                yield path, info


def make_plan(root: Path, hash_duplicates: bool, max_hash_bytes: int) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("root 必须是存在的文件夹")
    candidates = []
    cloud_placeholders = []
    duplicate_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    total = 0
    for path, info in iter_files(root):
        total += 1
        relative = path.relative_to(root).as_posix()
        item = {
            "path": relative,
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "device": info.st_dev,
            "inode": info.st_ino,
        }
        allocated = getattr(info, "st_blocks", 0) * 512
        labels = candidate_labels(path.name)
        if labels:
            candidate = {**item, "reasons": labels, "sha256": None}
            if allocated > 0 and 0 <= info.st_size <= max_hash_bytes:
                try:
                    candidate["sha256"] = sha256_file(path)
                except OSError:
                    pass
            candidates.append(candidate)
        if info.st_size > 0 and allocated == 0:
            cloud_placeholders.append({**item, "reason": "dataless_placeholder"})
        if hash_duplicates and 0 < info.st_size <= max_hash_bytes and allocated > 0:
            try:
                digest = sha256_file(path)
            except OSError:
                continue
            duplicate_groups[digest].append(item)
    duplicates = [
        {"sha256": digest, "files": items, "count": len(items), "size_each": items[0]["size"]}
        for digest, items in duplicate_groups.items()
        if len(items) > 1
    ]
    return {
        "version": "1.0",
        "created_at": utc_now(),
        "root": str(root),
        "policy": "plan-and-copy-only; never delete or move originals",
        "summary": {
            "files": total,
            "cleanup_candidates": len(candidates),
            "cloud_placeholders": len(cloud_placeholders),
            "exact_duplicate_groups": len(duplicates),
        },
        "cleanup_candidates": candidates,
        "cloud_placeholders": cloud_placeholders,
        "exact_duplicates": sorted(duplicates, key=lambda item: (-item["count"], -item["size_each"])),
        "warnings": [
            "候选不代表应该删除。安装包、备份和重复文件可能仍承担归档职责。",
            "默认不读取云端占位文件内容；下载应单独排队并记录。",
            "归档命令只复制候选，原文件原地保留。",
        ],
    }


def safe_archive_name(relative: str, index: int) -> str:
    name = Path(relative).name or "unnamed"
    digest = hashlib.sha256(relative.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"candidates/{index:05d}_{digest}_{name}"


def bundle(plan_path: Path, output: Path, max_total_bytes: int, reasons: set[str] | None = None) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    root = Path(plan["root"]).resolve()
    candidates = plan.get("cleanup_candidates", [])
    if reasons:
        candidates = [item for item in candidates if reasons.intersection(item.get("reasons", []))]
    if output.exists():
        raise ValueError("输出归档已存在，拒绝覆盖")
    copied = []
    skipped = []
    total = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for index, item in enumerate(candidates, start=1):
            relative = item["path"]
            source = (root / relative).resolve()
            try:
                source.relative_to(root)
            except ValueError:
                skipped.append({"path": relative, "reason": "path_escape"})
                continue
            if not source.is_file() or source.is_symlink():
                skipped.append({"path": relative, "reason": "missing_or_not_regular"})
                continue
            current = source.stat()
            planned_identity = (item.get("device"), item.get("inode"), item.get("size"), item.get("mtime_ns"))
            current_identity = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
            if planned_identity != current_identity:
                skipped.append({"path": relative, "reason": "changed_since_plan"})
                continue
            if not item.get("sha256"):
                skipped.append({"path": relative, "reason": "missing_planned_hash"})
                continue
            try:
                before_hash = sha256_file(source)
            except OSError:
                skipped.append({"path": relative, "reason": "read_failed_or_cloud_not_downloaded"})
                continue
            if before_hash != item["sha256"]:
                skipped.append({"path": relative, "reason": "hash_changed_since_plan"})
                continue
            size = current.st_size
            if total + size > max_total_bytes:
                skipped.append({"path": relative, "reason": "archive_size_cap"})
                continue
            archive_name = safe_archive_name(relative, index)
            try:
                archive.write(source, archive_name)
            except OSError:
                skipped.append({"path": relative, "reason": "read_failed_or_cloud_not_downloaded"})
                continue
            after = source.stat()
            after_hash = sha256_file(source)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != current_identity or after_hash != before_hash:
                archive.writestr("BUNDLE_INVALID.txt", "A source changed while bundling. Do not use this archive.\n")
                raise ValueError("源文件在打包过程中变化；归档已标记无效")
            copied.append({"source": relative, "archive": archive_name, "size": size, "sha256": before_hash})
            total += size
        manifest = {
            "created_at": utc_now(),
            "policy": "copies only; originals were not moved or deleted",
            "selected_reasons": sorted(reasons or []),
            "copied": copied,
            "skipped": skipped,
            "total_bytes": total,
        }
        archive.writestr("MANIFEST.private.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"已复制打包 {len(copied)} 个候选；跳过 {len(skipped)} 个。原文件未移动、未删除。")
    print(f"归档：{output}")
    return 0


def organize_loose(
    root: Path,
    destination_name: str,
    min_age_days: int,
    include_cloud: bool,
    apply_moves: bool,
    manifest_path: Path,
) -> int:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("root 必须是文件夹")
    destination_root = root / destination_name
    cutoff = datetime.now(timezone.utc).timestamp() - min_age_days * 86400
    moves = []
    skipped = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.is_symlink() or path.name.startswith("."):
            continue
        info = path.stat()
        if info.st_mtime > cutoff:
            skipped.append({"name": path.name, "reason": "newer_than_cutoff"})
            continue
        if candidate_labels(path.name):
            skipped.append({"name": path.name, "reason": "cleanup_candidate_kept_in_place"})
            continue
        if info.st_size == 0:
            skipped.append({"name": path.name, "reason": "zero_byte_review_first"})
            continue
        allocated = getattr(info, "st_blocks", 0) * 512
        if info.st_size > 0 and allocated == 0 and not include_cloud:
            skipped.append({"name": path.name, "reason": "cloud_placeholder"})
            continue
        category = category_for(path)
        destination = destination_root / category / path.name
        if destination.exists():
            digest = hashlib.sha256(path.name.encode("utf-8", errors="ignore")).hexdigest()[:8]
            destination = destination.with_name(f"{destination.stem}_{digest}{destination.suffix}")
        moves.append(
            {
                "source": path.name,
                "destination": destination.relative_to(root).as_posix(),
                "category": category,
                "size": info.st_size,
                "mtime": int(info.st_mtime),
                "cloud_placeholder": info.st_size > 0 and allocated == 0,
            }
        )
    if manifest_path.exists():
        raise ValueError("manifest 已存在，拒绝覆盖")
    manifest = {
        "version": "1.0",
        "created_at": utc_now(),
        "root": str(root),
        "destination": destination_name,
        "policy": "top-level files only; no delete; no overwrite; cleanup candidates remain in place",
        "applied": apply_moves,
        "moves": moves,
        "skipped": skipped,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not apply_moves:
        print(f"整理预览：{len(moves)} 个；跳过 {len(skipped)} 个。未移动、未删除。")
        print(f"manifest：{manifest_path}")
        return 0
    moved = 0
    for item in moves:
        source = root / item["source"]
        destination = root / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_file() or destination.exists():
            continue
        source.rename(destination)
        moved += 1
    print(f"已整理移动 {moved} 个顶层文件；未删除、未覆盖任何文件。")
    print(f"回溯清单：{manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="非删除式本机整理与清理候选归档")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="只生成整理计划")
    plan_parser.add_argument("root", type=Path)
    plan_parser.add_argument("--output", required=True, type=Path)
    plan_parser.add_argument("--hash-duplicates", action="store_true", help="会读取文件内容，可能触发云端下载")
    plan_parser.add_argument("--max-hash-mb", type=int, default=256)
    bundle_parser = subparsers.add_parser("bundle", help="复制候选到 ZIP，绝不删除原文件")
    bundle_parser.add_argument("plan", type=Path)
    bundle_parser.add_argument("--output", required=True, type=Path)
    bundle_parser.add_argument("--max-total-gb", type=float, default=10.0)
    bundle_parser.add_argument("--reason", action="append", choices=sorted(CANDIDATE_RULES), help="只复制指定类别；可重复")
    organize_parser = subparsers.add_parser("organize", help="按类型整理顶层散落文件，不删除、不覆盖")
    organize_parser.add_argument("root", type=Path)
    organize_parser.add_argument("--destination", default="已整理")
    organize_parser.add_argument("--min-age-days", type=int, default=30)
    organize_parser.add_argument("--include-cloud", action="store_true", help="允许移动云端占位的目录项，不读取内容")
    organize_parser.add_argument("--apply", action="store_true", help="默认仅预览；指定后执行移动")
    organize_parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            if args.output.exists():
                raise ValueError("计划文件已存在，拒绝覆盖")
            report = make_plan(args.root, args.hash_duplicates, args.max_hash_mb * 1024 * 1024)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report["summary"], ensure_ascii=False))
            print(f"计划：{args.output}")
            print("未移动、未删除任何原文件。")
            return 0
        if args.command == "bundle":
            return bundle(args.plan, args.output, int(args.max_total_gb * 1024**3), set(args.reason or []))
        return organize_loose(
            args.root,
            args.destination,
            args.min_age_days,
            args.include_cloud,
            args.apply,
            args.manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
