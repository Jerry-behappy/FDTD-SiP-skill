#!/usr/bin/env python3
"""Apply auditable Layout-only settings to FDTD, MODE/FDE, EME, or varFDTD.

Run as a PyLumerical MCP ``code_file`` with a JSON ``code_context``. Supported
operations are named-object settings, global source/monitor settings,
mode-expansion bindings, optional ``runsetup()``, readback, and an explicitly
named fresh save target. The worker refuses Analysis mode and never calls a
solver or ``switchtolayout()``.

Reusable role: configure solver regions, sources, ports, monitors, meshes, and
parameterized structure-group properties without copying project-specific
Python code into every simulation folder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _context() -> dict[str, Any]:
    value = globals().get("CODEX_CONTEXT")
    if not isinstance(value, dict):
        raise RuntimeError("CODEX_CONTEXT must be injected as a JSON object")
    return value


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return _jsonable(value.tolist())
        except Exception:
            pass
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _require_mapping(context: dict[str, Any], key: str) -> dict[str, Any]:
    value = context.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _require_array(context: dict[str, Any], key: str) -> list[Any]:
    value = context.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    return value


def _apply_named_settings(handle: Any, requests: list[Any]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError(f"named_settings[{index}] requires path")
        properties = request.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise ValueError(f"named_settings[{index}].properties must be a nonempty object")
        for property_name, value in properties.items():
            if not isinstance(property_name, str):
                raise ValueError(f"named_settings[{index}] property names must be strings")
            handle.setnamed(request["path"], property_name, value)
        applied.append(
            {
                "path": request["path"],
                "properties": sorted(str(name) for name in properties),
            }
        )
    return applied


def _apply_global(handle: Any, method_name: str, settings: dict[str, Any]) -> list[str]:
    method = getattr(handle, method_name)
    for property_name, value in settings.items():
        method(property_name, value)
    return sorted(settings)


def _readback_named(handle: Any, requests: list[Any]) -> list[dict[str, Any]]:
    readback: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError(f"readback_named[{index}] requires path")
        properties = request.get("properties", [])
        if not isinstance(properties, list) or not all(
            isinstance(item, str) for item in properties
        ):
            raise ValueError(f"readback_named[{index}].properties must be strings")
        item: dict[str, Any] = {"path": request["path"], "properties": {}}
        for property_name in properties:
            item["properties"][property_name] = _jsonable(
                handle.getnamed(request["path"], property_name)
            )
        readback.append(item)
    return readback


def main() -> None:
    context = _context()
    session = context.get("session")
    if not isinstance(session, str) or not session:
        raise ValueError("session is required")

    handle = _lum_get(session)
    initial_layout_mode = int(round(float(handle.layoutmode())))
    if initial_layout_mode != 1:
        raise RuntimeError(
            "Target must already be in Layout mode; this worker will not call switchtolayout()"
        )

    save_as_raw = context.get("save_as")
    source_raw = context.get("source_file")
    save_as: Path | None = None
    if save_as_raw is not None:
        if not isinstance(save_as_raw, str) or not save_as_raw:
            raise ValueError("save_as must be a nonempty path string")
        if not isinstance(source_raw, str) or not source_raw:
            raise ValueError("source_file is required whenever save_as is used")
        source = Path(source_raw)
        save_as = Path(save_as_raw)
        if _same_path(source, save_as):
            raise RuntimeError("save_as must differ from source_file")
        if save_as.exists() and not bool(context.get("allow_overwrite", False)):
            raise FileExistsError(f"save target already exists: {save_as}")
        save_as.parent.mkdir(parents=True, exist_ok=True)

    named_applied = _apply_named_settings(
        handle, _require_array(context, "named_settings")
    )
    global_source_applied = _apply_global(
        handle,
        "setglobalsource",
        _require_mapping(context, "global_source_settings"),
    )
    global_monitor_applied = _apply_global(
        handle,
        "setglobalmonitor",
        _require_mapping(context, "global_monitor_settings"),
    )

    bindings: list[dict[str, str]] = []
    for index, binding in enumerate(
        _require_array(context, "expansion_bindings"), start=1
    ):
        if not isinstance(binding, dict):
            raise ValueError(f"expansion_bindings[{index}] must be an object")
        expansion = binding.get("expansion")
        monitor = binding.get("monitor")
        if not isinstance(expansion, str) or not isinstance(monitor, str):
            raise ValueError(
                f"expansion_bindings[{index}] requires expansion and monitor"
            )
        handle.setexpansion(expansion, monitor)
        bindings.append({"expansion": expansion, "monitor": monitor})

    runsetup_called = bool(context.get("runsetup", False))
    if runsetup_called:
        handle.runsetup()

    readback = _readback_named(
        handle, _require_array(context, "readback_named")
    )

    save_called = save_as is not None
    if save_as is not None:
        handle.save(str(save_as))

    _lum_print_json(
        {
            "schema": "fdtd-sip-layout-configuration/v1",
            "session": session,
            "initial_layout_mode": initial_layout_mode,
            "final_layout_mode": int(round(float(handle.layoutmode()))),
            "named_settings": named_applied,
            "global_source_settings": global_source_applied,
            "global_monitor_settings": global_monitor_applied,
            "expansion_bindings": bindings,
            "runsetup_called": runsetup_called,
            "readback": readback,
            "save_called": save_called,
            "saved_as": str(save_as.resolve()) if save_as is not None else None,
            "solver_called": False,
            "switchtolayout_called": False,
        }
    )


main()
