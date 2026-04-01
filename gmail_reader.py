import os
import json
import logging
import base64
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def get_gmail_service():
    return build("gmail", "v1", credentials=get_credentials())

def decode_body(payload):
    """Extract plain text body from email payload, handling nested multipart."""
    body = ""

    def extract_parts(part):
        nonlocal body
        mime_type = part.get("mimeType", "")
        # Recurse into multipart containers
        if mime_type.startswith("multipart"):
            for subpart in part.get("parts", []):
                extract_parts(subpart)
        elif mime_type == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                body += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    extract_parts(payload)

    # Fallback to top level body if nothing found
    if not body:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    return body[:2000]

def get_message_detail(service, msg_id):
    """Get full details of a single email."""
    try:
        msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        timestamp = int(msg["internalDate"]) / 1000
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        return {
            "id": msg_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": date,
            "days_ago": (datetime.now(timezone.utc) - date).days,
            "body": decode_body(msg["payload"]),
            "thread_id": msg["threadId"]
        }
    except Exception as e:
        logger.warning(f"Failed to get message {msg_id}: {e}")
        return None

def search_messages(service, query, max_results=20):
    """Search Gmail and return message details."""
    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        detailed = []
        for msg in messages:
            detail = get_message_detail(service, msg["id"])
            if detail:
                detailed.append(detail)
        return detailed
    except Exception as e:
        logger.error(f"Gmail search failed for query '{query}': {e}")
        return []

def get_inbox_emails(companies):
    """Get recent unread emails from recruiters and hiring managers."""
    service = get_gmail_service()
    company_names = [c.get("Company", "") for c in companies if c.get("Company")]
    query = "is:unread newer_than:14d"
    emails = search_messages(service, query, max_results=30)
    logger.info(f"Found {len(emails)} unread emails")
    return emails

def get_sent_emails(companies):
    """Get sent emails from last 30 days to track follow ups needed."""
    service = get_gmail_service()
    query = "in:sent newer_than:30d"
    emails = search_messages(service, query, max_results=50)
    logger.info(f"Found {len(emails)} sent emails")
    return emails

def get_all_email_data(companies):
    """Return inbox and sent emails for Claude to analyze."""
    return {
        "inbox": get_inbox_emails(companies),
        "sent": get_sent_emails(companies)
    }

if __name__ == "__main__":
    from sheets_reader import read_tracker
    companies = read_tracker()
    data = get_all_email_data(companies)
    print(f"Inbox: {len(data['inbox'])} emails")
    print(f"Sent: {len(data['sent'])} emails")
    for email in data["inbox"][:3]:
        print(f"\n--- {email['subject']} ({email['days_ago']} days ago) ---")
        print(email["body"][:200])
