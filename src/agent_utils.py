import datetime
import json
import os
from typing import Optional

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

CONFIG_DIR = os.path.expanduser(os.getenv('GOOGLE_CONFIG_DIR', '~/.config/productivity-agent'))

def get_credentials(token_filename: str, scopes: list) -> Credentials:
    """Standard OAuth2 credential flow for productivity agents.

    Prefers a local authorized_user credentials.json when present.
    Falls back to the per-script token file + OAuth browser flow.

    Args:
        token_filename: Token filename only (e.g. 'google-chat-token.json').
        scopes: List of OAuth2 scope strings.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    token_path = os.path.join(CONFIG_DIR, token_filename)
    creds_path = os.path.join(CONFIG_DIR, 'credentials.json')

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
            creds = flow.run_local_server(port=0)
        with os.fdopen(os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as token:
            token.write(creds.to_json())
    return creds


SAST_TZ = datetime.timezone(datetime.timedelta(hours=2), name="SAST")

WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def get_date_range(date_str: Optional[str] = None) -> Optional[tuple]:
    """Return (start_of_target_day, end_of_target_day) in SAST for the requested date.

    Args:
        date_str: None → previous weekday (same as get_yesterday_range),
                  "today" → today's date,
                  "DD/MM/YYYY" → the specified date.

    When a specific date or "today" is supplied, weekends are still processed
    (the caller explicitly chose the date).  In the default (None) mode,
    weekends are skipped as before.
    """
    if date_str is None:
        return get_yesterday_range()

    if date_str.lower() == 'today':
        target_date = datetime.datetime.now(SAST_TZ).date()
    else:
        try:
            target_date = datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError:
            print(f"Invalid date format '{date_str}'. Expected DD/MM/YYYY, or 'today'.")
            return None

    start = datetime.datetime(target_date.year, target_date.month, target_date.day,
                              0, 0, 0, tzinfo=SAST_TZ)
    end   = datetime.datetime(target_date.year, target_date.month, target_date.day,
                              23, 59, 59, 999999, tzinfo=SAST_TZ)
    print(f"Processing data for {WEEKDAY_NAMES[target_date.weekday()]} {target_date} (SAST).")
    return start, end


def get_yesterday_range() -> Optional[tuple]:
    """Return (start_of_target_day, end_of_target_day) in SAST for the previous weekday.

    If today is Monday, it looks back 3 days to the previous Friday.
    Otherwise, it looks back 1 day.
    Returns None if the target day was a Saturday or Sunday so callers can exit cleanly.
    """
    today = datetime.datetime.now(SAST_TZ).date()
    
    # If today is Monday (0), look back to Friday (today - 3)
    if today.weekday() == 0:
        target_date = today - datetime.timedelta(days=3)
    else:
        target_date = today - datetime.timedelta(days=1)

    # weekday(): Monday=0, Friday=4, Saturday=5, Sunday=6
    if target_date.weekday() >= 5:
        print(f"Target date was {WEEKDAY_NAMES[target_date.weekday()]} ({target_date}). Skipping — weekends are not processed.")
        return None

    start = datetime.datetime(target_date.year, target_date.month, target_date.day,
                              0, 0, 0, tzinfo=SAST_TZ)
    end   = datetime.datetime(target_date.year, target_date.month, target_date.day,
                              23, 59, 59, 999999, tzinfo=SAST_TZ)
    print(f"Processing data for {WEEKDAY_NAMES[target_date.weekday()]} {target_date} (SAST).")
    return start, end


def load_config() -> dict:
    """Load settings.json from the project root. Returns {} if not found."""
    config_path = os.path.join(_PROJECT_ROOT, 'settings.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}
