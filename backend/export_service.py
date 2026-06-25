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
# Notion Export
# ---------------------------------------------------------------------------

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _notion_rich_text(content: str, bold: bool = False) -> dict:
    """Build a Notion rich_text element."""
    return {
        "type": "text",
        "text": {"content": content},
        "annotations": {
            "bold": bold,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    }


def _chunk_text(text: str, max_len: int = 2000) -> list[str]:
    """Split text into chunks ≤ max_len characters (Notion block limit)."""
    chunks = []
    while len(text) > max_len:
        # Try to split at a newline boundary
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _messages_to_notion_blocks(messages: list[dict]) -> list[dict]:
    """Convert chat messages to a flat list of Notion block objects."""
    blocks = []

    # Metadata paragraph
    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                _notion_rich_text(f"Exported on {_ist_timestamp()} • Morepen AI Assistant")
            ],
            "color": "gray",
        },
    })

    # Divider after header
    blocks.append({"object": "block", "type": "divider", "divider": {}})

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Skip file-indicator messages
        if content.startswith(("Uploaded file:", "Restored file:", "Imported from Google Drive:")):
            continue

        label = "You" if role == "user" else "Assistant"
        color = "blue_background" if role == "user" else "orange_background"

        # Callout block for speaker label
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [_notion_rich_text(label, bold=True)],
                "icon": {"emoji": "🧑" if role == "user" else "🤖"},
                "color": color,
            },
        })

        # Split long messages into multiple paragraph blocks (2000-char Notion limit)
        clean = _sanitize_text(content)
        for chunk in _chunk_text(clean, 1990):
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [_notion_rich_text(chunk)],
                    "color": "default",
                },
            })

        # Visual spacer
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": []},
        })

    return blocks


def export_to_notion(
    messages: list[dict],
    title: str,
    notion_token: str,
    parent_page_id: str,
) -> str:
    """Export chat messages as a new Notion page.

    Args:
        messages: List of chat message dicts (role, content).
        title: Title for the Notion page.
        notion_token: Notion Internal Integration Token (secret_xxx...).
        parent_page_id: ID of the parent Notion page where the new page is created.

    Returns:
        URL of the newly created Notion page.

    Raises:
        RuntimeError: If the API call fails.
    """
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VERSION,
    }

    blocks = _messages_to_notion_blocks(messages)

    # Notion API limits to 100 children per request — split if needed
    first_batch = blocks[:100]
    remaining = blocks[100:]

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🤖"},
        "cover": {
            "type": "external",
            "external": {
                "url": "https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=1200"
            },
        },
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": first_batch,
    }

    response = requests.post(
        f"{_NOTION_API}/pages",
        json=payload,
        headers=headers,
        timeout=20,
    )

    if response.status_code not in (200, 201):
        error_msg = response.json().get("message", response.text)
        raise RuntimeError(f"Notion API error {response.status_code}: {error_msg}")

    page_data = response.json()
    page_id = page_data.get("id", "")
    page_url = page_data.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")

    # Append remaining blocks in batches of 100
    if remaining and page_id:
        for i in range(0, len(remaining), 100):
            batch = remaining[i:i + 100]
            requests.patch(
                f"{_NOTION_API}/blocks/{page_id}/children",
                json={"children": batch},
                headers=headers,
                timeout=20,
            )

    return page_url


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
