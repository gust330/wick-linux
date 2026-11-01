"""Battery state detection for Linux systems."""

from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Battery:
    percent: int
    is_discharging: bool

    @classmethod
    def current(cls) -> Battery | None:
        """Reads battery capacity and status from /sys/class/power_supply/BAT*."""
        # Support simulation for unit tests / e2e tests
        sim_bat = os.environ.get("WICK_SIMULATE_BATTERY")
        if sim_bat:
            try:
                parts = sim_bat.split(",")
                p = int(parts[0])
                dis = parts[1].strip().lower() == "discharging" if len(parts) > 1 else False
                return cls(percent=p, is_discharging=dis)
            except Exception:
                pass

        # In simulated power test harness, default to healthy AC power unless low battery is explicitly tested
        if os.environ.get("WICK_SIMULATE_POWER_FILE") and not sim_bat:
            return cls(percent=80, is_discharging=False)

        power_supply = Path("/sys/class/power_supply")
        if not power_supply.exists():
            return None

        # Look for standard batteries (BAT0, BAT1, etc.)
        candidates = sorted(power_supply.glob("BAT*"))
        for bat in candidates:
            cap_file = bat / "capacity"
            status_file = bat / "status"
            if cap_file.exists() and status_file.exists():
                try:
                    percent = int(cap_file.read_text().strip())
                    status = status_file.read_text().strip().lower()
                    is_discharging = status == "discharging"
                    return cls(percent=percent, is_discharging=is_discharging)
                except (ValueError, OSError):
                    continue

        return None
