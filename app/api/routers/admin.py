"""Admin management router — admins, role presets, user management."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Body

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.admin")

router = APIRouter(prefix="/api/portal", tags=["admin"])


def _get_auth():
    from ...auth import get_auth
    return get_auth()


# ---------------------------------------------------------------------------
# Admin me — matches legacy portal_routes_get
# ---------------------------------------------------------------------------

@router.get("/admin/me")
async def get_admin_me(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get current admin user info + manageable agents."""
    try:
        auth = _get_auth()
        admin_user_id = getattr(user, "admin_user_id", "") or getattr(user, "user_id", "")
        if admin_user_id:
            admin = auth.admin_mgr.get_admin(admin_user_id)
            if admin:
                manageable_agents = hub.list_agents()
                return {
                    "admin": admin.to_dict(include_secrets=False),
                    "manageable_agents": manageable_agents,
                }
        # Fallback for legacy tokens
        if getattr(user, "role", "") == "admin" or getattr(user, "is_super_admin", False):
            return {
                "admin": {
                    "user_id": "",
                    "username": getattr(user, "username", ""),
                    "role": "superAdmin",
                    "display_name": getattr(user, "username", ""),
                    "agent_ids": [],
                    "active": True,
                },
                "manageable_agents": hub.list_agents(),
            }
        return {"admin": None, "manageable_agents": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Admin CRUD — matches legacy portal_routes_post
# ---------------------------------------------------------------------------

@router.post("/admins/list")
async def list_admins(
    body: dict = Body(default={}),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """List all admin users (superAdmin only)."""
    try:
        auth = _get_auth()
        admins = auth.admin_mgr.list_admins()
        return {"admins": admins}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admins/create")
async def create_admin(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new admin user (superAdmin only)."""
    try:
        auth = _get_auth()
        username = body.get("username", "").strip()
        password = body.get("password", "").strip()
        display_name = body.get("display_name", "").strip()
        agent_ids = body.get("agent_ids", [])
        if not username or not password:
            raise HTTPException(400, "username and password required")
        admin = auth.admin_mgr.create_admin(
            username=username,
            password=password,
            display_name=display_name or username,
            agent_ids=agent_ids,
        )
        return {"ok": True, "admin": admin.to_dict(include_secrets=False)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admins/update")
async def update_admin(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Update an admin user (superAdmin only)."""
    try:
        auth = _get_auth()
        user_id = body.get("user_id", "")
        if not user_id:
            raise HTTPException(400, "user_id required")
        kwargs = {}
        if "password" in body:
            kwargs["password"] = body["password"]
        if "display_name" in body:
            kwargs["display_name"] = body["display_name"]
        if "agent_ids" in body:
            kwargs["agent_ids"] = body["agent_ids"]
        if "active" in body:
            kwargs["active"] = body["active"]
        admin = auth.admin_mgr.update_admin(user_id, **kwargs)
        if not admin:
            raise HTTPException(404, "Admin not found")
        return {"ok": True, "admin": admin.to_dict(include_secrets=False)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admins/delete")
async def delete_admin(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Delete an admin user (superAdmin only)."""
    try:
        auth = _get_auth()
        user_id = body.get("user_id", "")
        if not user_id:
            raise HTTPException(400, "user_id required")
        ok = auth.admin_mgr.delete_admin(user_id)
        return {"ok": ok}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admins/bind")
async def bind_agents_to_admin(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Bind agents to an admin user (superAdmin only)."""
    try:
        auth = _get_auth()
        user_id = body.get("user_id", "")
        agent_ids = body.get("agent_ids", [])
        if not user_id:
            raise HTTPException(400, "user_id required")
        admin = auth.admin_mgr.bind_agents(user_id, agent_ids)
        if not admin:
            raise HTTPException(404, "Admin not found")
        return {"ok": True, "admin": admin.to_dict(include_secrets=False)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admins/change-password")
async def change_admin_password(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Change admin password."""
    try:
        auth = _get_auth()
        user_id = body.get("user_id", "") or getattr(user, "user_id", "")
        new_password = body.get("password", "") or body.get("new_password", "")
        if not user_id or not new_password:
            raise HTTPException(400, "user_id and password required")
        admin = auth.admin_mgr.update_admin(user_id, password=new_password)
        if not admin:
            raise HTTPException(404, "Admin not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Role presets
# ---------------------------------------------------------------------------

@router.post("/role-presets/update")
async def update_role_preset(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Create or update a role preset — matches legacy handlers/config.py."""
    try:
        from ...agent import ROLE_PRESETS, AgentProfile
        key = (body.get("key") or "").strip()
        if not key:
            raise HTTPException(400, "key required")
        name = body.get("name", key)
        system_prompt = body.get("system_prompt", "")
        prof_data = body.get("profile", {})
        profile = AgentProfile(
            personality=prof_data.get("personality", ""),
            communication_style=prof_data.get("communication_style", ""),
            expertise=prof_data.get("expertise", []),
            skills=prof_data.get("skills", []),
            allowed_tools=prof_data.get("allowed_tools") or [],
            denied_tools=prof_data.get("denied_tools") or [],
            auto_approve_tools=prof_data.get("auto_approve_tools") or [],
        )
        ROLE_PRESETS[key] = {
            "name": name,
            "system_prompt": system_prompt,
            "profile": profile,
        }
        # Persist custom presets to disk
        from ...server.handlers.config import _save_custom_role_presets
        _save_custom_role_presets()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/role-presets/delete")
async def delete_role_preset(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a role preset — matches legacy handlers/config.py."""
    try:
        from ...agent import ROLE_PRESETS
        key = (body.get("key") or "").strip()
        if not key:
            raise HTTPException(400, "key required")
        if key in ROLE_PRESETS:
            del ROLE_PRESETS[key]
            from ...server.handlers.config import _save_custom_role_presets
            _save_custom_role_presets()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
