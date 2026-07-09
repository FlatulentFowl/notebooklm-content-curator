# Productivity Agent - Decision Log

Significant architectural and security decisions, per CLAUDE.md §6. Newest entries last.

## D-001: requirements.txt is generated output of uv.lock (2026-07-09)

`uv.lock` is the source of truth for dependency resolution. `requirements.txt` is kept only
for pip-based installs and is regenerated with:

```
uv export --format requirements-txt --no-dev > requirements.txt
```

Never hand-edit `requirements.txt`. Context: the file had drifted — it still pinned
`yt-dlp==2026.3.17` long after the podcast tool migrated to the YouTube Data API, and it
omitted `requests` (used directly by `tool_podcast.py`) which is now declared in
`pyproject.toml`.

## D-002: Scope of the 2026-07 remediation round — podcast tool only (2026-07-09)

A full-app review (efficiency / effectiveness / security) was performed on 2026-07-09.
Remediation this round is intentionally limited to the podcast tool: HTTP timeout,
API retries, `--dry-run`, dependency hygiene, service-layer refactor per
ARCHITECTURE.md, tests, and CI.

Remaining findings are accepted for now and tracked here as follow-ups:

- **Meet tool duplicates tasks on re-run** (`src/tools/tool_meet.py`,
  `create_task_with_subtasks`): no existence check before insert. Highest-priority
  follow-up.
- **`tool_tasks.py` promote is non-atomic**: subtasks are created before source notes
  are cleared; a crash in between duplicates subtasks on the next run.
- **Missing `num_retries` in `tool_tasks.py` and `tool_notebooklm.py`** API calls.
- **N+1 Drive lookups in `tool_notebooklm.py`**: one `files().list` per local file;
  should list the target folder once.
- **Dead code**: `src/prod_agent_meet.py` is a byte-identical orphaned copy of
  `src/tools/tool_meet.py` (still referenced in pyproject `script-files`); `k.json`
  is a tracked empty stray file.
- **security-scan.py gaps**: `k.json` not in `SENSITIVE_FILENAMES`; lone first names
  (e.g. in `pyproject.toml` authors) are not detected.
- **PII in git history (accepted risk)**: `config.json` containing a real name and
  playlist URLs was committed at `ba78ae0` and later untracked; it remains retrievable
  from history. Decision: no history rewrite (private repo; a rewrite would invalidate
  clones). Mitigations: file is gitignored, and the scanner's history check flags it.
- **SSH private key in git history (ACTION REQUIRED)**: an OpenSSH ed25519 keypair
  (`ghPAT` / `ghPAT.pub`) was committed at `70db7a6` and removed at `2d2d920`, but the
  private key remains fully retrievable from history (`git show 70db7a6:ghPAT`). The key
  is passphrase-protected, which limits immediate exposure, but it must be treated as
  compromised: **remove this public key from GitHub (Settings → SSH keys / deploy keys)
  and stop using the keypair.** Once revoked, the historical blob is inert; a history
  rewrite remains optional and is currently declined for the same reasons as above.
- **Service-layer refactor of the remaining tools** (meet, tasks, notebooklm) and
  replacing the `subprocess.run` dispatch in `prod_agent.py` with direct imports —
  per docs/ARCHITECTURE.md and docs/STATUS.md Phase 1.

## D-003: Podcast HTTP resilience defaults (2026-07-09)

All podcast HTTP traffic (transcript fetches via `youtube_transcript_api`) now goes
through a `TimeoutSession` with a default timeout of 30 seconds, overridable via the
`PODCAST_HTTP_TIMEOUT` env var. YouTube Data API calls use the client library's
`num_retries=3` exponential backoff. Rationale: CLAUDE.md §3 resilience rules — no
silent hangs, exponential backoff for APIs.
