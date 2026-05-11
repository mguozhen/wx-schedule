# wx-schedule

Local CLI: WeChat screenshot → DingTalk free-slot lookup → .ics calendar invite over SMTP.

## Setup

```bash
cd ~/wx-schedule
cp .env.example .env  # fill in keys
.venv/bin/python src/schedule.py fixtures/mason.png
```

## Flow

1. `parse.py` — Claude vision reads the WeChat screenshot, extracts sender / email / city / intent.
2. `freebusy.py` — pulls your DingTalk events for the next 7 days, intersects with both parties' working hours (09:00-18:00 each TZ), returns 3 candidate 30-min slots.
3. `ics.py` + `mailer.py` — builds an RFC 5545 .ics, sends multipart email via Gmail SMTP. Recipient's mail client surfaces "Add to calendar".
4. `dingtalk.py` — writes the chosen slot back into your DingTalk calendar.

No SaaS dependencies beyond Anthropic API + your own SMTP + DingTalk OpenAPI.
