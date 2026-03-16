"""
Google Sheets storage layer.
Each capture becomes a row: timestamp | type | raw_text | extracted_text | source_url | tags
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import os


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheet():
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = spreadsheet.worksheet("captures")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="captures", rows=1000, cols=6)
        worksheet.append_row(
            ["timestamp", "type", "raw_text", "extracted_text", "source_url", "tags"]
        )

    return worksheet


def save_capture(
    capture_type: str,
    raw_text: str = "",
    extracted_text: str = "",
    source_url: str = "",
    tags: str = "",
):
    """Save a single capture to the sheet."""
    sheet = get_sheet()
    timestamp = datetime.now().isoformat()
    sheet.append_row([timestamp, capture_type, raw_text, extracted_text, source_url, tags])
    return timestamp


def get_captures_since(days: int = 7) -> list[dict]:
    """Get all captures from the last N days."""
    sheet = get_sheet()
    all_rows = sheet.get_all_records()

    cutoff = datetime.now() - timedelta(days=days)
    recent = []

    for row in all_rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            if ts >= cutoff:
                recent.append(row)
        except (ValueError, KeyError):
            continue

    return recent
