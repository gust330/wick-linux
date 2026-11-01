"""Core orchestration coordinating power, session state, and the guard daemon."""

from __future__ import annotations
from wick import guard, power
from wick.session import EndReason, Session, SessionStore


class Wick:
    @staticmethod
    def start(session: Session, executable: str, store: SessionStore | None = None) -> None:
        if store is None:
            store = SessionStore()

        def _setup():
            running_session = store.load()
            if running_session:
                for pid in running_session.heldPIDs:
                    if pid not in session.heldPIDs:
                        session.heldPIDs.append(pid)
            store.save(session)
            power.set_sleep_disabled(True)

        store.with_lock(_setup)

        try:
            guard.spawn(executable)
        except Exception:
            try:
                Wick.stop(EndReason.STOPPED_EXTERNALLY, store=store)
            except Exception:
                pass
            raise

    @staticmethod
    def stop(reason: EndReason = EndReason.STOPPED_BY_USER, store: SessionStore | None = None) -> None:
        if store is None:
            store = SessionStore()

        def _cleanup():
            power.set_sleep_disabled(False)
            store.finish(reason)

        store.with_lock(_cleanup)

    @staticmethod
    def reconcile(executable: str, store: SessionStore | None = None) -> bool:
        """Picks up a session whose guard died or cleans up broken state."""
        if store is None:
            store = SessionStore()

        def _check() -> bool:
            if store.has_unreadable_session():
                try:
                    power.set_sleep_disabled(False)
                except Exception:
                    pass
                store.finish(EndReason.STOPPED_EXTERNALLY)
                return False

            session = store.load()
            if session is None:
                return False

            if not power.sleep_disabled():
                store.finish(EndReason.STOPPED_EXTERNALLY)
                return False

            return True

        needs_guard = store.with_lock(_check)
        if needs_guard:
            try:
                guard.spawn(executable)
                return True
            except Exception:
                return False
        return False
