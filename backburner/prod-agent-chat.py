import argparse
import os
import json
import dateutil.parser

from googleapiclient.discovery import build
from agent_utils import get_credentials, get_date_range, load_config

# If modifying these scopes, delete the token file.
SCOPES = [
    'https://www.googleapis.com/auth/chat.spaces.readonly',
    'https://www.googleapis.com/auth/chat.messages.readonly',
    'https://www.googleapis.com/auth/chat.memberships.readonly',
    'https://www.googleapis.com/auth/userinfo.profile'
]

OUTPUT_DIR = "raw/google-chat"

def main():
    """Lists messages from the previous weekday in all accessible spaces and exports as markdown."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-date', dest='date', default=None,
                        help="Date to search: DD/MM/YYYY, 'today', or omit for previous weekday")
    args = parser.parse_args()

    creds = get_credentials('google-chat-token.json', SCOPES)

    try:
        service = build('chat', 'v1', credentials=creds)

        # Load configuration files
        config_data = load_config()
        ignored_spaces = config_data.get('ignored_spaces', [])

        user_mapping = {}
        if os.path.exists('user_mapping.json'):
            with open('user_mapping.json', 'r') as f:
                user_mapping = json.load(f)

        space_mapping = {}
        if os.path.exists('space_mapping.json'):
            with open('space_mapping.json', 'r') as f:
                space_mapping = json.load(f)

        # Calculate the target date range (SAST)
        result = get_date_range(args.date)
        if result is None:
            return
        start, end = result
        file_date = start.strftime("%d-%m-%Y")

        print(f"Looking for messages between {start.isoformat()} and {end.isoformat()}")

        # Fetch all spaces with pagination
        spaces = []
        page_token = None
        while True:
            results = service.spaces().list(pageSize=100, pageToken=page_token).execute()
            spaces.extend(results.get('spaces', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        if not spaces:
            print('No spaces found.')
            return

        print(f'Found {len(spaces)} spaces. Fetching recent messages...')

        # TEST MODE CONFIGURATION
        TEST_MODE = False
        TEST_SPACES_LIMIT = 5
        TEST_MESSAGES_LIMIT = 3
        
        spaces_processed_with_messages = 0
        spaces_checked = 0
        output_transcripts = []

        for space in spaces:
            space_name = space.get('name')
            raw_display_name = space.get('displayName', f"Unnamed Space ({space_name})")
            display_name = space_mapping.get(space_name, raw_display_name)
            space_type = space.get('type', 'UNKNOWN')
            
            if display_name in ignored_spaces or space_name in ignored_spaces:
                continue
            
            last_active_time_str = space.get('lastActiveTime')
            if last_active_time_str:
                last_active_time = dateutil.parser.isoparse(last_active_time_str)
                if last_active_time < start:
                    continue
            
            if TEST_MODE:
                if spaces_checked >= 15:
                    print("  Reached maximum spaces check limit for testing.")
                    break
                spaces_checked += 1
                
            print(f"Checking space: {display_name}...")

            messages_results = service.spaces().messages().list(
                parent=space_name,
                orderBy="createTime desc",
                pageSize=1000
            ).execute()
            
            messages = messages_results.get('messages', [])
            recent_messages = []

            for msg in messages:
                create_time_str = msg.get('createTime')
                if create_time_str:
                    create_time = dateutil.parser.isoparse(create_time_str)
                    if start <= create_time <= end:
                        recent_messages.insert(0, msg)
                        if TEST_MODE and len(recent_messages) >= TEST_MESSAGES_LIMIT:
                            break
                    elif create_time < start:
                        break

            if recent_messages:
                if TEST_MODE:
                    spaces_processed_with_messages += 1
                
                print(f"  Found {len(recent_messages)} recent message(s).")
                output_transcripts.append(f"## Space: {display_name} ({space_type})\n")
                
                for msg in recent_messages:
                    sender_info = msg.get('sender', {})
                    sender_name_id = sender_info.get('name')
                    sender = user_mapping.get(sender_name_id, sender_info.get('displayName', "Unknown User"))
                    text = msg.get('text', '')
                    time = msg.get('createTime')
                    
                    create_dt = dateutil.parser.isoparse(time)
                    msg_date = create_dt.strftime("%d-%m-%Y %H:%M")
                    
                    msg_output = f"[{msg_date}] **{sender}**: {text}"
                    output_transcripts.append(msg_output)
                    
                output_transcripts.append("\n---\n")
                    
                if TEST_MODE and spaces_processed_with_messages >= TEST_SPACES_LIMIT:
                    break

        if output_transcripts:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            filename = os.path.join(OUTPUT_DIR, f"google-chats-{file_date}.md")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Google Chats Transcript - {file_date}\n\n")
                f.write("\n".join(output_transcripts))
            print(f"\nTranscripts successfully exported → {filename}")
        else:
            print("\nNo messages found to export.")

    except Exception as error:
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
