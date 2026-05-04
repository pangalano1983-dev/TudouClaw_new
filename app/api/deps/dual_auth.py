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
    """Resolve to a CurrentUser via UI auth (JWT/cookie/token) or X-Hub-Secret.

    Order:
      1. Try ``get_current_user`` first — it knows about three UI paths
         (Bearer JWT, ``td_sess`` cookie, ``X-API-Token``). If any of
         those resolve, return that user (UI behaviour unchanged).
      2. Only when all UI paths fail AND ``X-Hub-Secret`` is present,
         validate the secret and return a synthetic ``hub_proxy``
         user with role=admin (never superAdmin).
      3. Else → 401.

    The earlier version of this dep only checked the Authorization
    bearer header, so portal users who relied on the legacy cookie
    session got 401 here even though their session was valid.
    """
    # Try UI paths first — get_current_user does Bearer / cookie / token
    # internally and raises 401 when none work. We swallow that to fall
    # through to the hub-secret branch (and ultimately a 401 of our own
    # with a clearer detail message).
    try:
        return await get_current_user(request, credentials)
    except HTTPException as ui_exc:
        # Re-raise non-401 (e.g. expired token has the right error
        # already; a generic 500 from upstream we shouldn't mask).
        if ui_exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise

    # No UI auth — try inter-node hub secret.
    if request.headers.get("X-Hub-Secret"):
        await verify_hub_secret(request)
        return CurrentUser(
            user_id="hub_proxy",
            role="admin",
            claims={"hub_proxy": True},
        )

    # Nothing worked.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (need Bearer JWT, td_sess cookie, "
               "X-API-Token, or X-Hub-Secret)",
        headers={"WWW-Authenticate": "Bearer"},
    )


__all__ = ["get_user_or_hub_proxy"]
