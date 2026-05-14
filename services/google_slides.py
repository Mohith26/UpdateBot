import google.auth
from googleapiclient.discovery import build

_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]


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
        slides.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        ).execute()


def get_presentation_url(presentation_id: str) -> str:
    return f"https://docs.google.com/presentation/d/{presentation_id}/edit"
