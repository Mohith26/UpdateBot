from datetime import datetime, timezone
import re
import time
import config
from services.google_docs import read_full_text
from services.google_sheets import read_range
from services.google_slides import (
    copy_template,
    fill_placeholders,
    find_unfilled_placeholders,
    get_presentation_url,
)
from services.slack_client import post_message
from services.run_log import finalize_run, start_run


_PROPERTY_UPDATES_WORD_CAP = 250
_MISSING_CASH_BALANCE = "[Data not available]"


def _quarter(month: int, year: int) -> str:
    return f"Q{(month - 1) // 3 + 1} {year}"


def _truncate_words(text: str, max_words: int) -> str:
    """Truncate to max_words on a word boundary; append '…' if truncated."""
    if not text:
        return text
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def _sanitize_slides_value(value: str) -> str:
    """Strip nulls; collapse trailing whitespace. Keep newlines (Slides handles them)."""
    if value is None:
        return ""
    s = str(value).replace("\0", "")
    return s.strip()


def _extract_section(doc_text: str, section_name: str, prop_name: str) -> str:
    """Extract content under a plain-text section label until the next label or separator."""
    if section_name == "Market Update":
        header_pattern = r"[^\n]*Market Update"
    else:
        header_pattern = re.escape(section_name)
    pattern = rf"^{header_pattern}\s*\n(.*?)(?=\n[A-Z][^\n]{{0,59}}\n|\n─{{10,}}\n|\Z)"
    match = re.search(pattern, doc_text, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(1).strip()
    print(f"    WARNING: section '{section_name}' not found in doc for '{prop_name}'; defaulting to 'No updates this period.'")
    return "No updates this period."


def _read_cash_balance(cell_cash_balance: str, prop_name: str) -> str:
    """Read cash balance from a combined SHEET_ID:RANGE value, e.g. '1abc...:Sheet1!B5'."""
    if not cell_cash_balance:
        print(f"    WARNING: cell_cash_balance is empty for '{prop_name}'; using placeholder")
        return _MISSING_CASH_BALANCE
    if ":" not in cell_cash_balance:
        print(f"    WARNING: cell_cash_balance for '{prop_name}' is malformed (missing ':' separator): {cell_cash_balance!r}; using placeholder")
        return _MISSING_CASH_BALANCE
    sheet_id, cell_ref = cell_cash_balance.split(":", 1)
    sheet_id = sheet_id.strip()
    cell_ref = cell_ref.strip()
    if not sheet_id or not cell_ref:
        print(f"    WARNING: cell_cash_balance for '{prop_name}' has empty sheet_id or cell_ref: {cell_cash_balance!r}; using placeholder")
        return _MISSING_CASH_BALANCE
    try:
        rows = read_range(sheet_id, cell_ref)
    except Exception as e:
        print(f"    WARNING: failed to read cash balance for '{prop_name}' from {sheet_id}:{cell_ref}: {e}; using placeholder")
        return _MISSING_CASH_BALANCE
    if rows and rows[0]:
        return str(rows[0][0])
    print(f"    WARNING: cash balance cell for '{prop_name}' ({sheet_id}:{cell_ref}) returned no value; using placeholder")
    return _MISSING_CASH_BALANCE


def _resolve_replacements(prop, report_period: str) -> dict:
    if not prop.live_doc_id:
        raise ValueError(f"live_doc_id is empty for property '{prop.name}'")
    try:
        doc_text = read_full_text(prop.live_doc_id)
    except Exception as e:
        raise RuntimeError(f"failed to read live doc {prop.live_doc_id} for '{prop.name}': {e}") from e

    property_updates = _extract_section(doc_text, "Property Update", prop.name)
    market_update = _extract_section(doc_text, "Market Update", prop.name)

    original_word_count = len(property_updates.split())
    property_updates = _truncate_words(property_updates, _PROPERTY_UPDATES_WORD_CAP)
    if original_word_count > _PROPERTY_UPDATES_WORD_CAP:
        print(f"    Truncated PROPERTY_UPDATES for '{prop.name}' from {original_word_count} to {_PROPERTY_UPDATES_WORD_CAP} words")

    what_we_are_reading = ""
    if prop.what_we_are_reading_doc_id:
        try:
            what_we_are_reading = read_full_text(prop.what_we_are_reading_doc_id).strip()
        except Exception as e:
            print(f"    WARNING: failed to read what_we_are_reading doc {prop.what_we_are_reading_doc_id} for '{prop.name}': {e}")
            what_we_are_reading = ""
    if not what_we_are_reading:
        what_we_are_reading = _extract_section(doc_text, "What We're Reading", prop.name)

    cash_balance = _read_cash_balance(prop.cell_cash_balance, prop.name)

    raw = {
        "PROPERTY_NAME": prop.name,
        "REPORT_PERIOD": report_period,
        "PROPERTY_UPDATES": property_updates,
        "CASH_BALANCE": cash_balance,
        "WHAT_WE_ARE_READING": what_we_are_reading,
        "MARKET_UPDATE": market_update,
        "ADDRESS": prop.address,
        "PURCHASE_DATE": prop.purchase_date,
        "PURCHASE_PRICE": prop.purchase_price,
        "SIZE_SQFT": prop.size_sqft,
        "NUM_UNITS": prop.num_units,
        "YEAR_BUILT": prop.year_built,
        "MARKET_NAME": prop.market_name,
    }
    return {k: _sanitize_slides_value(v) for k, v in raw.items()}


def _print_dry_run_block(prop_name: str, replacements: dict) -> None:
    print(f"=== Property: {prop_name} ===")
    for key, value in replacements.items():
        print(f"{{{{{key}}}}} = {value}")
    print()


def _compute_status(processed: int, failed: int) -> str:
    if processed == 0:
        return "failed"
    if failed == 0:
        return "success"
    if failed >= processed:
        return "failed"
    return "partial"


def run(dry_run: bool = False) -> None:
    start_time = time.time()
    if dry_run:
        print("Starting monthly-report job (DRY RUN — no writes will be performed)...")
    else:
        print("Starting monthly-report job...")

    # Write a 'running' RunLog row immediately so the dashboard reflects
    # the job even if we crash before finalize_run. Dry-run also writes a
    # row so the operator can validate placeholder resolution from the
    # dashboard without hunting through Cloud Logging.
    job_label = "monthly-report" + (" (dry-run)" if dry_run else "")
    run_row = start_run(job_label)

    details: list[dict] = []
    succeeded: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []

    try:
        properties = config.load_properties()
    except Exception as e:
        print(f"FATAL: failed to load properties: {e}")
        duration = int(time.time() - start_time)
        finalize_run(
            row_key=run_row,
            job_name=job_label,
            status="failed",
            properties_processed=0,
            properties_failed=0,
            duration_seconds=duration,
            summary=f"Failed to load properties: {e}",
            details=[],
        )
        raise

    now = datetime.now(timezone.utc)
    report_period = _quarter(now.month, now.year)

    for prop in properties:
        print(f"  Generating report for: {prop.name}")
        try:
            replacements = _resolve_replacements(prop, report_period)

            if dry_run:
                _print_dry_run_block(prop.name, replacements)
                details.append({
                    "name": prop.name,
                    "status": "preview",
                    "placeholders": replacements,
                })
                succeeded.append((prop.name, ""))
                continue

            if not prop.slides_template_id:
                raise ValueError(f"slides_template_id is empty for '{prop.name}'")

            deck_title = f"{prop.name} — {report_period} Investor Update"
            try:
                presentation_id = copy_template(prop.slides_template_id, deck_title)
            except Exception as e:
                raise RuntimeError(f"failed to copy template for '{prop.name}': {e}") from e

            fill_placeholders(presentation_id, replacements)

            url = get_presentation_url(presentation_id)

            # Post-fill safety check: if the deck still contains any
            # `{{TAG}}` patterns, the template has a tag the backend does
            # not know how to fill (typo, new tag, etc.). Treat as failure
            # so it lands on the dashboard, but do NOT delete the deck —
            # the operator may want to inspect it to learn what's missing.
            unfilled = find_unfilled_placeholders(presentation_id)
            if unfilled:
                err = f"deck has unfilled placeholders: {unfilled}"
                print(f"    ERROR [{prop.name}]: {err} (deck left in place for inspection: {url})")
                failed.append((prop.name, err))
                details.append({
                    "name": prop.name,
                    "status": "failed",
                    "error": err,
                    "urls": {"deck": url},
                })
                continue

            succeeded.append((prop.name, url))
            details.append({"name": prop.name, "status": "success", "urls": {"deck": url}})
            print(f"    Deck created: {url}")
        except Exception as e:
            err = str(e)
            print(f"    ERROR generating report for '{prop.name}': {err}")
            failed.append((prop.name, err))
            details.append({"name": prop.name, "status": "failed", "error": err})

    properties_processed = len(succeeded) + len(failed)
    properties_failed = len(failed)
    duration = int(time.time() - start_time)

    if dry_run:
        dry_status = _compute_status(properties_processed, properties_failed)
        dry_summary = (
            f"Dry-run: resolved placeholders for {len(succeeded)} propert"
            f"{'y' if len(succeeded) == 1 else 'ies'}, {properties_failed} failed"
        )
        finalize_run(
            row_key=run_row,
            job_name=job_label,
            status=dry_status,
            properties_processed=properties_processed,
            properties_failed=properties_failed,
            duration_seconds=duration,
            summary=dry_summary,
            details=details,
        )
        print("Monthly report job complete (dry run — no Slack post sent).")
        return

    lines = [f":bar_chart: *{report_period} Investor Reports — Ready for Review*"]
    if succeeded:
        lines.append("Please review each deck before sending to investors:")
        for name, url in succeeded:
            lines.append(f"• {name} → {url}")
    else:
        lines.append("_No decks were successfully generated._")
    if failed:
        lines.append("")
        lines.append(f":warning: *{len(failed)} propert{'y' if len(failed) == 1 else 'ies'} failed:*")
        for name, err in failed:
            lines.append(f"• {name}: {err}")
    if succeeded:
        lines.append("")
        lines.append("Once reviewed, send directly to your investor distribution list.")

    try:
        post_message(config.REVIEW_CHANNEL_ID, "\n".join(lines), config.SLACK_BOT_TOKEN)
    except Exception as e:
        print(f"ERROR posting Slack notification: {e}")

    status = _compute_status(properties_processed, properties_failed)
    fail_snippet = ""
    if failed:
        first = failed[0]
        fail_snippet = f" ({first[0]}: {first[1]})"
    summary = (
        f"Generated {len(succeeded)} deck{'s' if len(succeeded) != 1 else ''}"
        f", {properties_failed} failed{fail_snippet}"
    )
    finalize_run(
        row_key=run_row,
        job_name=job_label,
        status=status,
        properties_processed=properties_processed,
        properties_failed=properties_failed,
        duration_seconds=duration,
        summary=summary,
        details=details,
    )
    print("Monthly report job complete.")
