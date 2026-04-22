import argparse
import base64
import datetime
import os
import re

from googleapiclient.discovery import build
from agent_utils import get_credentials, get_date_range, load_config

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

OUTPUT_DIR = "raw/google-mail"


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
    sast_tz = datetime.timezone(datetime.timedelta(hours=2), name="SAST")
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
    most recent message ID per thread (relying on Gmail's default sort).
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

    # Gmail's list returns messages in reverse chronological order (newest first).
    # The first time we encounter a threadId, it is the latest message in that thread for our query.
    thread_latest_ids = {}
    for stub in stubs:
        thread_id = stub.get('threadId')
        msg_id = stub.get('id')
        if thread_id and msg_id and thread_id not in thread_latest_ids:
            thread_latest_ids[thread_id] = msg_id

    # Fetch full content only for the surviving messages
    messages = []
    for msg_id in thread_latest_ids.values():
        full_msg = gmail_service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
        messages.append(full_msg)

    # Sort by internalDate ascending (oldest first) so the final markdown flows forward
    messages.sort(key=lambda m: int(m.get('internalDate', 0)))
    return messages


def main():
    """Fetches inbound emails from the previous weekday and exports them as markdown."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-date', dest='date', default=None,
                        help="Date to search: DD/MM/YYYY, 'today', or omit for previous weekday")
    args = parser.parse_args()

    creds = get_credentials('google-mail-token.json', SCOPES)

    try:
        gmail_service = build('gmail', 'v1', credentials=creds)

        # Load configuration
        config_data = load_config()
        ignored_senders = [s.lower() for s in config_data.get('ignored_senders', [])]
        ignored_recipients = [r.lower() for r in config_data.get('ignored_recipients', [])]

        # Calculate the target date range (SAST)
        result = get_date_range(args.date)
        if result is None:
            return
        start, end = result

        # Gmail search uses Unix epoch seconds in the 'after:' / 'before:' operators
        after_epoch = int(start.timestamp())
        before_epoch = int(end.timestamp()) + 1  # +1s so 23:59:59 is fully included
        file_date = start.strftime("%d-%m-%Y")

        print(f"Looking for emails between {start.isoformat()} and {end.isoformat()}")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        for label, query, filename_suffix, heading in [
            ('inbound', f'in:inbox after:{after_epoch} before:{before_epoch}', 'emails-inbound', 'Inbound Emails'),
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

                # Filter based on ignored senders and recipients
                if any(pattern in from_addr for pattern in ignored_senders) or \
                   any(pattern in to_addr for pattern in ignored_recipients):
                    skipped += 1
                    continue

                if is_meeting_invite(msg.get('payload', {})):
                    skipped += 1
                    continue

                blocks.append(format_email_block(msg))

            if skipped:
                print(f"  Skipped {skipped} email(s) from ignored senders or meeting invites.")

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
