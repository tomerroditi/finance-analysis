from datetime import date

from dateutil.relativedelta import relativedelta


def get_all_months(start_date: date, future_months: int = 0) -> list[date]:
    """Generate list of first-of-month dates from start_date to now."""
    current = start_date.replace(day=1)
    end = date.today().replace(day=1) + relativedelta(months=future_months)
    months = []
    while current <= end:
        months.append(current)
        current += relativedelta(months=1)
    return months
