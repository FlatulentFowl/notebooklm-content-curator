import datetime
import os
import json
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the token file.
SCOPES = [
    'https://www.googleapis.com/auth/drive.meet.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
]

HEADING_MAP = {
    'HEADING_1': '#',
    'HEADING_2': '##',
    'HEADING_3': '###',
    'HEADING_4': '####',
    'HEADING_5': '#####',
    'HEADING_6': '######',
}


def doc_content_to_markdown(body_content):
    """Convert Google Docs body content elements to a markdown string."""
    lines = []
    for element in body_content:
        paragraph = element.get('paragraph')
        if not paragraph:
            continue

        style = paragraph.get('paragraphStyle', {}).get('namedStyleType', 'NORMAL_TEXT')

        text = ''
        for pe in paragraph.get('elements', []):
            text += pe.get('textRun', {}).get('content', '')
        text = text.rstrip('\n')

        if not text:
            lines.append('')
            continue

        if style in HEADING_MAP:
            lines.append(f"{HEADING_MAP[style]} {text}")
        elif paragraph.get('bullet'):
            nesting = paragraph['bullet'].get('nestingLevel', 0)
            indent = '  ' * nesting
            lines.append(f"{indent}- {text}")
        else:
            lines.append(text)

    return '\n'.join(lines)


def safe_filename(name):
    """Strip characters that are invalid in filenames."""
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()


OUTPUT_DIR = "Google Meet"


def write_file(filename, content):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Exported → {path}")


def main():
    """Finds Google Meet Gemini notes from calendar events in the last 24 hours and exports them as markdown."""
    config_dir = os.path.expanduser('~/.config/productivity-agent')
    os.makedirs(config_dir, exist_ok=True)
    token_path = os.path.join(config_dir, 'google-meet-token.json')
    creds_path = os.path.join(config_dir, 'credentials.json')

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    try:
        calendar_service = build('calendar', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)

        # Load configuration
        ignored_meetings = []
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                config_data = json.load(f)
                ignored_meetings = config_data.get('ignored_meetings', [])

        # Calculate the past 24 hours date range (SAST)
        sast_tz = datetime.timezone(datetime.timedelta(hours=2), name="SAST")
        now = datetime.datetime.now(sast_tz)
        twenty_four_hours_ago = now - datetime.timedelta(days=1)

        time_min = twenty_four_hours_ago.astimezone(datetime.timezone.utc).isoformat()
        time_max = now.astimezone(datetime.timezone.utc).isoformat()

        print(f"Looking for calendar events with Meet notes from the last 24 hours (since {twenty_four_hours_ago.isoformat()})")

        # Fetch calendar events for the last 24 hours.
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            print('No calendar events found in the last 24 hours.')
            return

        print(f'Found {len(events)} calendar event(s). Checking for attached Gemini notes...')

        files_written = 0

        for event in events:
            event_title = event.get('summary', 'Untitled Meeting')
            event_id = event.get('id', '')
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))

            # Check if this meeting should be ignored (by title or event ID)
            if event_title in ignored_meetings or event_id in ignored_meetings:
                print(f"Skipping ignored meeting: {event_title}")
                continue

            # Gemini notes are linked as Google Doc attachments on the calendar event
            attachments = event.get('attachments', [])
            doc_attachments = [
                a for a in attachments
                if a.get('mimeType') == 'application/vnd.google-apps.document'
            ]

            if not doc_attachments:
                continue

            # Format the event start time as DD-MM-YYYY for filenames
            try:
                start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted_date = start_dt.strftime("%d-%m-%Y")
            except Exception:
                formatted_date = now.strftime("%d-%m-%Y")

            base_name = safe_filename(event_title)
            print(f"\nProcessing: {event_title} ({formatted_date})")

            for attachment in doc_attachments:
                file_id = attachment.get('fileId')
                file_title = attachment.get('title', 'Untitled')

                if not file_id:
                    continue

                print(f"  Reading: {file_title}")

                try:
                    doc = docs_service.documents().get(
                        documentId=file_id,
                        includeTabsContent=True
                    ).execute()
                except Exception as e:
                    print(f"  Could not read '{file_title}': {e}")
                    continue

                tabs = doc.get('tabs', [])

                if not tabs:
                    # No tabs — treat the whole document body as notes
                    body_content = doc.get('body', {}).get('content', [])
                    notes_md = doc_content_to_markdown(body_content)
                    if notes_md.strip():
                        filename = f"{base_name} - {formatted_date}.md"
                        write_file(filename, f"# {event_title}\n\n{notes_md}")
                        files_written += 1
                else:
                    # Tab 1: Notes
                    notes_md = ''
                    if len(tabs) >= 1:
                        notes_body = tabs[0].get('documentTab', {}).get('body', {}).get('content', [])
                        notes_md = doc_content_to_markdown(notes_body)

                    # Tab 2: Transcript
                    transcript_md = ''
                    if len(tabs) >= 2:
                        transcript_body = tabs[1].get('documentTab', {}).get('body', {}).get('content', [])
                        transcript_md = doc_content_to_markdown(transcript_body)

                    # Skip meetings that have neither notes nor transcript
                    if not notes_md.strip() and not transcript_md.strip():
                        print(f"  No content found — skipping.")
                        continue

                    if notes_md.strip():
                        filename = f"{base_name} - {formatted_date}.md"
                        write_file(filename, f"# {event_title}\n\n{notes_md}")
                        files_written += 1

                    if transcript_md.strip():
                        filename = f"{base_name} - {formatted_date} (Transcript).md"
                        write_file(filename, f"# {event_title} (Transcript)\n\n{transcript_md}")
                        files_written += 1

        if files_written:
            print(f"\n{files_written} file(s) exported.")
        else:
            print("\nNo Gemini notes found on any calendar events.")

    except Exception as error:
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
