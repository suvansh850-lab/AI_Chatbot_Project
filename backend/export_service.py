"""Export service — Notion page and Google Docs export for chat conversations."""

import datetime
import re
import requests


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ist_timestamp() -> str:
    """Return current IST timestamp as a readable string."""
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist_tz).strftime("%Y-%m-%d %H:%M:%S IST")


def _sanitize_text(text: str) -> str:
    """Strip Markdown formatting for plain-text destinations."""
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
    # Remove inline code backticks
    text = re.sub(r'`{1,3}(.*?)`{1,3}', r'\1', text, flags=re.DOTALL)
    # Remove markdown headings (keep text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()



# ---------------------------------------------------------------------------
# Google Docs Export
# ---------------------------------------------------------------------------

_DOCS_API = "https://docs.googleapis.com/v1/documents"
_DRIVE_API = "https://www.googleapis.com/drive/v3/files"


def export_to_google_docs(
    messages: list[dict],
    title: str,
    access_token: str,
) -> str:
    """Export chat messages as a new Google Doc.

    Args:
        messages: List of chat message dicts (role, content).
        title: Title for the new Google Doc.
        access_token: Valid Google OAuth access token with documents + drive.file scope.

    Returns:
        URL of the newly created Google Doc.

    Raises:
        RuntimeError: If any API call fails.
    """
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Step 1 — Create empty document
    create_resp = requests.post(
        _DOCS_API,
        json={"title": title},
        headers=auth_headers,
        timeout=15,
    )
    if create_resp.status_code not in (200, 201):
        error_detail = create_resp.json().get("error", {}).get("message", create_resp.text)
        raise RuntimeError(f"Google Docs create error {create_resp.status_code}: {error_detail}")

    doc_data = create_resp.json()
    doc_id = doc_data["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    # Step 2 — Build batchUpdate requests (insert text from BOTTOM to TOP so indexes stay valid)
    # We insert all content as a single block of text then style it.
    # Strategy: build the full text first, then insert it all at once.

    lines = []
    lines.append(f"Morepen AI Assistant — Chat Transcript")
    lines.append(f"Exported on {_ist_timestamp()}")
    lines.append("")
    lines.append("─" * 60)
    lines.append("")

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if content.startswith(("Uploaded file:", "Restored file:", "Imported from Google Drive:")):
            continue

        label = "YOU" if role == "user" else "ASSISTANT"
        clean = _sanitize_text(content)
        lines.append(f"[{label}]")
        lines.append(clean)
        lines.append("")

    full_text = "\n".join(lines)

    # Google Docs API: insert text at index 1 (after the document's implicit start)
    # We insert the body text, then apply heading style to the title lines.
    requests_body = []

    # Insert all text at once at index 1
    requests_body.append({
        "insertText": {
            "location": {"index": 1},
            "text": full_text,
        }
    })

    # Style the document title (first line) as HEADING_1
    title_end = len("Morepen AI Assistant — Chat Transcript") + 1  # +1 for \n
    requests_body.append({
        "updateParagraphStyle": {
            "range": {"startIndex": 1, "endIndex": title_end},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType",
        }
    })

    # Apply bold to all [YOU] and [ASSISTANT] labels using text search
    # Build a map of where each label starts in the text
    current_index = 1  # document starts at index 1
    for line in lines:
        line_with_newline = line + "\n"
        if line in ("[YOU]", "[ASSISTANT]"):
            label_start = current_index
            label_end = current_index + len(line)
            requests_body.append({
                "updateTextStyle": {
                    "range": {"startIndex": label_start, "endIndex": label_end},
                    "textStyle": {
                        "bold": True,
                        "foregroundColor": {
                            "color": {
                                "rgbColor": {
                                    "red": 0.22,
                                    "green": 0.46,
                                    "blue": 0.85,
                                } if line == "[YOU]" else {
                                    "red": 0.85,
                                    "green": 0.47,
                                    "blue": 0.34,
                                }
                            }
                        },
                    },
                    "fields": "bold,foregroundColor",
                }
            })
        current_index += len(line_with_newline)

    # Execute batchUpdate
    batch_resp = requests.post(
        f"{_DOCS_API}/{doc_id}:batchUpdate",
        json={"requests": requests_body},
        headers=auth_headers,
        timeout=20,
    )
    if batch_resp.status_code not in (200, 201):
        error_detail = batch_resp.json().get("error", {}).get("message", batch_resp.text)
        raise RuntimeError(f"Google Docs batchUpdate error {batch_resp.status_code}: {error_detail}")

    return doc_url


def check_google_docs_scope(access_token: str) -> bool:
    """Check whether the access token has the Google Docs write scope.

    Uses the token-info endpoint to inspect granted scopes.
    Returns True if documents scope is present, False otherwise.
    """
    try:
        resp = requests.get(
            f"https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={access_token}",
            timeout=10,
        )
        if resp.status_code == 200:
            scope_str = resp.json().get("scope", "")
            return "documents" in scope_str
    except Exception:
        pass
    return False
