from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def today_ist() -> str:
    return now_ist().date().isoformat()


def is_business_hours_ist(start_hour: int, end_hour: int) -> bool:
    current = now_ist().time()
    return time(start_hour, 0) <= current < time(end_hour, 0)


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
