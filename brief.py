import os
import json
import logging
from datetime import datetime, timezone
from anthropic import Anthropic
from sheets_reader import read_tracker, get_active_companies
from gmail_reader import get_all_email_data
from calendar_reader import get_upcoming_events
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Anthropic()
YOUR_EMAIL = os.environ.get("YOUR_EMAIL")

def get_gmail_service():
    creds_json = os.environ.get("GMAIL_CREDENTIALS")
    creds_data = json.loads(creds_json)
    creds = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data["refresh_token"],
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"]
    )
    return build("gmail", "v1", credentials=creds)

def load_voice_samples():
    """Load Emily's voice samples for draft replies."""
    try:
        with open("voice_samples.txt", "r") as f:
            return f.read()
    except Exception:
        return ""

def is_weekly_summary_day():
    """Returns True if today is Monday."""
    return datetime.now(timezone.utc).weekday() == 0

def format_emails_for_claude(emails):
    """Trim email data to essentials for Claude."""
    formatted = []
    for e in emails:
        formatted.append({
            "subject": e.get("subject", ""),
            "from": e.get("from", ""),
            "to": e.get("to", ""),
            "days_ago": e.get("days_ago", 0),
            "body": e.get("body", "")[:1000]
        })
    return formatted

def format_events_for_claude(events):
    """Trim event data to essentials for Claude."""
    formatted = []
    for e in events:
        formatted.append({
            "title": e.get("title", ""),
            "days_away": e.get("days_away", 0),
            "start": e.get("start", ""),
            "attendees": e.get("attendees", []),
            "description": e.get("description", "")[:300]
        })
    return formatted

def generate_daily_brief(companies, email_data, calendar_data, voice_samples):
    """Ask Claude to generate the full daily brief."""
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    is_monday = is_weekly_summary_day()

    if is_monday:
        task_instructions = "Generate a WEEKLY MOMENTUM REPORT. Summarize pipeline health, what moved forward, what stalled, who went quiet, where energy was spent vs where the opportunity is, and recommended focus for the week. Keep it tight and strategic."
    else:
        task_instructions = """Generate a DAILY BRIEF with these sections in order:

PRIORITY ACTIONS
List 3-5 items ranked by urgency. For each item needing a reply include a DRAFT in Emily's voice. Keep drafts concise and natural, 2-4 sentences max. Format each as:
[P1] Action needed
     DRAFT: draft text here

TODAY
For each meeting today:
- Take the attendee emails and search through her inbox and sent mail to find any related threads
- Identify who each attendee is and what company they represent based on those email threads
- If the meeting title is vague, figure out who the person is from the email history
- Flag any unread emails from attendees she has not responded to
- Flag if she has not been in touch with the attendee recently and may need a prep or confirmation note
- If there is no email history with an attendee at all, flag it as a cold or uncontextualized meeting

THIS WEEK
Apply the same attendee cross-reference logic to all meetings this week.
Flag anything unconfirmed, missing email history, or needing prep.

LONG RANGE
Anything 2 or more weeks out worth getting ahead of.

GONE QUIET
Companies marked active in her tracker with no email activity in 7 or more days. Suggest a next move for each.

WAITING ON THEM
Emails Emily sent with no reply yet. Flag anything overdue based on priority:
High priority flag after 3 days, Medium priority flag after 6 days, Low priority flag after 10 days.

Keep the entire brief concise and scannable. No fluff. Emily reads this at 6:30am."""

    prompt = """You are Emily's personal job search chief of staff. Today is """ + today + """.

You have access to four sources of data:

1. HER COMPANY TRACKER:
""" + json.dumps(companies, indent=2) + """

2. HER INBOX (unread emails, last 14 days):
""" + json.dumps(format_emails_for_claude(email_data['inbox']), indent=2) + """

3. HER SENT EMAILS (last 30 days):
""" + json.dumps(format_emails_for_claude(email_data['sent']), indent=2) + """

4. HER CALENDAR:
Today: """ + json.dumps(format_events_for_claude(calendar_data['today']), indent=2) + """
This week: """ + json.dumps(format_events_for_claude(calendar_data['this_week']), indent=2) + """
Next two weeks: """ + json.dumps(format_events_for_claude(calendar_data['next_two_weeks']), indent=2) + """
Long range: """ + json.dumps(format_events_for_claude(calendar_data['long_range']), indent=2) + """

5. EMILY'S WRITING VOICE:
""" + voice_samples + """

YOUR TASK:
""" + task_instructions + """

Cross reference all data sources. Connect calendar meetings to email threads to companies in her tracker. Think strategically.

Return plain text only, no markdown, no asterisks, no pound signs."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()

def send_brief(content, is_monday):
    """Send the daily brief via Gmail."""
    service = get_gmail_service()
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    if is_monday:
        subject = f"Weekly Momentum Report - {today}"
    else:
        subject = f"Daily Brief - {today}"

    email_lines = [
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        f"To: {YOUR_EMAIL}",
        f"From: {YOUR_EMAIL}",
        f"Subject: {subject}",
        "",
        content
    ]
    raw_email = "\n".join(email_lines)
    encoded = base64.urlsafe_b64encode(raw_email.encode()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": encoded}
    ).execute()

    logger.info(f"Brief sent successfully")

def main():
    logger.info("Starting daily brief...")

    # Load all data sources
    logger.info("Reading company tracker...")
    all_companies = read_tracker()
    active_companies = get_active_companies(all_companies)
    logger.info(f"Found {len(active_companies)} active companies")

    logger.info("Reading emails...")
    email_data = get_all_email_data(active_companies)

    logger.info("Reading calendar...")
    calendar_data = get_upcoming_events(days_ahead=30)

    logger.info("Loading voice samples...")
    voice_samples = load_voice_samples()

    # Generate the brief
    logger.info("Generating brief with Claude...")
    is_monday = is_weekly_summary_day()
    brief_content = generate_daily_brief(
        active_companies,
        email_data,
        calendar_data,
        voice_samples
    )

    # Send it
    logger.info("Sending email...")
    send_brief(brief_content, is_monday)

    logger.info("Done!")

if __name__ == "__main__":
    main()
