#!/usr/bin/env python3
"""Small deterministic CSV profiler and duplicate-candidate generator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip().casefold()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value)
    return value


def stable_key(row: dict[str, str], fields: list[str]) -> str:
    joined = "\x1f".join(normalize(row.get(field, "")) for field in fields)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def profile(path: Path, key_fields: list[str]) -> dict[str, object]:
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise ValueError("CSV 没有表头")
    missing_fields = sorted(set(key_fields) - set(reader.fieldnames))
    if missing_fields:
        raise ValueError(f"稳定键字段不存在：{', '.join(missing_fields)}")
    rows = list(reader)
    null_counts = Counter()
    distinct: dict[str, set[str]] = {field: set() for field in reader.fieldnames}
    keys: dict[str, list[int]] = defaultdict(list)
    invalid_rows = []
    for index, row in enumerate(rows, start=2):
        if None in row:
            invalid_rows.append({"row": index, "reason": "extra_columns"})
        missing_columns = [field for field in reader.fieldnames if row.get(field) is None]
        if missing_columns:
            invalid_rows.append({"row": index, "reason": "missing_columns", "count": len(missing_columns)})
        for field in reader.fieldnames:
            value = normalize(row.get(field, ""))
            if not value:
                null_counts[field] += 1
            else:
                distinct[field].add(value)
        if key_fields:
            if any(not normalize(row.get(field)) for field in key_fields):
                invalid_rows.append({"row": index, "reason": "empty_stable_key_component"})
            else:
                keys[stable_key(row, key_fields)].append(index)
    duplicates = [
        {"stable_key": key, "rows": line_numbers, "count": len(line_numbers)}
        for key, line_numbers in sorted(keys.items())
        if len(line_numbers) > 1 and key_fields
    ]
    return {
        "source": {"name": path.name, "sha256": hashlib.sha256(data).hexdigest()},
        "rows": len(rows),
        "columns": reader.fieldnames,
        "nulls": {field: null_counts[field] for field in reader.fieldnames},
        "distinct": {field: len(distinct[field]) for field in reader.fieldnames},
        "stable_key_fields": key_fields,
        "duplicate_candidates": duplicates,
        "invalid_rows": invalid_rows,
        "notes": [
            "重复项只是候选，不自动删除或合并。",
            "缺失值不会被 AI 猜测补全。",
            "业务评分真值与阈值应在领域 Loop 中单独校准。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV 质量画像与稳定键重复候选")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--key", action="append", default=[], help="可重复；共同组成稳定键")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = profile(args.csv_file, args.key)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"已写入：{args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
