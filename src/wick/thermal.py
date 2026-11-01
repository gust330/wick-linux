"""Thermal monitoring for Linux laptops."""

from __future__ import annotations
import os
from pathlib import Path


def is_overheating(default_critical_temp_c: float = 95.0) -> bool:
    """Returns True if any thermal zone reports critical temperature or exceeds safety limits."""
    # Test simulation support
    sim_thermal = os.environ.get("WICK_SIMULATE_THERMAL")
    if sim_thermal:
        return sim_thermal.lower() in ("1", "true", "critical", "overheating")

    thermal_dir = Path("/sys/class/thermal")
    if not thermal_dir.exists():
        return False

    for zone in thermal_dir.glob("thermal_zone*"):
        temp_file = zone / "temp"
        if not temp_file.exists():
            continue

        try:
            current_temp = float(temp_file.read_text().strip()) / 1000.0
        except (ValueError, OSError):
            continue

        # Check zone trip points for explicitly defined critical thresholds
        for trip_type_file in zone.glob("trip_point_*_type"):
            try:
                trip_type = trip_type_file.read_text().strip().lower()
                if trip_type in ("critical", "hot"):
                    trip_temp_file = zone / trip_type_file.name.replace("_type", "_temp")
                    if trip_temp_file.exists():
                        trip_temp = float(trip_temp_file.read_text().strip()) / 1000.0
                        if current_temp >= trip_temp:
                            return True
            except (ValueError, OSError):
                continue

        # Fallback ceiling check (default 95°C)
        if current_temp >= default_critical_temp_c:
            return True

    return False
