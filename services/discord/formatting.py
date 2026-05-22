"""
Shared formatting utilities.

All timestamps across the entire project use the format:
    D-M-YY@H:MM:SS AM/PM

Examples:
    1-12-26@6:45:20 PM
    15-3-27@11:00:00 AM
"""

from __future__ import annotations

from datetime import datetime


def format_timestamp(dt: datetime) -> str:
    """
    Convert a datetime to the project-standard format.

    Format: D-M-YY@H:MM:SS AM/PM
        D  = day of month, no leading zero
        M  = month, no leading zero
        YY = two-digit year
        H  = hour (12h), no leading zero
        MM = minute, zero-padded
        SS = second, zero-padded
        AM/PM

    Examples:
        datetime(2026, 12, 1, 18, 45, 20) → "1-12-26@6:45:20 PM"
        datetime(2027, 3, 15, 11, 0, 0)   → "15-3-27@11:00:00 AM"
    """
    day = dt.day                          # no leading zero
    month = dt.month                      # no leading zero
    year = dt.strftime("%y")              # two-digit year

    # 12-hour clock without leading zero
    hour_24 = dt.hour
    am_pm = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12

    minute = dt.strftime("%M")           # zero-padded
    second = dt.strftime("%S")           # zero-padded

    return f"{day}-{month}-{year}@{hour_12}:{minute}:{second} {am_pm}"


def format_timestamp_filesafe(dt: datetime) -> str:
    """
    Same format as format_timestamp but replaces characters
    that are illegal in filenames on Windows.

    Replaces : with - and spaces with _

    Example:
        datetime(2026, 12, 1, 18, 45, 20) → "1-12-26@6-45-20_PM"
    """
    raw = format_timestamp(dt)
    return raw.replace(":", "-").replace(" ", "_")
