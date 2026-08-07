#!/usr/bin/env python3
"""创建原生 Lumerical Parameter Sweep 或 Optimization，但不启动运行。

通过 PyLumerical MCP 把本文件作为 ``code_file`` 执行，并提供
``code_context``。JSON context 包含原生 ``setsweep`` 设置，以及传给
``addsweepparameter`` 和 ``addsweepresult`` 的 parameter/result struct。
脚本保留 Lumerical 原生字段名，可复用于 FDTD、MODE、EME 和 varFDTD 工程。

本 worker 要求工程处于 Layout mode；可选替换前先枚举现有 analysis item；
永不调用 ``runsweep``/``emesweep``；仅保存到与不可变源文件不同的显式路径。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


SWEEP_TYPES = {"parameter_sweep": (0, "sweep"), "optimization": (1, "optimization")}


def _context() -> dict[str, Any]:
    value = globals().get("CODEX_CONTEXT")
    if not isinstance(value, dict):
        raise RuntimeError("CODEX_CONTEXT must be injected as a JSON object")
    return value


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _sweep_names(handle: Any) -> tuple[Any, list[str]]:
    raw = handle.getsweep()
    if isinstance(raw, str):
        names = [line.strip() for line in raw.replace(";", "\n").splitlines() if line.strip()]
        return raw, names
    if hasattr(raw, "tolist"):
        try:
            raw = raw.tolist()
        except Exception:
            pass
    if isinstance(raw, (list, tuple)):
        return raw, [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    return text, [text] if text else []


def _validate_structs(value: Any, key: str, required: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{key}[{index}] must be an object")
        missing = [name for name in required if name not in item]
        if missing:
            raise ValueError(f"{key}[{index}] is missing: {', '.join(missing)}")
        validated.append(dict(item))
    return validated


def main() -> None:
    context = _context()
    session = context.get("session")
    kind = context.get("kind")
    name = context.get("name")
    if not isinstance(session, str) or not session:
        raise ValueError("session is required")
    if kind not in SWEEP_TYPES:
        raise ValueError("kind must be parameter_sweep or optimization")
    if not isinstance(name, str) or not name:
        raise ValueError("name is required")

    settings = context.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    parameters = _validate_structs(
        context.get("parameters", []), "parameters", ("Name", "Parameter")
    )
    results = _validate_structs(
        context.get("results", []), "results", ("Name", "Result")
    )
    if not parameters:
        raise ValueError("at least one native parameter is required")
    if not results:
        raise ValueError("at least one native result is required")

    handle = _lum_get(session)
    initial_layout_mode = int(round(float(handle.layoutmode())))
    if initial_layout_mode != 1:
        raise RuntimeError(
            "Target must already be in Layout mode; this worker will not call switchtolayout()"
        )

    raw_before, names_before = _sweep_names(handle)
    exists = name in names_before
    if not exists:
        try:
            handle.getsweep(name, "name")
            exists = True
        except Exception:
            exists = False
    if exists and not bool(context.get("replace_existing", False)):
        raise RuntimeError(
            f"analysis item already exists: {name}; set replace_existing=true explicitly"
        )
    if exists:
        handle.deletesweep(name)

    sweep_type, default_name = SWEEP_TYPES[str(kind)]
    handle.addsweep(sweep_type)
    handle.setsweep(default_name, "name", name)
    for property_name, value in settings.items():
        handle.setsweep(name, property_name, value)
    for parameter in parameters:
        handle.addsweepparameter(name, parameter)
    for result in results:
        handle.addsweepresult(name, result)

    readback: dict[str, Any] = {}
    readback_properties = context.get("readback_properties", list(settings))
    if not isinstance(readback_properties, list) or not all(
        isinstance(item, str) for item in readback_properties
    ):
        raise ValueError("readback_properties must be an array of strings")
    for property_name in readback_properties:
        value = handle.getsweep(name, property_name)
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if not isinstance(value, (type(None), bool, int, float, str)):
            value = str(value)
        readback[property_name] = value

    save_as_raw = context.get("save_as")
    save_as: Path | None = None
    if save_as_raw is not None:
        source_raw = context.get("source_file")
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
        handle.save(str(save_as))

    _, names_after = _sweep_names(handle)
    _lum_print_json(
        {
            "schema": "fdtd-sip-native-sweep-configuration/v1",
            "session": session,
            "kind": kind,
            "name": name,
            "existing_items_before": names_before,
            "existing_items_before_raw": str(raw_before),
            "replaced_existing": exists,
            "analysis_items_after": names_after,
            "settings": sorted(settings),
            "parameter_names": [str(item["Name"]) for item in parameters],
            "result_names": [str(item["Name"]) for item in results],
            "readback": readback,
            "initial_layout_mode": initial_layout_mode,
            "final_layout_mode": int(round(float(handle.layoutmode()))),
            "save_called": save_as is not None,
            "saved_as": str(save_as.resolve()) if save_as is not None else None,
            "runsweep_called": False,
            "emesweep_called": False,
            "solver_called": False,
            "switchtolayout_called": False,
        }
    )


main()
