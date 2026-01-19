"""
Datetime Utilities
Shared module for consistent datetime handling across all systems
Uses Eastern Time (America/New_York) as the standard timezone
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Standard timezone for the restaurant system
TIMEZONE = ZoneInfo("America/New_York")


def now() -> datetime:
    """
    Get current datetime in Eastern Time

    Returns:
        datetime: Current time in America/New_York timezone
    """
    return datetime.now(TIMEZONE)


def today() -> datetime:
    """
    Get today's date at midnight in Eastern Time

    Returns:
        datetime: Today at 00:00:00 in America/New_York timezone
    """
    return datetime.now(TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
