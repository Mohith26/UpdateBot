import time
import config
from services.slack_client import post_message
from services.run_log import finalize_run, start_run


def _doc_link(doc_id: str) -> str:
    if not doc_id:
        return ""
    return f"https://docs.google.com/document/d/{doc_id}/edit"


def _compute_status(processed: int, failed: int) -> str:
    if processed == 0:
        return "failed"
    if failed == 0:
        return "success"
    if failed >= processed:
        return "failed"
    return "partial"


def run() -> None:
    start_time = time.time()
    print("Starting weekly-notify job...")

    # Write a 'running' RunLog row immediately so the dashboard reflects
    # the job even if we crash before finalize_run.
    run_row = start_run("weekly-notify")

    details: list[dict] = []
    failed: list[tuple[str, str]] = []
    succeeded: list[str] = []

    try:
        properties = config.load_properties()
    except Exception as e:
        print(f"FATAL: failed to load properties: {e}")
        duration = int(time.time() - start_time)
        finalize_run(
            row_key=run_row,
            job_name="weekly-notify",
            status="failed",
            properties_processed=0,
            properties_failed=0,
            duration_seconds=duration,
            summary=f"Failed to load properties: {e}",
            details=[],
        )
        raise

    lines = [":spiral_notepad: *Weekly Property Doc Review*"]
    lines.append("Please review and edit the following docs before the monthly report cycle:\n")

    for prop in properties:
        try:
            if not prop.live_doc_id:
                raise ValueError(f"live_doc_id is empty for '{prop.name}'")
            link = _doc_link(prop.live_doc_id)
            lines.append(f"• {prop.name} → {link}")
            succeeded.append(prop.name)
            details.append({
                "name": prop.name,
                "status": "success",
                "urls": {"doc": link},
            })
        except Exception as e:
            err = str(e)
            print(f"  WARNING: skipping '{prop.name}': {err}")
            failed.append((prop.name, err))
            details.append({"name": prop.name, "status": "failed", "error": err})

    lines.append("\nDocs will be used to generate investor reports on the 1st.")

    processed = len(succeeded) + len(failed)
    failed_count = len(failed)
    assembly_ok = len(succeeded) > 0
    print(
        f"weekly-notify: doc assembly "
        f"{'succeeded' if assembly_ok else 'failed'} "
        f"({len(succeeded)} ok, {failed_count} failed)"
    )

    message = "\n".join(lines)
    post_failed = False
    post_error = ""
    try:
        post_message(config.REVIEW_CHANNEL_ID, message, config.SLACK_BOT_TOKEN)
        print(f"weekly-notify: Slack notification posted to channel {config.REVIEW_CHANNEL_ID}.")
    except Exception as e:
        post_failed = True
        post_error = str(e)
        print(f"ERROR weekly-notify: Slack notification FAILED: {post_error}")

    duration = int(time.time() - start_time)

    # Status precedence:
    #   1. If every property failed → "failed" regardless of the Slack post.
    #   2. Else if Slack post failed → "partial" (decks are ready in the docs,
    #      but operators won't see the prompt unless they check the dashboard).
    #   3. Else → standard processed/failed compute.
    if processed > 0 and failed_count >= processed:
        status = "failed"
    elif post_failed and processed > 0:
        status = "partial"
    else:
        status = _compute_status(processed, failed_count)

    fail_snippet = ""
    if failed:
        first = failed[0]
        fail_snippet = f" ({first[0]}: {first[1]})"
    summary_parts = [
        f"Listed {len(succeeded)} propert{'y' if len(succeeded) == 1 else 'ies'}",
        f"{failed_count} failed{fail_snippet}",
    ]
    if post_failed:
        summary_parts.append(f"Slack notification FAILED: {post_error}")
    summary = "; ".join(summary_parts)
    finalize_run(
        row_key=run_row,
        job_name="weekly-notify",
        status=status,
        properties_processed=processed,
        properties_failed=failed_count,
        duration_seconds=duration,
        summary=summary,
        details=details,
    )
