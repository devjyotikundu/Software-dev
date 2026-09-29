"""Weekly availability overlap across time zones.

Each person's slots are stored as local weekday + times. To compare two
people, both are converted to minutes-of-the-week in UTC for a reference
week (so daylight-saving time is handled for that week), then intersected.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

WEEK = 7 * 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def reference_monday(today=None):
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def to_utc_intervals(slots, tz_name, monday):
    """[(weekday, start_time, end_time)] in ``tz_name`` -> merged [(start, end)] UTC minutes of week."""
    tz = ZoneInfo(tz_name)
    week_start = datetime.combine(monday, datetime.min.time(), tzinfo=dt_timezone.utc)
    intervals = []
    for weekday, start, end in slots:
        day = monday + timedelta(days=weekday)
        local_start = datetime.combine(day, start, tzinfo=tz)
        local_end = datetime.combine(day, end, tzinfo=tz)
        a = int((local_start - week_start).total_seconds() // 60) % WEEK
        length = int((local_end - local_start).total_seconds() // 60)
        b = a + length
        if b <= WEEK:
            intervals.append((a, b))
        else:  # wraps past the end of the week
            intervals += [(a, WEEK), (0, b - WEEK)]
    return merge(intervals)


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def intersect(a, b):
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            out.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def total_minutes(intervals):
    return sum(end - start for start, end in intervals)


def describe_window(interval, tz_name, monday):
    """One overlap window in the viewer's local time, e.g. ("Monday", "18:00", "20:00")."""
    week_start = datetime.combine(monday, datetime.min.time(), tzinfo=dt_timezone.utc)
    tz = ZoneInfo(tz_name)
    start = (week_start + timedelta(minutes=interval[0])).astimezone(tz)
    end = (week_start + timedelta(minutes=interval[1])).astimezone(tz)
    return WEEKDAYS[start.weekday()], start.strftime("%H:%M"), end.strftime("%H:%M")
