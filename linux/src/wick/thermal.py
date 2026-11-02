"""Thermal protection, from sysfs.

Stopping too eagerly has a real cost: the laptop suspends in the middle of the build it was kept awake for. CPUs run
at 95°C under load as a matter of course, and many laptops define a "hot" trip point well below danger, so neither
of those counts. This looks for a sensor at its critical limit, and only believes it once that has lasted.

Both places matter: thermal zones have the trip points the kernel shuts down at, and hwmon has the CPU's own sensors,
like coretemp, where the critical limit is the point the chip throttles at. Sitting there with the lid closed is
the bag scenario this exists for, so hwmon counts closer to its limit than a zone does.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Callable

from wick.battery import sysfs_root

_ZONE_MARGIN_C = 3.0
_HWMON_MARGIN_C = 1.0
_NO_LIMIT_CEILING_C = 105.0
_SUSTAINED_SECONDS = 30.0
# Sensors report 0, -273 and 255 when they aren't really reading anything.
_PLAUSIBLE_C = (1.0, 150.0)


@dataclass(frozen=True)
class Zone:
    name: str
    temperature: float
    critical: float | None
    margin: float = _ZONE_MARGIN_C

    @property
    def is_too_hot(self) -> bool:
        if self.critical is not None:
            return self.temperature >= self.critical - self.margin
        return self.temperature >= _NO_LIMIT_CEILING_C


def _millidegrees(path: Path) -> float | None:
    try:
        value = float(path.read_text(encoding="utf-8").strip()) / 1000.0
    except (OSError, ValueError):
        return None
    return value if _PLAUSIBLE_C[0] <= value <= _PLAUSIBLE_C[1] else None


def _text(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return fallback


def zones() -> list[Zone]:
    found = []
    for zone in sorted((sysfs_root() / "class" / "thermal").glob("thermal_zone*")):
        temperature = _millidegrees(zone / "temp")
        if temperature is None:
            continue
        critical = None
        for type_file in zone.glob("trip_point_*_type"):
            if _text(type_file, "").lower() == "critical":
                critical = _millidegrees(zone / type_file.name.replace("_type", "_temp"))
        found.append(Zone(_text(zone / "type", zone.name), temperature, critical))

    for monitor in sorted((sysfs_root() / "class" / "hwmon").glob("hwmon*")):
        name = _text(monitor / "name", monitor.name)
        for sensor in sorted(monitor.glob("temp*_input")):
            temperature = _millidegrees(sensor)
            if temperature is None:
                continue
            critical = _millidegrees(monitor / sensor.name.replace("_input", "_crit"))
            found.append(Zone(name, temperature, critical, _HWMON_MARGIN_C))
    return found


def simulated_overheating() -> bool | None:
    value = os.environ.get("WICK_SIMULATE_THERMAL")
    return value.lower() in ("1", "true", "critical", "overheating") if value else None


class Monitor:
    """Goes by how long it has lasted, so a spike or a bad sample doesn't end a session, however often it's asked."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hot_since: float | None = None

    def is_overheating(self) -> bool:
        simulated = simulated_overheating()
        if simulated is not None:
            return simulated
        if not any(zone.is_too_hot for zone in zones()):
            self._hot_since = None
            return False
        now = self._clock()
        if self._hot_since is None:
            self._hot_since = now
        return now - self._hot_since >= _SUSTAINED_SECONDS
