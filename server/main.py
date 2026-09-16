"""Meeting transcript analysis and email delivery service.

Run locally with: uvicorn main:app --reload --port 8080
"""

import html
import json
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from openrouter import OpenRouter
from github_issues import handle_issue_command, ISSUE_COMMAND_RE
from calendar_reminder import handle_reminder_command, REMINDER_COMMAND_RE

# Server-side idempotency: track commands already executed this process lifetime.
# Prevents duplicate API calls when the extension sends the same command multiple times.
_executed_commands: dict[str, dict] = {}

load_dotenv(Path(__file__).with_name(".env"))

REQUIRED_RECIPIENT = os.getenv("SMTP_USER", "vishalkumar09837@gmail.com")
MODEL = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-small-3.1-24b-instruct")

app = FastAPI(title="Transcriber meeting analyst")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class MeetingPayload(BaseModel):
    meetingTitle: str = "Meeting"
    meetingSoftware: str = "Google Meet"
    meetingStartTimestamp: str | None = None
    meetingEndTimestamp: str | None = None
    transcript: str | list[dict[str, Any]]
    chatMessages: str | list[dict[str, Any]] = Field(default_factory=list)


def blocks_to_text(value: str | list[dict[str, Any]], text_key: str) -> str:
    if isinstance(value, str):
        return value.strip()
    lines = []
    for item in value:
        speaker = item.get("personName", "Unknown")
        content = item.get(text_key, "")
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def extract_json(text: str) -> dict[str, Any]:
    """Accept JSON even if the model wraps it in a Markdown code fence."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise ValueError("The model did not return a JSON report")
        return json.loads(match.group(0))


def extract_links(text: str) -> list[str]:
    """Return all unique URLs found in the given text, in order of appearance."""
    url_pattern = re.compile(r"https?://[^\s\"'<>)\]]+")
    return list(dict.fromkeys(url_pattern.findall(text)))


def analyze(transcript: str, chat: str, title: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(500, "OPENROUTER_API_KEY is not configured")

    links = extract_links(chat) if chat else []
    links_section = (
        "Links shared in chat:\n" + "\n".join(f"- {link}" for link in links)
        if links
        else "Links shared in chat: None"
    )

    prompt = f"""You are an expert meeting analyst. Analyse the transcript below and produce a structured, actionable report.

STRICT RULES:
- Speaker labels (e.g. "Alice", "Bob") are participant names captured automatically. Use them as-is when attributing action items. Do NOT describe participants by role or identity unless the transcript explicitly states it.
- Do NOT invent decisions, owners, dates, or commitments that are not present in the transcript.
- If a field has no relevant content, return an empty array [] — never fill it with placeholder text.
- summary: 2-4 sentences covering WHAT was discussed, any concrete outcomes, and overall tone/progress. Be specific to this meeting's content.
- key_points: the most important factual statements or discussion points (3-7 items).
- decisions: only conclusions the group explicitly agreed on.
- action_items: only tasks someone explicitly committed to. Each must have: owner (exact speaker name, or "Not specified"), action (what they will do), due_date (if mentioned, else "Not specified").
- risks_or_open_questions: unresolved issues, blockers, or questions raised but not answered.
- insights: 1-3 higher-level observations about meeting quality, participation balance, or strategic implications.

Return ONLY valid JSON with exactly these keys:
  summary (string),
  key_points (array of strings),
  decisions (array of strings),
  action_items (array of objects with owner, action, due_date),
  risks_or_open_questions (array of strings),
  insights (array of strings)

Meeting title: {title}

Transcript:
{transcript}

Chat messages:
{chat or "None"}

