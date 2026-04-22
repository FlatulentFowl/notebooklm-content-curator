import argparse
import datetime

from googleapiclient.discovery import build
from agent_utils import get_credentials, get_date_range, load_config

# If modifying these scopes, delete the token file.
SCOPES = [
    'https://www.googleapis.com/auth/drive.meet.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/tasks',
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


def extract_action_items(markdown_text, assignees):
    """Return clean task titles for bullet lines assigned to one of the given assignees."""
    items = []
    for line in markdown_text.splitlines():
        content = line.lstrip().removeprefix('- ')
        for assignee in assignees:
            prefix = f'[{assignee}] '
            if content.startswith(prefix):
                items.append(content[len(prefix):].strip())
                break
    return items


def find_next_steps_tab(tabs):
    """Return the first tab whose title contains 'next step' (case-insensitive)."""
    for tab in tabs:
        title = tab.get('tabProperties', {}).get('title', '')
        if 'next step' in title.lower():
            return tab
    return None


def extract_next_steps_from_body(body_content):
    """Extract content under the first heading containing 'next step'."""
    in_section = False
    section_heading_level = None
    section_elements = []

    for element in body_content:
        paragraph = element.get('paragraph')
        if not paragraph:
            continue

        style = paragraph.get('paragraphStyle', {}).get('namedStyleType', 'NORMAL_TEXT')
        text = ''.join(
            pe.get('textRun', {}).get('content', '') for pe in paragraph.get('elements', [])
        ).rstrip('\n')

        if not in_section:
            if style in HEADING_MAP and 'next step' in text.lower():
                in_section = True
                section_heading_level = int(style.split('_')[1])
        else:
            if style in HEADING_MAP and int(style.split('_')[1]) <= section_heading_level:
                break
            section_elements.append(element)

    return doc_content_to_markdown(section_elements) if section_elements else None


def get_default_tasklist(tasks_service):
    """Return the ID of the first (default) task list."""
    result = tasks_service.tasklists().list(maxResults=1).execute()
    items = result.get('items', [])
    if not items:
        raise RuntimeError('No task lists found in Google Tasks.')
    return items[0]['id']


def create_task_with_subtasks(tasks_service, tasklist_id, title, subtask_titles):
    """Create a parent task and add subtasks under it."""
    parent = tasks_service.tasks().insert(
        tasklist=tasklist_id,
        body={'title': title, 'status': 'needsAction'}
    ).execute()
    for subtask_title in subtask_titles:
        tasks_service.tasks().insert(
            tasklist=tasklist_id,
            parent=parent['id'],
            body={'title': subtask_title, 'status': 'needsAction'}
        ).execute()
    return parent


def main():
    """Finds Google Meet Gemini next steps and creates Google Tasks from them."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-date', dest='date', default=None,
                        help="Date to search: DD/MM/YYYY, 'today', or omit for previous weekday")
    args = parser.parse_args()

    creds = get_credentials('google-meet-token.json', SCOPES)

    try:
        calendar_service = build('calendar', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)
        tasks_service = build('tasks', 'v1', credentials=creds)

        # Load configuration
        config_data = load_config()
        ignored_meetings = config_data.get('ignored_meetings', [])
        primary_user = config_data.get('primary_user', [])

        tasklist_id = get_default_tasklist(tasks_service)

        # Calculate the target date range (SAST)
        result = get_date_range(args.date)
        if result is None:
            return
        start, end = result

        time_min = start.astimezone(datetime.timezone.utc).isoformat()
        time_max = end.astimezone(datetime.timezone.utc).isoformat()

        print(f"Looking for calendar events with Meet notes between {start.isoformat()} and {end.isoformat()}")

        # Fetch calendar events with pagination
        events = []
        page_token = None
        while True:
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token
            ).execute()
            events.extend(events_result.get('items', []))
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break

        if not events:
            print('No calendar events found for the target date.')
            return

        print(f'Found {len(events)} calendar event(s). Checking for attached Gemini notes...')

        tasks_created = 0

        for event in events:
            event_title = event.get('summary', 'Untitled Meeting')
            event_id = event.get('id', '')
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))

            if event_title in ignored_meetings or event_id in ignored_meetings:
                continue

            # Gemini notes are linked as Google Doc attachments on the calendar event
            attachments = event.get('attachments', [])
            doc_attachments = [
                a for a in attachments
                if a.get('mimeType') == 'application/vnd.google-apps.document'
            ]

            if not doc_attachments:
                continue

            try:
                start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted_date = start_dt.strftime("%d-%m-%Y")
            except Exception:
                formatted_date = start.strftime("%d-%m-%Y")

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
                next_steps_md = None

                if not tabs:
                    body_content = doc.get('body', {}).get('content', [])
                    next_steps_md = extract_next_steps_from_body(body_content)
                else:
                    next_steps_tab = find_next_steps_tab(tabs)
                    if next_steps_tab:
                        tab_body = next_steps_tab.get('documentTab', {}).get('body', {}).get('content', [])
                        next_steps_md = doc_content_to_markdown(tab_body)
                    elif tabs:
                        tab_body = tabs[0].get('documentTab', {}).get('body', {}).get('content', [])
                        next_steps_md = extract_next_steps_from_body(tab_body)

                action_items = extract_action_items(next_steps_md, primary_user) if next_steps_md and primary_user else []

                if action_items:
                    task_title = f"{event_title} ({formatted_date})"
                    create_task_with_subtasks(tasks_service, tasklist_id, task_title, action_items)
                    print(f"  Created task '{task_title}' with {len(action_items)} subtask(s).")
                    tasks_created += 1
                else:
                    print(f"    No Next Steps content found — skipping.")

        if tasks_created:
            print(f"\n{tasks_created} task(s) created in Google Tasks.")
        else:
            print("\nNo Gemini notes found on any calendar events.")

    except Exception as error:
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
