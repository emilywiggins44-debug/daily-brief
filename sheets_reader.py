import os
import json
import logging
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SHEET_ID = os.environ.get("SHEET_ID")

def get_credentials():
    creds_json = os.environ.get("GMAIL_CREDENTIALS")
    creds_data = json.loads(creds_json)
    return Credentials(
        token=creds_data["token"],
        refresh_token=creds_data["refresh_token"],
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"]
    )

def read_tracker():
    """Read all rows from the Google Sheet tracker."""
    try:
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)

        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range="Companies | Target!A:G"
        ).execute()

        rows = result.get("values", [])
        if not rows:
            logger.warning("No data found in sheet")
            return []

        # First row is headers
        headers = rows[0]
        companies = []

        for row in rows[1:]:
            # Pad row if missing columns
            while len(row) < len(headers):
                row.append("")

            company = dict(zip(headers, row))
            companies.append(company)

        logger.info(f"Read {len(companies)} companies from tracker")
        return companies

    except Exception as e:
        logger.error(f"Failed to read sheet: {e}")
        return []

def get_active_companies(companies):
    """Return active companies sorted by priority."""
    active_stages = [
        "Applied", "Screening", "Interviewing",
        "Final Round", "Offer"
    ]
    priority_order = {"High": 0, "Medium": 1, "Low": 2}

    active = [
        c for c in companies
        if c.get("Stage", "") in active_stages
    ]

    return sorted(
        active,
        key=lambda c: priority_order.get(c.get("Priority", "Low"), 2)
    )

if __name__ == "__main__":
    companies = read_tracker()
    for c in companies:
        print(c)
