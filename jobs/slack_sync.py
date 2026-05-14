from datetime import datetime, timezone
import config
from services.slack_client import get_messages_since
from services.claude_client import extract_property_updates
from services.google_docs import prepend_update


def run() -> None:
    print("Starting slack-sync job...")
    properties = config.load_properties()
    now = datetime.now(timezone.utc)

    for prop in properties:
        print(f"  Processing: {prop.name}")

        messages = get_messages_since(
            channel_id=prop.slack_channel_id,
            oldest_timestamp=prop.last_sync_timestamp,
            token=config.SLACK_BOT_TOKEN,
        )

        if not messages:
            print(f"    No new messages.")
            continue

        print(f"    Found {len(messages)} new messages. Summarizing with Claude...")
        sections = extract_property_updates(
            property_name=prop.name,
            market_name=prop.market_name,
            messages=messages,
            api_key=config.ANTHROPIC_API_KEY,
        )

        if sections is None:
            print(f"    No meaningful updates extracted.")
        else:
            month_year = now.strftime("%B %Y")
            date_header = f"{month_year} Update - {prop.name}"
            content = f"Hi [Name],\n\n{sections}"
            prepend_update(
                doc_id=prop.live_doc_id,
                date_header=date_header,
                content=content,
            )
            print(f"    Appended update to doc.")

        latest_ts = messages[-1]["ts"]
        config.update_last_sync(prop, latest_ts)
        print(f"    Last sync timestamp updated to {latest_ts}.")

    print("slack-sync job complete.")
