"""Microsoft Calendar reminder helper.

Triggered when a meeting participant types in chat:
  SET REMINDER <email> <description>

Strategy: sends an iCalendar (.ics) event as an email attachment via SMTP.
This works with ANY email address (Gmail, Outlook, personal, work) — no
Azure AD or Graph API permissions required. Every major email client
(Gmail, Outlook, Apple Mail) shows an "Add to Calendar" prompt automatically.

Required .env keys (same SMTP creds already used for meeting reports):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
  REMINDER_OFFSET_HOURS  (optional, default 1)
  REMINDER_DURATION_MINS (optional, default 30)
"""

import os
import re
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

REMINDER_COMMAND_RE = re.compile(
    r"(?i)SET\s+REMINDER\s+([\w.+\-]+@[\w.\-]+\.[a-zA-Z]{2,})\s+(.+)",
)


def parse_reminder_command(text: str) -> dict[str, Any] | None:
    match = REMINDER_COMMAND_RE.search(text.strip())
    if not match:
        return None
    return {
        "email": match.group(1).strip(),
        "description": match.group(2).strip(),
    }


def _build_ics(subject: str, description: str, start: datetime, end: datetime) -> str:
    """Build a minimal RFC 5545 iCalendar string."""
    uid = str(uuid.uuid4())
    fmt = "%Y%m%dT%H%M%SZ"
    now = datetime.now(timezone.utc).strftime(fmt)
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Transcriber//Byte by Byte//EN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{subject}",
        f"DESCRIPTION:{description}",
        "BEGIN:VALARM",
        "TRIGGER:PT0S",
        "ACTION:DISPLAY",
        f"DESCRIPTION:Reminder: {subject}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])


def _send_calendar_email(
    to_email: str,
    subject: str,
    body_text: str,
    ics_content: str,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP_USER and SMTP_PASSWORD must be set in .env")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(body_text)

    # Attach the .ics so email clients show "Add to Calendar"
    msg.add_attachment(
        ics_content.encode("utf-8"),
        maintype="text",
        subtype="calendar",
        filename="reminder.ics",
    )
    # Also attach as application/ics for broader compatibility
    msg.add_attachment(
        ics_content.encode("utf-8"),
        maintype="application",
        subtype="ics",
        filename="reminder.ics",
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


def handle_reminder_command(text: str) -> dict[str, Any]:
    """
    Parse SET REMINDER command, send a calendar invite email, return result dict.
    Raises ValueError if command not recognised.
    Raises RuntimeError on SMTP failure.
    """
    parsed = parse_reminder_command(text)
    if parsed is None:
        raise ValueError(f"Not a valid SET REMINDER command: {text!r}")

    email = parsed["email"]
    description = parsed["description"]
    subject = f"Reminder: {description}"

    offset_hours = int(os.getenv("REMINDER_OFFSET_HOURS", "0"))
    offset_mins = int(os.getenv("REMINDER_OFFSET_MINS", "1"))
    duration_mins = int(os.getenv("REMINDER_DURATION_MINS", "30"))

    start_dt = datetime.now(timezone.utc) + timedelta(hours=offset_hours, minutes=offset_mins)
    end_dt = start_dt + timedelta(minutes=duration_mins)

    ics = _build_ics(subject, description, start_dt, end_dt)

    body = (
        f"Hi,\n\n"
        f"A calendar reminder has been set for you from a meeting.\n\n"
        f"📌 {description}\n"
        f"🕐 {start_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"Open the attached .ics file or click 'Add to Calendar' to save this reminder.\n\n"
        f"— Transcriber by Byte by Byte"
    )

    try:
        _send_calendar_email(to_email=email, subject=subject, body_text=body, ics_content=ics)
    except Exception as exc:
        raise RuntimeError(f"Failed to send calendar invite email: {exc}") from exc

    return {
        "email": email,
        "description": description,
        "event_subject": subject,
        "event_start": start_dt.isoformat(),
        "web_link": None,
        "status": "sent",
    }
