from datetime import datetime, timezone
import re
import config
from services.google_docs import read_full_text
from services.google_sheets import read_range
from services.google_slides import copy_template, fill_placeholders, get_presentation_url
from services.slack_client import post_message


def _quarter(month: int, year: int) -> str:
    return f"Q{(month - 1) // 3 + 1} {year}"


def _extract_section(doc_text: str, section_name: str) -> str:
    """Extract content under a plain-text section label until the next label or separator."""
    # Match a line that ends with section_name (handles "Laredo Market Update" for "Market Update")
    if section_name == "Market Update":
        header_pattern = r"[^\n]*Market Update"
    else:
        header_pattern = re.escape(section_name)
    pattern = rf"^{header_pattern}\s*\n(.*?)(?=\n[A-Z][^\n]{{0,59}}\n|\n─{{10,}}\n|\Z)"
    match = re.search(pattern, doc_text, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "No updates this period."


def _read_cash_balance(cell_cash_balance: str) -> str:
    """Read cash balance from a combined SHEET_ID:RANGE value, e.g. '1abc...:Sheet1!B5'."""
    if not cell_cash_balance or ":" not in cell_cash_balance:
        return ""
    sheet_id, cell_ref = cell_cash_balance.split(":", 1)
    rows = read_range(sheet_id.strip(), cell_ref.strip())
    if rows and rows[0]:
        return str(rows[0][0])
    return ""


def run() -> None:
    print("Starting monthly-report job...")
    properties = config.load_properties()
    now = datetime.now(timezone.utc)
    report_period = _quarter(now.month, now.year)
    deck_links = []

    for prop in properties:
        print(f"  Generating report for: {prop.name}")

        doc_text = read_full_text(prop.live_doc_id)
        property_updates = _extract_section(doc_text, "Property Update")
        market_update = _extract_section(doc_text, "Market Update")

        what_we_are_reading = ""
        if prop.what_we_are_reading_doc_id:
            what_we_are_reading = read_full_text(prop.what_we_are_reading_doc_id).strip()
        if not what_we_are_reading:
            what_we_are_reading = _extract_section(doc_text, "What We're Reading")

        cash_balance = _read_cash_balance(prop.cell_cash_balance)

        replacements = {
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

        deck_title = f"{prop.name} — {report_period} Investor Update"
        presentation_id = copy_template(prop.slides_template_id, deck_title)
        fill_placeholders(presentation_id, replacements)

        url = get_presentation_url(presentation_id)
        deck_links.append((prop.name, url))
        print(f"    Deck created: {url}")

    lines = [f":bar_chart: *{report_period} Investor Reports — Ready for Review*"]
    lines.append("Please review each deck before sending to investors:\n")
    for name, url in deck_links:
        lines.append(f"• {name} → {url}")
    lines.append("\nOnce reviewed, send directly to your investor distribution list.")

    post_message(config.REVIEW_CHANNEL_ID, "\n".join(lines), config.SLACK_BOT_TOKEN)
    print("Monthly report job complete.")
