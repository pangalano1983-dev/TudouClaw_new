"""Dual authentication for routes that serve both UI users AND
inter-node calls.

Worker nodes need to expose endpoints (create_agent, chat, etc.) that
the master can call via X-Hub-Secret. The same endpoints, when called
from a UI on the worker itself, should use JWT. This dep tries both
in order — JWT first (so existing UI calls aren't perturbed), falling
back to X-Hub-Secret if no Bearer token is present.

Returns a CurrentUser either way:
  - JWT path: real user identity (capped per ``_cap_role_for_worker_node``)
  - X-Hub-Secret path: synthetic user_id="hub_proxy", role="admin"
    (NOT superAdmin — even if master signed as superAdmin, the worker
    must enforce the boundary).

This is the only mechanism worker exposes to master for state-changing
calls, so the role grant is intentionally "admin" — enough for normal
agent CRUD but blocked from cluster-level operations (which only
superAdmin would be allowed to do, and superAdmin can never reach a
worker).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import CurrentUser, get_current_user
from .hub_auth import verify_hub_secret

logger = logging.getLogger("tudouclaw.api.dual_auth")

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_user_or_hub_proxy(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """Resolve to a CurrentUser via JWT, falling back to X-Hub-Secret.

    Order:
      1. If Authorization: Bearer <jwt> present → delegate to
         get_current_user (existing behaviour, no surprises for UI).
      2. Else if X-Hub-Secret matches the master's TUDOU_SECRET →
         return synthetic ``hub_proxy`` user with role=admin.
      3. Else → 401 (same as get_current_user would do).
    """
    # JWT path takes priority — no behaviour change for existing
    # authenticated UI calls.
    if credentials and credentials.credentials:
        return await get_current_user(request, credentials)

    # No bearer token — try hub secret. verify_hub_secret raises 401
    # itself when the header is wrong; we let that propagate.
    if request.headers.get("X-Hub-Secret"):
        await verify_hub_secret(request)
        return CurrentUser(
            user_id="hub_proxy",
            role="admin",
            claims={"hub_proxy": True},
        )

    # Neither — fall through to the standard 401.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (no Bearer token, no X-Hub-Secret)",
        headers={"WWW-Authenticate": "Bearer"},
    )


__all__ = ["get_user_or_hub_proxy"]
