"""
Portal authentication and authorization helpers.
"""
import logging
from urllib.parse import urlparse

logger = logging.getLogger("tudou.portal")


def _safe_secret_indicator(secret_value: str) -> str:
    """Convert secret value to safe indicator for logging (only shows 'has_secret=true/false')."""
    return bool(secret_value)


def get_client_ip(handler) -> str:
    """Get client IP address from request handler."""
    return handler.client_address[0]


def get_session_cookie(handler) -> str:
    """Extract session cookie from request headers."""
    cookie_header = handler.headers.get("Cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("td_sess="):
            return part.split("=", 1)[1]
    return ""


def set_session_cookie(handler, session_id: str):
    """Set session cookie in response headers with security attributes."""
    import os
    # Use Secure flag in production (HTTPS). In development (HTTP), omit it.
    is_secure = os.environ.get("TUDOU_SECURE_COOKIES", "").lower() in ("true", "1", "yes")
    secure_flag = "; Secure" if is_secure else ""
    handler.send_header("Set-Cookie", f"td_sess={session_id}; Path=/; SameSite=Lax; HttpOnly{secure_flag}")


def require_auth(handler) -> bool:
    """Check if request is authenticated. Return False if not, True if yes."""
    from .portal_server import is_hub_mode
    from ..auth import get_auth

    path = urlparse(handler.path).path
    client_ip = get_client_ip(handler)
    
    # Public endpoints
    if path in ("/", "/index.html", "/api/auth/login", "/api/health"):
        return True
    if path.startswith("/api/auth/login"):
        return True
    
    # Node mode: no login required. Remote-node portals allow direct
    # access (global write ops are still blocked in do_POST/do_DELETE).
    if not is_hub_mode():
        return True
    
    # Channel webhook endpoints are public (external platforms call them)
    if "/webhook" in path and path.startswith("/api/portal/channels/"):
        return True
    
    # Hub endpoints and remote-node agent creation use secret
    if path.startswith("/api/hub/") or path == "/api/portal/agent/create":
        auth = get_auth()
        secret = handler.headers.get("X-Claw-Secret", "")
        # If no shared_secret is configured, allow hub/remote endpoints freely
        if auth.verify_secret(secret):
            logger.debug("AUTH OK (secret/open) path=%s ip=%s has_secret=%s",
                         path, client_ip, bool(secret))
            return True
        else:
            # Log with redacted secret for security (never log the actual secret value)
            logger.warning("AUTH FAIL (bad secret) path=%s ip=%s has_secret=%s",
                         path, client_ip, bool(secret))
    
    auth = get_auth()
    # 1) Bearer token
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth.validate_token(auth_header[7:].strip())
        if token:
            logger.debug("AUTH OK (bearer) path=%s user=%s", path, token.name)
            return True
    
    # 2) Session cookie
    session_id = get_session_cookie(handler)
    if session_id and auth.validate_session(session_id):
        return True
    
    logger.warning("AUTH REJECTED path=%s ip=%s method=%s", path, client_ip, handler.command)
    handler._json({"error": "Unauthorized"}, 401)
    return False


def get_auth_info(handler) -> tuple[str, str]:
    """Get (actor_name, role) from current request. Call after require_auth."""
    from .portal_server import is_hub_mode
    from ..auth import get_auth

    auth = get_auth()
    
    # Bearer token
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth.validate_token(auth_header[7:].strip())
        if token:
            return (token.name, token.role)
    
    # Session cookie
    session_id = get_session_cookie(handler)
    if session_id:
        session = auth.validate_session(session_id)
        if session:
            return (session.name, session.role)
    
    # Node mode: grant operator role by default (node-level writes allowed,
    # global writes are blocked via _admin_only_paths in do_POST/DELETE)
    if not is_hub_mode():
        return ("node-user", "operator")
    
    return ("anonymous", "viewer")


def get_admin_context(handler) -> str:
    """Get admin_user_id from current session. Returns empty string if not an admin session."""
    from ..auth import get_auth
    
    auth = get_auth()
    session_id = get_session_cookie(handler)
    if session_id:
        session = auth.validate_session(session_id)
        if session and session.admin_user_id:
            return session.admin_user_id
    return ""


def is_super_admin(handler) -> bool:
    """Check if current user is a superAdmin."""
    from ..auth import get_auth, AdminRole
    
    admin_user_id = get_admin_context(handler)
    if admin_user_id:
        auth = get_auth()
        admin = auth.admin_mgr.get_admin(admin_user_id)
        if admin:
            return admin.role == AdminRole.SUPER_ADMIN.value
    
    # Fallback: check if session role is "admin" (legacy token with role=admin)
    auth = get_auth()
    session_id = get_session_cookie(handler)
    if session_id:
        session = auth.validate_session(session_id)
        if session and session.role == "admin":
            return True
    return False


def get_visible_agents(handler, hub, admin_user_id: str) -> list[dict]:
    """Get list of agents visible to the given admin user.

    If admin_user_id is empty or maps to superAdmin, return all agents.
    If maps to regular admin, return only agents in their agent_ids list.
    """
    from ..auth import get_auth, AdminRole

    all_agents = hub.list_agents()
    if not admin_user_id:
        return all_agents
    
    auth = get_auth()
    admin = auth.admin_mgr.get_admin(admin_user_id)
    if not admin:
        return []
    
    if admin.role == AdminRole.SUPER_ADMIN.value:
        return all_agents
    
    # Regular admin: filter by agent_ids
    return [a for a in all_agents if a.get("id") in admin.agent_ids]
