#!/usr/bin/env python3
"""Atomically preserve an FSP with its exact relative GPU H5 sidecar.

The destination must not exist. The script copies through a temporary sibling,
verifies hashes, writes ``bundle_manifest.json``, and then atomically renames
the completed directory. It never opens or modifies the source FSP/H5.

Reusable role: preserve a readable candidate or best-solution FSP together
with the exact relative H5 sidecar before Optimization directories are cleaned.
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
        description="Copy an FSP and its referenced GPU H5 as one atomic bundle."
    )
    parser.add_argument("fsp", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--h5", type=Path, help="Explicit source H5")
    parser.add_argument(
        "--h5-relative",
        type=Path,
        help="Required when explicit H5 is outside the FSP parent",
    )
    parser.add_argument("--p0-log", type=Path)
    parser.add_argument("--require-success-log", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
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
