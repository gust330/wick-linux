"""Session persistence and state transitions for Wick."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable

from wick.battery import Battery


class EndReason(str, Enum):
    TIME_UP = "timeUp"
    AGENTS_FINISHED = "agentsFinished"
    COMMAND_FINISHED = "commandFinished"
    LOW_BATTERY = "lowBattery"
    OVERHEATING = "overheating"
    STOPPED_BY_USER = "stoppedByUser"
    STOPPED_EXTERNALLY = "stoppedExternally"

    @property
    def sentence(self) -> str:
        sentences = {
            EndReason.TIME_UP: "Time's up. Sleep is back to normal.",
            EndReason.AGENTS_FINISHED: "Agents finished. Sleep is back to normal.",
            EndReason.COMMAND_FINISHED: "Command finished. Sleep is back to normal.",
            EndReason.LOW_BATTERY: "Stopped to protect the battery.",
            EndReason.OVERHEATING: "Stopped because the laptop was overheating.",
            EndReason.STOPPED_BY_USER: "Stopped.",
            EndReason.STOPPED_EXTERNALLY: "Sleep was turned back on outside Wick.",
        }
        return sentences.get(self, "Stopped.")


def parse_iso(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    # Python 3.11+ fromisoformat handles standard ISO 8601 strings (including 'Z' and offsets)
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


@dataclass
class Conditions:
    now: datetime
    battery: Battery | None
    is_overheating: bool
    any_held_process_alive: bool


@dataclass
class Session:
    startedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    endsAt: str | None = None
    untilAgentsFinish: bool = False
    heldPIDs: list[int] = field(default_factory=list)
    endsWithHeldProcesses: bool = False
    batteryFloor: int | None = 20
    lastAgentSeen: str | None = None

    AGENT_GRACE: float = 90.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        return cls(
            startedAt=data.get("startedAt", datetime.now(timezone.utc).isoformat()),
            endsAt=data.get("endsAt"),
            untilAgentsFinish=data.get("untilAgentsFinish", False),
            heldPIDs=data.get("heldPIDs", []),
            endsWithHeldProcesses=data.get("endsWithHeldProcesses", False),
            batteryFloor=data.get("batteryFloor", 20),
            lastAgentSeen=data.get("lastAgentSeen"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def end_reason(self, conditions: Conditions) -> EndReason | None:
        """Safety outranks everything else the session asked for."""
        if conditions.is_overheating:
            return EndReason.OVERHEATING

        if self.batteryFloor is not None and conditions.battery is not None:
            if conditions.battery.is_discharging and conditions.battery.percent <= self.batteryFloor:
                return EndReason.LOW_BATTERY

        # A command that's still running outlives the timer
        ends_dt = parse_iso(self.endsAt)
        if ends_dt and conditions.now >= ends_dt and not conditions.any_held_process_alive:
            return EndReason.TIME_UP

        if self.endsWithHeldProcesses and not conditions.any_held_process_alive:
            return EndReason.COMMAND_FINISHED

        if self.untilAgentsFinish and self.lastAgentSeen:
            last_dt = parse_iso(self.lastAgentSeen)
            if last_dt and (conditions.now - last_dt).total_seconds() >= self.AGENT_GRACE:
                return EndReason.AGENTS_FINISHED

        return None


class SessionStore:
    def __init__(self, directory: Path | None = None) -> None:
        if directory is not None:
            self.directory = directory
        else:
            override = os.environ.get("WICK_STATE_DIR")
            if override:
                self.directory = Path(override)
            else:
                xdg_state = os.environ.get("XDG_STATE_HOME")
                base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
                self.directory = base / "wick"

        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def session_path(self) -> Path:
        return self.directory / "session.json"

    @property
    def last_end_path(self) -> Path:
        return self.directory / "last-end.json"

    @property
    def state_lock_path(self) -> Path:
        return self.directory / "state.lock"

    @property
    def guard_lock_path(self) -> Path:
        return self.directory / "guard.lock"

    def with_lock(self, fn: Callable[[], Any]) -> Any:
        lock_fd = os.open(str(self.state_lock_path), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    def load(self) -> Session | None:
        if not self.session_path.exists():
            return None
        try:
            content = self.session_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return Session.from_dict(data)
        except Exception:
            return None

    def has_unreadable_session(self) -> bool:
        if not self.session_path.exists():
            return False
        try:
            content = self.session_path.read_text(encoding="utf-8")
            json.loads(content)
            return False
        except Exception:
            return True

    def save(self, session: Session) -> None:
        temp_file = self.directory / f"session.tmp.{os.getpid()}"
        data = json.dumps(session.to_dict(), indent=2)
        temp_file.write_text(data, encoding="utf-8")
        temp_file.replace(self.session_path)

    def discard_session(self) -> None:
        try:
            self.session_path.unlink(missing_ok=True)
        except OSError:
            pass

    def finish(self, reason: EndReason) -> None:
        record = {
            "reason": reason.value,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            temp_file = self.directory / f"last-end.tmp.{os.getpid()}"
            temp_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            temp_file.replace(self.last_end_path)
        except OSError:
            pass

        self.discard_session()

    def update(self, mutator: Callable[[Session], None]) -> Session | None:
        def _mutate():
            session = self.load()
            if session is None:
                return None
            mutator(session)
            self.save(session)
            return session

        return self.with_lock(_mutate)
