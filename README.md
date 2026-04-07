# NotebookLM Content Curator `v0.1.0`

Syncs tagged markdown files from any folder into a Google Doc, so they can be used as sources in [NotebookLM](https://notebooklm.google.com).

Each tagged file gets its own tab in the Google Doc. The script tracks what has already been synced and only updates files whose content has actually changed. New tabs are created automatically when needed.

---

## How it works

1. Run the script from any folder (or point it at one with `--dir`)
2. It scans recursively for `.md` files tagged as NotebookLM sources in their YAML frontmatter
3. It connects to your Google Doc and checks the current tab state
4. It adds new files to available tabs (creating new tabs if needed), updates changed files, and skips unchanged ones
5. It saves a `notebooklm-registry.json` in your folder to track sync state
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

The first time you run the script a browser window opens asking you to sign in and grant access. After that the token is cached at `~/.config/notebooklm-curator/token.json` and you won't be prompted again.

### 3. Prepare your Google Doc

- Create a Google Doc named exactly: `frictionless-supply-chain-notebooklm`
- You don't need to pre-create tabs — the script creates them automatically as needed

> **Tip:** You can change the document name in `notebooklm-registry.json` under `google_doc_name`, or add a `google_doc_id` field directly if you know the document ID.

---

## Tagging a file

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

## Tab titles

The tab title in Google Docs is derived from the file:

- If the file has a `# H1 heading`, that becomes the tab title
- Otherwise the filename is used, with hyphens/underscores replaced by spaces and title-cased

| Filename | H1 heading | Tab title |
|---|---|---|
| `supply-chain-overview.md` | `# Supply Chain Overview` | Supply Chain Overview |
| `risk-register.md` | *(none)* | Risk Register |

If two files would produce the same tab title, the filename is appended to disambiguate: `Supply Chain Overview (overview-v1.md)`.

> **Note:** Tab renaming is not currently supported by the Google Docs API. Tabs keep whatever title they had when created.

---

## Usage

```bash
# Preview what would change — no writes to Google Doc or registry
python3 notebooklm-content-curator.py --dry-run

# Sync from a specific directory
python3 notebooklm-content-curator.py --dir /path/to/your/vault

# Sync files with a custom tag
python3 notebooklm-content-curator.py --tag my-custom-tag

# Sync to a specific Google Doc by name
python3 notebooklm-content-curator.py --file "my-notebooklm-doc"

# Combine all options
python3 notebooklm-content-curator.py --dir ~/notes --tag research --file "research-notebooklm" --dry-run
```

### Switches

| Switch | Default | Description |
|---|---|---|
| `--dir PATH` | `test` | Directory to scan recursively for tagged markdown files |
| `--tag TAG` | `notebooklm-source` | Frontmatter tag to look for |
| `--file DOC_NAME` | *(from registry)* | Name of the Google Doc to sync to |
| `--dry-run` | off | Preview changes without writing anything |

### `--tag`

By default the script looks for files tagged `notebooklm-source`. Use `--tag` to target a different tag, for example if you have multiple workflows or vaults with different tagging conventions.

```yaml
# This file would be picked up with --tag research
---
tags:
  - research
---
```

```bash
python3 notebooklm-content-curator.py --tag research --dir ~/notes/research
```

### `--file`

By default the target Google Doc is read from `notebooklm-registry.json`. Use `--file` to override this — useful when syncing different directories to different docs, or when setting up for the first time without editing the registry manually.

```bash
# Sync project-a notes to one doc, project-b to another
python3 notebooklm-content-curator.py --dir ~/notes/project-a --file "project-a-notebooklm"
python3 notebooklm-content-curator.py --dir ~/notes/project-b --file "project-b-notebooklm"
```

> **Note:** `--file` always looks up the doc by name, ignoring any cached doc ID in the registry.

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

**You do not need to edit this file manually.** But if something looks wrong, you can open it to inspect or correct entries. The important fields are:

| Field | Description |
|---|---|
| `google_doc_name` | Name used to search for the Google Doc |
| `google_doc_id` | Cached document ID (populated after first run) |
| `last_sync` | UTC timestamp of the last successful sync |
| `tabs` | Map of tab keys to synced file metadata |

---

## Warnings and edge cases

| Situation | Behaviour |
|---|---|
| Registry exists but doc was recreated | Integrity check surfaces mismatches — reported as warnings |
| Tag removed from a file | Warning printed, tab left intact — no automatic deletion |
| File deleted from disk | Warning printed, tab left intact |
| Not enough empty tabs | New tabs created automatically |
| File larger than 1 MB | Skipped with a warning |
| Symlinks in the scanned directory | Skipped (security) |
| Google Doc not found by name | Error message with instructions to verify the name or add the ID manually |
| No tagged files found | Script exits cleanly with a message |
| Duplicate tab titles across files | Filename appended automatically to disambiguate |
| Corrupt registry file | Warning printed, registry starts fresh |
| Expired or revoked token | Automatically re-authenticates via browser |

---

## Running from multiple folders

Each folder gets its own `notebooklm-registry.json`. You can sync multiple vaults to the same Google Doc or to different ones — just set the appropriate `google_doc_name` or `google_doc_id` in each registry file.

```bash
python3 notebooklm-content-curator.py --dir ~/work/project-a
python3 notebooklm-content-curator.py --dir ~/work/project-b
```
