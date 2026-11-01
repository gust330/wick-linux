"""Duration parsing and clock formatting for Wick."""

from __future__ import annotations
import math
import re

VERSION = "0.1.0"


def parse(text: str) -> float | None:
    """Accepts '90', '90m', '2h', '1h30m', and '45s'. A bare number means minutes."""
    text = text.strip().lower()
    if not text:
        return None

    # Bare number means minutes
    try:
        minutes = float(text)
        return minutes * 60.0 if minutes > 0 else None
    except ValueError:
        pass

    pattern = re.compile(r"^(\d+)(h|m|s)")
    total = 0.0
    remainder = text

    while remainder:
        match = pattern.match(remainder)
        if not match:
            return None
        val_str, unit = match.groups()
        val = float(val_str)
        if unit == "h":
            total += val * 3600.0
        elif unit == "m":
            total += val * 60.0
        elif unit == "s":
            total += val * 1.0
        remainder = remainder[match.end():]

    return total if total > 0 else None


def clock(interval: float) -> str:
    """Formatted like '1:42:09', or '42:09' under an hour."""
    seconds = max(0, int(math.ceil(interval)))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    rest = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{rest:02d}"
    return f"{minutes:02d}:{rest:02d}"


def compact(interval: float) -> str:
    """Formatted like '2h 05m', '42m', or '<1m'."""
    if interval < 60:
        return "<1m"
    minutes = int(math.ceil(interval / 60.0))
    hours = minutes // 60
    rem_min = minutes % 60
    if hours > 0:
        return f"{hours}h {rem_min:02d}m"
    return f"{minutes}m"
