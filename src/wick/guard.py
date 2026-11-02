"""Background guard process enforcing Wick sessions."""

from __future__ import annotations
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from wick import agents, battery, power, thermal
from wick.session import Conditions, EndReason, Session, SessionStore, parse_iso


def get_boot_time() -> float:
    """Reads Linux system boot epoch from /proc/stat."""
    try:
        proc_stat = Path("/proc/stat")
        if proc_stat.exists():
            for line in proc_stat.read_text().splitlines():
                if line.startswith("btime "):
                    return float(line.split()[1])
    except Exception:
        pass
    return 0.0


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def any_held_process_alive(session: Session) -> bool:
    boot_time = get_boot_time()
    started_dt = parse_iso(session.startedAt)
    if started_dt and boot_time > 0:
        if started_dt.timestamp() < boot_time:
            return False

    return any(is_pid_alive(pid) for pid in session.heldPIDs)


def acquire_lock(store: SessionStore) -> int | None:
    """Acquires non-blocking exclusive flock on guard.lock, retrying briefly."""
    lock_file = store.guard_lock_path
    lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o644)
    for _ in range(15):
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except (BlockingIOError, OSError):
            time.sleep(0.1)

    os.close(lock_fd)
    return None


def spawn(executable: str) -> None:
    """Spawns a detached guard process that survives terminal closure."""
    subprocess.Popen(
        [executable, "guard"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def run_guard(store: SessionStore | None = None) -> None:
    """Main execution loop of the guard daemon."""
    if store is None:
        store = SessionStore()

    lock_fd = acquire_lock(store)
    if lock_fd is None:
        sys.exit(0)

    # Only activate sleep inhibition if an active session exists
    session = store.load()
    if session is None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
        sys.exit(0)

    # Only in real Linux mode does the guard process need to acquire and hold the inhibitor lock.
    # In simulated mode, the simulated file is managed strictly by Wick.start/stop and external edits.
    if power.get_simulated_file() is None:
        try:
            power.set_sleep_disabled(True)
        except Exception:
            pass

    # Clean shutdown on SIGTERM / SIGINT
    def _handle_term(signum, frame):
        try:
            power.set_sleep_disabled(False)
            store.finish(EndReason.STOPPED_EXTERNALLY)
        except Exception:
            pass
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass
            sys.exit(0)

    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    is_enforcing = False
    tick = 5.0
    agent_note_interval = 60.0

    try:
        while True:
            session = enforce(store, is_enforcing)
            if session is None:
                break
            is_enforcing = True

            now = datetime.now(timezone.utc)
            until_deadline = tick
            ends_dt = parse_iso(session.endsAt)
            if ends_dt:
                until_deadline = (ends_dt - now).total_seconds()

            sleep_time = min(tick, max(until_deadline, 0.5))
            time.sleep(sleep_time)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
        sys.exit(0)


def enforce(store: SessionStore, is_enforcing: bool) -> Session | None:
    """One enforcement tick under state lock."""
    def _tick() -> Session | None:
        session = store.load()
        if session is None:
            # If session file was deleted or unreadable while sleep is still disabled
            if is_enforcing and power.sleep_disabled():
                try:
                    power.set_sleep_disabled(False)
                except Exception:
                    return None
                store.finish(EndReason.STOPPED_EXTERNALLY)
            return None

        # Check if sleep was re-enabled outside of Wick
        if not power.sleep_disabled():
            store.finish(EndReason.STOPPED_EXTERNALLY)
            return None

        now = datetime.now(timezone.utc)

        # Agent tracking
        if session.untilAgentsFinish and len(agents.running()) > 0:
            last_dt = parse_iso(session.lastAgentSeen)
            is_stale = (last_dt is None) or ((now - last_dt).total_seconds() >= 60.0)
            if is_stale:
                session.lastAgentSeen = now.isoformat()
                store.save(session)

        conditions = Conditions(
            now=now,
            battery=battery.Battery.current(),
            is_overheating=thermal.is_overheating(),
            any_held_process_alive=any_held_process_alive(session),
        )

        reason = session.end_reason(conditions)
        if reason is not None:
            try:
                power.set_sleep_disabled(False)
            except Exception:
                pass
            store.finish(reason)
            return None

        return session

    return store.with_lock(_tick)
