"""Detect running coding agents from /proc command lines on Linux."""

from __future__ import annotations
import os
from pathlib import Path

KNOWN_AGENTS: dict[str, str] = {
    "aider": "Aider",
    "amp": "Amp",
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor-agent": "Cursor Agent",
    "droid": "Droid",
    "gemini": "Gemini CLI",
    "goose": "Goose",
    "hermes": "Hermes Agent",
    "hermes-agent": "Hermes Agent",
    "opencode": "OpenCode",
    "qwen": "Qwen Code",
}

INTERPRETERS = {"node", "bun", "deno", "python", "python3"}


def match_command(process_name: str, arguments: list[str]) -> str | None:
    """Matches a process name and argument vector to a known coding agent."""
    # Direct match on process comm
    if process_name in KNOWN_AGENTS:
        return KNOWN_AGENTS[process_name]

    if not arguments:
        return None

    # Match on binary path in arguments[0]
    binary_name = Path(arguments[0]).name
    if binary_name in KNOWN_AGENTS:
        return KNOWN_AGENTS[binary_name]

    # Interpreted scripts (python script.py, node agent.js)
    if process_name in INTERPRETERS and len(arguments) > 1:
        script_name = Path(arguments[1]).name
        if script_name in KNOWN_AGENTS:
            return KNOWN_AGENTS[script_name]
        no_ext = Path(script_name).stem
        if no_ext in KNOWN_AGENTS:
            return KNOWN_AGENTS[no_ext]

    return None


def running() -> list[str]:
    """Returns sorted, unique display names of active coding agents."""
    proc = Path("/proc")
    if not proc.exists():
        return []

    found = set()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue

        try:
            comm_file = entry / "comm"
            cmdline_file = entry / "cmdline"

            process_name = comm_file.read_text(errors="replace").strip() if comm_file.exists() else ""
            raw_cmdline = cmdline_file.read_bytes() if cmdline_file.exists() else b""

            # /proc/[pid]/cmdline is NUL-separated
            args = [arg.decode("utf-8", errors="replace") for arg in raw_cmdline.split(b"\x00") if arg]

            agent = match_command(process_name, args)
            if agent:
                found.add(agent)
        except (OSError, PermissionError):
            continue

    return sorted(found)
