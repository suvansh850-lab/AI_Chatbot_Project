"""Service module for interacting with Gmail and Google Calendar APIs."""

import base64
import time
import re
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

from .config import OPENAI_API_KEY  # just to import config values
import os
# We will read CLIENT_ID and CLIENT_SECRET from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a new access token."""
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=token_data, timeout=15)
    if response.status_code == 200:
        res_json = response.json()
        return {
            "access_token": res_json["access_token"],
            "expires_in": res_json.get("expires_in", 3600),
            "refresh_token": res_json.get("refresh_token", refresh_token)  # keep old if not returned
        }
    else:
        raise RuntimeError(f"Failed to refresh Google token: {response.status_code} - {response.text}")


def get_valid_token(user_id: int | None, session_creds: dict | None = None) -> tuple[str | None, dict | None]:
    """Get a valid access token. Refreshes if expired.
    
    Returns (access_token, updated_session_creds_dict)
    """
    db_credentials = None
    if user_id is not None:
        try:
            from database import load_google_credentials
            db_credentials = load_google_credentials(user_id)
        except Exception:
            pass

    creds = db_credentials or session_creds
    if not creds:
        return None, None

    access_token = creds.get("access_token")
    refresh_token = creds.get("refresh_token")
    expires_at = creds.get("expires_at", 0.0)

    # Refresh 1 minute before actual expiration
    if time.time() + 60 >= expires_at:
        if not refresh_token:
            return None, None
        try:
            refreshed = refresh_access_token(refresh_token)
            new_access_token = refreshed["access_token"]
            new_expires_at = time.time() + refreshed["expires_in"]
            
            # Save to db if enabled
            if user_id is not None:
                try:
                    from database import save_google_credentials
                    save_google_credentials(user_id, new_access_token, refresh_token, new_expires_at)
                except Exception:
                    pass
            
            updated_creds = {
                "access_token": new_access_token,
                "refresh_token": refresh_token,
                "expires_at": new_expires_at
            }
            return new_access_token, updated_creds
        except Exception:
            return None, None

    return access_token, None


def markdown_to_html(text: str) -> str:
    """Convert markdown text to a well-structured HTML email body.
    
    Handles: bold, italic, headings (# ## ###), bullet lists (- * •),
    numbered lists, horizontal rules, inline code, and paragraphs.
    All special HTML chars in user text are escaped BEFORE injecting HTML tags.
    """
    if not text:
        return ""

    lines = text.split("\n")
    html_lines = []
    in_ul = False
    in_ol = False
    ol_counter = 0

    def escape(s: str) -> str:
        """Escape HTML special characters in a plain text segment."""
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def apply_inline(s: str) -> str:
        """Apply bold/italic/code formatting to an already-escaped string."""
        # Bold+italic: ***text*** or ___text___
        s = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', s)
        # Bold: **text** or __text__
        s = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'__(.*?)__', r'<strong>\1</strong>', s)
        # Italic: *text* or _text_
        s = re.sub(r'\*(.*?)\*', r'<em>\1</em>', s)
        s = re.sub(r'_(.*?)_', r'<em>\1</em>', s)
        # Inline code: `code`
        s = re.sub(r'`(.*?)`', r'<code style="background:#f3f4f6;padding:1px 4px;border-radius:3px;font-family:monospace;">\1</code>', s)
        # Markdown links: [text](url)
        s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
        return s

    def close_lists():
        nonlocal in_ul, in_ol, ol_counter
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False
            ol_counter = 0

    for raw_line in lines:
        line = raw_line.rstrip()

        # Blank line — close any open list, add paragraph break
        if not line.strip():
            close_lists()
            html_lines.append('<div style="margin:6px 0;"></div>')
            continue

        # Horizontal rule
        if re.match(r'^[-*_]{3,}$', line.strip()):
            close_lists()
            html_lines.append('<hr style="border:none;border-top:1px solid #e5e7eb;margin:12px 0;">')
            continue

        # Headings: ### ## #
        heading_match = re.match(r'^(#{1,3})\s+(.*)', line)
        if heading_match:
            close_lists()
            level = len(heading_match.group(1))
            content = apply_inline(escape(heading_match.group(2).strip()))
            sizes = {1: "22px", 2: "18px", 3: "15px"}
            weights = {1: "700", 2: "700", 3: "600"}
            html_lines.append(
                f'<div style="font-size:{sizes[level]};font-weight:{weights[level]};'
                f'color:#111827;margin:14px 0 4px 0;">{content}</div>'
            )
            continue

        # Bullet list: lines starting with "- ", "* ", "• "
        bullet_match = re.match(r'^(\s*)([-*•])\s+(.*)', line)
        if bullet_match:
            indent = len(bullet_match.group(1))
            item_text = apply_inline(escape(bullet_match.group(3).strip()))
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
                ol_counter = 0
            if not in_ul:
                html_lines.append('<ul style="margin:6px 0 6px 20px;padding:0;">')
                in_ul = True
            padding = f"padding-left:{indent * 12}px;" if indent > 0 else ""
            html_lines.append(f'<li style="margin:3px 0;{padding}">{item_text}</li>')
            continue

        # Numbered list: lines starting with "1. " "2. " etc.
        ol_match = re.match(r'^\s*(\d+)\.\s+(.*)', line)
        if ol_match:
            item_text = apply_inline(escape(ol_match.group(2).strip()))
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                html_lines.append('<ol style="margin:6px 0 6px 20px;padding:0;">')
                in_ol = True
                ol_counter = 0
            ol_counter += 1
            html_lines.append(f'<li style="margin:3px 0;">{item_text}</li>')
            continue

        # Regular paragraph line
        close_lists()
        content = apply_inline(escape(line))
        html_lines.append(f'<div style="margin:3px 0;">{content}</div>')

    close_lists()
    return "\n".join(html_lines)


