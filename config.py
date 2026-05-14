import os
from dataclasses import dataclass
from services.google_sheets import read_range, write_cell


CONFIG_SHEET_ID = os.environ["CONFIG_SHEET_ID"]
REVIEW_CHANNEL_ID = os.environ["REVIEW_CHANNEL_ID"]

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
# No GOOGLE_SERVICE_ACCOUNT_JSON — Cloud Run uses attached service account via ADC


@dataclass
class Property:
    name: str
    slack_channel_id: str
    live_doc_id: str
    slides_template_id: str
    cell_cash_balance: str          # format: SHEET_ID:RANGE e.g. "1abc...:Sheet1!B5"
    what_we_are_reading_doc_id: str
    address: str
    purchase_date: str
    purchase_price: str
    size_sqft: str
    num_units: str
    year_built: str
    market_name: str
    last_sync_timestamp: str
    config_row_index: int  # 1-based row in the config sheet (for writing back)


# Columns A–M (0-indexed)
_COL = {
    "property_name": 0,               # A
    "slack_channel_id": 1,            # B
    "live_doc_id": 2,                 # C
    "slides_template_id": 3,          # D
    "cell_cash_balance": 4,           # E  format: SHEET_ID:RANGE
    "what_we_are_reading_doc_id": 5,  # F
    "address": 6,                     # G
    "purchase_date": 7,               # H
    "purchase_price": 8,              # I
    "size_sqft": 9,                   # J
    "num_units": 10,                  # K
    "year_built": 11,                 # L
    "market_name": 12,                # M
    "last_sync_timestamp": 13,        # N
}

_HEADER_ROWS = 1
_NUM_COLS = 14  # A through N


def load_properties() -> list[Property]:
    rows = read_range(CONFIG_SHEET_ID, "A1:N200")
    properties = []
    for i, row in enumerate(rows[_HEADER_ROWS:], start=_HEADER_ROWS + 1):
        row = row + [""] * (_NUM_COLS - len(row))
        if not row[_COL["property_name"]]:
            continue
        properties.append(
            Property(
                name=row[_COL["property_name"]],
                slack_channel_id=row[_COL["slack_channel_id"]],
                live_doc_id=row[_COL["live_doc_id"]],
                slides_template_id=row[_COL["slides_template_id"]],
                cell_cash_balance=row[_COL["cell_cash_balance"]],
                what_we_are_reading_doc_id=row[_COL["what_we_are_reading_doc_id"]],
                address=row[_COL["address"]],
                purchase_date=row[_COL["purchase_date"]],
                purchase_price=row[_COL["purchase_price"]],
                size_sqft=row[_COL["size_sqft"]],
                num_units=row[_COL["num_units"]],
                year_built=row[_COL["year_built"]],
                market_name=row[_COL["market_name"]],
                last_sync_timestamp=row[_COL["last_sync_timestamp"]],
                config_row_index=i,
            )
        )
    return properties


def update_last_sync(prop: Property, timestamp: str) -> None:
    col_letter = chr(ord("A") + _COL["last_sync_timestamp"])  # "N"
    cell = f"{col_letter}{prop.config_row_index}"
    write_cell(CONFIG_SHEET_ID, cell, timestamp)
