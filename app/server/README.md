# app/server/ — Legacy HTTP Backend (Deprecated)

This is the **legacy** HTTP backend built on Python's `BaseHTTPRequestHandler`.
It is being replaced by the FastAPI system in `app/api/`.

## Status: DEPRECATED — Do not add new endpoints here

All new endpoint development should go to `app/api/routers/`.

## Structure

```
app/server/
├── portal_server.py         # BaseHTTPRequestHandler main server
├── portal_routes_get.py     # All GET route dispatch (path == "..." pattern)
├── portal_routes_post.py    # All POST route dispatch
├── portal_templates.py      # HTML templates (login, portal pages)
├── portal_auth.py           # Legacy auth helpers (token validation)
├── html_tag_router.py       # HTML tag routing for SSE streams
├── tools.py                 # Server-side tool helpers
└── static/                  # Static JS/CSS assets
```

## Migration Path

1. Each `if path == "/api/portal/..."` block in portal_routes_get/post.py
   has a corresponding FastAPI endpoint in `app/api/routers/*.py`
2. Once all consumers (frontend + external) are migrated to FastAPI,
   this directory will be removed
3. The FastAPI system runs on the same port — no client-side changes needed
