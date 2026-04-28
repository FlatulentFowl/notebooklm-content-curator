# AGENTS.md — Agent Workflow

Documents the agents and agent patterns used in this project, and how to invoke them.

---

## The Advisor

The advisor is a stronger reviewer model that sees your entire conversation history — every tool call, every result, every piece of reasoning — and gives independent feedback before you commit to an approach.

### When to call it

Call `advisor()` (the tool, not a subagent) before any of the following:

- **Before writing code** — especially when the approach involves multiple files, an ordering dependency, or a security-sensitive area (credentials, config loading, gitignore)
- **When stuck** — recurring errors, an approach that isn't converging, results that don't make sense
- **When changing direction** — before abandoning an approach, ask the advisor whether the premise was wrong
- **When the task is complete** — write the file or make the change first (so the result is durable), then call advisor to validate before reporting done

The advisor adds the most value on the *first* call, before the approach crystallises. On short reactive tasks where the next action is obvious from the tool output you just read, skip it.

### How to use the feedback

Give the advice serious weight. If empirical evidence (a file says X, a test shows Y) contradicts a specific advisor claim, surface the conflict with another advisor call rather than silently switching sides. If the advice is sound, follow it — don't re-derive the same conclusion independently.

---

## Plan Mode

For any change touching more than two files, or where execution order matters, enter plan mode before writing code.

```
/plan
```

The plan file lives at `.claude/plans/<name>.md`. A good plan includes:
- **Context** — why the change is needed
- **Ordered steps** — what changes, in what files, in what sequence
- **Verification** — concrete commands to confirm correctness after execution

Plans are approved by the user before implementation begins. Use the advisor inside plan mode to validate the approach before writing the plan file.

---

## Security Scan Agent

A dedicated Python script that audits the codebase for privacy and security issues. Run it before any commit that touches credential handling, config loading, or `.gitignore`, and before making the repository public.

### Running the scan

```bash
python3 scripts/security-scan.py

# Exit 1 on any MEDIUM or higher finding (stricter mode)
python3 scripts/security-scan.py --strict
```

### What it checks

| Category | Checks |
|---|---|
| **Hardcoded secrets** | Patterns matching API keys, OAuth tokens, client IDs/secrets, passwords, bearer tokens |
| **Personal data** | Email addresses, names in the format `"First Last"`, phone number patterns (in tracked files only) |
| **Git tracking** | Whether sensitive files (credentials, tokens, config) are currently tracked |
| **Git history** | Whether any sensitive files appear anywhere in commit history |
| **Gitignore coverage** | Whether known-sensitive filenames are covered by `.gitignore` |
| **File permissions** | Whether credential files in `GOOGLE_CONFIG_DIR` have overly permissive modes (should be 600) |
| **Environment leaks** | `os.getenv()` calls with hardcoded secret-looking fallback values |
| **Direct config reads** | Scripts that read `settings.json` directly instead of using `agent_utils.load_config()` |

### Severity levels

- **CRITICAL** — active credential or secret exposed in a tracked file
- **HIGH** — personal data in a tracked file; sensitive file in git history
- **MEDIUM** — overly permissive file permissions; missing gitignore entry
- **LOW** — suspicious pattern that may be a false positive; direct config file access

### Interpreting results

The scan prints findings grouped by severity. CRITICAL and HIGH findings must be resolved before the repository is made public. MEDIUM findings are strong recommendations. LOW findings require human judgement.

After resolving findings, re-run the scan to confirm they are cleared.

---

## Explore Subagent

For open-ended codebase exploration — finding where a function is defined, which files reference a symbol, understanding an unfamiliar area — spawn an `Explore` subagent rather than running multiple `grep`/`find` commands inline.

Use `Explore` when:
- The scope of a search is uncertain (multiple naming conventions, nested directories)
- You need to understand a pattern across more than 3–4 files
- You want to find existing implementations before proposing to write new code

Use direct `grep` or `Read` when:
- You already know the file or line number
- It's a single targeted lookup

---

## Agent Invocation Reference

| Situation | Action |
|---|---|
| Multi-file implementation | `/plan` → advisor → implement → advisor |
| Security-sensitive change | `advisor()` → implement → `python3 scripts/security-scan.py` |
| Unfamiliar area of codebase | Spawn `Explore` subagent |
| Stuck or blocked | `advisor()` with full context of what's been tried |
| Task complete | Write result → `advisor()` → report to user |
| Recurring errors | `advisor()` — describe what's been tried and what failed |
