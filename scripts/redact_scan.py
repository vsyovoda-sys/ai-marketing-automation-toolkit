#!/usr/bin/env python3
"""Fail-closed secret and identity scan without echoing matched values."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


TEXT_EXTENSIONS = {
    ".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".py", ".js", ".ts", ".tsx", ".jsx", ".sh",
    ".zsh", ".html", ".css", ".xml", ".srt", ".vtt", ".sql",
}
CONTAINER_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".xlsm", ".zip"}
IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
# Finder metadata is neither a publishable artifact nor source content. It is
# ignored rather than treated as an uninspectable text file.
IGNORE_FILE_NAMES = {".DS_Store"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_CONTAINER_MEMBERS = 5000
MAX_CONTAINER_EXPANDED_BYTES = 100 * 1024 * 1024


RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "generic_secret_assignment": re.compile(
        r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|cookie)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+\-=]{8,}"
    ),
    "provider_token": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    "email": re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"),
    "cn_id": re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?!\d)"),
    "absolute_user_path": re.compile(r"/(?:Users|home)/[^/\s]+/"),
    "sensitive_url_parameter": re.compile(r"(?i)[?&](?:token|key|secret|auth|signature|code)=[^&#\s]+"),
    "environment_file_reference": re.compile(r"(?i)(?:^|[/\\])\.env(?:[.\w-]*)?(?:$|[/\\])"),
}


@dataclass(frozen=True)
class Finding:
    file_id: str
    location: str
    rule: str
    line: int | None


def file_id(relative: str) -> str:
    return "file_" + hashlib.sha256(relative.encode("utf-8", errors="ignore")).hexdigest()[:12]


def scan_text(text: str, relative: str, location: str = "content", custom_terms: Iterable[str] = ()) -> list[Finding]:
    findings: list[Finding] = []
    for rule, pattern in RULES.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(Finding(file_id(relative), location, rule, line))
    lowered = text.casefold()
    for index, term in enumerate(custom_terms, start=1):
        if not term:
            continue
        start = 0
        target = term.casefold()
        while True:
            position = lowered.find(target, start)
            if position < 0:
                break
            findings.append(Finding(file_id(relative), location, f"custom_term_{index}", text.count("\n", 0, position) + 1))
            start = position + max(1, len(target))
    return findings


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def scan_file(path: Path, root: Path, custom_terms: list[str]) -> tuple[list[Finding], list[dict[str, str]]]:
    relative = path.relative_to(root).as_posix()
    findings = scan_text(relative, relative, "filename", custom_terms)
    unknown: list[dict[str, str]] = []
    if path.is_symlink():
        return findings, [{"file_id": file_id(relative), "reason": "symlink_not_scanned"}]
    try:
        size = path.stat().st_size
    except OSError:
        return findings, [{"file_id": file_id(relative), "reason": "stat_failed"}]
    if size > MAX_FILE_BYTES:
        return findings, [{"file_id": file_id(relative), "reason": "file_too_large"}]
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS or not suffix:
        try:
            data = path.read_bytes()
        except OSError:
            return findings, [{"file_id": file_id(relative), "reason": "read_failed"}]
        if b"\x00" in data:
            return findings, [{"file_id": file_id(relative), "reason": "binary_content_in_text_extension"}]
        text = data.decode("utf-8", errors="replace")
        if "\ufffd" in text:
            unknown.append({"file_id": file_id(relative), "reason": "undecodable_text_bytes"})
        findings.extend(scan_text(text, relative, "content", custom_terms))
        return findings, unknown
    if suffix in CONTAINER_EXTENSIONS:
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) > MAX_CONTAINER_MEMBERS:
                    return findings, [{"file_id": file_id(relative), "reason": "container_member_limit"}]
                expanded = sum(max(0, info.file_size) for info in members)
                if expanded > MAX_CONTAINER_EXPANDED_BYTES:
                    return findings, [{"file_id": file_id(relative), "reason": "container_expanded_size_limit"}]
                for info in members:
                    member = info.filename
                    member_location = f"container:{file_id(member)}"
                    findings.extend(scan_text(member, relative, member_location, custom_terms))
                    if not safe_member(member):
                        unknown.append({"file_id": file_id(relative), "reason": "unsafe_container_member"})
                        continue
                    if info.is_dir() or info.file_size > MAX_MEMBER_BYTES:
                        if info.file_size > MAX_MEMBER_BYTES:
                            unknown.append({"file_id": file_id(relative), "reason": "container_member_too_large"})
                        continue
                    member_suffix = PurePosixPath(member).suffix.lower()
                    if member_suffix in CONTAINER_EXTENSIONS:
                        unknown.append({"file_id": file_id(relative), "reason": "nested_container_requires_separate_scan"})
                        continue
                    if member_suffix not in TEXT_EXTENSIONS and member_suffix not in {".xml", ".rels"}:
                        unknown.append(
                            {"file_id": file_id(relative), "reason": f"unsupported_container_member:{member_suffix or '[none]'}"}
                        )
                        continue
                    data = archive.read(info)
                    text = data.decode("utf-8", errors="replace")
                    findings.extend(scan_text(text, relative, member_location, custom_terms))
        except (OSError, zipfile.BadZipFile, RuntimeError):
            unknown.append({"file_id": file_id(relative), "reason": "unreadable_or_encrypted_container"})
        return findings, unknown
    unknown.append({"file_id": file_id(relative), "reason": f"unsupported_extension:{suffix or '[none]'}"})
    return findings, unknown


def collect_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = []
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.is_file() and path.name not in IGNORE_FILE_NAMES and not path.is_symlink():
            files.append(path)
    return sorted(files)


def load_custom_terms(path: Path | None) -> list[str]:
    if path is None:
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            terms.append(value)
    return terms


def run_scan(root: Path, custom_terms: list[str]) -> dict[str, object]:
    original_root = root.expanduser().absolute()
    if original_root.is_symlink():
        return {
            "summary": {"files": 0, "findings": 0, "unknown": 1},
            "findings": [],
            "unknown": [{"file_id": file_id(str(original_root)), "reason": "root_symlink_not_scanned"}],
            "safe_to_publish": False,
        }
    root = original_root.resolve()
    if not root.exists():
        return {
            "summary": {"files": 0, "findings": 0, "unknown": 1},
            "findings": [],
            "unknown": [{"file_id": file_id(str(root)), "reason": "root_not_found"}],
            "safe_to_publish": False,
        }
    base = root.parent if root.is_file() else root
    findings: list[Finding] = []
    unknown: list[dict[str, str]] = []
    files = collect_files(root)
    if not files:
        unknown.append({"file_id": file_id(str(root)), "reason": "no_files_to_scan"})
    for path in files:
        file_findings, file_unknown = scan_file(path, base, custom_terms)
        findings.extend(file_findings)
        unknown.extend(file_unknown)
    deduped = sorted(
        {finding for finding in findings},
        key=lambda item: (item.file_id, item.location, item.rule, item.line or 0),
    )
    return {
        "summary": {"files": len(files), "findings": len(deduped), "unknown": len(unknown)},
        "findings": [asdict(item) for item in deduped],
        "unknown": unknown,
        "safe_to_publish": not deduped and not unknown,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="不回显命中值的发布前敏感信息扫描")
    parser.add_argument("root", type=Path)
    parser.add_argument("--custom-terms", type=Path, help="每行一个私有专名；文件本身不要加入公开仓库")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--allow-unknown", action="store_true", help="仅用于私有盘点；公开发布禁止使用")
    args = parser.parse_args()
    try:
        report = run_scan(args.root, load_custom_terms(args.custom_terms))
    except (OSError, UnicodeError) as exc:
        print(f"扫描失败：{type(exc).__name__}", file=sys.stderr)
        return 2
    if args.allow_unknown and not report["findings"]:
        report["safe_to_publish"] = True
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
        print(f"报告已写入：{args.report}")
    else:
        print(rendered)
    return 0 if report["safe_to_publish"] else 1


if __name__ == "__main__":
    sys.exit(main())
