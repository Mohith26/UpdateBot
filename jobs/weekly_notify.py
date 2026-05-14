import config
from services.slack_client import post_message


def _doc_link(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


def run() -> None:
    print("Starting weekly-notify job...")
    properties = config.load_properties()

    lines = [":spiral_notepad: *Weekly Property Doc Review*"]
    lines.append("Please review and edit the following docs before the monthly report cycle:\n")

    for prop in properties:
        lines.append(f"• {prop.name} → {_doc_link(prop.live_doc_id)}")

    lines.append("\nDocs will be used to generate investor reports on the 1st.")

    message = "\n".join(lines)
    post_message(config.REVIEW_CHANNEL_ID, message, config.SLACK_BOT_TOKEN)
    print(f"Weekly review message posted to channel {config.REVIEW_CHANNEL_ID}.")
