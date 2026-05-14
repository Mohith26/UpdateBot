from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_messages_since(channel_id: str, oldest_timestamp: str, token: str) -> list[dict]:
    """Return list of {user, text, ts} dicts for messages newer than oldest_timestamp."""
    client = WebClient(token=token)
    messages = []
    cursor = None

    while True:
        kwargs = {
            "channel": channel_id,
            "oldest": oldest_timestamp or "0",
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor

        try:
            response = client.conversations_history(**kwargs)
        except SlackApiError as e:
            raise RuntimeError(f"Slack API error for channel {channel_id}: {e.response['error']}") from e

        for msg in response["messages"]:
            # skip bot messages and subtypes (joins, leaves, etc.)
            if msg.get("subtype") or msg.get("bot_id"):
                continue
            if msg.get("text"):
                messages.append({
                    "user": msg.get("user", "unknown"),
                    "text": msg["text"],
                    "ts": msg["ts"],
                })

        metadata = response.get("response_metadata") or {}
        cursor = metadata.get("next_cursor")
        if not cursor:
            break

    # oldest first
    messages.sort(key=lambda m: float(m["ts"]))
    return messages


def post_message(channel_id: str, text: str, token: str) -> None:
    client = WebClient(token=token)
    try:
        client.chat_postMessage(channel=channel_id, text=text)
    except SlackApiError as e:
        raise RuntimeError(f"Slack post error to {channel_id}: {e.response['error']}") from e
