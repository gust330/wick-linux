"""Background process that enforces a session: the dead man's switch behind every safety promise Wick makes.

It holds the lid lock itself, so if it dies for any reason the lock goes with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

from wick import agents, battery, power, thermal
from wick.session import Conditions, EndReason, Session, SessionStore, parse_iso

_TICK = 5.0
_AGENT_NOTE_INTERVAL = 60.0


def boot_time() -> float:
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError, IndexError):
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


def started_this_boot(session: Session) -> bool:
    started = parse_iso(session.startedAt)
    booted = boot_time()
    return started is None or booted <= 0 or started.timestamp() >= booted


def any_held_process_alive(session: Session) -> bool:
    # PIDs from before the last boot mean nothing, whatever process has them now.
    return started_this_boot(session) and any(is_pid_alive(pid) for pid in session.heldPIDs)


def acquire_lock(store: SessionStore) -> int | None:
    """One guard at a time. Retries, because a guard that has just seen "no session" may still be on its way out,
    and giving up then would leave the new session with nobody watching it."""
    descriptor = os.open(str(store.guard_lock_path), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o644)
    for _ in range(50):
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return descriptor
        except OSError:
            time.sleep(0.1)
    os.close(descriptor)
    return None


def spawn(executable: str) -> None:
    """Detached, so it survives the terminal that started it, and orphaned on purpose through a short-lived shell.

    As a direct child of a long-running `wick run` it would never be reaped if it died. A zombie still answers
    `kill -0`, so the loop tied to it would keep holding the lock with nothing enforcing the session.
    """
    if not os.access(executable, os.X_OK):
        raise OSError(f"{executable} isn't executable")
    subprocess.run(
        ["sh", "-c", '"$0" guard </dev/null >/dev/null 2>&1 &', executable],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        check=True,
    )


def wake(store: SessionStore) -> None:
    """Asks a sleeping guard to check right away, so `wick off` doesn't wait for the next tick."""
    pid = store.guard_pid()
    if pid is None:
        return
    # A stale pid file could name anyone's process, and SIGUSR1 kills by default.
    try:
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if b"guard" in arguments:
            os.kill(pid, signal.SIGUSR1)
    except OSError:
        pass


def run_guard(store: SessionStore | None = None) -> None:
    store = store or SessionStore()

    lock = acquire_lock(store)
    if lock is None:
        sys.exit(0)
    # A file that's there but unreadable carries on to the first tick, which ends it properly.
    session = store.load()
    if session is None and not store.has_unreadable_session():
        sys.exit(0)

    inhibitor = power.Inhibitor() if power.simulated_file() is None and session is not None else None
    guard = _Guard(store, inhibitor)

    # In place before the lock is taken, so a `wick off` right after `wick on` is never missed.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    # Handlers only set flags: taking the state lock from one could deadlock with a tick in progress.
    signal.signal(signal.SIGTERM, guard.request_stop)
    signal.signal(signal.SIGINT, guard.request_stop)
    signal.signal(signal.SIGUSR1, guard.request_check)
    store.write_guard_pid()

    try:
        if inhibitor is not None:
            try:
                inhibitor.acquire()
            except power.PowerError as error:
                store.write_guard_error(str(error))
                sys.exit(1)
        guard.loop()
    finally:
        if inhibitor is not None:
            inhibitor.release()
        store.clear_guard_pid()
    sys.exit(0)


class _Guard:
    def __init__(self, store: SessionStore, inhibitor: power.Inhibitor | None) -> None:
        self.store = store
        self.inhibitor = inhibitor
        self.heat = thermal.Monitor()
        self.stop_requested = False
        # A pipe to wake on, because nothing that takes a lock is safe in a signal handler: threading.Event could
        # deadlock if a signal landed inside wait(), leaving the lock held with nothing enforcing it.
        self.wake_read, self.wake_write = os.pipe()
        os.set_blocking(self.wake_read, False)
        os.set_blocking(self.wake_write, False)

    def request_stop(self, signum: int, frame: object) -> None:
        self.stop_requested = True
        self.request_check(signum, frame)

    def request_check(self, signum: int, frame: object) -> None:
        try:
            os.write(self.wake_write, b"x")
        except OSError:
            pass  # The pipe is full, so a wake-up is already waiting.

    def sleep(self, seconds: float) -> None:
        select.select([self.wake_read], [], [], seconds)
        try:
            os.read(self.wake_read, 4096)
        except OSError:
            pass

    def loop(self) -> None:
        while True:
            session = self.store.with_lock(self.tick)
            if session is None:
                return
            ends = parse_iso(session.endsAt)
            until_deadline = (ends - datetime.now(timezone.utc)).total_seconds() if ends else _TICK
            # Past the deadline with a command still holding it open, there's nothing to hurry for.
            self.sleep(min(_TICK, until_deadline) if until_deadline > 0 else _TICK)

    def tick(self) -> Session | None:
        """One check, under the state lock. Returns None once there's nothing left to enforce."""
        session = self.store.load()

        if self.stop_requested:
            # Logout and shutdown arrive as SIGTERM.
            return self.end(EndReason.STOPPED_EXTERNALLY if session else None)

        if session is None:
            # `stop` removes the file on purpose, but so can a deleted or corrupt file. Either way, nobody
            # can say when this should end, and the safe answer is now.
            if self.store.has_unreadable_session() or (power.simulated_file() is not None and power.sleep_disabled()):
                return self.end(EndReason.STOPPED_EXTERNALLY)
            return self.end(None)

        if not self.lock_in_place():
            self.store.finish(EndReason.STOPPED_EXTERNALLY)
            return None

        now = datetime.now(timezone.utc)
        if session.untilAgentsFinish and agents.running():
            seen = parse_iso(session.lastAgentSeen)
            if seen is None or (now - seen).total_seconds() >= _AGENT_NOTE_INTERVAL:
                session.lastAgentSeen = now.isoformat()
                self.store.save(session)

        reason = session.end_reason(
            Conditions(
                now=now,
                battery=battery.Battery.current(),
                is_overheating=self.heat.is_overheating(),
                any_held_process_alive=any_held_process_alive(session),
            )
        )
        if reason is not None:
            return self.end(reason)
        return session

    def lock_in_place(self) -> bool:
        return self.inhibitor.is_alive() if self.inhibitor is not None else power.sleep_disabled()

    def end(self, reason: EndReason | None) -> None:
        # Released before the state lock is, so nothing can start a new session and watch this one's lock vanish.
        if self.inhibitor is not None:
            self.inhibitor.release()
        if reason is not None:
            power.set_simulated(False)
            self.store.finish(reason)
        return None
