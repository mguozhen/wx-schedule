"""Main CLI: WeChat screenshot → calendar invite emailed to the contact.

Usage:
  python src/schedule.py <screenshot.png>             # interactive
  python src/schedule.py <screenshot.png> --dry-run   # build, don't send / don't write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Load .env
ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(ROOT / "src"))
from parse import parse_screenshot
from freebusy import find_slots, fmt_slot_bilingual
import dingtalk
from ics import build_ics
from mailer import send_invite


def pick_slot(slots: list, my_tz: str, their_tz: str) -> int:
    print("\n候选时段（已避开你钉钉日程上的占用）:\n")
    for i, slot in enumerate(slots, 1):
        print(f"  [{i}] {fmt_slot_bilingual(slot, my_tz, their_tz)}")
    print()
    while True:
        choice = input(f"选哪个? (1-{len(slots)}, q 退出): ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(slots):
            return int(choice) - 1
        print("无效选择, 重试")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("screenshot")
    ap.add_argument("--dry-run", action="store_true", help="don't send email or write to DingTalk")
    ap.add_argument("--duration", type=int, default=30, help="meeting length in minutes")
    args = ap.parse_args()

    my_tz = os.environ.get("MY_TZ", "Asia/Shanghai")
    my_name = os.environ.get("MY_NAME", "Hunter")
    my_email = os.environ.get("MY_EMAIL", os.environ.get("SMTP_USER", ""))

    print(f"→ Parsing {args.screenshot} ...")
    intent = parse_screenshot(args.screenshot)
    print(json.dumps(intent, ensure_ascii=False, indent=2))

    if intent.get("intent") != "meeting":
        print("\n⚠️  解析结果不是 meeting 请求, 退出.")
        return 1
    if not intent.get("contact_email"):
        print("\n⚠️  对方没给邮箱, 无法发送日历邀请. 改用文字回复吧.")
        return 1

    their_tz = intent.get("contact_tz") or "Asia/Shanghai"
    print(f"\n→ 时区: 你 {my_tz} ↔ 对方 {their_tz}")

    print("→ 拉钉钉日程...")
    now = datetime.now(timezone.utc)
    busy = dingtalk.busy_intervals(now, now + timedelta(days=8))
    print(f"   {len(busy)} 个事件占用" if dingtalk._enabled() else "   (DingTalk 未配置, 跳过 busy 检查)")

    slots = find_slots(my_tz, their_tz, busy, n=3, duration_min=args.duration)
    if not slots:
        print("⚠️  未来 7 天找不到双方都合适的时段.")
        return 1

    idx = pick_slot(slots, my_tz, their_tz)
    start, end = slots[idx]

    summary = f"{my_name} × {intent['contact_name']} — {intent.get('summary', 'intro chat')[:60]}"

    # Step 1: create DingTalk event FIRST so we can extract the meeting URL + room code
    meeting_url = ""
    meeting_code = ""
    if dingtalk._enabled() and not args.dry_run:
        print("\n→ Creating DingTalk event (to obtain meeting URL) ...")
        ev = dingtalk.create_event(
            summary=summary, start=start, end=end,
            description=intent.get("summary", ""),
            attendee_email=intent["contact_email"],
        )
        # response shape: {"result": {"onlineMeetingInfo": {"extraInfo": {"extraUrl": ..., "roomCode": ...}}}}
        try:
            info = ev.get("result", {}).get("onlineMeetingInfo", {}).get("extraInfo", {})
            meeting_url = info.get("extraUrl") or ""
            meeting_code = info.get("roomCode") or ""
        except Exception:
            pass
        print(f"   meeting URL: {meeting_url or '(not available)'}")

    # Step 2: build description + .ics + email body using meeting_url if we have it
    join_line = (
        f"Join: {meeting_url}\n  Room code: {meeting_code}\n"
        if meeting_url else
        "I'll send a Zoom/Tencent Meeting link before we start."
    )
    description = (
        f"线上会议\n\n"
        f"约见缘由: {intent.get('summary', '')}\n\n"
        f"时间:\n"
        f"  {my_tz}: {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')}\n"
        f"  {their_tz}: {start.astimezone(ZoneInfo(their_tz)).strftime('%Y-%m-%d %H:%M')}\n\n"
        f"{join_line}\n"
        f"如需改时, 直接回复本邮件即可."
    )

    ics_content = build_ics(
        summary=summary,
        description=description,
        start=start,
        end=end,
        organizer_name=my_name,
        organizer_email=my_email,
        attendee_email=intent["contact_email"],
        attendee_name=intent["contact_name"],
        location=meeting_url or "Online (link to follow)",
    )

    out_ics = ROOT / "out" / f"{intent['contact_name'].replace(' ', '_')}_{start.strftime('%Y%m%d_%H%M')}.ics"
    out_ics.parent.mkdir(exist_ok=True)
    out_ics.write_text(ics_content)
    print(f"\n→ ICS written: {out_ics}")

    body_text = (
        f"Hi {intent['contact_name'].split()[0]},\n\n"
        f"Following up from WeChat — let's lock in a time. I've attached a calendar invite for:\n\n"
        f"  • {start.astimezone(ZoneInfo(their_tz)).strftime('%A, %b %d at %H:%M')} {their_tz.split('/')[-1].replace('_', ' ')}\n"
        f"  • {start.strftime('%A, %b %d at %H:%M')} {my_tz.split('/')[-1].replace('_', ' ')}\n\n"
        f"{join_line}\n"
        f"If this slot doesn't work, just reply with a couple of times that suit you and I'll resend.\n\n"
        f"Talk soon,\n{my_name}"
    )
    subject = f"Calendar invite: {my_name} × {intent['contact_name'].split()[0]} chat"

    print(f"\n→ Sending email to {intent['contact_email']} ...")
    result = send_invite(
        to_email=intent["contact_email"],
        to_name=intent["contact_name"],
        subject=subject,
        body_text=body_text,
        ics_content=ics_content,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:400])

    print("\n✓ Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
