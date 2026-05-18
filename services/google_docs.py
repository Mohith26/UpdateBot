import re

import google.auth
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/documents"]

_SEPARATOR = "─" * 60

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
# Date header format we emit: "{Month} {Year} Update - {Property}"
_MONTH_HEADER_RE = re.compile(rf"^({_MONTHS})\s+(\d{{4}})\s+Update\b")


def _get_service():
    creds, _ = google.auth.default(scopes=_SCOPES)
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def read_full_text(doc_id: str) -> str:
    """Returns the full plain text content of a Google Doc."""
    service = _get_service()
    doc = service.documents().get(documentId=doc_id).execute()
    return "".join(p["text"] for p in _iter_paragraphs(doc))


def _iter_paragraphs(doc: dict):
    """Yield {text, start_index, end_index} for each paragraph in the doc body.

    `start_index` / `end_index` are the Docs API character offsets — end is
    exclusive and includes the trailing paragraph mark. Empty paragraphs are
    included so callers can locate blank-line separators.
    """
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text_parts = []
        for part in paragraph.get("elements", []):
            text_run = part.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
        yield {
            "text": "".join(text_parts),
            "start_index": element.get("startIndex"),
            "end_index": element.get("endIndex"),
        }


def _is_section_label(line: str) -> bool:
    """True if a line is a bare section label (no punctuation, short, not a sentence)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    exact = {"Property Update", "Active Prospects", "Financial Update", "What We're Reading"}
    if stripped in exact:
        return True
    if stripped.endswith("Market Update") and len(stripped) > len("Market Update"):
        return True
    return False


def _build_section_text(date_header: str, content: str) -> str:
    return f"{date_header}\n\n{content}\n\n{_SEPARATOR}\n\n"


def _section_insert_requests(insert_at: int, date_header: str, content: str) -> list[dict]:
    """Build batchUpdate requests that insert a styled section at `insert_at`."""
    section_text = _build_section_text(date_header, content)

    requests: list[dict] = [
        {
            "insertText": {
                "location": {"index": insert_at},
                "text": section_text,
            }
        },
        {
            "updateParagraphStyle": {
                "range": {
                    "startIndex": insert_at,
                    "endIndex": insert_at + len(date_header),
                },
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                "fields": "namedStyleType",
            }
        },
    ]

    char_pos = 0
    for line in section_text.split("\n"):
        if _is_section_label(line):
            start = insert_at + char_pos
            end = start + len(line)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": {"namedStyleType": "HEADING_3"},
                        "fields": "namedStyleType",
                    }
                }
            )
        char_pos += len(line) + 1  # +1 for the \n we split on
    return requests


def _find_section_bounds(
    paragraphs: list[dict], start_para_idx: int
) -> tuple[int, int, str]:
    """Walk forward from a date-header paragraph and find where the section ends.

    A section ends at whichever comes first:
      - the next monthly heading (the new section starts there; we stop before it)
      - the separator line plus the blank paragraph immediately after it
      - end of doc

    Returns (start_index, end_index, text). Indices are Docs API offsets;
    end_index is exclusive.
    """
    start_para = paragraphs[start_para_idx]
    section_text_parts: list[str] = []
    end_para_idx = start_para_idx
    for i in range(start_para_idx, len(paragraphs)):
        p = paragraphs[i]
        if i > start_para_idx and _MONTH_HEADER_RE.match(p["text"].strip()):
            # Next month's heading: stop before it.
            end_para_idx = i - 1
            break
        section_text_parts.append(p["text"])
        if _SEPARATOR[:10] in p["text"]:
            # The separator paragraph is part of the section. Swallow one
            # trailing blank paragraph after the separator if present so the
            # doc keeps its visual spacing.
            if i + 1 < len(paragraphs) and not paragraphs[i + 1]["text"].strip():
                end_para_idx = i + 1
                section_text_parts.append(paragraphs[i + 1]["text"])
            else:
                end_para_idx = i
            break
        end_para_idx = i

    start_index = start_para["start_index"]
    end_index = paragraphs[end_para_idx]["end_index"]
    return start_index, end_index, "".join(section_text_parts)


def find_month_section(doc_id: str, month_name: str, year: int) -> dict | None:
    """Locate the existing entry for `{month_name} {year}` in the doc.

    Returns `{start_index, end_index, text}` for the first matching section,
    or `None` if no such heading exists. Used by slack-sync to decide whether
    to edit an existing monthly entry or prepend a new one.
    """
    service = _get_service()
    doc = service.documents().get(documentId=doc_id).execute()
    paragraphs = list(_iter_paragraphs(doc))

    target_re = re.compile(rf"^{re.escape(month_name)}\s+{year}\s+Update\b")
    for i, p in enumerate(paragraphs):
        if target_re.match(p["text"].strip()):
            start, end, text = _find_section_bounds(paragraphs, i)
            return {"start_index": start, "end_index": end, "text": text}
    return None


def read_recent_monthly_sections(
    doc_id: str,
    exclude_month: str,
    exclude_year: int,
    max_n: int = 3,
) -> list[str]:
    """Return plain text for up to `max_n` recent monthly sections, newest first.

    Excludes the section for `(exclude_month, exclude_year)` so callers can
    pass the current month and not mix tone reference with the entry they're
    about to rewrite. Used as style examples for the LLM.
    """
    service = _get_service()
    doc = service.documents().get(documentId=doc_id).execute()
    paragraphs = list(_iter_paragraphs(doc))

    out: list[str] = []
    for i, p in enumerate(paragraphs):
        m = _MONTH_HEADER_RE.match(p["text"].strip())
        if not m:
            continue
        month_name, year_str = m.group(1), m.group(2)
        if month_name == exclude_month and year_str == str(exclude_year):
            continue
        _start, _end, text = _find_section_bounds(paragraphs, i)
        out.append(text.strip())
        if len(out) >= max_n:
            break
    return out


def prepend_update(doc_id: str, date_header: str, content: str) -> None:
    """Insert a date-stamped update section at the top of the document body."""
    service = _get_service()
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": _section_insert_requests(1, date_header, content)},
    ).execute()


def replace_section(
    doc_id: str,
    start_index: int,
    end_index: int,
    date_header: str,
    content: str,
) -> None:
    """Delete an existing section range and insert a rebuilt one at the same offset.

    Indices are Docs API offsets (typically obtained via `find_month_section`).
    The delete + insert + paragraph styling are issued in a single
    `batchUpdate` so the operation is atomic — partial failure cannot leave
    the doc with a deleted-but-not-replaced section.
    """
    requests = [
        {
            "deleteContentRange": {
                "range": {"startIndex": start_index, "endIndex": end_index},
            }
        }
    ]
    requests.extend(_section_insert_requests(start_index, date_header, content))

    service = _get_service()
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()
