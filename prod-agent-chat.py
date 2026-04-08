import datetime
import os.path
import json
import dateutil.parser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/chat.spaces.readonly',
    'https://www.googleapis.com/auth/chat.messages.readonly',
    'https://www.googleapis.com/auth/chat.memberships.readonly',
    'https://www.googleapis.com/auth/userinfo.profile'
]

def main():
    """Shows basic usage of the Google Chat API.
    Lists messages from the last 24 hours in all accessible spaces.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    config_dir = os.path.expanduser('~/.config/productivity-agent')
    os.makedirs(config_dir, exist_ok=True)
    token_path = os.path.join(config_dir, 'google-chat-token.json')
    creds_path = os.path.join(config_dir, 'credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('chat', 'v1', credentials=creds)
        
        # Load configuration files
        ignored_spaces = []
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                config_data = json.load(f)
                ignored_spaces = config_data.get('ignored_spaces', [])
                
        user_mapping = {}
        if os.path.exists('user_mapping.json'):
            with open('user_mapping.json', 'r') as f:
                user_mapping = json.load(f)
                
        space_mapping = {}
        if os.path.exists('space_mapping.json'):
            with open('space_mapping.json', 'r') as f:
                space_mapping = json.load(f)

        # Calculate the past 24 hours date range (SAST)
        sast_tz = datetime.timezone(datetime.timedelta(hours=2), name="SAST")
        now = datetime.datetime.now(sast_tz)
        twenty_four_hours_ago = now - datetime.timedelta(days=1)

        print(f"Looking for messages from the last 24 hours (since {twenty_four_hours_ago.isoformat()})")

        # Call the Chat API to list spaces the user is a member of
        # Note: Depending on the number of spaces, you may need to handle pagination (pageToken).
        results = service.spaces().list().execute()
        spaces = results.get('spaces', [])

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
                if last_active_time < twenty_four_hours_ago:
                    # Skip fetching messages if the space hasn't had activity in the last 24 hours
                    continue
            
            if TEST_MODE:
                if spaces_checked >= 15: # check max 15 spaces to avoid hanging during testing
                    print("Reached maximum spaces check limit for testing.")
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
                # The createTime is a string like "2023-08-15T15:45:00.123Z"
                create_time_str = msg.get('createTime')
                if create_time_str:
                    create_time = dateutil.parser.isoparse(create_time_str)
                    if create_time >= twenty_four_hours_ago:
                        recent_messages.insert(0, msg)
                        # In TEST_MODE, limit how many we collect per space
                        if TEST_MODE and len(recent_messages) >= TEST_MESSAGES_LIMIT:
                            break
                    else:
                        # Since we are iterating descending by createTime, as soon as we hit an old message, we can stop
                        break

            if recent_messages:
                if TEST_MODE:
                    spaces_processed_with_messages += 1
                    
                
                print(f"\n======== Space: {display_name} ({space_type}) ========")
                output_transcripts.append(f"## Space: {display_name} ({space_type})\n")
                
                for msg in recent_messages:
                    sender_info = msg.get('sender', {})
                    sender_name_id = sender_info.get('name')
                    sender = user_mapping.get(sender_name_id, sender_info.get('displayName', str(sender_info)))
                    text = msg.get('text', '')
                    time = msg.get('createTime')
                    
                    create_dt = dateutil.parser.isoparse(time)
                    formatted_date = create_dt.strftime("%d-%m-%Y")
                    msg_output = f"[{formatted_date}] **{sender}**: {text}"
                    print(f"[{formatted_date}] {sender}: {text}")
                    output_transcripts.append(msg_output)
                    
                output_transcripts.append("---\n")
                    
                if TEST_MODE and spaces_processed_with_messages >= TEST_SPACES_LIMIT:
                    break

        if output_transcripts:
            file_date = now.strftime("%d-%m-%Y")
            output_dir = "Google Chat"
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.join(output_dir, f"google-chats-{file_date}.md")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Google Chats Transcript - {file_date}\n\n")
                f.write("\n".join(output_transcripts))
            print(f"\nTranscripts successfully exported to {filename}")
        else:
            print("\nNo messages found to export.")

    except Exception as error:
        # TODO(developer) - Handle errors from chat API.
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
