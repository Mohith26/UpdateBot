from datetime import datetime, timezone
import time
import config
from services.slack_client import SlackRateLimitExceeded, get_messages_since
from services.claude_client import extract_property_updates
from services.google_docs import prepend_update
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
    print("Starting slack-sync job...")

    # Write a 'running' RunLog row immediately so the dashboard reflects
    # the job even if we crash before finalize_run.
    run_row = start_run("slack-sync")

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
            job_name="slack-sync",
            status="failed",
            properties_processed=0,
            properties_failed=0,
            duration_seconds=duration,
            summary=f"Failed to load properties: {e}",
            details=[],
        )
        raise

    now = datetime.now(timezone.utc)

    for prop in properties:
        print(f"  Processing: {prop.name}")
        try:
            if not prop.slack_channel_id:
                raise ValueError(f"slack_channel_id is empty for '{prop.name}'")

            messages = get_messages_since(
                channel_id=prop.slack_channel_id,
                oldest_timestamp=prop.last_sync_timestamp,
                token=config.SLACK_BOT_TOKEN,
            )

            if not messages:
                print(f"    No new messages.")
                succeeded.append(prop.name)
                details.append({
                    "name": prop.name,
                    "status": "success",
                    "urls": {"doc": _doc_link(prop.live_doc_id)},
                })
                continue

            print(f"    Found {len(messages)} new messages. Summarizing with Claude...")
            sections = extract_property_updates(
                property_name=prop.name,
                market_name=prop.market_name,
                messages=messages,
                api_key=config.ANTHROPIC_API_KEY,
            )

            # Order matters: prepend_update must succeed BEFORE we advance
            # last_sync_timestamp. If prepend raises, the except below catches
            # it, the timestamp stays put, and the next run re-processes these
            # messages (rather than silently dropping them).
            if sections is None:
                print(f"    No meaningful updates extracted.")
            else:
                if not prop.live_doc_id:
                    raise ValueError(f"live_doc_id is empty for '{prop.name}'; cannot append update")
                month_year = now.strftime("%B %Y")
                date_header = f"{month_year} Update - {prop.name}"
                content = f"Hi [Name],\n\n{sections}"
                prepend_update(
                    doc_id=prop.live_doc_id,
                    date_header=date_header,
                    content=content,
                )
                print(f"    Appended update to doc.")

            # Only reached if prepend_update returned (or was skipped because
            # extraction found nothing meaningful — in which case re-processing
            # those messages on the next run would still yield None).
            latest_ts = messages[-1]["ts"]
            config.update_last_sync(prop, latest_ts)
            print(f"    Last sync timestamp updated to {latest_ts}.")

            succeeded.append(prop.name)
            details.append({
                "name": prop.name,
                "status": "success",
                "urls": {"doc": _doc_link(prop.live_doc_id)},
            })
        except SlackRateLimitExceeded as e:
            err = (
                f"Slack rate limit Retry-After {e.retry_after}s exceeds cap; "
                f"skipped this property"
            )
            print(f"    SKIP '{prop.name}': {err}")
            failed.append((prop.name, err))
            details.append({
                "name": prop.name,
                "status": "failed",
                "error": err,
                "urls": {"doc": _doc_link(prop.live_doc_id)},
            })
        except Exception as e:
            err = str(e)
            print(f"    ERROR processing '{prop.name}': {err}")
            failed.append((prop.name, err))
            details.append({
                "name": prop.name,
                "status": "failed",
                "error": err,
                "urls": {"doc": _doc_link(prop.live_doc_id)},
            })

    processed = len(succeeded) + len(failed)
    failed_count = len(failed)
    duration = int(time.time() - start_time)
    status = _compute_status(processed, failed_count)
    fail_snippet = ""
    if failed:
        first = failed[0]
        fail_snippet = f" ({first[0]}: {first[1]})"
    summary = (
        f"Synced {len(succeeded)} propert{'y' if len(succeeded) == 1 else 'ies'}, "
        f"{failed_count} failed{fail_snippet}"
    )
    finalize_run(
        row_key=run_row,
        job_name="slack-sync",
        status=status,
        properties_processed=processed,
        properties_failed=failed_count,
        duration_seconds=duration,
        summary=summary,
        details=details,
    )

    print("slack-sync job complete.")
