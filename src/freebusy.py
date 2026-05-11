"""Find candidate meeting slots in Hunter's preferred window: 14:00-18:00 America/Los_Angeles.

This is a hard preference (see feedback memory): all meetings default to Bay Area
afternoon regardless of Hunter's local timezone or contact's timezone. The contact's
TZ is only used for display formatting, not slot generation.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PREFERRED_TZ = ZoneInfo("America/Los_Angeles")
PREFERRED_START = time(14, 0)  # 2 PM PT
PREFERRED_END = time(18, 0)    # 6 PM PT
SLOT_MINUTES = 30
LOOKAHEAD_DAYS = 14            # widened so we can skip weekends + busy days


def _preferred_window(d: date) -> tuple[datetime, datetime]:
    """Return (start, end) in PT for date d's preferred window."""
    return (datetime.combine(d, PREFERRED_START, tzinfo=PREFERRED_TZ),
            datetime.combine(d, PREFERRED_END, tzinfo=PREFERRED_TZ))


def _subtract_busy(window: tuple[datetime, datetime],
                   busy: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    free = [window]
    for bs, be in busy:
        new_free = []
        for fs, fe in free:
            if be <= fs or bs >= fe:
                new_free.append((fs, fe))
                continue
            if bs > fs:
                new_free.append((fs, bs))
            if be < fe:
                new_free.append((be, fe))
        free = new_free
    return free


def find_slots(
    my_tz: str,
    their_tz: str,
    busy: list[tuple[datetime, datetime]],
    n: int = 3,
    duration_min: int = 30,
) -> list[tuple[datetime, datetime]]:
    """Return up to n (start, end) tuples in PT, one per business day."""
    today_pt = datetime.now(PREFERRED_TZ).date()
    candidates: list[tuple[datetime, datetime]] = []
    days_used: set[date] = set()

    for day_offset in range(1, LOOKAHEAD_DAYS + 1):
        if len(candidates) >= n:
            break
        d_pt = today_pt + timedelta(days=day_offset)
        if d_pt.weekday() >= 5:  # skip Sat/Sun in PT
            continue

        window = _preferred_window(d_pt)
        free_blocks = _subtract_busy(window, busy)

        for fs, fe in free_blocks:
            if d_pt in days_used:
                break
            slot_end = fs + timedelta(minutes=duration_min)
            if slot_end <= fe:
                candidates.append((fs, slot_end))
                days_used.add(d_pt)
                break  # one per day

    return candidates


def fmt_slot_bilingual(slot: tuple[datetime, datetime], my_tz: str, their_tz: str) -> str:
    s, e = slot
    my = ZoneInfo(my_tz)
    their = ZoneInfo(their_tz)
    return (
        f"{s.astimezone(PREFERRED_TZ).strftime('%a %b %d, %H:%M')}-"
        f"{e.astimezone(PREFERRED_TZ).strftime('%H:%M')} (Bay Area) | "
        f"{s.astimezone(their).strftime('%a %H:%M')} ({their_tz.split('/')[-1].replace('_', ' ')}) | "
        f"{s.astimezone(my).strftime('%a %H:%M')} ({my_tz.split('/')[-1].replace('_', ' ')})"
    )


if __name__ == "__main__":
    import sys
    my_tz = sys.argv[1] if len(sys.argv) > 1 else "Asia/Shanghai"
    their_tz = sys.argv[2] if len(sys.argv) > 2 else "America/New_York"
    slots = find_slots(my_tz, their_tz, busy=[])
    for s in slots:
        print(fmt_slot_bilingual(s, my_tz, their_tz))
