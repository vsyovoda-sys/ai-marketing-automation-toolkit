#!/usr/bin/env python3
"""Validate one or more public workflow JSON definitions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workflow_core import WorkflowError, load_json, validate_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 AI Loop 工作流契约")
    parser.add_argument("workflow", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.workflow:
        try:
            errors = validate_workflow(load_json(path))
        except WorkflowError as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
