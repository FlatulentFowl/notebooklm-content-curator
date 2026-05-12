import argparse
import re

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from agent_utils import get_credentials

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/tasks']

CHECKBOX_PATTERN = re.compile(r'^\s*\[ ?\]\s*(?:-\s*)?(.+)', re.MULTILINE)


def get_all_task_lists(service):
    lists = []
    page_token = None
    while True:
        result = service.tasklists().list(maxResults=100, pageToken=page_token).execute()
        lists.extend(result.get('items', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    return lists


def get_open_tasks(service, tasklist_id):
    tasks = []
    page_token = None
    while True:
        result = service.tasks().list(
            tasklist=tasklist_id,
            showCompleted=False,
            showHidden=False,
            maxResults=100,
            pageToken=page_token
        ).execute()
        tasks.extend(result.get('items', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    return tasks


def create_subtask(service, tasklist_id, parent_id, title):
    body = {'title': title, 'status': 'needsAction'}
    result = service.tasks().insert(
        tasklist=tasklist_id,
        parent=parent_id,
        body=body
    ).execute()
    return result


def clear_task_notes(service, tasklist_id, task):
    service.tasks().patch(
        tasklist=tasklist_id,
        task=task['id'],
        body={'notes': ''}
    ).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without creating subtasks or clearing notes')
    args = parser.parse_args()

    if args.dry_run:
        print('Dry run mode — no changes will be made.\n')

    creds = get_credentials('google-tasks-token.json', SCOPES)

    try:
        service = build('tasks', 'v1', credentials=creds)

        task_lists = get_all_task_lists(service)
        if not task_lists:
            print('No task lists found.')
            return

        total_subtasks_created = 0

        for task_list in task_lists:
            list_id = task_list['id']
            list_title = task_list.get('title', 'Untitled')
            tasks = get_open_tasks(service, list_id)

            if not tasks:
                continue

            for task in tasks:
                # Skip tasks that are themselves subtasks (have a parent)
                if task.get('parent'):
                    continue

                notes = task.get('notes', '')
                if not notes:
                    continue

                matches = CHECKBOX_PATTERN.findall(notes)
                if not matches:
                    continue

                task_id = task['id']
                task_title = task.get('title', 'Untitled Task')
                print(f'\n[{list_title}] "{task_title}"')
                print(f'  Found {len(matches)} checkbox line(s) to convert to subtasks:')

                for subtask_title in matches:
                    subtask_title = subtask_title.strip()
                    if args.dry_run:
                        print(f'  + Would create subtask: "{subtask_title}"')
                    else:
                        created = create_subtask(service, list_id, task_id, subtask_title)
                        print(f'  + Created subtask ID: "{created.get("id")}"')
                    total_subtasks_created += 1

                if not args.dry_run:
                    clear_task_notes(service, list_id, task)
                    print(f'  Cleared notes for task ID "{task_id}"')

        verb = 'Would create' if args.dry_run else 'Created'
        if total_subtasks_created:
            print(f'\nDone. {verb} {total_subtasks_created} subtask(s) total.')
        else:
            print('\nNo checkbox lines found in any open task notes.')

    except HttpError as error:
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