def build_html_email(body_html: str) -> str:
    """Wrap email body HTML in a full, styled HTML document for best Gmail rendering."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 15px;
    color: #1f2937;
    line-height: 1.6;
    margin: 0;
    padding: 0;
    background: #ffffff;
  }}
  .email-wrapper {{
    max-width: 640px;
    margin: 0 auto;
    padding: 28px 32px;
  }}
  ul, ol {{
    margin: 8px 0 8px 24px;
    padding: 0;
  }}
  li {{
    margin: 4px 0;
  }}
  strong {{ color: #111827; }}
  code {{
    background: #f3f4f6;
    padding: 1px 4px;
    border-radius: 3px;
    font-family: monospace;
    font-size: 13px;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 16px 0;
  }}
  a {{ color: #4f46e5; }}
</style>
</head>
<body>
<div class="email-wrapper">
{body_html}
</div>
</body>
</html>"""


def draft_email(recipient: str, subject: str, body: str, access_token: str) -> str:
    """Draft a compose email via Gmail API."""
    url = "https://www.googleapis.com/gmail/v1/users/me/drafts"
    headers_http = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Sanitize subject
    subject = subject.strip()

    # Convert markdown body to HTML and wrap in a full HTML document
    body_html = markdown_to_html(body)
    full_html = build_html_email(body_html)

    # Build MIME message
    message = MIMEMultipart("alternative")
    message["To"] = recipient
    message["Subject"] = subject

    # Attach plain text fallback (stripped of markdown)
    plain_text = re.sub(r'\*+|#+|`', '', body)
    message.attach(MIMEText(plain_text, "plain", "utf-8"))

    # Attach HTML version (preferred by email clients)
    message.attach(MIMEText(full_html, "html", "utf-8"))

    # Encode as urlsafe base64 (required by Gmail API)
    raw_bytes = message.as_bytes()
    raw_base64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    payload = {
        "message": {
            "raw": raw_base64
        }
    }

    response = requests.post(url, json=payload, headers=headers_http, timeout=15)
    if response.status_code == 200:
        res_json = response.json()
        draft_id = res_json.get("id", "unknown")
        return f"Successfully created email draft (ID: {draft_id}) for {recipient}. The draft is now saved in Gmail Drafts."
    else:
        return f"Failed to draft email: {response.status_code} - {response.text}"


def send_email(recipient: str, subject: str, body: str, access_token: str) -> str:
    """Send an email directly via Gmail API (no draft — sends immediately)."""
    url = "https://www.googleapis.com/gmail/v1/users/me/messages/send"
    headers_http = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    subject = subject.strip()

    body_html = markdown_to_html(body)
    full_html = build_html_email(body_html)

    message = MIMEMultipart("alternative")
    message["To"] = recipient
    message["Subject"] = subject

    plain_text = re.sub(r'\*+|#+|`', '', body)
    message.attach(MIMEText(plain_text, "plain", "utf-8"))
    message.attach(MIMEText(full_html, "html", "utf-8"))

    raw_bytes = message.as_bytes()
    raw_base64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    payload = {"raw": raw_base64}

    response = requests.post(url, json=payload, headers=headers_http, timeout=15)
    if response.status_code == 200:
        return f"Email successfully sent to {recipient}."
    else:
        return f"Failed to send email: {response.status_code} - {response.text}"


def create_event(summary: str, start_time: str, end_time: str, description: str, location: str, access_token: str) -> str:
    """Create a calendar event via Google Calendar API."""
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Check for timezone offset. Ignore date hyphens by checking time part after 'T'.
    time_part = start_time.split("T")[1] if "T" in start_time else ""
    has_tz = "Z" in start_time or "+" in start_time or "-" in time_part
    
    start_payload = {"dateTime": start_time}
    end_payload = {"dateTime": end_time}
    
    if not has_tz:
        start_payload["timeZone"] = "Asia/Kolkata"
        end_payload["timeZone"] = "Asia/Kolkata"
        
    payload = {
        "summary": summary,
        "description": description or "",
        "location": location or "",
        "start": start_payload,
        "end": end_payload
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=15)
    if response.status_code == 200:
        res_json = response.json()
        event_link = res_json.get("htmlLink", "")
        return f"Successfully scheduled calendar event '{summary}' from {start_time} to {end_time}. Event Link: {event_link}"
    else:
        return f"Failed to schedule event: {response.status_code} - {response.text}"
