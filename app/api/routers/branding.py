"""Branding (site name + logo) — admin-managed, single deployment.

3 endpoints:
  * GET  /api/portal/branding         — public read (no auth) so the
                                         login page can render the logo too
  * POST /api/portal/branding         — admin update (requires auth)
  * POST /api/portal/branding/reset   — admin restore defaults
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Body

from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.branding")

router = APIRouter(prefix="/api/portal", tags=["branding"])


def _store_or_503():
    from ...branding import get_store
    s = get_store()
    if s is None:
        raise HTTPException(503, "branding store not initialized")
    return s


@router.get("/branding")
async def get_branding():
    """Read current branding. UNAUTHENTICATED on purpose — needed
    by the login page to render the logo before the user logs in."""
    store = _store_or_503()
    return store.get()


@router.post("/branding")
async def update_branding(
    body: dict = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Patch site_name / site_subtitle / logo_url. Empty string for
    any field clears it back to the default ("Tudou Claws" etc).
    Admin-only — relies on get_current_user to gate."""
    store = _store_or_503()
    try:
        return store.update(body or {})
    except Exception as e:
        logger.exception("branding update failed")
        raise HTTPException(500, str(e))


@router.post("/branding/reset")
async def reset_branding(
    user: CurrentUser = Depends(get_current_user),
):
    """Wipe all customizations and restore defaults."""
    store = _store_or_503()
    return store.reset()
