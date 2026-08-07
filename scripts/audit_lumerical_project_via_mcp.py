#!/usr/bin/env python3
"""只读审计 FDTD、MODE/FDE、EME 与 varFDTD 的配置和结果。

通过 ``pylumerical_mcp_stdio_runner.py`` 把本文件作为 ``code_file`` 执行，
并提供 JSON ``code_context``。PyLumerical 执行环境负责提供 ``_lum_get`` 和
``_lum_print_json``。本 worker 不调用求解器、不保存工程、不切换
Layout/Analysis mode，也不导入 ``lumapi``。

可复用用途：使用统一、紧凑且与产品无关的接口，回读 named object、global
source/monitor、原生 Sweep 设置和原生结果 dataset。数值数组只输出摘要，
不把大数组直接复制到 MCP 日志。
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def _context() -> dict[str, Any]:
    value = globals().get("CODEX_CONTEXT")
    if not isinstance(value, dict):
        raise RuntimeError("CODEX_CONTEXT must be injected as a JSON object")
    return value


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _shape(value: Any) -> list[int] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    try:
        return [int(item) for item in shape]
    except Exception:
        return None


def _flatten(value: Any) -> Iterable[Any]:
    flat = getattr(value, "flat", None)
    if flat is not None:
        yield from flat
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (list, tuple)) or hasattr(item, "flat"):
                yield from _flatten(item)
            else:
                yield item
        return
    yield value


def _numeric_summary(value: Any, max_scan: int, max_sample: int) -> dict[str, Any]:
    finite_real: list[float] = []
    finite_imag: list[float] = []
    finite_abs: list[float] = []
    sample: list[Any] = []
    scanned = 0
    nonfinite = 0
    complex_seen = False

    for raw in _flatten(value):
        if scanned >= max_scan:
            break
        item = _scalar(raw)
        if isinstance(item, bool) or not isinstance(item, (int, float, complex)):
            continue
        scanned += 1
        number = complex(item)
        complex_seen = complex_seen or number.imag != 0.0
        if not (math.isfinite(number.real) and math.isfinite(number.imag)):
            nonfinite += 1
            continue
        finite_real.append(float(number.real))
        finite_imag.append(float(number.imag))
        finite_abs.append(float(abs(number)))
        if len(sample) < max_sample:
            sample.append(
                {"real": number.real, "imag": number.imag}
                if number.imag != 0.0
                else number.real
            )

    report: dict[str, Any] = {
        "scanned_numeric_values": scanned,
        "finite_numeric_values": len(finite_abs),
        "nonfinite_numeric_values": nonfinite,
        "scan_truncated": scanned >= max_scan,
        "sample": sample,
    }
    if finite_abs:
        if complex_seen:
            report["real"] = {
                "min": min(finite_real),
                "max": max(finite_real),
                "mean": sum(finite_real) / len(finite_real),
            }
            report["imag"] = {
                "min": min(finite_imag),
                "max": max(finite_imag),
                "mean": sum(finite_imag) / len(finite_imag),
            }
            report["magnitude"] = {
                "min": min(finite_abs),
                "max": max(finite_abs),
                "mean": sum(finite_abs) / len(finite_abs),
            }
        else:
            report.update(
                {
                    "min": min(finite_real),
                    "max": max(finite_real),
                    "mean": sum(finite_real) / len(finite_real),
                }
            )
    return report


def _summarize(value: Any, max_scan: int, max_sample: int) -> Any:
    scalar = _scalar(value)
    if scalar is None or isinstance(scalar, (bool, str)):
        return scalar
    if isinstance(scalar, (int, float, complex)):
        return _numeric_summary(scalar, max_scan, max_sample)
    if isinstance(value, dict):
        return {
            "kind": "mapping",
            "keys": [str(key) for key in value],
            "fields": {
                str(key): _summarize(item, max_scan, max_sample)
                for key, item in value.items()
            },
        }
    if isinstance(value, (list, tuple)) or hasattr(value, "shape"):
        return {
            "kind": type(value).__name__,
            "shape": _shape(value),
            "dtype": str(getattr(value, "dtype", "")) or None,
            "numeric": _numeric_summary(value, max_scan, max_sample),
        }
    return {"kind": type(value).__name__, "text": str(value)[:1000]}


def _require_list(context: dict[str, Any], key: str) -> list[Any]:
    value = context.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    return value


def _read_named(handle: Any, requests: list[Any], max_scan: int, max_sample: int) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError(f"named_reads[{index}] requires path")
        properties = request.get("properties", [])
        if not isinstance(properties, list) or not all(
            isinstance(item, str) for item in properties
        ):
            raise ValueError(f"named_reads[{index}].properties must be strings")
        item: dict[str, Any] = {"path": request["path"], "properties": {}}
        for property_name in properties:
            try:
                value = handle.getnamed(request["path"], property_name)
                item["properties"][property_name] = {
                    "ok": True,
                    "value": _summarize(value, max_scan, max_sample),
                }
            except Exception as exc:
                item["properties"][property_name] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        reports.append(item)
    return reports


def _read_global(handle: Any, method_name: str, properties: list[Any], max_scan: int, max_sample: int) -> dict[str, Any]:
    if not all(isinstance(item, str) for item in properties):
        raise ValueError(f"{method_name} property names must be strings")
    method = getattr(handle, method_name)
    report: dict[str, Any] = {}
    for property_name in properties:
        try:
            report[property_name] = {
                "ok": True,
                "value": _summarize(method(property_name), max_scan, max_sample),
            }
        except Exception as exc:
            report[property_name] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return report


def main() -> None:
    context = _context()
    session = context.get("session")
    if not isinstance(session, str) or not session:
        raise ValueError("session is required")
    max_scan = int(context.get("max_scan_values", 100000))
    max_sample = int(context.get("max_sample_values", 8))
    if max_scan <= 0 or max_sample < 0:
        raise ValueError("max_scan_values must be positive and max_sample_values nonnegative")

    handle = _lum_get(session)
    report: dict[str, Any] = {
        "schema": "fdtd-sip-project-audit/v1",
        "session": session,
        "layout_mode": int(round(float(handle.layoutmode()))),
        "named_objects": _read_named(
            handle,
            _require_list(context, "named_reads"),
            max_scan,
            max_sample,
        ),
        "global_source": _read_global(
            handle,
            "getglobalsource",
            _require_list(context, "global_source_properties"),
            max_scan,
            max_sample,
        ),
        "global_monitor": _read_global(
            handle,
            "getglobalmonitor",
            _require_list(context, "global_monitor_properties"),
            max_scan,
            max_sample,
        ),
        "sweeps": [],
        "results": [],
        "solver_called": False,
        "save_called": False,
        "switchtolayout_called": False,
    }

    if bool(context.get("read_data_catalog", False)):
        try:
            report["data_catalog"] = str(handle.getdata())
        except Exception as exc:
            report["data_catalog_error"] = f"{type(exc).__name__}: {exc}"

    for index, request in enumerate(_require_list(context, "sweep_reads"), start=1):
        if not isinstance(request, dict) or not isinstance(request.get("name"), str):
            raise ValueError(f"sweep_reads[{index}] requires name")
        properties = request.get("properties", [])
        if not isinstance(properties, list) or not all(
            isinstance(item, str) for item in properties
        ):
            raise ValueError(f"sweep_reads[{index}].properties must be strings")
        item: dict[str, Any] = {"name": request["name"], "properties": {}}
        for property_name in properties:
            try:
                item["properties"][property_name] = {
                    "ok": True,
                    "value": _summarize(
                        handle.getsweep(request["name"], property_name),
                        max_scan,
                        max_sample,
                    ),
                }
            except Exception as exc:
                item["properties"][property_name] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        report["sweeps"].append(item)

    for index, request in enumerate(_require_list(context, "result_reads"), start=1):
        if not isinstance(request, dict):
            raise ValueError(f"result_reads[{index}] must be an object")
        object_path = request.get("object")
        result_name = request.get("result")
        if not isinstance(object_path, str) or not isinstance(result_name, str):
            raise ValueError(f"result_reads[{index}] requires object and result")
        item = {"object": object_path, "result": result_name}
        try:
            value = handle.getresult(object_path, result_name)
            item.update(
                {
                    "ok": True,
                    "summary": _summarize(value, max_scan, max_sample),
                }
            )
        except Exception as exc:
            item.update(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        report["results"].append(item)

    _lum_print_json(report)


main()
