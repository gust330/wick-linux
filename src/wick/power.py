"""Power management and sleep inhibition for Linux laptops."""

from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess


class PowerError(Exception):
    pass


class NotAuthorizedError(PowerError):
    pass


class CommandFailedError(PowerError):
    pass


_active_inhibitor_fd: int | None = None
_active_inhibit_proc: subprocess.Popen | None = None


def get_simulated_file() -> Path | None:
    path_str = os.environ.get("WICK_SIMULATE_POWER_FILE")
    return Path(path_str) if path_str else None


def is_authorized() -> bool:
    """On Linux with systemd-logind, inhibitor locks are unprivileged. No sudo needed."""
    return True


def sleep_disabled() -> bool:
    """Checks whether lid-close / sleep inhibition is currently active."""
    sim = get_simulated_file()
    if sim is not None:
        if not sim.exists():
            return False
        try:
            return sim.read_text(encoding="utf-8").strip().startswith("1")
        except OSError:
            return False

    # Check via system D-Bus login1 Manager if dbus is available
    try:
        import dbus

        bus = dbus.SystemBus()
        login1 = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
        mgr = dbus.Interface(login1, "org.freedesktop.login1.Manager")
        inhibitors = mgr.ListInhibitors()
        for what, who, why, mode, uid, pid in inhibitors:
            if who in ("wick", "wick-linux") and "handle-lid-switch" in what and mode == "block":
                return True
    except Exception:
        pass

    # Check via systemd-inhibit CLI list
    inhibit_cmd = shutil.which("systemd-inhibit")
    if inhibit_cmd:
        try:
            res = subprocess.run(
                [inhibit_cmd, "--list"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.splitlines():
                if "wick" in line and "handle-lid-switch" in line and "block" in line:
                    return True
        except Exception:
            pass

    # Global in-process inhibitor FD / proc check
    global _active_inhibitor_fd, _active_inhibit_proc
    return _active_inhibitor_fd is not None or (_active_inhibit_proc is not None and _active_inhibit_proc.poll() is None)


def set_sleep_disabled(disabled: bool) -> None:
    """Enables or disables sleep inhibition."""
    sim = get_simulated_file()
    if sim is not None:
        try:
            sim.write_text("1\n" if disabled else "0\n", encoding="utf-8")
            return
        except OSError as exc:
            raise CommandFailedError(str(exc)) from exc

    global _active_inhibitor_fd, _active_inhibit_proc
    if disabled:
        if _active_inhibitor_fd is not None or (_active_inhibit_proc is not None and _active_inhibit_proc.poll() is None):
            return  # Already inhibiting

        # 1. Try D-Bus directly
        try:
            import dbus

            bus = dbus.SystemBus()
            login1 = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
            mgr = dbus.Interface(login1, "org.freedesktop.login1.Manager")
            fd_boxed = mgr.Inhibit(
                "handle-lid-switch:sleep:idle",
                "wick",
                "Keep laptop awake with lid closed",
                "block",
            )
            _active_inhibitor_fd = fd_boxed.take()
            return
        except Exception:
            pass

        # 2. Fallback to systemd-inhibit binary
        inhibit_cmd = shutil.which("systemd-inhibit")
        if inhibit_cmd:
            try:
                _active_inhibit_proc = subprocess.Popen(
                    [
                        inhibit_cmd,
                        "--what=handle-lid-switch:sleep:idle",
                        "--who=wick",
                        "--why=Keep laptop awake with lid closed",
                        "--mode=block",
                        "sleep",
                        "infinity",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception as exc:
                raise CommandFailedError(f"Failed to run systemd-inhibit: {exc}") from exc

        raise CommandFailedError("Neither D-Bus nor systemd-inhibit is available on this system.")
    else:
        if _active_inhibitor_fd is not None:
            try:
                os.close(_active_inhibitor_fd)
            except OSError:
                pass
            _active_inhibitor_fd = None

        if _active_inhibit_proc is not None:
            try:
                _active_inhibit_proc.terminate()
                _active_inhibit_proc.wait(timeout=2)
            except Exception:
                try:
                    _active_inhibit_proc.kill()
                except Exception:
                    pass
            _active_inhibit_proc = None

        # Clean up any lingering wick systemd-inhibit processes
        try:
            res = subprocess.run(["pgrep", "-f", "systemd-inhibit.*--who=wick"], capture_output=True, text=True)
            for pid_str in res.stdout.split():
                if pid_str.isdigit():
                    try:
                        os.kill(int(pid_str), 15)
                    except OSError:
                        pass
        except Exception:
            pass
