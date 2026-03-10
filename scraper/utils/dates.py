from datetime import date, datetime
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

_ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def utc_to_israel_date_str(timestamp: str) -> str:
    """Convert a UTC ISO timestamp to an Israel-local YYYY-MM-DD date string."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return dt.astimezone(_ISRAEL_TZ).strftime("%Y-%m-%d")


def get_all_months(start_date: date, future_months: int = 0) -> list[date]:
    """Generate list of first-of-month dates from start_date to now."""
    current = start_date.replace(day=1)
    end = date.today().replace(day=1) + relativedelta(months=future_months)
    months = []
    while current <= end:
        months.append(current)
        current += relativedelta(months=1)
    return months
