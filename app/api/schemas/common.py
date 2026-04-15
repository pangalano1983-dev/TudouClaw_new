"""Common Pydantic schemas shared across routers."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


class PaginatedRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class ActionRequest(BaseModel):
    """Generic request for endpoints that use action-based dispatch."""
    action: str
    data: dict[str, Any] = Field(default_factory=dict)
