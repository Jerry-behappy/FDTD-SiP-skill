#!/usr/bin/env python3
"""Shared stdlib helpers for auditable Lumerical project artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


P0_SUCCESS_MARKER = "simulation completed successfully"
_H5_REFERENCE = re.compile(
    rb"(?<![A-Za-z0-9_.-])"
    rb"(?P<relative>[A-Za-z0-9_.-]+g[0-9]+_[0-9]+[\\/][A-Za-z0-9_.-]+_output[.]h5)"
    rb"(?![A-Za-z0-9_.-])"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest().upper()


def is_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def display_path(path: Path, root: Path | None = None) -> str:
    resolved = path.resolve()
    if root is not None:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return str(resolved)


def file_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": display_path(resolved, root),
        "bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "sha256": sha256_file(resolved),
    }


def atomic_write_json(path: Path, payload: Any) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def p0_log_succeeded(path: Path) -> bool:
    if not is_nonempty_file(path):
        return False
    text = path.read_text(encoding="utf-8", errors="replace").casefold()
    return P0_SUCCESS_MARKER in text


def deterministic_sidecar(fsp: Path) -> Path:
    return fsp.parent / fsp.stem / f"{fsp.stem}_output.h5"


def embedded_h5_relatives(
    fsp: Path, chunk_size: int = 1024 * 1024, overlap: int = 4096
) -> list[Path]:
    """Find native GPU relative H5 references without loading the whole FSP."""

    found: list[Path] = []
    tail = b""
    with fsp.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            data = tail + chunk
            for match in _H5_REFERENCE.finditer(data):
                raw = match.group("relative").decode("ascii").replace("\\", "/")
                relative = Path(*raw.split("/"))
                if relative not in found:
                    found.append(relative)
            tail = data[-overlap:]
    return found


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            seen.add(key)
            unique.append(path.resolve())
    return unique


def candidate_h5_paths(fsp: Path, explicit_h5: Path | None = None) -> list[Path]:
    if explicit_h5 is not None:
        return [explicit_h5.resolve()]

    deterministic = deterministic_sidecar(fsp)
    if deterministic.exists():
        return [deterministic.resolve()]
    if not fsp.is_file():
        return []
    return unique_paths(fsp.parent / item for item in embedded_h5_relatives(fsp))
