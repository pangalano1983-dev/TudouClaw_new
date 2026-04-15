"""Internationalization router — locale string tables."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.i18n")

router = APIRouter(prefix="/api/portal", tags=["i18n"])


@router.get("/i18n/{locale}")
async def get_locale_table(
    locale: str,
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get locale string table for a given language code."""
    try:
        from ... import i18n as _i18n
        return {"locale": locale, "table": _i18n.get_locale_table(locale)}
    except (ImportError, Exception) as e:
        raise HTTPException(status_code=500, detail=str(e))
