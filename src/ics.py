"""Build a minimal RFC 5545 .ics file by hand. Tested in Gmail / Apple Mail / Outlook."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _fold(line: str) -> str:
    # RFC 5545 line folding: 75 octets max
    out = []
    while len(line.encode()) > 75:
        cut = 73
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    organizer_name: str,
    organizer_email: str,
    attendee_email: str,
    attendee_name: str = "",
    location: str = "Online (Zoom/Tencent Meeting link to follow)",
    method: str = "REQUEST",
) -> str:
    uid = f"{uuid.uuid4()}@wx-schedule"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wx-schedule//EN",
        f"METHOD:{method}",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(start)}",
        f"DTEND:{_utc(end)}",
        _fold(f"SUMMARY:{_esc(summary)}"),
        _fold(f"DESCRIPTION:{_esc(description)}"),
        _fold(f"LOCATION:{_esc(location)}"),
        _fold(f"ORGANIZER;CN={_esc(organizer_name)}:mailto:{organizer_email}"),
        _fold(
            f"ATTENDEE;CN={_esc(attendee_name or attendee_email)};"
            f"RSVP=TRUE;PARTSTAT=NEEDS-ACTION;ROLE=REQ-PARTICIPANT:mailto:{attendee_email}"
        ),
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        "DESCRIPTION:Reminder",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
