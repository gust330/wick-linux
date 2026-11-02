"""The operations the CLI and the tray app share."""

from __future__ import annotations

import time

from wick import battery, guard, power
from wick.session import EndReason, Session, SessionStore

_GUARD_START_TIMEOUT = 8.0
# Longer than the guard's tick, so that even a wake-up that went astray still ends in time.
_RELEASE_TIMEOUT = 7.0


class Wick:
    @staticmethod
    def start(session: Session, executable: str, store: SessionStore | None = None) -> None:
        """Returns only once the lock is confirmed in place. Raises PowerError if it can't be."""
        store = store or SessionStore()

        # The guard's first check would end this straight away, and whatever was counting on it would run unprotected.
        current = battery.Battery.current()
        if session.batteryFloor is not None and current and current.is_discharging and current.percent <= session.batteryFloor:
            raise power.BelowBatteryFloorError(
                f"the battery is at {current.percent}%, at or below the {session.batteryFloor}% floor, so Wick would "
                "stop straight away. Plug in, or set a lower one with --floor."
            )

        # All of it under the state lock: anything reconciling meanwhile would otherwise see a session
        # with no lock yet and end it.
        def setup() -> None:
            # Starting over a session mustn't drop the commands relying on it, but only ones still running: a dead
            # PID copied into a new session could later belong to another process and hold the timer open forever.
            running = store.load()
            if running and guard.started_this_boot(running):
                session.heldPIDs.extend(
                    pid for pid in running.heldPIDs if pid not in session.heldPIDs and guard.is_pid_alive(pid)
                )
            store.clear_guard_error()
            store.save(session)
            try:
                power.set_simulated(True)
                guard.spawn(executable)
                if power.simulated_file() is None:
                    _wait_for_guard(store)
            except BaseException:  # Including Ctrl-C while waiting, which would otherwise leave a session running.
                store.discard_session()
                power.set_simulated(False)
                raise

        store.with_lock(setup)

    @staticmethod
    def stop(reason: EndReason = EndReason.STOPPED_BY_USER, store: SessionStore | None = None) -> None:
        """Returns only once sleep is really back."""
        store = store or SessionStore()

        def finish() -> None:
            power.set_simulated(False)
            store.finish(reason)

        store.with_lock(finish)
        _wait_for_release(store)

    @staticmethod
    def release_hold(pid: int, store: SessionStore | None = None) -> None:
        """A `wick run` finishing. Removing its hold and ending the session it created have to be one step, or a
        session started in between would be ended too, after being told it was running."""
        store = store or SessionStore()

        def release() -> bool:
            session = store.load()
            if session is None:
                return False
            session.heldPIDs = [held for held in session.heldPIDs if held != pid]
            if session.endsWithHeldProcesses and not session.heldPIDs:
                power.set_simulated(False)
                store.finish(EndReason.COMMAND_FINISHED)
                return True
            store.save(session)
            return False

        if store.with_lock(release):
            _wait_for_release(store)

    @staticmethod
    def reconcile(executable: str, store: SessionStore | None = None) -> None:
        """Run on every launch: clears up after a guard that died, or a session file that can't be trusted."""
        store = store or SessionStore()

        def check() -> bool:
            if store.has_unreadable_session():
                power.set_simulated(False)
                store.finish(EndReason.STOPPED_EXTERNALLY)
                return False
            if store.load() is None:
                return False
            if power.lock_held() is False:
                store.finish(EndReason.STOPPED_EXTERNALLY)
                return False
            return True

        if store.with_lock(check):
            try:
                guard.spawn(executable)
            except OSError:
                pass


def _wait_for_release(store: SessionStore) -> None:
    """Returns only once sleep is really back. Outside the state lock, because the guard needs it to act on this."""
    guard.wake(store)
    if power.simulated_file() is not None:
        return
    deadline = time.monotonic() + _RELEASE_TIMEOUT
    while time.monotonic() < deadline:
        if power.lock_held() is False or store.load() is not None:
            return
        time.sleep(0.05)
    raise power.CommandFailedError("the lid lock is still held. Check `wick doctor`.")


def _wait_for_guard(store: SessionStore) -> None:
    deadline = time.monotonic() + _GUARD_START_TIMEOUT
    while time.monotonic() < deadline:
        failure = store.guard_error()
        if failure is not None:
            kind = power.NotAuthorizedError if failure.startswith("logind refused") else power.CommandFailedError
            raise kind(failure)
        if power.sleep_disabled():
            return
        time.sleep(0.05)
    raise power.CommandFailedError("the guard process didn't take the lid lock in time.")
