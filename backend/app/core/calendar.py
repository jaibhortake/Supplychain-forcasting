"""Weekly calendar helpers. A "week" is identified by its Monday (ISO week start)."""

from datetime import date, timedelta


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_range(start: date, count: int) -> list[date]:
    first = week_start(start)
    return [first + timedelta(weeks=i) for i in range(count)]


def weeks_between(start: date, end: date) -> list[date]:
    """All week starts from start's week up to and including end's week."""
    first, last = week_start(start), week_start(end)
    n = (last - first).days // 7 + 1
    return week_range(first, max(n, 0))


def iso_week_of_year(d: date) -> int:
    """ISO week number, folding the rare week 53 into 52 so yearly profiles have 52 slots."""
    return min(d.isocalendar()[1], 52)


def week_label(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def safe_replace_year(d: date, year: int) -> date:
    """date.replace(year=...) that maps Feb 29 to Feb 28 in non-leap years."""
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)
