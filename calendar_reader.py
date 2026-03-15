import os
import json
import logging
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

def get_calendar_service():
    return build("calendar", "v3", credentials=get_credentials())

def parse_event(event):
    """Extract useful fields from a calendar event."""
    start = event.get("start", {})
    end = event.get("end", {})

    # Handle all day events vs timed events
    start_str = start.get("dateTime", start.get("date", ""))
    end_str = end.get("dateTime", end.get("date", ""))

    try:
        if "T" in start_str:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        else:
            start_dt = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    except Exception:
        start_dt = datetime.now(timezone.utc)

    days_away = (start_dt.date() - datetime.now(timezone.utc).date()).days

    attendees = [
        a.get("email", "") for a in event.get("attendees", [])
        if not a.get("self", False)
    ]

    return {
        "title": event.get("summary", "No title"),
        "start": start_str,
        "start_dt": start_dt,
        "days_away": days_away,
        "location": event.get("location", ""),
        "description": event.get("description", "")[:500],
        "attendees": attendees,
        "meeting_link": event.get("hangoutLink", ""),
        "event_id": event.get("id", "")
    }

def get_upcoming_events(days_ahead=30):
    """Fetch all calendar events for the next 30 days."""
    try:
        service = get_calendar_service()

        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=days_ahead)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        parsed = [parse_event(e) for
