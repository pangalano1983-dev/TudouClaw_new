"""LoginGuard — transparent login-wall handler in the tool execution pipeline.

Architecture
============
When an Agent calls any web-facing tool (mcp_call with browser, web_fetch,
http_request …) and the result looks like a login page, LoginGuard
**automatically** shows a login card to the user, waits for credentials,
then retries the original tool call with the now-authenticated session.

The LLM never needs to decide "should I call request_web_login?" — it is
entirely transparent.  The LLM sees the post-login page content as if the
login wall never existed.

Integration point
-----------------
``Agent._execute_tool_guarded()`` wraps every ``tools.execute_tool()`` call
with ``LoginGuard.guard()``.  No other code changes are needed.

Extensibility
-------------
* ``LoginDetector`` is a dataclass — override any field to customize
  URL patterns, keywords, guarded tool names, etc.
* Subclass ``LoginDetector.detect()`` for site-specific logic.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    pass  # avoid circular imports; Agent is only used for type hints

logger = logging.getLogger("tudouclaw.login_guard")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass
class LoginSignal:
    """Payload describing a detected login requirement."""
    url: str = ""
    login_url: str = ""
    site_name: str = ""
    reason: str = "Login required to access this page"


@dataclass
class LoginDetector:
    """Configurable login-page detection strategy.

    All fields are overridable at construction time::

        detector = LoginDetector(url_patterns=("/my-login",), min_keyword_hits=3)

    Detection fires when:
      * The result URL matches any ``url_patterns``, **or**
      * Content keyword hits >= ``min_keyword_hits`` AND (HTTP status is
        401/403 **or** hits >= ``keyword_hard_threshold``).
    """

    # URL path fragments that indicate a login/auth page.
    url_patterns: tuple[str, ...] = (
        "/login", "/signin", "/sign-in", "/sign_in",
        "/auth/", "/oauth", "/sso/", "/passport",
        "/account/login", "/user/login",
    )

    # Text keywords found on login pages (case-insensitive matching).
    content_keywords: tuple[str, ...] = (
        "sign in", "log in", "login", "登录", "登陆",
        "password", "密码", "forgot password", "忘记密码",
        "验证码", "请输入账号",
    )

    # HTTP status codes that signal authentication required.
    status_codes: tuple[int, ...] = (401, 403)

    # Minimum keyword hits (with a supporting status code) to trigger.
    min_keyword_hits: int = 2

    # Keyword hits alone (no status code) that are strong enough to trigger.
    keyword_hard_threshold: int = 3

    # Top-level tool names that access the web.
    guarded_tools: frozenset[str] = frozenset((
        "mcp_call", "web_fetch", "http_request", "web_screenshot",
    ))

    # MCP sub-tool names whose results carry URL + page info.
    browser_nav_tools: frozenset[str] = frozenset((
        "browser_navigate", "browser_goto", "navigate",
        "playwright_navigate", "puppeteer_navigate",
    ))

    # ------------------------------------------------------------------ #

    def detect(
        self,
        tool_name: str,
        arguments: dict,
        result: str,
    ) -> Optional[LoginSignal]:
        """Return a ``LoginSignal`` if *result* looks like a login page."""
        if tool_name not in self.guarded_tools:
            return None

        lower = result.lower() if isinstance(result, str) else ""
        if not lower:
            return None

        url, site_name = self._extract_url(tool_name, arguments, result)

        url_match = self._check_url(url)
        keyword_hits = self._count_keywords(lower)
        status_match = self._check_status(lower)

        triggered = (
            url_match
            or (keyword_hits >= self.min_keyword_hits and status_match)
            or (keyword_hits >= self.keyword_hard_threshold)
        )
        if not triggered:
            return None

        if not site_name and url:
            try:
                site_name = urlparse(url).hostname or ""
            except Exception:
                site_name = ""

        return LoginSignal(
            url=url,
            login_url=url,
            site_name=site_name,
            reason=f"Login required to access {site_name or url or 'this page'}",
        )

    # ---- helpers ----

    def _check_url(self, url: str) -> bool:
        lower_url = url.lower()
        return any(p in lower_url for p in self.url_patterns)

    def _count_keywords(self, lower_text: str) -> int:
        return sum(1 for kw in self.content_keywords if kw in lower_text)

    def _check_status(self, lower_text: str) -> bool:
        for code in self.status_codes:
            if f'"status": {code}' in lower_text or f'"status_code": {code}' in lower_text:
                return True
        return False

    def _extract_url(
        self, tool_name: str, arguments: dict, result: str,
    ) -> tuple[str, str]:
        """Best-effort URL + site_name extraction from a tool result."""
        url = ""
        site_name = ""

        if tool_name == "mcp_call":
            # Only inspect results from navigational browser sub-tools.
            sub_tool = str(arguments.get("tool", "")).lower()
            if sub_tool and sub_tool not in self.browser_nav_tools:
                # e.g. browser_screenshot — no URL to parse.
                return "", ""
            try:
                data = json.loads(result) if isinstance(result, str) else result
                if isinstance(data, dict):
                    url = str(data.get("url", "") or "")
                    title = str(data.get("title", "") or "")
                    if title:
                        site_name = title.split(" - ")[0].split(" | ")[0].strip()
            except (json.JSONDecodeError, TypeError):
                pass
            # Fallback: URL from arguments
            if not url:
                args = arguments.get("arguments", {})
                if isinstance(args, dict):
                    url = str(args.get("url", "") or "")

        elif tool_name in ("web_fetch", "http_request"):
            url = str(arguments.get("url", "") or "")

        return url, site_name


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

class LoginGuard:
    """Transparent login-wall handler.

    Sits between ``tools.execute_tool()`` and the caller.  When a login page
    is detected the guard:

    1. Emits an SSE ``login_request`` event (chat UI shows the login card).
    2. Blocks until the user submits credentials / confirms login.
    3. Retries the original tool call (the browser session is now authed).
    4. Returns the **post-login** result to the LLM — completely transparent.

    Session memory
    --------------
    ``_attempted`` tracks domains that have been presented to the user
    (succeeded or timed out).  ``_authenticated`` tracks domains where
    the user successfully logged in.  A domain that was attempted but
    NOT authenticated is never retried — the user already declined or
    was absent.
    """

    def __init__(self, detector: LoginDetector | None = None):
        self.detector = detector or LoginDetector()
        # domain → True (success) / False (failed/expired)
        self._attempted: dict[str, bool] = {}

    # ------------------------------------------------------------------ #
    # Public helpers — used by both guard() and _handle_web_login_request
    # ------------------------------------------------------------------ #

    @staticmethod
    def _domain_key(url: str) -> str:
        """Extract a stable domain key from a URL."""
        try:
            host = urlparse(url).hostname or ""
            # Strip leading "www."
            if host.startswith("www."):
                host = host[4:]
            return host.lower()
        except Exception:
            return url.lower()

    def already_attempted(self, url: str) -> bool:
        """Return True if this domain was already attempted (success or fail)."""
        return self._domain_key(url) in self._attempted

    def was_authenticated(self, url: str) -> bool:
        """Return True if this domain was successfully authenticated."""
        return self._attempted.get(self._domain_key(url), False)

    def record_attempt(self, url: str, success: bool) -> None:
        """Record a login attempt result for this domain."""
        self._attempted[self._domain_key(url)] = success

    def guard(
        self,
        agent: Any,
        tool_name: str,
        arguments: dict,
        result: str,
        *,
        retry_fn: Callable[[], str] | None = None,
        on_event: Any = None,
    ) -> str:
        """Inspect *result* for login signals; if found, handle and retry.

        Parameters
        ----------
        agent : Agent
            The running Agent (provides ``_handle_web_login_request``
            and ``_credential_vault``).
        tool_name : str
            The tool that produced *result*.
        arguments : dict
            Arguments that were passed to the tool.
        result : str
            The tool's return string.
        retry_fn : callable, optional
            Re-executes the original tool call.  Called after successful login.
        on_event : callable, optional
            SSE event emitter (passed through to the login flow).

        Returns
        -------
        str
            *result* unchanged if no login detected, or the retried result
            after a successful login.
        """
        signal = self.detector.detect(tool_name, arguments, result)
        if signal is None:
            return result

        # Prevent infinite loops: don't re-handle the same domain.
        key_url = signal.url or signal.login_url or ""
        if self.already_attempted(key_url):
            if self.was_authenticated(key_url):
                logger.debug("LoginGuard: %s already authenticated, returning result as-is", key_url)
            else:
                logger.debug("LoginGuard: %s already failed/skipped, not retrying", key_url)
            return result

        logger.info("LoginGuard: login detected at %s — triggering login flow", key_url)

        # Delegate to the Agent's existing login-request machinery
        # (PendingLoginRequest → SSE → block → user submits → unblock).
        login_args = {
            "url": signal.url,
            "login_url": signal.login_url,
            "site_name": signal.site_name,
            "reason": signal.reason,
        }
        try:
            login_result_str = agent._handle_web_login_request(
                login_args, on_event=on_event,
            )
            login_result = json.loads(login_result_str)
        except Exception as exc:
            logger.warning("LoginGuard: login flow error: %s", exc)
            self.record_attempt(key_url, False)
            return result

        if not login_result.get("ok"):
            logger.info("LoginGuard: login skipped or failed, returning original result")
            self.record_attempt(key_url, False)
            return result

        # Login succeeded
        self.record_attempt(key_url, True)

        # Retry the original tool call with the now-authenticated session.
        if retry_fn is not None:
            logger.info("LoginGuard: login succeeded, retrying %s", tool_name)
            try:
                retried = retry_fn()
                return retried
            except Exception as exc:
                logger.warning("LoginGuard: retry failed: %s", exc)
                return result

        # No retry function — just return the original (caller may handle).
        return result
