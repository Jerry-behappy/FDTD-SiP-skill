#!/usr/bin/env python3
"""Build a deterministic SHA-256 manifest for files in a project.

This script is read-only except for the optional JSON output. Paths are
resolved against ``--root`` and must remain inside it unless
``--allow-outside-root`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from _artifact_utils import atomic_write_json, file_record, utc_now


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def expand_path(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.rglob("*") if item.is_file())
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a JSON SHA-256 manifest without modifying inputs."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Repeatable glob matched against root-relative POSIX paths",
    )
    parser.add_argument("--allow-outside-root", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero when inputs are missing or outside root",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    requested = [item if item.is_absolute() else root / item for item in args.paths]
    output = args.output.resolve() if args.output else None
    files: list[Path] = []
    missing: list[str] = []
    outside_root: list[str] = []

    for requested_path in requested:
        resolved = requested_path.resolve()
        if not resolved.exists():
            missing.append(str(resolved))
            continue
        if not args.allow_outside_root and not is_within(resolved, root):
            outside_root.append(str(resolved))
            continue
        files.extend(expand_path(resolved))

    deduplicated = {str(path.resolve()).casefold(): path.resolve() for path in files}
    selected: list[Path] = []
    for path in sorted(deduplicated.values(), key=lambda item: str(item).casefold()):
        if output is not None and path == output:
            continue
        if not args.allow_outside_root and not is_within(path, root):
            outside_root.append(str(path))
            continue
        relative = (
            path.relative_to(root).as_posix() if is_within(path, root) else str(path)
        )
        if any(fnmatch.fnmatch(relative, pattern) for pattern in args.exclude):
            continue
        selected.append(path)

    payload = {
        "schema": "fdtd-sip-sha256-manifest/v1",
        "created_utc": utc_now(),
        "root": str(root),
        "read_only_inputs": True,
        "entries": [file_record(path, root) for path in selected],
        "missing": missing,
        "outside_root_rejected": outside_root,
        "summary": {
            "file_count": len(selected),
            "total_bytes": sum(path.stat().st_size for path in selected),
            "missing_count": len(missing),
            "outside_root_rejected_count": len(outside_root),
        },
    }

    if output is not None:
        atomic_write_json(output, payload)
        print(output)
    else:
        import json

        print(json.dumps(payload, ensure_ascii=False, indent=2))

    failed = bool(missing or outside_root)
    return 2 if args.strict and failed else 0


if __name__ == "__main__":
    sys.exit(main())
