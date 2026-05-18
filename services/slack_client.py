import time
from datetime import datetime, timedelta, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# Cap unbounded history fetches: if the caller's oldest_timestamp is empty
# or older than this many days, we clamp the lookback to this window and
# log a warning. Prevents pulling years of channel history on first run.
DEFAULT_LOOKBACK_DAYS = 30

# 429 retry policy
_MAX_429_RETRIES = 3
_DEFAULT_RETRY_AFTER_SECS = 5
# Cap on Retry-After honored before giving up: Slack can ask for 30-60s+,
# and N channels × 3 retries × 60s blows past Cloud Run's wall-clock limit.
# If a Retry-After exceeds this, raise SlackRateLimitExceeded so the caller
# can skip the channel and continue with the rest of the run.
MAX_RETRY_WAIT_SECONDS = 30


class SlackRateLimitExceeded(Exception):
    """Raised when Slack 429 Retry-After exceeds MAX_RETRY_WAIT_SECONDS."""

    def __init__(self, channel_id: str, retry_after: int):
        self.channel_id = channel_id
        self.retry_after = retry_after
        super().__init__(
            f"Slack 429 Retry-After {retry_after}s exceeds cap "
            f"{MAX_RETRY_WAIT_SECONDS}s for channel {channel_id}; skipping"
        )


def _resolve_oldest(oldest_timestamp: str, channel_id: str) -> str:
    """Clamp `oldest_timestamp` to the DEFAULT_LOOKBACK_DAYS window.

    Returns a Slack-style epoch-seconds string. Logs a warning whenever
    the cap is applied so the operator knows older messages were skipped.
    """
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    cutoff_ts = cutoff_dt.timestamp()

    if not oldest_timestamp:
        print(
            f"WARN [{channel_id}]: last_sync_timestamp is empty/ancient, "
            f"capping lookback to {DEFAULT_LOOKBACK_DAYS}d; "
            f"older messages will not be processed."
        )
        return f"{cutoff_ts:.6f}"

    try:
        caller_ts = float(oldest_timestamp)
    except (TypeError, ValueError):
        print(
            f"WARN [{channel_id}]: last_sync_timestamp {oldest_timestamp!r} is "
            f"unparseable, capping lookback to {DEFAULT_LOOKBACK_DAYS}d; "
            f"older messages will not be processed."
        )
        return f"{cutoff_ts:.6f}"

    if caller_ts < cutoff_ts:
        print(
            f"WARN [{channel_id}]: last_sync_timestamp is empty/ancient, "
            f"capping lookback to {DEFAULT_LOOKBACK_DAYS}d; "
            f"older messages will not be processed."
        )
        return f"{cutoff_ts:.6f}"

    return oldest_timestamp


def _conversations_history_with_retry(client: WebClient, channel_id: str, kwargs: dict):
    """Call conversations_history with 429 retry/backoff.

    Retries up to _MAX_429_RETRIES times on HTTP 429, honoring the
    Retry-After header when present. Non-429 SlackApiError propagates
    unchanged for the caller to handle.
    """
    for attempt in range(1, _MAX_429_RETRIES + 1):
        try:
            return client.conversations_history(**kwargs)
        except SlackApiError as e:
            status = getattr(e.response, "status_code", None)
            if status != 429:
                raise
            if attempt == _MAX_429_RETRIES:
                # Out of retries; let the caller see the 429.
                raise
            retry_after = _DEFAULT_RETRY_AFTER_SECS
            headers = getattr(e.response, "headers", None) or {}
            header_val = headers.get("Retry-After") or headers.get("retry-after")
            if header_val:
                try:
                    retry_after = int(header_val)
                except (TypeError, ValueError):
                    retry_after = _DEFAULT_RETRY_AFTER_SECS
            if retry_after > MAX_RETRY_WAIT_SECONDS:
                raise SlackRateLimitExceeded(channel_id, retry_after) from e
            print(
                f"WARN [{channel_id}]: Slack 429, retrying in {retry_after}s "
                f"(attempt {attempt}/{_MAX_429_RETRIES})"
            )
            time.sleep(retry_after)
    # Unreachable, but keeps type checkers happy.
    raise RuntimeError("conversations_history retry loop exited unexpectedly")


def get_messages_since(channel_id: str, oldest_timestamp: str, token: str) -> list[dict]:
    """Return list of {user, text, ts} dicts for messages newer than oldest_timestamp.

    If `oldest_timestamp` is empty or older than DEFAULT_LOOKBACK_DAYS ago,
    the lookback is capped to that window (with a logged warning).
    """
    client = WebClient(token=token)
    messages = []
    cursor = None

    effective_oldest = _resolve_oldest(oldest_timestamp, channel_id)

    while True:
        kwargs = {
            "channel": channel_id,
            "oldest": effective_oldest,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor

        try:
            response = _conversations_history_with_retry(client, channel_id, kwargs)
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
