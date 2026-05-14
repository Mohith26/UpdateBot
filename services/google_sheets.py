import google.auth
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    creds, _ = google.auth.default(scopes=_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_range(spreadsheet_id: str, range_name: str) -> list[list]:
    service = _get_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    return result.get("values", [])


def write_cell(spreadsheet_id: str, cell: str, value: str) -> None:
    service = _get_service()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=cell,
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()
