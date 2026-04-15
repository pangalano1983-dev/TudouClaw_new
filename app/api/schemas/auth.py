"""Auth-related Pydantic schemas."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login via username+password or token."""
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str
    session_id: Optional[str] = None


class TokenCreateRequest(BaseModel):
    name: str
    role: str = "admin"
    admin_user_id: Optional[str] = None


class TokenInfo(BaseModel):
    id: str
    name: str
    role: str
    created_at: str
    last_used: Optional[str] = None
