"""DingTalk Calendar via mcporter CLI → Streamable HTTP MCP server.

Setup:
1. `bun install -g mcporter`
2. Go to https://mcp.dingtalk.com/, find "钉钉日程" / "日历" MCP, copy the Streamable HTTP URL
3. Put it in .env as DINGTALK_CALENDAR_MCP_URL

Discovery:
  python src/dingtalk.py discover    # list available tools on the URL
  python src/dingtalk.py list 7      # list events in next 7 days
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional


def _bin() -> str:
    return os.environ.get("MCPORTER_BIN") or os.path.expanduser("~/.bun/bin/mcporter")


def _url() -> Optional[str]:
    return os.environ.get("DINGTALK_CALENDAR_MCP_URL")


def _enabled() -> bool:
    return bool(_url())


def _run(args: list[str], timeout: int = 60) -> dict:
    """Run mcporter and return parsed JSON, or raise with stderr."""
    full = [_bin(), *args]
    proc = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"mcporter failed: {proc.stderr.strip() or proc.stdout.strip()}")
    out = proc.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"_raw": out}


def discover() -> dict:
    """List tools exposed by the configured MCP URL."""
    url = _url()
    if not url:
        raise RuntimeError("DINGTALK_CALENDAR_MCP_URL not set")
    return _run(["list", url, "--schema", "--json"])


def call(tool: str, **params) -> dict:
    """Call a tool against the configured MCP URL.

    `tool` is just the tool name (e.g. "list_events"). The selector becomes
    `<url>.<tool>` per mcporter convention.
    """
    url = _url()
    if not url:
        raise RuntimeError("DINGTALK_CALENDAR_MCP_URL not set")
    args = ["call", url, "--tool", tool]
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        args.append(f"{k}={v}")
    return _run(args)


# ---- High-level helpers (tool names guessed; fix after `discover` reveals real names) ----

CANDIDATE_LIST_TOOLS = ["list_calendar_events", "list_events", "listEvents", "calendar_list_events"]
CANDIDATE_CREATE_TOOLS = ["create_calendar_event", "create_event", "createEvent", "calendar_create_event"]


def _pick_tool(candidates: list[str], available: list[str]) -> Optional[str]:
    for c in candidates:
        if c in available:
            return c
    return None


def busy_intervals(time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    """Pull events between two UTC datetimes. Returns [] if MCP not configured."""
    if not _enabled():
        return []
    schema = discover()
    tools = [t.get("name") for t in schema.get("tools", []) if t.get("name")]
    list_tool = _pick_tool(CANDIDATE_LIST_TOOLS, tools)
    if not list_tool:
        raise RuntimeError(f"Couldn't find list-events tool. Available: {tools}")

    res = call(
        list_tool,
        startTime=int(time_min.timestamp() * 1000),
        endTime=int(time_max.timestamp() * 1000),
    )
    events = (res.get("events") or res.get("data") or
              res.get("body", {}).get("events") or
              res.get("result", {}).get("events") or [])
    busy = []
    for e in events:
        s = (e.get("start") or {}).get("dateTime") or e.get("startDateTime") or e.get("startTime")
        t = (e.get("end") or {}).get("dateTime") or e.get("endDateTime") or e.get("endTime")
        if not s or not t:
            continue
        if isinstance(s, (int, float)):
            s_dt = datetime.fromtimestamp(s / 1000, tz=timezone.utc)
            t_dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        else:
            s_dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            t_dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        busy.append((s_dt, t_dt))
    return busy


def create_event(summary: str, start: datetime, end: datetime,
                 description: str = "", attendee_email: Optional[str] = None) -> dict:
    if not _enabled():
        raise RuntimeError("DINGTALK_CALENDAR_MCP_URL not set")
    schema = discover()
    tools = [t.get("name") for t in schema.get("tools", []) if t.get("name")]
    create_tool = _pick_tool(CANDIDATE_CREATE_TOOLS, tools)
    if not create_tool:
        raise RuntimeError(f"Couldn't find create-event tool. Available: {tools}")

    # DingTalk MCP wants ISO-8601 with offset, e.g. 2025-11-14T10:00:00+08:00
    params = {
        "summary": summary,
        "description": description,
        "startDateTime": start.isoformat(timespec="seconds"),
        "endDateTime": end.isoformat(timespec="seconds"),
    }
    # NOTE: DingTalk attendees are internal userIds, not emails — external invitees
    # ride along through the .ics email instead.
    return call(create_tool, **params)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "discover":
        s = discover()
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif cmd == "list":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        now = datetime.now(timezone.utc)
        evs = busy_intervals(now, now + timedelta(days=days))
        print(json.dumps([(s.isoformat(), e.isoformat()) for s, e in evs], indent=2))
    else:
        print("usage: dingtalk.py {discover|list [days]}", file=sys.stderr)
