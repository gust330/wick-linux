"""Command-line interface for Wick on Linux."""

from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from wick import agents, battery, core, durations, guard, power, thermal
from wick.session import EndReason, Session, SessionStore, parse_iso

USAGE = """wick keeps your laptop awake with the lid closed.

  wick on [2h]             stay awake, for a duration or until `wick off`
      --agents             also stop when running coding agents finish
      --floor <percent>    stop at this battery level on battery (default 20, or "off")
  wick off                 back to normal sleep
  wick run <command...>    stay awake while a command runs, then go back to normal
  wick status [--json]     show the current state
  wick agents              list the coding agents Wick can see right now
  wick doctor              diagnose power, battery, thermal and logind status
  wick setup               verify or configure permissions for sleep inhibition
  wick uninstall           clean up configuration

Durations look like 90m, 2h or 1h30m.
"""


from typing import NoReturn

def fail(message: str, code: int = 1) -> NoReturn:
    sys.stderr.write(f"wick: {message}\n")
    sys.exit(code)


def get_executable() -> str:
    # Resolves canonical path to wick executable
    return str(Path(sys.argv[0]).resolve())


def print_status(executable: str) -> None:
    store = SessionStore()
    core.Wick.reconcile(executable, store=store)
    awake = power.sleep_disabled()

    if "--json" in sys.argv:
        session = store.load()
        payload = {
            "sleepDisabled": awake,
            "session": session.to_dict() if session else None,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    if not awake:
        print("Sleeping normally.")
        return

    session = store.load()
    if session is None:
        print("Awake with the lid closed. Turned on outside Wick.")
        return

    line = "Awake with the lid closed"
    if session.endsAt:
        ends_dt = parse_iso(session.endsAt)
        if ends_dt:
            now = datetime.now(timezone.utc)
            rem = (ends_dt - now).total_seconds()
            line += f", {durations.clock(rem)} left"

    if session.untilAgentsFinish:
        line += ", or until agents finish"
    if session.heldPIDs:
        line += ", while a command runs"

    print(f"{line}.")


def parse_floor(args: list[str]) -> tuple[int | None, list[str]]:
    remaining = []
    floor: int | None = 20
    idx = 0
    while idx < len(args):
        if args[idx] == "--floor":
            if idx + 1 >= len(args):
                fail("--floor needs a value.")
            val_str = args[idx + 1]
            if val_str == "off":
                floor = None
            else:
                try:
                    p = int(val_str)
                    if not (1 <= p <= 99):
                        raise ValueError()
                    floor = p
                except ValueError:
                    fail('--floor takes a percentage from 1 to 99, or "off".')
            idx += 2
        else:
            remaining.append(args[idx])
            idx += 1
    return floor, remaining


def handle_on(args: list[str], executable: str) -> None:
    agents_flag = "--agents" in args
    args = [a for a in args if a != "--agents"]

    floor, args = parse_floor(args)

    ends_at_iso = None
    if args:
        duration_text = args[0]
        secs = durations.parse(duration_text)
        if secs is None:
            fail(f'"{duration_text}" is not a duration. Try 90m or 2h.')
        ends_at_dt = datetime.now(timezone.utc).timestamp() + secs
        ends_at_iso = datetime.fromtimestamp(ends_at_dt, timezone.utc).isoformat()

    session = Session(
        endsAt=ends_at_iso,
        untilAgentsFinish=agents_flag,
        batteryFloor=floor,
    )

    core.Wick.start(session, executable=executable)
    print_status(executable)

    if agents_flag and ends_at_iso is None and not agents.running():
        print("No agents running yet. Wick waits for one to start, then stops when the last one exits.")


def handle_off(args: list[str]) -> None:
    store = SessionStore()
    if "--session-only" in args and store.load() is None:
        sys.exit(0)

    try:
        core.Wick.stop(EndReason.STOPPED_BY_USER, store=store)
    except Exception as exc:
        fail(f"could not stop: {exc}")

    print("Sleeping normally.")


def handle_run(args: list[str], executable: str) -> None:
    if args and args[0] == "--":
        cmd = args[1:]
    else:
        cmd = args

    if not cmd:
        fail("wick run needs a command, like: wick run claude")

    store = SessionStore()
    core.Wick.reconcile(executable, store=store)
    pid = os.getpid()

    def _add_pid(s: Session) -> None:
        if pid not in s.heldPIDs:
            s.heldPIDs.append(pid)

    if store.update(_add_pid) is None:
        core.Wick.start(
            Session(heldPIDs=[pid], endsWithHeldProcesses=True),
            executable=executable,
            store=store,
        )

    exit_code = 0
    old_sigint = None
    old_sigquit = None
    try:
        proc = subprocess.Popen(cmd)
        # Ignore SIGINT and SIGQUIT only AFTER spawn so child does not inherit SIG_IGN
        old_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
        old_sigquit = signal.signal(signal.SIGQUIT, signal.SIG_IGN)
        proc.wait()
        exit_code = proc.returncode
    except FileNotFoundError:
        exit_code = 127
    finally:
        if old_sigint is not None:
            signal.signal(signal.SIGINT, old_sigint)
        if old_sigquit is not None:
            signal.signal(signal.SIGQUIT, old_sigquit)

        def _remove_pid(s: Session) -> None:
            s.heldPIDs = [p for p in s.heldPIDs if p != pid]

        remaining = store.update(_remove_pid)
        if remaining and remaining.endsWithHeldProcesses and not remaining.heldPIDs:
            try:
                core.Wick.stop(EndReason.COMMAND_FINISHED, store=store)
            except Exception:
                pass

    if exit_code == 127:
        fail(f"could not run {cmd[0]}.", code=127)

    sys.exit(exit_code)


def handle_doctor() -> None:
    print("=== Wick Linux Diagnostics ===")
    print(f"Kernel: {os.uname().release} ({os.uname().sysname})")
    print(f"Logind authorization: {'Granted (user inhibitor)' if power.is_authorized() else 'No'}")
    print(f"Inhibitor active: {power.sleep_disabled()}")

    bat = battery.Battery.current()
    if bat:
        print(f"Battery: {bat.percent}% ({'discharging' if bat.is_discharging else 'charging/full'})")
    else:
        print("Battery: None detected")

    print(f"Thermal overheating: {thermal.is_overheating()}")
    active_agents = agents.running()
    print(f"Active coding agents: {', '.join(active_agents) if active_agents else 'None'}")


def main() -> None:
    args = sys.argv[1:]
    command = args.pop(0) if args else "status"
    executable = get_executable()

    if command == "on":
        handle_on(args, executable)
    elif command == "off":
        handle_off(args)
    elif command == "run":
        handle_run(args, executable)
    elif command == "status":
        print_status(executable)
    elif command == "agents":
        running_agents = agents.running()
        if running_agents:
            print("\n".join(running_agents))
        else:
            print("No agents running.")
    elif command == "guard":
        guard.run_guard()
    elif command in ("gui", "app"):
        from wick import ui
        ui.launch_gui(executable)
    elif command == "doctor":
        handle_doctor()
    elif command == "setup":
        print("Ready. Wick can now change this setting without a password.")
    elif command == "uninstall":
        handle_off(["--session-only"])
        print("Permission removed.")
    elif command in ("help", "--help", "-h"):
        print(USAGE)
    elif command in ("version", "--version"):
        print(f"wick {durations.VERSION}")
    else:
        fail(f'unknown command "{command}".\n\n{USAGE}')


if __name__ == "__main__":
    main()
