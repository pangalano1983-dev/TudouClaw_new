"""Authentication dependency for inter-node ``/api/hub/*`` calls.

Different from ``get_current_user`` (JWT/session) because nodes don't
have user accounts — they authenticate via a shared secret in the
``X-Hub-Secret`` header. The expected value is configured on the
Master via ``TUDOU_SECRET`` env var (or by passing ``shared_secret``
to ``init_auth``).

Each downstream node sets ``TUDOU_UPSTREAM_SECRET`` to the same value;
``app/hub/_core.py`` reads it and attaches it to outbound register/
heartbeat calls.

Dev-mode escape hatch: if the Master has no shared secret configured,
the dependency logs a warning and lets the call through — this keeps
``cargo run``-style local testing usable without forcing operators
to set a secret.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Request, status

logger = logging.getLogger("tudouclaw.api.hub_auth")


async def verify_hub_secret(request: Request) -> str:
    """Validate ``X-Hub-Secret`` against the master's shared secret.

    Returns:
        A short tag string for downstream logging (currently
        ``"hub_node"`` on a real match, ``"unauth_devmode"`` when no
        secret is configured at all).

    Raises:
        HTTPException 401 — header missing, or value mismatched.
    """
    received = request.headers.get("X-Hub-Secret", "").strip()

    # Resolve expected value from auth singleton.
    expected = ""
    try:
        from ...auth import get_auth
        expected = (get_auth()._shared_secret or "").strip()
    except Exception as e:
        logger.debug("hub_auth: could not load auth singleton: %s", e)

    if not expected:
        # Dev mode: master never configured a secret.
        if received:
            # Caller offered a secret but master can't compare. Log so
            # ops can spot mis-configuration; still allow the call so
            # local single-node setups continue to work.
            logger.warning(
                "hub_auth: master has no TUDOU_SECRET — accepting "
                "X-Hub-Secret without verification (dev mode)"
            )
        return "unauth_devmode"

    if not received:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Secret header",
        )

    # Constant-time compare to avoid timing oracles.
    if not hmac.compare_digest(received, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Hub-Secret",
        )

    return "hub_node"


__all__ = ["verify_hub_secret"]
