"""Timezone utilities for BrainBets.

All user-facing date operations should use America/Bogota (UTC-5)
to ensure consistent date handling across frontend, backend, and workflows.
"""
from datetime import datetime, timezone, timedelta, date

# America/Bogota is UTC-5 (no DST)
BOGOTA_TZ = timezone(timedelta(hours=-5))


def now_bogota() -> datetime:
    """Get current datetime in America/Bogota timezone."""
    return datetime.now(BOGOTA_TZ)


def today_bogota() -> date:
    """Get today's date in America/Bogota timezone."""
    return now_bogota().date()


def today_start_bogota() -> datetime:
    """Get start of today (00:00:00) in America/Bogota timezone."""
    return now_bogota().replace(hour=0, minute=0, second=0, microsecond=0)


def yesterday_start_bogota() -> datetime:
    """Get start of yesterday (00:00:00) in America/Bogota timezone."""
    return today_start_bogota() - timedelta(days=1)


def tomorrow_start_bogota() -> datetime:
    """Get start of tomorrow (00:00:00) in America/Bogota timezone."""
    return today_start_bogota() + timedelta(days=1)
