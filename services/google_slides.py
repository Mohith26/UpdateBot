import re

import google.auth
from googleapiclient.discovery import build

_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]

_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")


def _get_creds():
    creds, _ = google.auth.default(scopes=_SCOPES)
    return creds


def copy_template(template_id: str, title: str) -> str:
    """Copies the template file and returns the new presentation ID."""
    drive = build("drive", "v3", credentials=_get_creds(), cache_discovery=False)
    result = drive.files().copy(
        fileId=template_id,
        body={"name": title},
    ).execute()
    return result["id"]


def fill_placeholders(presentation_id: str, replacements: dict[str, str]) -> None:
    """Replaces all {{KEY}} placeholders in the presentation with their values."""
    slides = build("slides", "v1", credentials=_get_creds(), cache_discovery=False)
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": f"{{{{{key}}}}}", "matchCase": True},
                "replaceText": value,
            }
        }
        for key, value in replacements.items()
    ]
    if requests:
        try:
            slides.presentations().batchUpdate(
                presentationId=presentation_id,
                body={"requests": requests},
            ).execute()
        except Exception as e:
            raise RuntimeError(f"Slides batchUpdate failed for presentation {presentation_id}: {e}") from e


def get_presentation_url(presentation_id: str) -> str:
    return f"https://docs.google.com/presentation/d/{presentation_id}/edit"


def _scan_text(text_obj: dict, found: set[str]) -> None:
    """Extract `{{TAG}}` matches from a Slides `text` object into `found`."""
    if not text_obj:
        return
    for text_element in text_obj.get("textElements", []) or []:
        text_run = text_element.get("textRun") or {}
        content = text_run.get("content")
        if not content:
            continue
        for match in _PLACEHOLDER_RE.findall(content):
            found.add(match)


def _scan_page_element(element: dict, found: set[str]) -> None:
    """Recursively scan a pageElement for placeholder text.

    Walks shapes, table cells, and nested element groups. Groups can
    themselves contain groups, hence the recursion.
    """
    if not element:
        return
    shape = element.get("shape") or {}
    _scan_text(shape.get("text") or {}, found)

    table = element.get("table") or {}
    for row in table.get("tableRows", []) or []:
        for cell in row.get("tableCells", []) or []:
            _scan_text(cell.get("text") or {}, found)

    group = element.get("elementGroup") or {}
    for child in group.get("children", []) or []:
        _scan_page_element(child, found)


def find_unfilled_placeholders(presentation_id: str) -> list[str]:
    """Return a sorted list of unique `{{TAG}}` patterns still present in the deck.

    Empty list means every placeholder was filled. Used as a post-fill safety
    check so decks with typos / unknown tags do not ship to investors.

    Scans shapes, table cells, nested element groups, AND speaker notes —
    anywhere a `{{TAG}}` can hide in a Slides deck.
    """
    slides = build("slides", "v1", credentials=_get_creds(), cache_discovery=False)
    # Field mask widened to cover: shapes, tables, element groups (recursive),
    # and the speaker-notes pages (`notesPage.pageElements`).
    fields = (
        "slides.pageElements("
        "shape.text.textElements.textRun.content,"
        "table.tableRows.tableCells.text.textElements.textRun.content,"
        "elementGroup"
        "),"
        "slides.notesPage.pageElements("
        "shape.text.textElements.textRun.content,"
        "table.tableRows.tableCells.text.textElements.textRun.content,"
        "elementGroup"
        ")"
    )
    presentation = slides.presentations().get(
        presentationId=presentation_id,
        fields=fields,
    ).execute()

    found: set[str] = set()
    for slide in presentation.get("slides", []) or []:
        for element in slide.get("pageElements", []) or []:
            _scan_page_element(element, found)
        notes_page = slide.get("notesPage") or {}
        for element in notes_page.get("pageElements", []) or []:
            _scan_page_element(element, found)
    return sorted(found)
