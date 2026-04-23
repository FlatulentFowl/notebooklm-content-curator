"""
One-time OAuth setup. Run this to (re)build credentials.json with all scopes
needed across every productivity agent. Opens a browser for consent, then
saves the authorized token to credentials.json in this directory.
"""

import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    # Tasks
    'https://www.googleapis.com/auth/tasks',
    # Calendar + Meet notes
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/drive.meet.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    # Drive (NotebookLM sync)
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]

_config_dir = os.path.expanduser(os.getenv('GOOGLE_CONFIG_DIR', '~/.config/productivity-agent'))
CLIENT_SECRETS = os.path.join(_config_dir, 'credentials.json')
OUTPUT = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')

if not os.path.exists(CLIENT_SECRETS):
    raise FileNotFoundError(f'Client secrets not found at {CLIENT_SECRETS}')

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
creds = flow.run_local_server(port=0)

import json
creds_data = json.loads(creds.to_json())
creds_data['type'] = 'authorized_user'
with open(OUTPUT, 'w') as f:
    json.dump(creds_data, f, indent=2)

print(f'Saved credentials to {OUTPUT}')
