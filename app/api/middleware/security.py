"""Security headers middleware for FastAPI.

Uses pure ASGI implementation instead of BaseHTTPMiddleware to avoid
buffering streaming responses (SSE, chunked transfer, etc.).
BaseHTTPMiddleware is known to consume the entire response body before
returning, which breaks Server-Sent Events (SSE) real-time delivery.
"""
from starlette.types import ASGIApp, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Inject standard security headers into every HTTP response.

    Pure ASGI middleware — does NOT buffer streaming responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-xss-protection", b"1; mode=block"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
