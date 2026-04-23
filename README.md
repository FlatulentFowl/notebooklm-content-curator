# Productivity Agent

A suite of scripts that pull your Google Workspace activity from the previous weekday and export it as markdown files, ready for use as [NotebookLM](https://notebooklm.google.com) sources or any other purpose. On Mondays, the scripts automatically look back to the previous Friday.

| Script | What it does | Output folder |
|---|---|---|
| `prod-agent-meet.py` | Google Meet Gemini notes and transcripts | `Google Meet/` |
| `prod-agent-notebooklm.py` | Syncs tagged markdown files to a Google Doc for NotebookLM | — |

---

## Setup

### 1. Install dependencies

```bash
pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dateutil pyyaml
```

### 2. Set up Google OAuth (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account
2. Create a project (any name)
3. Enable the APIs you need (see per-script requirements below)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
5. Choose **Desktop app**, click Create, then **Download JSON**
6. Save the downloaded file to:

```
~/.config/productivity-agent/credentials.json
```

The first time you run each script a browser window opens asking you to sign in and grant access. Tokens are cached in `~/.config/productivity-agent/` and you won't be prompted again until they expire.

> **Security:** Tokens are stored as JSON with `0o600` permissions (owner-readable only). The `credentials.json` file and all token files should never be committed — they are excluded via `.gitignore`.

---

## Configuration

Create a `config.json` file in the project directory. All fields are optional.

```json
{
  "ignored_meetings": [
    "All Hands Meeting"
  ],
  "meet_notes_search_term": "Notes from"
}
```

| Key | Used by | Description |
|---|---|---|
| `ignored_meetings` | `prod-agent-meet.py` | Calendar event titles or event IDs to skip |
| `meet_notes_search_term` | `prod-agent-meet.py` | Override the Drive search term for Gemini notes (default: `"Notes from"`) |

> **Note:** `config.json` is excluded from git via `.gitignore` as it may contain identifying information.

---

## Scripts

### `prod-agent-meet.py` — Google Meet Gemini Notes

Fetches calendar events from the previous weekday and reads any Google Docs attached as Gemini notes. Gemini notes typically have two tabs — Notes and Transcript — each exported as a separate file. On Mondays, it processes events from the previous Friday.

**APIs required:** Google Calendar API, Google Drive API (`drive.meet.readonly`), Google Docs API  
**Token:** `~/.config/productivity-agent/google-meet-token.json`

**Output:** `Google Meet/`
- `Event Name - DD-MM-YYYY.md` — notes tab
- `Event Name - DD-MM-YYYY (Transcript).md` — transcript tab

Meetings with no Gemini notes attached, or where both tabs are empty, are skipped.

```bash
python3 prod-agent-meet.py
```

---

### `prod-agent-notebooklm.py` — NotebookLM Sync

Syncs tagged markdown files from any folder into a Google Doc, so they can be used as sources in NotebookLM. Each tagged file is written to its own tab. The script tracks sync state using a local registry file and only updates tabs whose content has changed.

**APIs required:** Google Docs API, Google Drive API  
**Token:** `~/.config/productivity-agent/google-drive-token.json`

```bash
# Preview what would change
python3 prod-agent-notebooklm.py --tag notebooklm-source --file "My NotebookLM Doc" --dry-run

# Sync
python3 prod-agent-notebooklm.py --tag notebooklm-source --file "My NotebookLM Doc"

# Sync a specific folder
python3 prod-agent-notebooklm.py --dir ~/notes --tag notebooklm-source --file "My NotebookLM Doc"
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

### v0.1.4
- On Mondays, scripts now process data from the previous Friday instead of Sunday
- Standardised date range logic in `agent_utils.py` to target the "previous weekday"
- Updated misleading print messages and documentation regarding the search window

### v0.1.3
- Added `prod-agent-meet.py` — exports Google Meet Gemini notes and transcripts to markdown
- Added `config.json` support for filtering ignored meetings
- Output files written to `Google Meet/`

### v0.1.2
- Increased file size limit from 1 MB to 5 MB
- `--tag` is now a required argument
- `--file` is now a required argument

### v0.1.1
- Added `--tag`, `--file`, `--dir`, `--dry-run`, `--version` switches

### v0.1.0
- Initial release
