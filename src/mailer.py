"""Send a calendar invite via SMTP. multipart/mixed with text/plain + text/calendar + .ics attachment."""
from __future__ import annotations

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid


def send_invite(
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    ics_content: str,
    dry_run: bool = False,
) -> dict:
    from_email = os.environ["SMTP_USER"]
    from_name = os.environ.get("SMTP_FROM_NAME", from_email)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = formataddr((to_name, to_email))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[1])

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    cal_part = MIMEText(ics_content, "calendar; method=REQUEST; charset=UTF-8", "utf-8")
    cal_part.add_header("Content-Class", "urn:content-classes:calendarmessage")
    alt.attach(cal_part)
    msg.attach(alt)

    ics_attach = MIMEApplication(ics_content.encode("utf-8"), _subtype="ics", name="invite.ics")
    ics_attach.add_header("Content-Disposition", "attachment", filename="invite.ics")
    msg.attach(ics_attach)

    if dry_run:
        return {"dry_run": True, "raw": msg.as_string()[:800] + "..."}

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(from_email, os.environ["SMTP_PASS"])
        s.sendmail(from_email, [to_email], msg.as_string())
    return {"sent": True, "to": to_email, "subject": subject}
