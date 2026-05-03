"""JWT-based authentication dependency for FastAPI.

Supports two auth modes (backward compatible):
  1. JWT Bearer token in Authorization header (new, preferred)
  2. Session cookie td_sess (legacy, for migration period)
"""
from __future__ import annotations

import os
import time
import hmac
import hashlib
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("tudouclaw.api.auth")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JWT_SECRET = os.environ.get("TUDOU_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = int(os.environ.get("TUDOU_JWT_EXPIRE", "86400"))  # 24h

# Auto-generate secret on first run if not set
if not JWT_SECRET:
    JWT_SECRET = hashlib.sha256(
        os.environ.get("TUDOU_ADMIN_SECRET", "tudouclaw-dev-secret").encode()
    ).hexdigest()

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    role: str = "admin",
    extra: dict | None = None,
) -> str:
    """Create a JWT access token."""
    now = time.time()
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now),
        "exp": int(now) + JWT_EXPIRE_SECONDS,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

class CurrentUser:
    """Represents an authenticated user.

    Extended with the user's delegation lists so permission checks in
    ``app.permissions`` don't need to re-hit the admin manager on every
    API call. Populated by ``get_current_user`` at request time.
    """
    __slots__ = ("user_id", "role", "claims",
                 "delegated_agent_ids", "delegated_node_ids",
                 "_perm_cache")

    def __init__(self, user_id: str, role: str = "admin",
                 claims: dict | None = None,
                 delegated_agent_ids: list | None = None,
                 delegated_node_ids: list | None = None):
        self.user_id = user_id
        self.role = role
        self.claims = claims or {}
        self.delegated_agent_ids = list(delegated_agent_ids or [])
        self.delegated_node_ids = list(delegated_node_ids or [])
        # Scratch cache for app.permissions._lookup_admin_lists fallback.
        self._perm_cache = None

    @property
    def is_super_admin(self) -> bool:
        return self.role == "superAdmin"


def _fetch_delegation(user_id: str) -> tuple[list[str], list[str]]:
    """Resolve (delegated_agent_ids, delegated_node_ids) from the
    admin manager. Returns ([], []) if user has no admin record, isn't
    persisted yet, or the admin manager can't be loaded. Callers must
    never depend on non-empty lists — absence means "no delegation"
    which is correct for regular users and brand-new admins."""
    if not user_id:
        return [], []
    try:
        from ...auth import get_auth
        admin = get_auth().admin_mgr.get_admin(user_id)
        if admin is None:
            return [], []
        return (list(admin.agent_ids or []),
                list(admin.node_ids or []))
    except Exception as e:
        logger.debug("delegation lookup failed for %s: %s", user_id[:12], e)
        return [], []


def _cap_role_for_worker_node(role: str) -> str:
    """Worker nodes never grant superAdmin.

    The master owns the canonical admin store; superAdmin operations
    (managing other admins, cluster-wide policy) are meaningless on a
    downstream worker. If a token issued by the master arrives with
    role=superAdmin, downgrade it to admin so the request is still
    authorised for normal operations but blocked from superAdmin-only
    surfaces.

    Safe on the master too — ``is_worker_node`` is False there.
    """
    if role != "superAdmin":
        return role
    try:
        from .hub import get_hub
        hub = get_hub()
        if getattr(hub, "is_worker_node", False):
            return "admin"
    except Exception:
        # Hub not initialised yet (early request during startup)
        # — be conservative, leave role alone.
        pass
    return role


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """Extract and validate user from JWT or legacy session cookie.

    Priority:
      1. Authorization: Bearer <jwt>
      2. Cookie: td_sess=<session_id>  (legacy bridge to old auth system)

    Worker-node side note: when the local hub has ``TUDOU_UPSTREAM_HUB``
    set (i.e. ``hub.is_worker_node``), an incoming role of
    ``superAdmin`` is downgraded to ``admin``. See
    ``_cap_role_for_worker_node``.
    """
    # --- Try JWT Bearer first ---
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            uid = payload.get("sub", "")
            role = _cap_role_for_worker_node(payload.get("role", "admin"))
            # Look up the admin record to populate delegation lists.
            # Non-admin users (role="user") won't be in admin_mgr — that's
            # fine, empty delegation lists are correct for them.
            deleg_agents, deleg_nodes = _fetch_delegation(uid)
            return CurrentUser(
                user_id=uid,
                role=role,
                claims=payload,
                delegated_agent_ids=deleg_agents,
                delegated_node_ids=deleg_nodes,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # --- Fallback: legacy session cookie ---
    session_id = request.cookies.get("td_sess")
    if session_id:
        try:
            from ...auth import get_auth
            auth = get_auth()
            session = auth.validate_session(session_id)
            if session:
                # Resolve the real admin role from admin_mgr (session.role is a
                # coarse Role enum — "admin"/"operator" — and loses the
                # superAdmin distinction). Fall back to session.role otherwise.
                effective_role = getattr(session, "role", "admin")
                admin_uid = getattr(session, "admin_user_id", "")
                if admin_uid:
                    try:
                        admin = auth.admin_mgr.get_admin(admin_uid)
                        if admin and getattr(admin, "role", ""):
                            effective_role = admin.role
                    except Exception:
                        pass
                # Bridge: create a CurrentUser from the WebSession
                bridged_uid = admin_uid or getattr(session, "name", "legacy")
                deleg_agents, deleg_nodes = _fetch_delegation(bridged_uid)
                return CurrentUser(
                    user_id=bridged_uid,
                    role=_cap_role_for_worker_node(effective_role),
                    claims={"session": True, "session_id": session_id},
                    delegated_agent_ids=deleg_agents,
                    delegated_node_ids=deleg_nodes,
                )
        except Exception as e:
            logger.debug("Legacy session validation failed: %s", e)

    # --- Fallback: old-style API token in header ---
    api_token = request.headers.get("X-API-Token") or request.query_params.get("token")
    if api_token:
        try:
            from ...auth import get_auth
            auth = get_auth()
            if auth.validate_token(api_token):
                return CurrentUser(
                    user_id="token_user",
                    role=_cap_role_for_worker_node("admin"),
                )
        except Exception as e:
            logger.debug("API token validation failed: %s", e)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[CurrentUser]:
    """Like get_current_user but returns None instead of 401."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None
