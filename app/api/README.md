# app/api/ — FastAPI Backend (New)

This is the **new** HTTP backend built on FastAPI.
It is intended to fully replace the legacy `app/server/` system.

## Structure

```
app/api/
├── main.py              # FastAPI app factory, lifespan, static files
├── deps/                # Dependency injection (hub, auth)
│   ├── hub.py           # get_hub() — shared Hub singleton
│   └── auth.py          # get_current_user() — JWT/token auth
├── middleware/           # ASGI middleware
│   └── security.py      # Security headers
└── routers/             # One file per domain (APIRouter)
    ├── agents.py        # Agent CRUD, model, profile, tasks, thinking, enhancement
    ├── admin.py         # Admin user management, role presets
    ├── attachment.py    # Workspace file serving (inline images)
    ├── audio.py         # TTS/STT audio events
    ├── auth.py          # Login, logout, token management
    ├── channels.py      # Channel CRUD, webhook, test messaging
    ├── chat.py          # SSE streaming, chat-task status/abort
    ├── config.py        # System config, policies, audit, costs, state
    ├── experience.py    # Agent experience, learning, retrospective
    ├── health.py        # Health check
    ├── hub_sync.py      # Inter-node sync, config deployment
    ├── i18n.py          # Internationalization locale tables
    ├── knowledge.py     # Knowledge base, RAG, domain-KB, vector memory
    ├── mcp.py           # MCP catalog, node config, source editing
    ├── meetings.py      # Meeting management
    ├── nodes.py         # Node listing, config, sync
    ├── personas.py      # Persona templates
    ├── projects.py      # Projects, tasks, milestones, goals, deliverables
    ├── providers.py     # LLM provider management, model detection
    ├── scheduler.py     # Job scheduling, presets
    ├── skills.py        # Skill packages, prompt packs, skill store
    └── workflows.py     # Workflow catalog, execution
```

## Relationship to app/server/ (Legacy)

Both systems currently run in parallel. The legacy system in `app/server/`
uses Python's `BaseHTTPRequestHandler` and will be deprecated once the
FastAPI migration is complete. See `app/server/README.md` for details.

**Do not add new endpoints to app/server/.** All new work goes here.
