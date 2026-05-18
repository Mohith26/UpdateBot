import anthropic


_BASE_SECTIONS = """\
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
"""

EXTRACT_PROMPT = """\
You are a property management assistant for a real estate private equity firm.
Below are Slack messages from the property channel for {property_name}.
Extract meaningful updates only. Ignore casual conversation, greetings, and reactions.

""" + _BASE_SECTIONS + """
Messages:
{messages}
"""

MERGE_PROMPT = """\
You are a property management assistant for a real estate private equity firm.
You are updating the existing monthly entry for {property_name} with new Slack
activity. Produce a SINGLE refreshed version of the entry that incorporates
the new messages — do not duplicate items already present, do not append the
new content as a separate block. Refine narratives, update prospect statuses,
add new prospects, refresh financial figures, and integrate new reading items.
If the new messages contain nothing material beyond what the existing entry
already says, return the existing entry essentially unchanged.

""" + _BASE_SECTIONS + """
Existing entry for this month (verbatim — refresh this, do not repeat it):
{existing_section}

New Slack messages since the last sync:
{messages}
"""


def _format_tone_examples(examples: list[str]) -> str:
    if not examples:
        return ""
    bodies = "\n\n---\n\n".join(examples)
    return (
        "\n\nFor tone, voice, and level of detail, here are recent monthly "
        "entries from this same property's doc. Match this writing style:\n\n"
        f"{bodies}\n"
    )


def extract_property_updates(
    property_name: str,
    market_name: str,
    messages: list[dict],
    api_key: str,
    existing_section: str | None = None,
    tone_examples: list[str] | None = None,
) -> str | None:
    """Returns formatted update text with five sections, or None if no meaningful updates.

    When `existing_section` is provided, the LLM is asked to MERGE the new
    messages into that section instead of producing a fresh summary. When
    `tone_examples` is non-empty, those prior entries are included as
    style reference so the writing voice stays consistent month-over-month.
    """
    if not messages:
        return None

    formatted_messages = "\n".join(f"[{m['ts']}] {m['text']}" for m in messages)

    if existing_section:
        prompt = MERGE_PROMPT.format(
            property_name=property_name,
            market_name=market_name,
            existing_section=existing_section.strip(),
            messages=formatted_messages,
        )
    else:
        prompt = EXTRACT_PROMPT.format(
            property_name=property_name,
            market_name=market_name,
            messages=formatted_messages,
        )

    prompt += _format_tone_examples(tone_examples or [])

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    result = response.content[0].text.strip()
    if result == "NO_UPDATES":
        return None
    return result
