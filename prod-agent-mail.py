import base64
import datetime
import os
import json
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

OUTPUT_DIR = "Google Mail"


def get_header(headers, name):
    """Return the value of a message header by name (case-insensitive)."""
    for h in headers:
        if h.get('name', '').lower() == name.lower():
            return h.get('value', '')
    return ''


def extract_body(payload):
    """
    Walk the message payload tree to extract plain text body.
    Prefers text/plain; falls back to stripping HTML from text/html.
    """
    mime_type = payload.get('mimeType', '')

    # Single-part plain text
    if mime_type == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')

    # Single-part HTML — strip tags
    if mime_type == 'text/html':
        data = payload.get('body', {}).get('data', '')
        if data:
            html = base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')
            return re.sub(r'<[^>]+>', '', html)

    # Multipart — recurse into parts, prefer plain over html
    parts = payload.get('parts', [])
    plain_body = ''
    html_body = ''
    for part in parts:
        result = extract_body(part)
        if result:
            if part.get('mimeType', '') == 'text/plain' or 'plain' in part.get('mimeType', ''):
                plain_body = result
            else:
                html_body = result

    return plain_body or html_body


def is_meeting_invite(payload):
    """Return True if the message contains a calendar/iCalendar part."""
    mime_type = payload.get('mimeType', '')
    if mime_type == 'text/calendar':
        return True
    for part in payload.get('parts', []):
        if is_meeting_invite(part):
            return True
    return False


def format_email_block(msg):
    """Format a Gmail message object as a markdown block."""
    headers = msg.get('payload', {}).get('headers', [])
    subject = get_header(headers, 'Subject') or '(no subject)'
    from_addr = get_header(headers, 'From')
    to_addr = get_header(headers, 'To')

    # internalDate is milliseconds since epoch
    internal_date_ms = int(msg.get('internalDate', 0))
    dt = datetime.datetime.fromtimestamp(internal_date_ms / 1000, tz=datetime.timezone.utc)
    sast_tz = datetime.timezone(datetime.timedelta(hours=2))
    dt_sast = dt.astimezone(sast_tz)
    formatted_date = dt_sast.strftime("%d-%m-%Y %H:%M")

    body = extract_body(msg.get('payload', {})).strip()

    lines = [
        f"## {subject}",
        f"**From:** {from_addr}",
        f"**To:** {to_addr}",
        f"**Date:** {formatted_date}",
        "",
        body,
        "",
        "---",
        "",
    ]
    return '\n'.join(lines)


def fetch_latest_per_thread(gmail_service, query):
    """
    List messages matching query, group by threadId, return only the
    most recent message ID per thread (by internalDate).
    Returns a list of full message dicts.
    """
    # Collect all matching message stubs (id + threadId only)
    stubs = []
    page_token = None
    while True:
        kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token
        result = gmail_service.users().messages().list(**kwargs).execute()
        stubs.extend(result.get('messages', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break

    if not stubs:
        return []

    # Fetch minimal metadata (internalDate + threadId) for deduplication
    thread_latest = {}  # threadId -> (internalDate, messageId)
    for stub in stubs:
        msg_id = stub['id']
        thread_id = stub['threadId']
        meta = gmail_service.users().messages().get(
            userId='me', id=msg_id, format='metadata',
            metadataHeaders=['Date']
        ).execute()
        internal_date = int(meta.get('internalDate', 0))
        if thread_id not in thread_latest or internal_date > thread_latest[thread_id][0]:
            thread_latest[thread_id] = (internal_date, msg_id)

    # Fetch full content only for the surviving messages
    messages = []
    for _, msg_id in thread_latest.values():
        full_msg = gmail_service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
        messages.append(full_msg)

    # Sort by internalDate ascending (oldest first)
    messages.sort(key=lambda m: int(m.get('internalDate', 0)))
    return messages


def main():
    """Fetches sent and received emails from the last 24 hours and exports them as markdown."""
    config_dir = os.path.expanduser('~/.config/productivity-agent')
    os.makedirs(config_dir, exist_ok=True)
    token_path = os.path.join(config_dir, 'google-mail-token.json')
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
        gmail_service = build('gmail', 'v1', credentials=creds)

        # Load configuration
        ignored_senders = []
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                config_data = json.load(f)
                ignored_senders = [s.lower() for s in config_data.get('ignored_senders', [])]

        # Calculate the past 24 hours date range (SAST)
        sast_tz = datetime.timezone(datetime.timedelta(hours=2), name="SAST")
        now = datetime.datetime.now(sast_tz)
        twenty_four_hours_ago = now - datetime.timedelta(days=1)

        # Gmail search uses Unix epoch seconds in the 'after:' operator
        after_epoch = int(twenty_four_hours_ago.timestamp())
        file_date = now.strftime("%d-%m-%Y")

        print(f"Looking for emails from the last 24 hours (since {twenty_four_hours_ago.isoformat()})")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        for label, query, filename_suffix, heading in [
            ('received', f'in:inbox after:{after_epoch}', 'emails-received', 'Received Emails'),
            ('sent',     f'in:sent after:{after_epoch}',  'emails-sent',     'Sent Emails'),
        ]:
            print(f"\nFetching {label} emails...")
            messages = fetch_latest_per_thread(gmail_service, query)

            if not messages:
                print(f"  No {label} emails found.")
                continue

            print(f"  Found {len(messages)} thread(s) with recent {label} email(s).")

            blocks = []
            skipped = 0
            for msg in messages:
                headers = msg.get('payload', {}).get('headers', [])
                from_addr = get_header(headers, 'From').lower()
                to_addr = get_header(headers, 'To').lower()
                combined = from_addr + ' ' + to_addr

                if any(pattern in combined for pattern in ignored_senders):
                    skipped += 1
                    continue

                if is_meeting_invite(msg.get('payload', {})):
                    skipped += 1
                    continue

                blocks.append(format_email_block(msg))

            if skipped:
                print(f"  Skipped {skipped} email(s) from ignored senders.")

            if not blocks:
                print(f"  No {label} emails to export after filtering.")
                continue

            filepath = os.path.join(OUTPUT_DIR, f"{file_date}-{filename_suffix}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {heading} - {file_date}\n\n")
                f.write('\n'.join(blocks))
            print(f"  Exported → {filepath}")

    except Exception as error:
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
