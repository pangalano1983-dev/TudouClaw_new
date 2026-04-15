"""
Domain-specific POST route handlers.

Each handler module exports:
  try_handle(handler, path, hub, body, auth, actor_name, user_role) -> bool

Some also export:
  try_handle_public(handler, path, hub, body, auth) -> bool  (pre-auth)
"""
from . import auth, config, hub_sync, channels, scheduler, providers, agents, projects

# Ordered list: public handlers checked before auth, then domain handlers after.
PUBLIC_HANDLERS = [auth]

DOMAIN_HANDLERS = [
    config,
    hub_sync,
    channels,
    scheduler,
    providers,
    agents,
    projects,
]
