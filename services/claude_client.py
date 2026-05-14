import anthropic

EXTRACT_PROMPT = """\
You are a property management assistant for a real estate private equity firm.
Below are Slack messages from the property channel for {property_name}.
Extract meaningful updates only. Ignore casual conversation, greetings, and reactions.

Output exactly five sections using the plain-text labels shown below (no markdown, no asterisks).
Each label appears on its own line, followed by the content.
If a section has no relevant content, write "No updates this period." under that label.

Property Update
[Narrative paragraph summarizing leasing activity, tenant status, broker updates, \
and any other property-level developments. Write in third person for an investor report.]

Active Prospects
[Bullet list of active prospects or deals in progress. One bullet per prospect, starting with a dash (-). \
Include name, square footage, lease terms if known, and current status. \
If none, write "No active prospects this period."]

{market_name} Market Update
[Narrative paragraph summarizing market-level observations, comparable transactions, \
vacancy trends, broker sentiment, and economic conditions. Suitable for an investor report.]

Financial Update
Cash Balance: [amount if mentioned, otherwise leave blank]
[Any other financial notes: rent collections, delinquencies, upcoming expenses, capital items.]

What We're Reading
[List any articles, reports, or resources shared or mentioned. One per line starting with a dash (-). \
If none, write "No reading list items this period."]

If there are absolutely no meaningful updates in the messages, respond with exactly: NO_UPDATES

Messages:
{messages}
"""


def extract_property_updates(
    property_name: str, market_name: str, messages: list[dict], api_key: str
) -> str | None:
    """Returns formatted update text with five sections, or None if no meaningful updates."""
    if not messages:
        return None

    formatted_messages = "\n".join(
        f"[{m['ts']}] {m['text']}" for m in messages
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": EXTRACT_PROMPT.format(
                    property_name=property_name,
                    market_name=market_name,
                    messages=formatted_messages,
                ),
            }
        ],
    )

    result = response.content[0].text.strip()
    if result == "NO_UPDATES":
        return None
    return result
