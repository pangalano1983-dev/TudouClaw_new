# Tudou Claw — `app/` Architecture

## Overview

The `app/` package is the main application module for Tudou Claw (土豆爪), a multi-agent AI assistant platform. The codebase is organized into four sub-packages by responsibility, plus a `static/` directory for assets.

## Directory Structure

```
app/
├── __init__.py              # Package init
├── __main__.py              # Entry point (python -m app)
├── config.yaml              # Application configuration
│
├── core/                    # Core domain models & orchestration
│   ├── __init__.py
│   ├── agent.py             # Agent dataclass, lifecycle, system prompt building
│   ├── hub.py               # AgentHub — central registry & coordination
│   ├── project.py           # Project management & task tracking
│   ├── workflow.py           # Multi-step workflow engine
│   ├── channel.py           # Communication channels between agents
│   └── persona.py           # Role persona definitions & loading
│
├── engines/                 # Specialized processing engines
│   ├── __init__.py
│   ├── active_thinking.py   # Enhanced reasoning / chain-of-thought engine
│   ├── experience_library.py # Self-improvement: experience storage, retrieval, seeds
│   ├── enhancement.py       # Output enhancement & post-processing
│   └── template_library.py  # Reusable prompt/workflow templates
│
├── server/                  # HTTP servers & API endpoints
│   ├── __init__.py
│   ├── portal.py            # Main web portal — dashboard, agent management, UI
│   ├── web.py               # HTTP server setup & routing
│   ├── agent_server.py      # Agent service REST API
│   └── auth.py              # Authentication & authorization
│
├── infra/                   # Infrastructure & external integrations
│   ├── __init__.py
│   ├── llm.py               # LLM provider abstraction (OpenAI, Anthropic, etc.)
│   ├── tools.py             # Tool definitions & execution (bash, web, file, audio)
│   ├── sandbox.py           # Sandboxed code execution environment
│   ├── scheduler.py         # Task scheduling & cron-like jobs
│   ├── mcp_manager.py       # MCP (Model Context Protocol) server management
│   └── src_bridge.py        # Bridge to external source systems
│
├── static/                  # Static assets (served via HTTP)
│   ├── config/              # JSON configuration files
│   │   ├── roles.json       # Role definitions (id, title, can_do, cannot_do, delegates_to)
│   │   ├── robots.json      # Robot avatar metadata
│   │   └── experience_seeds.json  # Seed experiences per role for self-improvement
│   │
│   ├── robots/              # SVG robot avatars (one per role)
│   │   ├── robot_ceo.svg
│   │   ├── robot_cto.svg
│   │   ├── robot_coder.svg
│   │   └── ...              # robot_{role}.svg
│   │
│   └── templates/           # Markdown templates
│       ├── souls/           # Agent persona/soul templates
│       │   ├── soul_ceo.md
│       │   ├── soul_cto.md
│       │   └── ...          # soul_{role}.md
│       │
│       └── thinking/        # Active thinking prompt templates
│           ├── active_thinking_ceo.md
│           ├── active_thinking_coder.md
│           ├── active_thinking_rules.md
│           └── ...          # active_thinking_{role}.md
│
└── data/                    # Runtime data (not in git, generated at runtime)
    ├── experience/          # Experience library files (per-role, daily/weekly)
    │   ├── {role}/
    │   │   ├── exp_{role}_YYYYMMDD.json       # Daily experiences
    │   │   ├── exp_{role}_weekly_YYYYWNN.json  # Weekly consolidated
    │   │   └── exp_{role}_core.json            # Core high-priority experiences
    │   └── ...
    └── community_skills.json
```

## Module Responsibilities

### `core/` — Domain Models & Orchestration

The heart of the system. Contains the agent model, hub coordination, project management, and inter-agent communication.

- **agent.py**: The `Agent` dataclass is the central abstraction. Manages agent state, system prompt construction (with experience injection), token usage tracking, tool permissions, and self-improvement integration.
- **hub.py**: `AgentHub` is the global agent registry. Handles agent creation, persistence, lookup, and cross-agent coordination.
- **project.py**: Project and task management. Agents are assigned to projects; tasks flow through defined stages.
- **workflow.py**: Multi-step workflow engine for complex operations that span multiple agents.
- **channel.py**: Communication channels enabling message passing between agents.
- **persona.py**: Loads and manages role-based persona definitions from soul templates.

### `engines/` — Processing Engines

Specialized modules that enhance agent capabilities beyond basic LLM calls.

- **active_thinking.py**: Implements chain-of-thought reasoning with role-specific templates. Loads templates from `static/templates/thinking/`.
- **experience_library.py**: The self-improvement engine. Manages per-role experience storage with daily/weekly file rotation, size limits (512KB daily, 1MB weekly, 256KB core), seed loading, effectiveness tracking, and experience context injection into agent prompts.
- **enhancement.py**: Post-processing pipeline for agent outputs (formatting, validation, enrichment).
- **template_library.py**: Library of reusable prompt templates and workflow patterns.

### `server/` — HTTP & API Layer

All web-facing code lives here.

- **portal.py**: The main web portal (~9600 lines). Serves the single-page dashboard UI, agent management panels, self-improvement UI, and all `/api/portal/*` endpoints. Also serves static assets under `/static/robots/`, `/static/templates/`, and `/static/config/`.
- **web.py**: HTTP server initialization, middleware, and top-level routing.
- **agent_server.py**: REST API for agent operations (create, chat, stream, tool execution).
- **auth.py**: Token-based authentication and API key management.

### `infra/` — Infrastructure

External system integrations and low-level infrastructure.

- **llm.py**: Abstraction layer over LLM providers (OpenAI, Anthropic, local models). Handles streaming, retries, and token counting.
- **tools.py**: Tool registry and execution. Built-in tools include bash, file operations, web search, and audio (TTS/STT).
- **sandbox.py**: Sandboxed execution environment for running untrusted code safely.
- **scheduler.py**: Background task scheduling (periodic health checks, experience consolidation, etc.).
- **mcp_manager.py**: Manages MCP server connections for external tool integration.
- **src_bridge.py**: Bridge module for connecting to external source/knowledge systems.

### `static/` — Assets

All static files served to the frontend.

- **config/**: JSON configuration files loaded at startup (role definitions, experience seeds).
- **robots/**: SVG avatar images, one per agent role.
- **templates/souls/**: Markdown persona templates that define each role's personality, expertise, and behavioral guidelines.
- **templates/thinking/**: Markdown templates for active thinking prompts, customized per role.

## Backward Compatibility

The original flat Python files (`app/agent.py`, `app/portal.py`, etc.) remain at the top level alongside the sub-packages. These serve as backward-compatible entry points — existing imports like `from app.agent import Agent` continue to work. The canonical code now lives in the sub-packages.

The original `static/souls/` directory also remains for backward compatibility, with the canonical copies in `static/config/`, `static/templates/souls/`, and `static/templates/thinking/`.

## Key Design Patterns

1. **Role-based architecture**: Every agent has a role (ceo, cto, coder, etc.) that determines its soul template, thinking template, tool permissions, and experience seeds.
2. **Experience-driven self-improvement**: Agents accumulate experiences through retrospective analysis and active learning, stored in the experience library and injected into system prompts.
3. **Delegation chains**: Roles define `delegates_to` relationships (e.g., CEO delegates to CTO, PM, Architect) enabling hierarchical task delegation.
4. **File rotation**: Experience data uses daily/weekly file rotation with size limits to prevent unbounded growth.
