# **Productivity Agent**

A suite of scripts that connect your Google Workspace activity to Google Tasks, pulling from Meet Gemini notes and converting task note checkboxes into subtasks. On Mondays, date-based scripts automatically look back to the previous Friday.

| Script | What it does |
| :---- | :---- |
| prod_agent.py | Main wrapper to run individual agents or execute them all in sequence |
| prod_agent_meet.py | Extracts assigned Next Steps from Google Meet Gemini notes and creates Google Tasks |
| prod_agent_tasks.py | Converts \[ \] checkbox items in task notes into subtasks |
| prod_agent_notebooklm.py | Uploads tagged markdown files to a Google Drive folder for NotebookLM |
| prod_agent_podcast.py | Fetches transcripts from YouTube playlists or videos and saves them as markdown |

## **Setup**

### **1\. Install dependencies**

Since the project includes a pyproject.toml, you can install everything directly:

`pip3 install.`

Alternatively, install the packages manually:

`pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dateutil python-dotenv yt-dlp youtube-transcript-api`

### **2\. Configure environment**

Copy .env.example to .env and fill in your values:
```
GOOGLE\_CONFIG\_DIR=\~/.config/productivity-agent  
GOOGLE\_CREDENTIALS\_FILE=credentials.json  
NOTEBOOKLM\_DRIVE\_FOLDER\_ID=\<your-drive-folder-id\>  
NOTEBOOKLM\_SOURCE\_DIRS=\~/path/to/notes:\~/other/notes
```

| Variable | Description |
| :---- | :---- |
| GOOGLE\_CONFIG\_DIR | Directory where OAuth token files are stored |
| GOOGLE\_CREDENTIALS\_FILE | Local filename for the OAuth client credentials |
| NOTEBOOKLM\_DRIVE\_FOLDER\_ID | Google Drive folder ID to upload files into |
| NOTEBOOKLM\_SOURCE\_DIRS | Colon-separated list of local directories to scan for tagged files |
| PODCAST\_OUTPUT\_DIR | Local directory where podcast transcript markdown files are saved |

### **3\. Set up Google OAuth (one-time)**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in  
2. Create a project (any name)  
3. Enable the APIs you need (see per-script requirements below)  
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**  
5. Choose **Desktop app**, click Create, then **Download JSON**  
6. Save the downloaded file to `$GOOGLE\_CONFIG\_DIR/credentials.json` 
7. Run setup_auth.py to complete the OAuth flow and generate a local credentials.json:

`python3 src/setup_auth.py`

The first time you run each script, a browser window opens asking you to grant access. Tokens are cached in `$GOOGLE\_CONFIG\_DIR` and won't prompt you again until they expire.

**Security:** Token files and credentials.json are excluded via .gitignore and should never be committed. .env is also excluded.

## **Configuration**

Create a settings.json file in the project directory to configure script behavior:

```JSON
{  
  "primary\_user": \["Your Name"\],  
  "ignored\_meetings": \["All Hands Meeting"\]  
}
```

| Key | Used by | Description |
| :---- | :---- | :---- |
| primary\_user | prod_agent_meet.py | Names to match when extracting assigned action items from Next Steps |
| ignored\_meetings | prod_agent_meet.py | Calendar event titles or event IDs to skip |

## **Scripts**

You can run scripts individually or use the main wrapper.

### **prod_agent.py — Main Wrapper**

Run all agents sequentially or trigger them one by one.

\# Run all agents (meet → tasks → notebooklm → podcast)  
`python3 src/prod_agent.py all`

\# Dry run (skips podcast)  
python3 src/prod_agent.py all \--dry-run

### **prod_agent_meet.py — Meet → Tasks**

Fetches calendar events from the previous weekday and reads attached Google Docs for Gemini notes. It grabs bullet points assigned to `primary\_user` under "Next Steps" and creates a Google Task.

**APIs required:** Google Calendar API, Google Drive API, Google Docs API, Google Tasks API

**Token:** `$GOOGLE\_CONFIG\_DIR/google-meet-token.json`

`python3 src/prod_agent.py meet`

\# Process a specific date  
`python3 src/prod_agent.py meet \--date 21/04/2025`

\# Process today  
`python3 src/prod_agent.py meet \--date today`

### **prod_agent_tasks.py — Checkbox Notes → Subtasks**

Scans open Google Tasks for notes containing \[ \] checkboxes. It turns each checkbox into a subtask, then clears the notes field.

**APIs required:** Google Tasks API

**Token:** `$GOOGLE\_CONFIG\_DIR/google-tasks-token.json`

`python3 src/prod_agent.py tasks`

### **prod_agent_notebooklm.py — NotebookLM Sync**

Scans the directories listed in NOTEBOOKLM\_SOURCE\_DIRS for markdown files tagged with notebooklm-source. It uploads them to your target Drive folder as Google Docs, skipping files that already exist.

**APIs required:** Google Drive API

**Token:** `$GOOGLE\_CONFIG\_DIR/google-notebooklm-token.json`

`python3 src/prod_agent.py notebooklm`

Tag any .md file for syncing by adding a YAML frontmatter block:

\---  
tags:  
  \- notebooklm-source  
\---

### **prod_agent_podcast.py — YouTube → Transcripts**

Downloads auto-generated transcripts from a YouTube video or playlist and saves them locally as markdown files.

`python3 src/prod_agent.py podcast \--playlist \<URL\> \--out \~/path/to/save`

## **Changelog**

### **v0.1.5**

* Moved authentication paths and user-specific config to .env  
* Removed legacy chat and mail agents  
* prod_agent_meet.py now creates Google Tasks directly from Next Steps  
* Added prod_agent_tasks.py — converts task note checkboxes to subtasks  
* Added prod_agent_podcast.py for YouTube transcript harvesting  
* Switched configuration file from config.json to settings.json  
* Added main prod_agent.py wrapper script

### **v0.1.4**

* On Mondays, scripts now process data from the previous Friday  
* Standardized date range logic in agent\_utils.py

### **v0.1.3**

* Added prod_agent_meet.py support for Gemini notes  
* Added configuration support for filtering ignored meetings
