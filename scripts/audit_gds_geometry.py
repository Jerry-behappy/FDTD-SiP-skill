#!/usr/bin/env python3
"""Read-only, stdlib-only GDSII hierarchy and geometry audit.

The parser reports database units, cells, layers/datatypes, top-cell candidates,
flattened SREF geometry, labels, bounding boxes, areas, warnings, and SHA-256.
BOUNDARY, BOX, PATH, TEXT, and common SREF transforms are supported. AREF is
reported but deliberately not expanded, so unsupported array geometry is never
silently accepted as complete.

Reusable role: establish GDS geometry truth before Lumerical reconstruction or
after LSF export without requiring KLayout, gdstk, gdspy, or Lumerical.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from _artifact_utils import atomic_write_json, file_record


RECORD_NAMES = {
    0x00: "HEADER",
    0x01: "BGNLIB",
    0x02: "LIBNAME",
    0x03: "UNITS",
    0x04: "ENDLIB",
    0x05: "BGNSTR",
    0x06: "STRNAME",
    0x07: "ENDSTR",
    0x08: "BOUNDARY",
    0x09: "PATH",
    0x0A: "SREF",
    0x0B: "AREF",
    0x0C: "TEXT",
    0x0D: "LAYER",
    0x0E: "DATATYPE",
    0x0F: "WIDTH",
    0x10: "XY",
    0x11: "ENDEL",
    0x12: "SNAME",
    0x13: "COLROW",
    0x16: "TEXTTYPE",
    0x17: "PRESENTATION",
    0x19: "STRING",
    0x1A: "STRANS",
    0x1B: "MAG",
    0x1C: "ANGLE",
    0x21: "PATHTYPE",
    0x2D: "BOX",
    0x2E: "BOXTYPE",
}


@dataclass
class Element:
    kind: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Cell:
    name: str
    elements: list[Element] = field(default_factory=list)


def decode_real8(raw: bytes) -> float:
    if raw == b"\x00" * 8:
        return 0.0
    sign = -1.0 if raw[0] & 0x80 else 1.0
    exponent = (raw[0] & 0x7F) - 64
    mantissa = int.from_bytes(raw[1:], "big") / float(1 << 56)
    return sign * mantissa * (16.0**exponent)


def decode_value(dtype: int, raw: bytes) -> Any:
    if dtype == 0:
        return None
    if dtype == 1:
        return int.from_bytes(raw, "big")
    if dtype == 2:
        return list(struct.unpack(f">{len(raw) // 2}h", raw))
    if dtype == 3:
        return list(struct.unpack(f">{len(raw) // 4}i", raw))
    if dtype == 5:
        return [decode_real8(raw[index : index + 8]) for index in range(0, len(raw), 8)]
    if dtype == 6:
        return raw.rstrip(b"\x00").decode("ascii", errors="replace")
    return raw.hex()


def bbox(points: Iterable[tuple[float, float]]) -> list[float] | None:
    values = list(points)
    if not values:
        return None
    xs = [point[0] for point in values]
    ys = [point[1] for point in values]
    return [min(xs), min(ys), max(xs), max(ys)]


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    vertices = points[:-1] if points[0] == points[-1] else points
    return 0.5 * sum(
        vertices[index][0] * vertices[(index + 1) % len(vertices)][1]
        - vertices[(index + 1) % len(vertices)][0] * vertices[index][1]
        for index in range(len(vertices))
    )


def parse_gds(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    offset = 0
    record_counts: Counter[str] = Counter()
    library_name = ""
    units: list[float] | None = None
    cells: dict[str, Cell] = {}
    current_cell: Cell | None = None
    current_element: Element | None = None
    warnings: list[str] = []

    while offset < len(data):
        if offset + 4 > len(data):
            raise ValueError(f"incomplete record header at offset {offset}")
        length, record_type, dtype = struct.unpack(">HBB", data[offset : offset + 4])
        if length < 4 or offset + length > len(data):
            raise ValueError(f"invalid record length {length} at offset {offset}")
        raw = data[offset + 4 : offset + length]
        value = decode_value(dtype, raw)
        name = RECORD_NAMES.get(record_type, f"UNKNOWN_0x{record_type:02X}")
        record_counts[name] += 1
        offset += length

        if name == "LIBNAME":
            library_name = str(value)
        elif name == "UNITS":
            units = value
        elif name == "BGNSTR":
            current_cell = None
        elif name == "STRNAME":
            current_cell = Cell(str(value))
            cells[current_cell.name] = current_cell
        elif name in {"BOUNDARY", "PATH", "SREF", "AREF", "TEXT", "BOX"}:
            current_element = Element(name)
        elif name == "ENDEL":
            if current_cell is None or current_element is None:
                warnings.append("ENDEL without a current cell/element")
            else:
                current_cell.elements.append(current_element)
            current_element = None
        elif current_element is not None:
            if name == "XY":
                coordinates = value or []
                if len(coordinates) % 2:
                    warnings.append(f"odd XY coordinate count at record offset {offset - length}")
                current_element.attrs["xy_dbu"] = [
                    [coordinates[index], coordinates[index + 1]]
                    for index in range(0, len(coordinates) - 1, 2)
                ]
            elif name in {
                "LAYER",
                "DATATYPE",
                "TEXTTYPE",
                "PATHTYPE",
                "BOXTYPE",
                "WIDTH",
            }:
                current_element.attrs[name.lower()] = value[0] if value else None
            elif name in {"SNAME", "STRING"}:
                current_element.attrs[name.lower()] = value
            elif name in {"STRANS", "MAG", "ANGLE", "COLROW", "PRESENTATION"}:
                current_element.attrs[name.lower()] = value

    if units is None or len(units) != 2:
        raise ValueError("GDS does not contain a valid UNITS record")
    return {
        "library_name": library_name,
        "user_units_per_dbu": float(units[0]),
        "meters_per_dbu": float(units[1]),
        "cells_raw": cells,
        "record_counts": dict(sorted(record_counts.items())),
        "warnings": warnings,
    }


def transform_point(
    point: tuple[float, float],
    origin: tuple[float, float],
    angle_deg: float,
    magnification: float,
    reflect_x: bool,
) -> tuple[float, float]:
    x, y = point
    if reflect_x:
        y = -y
    x *= magnification
    y *= magnification
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        cosine * x - sine * y + origin[0],
        sine * x + cosine * y + origin[1],
    )


def flatten_cell(
    cell_name: str,
    cells: dict[str, Cell],
    dbu_to_um: float,
    stack: tuple[str, ...] = (),
    parent_origin: tuple[float, float] = (0.0, 0.0),
    parent_angle: float = 0.0,
    parent_magnification: float = 1.0,
    parent_reflect: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    if cell_name in stack:
        return [], [f"recursive reference: {' -> '.join(stack + (cell_name,))}"]
    if cell_name not in cells:
        return [], [f"missing referenced cell: {cell_name}"]

    flattened: list[dict[str, Any]] = []
    warnings: list[str] = []
    for element_index, element in enumerate(cells[cell_name].elements):
        attrs = element.attrs
        if element.kind in {"BOUNDARY", "PATH", "TEXT", "BOX"}:
            local_points = [
                (float(x) * dbu_to_um, float(y) * dbu_to_um)
                for x, y in attrs.get("xy_dbu", [])
            ]
            points = [
                transform_point(
                    point,
                    parent_origin,
                    parent_angle,
                    parent_magnification,
                    parent_reflect,
                )
                for point in local_points
            ]
            datatype = attrs.get(
                "datatype", attrs.get("boxtype", attrs.get("texttype"))
            )
            item: dict[str, Any] = {
                "source_cell": cell_name,
                "source_element_index": element_index,
                "kind": element.kind,
                "layer": attrs.get("layer"),
                "datatype": datatype,
                "points_um": [[round(x, 9), round(y, 9)] for x, y in points],
                "bbox_um": bbox(points),
                "signed_area_um2": (
                    polygon_area(points)
                    if element.kind in {"BOUNDARY", "BOX"}
                    else None
                ),
                "vertex_count": len(points),
            }
            if element.kind == "TEXT":
                item["text"] = attrs.get("string")
            if element.kind == "PATH":
                width_dbu = attrs.get("width")
                item["width_um"] = (
                    abs(float(width_dbu)) * dbu_to_um * parent_magnification
                    if width_dbu is not None
                    else None
                )
                item["pathtype"] = attrs.get("pathtype")
            flattened.append(item)
        elif element.kind == "SREF":
            reference = attrs.get("sname")
            coordinates = attrs.get("xy_dbu", [])
            if not reference or not coordinates:
                warnings.append(f"cell={cell_name} element={element_index}: incomplete SREF")
                continue
            local_origin = (
                float(coordinates[0][0]) * dbu_to_um,
                float(coordinates[0][1]) * dbu_to_um,
            )
            origin = transform_point(
                local_origin,
                parent_origin,
                parent_angle,
                parent_magnification,
                parent_reflect,
            )
            strans = attrs.get("strans", 0)
            if isinstance(strans, list):
                strans = strans[0] if strans else 0
            child_reflect = parent_reflect ^ bool(int(strans) & 0x8000)
            magnitude = attrs.get("mag", [1.0])
            angle = attrs.get("angle", [0.0])
            child_magnification = parent_magnification * float(
                magnitude[0] if isinstance(magnitude, list) else magnitude
            )
            child_angle = parent_angle + float(
                angle[0] if isinstance(angle, list) else angle
            )
            child_elements, child_warnings = flatten_cell(
                str(reference),
                cells,
                dbu_to_um,
                stack + (cell_name,),
                origin,
                child_angle,
                child_magnification,
                child_reflect,
            )
            flattened.extend(child_elements)
            warnings.extend(child_warnings)
        elif element.kind == "AREF":
            warnings.append(
                f"cell={cell_name} element={element_index}: AREF is reported but not expanded"
            )
    return flattened, warnings


def build_report(
    path: Path, requested_tops: list[str] | None, include_elements: bool
) -> dict[str, Any]:
    parsed = parse_gds(path)
    cells: dict[str, Cell] = parsed.pop("cells_raw")
    dbu_to_um = float(parsed["meters_per_dbu"]) * 1e6
    referenced = {
        str(element.attrs.get("sname"))
        for cell in cells.values()
        for element in cell.elements
        if element.kind in {"SREF", "AREF"} and element.attrs.get("sname")
    }
    candidates = sorted(set(cells) - referenced)
    selected = requested_tops or candidates
    missing = sorted(set(selected) - set(cells))
    if missing:
        raise ValueError(f"unknown top cell(s): {', '.join(missing)}")

    cell_summaries: dict[str, Any] = {}
    for name, cell in sorted(cells.items()):
        kinds = Counter(element.kind for element in cell.elements)
        layers: Counter[str] = Counter()
        references: list[str] = []
        for element in cell.elements:
            layer = element.attrs.get("layer")
            datatype = element.attrs.get(
                "datatype",
                element.attrs.get("boxtype", element.attrs.get("texttype")),
            )
            if layer is not None:
                layers[f"{layer}/{datatype if datatype is not None else 0}"] += 1
            if element.kind in {"SREF", "AREF"} and element.attrs.get("sname"):
                references.append(str(element.attrs["sname"]))
        cell_summaries[name] = {
            "element_counts": dict(sorted(kinds.items())),
            "layer_datatype_counts": dict(sorted(layers.items())),
            "references": references,
        }

    flattened_tops: dict[str, Any] = {}
    all_flatten_warnings: list[str] = []
    for top in selected:
        elements, warnings = flatten_cell(top, cells, dbu_to_um)
        geometry = [
            item for item in elements if item["kind"] in {"BOUNDARY", "PATH", "BOX"}
        ]
        points = [tuple(point) for item in geometry for point in item["points_um"]]
        layers = Counter(
            f"{item['layer']}/{item['datatype'] if item['datatype'] is not None else 0}"
            for item in geometry
        )
        top_report: dict[str, Any] = {
            "bbox_um": bbox(points),
            "geometry_count": len(geometry),
            "text_count": sum(item["kind"] == "TEXT" for item in elements),
            "layer_datatype_counts": dict(sorted(layers.items())),
            "flatten_warnings": warnings,
        }
        if include_elements:
            top_report["elements"] = elements
        flattened_tops[top] = top_report
        all_flatten_warnings.extend(warnings)

    return {
        "schema": "fdtd-sip-gds-audit/v1",
        "source": file_record(path),
        "library_name": parsed["library_name"],
        "user_units_per_dbu": parsed["user_units_per_dbu"],
        "meters_per_dbu": parsed["meters_per_dbu"],
        "database_unit_nm": float(parsed["meters_per_dbu"]) * 1e9,
        "record_counts": parsed["record_counts"],
        "top_cell_candidates": candidates,
        "audited_top_cells": selected,
        "cells": cell_summaries,
        "flattened_top_cells": flattened_tops,
        "warnings": parsed["warnings"] + all_flatten_warnings,
        "elements_included": include_elements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gds", type=Path, help="source GDSII file")
    parser.add_argument("--output", type=Path, help="JSON output; defaults beside the GDS")
    parser.add_argument(
        "--top-cell",
        action="append",
        dest="top_cells",
        help="top cell to flatten; repeat for more than one",
    )
    parser.add_argument(
        "--include-elements",
        action="store_true",
        help="include flattened points; default report stays compact",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return exit code 2 when any parse/flatten warning exists",
    )
    args = parser.parse_args()

    source = args.gds.resolve()
    if not source.is_file():
        parser.error(f"GDS does not exist: {source}")
    output = (
        args.output.resolve()
        if args.output
        else source.with_suffix(source.suffix + ".audit.json")
    )
    report = build_report(source, args.top_cells, args.include_elements)
    atomic_write_json(output, report)
    print(output)
    if args.strict and report["warnings"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
