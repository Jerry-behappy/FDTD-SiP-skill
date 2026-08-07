#!/usr/bin/env python3
"""为项目文件生成确定性的 SHA-256 manifest。

除可选 JSON 输出外，本脚本只读。所有路径都相对 ``--root`` 解析；除非显式
提供 ``--allow-outside-root``，否则路径必须位于 root 内部。

可复用用途：为 pre-run、重开、归档和清理审计生成确定且机器可读的项目输入
与交付文件清单。
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
        description="在不修改输入文件的情况下生成 JSON SHA-256 manifest。"
    )
    parser.add_argument("paths", nargs="+", type=Path, help="文件或目录")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="项目根目录")
    parser.add_argument("--output", type=Path, help="JSON manifest 输出路径")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="按 root 相对 POSIX 路径匹配的可重复 glob",
    )
    parser.add_argument("--allow-outside-root", action="store_true", help="允许审计 root 外部文件")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="输入缺失或位于 root 外时返回非零退出码",
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
