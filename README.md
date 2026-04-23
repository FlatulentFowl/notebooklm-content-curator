# Productivity Agent

A suite of scripts that connect your Google Workspace activity to Google Tasks, pulling from Meet Gemini notes and converting task note checkboxes into subtasks. On Mondays, date-based scripts automatically look back to the previous Friday.

| Script | What it does |
|---|---|
| `prod-agent-meet.py` | Extracts assigned Next Steps from Google Meet Gemini notes and creates Google Tasks |
| `prod-agent-tasks.py` | Converts `[ ]` checkbox items in task notes into subtasks |
| `prod-agent-notebooklm.py` | Uploads tagged markdown files to a Google Drive folder for NotebookLM |

---

## Setup

### 1. Install dependencies

```bash
pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dateutil python-dotenv
```

### 2. Configure environment

Copy `.env` and fill in your values:

```
GOOGLE_CONFIG_DIR=~/.config/productivity-agent
GOOGLE_CREDENTIALS_FILE=credentials.json
NOTEBOOKLM_DRIVE_FOLDER_ID=<your-drive-folder-id>
NOTEBOOKLM_SOURCE_DIRS=~/path/to/notes:~/other/notes
```

| Variable | Description |
|---|---|
| `GOOGLE_CONFIG_DIR` | Directory where OAuth token files are stored |
| `GOOGLE_CREDENTIALS_FILE` | Local filename for the OAuth client credentials |
| `NOTEBOOKLM_DRIVE_FOLDER_ID` | Google Drive folder ID to upload files into |
| `NOTEBOOKLM_SOURCE_DIRS` | Colon-separated list of local directories to scan for tagged files |

### 3. Set up Google OAuth (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in
2. Create a project (any name)
3. Enable the APIs you need (see per-script requirements below)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
5. Choose **Desktop app**, click Create, then **Download JSON**
6. Save the downloaded file to `$GOOGLE_CONFIG_DIR/credentials.json`
7. Run `setup-auth.py` to complete the OAuth flow and generate a local `credentials.json`:

```bash
python3 setup-auth.py
```

The first time you run each script a browser window opens asking you to grant access. Tokens are cached in `$GOOGLE_CONFIG_DIR` and won't prompt again until they expire.

> **Security:** Token files and `credentials.json` are excluded via `.gitignore` and should never be committed. `.env` is also excluded.

---

## Configuration

Create a `config.json` file in the project directory:

```json
{
  "primary_user": ["Your Name"],
  "ignored_meetings": ["All Hands Meeting"]
}
```

| Key | Used by | Description |
|---|---|---|
| `primary_user` | `prod-agent-meet.py` | Names to match when extracting assigned action items from Next Steps |
| `ignored_meetings` | `prod-agent-meet.py` | Calendar event titles or event IDs to skip |

> **Note:** `config.json` is excluded from git via `.gitignore`.

---

## Scripts

### `prod-agent-meet.py` — Meet → Tasks

Fetches calendar events from the previous weekday and reads any Google Docs attached as Gemini notes. Finds the Next Steps section (or tab), extracts bullet points assigned to `primary_user`, and creates a Google Task with subtasks for each meeting.

**APIs required:** Google Calendar API, Google Drive API (`drive.meet.readonly`), Google Docs API, Google Tasks API  
**Token:** `$GOOGLE_CONFIG_DIR/google-meet-token.json`

```bash
python3 prod-agent-meet.py

# Process a specific date
python3 prod-agent-meet.py -date 21/04/2025

# Process today
python3 prod-agent-meet.py -date today
```

---

### `prod-agent-tasks.py` — Checkbox Notes → Subtasks

Scans all open Google Tasks for notes containing `[ ]` checkbox lines and converts each one into a subtask, then clears the notes field.

**APIs required:** Google Tasks API  
**Token:** `$GOOGLE_CONFIG_DIR/google-tasks-token.json`

```bash
python3 prod-agent-tasks.py
```

---

### `prod-agent-notebooklm.py` — NotebookLM Sync

Scans the directories listed in `NOTEBOOKLM_SOURCE_DIRS` for markdown files tagged with `notebooklm-source` and uploads each one to the Google Drive folder set by `NOTEBOOKLM_DRIVE_FOLDER_ID`, converting them to Google Docs. Files that already exist in the folder are skipped.

**APIs required:** Google Drive API  
**Token:** `$GOOGLE_CONFIG_DIR/google-notebooklm-token.json`

```bash
python3 prod-agent-notebooklm.py
```

Tag any `.md` file for syncing by adding a YAML frontmatter block:

```yaml
---
tags:
  - notebooklm-source
---
```

---

## Changelog

### v0.1.5
- Moved authentication paths and user-specific config to `.env` (loaded via `python-dotenv`)
- Removed `prod-agent-chat.py` and `prod-agent-mail.py`
- `prod-agent-meet.py` now creates Google Tasks from Next Steps instead of exporting markdown
- Added `prod-agent-tasks.py` — converts task note checkboxes to subtasks
- Cleaned up `config.json` to remove keys for removed scripts

### v0.1.4
- On Mondays, scripts now process data from the previous Friday instead of Sunday
- Standardised date range logic in `agent_utils.py` to target the "previous weekday"

### v0.1.3
- Added `prod-agent-meet.py` — exports Google Meet Gemini notes and transcripts to markdown
- Added `config.json` support for filtering ignored meetings

### v0.1.2
- Increased file size limit from 1 MB to 5 MB
- `--tag` is now a required argument
- `--file` is now a required argument

### v0.1.1
- Added `--tag`, `--file`, `--dir`, `--dry-run`, `--version` switches

### v0.1.0
- Initial release
