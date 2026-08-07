#!/usr/bin/env python3
"""将 FSP 与其准确相对路径的 GPU H5 sidecar 原子归档。

目标目录必须不存在。脚本先复制到同级临时目录，校验哈希并写入
``bundle_manifest.json``，再把完整目录原子重命名。脚本不会打开或修改源
FSP/H5。

可复用用途：在清理 Optimization 目录前，把可读 candidate 或 best-solution
FSP 与其准确相对 H5 sidecar 一起保存。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from _artifact_utils import (
    atomic_write_json,
    candidate_h5_paths,
    file_record,
    is_nonempty_file,
    p0_log_succeeded,
    sha256_file,
    utc_now,
)


def safe_relative(path: Path) -> Path:
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"H5 relative path escapes bundle root: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 FSP 与其引用的 GPU H5 复制为一个原子结果包。"
    )
    parser.add_argument("fsp", type=Path, help="源 FSP 文件")
    parser.add_argument("destination", type=Path, help="目标结果包目录")
    parser.add_argument("--h5", type=Path, help="显式指定源 H5")
    parser.add_argument(
        "--h5-relative",
        type=Path,
        help="显式 H5 位于 FSP 父目录外时必须提供其目标相对路径",
    )
    parser.add_argument("--p0-log", type=Path, help="可选 p0 日志")
    parser.add_argument("--require-success-log", action="store_true", help="要求成功 p0 日志")
    parser.add_argument("--dry-run", action="store_true", help="只检查计划，不复制文件")
    args = parser.parse_args()

    fsp = args.fsp.resolve()
    destination = args.destination.resolve()
    explicit_h5 = args.h5.resolve() if args.h5 else None
    p0_log = args.p0_log.resolve() if args.p0_log else None

    if not is_nonempty_file(fsp):
        raise FileNotFoundError(f"FSP is missing or empty: {fsp}")
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")

    h5_candidates = candidate_h5_paths(fsp, explicit_h5)
    valid_h5 = [path for path in h5_candidates if is_nonempty_file(path)]
    if len(valid_h5) != 1:
        raise RuntimeError(
            f"expected one nonempty H5 sidecar, found {len(valid_h5)}: {h5_candidates}"
        )
    source_h5 = valid_h5[0]

    if args.h5_relative:
        h5_relative = safe_relative(args.h5_relative)
    else:
        try:
            h5_relative = safe_relative(source_h5.relative_to(fsp.parent))
        except ValueError as exc:
            raise ValueError(
                "explicit H5 is outside the FSP parent; provide --h5-relative"
            ) from exc

    if args.require_success_log:
        if p0_log is None:
            p0_log = fsp.with_name(f"{fsp.stem}_p0.log")
        if not p0_log_succeeded(p0_log):
            raise RuntimeError(f"p0 success marker is missing: {p0_log}")

    plan = {
        "schema": "fdtd-sip-preserved-result-bundle/v1",
        "created_utc": utc_now(),
        "source_fsp": file_record(fsp),
        "source_h5": file_record(source_h5),
        "h5_relative": h5_relative.as_posix(),
        "source_p0_log": file_record(p0_log) if p0_log and p0_log.is_file() else None,
        "destination": str(destination),
        "source_modified": False,
    }
    if args.dry_run:
        import json

        print(json.dumps({**plan, "dry_run": True}, ensure_ascii=False, indent=2))
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.copying.{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"stale temporary destination exists: {temporary}")
    temporary.mkdir()
    try:
        copied_fsp = temporary / fsp.name
        shutil.copy2(fsp, copied_fsp)
        copied_h5 = temporary / h5_relative
        if h5_relative.parent == Path("."):
            shutil.copy2(source_h5, copied_h5)
            sidecar_root = copied_h5.parent
            sidecar_files = [copied_h5]
        else:
            sidecar_root = temporary / h5_relative.parent
            sidecar_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_h5.parent, sidecar_root)
            sidecar_files = [
                path for path in sorted(sidecar_root.rglob("*")) if path.is_file()
            ]
        copied_log = None
        if p0_log and p0_log.is_file():
            copied_log = temporary / p0_log.name
            shutil.copy2(p0_log, copied_log)

        if sha256_file(copied_fsp) != sha256_file(fsp):
            raise RuntimeError("copied FSP SHA-256 mismatch")
        if sha256_file(copied_h5) != sha256_file(source_h5):
            raise RuntimeError("copied H5 SHA-256 mismatch")
        if copied_log and sha256_file(copied_log) != sha256_file(p0_log):
            raise RuntimeError("copied p0 log SHA-256 mismatch")

        manifest = {
            **plan,
            "preserved_fsp": file_record(copied_fsp, temporary),
            "preserved_h5": file_record(copied_h5, temporary),
            "preserved_sidecar_entries": [
                file_record(path, temporary) for path in sidecar_files
            ],
            "preserved_p0_log": (
                file_record(copied_log, temporary) if copied_log else None
            ),
            "status": "passed",
        }
        atomic_write_json(temporary / "bundle_manifest.json", manifest)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    print(destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
