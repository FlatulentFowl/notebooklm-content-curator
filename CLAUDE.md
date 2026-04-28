# **Productivity Agent \- AI Developer Context**

Welcome. If you are an AI Coding Assistant, Cursor, Claude, Gemini, or any other LLM interacting with this repository, this document contains your **core system instructions**. You must adhere to these principles at all times.

## **1\. The Core Mission (The "Why")**

This system is built for a busy ERP consultant specializing in NetSuite and Supply Chain Management (SCM). The project exists to solve high cognitive load via:

* **Cognitive Offloading:** Automatically extracting commitments and action items from unstructured sources (Google Meet transcripts, Gemini Smart Notes, local Markdown) and routing them to a structured hub (Google Tasks).  
* **Knowledge Pipeline Automation:** Continuously fetching domain-specific intelligence (SCM trends, NetSuite updates via podcasts/YouTube) to learning engines like NotebookLM.  
* **Ecosystem Bridging:** Seamlessly connecting Google Workspace, local file systems, and external APIs.

## **2\. Development Philosophy & Roadmap (The "How")**

We are employing a strict "Crawl, Walk, Run" phased approach.

* **PHASE 1 (Current State): Rock-Solid Modular Tools**  
  * We are currently building highly reliable, deterministic, and stable tools.  
  * **Strict Modularity is Required:** Procedural "spaghetti" scripts are forbidden. You must actively refactor existing procedural code (e.g., prod-agent-meet.py, prod-agent-tasks.py) into dedicated, reusable service classes.  
  * **Separation of Concerns:** Business logic (parsing text) must be strictly separated from API execution (calling Google).  
* **PHASE 2 (Future State): The Agent Swarm**  
  * Once the V1 tools are perfectly stable, we will introduce a probabilistic LLM Agent to autonomously orchestrate these tools. *All V1 refactoring must serve this eventual goal by exposing clean, predictable tool interfaces.*

## **3\. Security & Hardening (Zero Exceptions)**

Because this system handles enterprise consulting notes, security is paramount to prevent vulnerabilities:

* **No Hardcoded Credentials:** Never suggest or write code that hardcodes API keys, tokens, or secrets.  
* **Secure OAuth Handling:** Follow strict least-privilege principles. Reference .env.example and settings.json.example.  
* **Input Validation:** Always sanitize and validate inputs, especially when parsing external Markdown or transcripts.  
* **Robust Error Handling:** Do not allow silent failures. Implement exponential backoff for APIs and log errors explicitly.

## **4\. Technical Environment & Commands**

* **Language & Management:** Python 3.x using uv (Refer to pyproject.toml and uv.lock).  
* **Setup Authentication:** uv run src/setup-auth.py  
* **Run the Application:** uv run src/prod-agent.py  
* **Security Scanning:** uv run scripts/security-scan.py (Must be run to verify no exposed secrets or vulnerabilities).

## **5\. AI Workflow & State Management Rules**

To maintain context across sessions, you must interact with the following files:

1. **STATUS.md (The Save Game):** Before writing code, check STATUS.md to see what task is currently active. When you finish a task, you must update STATUS.md to check off the completed item.  
2. **ARCHITECTURE.md (The Map):** Consult this file for the target state of the codebase. Do not introduce new libraries or structural patterns without aligning them with this document.  
3. **DECISIONS.md (The Memory):** If we make a significant architectural or security decision, record it here so future AI sessions do not undo the work.