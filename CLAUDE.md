# CLAUDE.md — Productivity Agent

Project-level instructions for Claude Code. These override default behaviour for this repository.

---

## Project Overview

A suite of Python 3.12 automation scripts that wire together Google Workspace, YouTube, and local markdown files into a daily productivity workflow. All scripts share a common credential/config layer in `agent_utils.py`.

```
src/
  prod-agent-meet.py        Google Meet Gemini notes → Google Tasks
  prod-agent-tasks.py       Checkbox notes → subtasks (destructive: clears notes)
  prod-agent-notebooklm.py  Tagged markdown files → Google Drive / NotebookLM
  prod-agent-podcast.py     YouTube playlists → local transcript markdown files
  agent_utils.py            Shared OAuth, date range, and config utilities
  setup-auth.py             One-time OAuth consent flow (run manually)

scripts/
  security-scan.py          Privacy and security audit script
```

---

## Key Conventions

### Dry-run first
Every script that writes or deletes data has a `--dry-run` flag. Always suggest running with `--dry-run` before suggesting a real run. `prod-agent-tasks.py` is the most destructive — it permanently clears task notes after promoting checkboxes.

### Config lives in `settings.json`
User config (name, ignored meetings, podcast playlists) is in `settings.json` in the project root. It is gitignored. Access it only via `agent_utils.load_config()` — never read it directly in scripts. Never suggest adding it to git.

### Credentials are never in the repo
The following are gitignored and must stay that way:
- `settings.json` — personal config
- `credentials.json` — OAuth client secrets (downloaded from Google Cloud Console)
- `google-*-token.json` — per-script OAuth tokens (stored in `GOOGLE_CONFIG_DIR`)
- `.env` — environment variables

### Path convention for src/ scripts
`agent_utils.py` derives the project root as the parent of `src/` so that `.env` and `settings.json` are always resolved relative to the repository root, not `src/`. Scripts in `src/` that import `agent_utils` inherit this automatically. `setup-auth.py` does not import `agent_utils`, so it resolves the project root directly.

### Date handling
All date logic uses SAST (UTC+2). The default mode for `prod-agent-meet.py` is "previous weekday" — Friday on Mondays. Override with `--date DD/MM/YYYY` or `--date today`.

### No new scripts without `--dry-run`
Any new script in `src/` that writes or deletes data must have a `--dry-run` flag before being considered complete.

### Token files
Each script uses its own token file (`google-meet-token.json`, etc.) stored in `GOOGLE_CONFIG_DIR` (default: `~/.config/productivity-agent`). Do not change this pattern.

---

## Security Rules

- **Never commit** `settings.json`, `config.json`, `credentials.json`, `.env`, or any `*.token.json`.
- **Never hardcode** API keys, email addresses, OAuth client IDs/secrets, or personal names in source files.
- **Never suggest** `git add -A` or `git add .` — always stage files explicitly by name.
- If you find a credential or personal value hardcoded in a file, flag it immediately before doing anything else.
- If a file is being added to git and it looks like it may contain personal data, warn the user before proceeding.
- Run `python3 scripts/security-scan.py` before any commit that changes config loading, credential handling, or `.gitignore`.

---

## Agent Planning Workflow

### Use the advisor before committing to an approach

Call `advisor()` before any substantive work — before writing code, before interpreting an ambiguous requirement, before choosing between two approaches. The advisor is a stronger reviewer that sees your full conversation history and can catch blind spots before they become hard-to-reverse mistakes.

**Always call advisor:**
- Before the first significant edit in a session
- When stuck or getting recurring errors
- When considering a change of approach
- When the task is complete (call it, then report to the user)

### Plan mode for multi-file changes

For any change that touches more than two files or has non-obvious ordering dependencies, use `/plan` to write an implementation plan before executing. The plan should include a verification section. Execute only after the user approves the plan.

### Available agents (see AGENTS.md for detail)

| Agent | When to use |
|---|---|
| `advisor()` | Before/after substantive work; when stuck |
| `Explore` subagent | Codebase exploration across multiple files |
| Security scan | Before going public; after any config/credential change |

---

## Testing & Verification

There is no automated test suite. Verify changes by:

1. **Syntax check:** `python3 -m py_compile src/<file>.py`
2. **Import check:** `python3 -c "import sys; sys.path.insert(0, 'src'); import agent_utils"`
3. **Dry-run:** `python3 src/prod-agent-<name>.py --dry-run`
4. **Config check:** `python3 -c "import sys; sys.path.insert(0, 'src'); from agent_utils import load_config; print(load_config())"`
5. **Security scan:** `python3 scripts/security-scan.py`

Do not claim a change is complete without running at least the syntax check.

---

## Dependencies

Runtime: Python 3.12, managed via `pyproject.toml` and `requirements.txt`.
Install: `pip3 install -r requirements.txt`
No virtual environment is required — packages are installed to system Python 3.12.
