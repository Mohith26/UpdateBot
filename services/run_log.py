# RunLog tab schema (CONFIG_SHEET_ID, tab "RunLog", A:H): timestamp_utc | job_name | status | properties_processed | properties_failed | duration_seconds | summary | details_json
import json
import os
import re
from datetime import datetime, timezone

import google.auth
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_RANGE = "RunLog!A:H"


def _get_service():
    creds, _ = google.auth.default(scopes=_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize_details(details: list[dict]) -> str:
    try:
        return json.dumps(details, default=str)
    except Exception as e:
        print(f"RunLog: failed to serialize details ({e}); writing empty array")
        return "[]"


def _build_row(
    timestamp_utc: str,
    job_name: str,
    status: str,
    properties_processed: int,
    properties_failed: int,
    duration_seconds: int,
    summary: str,
    details_json: str,
) -> list:
    return [
        timestamp_utc,
        job_name,
        status,
        int(properties_processed),
        int(properties_failed),
        int(duration_seconds),
        summary,
        details_json,
    ]


def _parse_row_number(updated_range: str) -> int | None:
    """Extract the appended row number from an API `updatedRange` like 'RunLog!A12:H12'."""
    if not updated_range:
        return None
    match = re.search(r"!?[A-Za-z]+(\d+):", updated_range)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    # Fallback for single-cell ranges like 'RunLog!A12'.
    match = re.search(r"!?[A-Za-z]+(\d+)$", updated_range)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def append_run(
    job_name: str,
    status: str,
    properties_processed: int,
    properties_failed: int,
    duration_seconds: int,
    summary: str,
    details: list[dict],
) -> None:
    try:
        spreadsheet_id = os.environ["CONFIG_SHEET_ID"]
        timestamp_utc = _now_utc()
        details_json = _serialize_details(details)

        row = _build_row(
            timestamp_utc,
            job_name,
            status,
            properties_processed,
            properties_failed,
            duration_seconds,
            summary,
            details_json,
        )
        service = _get_service()
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
    except Exception as e:
        print(f"RunLog: failed to append run row for {job_name}: {e}")


def start_run(job_name: str) -> int | None:
    """Append a `running` placeholder row at job start; return its row number.

    The returned row number is fed to `finalize_run` so the same row is
    UPDATED with terminal status — guaranteeing the dashboard sees something
    even if the job crashes mid-run.

    Fail-soft: on any Sheets API error, log and return None. Callers should
    fall back to `append_run` at job end when this returns None.
    """
    try:
        spreadsheet_id = os.environ["CONFIG_SHEET_ID"]
        timestamp_utc = _now_utc()
        summary = f"Job started at {timestamp_utc}"
        row = _build_row(
            timestamp_utc,
            job_name,
            "running",
            0,
            0,
            0,
            summary,
            "[]",
        )
        service = _get_service()
        response = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        updates = response.get("updates") or {}
        row_num = _parse_row_number(updates.get("updatedRange", ""))
        if row_num is None:
            print(f"RunLog: started run for {job_name} but could not parse row number from {updates!r}")
        return row_num
    except Exception as e:
        print(f"RunLog: failed to start run row for {job_name}: {e}")
        return None


def finalize_run(
    row_key: int | None,
    job_name: str,
    status: str,
    properties_processed: int,
    properties_failed: int,
    duration_seconds: int,
    summary: str,
    details: list[dict],
) -> None:
    """Update the `running` row written by `start_run` to its terminal state.

    If `row_key` is None (start_run failed or was never called), falls back
    to appending a fresh terminal row via `append_run` so the dashboard
    still shows the run.
    """
    if row_key is None:
        append_run(
            job_name=job_name,
            status=status,
            properties_processed=properties_processed,
            properties_failed=properties_failed,
            duration_seconds=duration_seconds,
            summary=summary,
            details=details,
        )
        return

    try:
        spreadsheet_id = os.environ["CONFIG_SHEET_ID"]
        details_json = _serialize_details(details)
        # Update B:H only — column A is the start timestamp written by
        # start_run, and overwriting it would make long-running jobs
        # appear "just now" once they finalize (breaks at-a-glance triage).
        row_bh = [
            job_name,
            status,
            int(properties_processed),
            int(properties_failed),
            int(duration_seconds),
            summary,
            details_json,
        ]
        service = _get_service()
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"RunLog!B{row_key}:H{row_key}",
            valueInputOption="RAW",
            body={"values": [row_bh]},
        ).execute()
    except Exception as e:
        print(f"RunLog: failed to finalize run row {row_key} for {job_name}: {e}; falling back to append")
        append_run(
            job_name=job_name,
            status=status,
            properties_processed=properties_processed,
            properties_failed=properties_failed,
            duration_seconds=duration_seconds,
            summary=summary,
            details=details,
        )
