# Productivity Agent

A suite of scripts that pull your Google Workspace activity from the previous weekday and export it as markdown files, ready for use as [NotebookLM](https://notebooklm.google.com) sources or any other purpose. On Mondays, the scripts automatically look back to the previous Friday.

| Script | What it does | Output folder |
|---|---|---|
| `prod-agent-chat.py` | Google Chat messages from all spaces | `Google Chat/` |
| `prod-agent-meet.py` | Google Meet Gemini notes and transcripts | `Google Meet/` |
| `prod-agent-mail.py` | Gmail sent and received emails | `Google Mail/` |
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
  "ignored_spaces": [
    "Daily Standup (ROOM)"
  ],
  "ignored_meetings": [
    "All Hands Meeting"
  ],
  "ignored_senders": [
    "noreply@example.com",
    "notifications@"
  ],
  "meet_notes_search_term": "Notes from"
}
```

| Key | Used by | Description |
|---|---|---|
| `ignored_spaces` | `prod-agent-chat.py` | Space display names or space resource IDs to skip |
| `ignored_meetings` | `prod-agent-meet.py` | Calendar event titles or event IDs to skip |
| `ignored_senders` | `prod-agent-mail.py` | Substring patterns matched against From and To headers. Partial matches work — e.g. `"rgottwald+"` skips all plus-addressed variants |
| `meet_notes_search_term` | `prod-agent-meet.py` | Override the Drive search term for Gemini notes (default: `"Notes from"`) |

> **Note:** `config.json` is excluded from git via `.gitignore` as it may contain identifying information.

---

## Scripts

### `prod-agent-chat.py` — Google Chat

Fetches messages from all Google Chat spaces you are a member of, covering the previous weekday. On Mondays, it exports messages from the previous Friday. Spaces with no recent activity are skipped automatically.

**APIs required:** Google Chat API  
**Token:** `~/.config/productivity-agent/google-chat-token.json`

**Output:** `Google Chat/google-chats-DD-MM-YYYY.md`

Each message is formatted as:
```
[DD-MM-YYYY] **Sender Name**: Message text
```

**Optional files:**
- `user_mapping.json` — map Google user resource IDs to display names
- `space_mapping.json` — map space resource IDs to friendly names

> Both files are excluded from git via `.gitignore`.

```bash
python3 prod-agent-chat.py
```

---

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

### `prod-agent-mail.py` — Gmail

Fetches sent and received emails from the previous weekday. On Mondays, it processes emails from the previous Friday. For threaded conversations, only the most recent message in each thread is included.

**APIs required:** Gmail API  
**Token:** `~/.config/productivity-agent/google-mail-token.json`

**Output:** `Google Mail/`
- `DD-MM-YYYY-emails-received.md`
- `DD-MM-YYYY-emails-sent.md`

Each email is formatted as:
```markdown
## Subject line
**From:** sender@example.com
**To:** recipient@example.com
**Date:** DD-MM-YYYY HH:MM

Body text...

---
```

**Filtering:**
- Emails from/to addresses matching any pattern in `ignored_senders` are skipped
- Calendar meeting invites (emails with a `text/calendar` part) are skipped automatically

```bash
python3 prod-agent-mail.py
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
- Added `prod-agent-chat.py` — exports Google Chat messages to markdown
- Added `prod-agent-meet.py` — exports Google Meet Gemini notes and transcripts to markdown
- Added `prod-agent-mail.py` — exports Gmail sent/received emails to markdown
- Added `config.json` support across all scripts for filtering ignored spaces, meetings, and senders
- Output files now written to dedicated folders: `Google Chat/`, `Google Meet/`, `Google Mail/`
- Added `user_mapping.json` and `space_mapping.json` support in chat script
- Message timestamps formatted as `DD-MM-YYYY` (en-GB)

### v0.1.2
- Increased file size limit from 1 MB to 5 MB
- `--tag` is now a required argument
- `--file` is now a required argument

### v0.1.1
- Added `--tag`, `--file`, `--dir`, `--dry-run`, `--version` switches

### v0.1.0
- Initial release
