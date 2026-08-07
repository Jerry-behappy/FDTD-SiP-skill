#!/usr/bin/env python3
"""Audit one Lumerical FSP, GPU H5 sidecar, and optional p0 log bundle.

The script never opens Lumerical, runs a solver, saves an FSP, or changes the
input bundle. It checks the deterministic same-name sidecar first and falls
back to native relative H5 references embedded in the FSP.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _artifact_utils import (
    atomic_write_json,
    candidate_h5_paths,
    deterministic_sidecar,
    file_record,
    is_nonempty_file,
    p0_log_succeeded,
    sha256_file,
    utc_now,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit an FSP/H5/p0 result bundle without Lumerical."
    )
    parser.add_argument("fsp", type=Path)
    parser.add_argument("--h5", type=Path, help="Explicit sidecar H5 path")
    parser.add_argument("--p0-log", type=Path, help="Explicit p0 log path")
    parser.add_argument("--require-log", action="store_true")
    parser.add_argument("--expect-fsp-sha256")
    parser.add_argument("--expect-h5-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    fsp = args.fsp.resolve()
    explicit_h5 = args.h5.resolve() if args.h5 else None
    inferred_log = fsp.with_name(f"{fsp.stem}_p0.log")
    p0_log = args.p0_log.resolve() if args.p0_log else inferred_log

    h5_candidates = candidate_h5_paths(fsp, explicit_h5) if fsp.is_file() else []
    valid_h5 = [path for path in h5_candidates if is_nonempty_file(path)]
    selected_h5 = valid_h5[0] if len(valid_h5) == 1 else None
    fsp_ok = is_nonempty_file(fsp)
    log_present = is_nonempty_file(p0_log)
    log_success = p0_log_succeeded(p0_log)

    checks = {
        "fsp_nonempty": fsp_ok,
        "unique_nonempty_h5": selected_h5 is not None,
        "p0_log_required": args.require_log,
        "p0_log_success": log_success if args.require_log else None,
        "fsp_sha256_matches": (
            fsp_ok
            and sha256_file(fsp).casefold() == args.expect_fsp_sha256.casefold()
            if args.expect_fsp_sha256
            else None
        ),
        "h5_sha256_matches": (
            selected_h5 is not None
            and sha256_file(selected_h5).casefold()
            == args.expect_h5_sha256.casefold()
            if args.expect_h5_sha256
            else None
        ),
    }
    required = [checks["fsp_nonempty"], checks["unique_nonempty_h5"]]
    if args.require_log:
        required.append(bool(checks["p0_log_success"]))
    if args.expect_fsp_sha256:
        required.append(bool(checks["fsp_sha256_matches"]))
    if args.expect_h5_sha256:
        required.append(bool(checks["h5_sha256_matches"]))
    passed = all(required)

    payload = {
        "schema": "fdtd-sip-result-bundle-audit/v1",
        "created_utc": utc_now(),
        "status": "passed" if passed else "failed",
        "read_only": True,
        "solver_called": False,
        "switchtolayout_called": False,
        "fsp": file_record(fsp) if fsp_ok else {"path": str(fsp), "exists": False},
        "deterministic_h5": str(deterministic_sidecar(fsp)),
        "h5_candidates": [
            file_record(path) if path.is_file() else {"path": str(path), "exists": False}
            for path in h5_candidates
        ],
        "selected_h5": file_record(selected_h5) if selected_h5 else None,
        "p0_log": {
            "path": str(p0_log),
            "present": log_present,
            "success_marker": log_success,
        },
        "checks": checks,
    }

    if args.output:
        atomic_write_json(args.output, payload)
        print(args.output.resolve())
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if args.strict and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
