#!/usr/bin/env python3
"""Run an ordered PyLumerical MCP scenario over stdio.

This is an MCP client, not a solver wrapper. It never imports ``lumapi``.
Actual solver calls remain subject to the Skill authorization and visible-GUI
gates; use ``open_session(..., hide=false)`` in scenarios that are authorized
to run. A scenario may load a tool argument named ``code`` from ``code_file``
and inject a JSON object as ``CODEX_CONTEXT`` with ``code_context``.

Reusable role: execute ordered, reviewable PyLumerical MCP scenarios while
keeping long UTF-8 Python code in project files instead of one-off snippets.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tomllib
from typing import Any

from _artifact_utils import atomic_write_json


def _reader(stream: Any, output: "queue.Queue[str]") -> None:
    for line in iter(stream.readline, ""):
        output.put(line.rstrip("\r\n"))


class McpClient:
    def __init__(self, command: str, env: dict[str, str]) -> None:
        process_env = os.environ.copy()
        process_env.update(env)
        self.proc = subprocess.Popen(
            [command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=process_env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("failed to open MCP stdio pipes")
        self.stdout: "queue.Queue[str]" = queue.Queue()
        self.stderr: "queue.Queue[str]" = queue.Queue()
        threading.Thread(
            target=_reader, args=(self.proc.stdout, self.stdout), daemon=True
        ).start()
        threading.Thread(
            target=_reader, args=(self.proc.stderr, self.stderr), daemon=True
        ).start()
        self.next_id = 1
        self.notifications: list[dict[str, Any]] = []

    def request(
        self, method: str, params: dict[str, Any], timeout_s: float
    ) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None and self.stdout.empty():
                raise RuntimeError(
                    f"MCP server exited with code {self.proc.returncode}: "
                    + "\n".join(self.stderr_tail(40))
                )
            try:
                raw = self.stdout.get(timeout=0.1)
            except queue.Empty:
                continue
            if not raw.strip():
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                self.notifications.append({"non_json_stdout": raw})
                continue
            if message.get("id") == request_id:
                return message
            self.notifications.append(message)
        raise TimeoutError(f"MCP request timed out: {method}")

    def notify(self, method: str, params: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def stderr_tail(self, limit: int) -> list[str]:
        items: list[str] = []
        while True:
            try:
                items.append(self.stderr.get_nowait())
            except queue.Empty:
                break
        return items[-limit:]

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _load_mcp_config(path: Path) -> tuple[str, dict[str, str]]:
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    server = config["mcp_servers"]["pylumerical"]
    command = str(server["command"])
    env = {str(key): str(value) for key, value in server.get("env", {}).items()}
    return command, env


def _validate_scenario(scenario: Any) -> list[dict[str, Any]]:
    if not isinstance(scenario, dict) or not isinstance(scenario.get("calls"), list):
        raise ValueError("scenario must contain a calls array")
    calls: list[dict[str, Any]] = []
    for index, entry in enumerate(scenario["calls"], start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("tool"), str):
            raise ValueError(f"scenario call {index} is missing a string tool name")
        if "arguments" in entry and not isinstance(entry["arguments"], dict):
            raise ValueError(f"scenario call {index} arguments must be an object")
        calls.append(entry)
    return calls


def _materialize_arguments(
    arguments: dict[str, Any], scenario_dir: Path, label: str
) -> dict[str, Any]:
    result = dict(arguments)
    code_file = result.pop("code_file", None)
    code_context = result.pop("code_context", None)
    if code_context is not None and not isinstance(code_context, dict):
        raise ValueError(f"{label}: code_context must be a JSON object")
    if code_context is not None and code_file is None:
        raise ValueError(f"{label}: code_context requires code_file")
    if code_file is not None:
        code_path = Path(code_file)
        if not code_path.is_absolute():
            code_path = scenario_dir / code_path
        source = code_path.read_text(encoding="utf-8")
        prefix = ""
        if code_context is not None:
            prefix = f"CODEX_CONTEXT = {code_context!r}\n"
        result["code"] = prefix + f"exec(compile({source!r}, {label!r}, 'exec'))"
    return result


def _compact_tool_result(
    label: str, tool_name: str, response: dict[str, Any], capture: str
) -> dict[str, Any]:
    result = response.get("result", {})
    content = result.get("content", []) if isinstance(result, dict) else []
    texts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    joined = "\n".join(texts)
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    item = {
        "label": label,
        "tool": tool_name,
        "rpc_error": response.get("error"),
        "is_error": (
            bool(result.get("isError"))
            or (isinstance(structured, dict) and structured.get("success") is False)
        )
        if isinstance(result, dict)
        else None,
        "structured_content": structured,
    }
    if capture == "full":
        item["text"] = joined
    else:
        item["text_length"] = len(joined)
        item["text_head"] = joined[:240]
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a PyLumerical MCP scenario.")
    parser.add_argument("scenario", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".codex" / "config.toml"
    )
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate scenario and code files only"
    )
    args = parser.parse_args()

    scenario_path = args.scenario.resolve()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    calls = _validate_scenario(scenario)

    if args.dry_run:
        materialized = []
        for entry in calls:
            label = entry.get("label", entry["tool"])
            arguments = _materialize_arguments(
                entry.get("arguments", {}), scenario_path.parent, label
            )
            materialized.append(
                {
                    "label": label,
                    "tool": entry["tool"],
                    "capture": entry.get("capture", "summary"),
                    "argument_keys": sorted(arguments),
                    "code_bytes": len(arguments.get("code", "").encode("utf-8")),
                    "code_context_keys": sorted(
                        entry.get("arguments", {}).get("code_context", {})
                    ),
                }
            )
        payload = {"dry_run": True, "scenario": str(scenario_path), "calls": materialized}
        if args.output:
            atomic_write_json(args.output, payload)
            print(args.output.resolve())
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    command, env = _load_mcp_config(args.config.resolve())
    client = McpClient(command, env)
    output: dict[str, Any] = {"scenario": str(scenario_path), "calls": []}
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "codex-pylumerical-stdio-client",
                    "version": "1.1.0",
                },
            },
            args.timeout,
        )
        output["server_info"] = initialize.get("result", {}).get("serverInfo")
        client.notify("notifications/initialized", {})

        for entry in calls:
            tool_name = entry["tool"]
            label = entry.get("label", tool_name)
            capture = entry.get("capture", "summary")
            arguments = _materialize_arguments(
                entry.get("arguments", {}), scenario_path.parent, label
            )
            response = client.request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                float(entry.get("timeout_s", args.timeout)),
            )
            compact = _compact_tool_result(label, tool_name, response, capture)
            output["calls"].append(compact)
            if compact["rpc_error"] or compact["is_error"]:
                output["stopped_after"] = label
                break
    except Exception as exc:
        output["client_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        output["notifications"] = client.notifications
        output["stderr_tail"] = client.stderr_tail(80)
        client.close()

    if args.output:
        atomic_write_json(args.output, output)
        print(args.output.resolve())
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if output.get("client_error") or output.get("stopped_after") else 0


if __name__ == "__main__":
    sys.exit(main())
