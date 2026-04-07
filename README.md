# NotebookLM Content Curator `v0.1.1`

Syncs tagged markdown files from any folder into a Google Doc, so they can be used as sources in [NotebookLM](https://notebooklm.google.com).

Each tagged file is written to its own tab in the Google Doc. The script tracks what has already been synced using a local registry file and only updates tabs whose content has actually changed (detected by hash). New tabs are created automatically when needed.

---

## How it works

1. Run the script from your notes folder, or point it at one with `--dir`
2. It scans recursively for `.md` files whose YAML frontmatter includes the target tag
3. It connects to your Google Doc and checks the current tab state
4. It adds new files to available tabs (creating new ones if needed), updates changed files, and skips unchanged ones
5. It saves a `notebooklm-registry.json` in the scanned folder to track sync state
6. It prints a report showing exactly what happened

---

## Setup

### 1. Install dependencies

```bash
pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pyyaml
```

### 2. Set up Google OAuth (one-time, uses your existing Google account)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) — sign in with the Google account that owns your Docs
2. Create a project (any name, e.g. "NotebookLM Curator")
3. Enable two APIs: **Google Docs API** and **Google Drive API**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
5. Choose **Desktop app**, click Create, then **Download JSON**
6. Save the downloaded file to:

```
~/.config/notebooklm-curator/credentials.json
```

The first time you run the script a browser window opens asking you to sign in and grant access. After that the token is cached at `~/.config/notebooklm-curator/token.json` (readable only by you) and you won't be prompted again.

### 3. Create your Google Doc

- Create a Google Doc with any name
- You don't need to pre-create tabs — the script creates them automatically as needed
- Point the script at it using `--file "Your Doc Name"` or set `google_doc_name` in `notebooklm-registry.json`

---

## Tagging files

Add a YAML frontmatter block at the top of any `.md` file you want synced:

```yaml
---
tags:
  - notebooklm-source
---

# My Document Title

Content goes here...
```

Other accepted formats:

```yaml
# Inline list
tags: [notebooklm-source, other-tag]

# Standalone key
notebooklm-source: true
```

Files without the tag are ignored entirely. The YAML frontmatter block itself is not written to the Google Doc — only the markdown body is synced.

---

## Usage

```bash
# Check version
python3 notebooklm-content-curator.py --version

# Preview what would change in the current directory
python3 notebooklm-content-curator.py --tag notebooklm-source --file "my-notebooklm-doc" --dry-run

# Sync the current directory
python3 notebooklm-content-curator.py --tag notebooklm-source --file "my-notebooklm-doc"

# Sync a specific folder
python3 notebooklm-content-curator.py --dir ~/notes --tag notebooklm-source --file "my-notebooklm-doc"

# Sync with a custom tag
python3 notebooklm-content-curator.py --dir ~/notes --tag research --file "research-notebooklm" --dry-run
```

### Switches

| Switch | Default | Description |
|---|---|---|
| `--dir PATH` | current directory | Directory to scan recursively for tagged markdown files |
| `--tag TAG` | *(required)* | Frontmatter tag to look for |
| `--file DOC_NAME` | *(required)* | Name of the Google Doc to sync to |
| `--dry-run` / `--preview` | off | Preview changes without writing anything |
| `--version` | — | Print the version number and exit |

### `--tag`

Required. Specifies which frontmatter tag to look for. Useful when you have multiple workflows or vaults with different tagging conventions.

```yaml
# This file is picked up with --tag research
---
tags:
  - research
---
```

```bash
python3 notebooklm-content-curator.py --dir ~/notes/research --tag research --file "research-notebooklm"
```

### `--file`

Required. Specifies the name of the Google Doc to sync to.

```bash
# Sync two separate vaults to two separate docs
python3 notebooklm-content-curator.py --dir ~/notes/project-a --tag project-a --file "project-a-notebooklm"
python3 notebooklm-content-curator.py --dir ~/notes/project-b --tag project-b --file "project-b-notebooklm"
```

---

## Example output

```
📋 NotebookLM Sync Report — 2026-04-07 10:32 UTC

✅ Added:    2 file(s)
🔄 Updated:  1 file(s)
⏭️  Skipped:  4 file(s) (already up to date)

⚠️  Warnings:
  - "quarterly-review.md" — 'notebooklm-source' tag removed. Tab 'Quarterly Review' left intact.
    → Please confirm: should this tab be cleared or kept?

📊 Tab usage: 7 of 9 tabs used. 2 empty tabs remaining.
```

---

## Registry file

The script creates `notebooklm-registry.json` in the scanned directory. It tracks which files are synced to which tabs, along with content hashes used to detect changes.

**You do not need to edit this file manually.** But if something looks wrong, you can open it to inspect or correct entries.

| Field | Description |
|---|---|
| `google_doc_name` | Name used to search for the Google Doc |
| `google_doc_id` | Cached document ID (populated after first run) |
| `last_sync` | UTC timestamp of the last successful sync |
| `tabs` | Map of tab keys to synced file metadata |

> **Tip:** Delete `notebooklm-registry.json` to force a full re-sync from scratch.

---

## Warnings and edge cases

| Situation | Behaviour |
|---|---|
| Not enough empty tabs in the doc | New tabs created automatically |
| Tag removed from a file | Warning printed, tab left intact — no automatic deletion |
| File deleted from disk | Warning printed, tab left intact |
| File larger than 5 MB | Skipped with a warning |
| Symlinks in the scanned directory | Skipped |
| Registry exists but doc was recreated | Integrity check surfaces mismatches as warnings |
| Corrupt registry file | Warning printed, registry starts fresh |
| Google Doc not found by name | Error with instructions to verify the name or set `google_doc_id` manually |
| No tagged files found | Script exits cleanly with a message |
| Duplicate tab titles across files | Filename appended automatically to disambiguate |
| Expired or revoked token | Automatically re-authenticates via browser |

---

## Running from multiple folders

Each folder gets its own `notebooklm-registry.json`. You can sync multiple vaults to the same Google Doc or to different ones.

```bash
python3 notebooklm-content-curator.py --dir ~/work/project-a --file "project-a-notebooklm"
python3 notebooklm-content-curator.py --dir ~/work/project-b --file "project-b-notebooklm"
```

---

## Changelog

### v0.1.2
- Increased file size limit from 1 MB to 5 MB
- `--tag` is now a required argument (no longer defaults to `notebooklm-source`)
- `--file` is now a required argument (no longer read from registry)

### v0.1.1
- Added `--tag` switch to specify which frontmatter tag to look for
- Added `--file` switch to specify the target Google Doc by name
- Added `--dir` switch to specify the directory to scan
- Added `--dry-run` / `--preview` switch to preview changes without writing anything
- Added `--version` switch to print the version number

### v0.1.0
- Initial release

---

## Security

- OAuth token is stored as JSON with `0o600` permissions (owner-readable only)
- Symlinks inside the scanned directory are skipped to prevent reading files outside it
- Files larger than 5 MB are skipped
- The Google Drive search query is escaped to handle special characters in doc names
