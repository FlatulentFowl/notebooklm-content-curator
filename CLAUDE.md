# **Productivity Agent \- AI Developer Context**

Welcome. If you are an AI Coding Assistant (Claude, Cursor, Gemini, etc.) interacting with this repository, this document contains your **core system instructions and project context**. You must adhere to these principles at all times.

## **1\. Project Context & Mission**

* **Domain:** NetSuite and Supply Chain Management (SCM) consulting.  
* **Goal:** Reduce cognitive load through automation for understaffed environments.  
* **Core Loops:** 1\. *Cognitive Offloading:* Extract action items from Meet transcripts/Markdown \-\> Google Tasks.  
  2\. *Knowledge Automation:* Fetch SCM podcasts/YouTube \-\> NotebookLM.  
  3\. *Ecosystem Bridging:* Connect Google Workspace, local file systems, and external APIs seamlessly.

## **2\. Architecture Directives**

* **Phase 1 Priority:** Build rock-solid, deterministic, modular tools.  
* **Service Layer Pattern:** You must actively refactor legacy procedural scripts (prod-agent-\*.py) into strict, isolated service classes.  
* **Separation of Concerns:** UI, routing, business logic, and data access must be completely isolated from one another. Procedural "spaghetti" scripts are forbidden.

## **3\. Security Constraints (Zero Tolerance)**

* **No Hardcoded Secrets:** NEVER hardcode credentials, API keys, or tokens.  
* **OAuth:** Enforce least-privilege OAuth handling. Always reference .env.example and settings.json.example for environment structures.  
* **Validation:** ALWAYS sanitize and validate external inputs (Markdown, transcripts, API payloads).  
* **Resilience:** Implement exponential backoff for APIs. Do not allow silent failures; log errors explicitly.

## **4\. Technical Environment**

* **Stack:** Python 3.x, uv package manager (refer to pyproject.toml, uv.lock).  
* **Commands:**  
  * Setup Auth: uv run src/setup-auth.py  
  * Run App: uv run src/prod-agent.py  
  * Run Sec-Scan: uv run scripts/security-scan.py *(Mandatory before finalizing features)*.

## **5\. Workflow & Orchestration Protocol**

You act as the central orchestrator for the repository. Maintain overarching context using the following state files:

1. STATUS.md **(The Save Game):** Check this before starting work. Update and check off items immediately upon task completion.  
2. ARCHITECTURE.md **(The Map):** Align all structural changes or new libraries with this document.  
3. DECISIONS.md **(The Memory):** Record significant architectural/security decisions here.

**Sub-Agent Delegation:** For complex requests, avoid writing raw code monolithically. Instead, break down the user's intent and explicitly adopt (or instruct the user to invoke) the appropriate specialized persona from the .agents/ directory:

| Intent / Trigger | Action (Adopt Persona) | Suggested Model |
| :---- | :---- | :---- |
| Design, architecture, or complex planning | .agents/planner.md | Opus / Sonnet |
| Writing raw code or migrating logic | .agents/coder.md | Sonnet 3.5 |
| Code cleanup, modularization, Service Layer | .agents/refactoring.md | Sonnet 3.5 |
| Code review, auth validation, threat modeling | .agents/security.md | Opus |
| Sandboxing, dependencies, Docker, config | .agents/environment.md | Haiku 3.5 |
| Unit tests, validation scripts, QA | .agents/testsuite.md | Haiku / Sonnet |
| README updates, docstrings, API docs | .agents/documenter.md | Haiku 3.5 |