{links_section}
"""
    try:
        with OpenRouter(api_key=api_key) as client:
            response = client.chat.send(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2400,
            )
        content = response.choices[0].message.content
        return extract_json(content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"OpenRouter analysis failed: {exc}") from exc


def list_html(items: list[Any], empty: str = "None identified") -> str:
    if not items:
        return f'<p style="font-size:14px;color:#aaaaaa;font-style:italic;margin:0">{html.escape(empty)}</p>'
    return (
        '<ul style="padding-left:20px;margin:0">'
        + "".join(f'<li style="margin:6px 0;font-size:14px;color:#444444;line-height:1.6">{html.escape(str(item))}</li>' for item in items)
        + "</ul>"
    )


def _github_issues_html(issues: list[dict[str, Any]]) -> str:
    """Render the GitHub issues table block for the email."""
    if not issues:
        return ""
    rows = ""
    for issue in issues:
        num = html.escape(str(issue.get("issue_number", "")))
        title = html.escape(str(issue.get("title", "")))
        url = html.escape(str(issue.get("issue_url", "")))
        repo = html.escape(str(issue.get("repo", "")))
        assignees = ", ".join(
            f"@{html.escape(a)}" for a in issue.get("assignees", [])
        )
        status = html.escape(str(issue.get("status", "created")))
        link = f'<a href="{url}" style="color:#0066cc;text-decoration:underline">#{num}</a>' if url else f"#{num}"
        rows += (
            f'<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#333333;vertical-align:top">{link} &mdash; {title}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#555555;vertical-align:top">{repo}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#555555;vertical-align:top">{assignees}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:13px;color:#22863a;font-weight:700;vertical-align:top;white-space:nowrap">{status}</td>'
            f'</tr>'
        )
    return (
        '<p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;'
        'margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">GitHub Issues Created</p>'
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 28px 0;border-collapse:collapse">'
        '<thead><tr bgcolor="#f7f7f7" style="background-color:#f7f7f7">'
        '<th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Issue</th>'
        '<th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Repo</th>'
        '<th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Assignees</th>'
        '<th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Status</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
    )


def report_html(payload: MeetingPayload, report: dict[str, Any], links: list[str] | None = None, github_issues: list[dict[str, Any]] | None = None, reminders: list[dict[str, Any]] | None = None) -> str:
    actions = report.get("action_items", [])
    rows = "".join(
        '<tr><td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#333333;vertical-align:top">{}</td>'
        '<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#333333;vertical-align:top">{}</td>'
        '<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#999999;vertical-align:top;white-space:nowrap">{}</td></tr>'.format(
            html.escape(str(item.get("owner", "Not specified"))),
            html.escape(str(item.get("action", "Not specified"))),
            html.escape(str(item.get("due_date", "Not specified"))),
        )
        for item in actions if isinstance(item, dict)
    ) or '<tr><td colspan="3" style="padding:10px 12px;font-size:14px;color:#aaaaaa;font-style:italic">No action items identified</td></tr>'

    meeting_date = payload.meetingStartTimestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    insights = report.get("insights", [])
    insights_html = f"<h2>Insights</h2>{list_html(insights)}" if insights else ""

    links_html = ""
    if links:
        links_html = "<h2>Links shared in chat</h2><ul>" + "".join(
            f'<li><a href="{html.escape(link)}" style="color:#167aa5">{html.escape(link)}</a></li>'
            for link in links
        ) + "</ul>"

    return f"""<!doctype html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meeting Report — {html.escape(payload.meetingTitle)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
  body,table,td,p,a{{font-family:Arial,Helvetica,sans-serif;margin:0;padding:0}}
  body{{background-color:#ffffff!important;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}}
  table{{border-spacing:0;mso-table-lspace:0pt;mso-table-rspace:0pt}}
  img{{border:0;line-height:100%;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}}
  .muted{{color:#999999;font-style:italic}}
  ul{{padding-left:20px;margin:6px 0}}
  li{{margin:6px 0;color:#444444;font-size:14px;line-height:1.6}}
  @media only screen and (max-width:600px){{
    .email-wrapper{{width:100%!important}}
    .email-body{{padding:24px 20px!important}}
    .email-header{{padding:28px 20px!important}}
    .email-footer{{padding:16px 20px!important}}
  }}
</style>
</head>
<body bgcolor="#ffffff" style="background-color:#ffffff;margin:0;padding:0">

<!-- Outer wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#ffffff" style="background-color:#ffffff">
<tr><td align="center" style="padding:32px 16px">

  <!-- Card -->
  <table class="email-wrapper" width="600" cellpadding="0" cellspacing="0"
         style="background-color:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e5e5;box-shadow:0 2px 16px rgba(0,0,0,.06)">

    <!-- Header -->
    <tr>
      <td class="email-header" bgcolor="#0a0a0a"
          style="background-color:#0a0a0a;padding:36px 40px;border-radius:12px 12px 0 0">
        <p style="font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:#555555;margin:0 0 10px 0">
          Meeting Intelligence &mdash; Transcriber
        </p>
        <h1 style="font-size:22px;font-weight:700;color:#ffffff;margin:0 0 10px 0;letter-spacing:-0.3px;line-height:1.3">
          {html.escape(payload.meetingTitle)}
        </h1>
        <p style="margin:0;font-size:13px;color:#666666">
          <span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;background:#1e1e1e;color:#888888;border:1px solid #333333">{html.escape(payload.meetingSoftware)}</span>
          &nbsp; {html.escape(meeting_date)}
        </p>
      </td>
    </tr>

    <!-- Body -->
    <tr>
      <td class="email-body" bgcolor="#ffffff" style="background-color:#ffffff;padding:36px 40px">

        <!-- Summary -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">
          Executive Summary
        </p>
        <p style="font-size:14px;color:#333333;line-height:1.7;margin:0 0 28px 0">
          {html.escape(str(report.get("summary", "Not specified")))}
        </p>

        <!-- Key Points -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">
          Key Points
        </p>
        <div style="margin:0 0 28px 0">
          {list_html(report.get("key_points", []))}
        </div>

        <!-- Decisions -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">
          Decisions Taken
        </p>
        <div style="margin:0 0 28px 0">
          {list_html(report.get("decisions", []))}
        </div>

        <!-- Action Items -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">
          Action Items
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 28px 0;border-collapse:collapse">
          <thead>
            <tr bgcolor="#f7f7f7" style="background-color:#f7f7f7">
              <th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Owner</th>
              <th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Action</th>
              <th style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee">Due Date</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>

        <!-- Risks -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">
          Risks &amp; Open Questions
        </p>
        <div style="margin:0 0 28px 0">
          {list_html(report.get("risks_or_open_questions", []))}
        </div>

        {f'''<!-- Insights -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">Insights</p>
        <div style="margin:0 0 28px 0">{list_html(insights)}</div>''' if insights else ""}

        {f'''<!-- Links -->
        <p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">Links Shared in Chat</p>
        <ul style="margin:0 0 28px 0;padding-left:20px">{"".join(f'<li style="margin:6px 0"><a href="{html.escape(link)}" style="color:#0066cc;text-decoration:underline">{html.escape(link)}</a></li>' for link in links)}</ul>''' if links else ""}

        {_github_issues_html(github_issues or [])}

        {_calendar_reminders_html(reminders or [])}

      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td class="email-footer" bgcolor="#f7f7f7"
          style="background-color:#f7f7f7;padding:16px 40px;border-top:1px solid #eeeeee;border-radius:0 0 12px 12px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="font-size:11px;color:#aaaaaa">Transcriber &mdash; Created by Byte by Byte</td>
            <td align="right" style="font-size:11px;color:#cccccc">Model: {html.escape(MODEL)}</td>
          </tr>
        </table>
      </td>
    </tr>

  </table>
</td></tr>
</table>

</body>
</html>"""


def send_email(subject: str, html_body: str, transcript: str) -> None:
    """Send the HTML report via SMTP using credentials from .env."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    # Build recipient list: deduplicated union of REPORT_RECIPIENTS + SMTP_USER
    raw_recipients = os.getenv("REPORT_RECIPIENTS", smtp_user)
    recipients = list(dict.fromkeys(
        r.strip() for r in raw_recipients.split(",") if r.strip()
    ))
    if smtp_user and smtp_user not in recipients:
        recipients.append(smtp_user)

    if not smtp_user or not smtp_password:
        print("WARNING: SMTP_USER or SMTP_PASSWORD not set — skipping email.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content("Your email client does not support HTML. Please use an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(
        transcript.encode("utf-8"),
        maintype="text",
        subtype="plain",
        filename="meeting-transcript.txt",
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        print(f"Email sent to: {', '.join(recipients)}")


def process(payload: MeetingPayload) -> str:
    """Analyse the meeting, create any GitHub issues from chat commands,
    send the HTML report by email, and return the HTML."""
    transcript = blocks_to_text(payload.transcript, "transcriptText")
    if not transcript:
        raise HTTPException(422, "A non-empty transcript is required")
    chat = blocks_to_text(payload.chatMessages, "chatMessageText")
    links = extract_links(chat) if chat else []

    # Find and execute any CREATE ISSUE commands found in the chat — deduplicated
    created_issues: list[dict[str, Any]] = []
    seen_commands: set[str] = set()
    if chat:
        for match in ISSUE_COMMAND_RE.finditer(chat):
            command_text = match.group(0).strip()
            if command_text in seen_commands:
                continue
            seen_commands.add(command_text)
            try:
                result = handle_issue_command(command_text)
                result["status"] = "created"
                created_issues.append(result)
                print(f"GitHub issue created: #{result['issue_number']} — {result['issue_url']}")
            except Exception as exc:
                print(f"WARNING: GitHub issue creation failed for '{command_text}': {exc}")
                created_issues.append({
                    "issue_number": None,
                    "issue_url": None,
                    "title": command_text,
                    "repo": "unknown",
                    "assignees": [],
                    "status": f"failed: {exc}",
                })

    # Find and execute any SET REMINDER commands found in the chat — deduplicated
    created_reminders: list[dict[str, Any]] = []
    if chat:
        for match in REMINDER_COMMAND_RE.finditer(chat):
            command_text = match.group(0).strip()
            if command_text in seen_commands:
                continue
            seen_commands.add(command_text)
            try:
                result = handle_reminder_command(command_text)
                created_reminders.append(result)
                print(f"Calendar reminder created for {result['email']}: {result.get('web_link')}")
            except Exception as exc:
                print(f"WARNING: Calendar reminder failed for '{command_text}': {exc}")
                created_reminders.append({
                    "email": command_text,
                    "description": command_text,
                    "event_start": None,
                    "web_link": None,
                    "status": f"failed: {exc}",
                })

    report = analyze(transcript, chat, payload.meetingTitle)
    rendered = report_html(
        payload, report,
        links=links,
        github_issues=created_issues or None,
        reminders=created_reminders or None,
    )

    try:
        send_email(
            subject=f"Meeting report: {payload.meetingTitle}",
            html_body=rendered,
            transcript=transcript,
        )
    except Exception as exc:
        print(f"ERROR: Email delivery failed: {exc}")

    return rendered


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/", response_class=HTMLResponse)
async def root_post(
    transcript_file: UploadFile = File(...),
    meeting_title: str = "Meeting",
) -> HTMLResponse:
    """Catch-all for clients that POST to / — forwards to the real endpoint."""
    return await analyze_file(transcript_file=transcript_file, meeting_title=meeting_title)


@app.post("/github/create-issue")
async def github_create_issue(command: str = Form(...)) -> JSONResponse:
    key = f"issue:{command.strip()}"
    if key in _executed_commands:
        print(f"Duplicate command blocked: {key}")
        return JSONResponse(content={"status": "duplicate", **_executed_commands[key]})
    try:
        result = handle_issue_command(command)
        _executed_commands[key] = result
        return JSONResponse(content={"status": "created", **result})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


def _calendar_reminders_html(reminders: list[dict[str, Any]]) -> str:
    """Render the Calendar reminders table block for the email."""
    if not reminders:
        return ""
    rows = ""
    for r in reminders:
        email = html.escape(str(r.get("email", "")))
        desc = html.escape(str(r.get("description", "")))
        start = html.escape(str(r.get("event_start", "—")))
        web_link = r.get("web_link", "")
        status = html.escape(str(r.get("status", "created")))
        status_color = "#22863a" if r.get("status") == "created" else "#cc0000"
        link_td = (
            f'<a href="{html.escape(web_link)}" style="color:#0066cc;text-decoration:underline">Open in Outlook</a>'
            if web_link else "&mdash;"
        )
        rows += (
            f"<tr>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#333333;vertical-align:top">{email}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:14px;color:#333333;vertical-align:top">{desc}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:13px;color:#555555;vertical-align:top;white-space:nowrap">{start}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:13px;vertical-align:top">{link_td}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eeeeee;font-size:13px;font-weight:700;color:{status_color};vertical-align:top;white-space:nowrap">{status}</td>'
            f"</tr>"
        )
    th = (
        'style="text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;'
        'letter-spacing:.7px;color:#999999;font-weight:700;border-bottom:1px solid #eeeeee"'
    )
    return (
        '<p style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#999999;'
        'margin:0 0 10px 0;padding-bottom:8px;border-bottom:1px solid #eeeeee">Calendar Reminders Set</p>'
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 28px 0;border-collapse:collapse">'
        '<thead><tr bgcolor="#f7f7f7" style="background-color:#f7f7f7">'
        f'<th {th}>Recipient</th>'
        f'<th {th}>Description</th>'
        f'<th {th}>Scheduled (UTC)</th>'
        f'<th {th}>Link</th>'
        f'<th {th}>Status</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
    )


@app.post("/calendar/set-reminder")
async def calendar_set_reminder(command: str = Form(...)) -> JSONResponse:
    key = f"reminder:{command.strip()}"
    if key in _executed_commands:
        print(f"Duplicate command blocked: {key}")
        return JSONResponse(content={"status": "duplicate", **_executed_commands[key]})
    try:
        result = handle_reminder_command(command)
        _executed_commands[key] = result
        return JSONResponse(content={"status": "created", **result})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/meetings/analyze", response_class=HTMLResponse)
def analyze_meeting(payload: MeetingPayload) -> HTMLResponse:
    return HTMLResponse(content=process(payload))


@app.post("/api/meetings/analyze-file", response_class=HTMLResponse)
async def analyze_file(
    transcript_file: UploadFile = File(...),
    meeting_title: str = "Meeting",
) -> HTMLResponse:
    if not transcript_file.filename or not transcript_file.filename.lower().endswith(".txt"):
        raise HTTPException(422, "Upload a .txt transcript file")

    content = (await transcript_file.read()).decode("utf-8", errors="replace")

    # Split transcript text from the chat section the extension appends
    chat_section = ""
    chat_marker = "---------------\nCHAT MESSAGES\n---------------"
    if chat_marker in content:
        parts = content.split(chat_marker, 1)
        transcript_text = parts[0].strip()
        chat_raw = parts[1]
        # Strip the branding footer that follows the chat section
        branding_marker = "---------------\nTranscript saved using"
        if branding_marker in chat_raw:
            chat_raw = chat_raw.split(branding_marker, 1)[0]
        chat_section = chat_raw.strip()
    else:
        transcript_text = content

    payload = MeetingPayload(
        meetingTitle=meeting_title,
        transcript=transcript_text,
        chatMessages=chat_section,
    )
    return HTMLResponse(content=process(payload))
