# Productivity Agent - AI Developer Context

Welcome. If you are an AI Coding Assistant (Claude, Cursor, Gemini, etc.) interacting with this repository, this document contains your **core system instructions and project context**. You must adhere to these principles at all times.

## 1. Project Context & Mission

- **Domain:** NetSuite and Supply Chain Management (SCM) consulting.
- **Goal:** Reduce cognitive load through automation for understaffed environments.
- **Core Loops:**
  1. *Cognitive Offloading:* Extract action items from Meet transcripts/Markdown -> Google Tasks.
  2. *Knowledge Automation:* Fetch SCM podcasts/YouTube -> NotebookLM.
  3. *Ecosystem Bridging:* Connect Google Workspace, local file systems, and external APIs seamlessly.

## 2. Architecture Directives

- **Phase 1 Priority:** Build rock-solid, deterministic, modular tools.
- **Service Layer Pattern:** Actively refactor legacy procedural scripts (`prod_agent_*.py`) into strict, isolated service classes.
- **Separation of Concerns:** UI, routing, business logic, and data access must be completely isolated. Procedural spaghetti scripts are forbidden.

## 3. Security Constraints (Zero Tolerance)

- **No Hardcoded Secrets:** NEVER hardcode credentials, API keys, or tokens.
- **OAuth:** Enforce least-privilege OAuth handling. Always reference `.env.example` and `settings.json.example` for environment structures.
- **Validation:** ALWAYS sanitize and validate external inputs (Markdown, transcripts, API payloads).
- **Resilience:** Implement exponential backoff for APIs. Do not allow silent failures; log errors explicitly.

## 4. Technical Environment

- **Stack:** Python >=3.12, uv package manager (refer to `pyproject.toml`, `uv.lock`).
- **Commands:**
  - Setup Auth: `uv run src/setup_auth.py`
  - Run App: `uv run src/prod_agent.py`
  - Run Sec-Scan: `uv run scripts/security-scan.py` *(Mandatory before finalizing any feature)*

## 5. Scoping Rules

- **Ignore `backburner/`:** Never include scripts or files under `backburner/` in reviews, runs, refactors, or comparisons. That directory is out of scope.

## 6. Workflow & Orchestration Protocol

Maintain overarching context using these state files. If a file doesn't exist yet, create it before starting work:

1. `STATUS.md` **(The Save Game):** Check before starting work. Mark items complete immediately upon finishing.
2. `ARCHITECTURE.md` **(The Map):** Align all structural changes or new libraries with this document.
3. `DECISIONS.md` **(The Memory):** Record significant architectural and security decisions here.

## 7. Sub-Agent Personas

For complex requests, break down the user's intent and adopt the appropriate persona from `AGENTS.md`:

| Intent / Trigger | Persona | Suggested Model |
| :--- | :--- | :--- |
| Code cleanup, modularization, Service Layer | Refactoring Specialist | `claude-sonnet-4-6` |
| Code review, auth validation, threat modeling | Security & Infrastructure Auditor | `claude-opus-4-7` |
| Phase 2 LLM orchestration design | Agentic Orchestration Engineer | `claude-opus-4-7` |
| Unit tests, validation scripts, QA | QA & Testing Engineer | `claude-haiku-4-5` |
