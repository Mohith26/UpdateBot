import google.auth
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/documents"]


def _get_service():
    creds, _ = google.auth.default(scopes=_SCOPES)
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def read_full_text(doc_id: str) -> str:
    """Returns the full plain text content of a Google Doc."""
    service = _get_service()
    doc = service.documents().get(documentId=doc_id).execute()
    text_parts = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for part in paragraph.get("elements", []):
            text_run = part.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def _is_section_label(line: str) -> bool:
    """True if a line is a bare section label (no punctuation, short, not a sentence)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    # Matches known labels: "Property Update", "Active Prospects",
    # "<Market> Market Update", "Financial Update", "What We're Reading"
    exact = {"Property Update", "Active Prospects", "Financial Update", "What We're Reading"}
    if stripped in exact:
        return True
    if stripped.endswith("Market Update") and len(stripped) > len("Market Update"):
        return True
    return False


def prepend_update(doc_id: str, date_header: str, content: str) -> None:
    """Inserts a date-stamped update section at the top of the document body.

    Applies HEADING_2 to date_header and HEADING_3 to each section label line.
    """
    service = _get_service()

    separator = "─" * 60
    section_text = f"{date_header}\n\n{content}\n\n{separator}\n\n"

    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": section_text,
            }
        },
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": len(date_header) + 1},
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                "fields": "namedStyleType",
            }
        },
    ]

    # Walk the inserted text line by line to find section label positions.
    # doc offset = 1 (index 1 is where we inserted)
    doc_offset = 1
    char_pos = 0
    for line in section_text.split("\n"):
        line_len = len(line)
        if _is_section_label(line):
            start = doc_offset + char_pos
            end = start + line_len
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": {"namedStyleType": "HEADING_3"},
                        "fields": "namedStyleType",
                    }
                }
            )
        char_pos += line_len + 1  # +1 for the \n

    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()
