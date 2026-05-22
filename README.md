# **Productivity Agent**

A suite of scripts that connect your Google Workspace activity to Google Tasks, pulling from Meet Gemini notes and converting task note checkboxes into subtasks. On Mondays, date-based scripts automatically look back to the previous Friday.

| Script | What it does |
| :---- | :---- |
| src/prod_agent.py | Main wrapper to run individual agents or execute them all in sequence |
| src/tools/tool_meet.py | Extracts assigned Next Steps from Google Meet Gemini notes and creates Google Tasks |
| src/tools/tool_tasks.py | Converts [ ] checkbox items in task notes into subtasks |
| src/tools/tool_notebooklm.py | Uploads tagged markdown files to a Google Drive folder for NotebookLM |
| src/tools/tool_podcast.py | Fetches transcripts from YouTube playlists or videos and saves them as markdown |

## **Setup**

### **1. Install dependencies**

This project uses [uv](https://docs.astral.sh/uv/). Install dependencies with:

`uv sync`

### **2. Configure environment**

Copy .env.example to .env and fill in your values:

```
GOOGLE_CONFIG_DIR=~/.config/productivity-agent
GOOGLE_CREDENTIALS_FILE=credentials.json
NOTEBOOKLM_DRIVE_FOLDER_ID=<your-drive-folder-id>
NOTEBOOKLM_SOURCE_DIRS=~/path/to/notes:~/other/notes
```

| Variable | Description |
| :---- | :---- |
| GOOGLE_CONFIG_DIR | Directory where OAuth token files are stored |
| GOOGLE_CREDENTIALS_FILE | Local filename for the OAuth client credentials |
| NOTEBOOKLM_DRIVE_FOLDER_ID | Google Drive folder ID to upload files into |
| NOTEBOOKLM_SOURCE_DIRS | Colon-separated list of local directories to scan for tagged files |
| PODCAST_OUTPUT_DIR | Local directory where podcast transcript markdown files are saved |

### **3. Set up Google OAuth (one-time)**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in
2. Create a project (any name)
3. Enable the APIs you need (see per-script requirements below)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
5. Choose **Desktop app**, click Create, then **Download JSON**
6. Save the downloaded file to `$GOOGLE_CONFIG_DIR/credentials.json`
7. Run setup_auth.py to complete the OAuth flow and generate a local credentials.json:

`uv run src/setup_auth.py`

The first time you run each script, a browser window opens asking you to grant access. Tokens are cached in `$GOOGLE_CONFIG_DIR` and won't prompt you again until they expire.

**Security:** Token files and credentials.json are excluded via .gitignore and should never be committed. .env is also excluded.

## **Configuration**

Create a settings.json file in the project directory to configure script behavior:

```json
{
  "primary_user": ["Your Name"],
  "ignored_meetings": ["All Hands Meeting"]
}
```

| Key | Used by | Description |
| :---- | :---- | :---- |
| primary_user | tool_meet.py | Names to match when extracting assigned action items from Next Steps |
| ignored_meetings | tool_meet.py | Calendar event titles or event IDs to skip |

## **Scripts**

You can run scripts individually or use the main wrapper.

### **prod_agent.py — Main Wrapper**

Run all agents sequentially or trigger them one by one.

```
# Run all agents (meet → tasks → notebooklm → podcast)
uv run src/prod_agent.py all

# Dry run (skips podcast)
uv run src/prod_agent.py all --dry-run
```

### **tool_meet.py — Meet → Tasks**

Fetches calendar events from the previous weekday and reads attached Google Docs for Gemini notes. It grabs bullet points assigned to `primary_user` under "Next Steps" and creates a Google Task.

**APIs required:** Google Calendar API, Google Drive API, Google Docs API, Google Tasks API

**Token:** `$GOOGLE_CONFIG_DIR/google-meet-token.json`

```
uv run src/prod_agent.py meet

# Process a specific date
uv run src/prod_agent.py meet --date 21/04/2025

# Process today
uv run src/prod_agent.py meet --date today
```

### **tool_tasks.py — Checkbox Notes → Subtasks**

Scans open Google Tasks for notes containing [ ] checkboxes. It turns each checkbox into a subtask, then clears the notes field.

**APIs required:** Google Tasks API

**Token:** `$GOOGLE_CONFIG_DIR/google-tasks-token.json`

`uv run src/prod_agent.py tasks`

### **tool_notebooklm.py — NotebookLM Sync**

Scans the directories listed in NOTEBOOKLM_SOURCE_DIRS for markdown files tagged with `notebooklm-source`. It uploads them to your target Drive folder as Google Docs, skipping files that already exist.

**APIs required:** Google Drive API

**Token:** `$GOOGLE_CONFIG_DIR/google-notebooklm-token.json`

`uv run src/prod_agent.py notebooklm`

Tag any .md file for syncing by adding a YAML frontmatter block:

```yaml
---
tags:
  - notebooklm-source
---
```

### **tool_podcast.py — YouTube → Transcripts**

Downloads auto-generated transcripts from a YouTube video or playlist and saves them locally as markdown files.

`uv run src/prod_agent.py podcast --playlist <URL> --out ~/path/to/save`

## **Changelog**

### **v0.2.0**

* Replaced `yt-dlp` with YouTube Data API in `tool_podcast.py` for cookie authentication support and improved metadata handling

### **v0.1.7**

* Renamed individual agent scripts to `tool_*.py` naming convention
* Moved tool scripts into `src/tools/` package
* Switched install and run instructions from `pip3`/`python3` to `uv`

### **v0.1.5**

* Moved authentication paths and user-specific config to .env
* Removed legacy chat and mail agents
* tool_meet.py now creates Google Tasks directly from Next Steps
* Added tool_tasks.py — converts task note checkboxes to subtasks
* Added tool_podcast.py for YouTube transcript harvesting
* Switched configuration file from config.json to settings.json
* Added main prod_agent.py wrapper script

### **v0.1.4**

* On Mondays, scripts now process data from the previous Friday
* Standardized date range logic in agent_utils.py

### **v0.1.3**

* Added tool_meet.py support for Gemini notes
* Added configuration support for filtering ignored meetings
