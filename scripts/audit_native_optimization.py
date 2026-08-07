#!/usr/bin/env python3
"""根据文件系统产物审计原生 Lumerical Optimization 各代完整性。

完整 candidate 必须同时具有非空 FSP、成功 p0 日志和一个非空的引用 GPU H5
sidecar。本脚本只读审计文件系统，不宣称原生 FOM/history 可用，也不会启动或
连接 Lumerical。

可复用用途：按代只统计完整的 FSP+p0+H5 candidate 结果包，避免反复打开大型
FSP 或启动求解器。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _artifact_utils import (
    atomic_write_json,
    candidate_h5_paths,
    is_nonempty_file,
    p0_log_succeeded,
    utc_now,
)


def candidate_record(fsp: Path, summary_only: bool) -> dict:
    p0_log = fsp.with_name(f"{fsp.stem}_p0.log")
    h5_candidates = candidate_h5_paths(fsp)
    valid_h5 = [path for path in h5_candidates if is_nonempty_file(path)]
    fsp_ok = is_nonempty_file(fsp)
    log_ok = p0_log_succeeded(p0_log)
    h5_ok = len(valid_h5) == 1
    record = {
        "candidate": fsp.name,
        "complete_bundle": fsp_ok and log_ok and h5_ok,
        "fsp_nonempty": fsp_ok,
        "p0_log_success": log_ok,
        "unique_nonempty_h5": h5_ok,
    }
    if not summary_only:
        record.update(
            {
                "fsp": str(fsp.resolve()),
                "p0_log": str(p0_log.resolve()),
                "h5_candidates": [str(path.resolve()) for path in h5_candidates],
                "valid_h5": [str(path.resolve()) for path in valid_h5],
            }
        )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="审计原生 Optimization candidate 结果包。"
    )
    parser.add_argument("working_fsp", type=Path, help="Optimization working FSP")
    parser.add_argument("--optimization-name", required=True, help="原生 Optimization 名称")
    parser.add_argument("--generation-size", type=int, required=True, help="每代 candidate 数")
    parser.add_argument("--maximum-generations", type=int, help="计划最大代数")
    parser.add_argument("--summary-only", action="store_true", help="只输出代际摘要")
    parser.add_argument("--output", type=Path, help="JSON 审计输出路径")
    parser.add_argument("--strict", action="store_true", help="发现不完整 candidate 时返回非零退出码")
    args = parser.parse_args()

    if args.generation_size <= 0:
        parser.error("--generation-size must be positive")
    if args.maximum_generations is not None and args.maximum_generations <= 0:
        parser.error("--maximum-generations must be positive")

    working = args.working_fsp.resolve()
    prefix = f"{working.stem}_{args.optimization_name}g"
    generation_pattern = re.compile(rf"^{re.escape(prefix)}(?P<number>[0-9]+)$")
    generation_dirs: list[tuple[int, Path]] = []
    if working.parent.is_dir():
        for path in working.parent.glob(prefix + "*"):
            match = generation_pattern.match(path.name)
            if path.is_dir() and match:
                generation_dirs.append((int(match.group("number")), path))

    generations = []
    for number, directory in sorted(generation_dirs):
        candidates = [
            candidate_record(fsp, args.summary_only)
            for fsp in sorted(directory.glob("*.fsp"))
        ]
        complete_bundles = sum(item["complete_bundle"] for item in candidates)
        generation_complete = (
            len(candidates) == args.generation_size
            and complete_bundles == args.generation_size
        )
        item = {
            "generation": number,
            "directory": str(directory.resolve()),
            "candidate_fsps": len(candidates),
            "complete_result_bundles": complete_bundles,
            "expected_candidates": args.generation_size,
            "complete": generation_complete,
        }
        if not args.summary_only:
            item["candidates"] = candidates
        generations.append(item)

    discovered_numbers = [item["generation"] for item in generations]
    expected_discovered = (
        list(range(1, max(discovered_numbers) + 1)) if discovered_numbers else []
    )
    contiguous = discovered_numbers == expected_discovered
    complete_generations = sum(item["complete"] for item in generations)
    all_discovered_complete = bool(generations) and complete_generations == len(generations)
    formal_complete = (
        args.maximum_generations is not None
        and contiguous
        and discovered_numbers == list(range(1, args.maximum_generations + 1))
        and all_discovered_complete
    )
    plan_complete = formal_complete if args.maximum_generations is not None else (
        contiguous and all_discovered_complete
    )
    passed = is_nonempty_file(working) and plan_complete

    payload = {
        "schema": "fdtd-sip-native-optimization-filesystem-audit/v1",
        "created_utc": utc_now(),
        "status": "passed" if passed else "incomplete",
        "read_only": True,
        "filesystem_only": True,
        "native_fom_or_history_verified": False,
        "solver_called": False,
        "switchtolayout_called": False,
        "working_fsp": str(working),
        "working_fsp_present": is_nonempty_file(working),
        "optimization_name": args.optimization_name,
        "generation_size": args.generation_size,
        "maximum_generations": args.maximum_generations,
        "generation_prefix": prefix,
        "generations": generations,
        "summary": {
            "discovered_generations": len(generations),
            "complete_generations": complete_generations,
            "highest_generation": max(discovered_numbers, default=0),
            "complete_result_bundles": sum(
                item["complete_result_bundles"] for item in generations
            ),
            "generation_numbers_contiguous_from_1": contiguous,
            "all_discovered_generations_complete": all_discovered_complete,
            "formal_plan_complete": formal_complete,
        },
    }

    if args.output:
        atomic_write_json(args.output, payload)
        print(args.output.resolve())
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if args.strict and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
