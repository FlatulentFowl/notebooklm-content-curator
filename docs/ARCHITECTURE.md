# **Productivity Agent \- Architecture Map**

This document outlines the architectural vision for the productivity-agent repository. AI Assistants must use this to understand where logic belongs and how different components interact.

## **Architectural Pattern: The Service Layer**

To ensure testability, modularity, and a clean transition to an LLM Agent Swarm, the project strictly follows the **Service Layer Pattern**.

1. **Core Rule:** Business logic (parsing, filtering, decision making) must *never* be mixed directly with external I/O (API calls, file reading).  
2. **Layers:**  
   * **Orchestration Layer:** (The Controller / Agent) Directs traffic but does no actual work.  
   * **Service Layer:** Contains the business rules and logic. Uses adapters to fetch data.  
   * **Adapter/Infrastructure Layer:** Handles raw API calls to Google, YouTube, NotebookLM, etc.

## **Phase 1 Target State (Modular Monolith)**

In Phase 1, we are refactoring the existing prod-agent-\*.py scripts into the following domain-driven services:

### **1\. Core & Infrastructure Services**

* src/services/config\_service.py: Handles loading settings.json, .env variables, and path management.  
* src/services/auth\_service.py: Centralizes all OAuth flow, credential storage, and token refreshing for Google APIs.

### **2\. Domain Services**

* src/services/workspace\_service.py (Replaces prod-agent-meet.py logic)  
  * *Responsibilities:* Interfacing with Google Drive to fetch Meet transcripts and Docs.  
* src/services/task\_service.py (Replaces prod-agent-tasks.py logic)  
  * *Responsibilities:* Standardizing "Action Items" and syncing them to Google Tasks.  
* src/services/calendar\_service.py  
  * *Responsibilities:* Reading Google Calendar to determine daily context.  
* src/services/ingestion\_service.py (Replaces prod-agent-podcast.py logic)  
  * *Responsibilities:* Fetching and standardizing transcripts/audio from YouTube and podcasts.  
* src/services/knowledge\_service.py (Replaces prod-agent-notebooklm.py logic)  
  * *Responsibilities:* Pushing formatted SCM/NetSuite trends into NotebookLM.

### **3\. Utility Services**

* src/utils/markdown\_parser.py: Pure functions to extract action items, headers, and tags from raw text.

### **4\. The Orchestrator**

* src/prod_agent.py: Instead of using subprocess.run to call other scripts, this file will import the services above and execute them in a deterministic procedural flow (e.g., workspace\_service.get\_transcripts() \-\> markdown\_parser.extract() \-\> task\_service.create\_tasks()).

## **Phase 2 Target State (The Agent Swarm)**

Once Phase 1 establishes stable, isolated service classes, Phase 2 replaces the deterministic prod_agent.py orchestrator with an LLM-driven Agent.

* **The LLM Orchestrator (src/agent/controller.py):** An autonomous loop (e.g., using LangChain or native Anthropic/Gemini APIs) that reads the user's daily calendar and decides which tools to invoke.  
* **Tool Interfaces (src/agent/tools.py):** Wrappers around the Phase 1 Services (e.g., CreateTaskTool(TaskService), FetchSCMTrendsTool(IngestionService)). The LLM calls these tools instead of executing procedural steps.

## **Directory Structure Enforcement**

productivity-agent/  
├── .claude/                \# AI Context (CLAUDE.md, AGENTS.md)  
├── docs/                   \# ARCHITECTURE.md, STATUS.md, DECISIONS.md  
├── scripts/                \# Dev/Sec utilities (security-scan.py)  
├── src/  
│   ├── agent/              \# Phase 2: LLM orchestration and tools  
│   ├── services/           \# Phase 1: Modular business logic  
│   ├── tools/              \# Current CLI entry points (tool_meet.py, tool_tasks.py, tool_notebooklm.py, tool_podcast.py)  
│   ├── utils/              \# Pure functions (parsers, formatters)  
│   ├── prod_agent.py       \# Phase 1 Controller  
│   └── setup_auth.py       \# Auth initialization  
├── .env.example  
├── pyproject.toml  
└── uv.lock  
